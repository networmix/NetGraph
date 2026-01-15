"""Core demand placement with SPF caching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Sequence

import netgraph_core
import numpy as np

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

_MIN_FLOW = 1e-9


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
    """Complete placement result."""

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
) -> PlacementResult:
    """Place demands on a flow graph with SPF caching.

    Args:
        demands: Expanded demands (policy_preset, priority, names).
        volumes: Demand volumes (allows scaling without modifying demands).
        flow_graph: Target FlowGraph.
        ctx: AnalysisContext with graph infrastructure.
        node_mask: Node inclusion mask.
        edge_mask: Edge inclusion mask.
        resolved_ids: Pre-resolved (src_id, dst_id) pairs. Computed if None.
        collect_entries: If True, populate result.entries.
        include_cost_distribution: Include cost distribution in entries.
        include_used_edges: Include used edges in entries.

    Returns:
        PlacementResult with summary and optional entries.
    """
    if resolved_ids is None:
        resolved_ids = [
            (ctx.node_mapper.to_id(d.src_name), ctx.node_mapper.to_id(d.dst_name))
            for d in demands
        ]

    dag_cache: dict[tuple[int, FlowPolicyPreset], tuple[np.ndarray, Any]] = {}
    entries: list[PlacementEntry] | None = [] if collect_entries else None
    total_demand = 0.0
    total_placed = 0.0
    flow_idx_counter = 0

    for demand, volume, (src_id, dst_id) in zip(
        demands, volumes, resolved_ids, strict=True
    ):
        total_demand += volume

        if demand.policy_preset in CACHEABLE_PRESETS:
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
    dag_cache: dict[tuple[int, FlowPolicyPreset], tuple[np.ndarray, Any]],
    ctx: "AnalysisContext",
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    flow_idx_start: int,
    include_cost_distribution: bool,
    include_used_edges: bool,
) -> tuple[float, dict[float, float], set[str], int]:
    """Place single demand with SPF caching."""
    cache_key = (src_id, preset)
    selection = _get_edge_selection(preset)
    placement = _get_flow_placement(preset)
    is_te = preset in _CACHEABLE_TE

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
        for fidx in flow_indices:
            for edge_id, _ in flow_graph.get_flow_edges(fidx):
                ref = ctx.edge_mapper.to_ref(edge_id, ctx.multidigraph)
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
) -> tuple[float, dict[float, float], set[str]]:
    """Place single demand using FlowPolicy (for non-cacheable presets)."""
    policy = create_flow_policy(
        ctx.algorithms,
        ctx.handle,
        preset,
        node_mask=node_mask,
        edge_mask=edge_mask,
    )
    placed, _ = policy.place_demand(flow_graph, src_id, dst_id, priority, volume)

    cost_dist: dict[float, float] = {}
    used_edges: set[str] = set()

    if include_cost_distribution or include_used_edges:
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
                    ref = ctx.edge_mapper.to_ref(edge_id, ctx.multidigraph)
                    if ref:
                        used_edges.add(f"{ref.link_id}:{ref.direction}")

    return placed, cost_dist, used_edges
