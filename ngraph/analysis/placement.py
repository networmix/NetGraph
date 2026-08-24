"""Core demand placement with SPF caching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import netgraph_core
import numpy as np

from ngraph.analysis.static_paths import build_static_path_bundles
from ngraph.model.demand.spec import StaticPath
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy

if TYPE_CHECKING:
    from ngraph.analysis.context import AnalysisContext
    from ngraph.analysis.demand import ExpandedDemand

CACHEABLE_PRESETS: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
        FlowPolicyPreset.TE_WCMP_UNLIM,
    }
)

_CACHEABLE_TE: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.TE_WCMP_UNLIM,
    }
)

# Threshold for recording a placed amount as a flow entry. The core engine
# itself never augments below kMinFlow = 1/4096 (see NetGraph-Core
# constants.hpp), so any nonzero amount it returns clears this comfortably.
_MIN_FLOW = 1e-9

# Cached-path FlowIndex ids start far above the ids Core's FlowPolicy assigns
# internally (0..max_flow_count, <= 256), so a cached demand and a
# policy-based demand sharing (src, dst, priority) can never produce the same
# FlowIndex. Duplicate FlowIndex values silently merge flows in FlowGraph,
# corrupting placement totals.
_CACHED_FLOW_ID_BASE = 1 << 20


@dataclass(slots=True)
class PlacementSummary:
    """Aggregated placement totals."""

    total_demand: float
    total_placed: float

    @property
    def ratio(self) -> float:
        return self.total_placed / self.total_demand if self.total_demand > 0 else 1.0

    @property
    def is_feasible(self) -> bool:
        return self.ratio >= 1.0 - 1e-12


@dataclass(slots=True)
class PlacementEntry:
    """Single demand placement result."""

    src_name: str
    dst_name: str
    priority: int
    volume: float
    placed: float
    cost_distribution: dict[float, float] = field(default_factory=dict)
    used_edges: set[str] = field(default_factory=set)


@dataclass(slots=True)
class PlacementResult:
    """Result of one `place_demands` call.

    Attributes:
        summary: Aggregated demand and placed totals.
        entries: Per-demand results, or None unless the call passed
            ``collect_entries=True``.
    """

    summary: PlacementSummary
    entries: list[PlacementEntry] | None = None


def _get_edge_selection(preset: FlowPolicyPreset) -> netgraph_core.EdgeSelection:
    """Get EdgeSelection for a cacheable preset."""
    if preset in (
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
    ):
        return netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=False,
            tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
        )
    return netgraph_core.EdgeSelection(
        multi_edge=True,
        require_capacity=True,
        tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
    )


def _get_flow_placement(preset: FlowPolicyPreset) -> netgraph_core.FlowPlacement:
    """Get FlowPlacement for a cacheable preset."""
    if preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP:
        return netgraph_core.FlowPlacement.EQUAL_BALANCED
    return netgraph_core.FlowPlacement.PROPORTIONAL


def place_demands(
    demands: Sequence["ExpandedDemand"],
    volumes: Sequence[float],
    flow_graph: netgraph_core.FlowGraph,
    ctx: "AnalysisContext",
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    *,
    resolved_ids: Sequence[tuple[int, int]] | None = None,
    collect_entries: bool = False,
    include_cost_distribution: bool = False,
    include_used_edges: bool = False,
    dag_cache: dict[tuple[int, bool], tuple[np.ndarray, Any]] | None = None,
) -> PlacementResult:
    """Place demands on a flow graph with SPF caching.

    Args:
        demands: Expanded demands (policy_preset, priority, names).
        volumes: Volume per demand, positionally aligned with `demands`;
            passed separately so callers can scale without rebuilding demands.
        flow_graph: Target FlowGraph; placed flow accumulates here.
        ctx: AnalysisContext holding the built graph and Core algorithms.
        node_mask: Node inclusion mask (True = include), as built by
            ctx.build_node_mask.
        edge_mask: Edge inclusion mask (True = include), as built by
            ctx.build_edge_mask.
        resolved_ids: Pre-resolved (src_id, dst_id) pairs. Computed from the
            demand names if None.
        collect_entries: If True, populate result.entries.
        include_cost_distribution: Include cost distribution in entries.
        include_used_edges: Include used edges in entries.
        dag_cache: Optional persistent SPF DAG cache keyed by
            (src_id, uses_capacity_aware_selection). Base DAGs depend only on
            the static graph and masks, so repeated calls with the same
            context and masks (e.g. MSD probes) can share one cache.

    Returns:
        PlacementResult with summary and optional entries.

    Raises:
        ValueError: If a demand endpoint is not present in ``ctx``'s graph
            (checked only when ``resolved_ids`` is not supplied). Pseudo node
            names embed demand ids, so this usually means the context was
            built from a different demands_config.
        ValueError: If two policy-based demands (presets outside
            CACHEABLE_PRESETS) share the same (src, dst, priority): their
            FlowIndex values would collide and silently merge in FlowGraph.
        ValueError: If ``demands``, ``volumes``, and ``resolved_ids`` are not
            all the same length.
    """
    if resolved_ids is None:
        try:
            resolved_ids = [
                (ctx.node_mapper.to_id(d.src_name), ctx.node_mapper.to_id(d.dst_name))
                for d in demands
            ]
        except KeyError as exc:
            raise ValueError(
                f"Demand endpoint {exc.args[0]!r} is not present in the "
                "analysis context graph. The context was likely built from a "
                "different demands_config (pseudo node names embed demand "
                "ids); rebuild the context from the same config."
            ) from exc

    if dag_cache is None:
        dag_cache = {}
    entries: list[PlacementEntry] | None = [] if collect_entries else None
    total_demand = 0.0
    total_placed = 0.0
    flow_idx_counter = _CACHED_FLOW_ID_BASE
    # Core's FlowPolicy assigns flow ids internally per policy instance, so
    # two policy-based demands sharing (src, dst, priority) would produce
    # colliding FlowIndex values and silently merge/steal each other's flows.
    policy_triples: set[tuple[int, int, int]] = set()

    for demand, volume, (src_id, dst_id) in zip(
        demands, volumes, resolved_ids, strict=True
    ):
        total_demand += volume

        if demand.policy_preset in CACHEABLE_PRESETS and not demand.static_paths:
            placed, cost_dist, used_edges, flow_idx_counter = _place_cached(
                src_id,
                dst_id,
                volume,
                demand.priority,
                demand.policy_preset,
                dag_cache,
                ctx,
                flow_graph,
                node_mask,
                edge_mask,
                flow_idx_counter,
                include_cost_distribution,
                include_used_edges,
            )
        else:
            triple = (src_id, dst_id, demand.priority)
            if triple in policy_triples:
                same_pair = (
                    f"source '{demand.src_name}', destination "
                    f"'{demand.dst_name}', priority {demand.priority}"
                )
                if demand.static_paths:
                    raise ValueError(
                        f"Two demands pinned to static paths share {same_pair}. "
                        "Their flow ids would collide and corrupt placement. "
                        "List every route on a single demand, or give the "
                        "demands distinct priorities."
                    )
                raise ValueError(
                    f"Duplicate policy-based demand for {same_pair}: flow ids "
                    "would collide and corrupt placement. Merge the demand "
                    "volumes or use distinct priorities."
                )
            policy_triples.add(triple)
            placed, cost_dist, used_edges = _place_with_policy(
                src_id,
                dst_id,
                volume,
                demand.priority,
                demand.policy_preset,
                ctx,
                flow_graph,
                node_mask,
                edge_mask,
                include_cost_distribution,
                include_used_edges,
                static_paths=demand.static_paths,
                src_name=demand.src_name,
                dst_name=demand.dst_name,
            )

        total_placed += placed

        if entries is not None:
            entries.append(
                PlacementEntry(
                    src_name=demand.src_name,
                    dst_name=demand.dst_name,
                    priority=demand.priority,
                    volume=volume,
                    placed=placed,
                    cost_distribution=cost_dist if include_cost_distribution else {},
                    used_edges=used_edges if include_used_edges else set(),
                )
            )

    return PlacementResult(
        summary=PlacementSummary(total_demand=total_demand, total_placed=total_placed),
        entries=entries,
    )


def _place_cached(
    src_id: int,
    dst_id: int,
    volume: float,
    priority: int,
    preset: FlowPolicyPreset,
    dag_cache: dict[tuple[int, bool], tuple[np.ndarray, Any]],
    ctx: "AnalysisContext",
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    flow_idx_start: int,
    include_cost_distribution: bool,
    include_used_edges: bool,
) -> tuple[float, dict[float, float], set[str], int]:
    """Place single demand with SPF caching."""
    selection = _get_edge_selection(preset)
    placement = _get_flow_placement(preset)
    is_te = preset in _CACHEABLE_TE
    # ECMP and WCMP share one EdgeSelection; TE presets share the other.
    # Keying by selection family (not preset) lets mixed workloads reuse
    # the same base SPF DAG.
    cache_key = (src_id, is_te)

    flow_indices: list[netgraph_core.FlowIndex] = []
    flow_costs: list[tuple[float, float]] = []
    flow_idx_counter = flow_idx_start
    placed = 0.0
    remaining = volume

    if cache_key not in dag_cache:
        dists, dag = ctx.algorithms.spf(
            ctx.handle,
            src=src_id,
            dst=None,
            selection=selection,
            node_mask=node_mask,
            edge_mask=edge_mask,
            multipath=True,
            dtype="float64",
        )
        dag_cache[cache_key] = (dists, dag)

    dists, dag = dag_cache[cache_key]

    if dists[dst_id] == float("inf"):
        return 0.0, {}, set(), flow_idx_counter

    cost = float(dists[dst_id])

    flow_idx = netgraph_core.FlowIndex(src_id, dst_id, priority, flow_idx_counter)
    flow_idx_counter += 1
    amount = flow_graph.place(flow_idx, src_id, dst_id, dag, remaining, placement)

    if amount > _MIN_FLOW:
        flow_indices.append(flow_idx)
        flow_costs.append((cost, amount))
        placed += amount
        remaining -= amount

    if is_te and remaining > _MIN_FLOW:
        for _ in range(100):
            residual = np.ascontiguousarray(
                flow_graph.residual_view(), dtype=np.float64
            )
            # Note: Do NOT cache residual-based DAGs. The TE loop computes
            # DAGs specific to this demand's placement; caching them would
            # corrupt results for other demands from the same source.
            fresh_dists, fresh_dag = ctx.algorithms.spf(
                ctx.handle,
                src=src_id,
                dst=None,
                selection=selection,
                residual=residual,
                node_mask=node_mask,
                edge_mask=edge_mask,
                multipath=True,
                dtype="float64",
            )

            if fresh_dists[dst_id] == float("inf"):
                break

            fresh_cost = float(fresh_dists[dst_id])
            flow_idx = netgraph_core.FlowIndex(
                src_id, dst_id, priority, flow_idx_counter
            )
            flow_idx_counter += 1
            additional = flow_graph.place(
                flow_idx, src_id, dst_id, fresh_dag, remaining, placement
            )

            if additional < _MIN_FLOW:
                break

            flow_indices.append(flow_idx)
            flow_costs.append((fresh_cost, additional))
            placed += additional
            remaining -= additional

            if remaining < _MIN_FLOW:
                break

    cost_dist: dict[float, float] = {}
    if include_cost_distribution:
        for c, amt in flow_costs:
            cost_dist[c] = cost_dist.get(c, 0.0) + amt

    used_edges: set[str] = set()
    if include_used_edges:
        ext_ids = ctx.multidigraph.ext_edge_ids_view()
        for fidx in flow_indices:
            for edge_id, _ in flow_graph.get_flow_edges(fidx):
                ref = ctx.edge_mapper.decode_ext_id(int(ext_ids[edge_id]))
                if ref:
                    used_edges.add(f"{ref.link_id}:{ref.direction}")

    return placed, cost_dist, used_edges, flow_idx_counter


def _place_with_policy(
    src_id: int,
    dst_id: int,
    volume: float,
    priority: int,
    preset: FlowPolicyPreset,
    ctx: "AnalysisContext",
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    include_cost_distribution: bool,
    include_used_edges: bool,
    static_paths: Sequence[StaticPath] = (),
    src_name: str = "",
    dst_name: str = "",
) -> tuple[float, dict[float, float], set[str]]:
    """Place a single demand using FlowPolicy.

    Used for non-cacheable presets and for any demand pinned to explicit
    routes. With `static_paths` the policy is pinned to those routes: one flow
    per route, and a route broken by the masks carries nothing.
    """
    policy = create_flow_policy(
        ctx.algorithms,
        ctx.handle,
        preset,
        node_mask=node_mask,
        edge_mask=edge_mask,
        static_path_count=len(static_paths) or None,
    )
    if static_paths:
        bundles = build_static_path_bundles(ctx, static_paths, src_name, dst_name)
        policy.set_static_paths(src_id, dst_id, bundles)
    placed, _ = policy.place_demand(flow_graph, src_id, dst_id, priority, volume)

    cost_dist: dict[float, float] = {}
    used_edges: set[str] = set()

    if include_cost_distribution or include_used_edges:
        ext_ids = ctx.multidigraph.ext_edge_ids_view()
        for flow_key, flow_data in policy.flows.items():
            if include_cost_distribution:
                cost, flow_vol = float(flow_data[2]), float(flow_data[3])
                if flow_vol > 0:
                    cost_dist[cost] = cost_dist.get(cost, 0.0) + flow_vol

            if include_used_edges:
                fidx = netgraph_core.FlowIndex(
                    flow_key[0], flow_key[1], flow_key[2], flow_key[3]
                )
                for edge_id, _ in flow_graph.get_flow_edges(fidx):
                    ref = ctx.edge_mapper.decode_ext_id(int(ext_ids[edge_id]))
                    if ref:
                        used_edges.add(f"{ref.link_id}:{ref.direction}")

    return placed, cost_dist, used_edges
