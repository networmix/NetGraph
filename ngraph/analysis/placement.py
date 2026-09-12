"""Core demand placement with SPF caching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Sequence, Set, Tuple

import netgraph_core
import numpy as np

from ngraph.analysis.static_paths import build_static_path_bundles
from ngraph.logging import get_logger
from ngraph.model.demand.spec import StaticPath
from ngraph.model.flow.policy_config import (
    HOP_BY_HOP_PRESETS,
    FlowPolicyPreset,
    create_flow_policy,
    preset_config,
)

if TYPE_CHECKING:
    from ngraph.analysis.context import AnalysisContext
    from ngraph.analysis.demand import ExpandedDemand

logger = get_logger(__name__)

#: Presets placed by the SPF-cached engine. Hop-by-hop presets place in one
#: pass on the cost-only DAG of their source; TE_WCMP_UNLIM reroutes the
#: remainder tier by tier on residual-aware DAGs. The LSP presets need Core's
#: FlowPolicy (many flows, reoptimization) and are not cacheable.
CACHEABLE_PRESETS: frozenset[FlowPolicyPreset] = frozenset(
    HOP_BY_HOP_PRESETS | {FlowPolicyPreset.TE_WCMP_UNLIM}
)

_CACHEABLE_TE: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.TE_WCMP_UNLIM,
    }
)

#: Smallest flow the core engine distinguishes: it never augments below
#: kMinFlow = 1/4096 (NetGraph-Core constants.hpp) and rounds per-flow
#: targets up to it. A demand short by at most this much is placed to the
#: engine's numeric resolution, which is what feasibility means here.
FLOW_RESOLUTION = 1.0 / 4096.0

# Threshold for recording a placed amount as a flow entry. Any nonzero amount
# the core returns clears FLOW_RESOLUTION and hence this comfortably.
_MIN_FLOW = 1e-9

# Cached-path FlowIndex ids start far above the ids Core's FlowPolicy assigns
# internally (0..max_flow_count, <= 256), so a cached demand and a
# policy-based demand sharing (src, dst, priority) can never produce the same
# FlowIndex. Duplicate FlowIndex values silently merge flows in FlowGraph,
# corrupting placement totals.
_CACHED_FLOW_ID_BASE = 1 << 20


@dataclass(slots=True)
class PlacementSummary:
    """Aggregated placement totals.

    Attributes:
        total_demand: Sum of demand volumes.
        total_placed: Sum of placed volumes.
        max_shortfall: Largest ``volume - placed`` over all demands.
        unserved_demands: Demands with positive volume that placed nothing.
    """

    total_demand: float
    total_placed: float
    max_shortfall: float = 0.0
    unserved_demands: int = 0

    @property
    def ratio(self) -> float:
        return self.total_placed / self.total_demand if self.total_demand > 0 else 1.0

    @property
    def is_feasible(self) -> bool:
        """True when every demand is placed to the engine's resolution.

        The core engine cannot place less than ``FLOW_RESOLUTION`` on a flow,
        so a demand whose per-flow share is below it (many LSPs carrying a
        small volume) always comes back short by a fraction of that amount.
        Requiring an exact match would call such a demand infeasible at any
        scale; a shortfall within the resolution is the engine saying "placed".
        A demand that placed nothing at all is never feasible, whatever its
        volume: below the resolution the engine cannot evaluate it, and above
        it nothing was carried.
        """
        return self.max_shortfall <= FLOW_RESOLUTION and self.unserved_demands == 0


@dataclass(slots=True)
class PlacementEntry:
    """Single demand placement result.

    Attributes:
        src_name: Source node name (real or pseudo).
        dst_name: Destination node name (real or pseudo).
        priority: Priority class.
        volume: Requested volume.
        placed: Placed volume. For ``SHORTEST_PATHS_ECMP_LOSSY`` this is the
            volume delivered to the destination.
        cost_distribution: Placed volume by path cost, when requested.
        used_edges: ``link_id:direction`` of every edge carrying this demand,
            when requested.
        dropped_edges: Dropped volume by ``link_id:direction``, when requested;
            only lossy presets drop.
    """

    src_name: str
    dst_name: str
    priority: int
    volume: float
    placed: float
    cost_distribution: dict[float, float] = field(default_factory=dict)
    used_edges: set[str] = field(default_factory=set)
    dropped_edges: dict[str, float] = field(default_factory=dict)


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


@dataclass(slots=True)
class _CachedPlacement:
    """What one cached placement produced, before aggregation into an entry."""

    placed: float = 0.0
    cost_distribution: Dict[float, float] = field(default_factory=dict)
    used_edges: Set[str] = field(default_factory=set)
    dropped_edges: Dict[str, float] = field(default_factory=dict)

    def merge(self, other: "_CachedPlacement") -> None:
        self.placed += other.placed
        for cost, amount in other.cost_distribution.items():
            self.cost_distribution[cost] = (
                self.cost_distribution.get(cost, 0.0) + amount
            )
        self.used_edges |= other.used_edges
        for edge, amount in other.dropped_edges.items():
            self.dropped_edges[edge] = self.dropped_edges.get(edge, 0.0) + amount


_PRESET_MODES: Dict[
    FlowPolicyPreset, Tuple[netgraph_core.EdgeSelection, netgraph_core.FlowPlacement]
] = {}


def _preset_modes(
    preset: FlowPolicyPreset,
) -> Tuple[netgraph_core.EdgeSelection, netgraph_core.FlowPlacement]:
    """Edge selection and placement mode of a cacheable preset.

    Read from ``preset_config`` so the cached engine and Core's FlowPolicy
    agree by construction; memoized because presets are immutable.
    """
    modes = _PRESET_MODES.get(preset)
    if modes is None:
        config = preset_config(preset)
        modes = (config.selection, config.flow_placement)
        _PRESET_MODES[preset] = modes
    return modes


def _get_edge_selection(preset: FlowPolicyPreset) -> netgraph_core.EdgeSelection:
    """Get EdgeSelection for a cacheable preset."""
    return _preset_modes(preset)[0]


def _get_flow_placement(preset: FlowPolicyPreset) -> netgraph_core.FlowPlacement:
    """Get FlowPlacement for a cacheable preset."""
    return _preset_modes(preset)[1]


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
    dag_cache: dict[tuple, tuple[np.ndarray, Any]] | None = None,
) -> PlacementResult:
    """Place demands on a flow graph with SPF caching.

    Demands are placed one at a time in the given order (callers sort by
    priority), each seeing the residual left by the ones before it. Nothing
    is revisited, so within a priority class earlier demands win contended
    capacity and the totals of rerouting presets depend on demand order.

    Hop-by-hop presets (``HOP_BY_HOP_PRESETS``) place each demand in one pass
    on the cost-only shortest-path DAG of its source. A combine-mode demand is
    a virtual source, a pool of the selected sources: with such a preset
    (``ExpandedDemand.src_members`` set) every member that can reach a target
    originates an even share of the volume, since hop-by-hop routing has no
    controller that could choose where traffic originates, and each share is
    routed to that member's nearest targets. Under lossless ECMP the pool is
    admitted as one demand at a single scale. TE presets keep the aggregated
    pseudo source and let capacity decide which members originate. A fixed
    per-source matrix is a different question, answered by pairwise or
    per-group expansion.

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
        include_cost_distribution: Include cost distribution and, for lossy
            presets, dropped volume per link in entries.
        include_used_edges: Include used edges in entries.
        dag_cache: Optional persistent SPF DAG cache. Base DAGs are keyed by
            ``(src_id, uses_capacity_aware_selection)`` and combine-mode
            fan-out DAGs by ``(dst_id, "fanout")``. All of them depend only
            on the static graph and masks, so repeated calls with the same
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
    max_shortfall = 0.0
    unserved_demands = 0
    flow_idx_counter = _CACHED_FLOW_ID_BASE
    # Core's FlowPolicy assigns flow ids internally per policy instance, so
    # two policy-based demands sharing (src, dst, priority) would produce
    # colliding FlowIndex values and silently merge/steal each other's flows.
    policy_triples: set[tuple[int, int, int]] = set()
    node_id_of = ctx.node_mapper.node_id_of

    for demand, volume, (src_id, dst_id) in zip(
        demands, volumes, resolved_ids, strict=True
    ):
        total_demand += volume

        if demand.policy_preset in CACHEABLE_PRESETS and not demand.static_paths:
            if demand.src_members and demand.policy_preset in HOP_BY_HOP_PRESETS:
                # Hop-by-hop forwarding cannot steer where traffic originates:
                # every source that can reach a target sends an even share
                # toward the (aggregated) targets, and the shares are reported
                # as one demand.
                member_ids = []
                for member in demand.src_members:
                    member_id = node_id_of.get(member)
                    if member_id is None:
                        raise ValueError(
                            f"Demand source {member!r} is not present in the "
                            "analysis context graph; rebuild the context from "
                            "the same demands_config."
                        )
                    member_ids.append(member_id)
                if (
                    _preset_modes(demand.policy_preset)[1]
                    == netgraph_core.FlowPlacement.EQUAL_BALANCED_FIXED
                ):
                    # Lossless admission applies to the demand as a whole: one
                    # pass over a DAG that fans out evenly from the pseudo
                    # source, so a source that cannot carry its share throttles
                    # every source alike.
                    outcome, flow_idx_counter = _place_cached_fanout(
                        src_id,
                        dst_id,
                        member_ids,
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
                    # Best-effort and proportional presets carry each share
                    # independently; totals and per-link drops equal those of a
                    # simultaneous pass, and shared links are attributed to
                    # sources in selection order. The virtual source is a
                    # pool: a member with no path to any target is not part
                    # of the split.
                    outcome = _CachedPlacement()
                    selection = _preset_modes(demand.policy_preset)[0]
                    reachable = [
                        member_id
                        for member_id in member_ids
                        if _base_dag(
                            (member_id, False),
                            member_id,
                            selection,
                            dag_cache,
                            ctx,
                            node_mask,
                            edge_mask,
                        )[0][dst_id]
                        != float("inf")
                    ]
                    share = volume / len(reachable) if reachable else 0.0
                    for member_id in reachable:
                        partial, flow_idx_counter = _place_cached(
                            member_id,
                            dst_id,
                            share,
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
                        outcome.merge(partial)
            else:
                outcome, flow_idx_counter = _place_cached(
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
            outcome = _place_with_policy(
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

        total_placed += outcome.placed
        shortfall = volume - outcome.placed
        if shortfall > max_shortfall:
            max_shortfall = shortfall
        if volume > 0.0 and outcome.placed <= 0.0:
            unserved_demands += 1

        if entries is not None:
            entries.append(
                PlacementEntry(
                    src_name=demand.src_name,
                    dst_name=demand.dst_name,
                    priority=demand.priority,
                    volume=volume,
                    placed=outcome.placed,
                    cost_distribution=outcome.cost_distribution,
                    used_edges=outcome.used_edges,
                    dropped_edges=outcome.dropped_edges,
                )
            )

    return PlacementResult(
        summary=PlacementSummary(
            total_demand=total_demand,
            total_placed=total_placed,
            max_shortfall=max_shortfall,
            unserved_demands=unserved_demands,
        ),
        entries=entries,
    )


def _edge_label(ctx: "AnalysisContext", ext_ids: Any, edge_id: int) -> str | None:
    """``link_id:direction`` of a Core edge, or None for pseudo edges."""
    ref = ctx.edge_mapper.decode_ext_id(int(ext_ids[edge_id]))
    return f"{ref.link_id}:{ref.direction}" if ref else None


def _base_dag(
    cache_key: tuple,
    src_id: int,
    selection: netgraph_core.EdgeSelection,
    dag_cache: dict[tuple, tuple[np.ndarray, Any]],
    ctx: "AnalysisContext",
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
) -> tuple[np.ndarray, Any]:
    """Cost-only (or capacity-gated) SPF DAG from ``src_id``, cached under ``cache_key``.

    Base DAGs depend only on the static graph and the masks, so one entry
    serves every demand from the same source within a mask state.
    """
    entry = dag_cache.get(cache_key)
    if entry is None:
        entry = ctx.algorithms.spf(
            ctx.handle,
            src=src_id,
            dst=None,
            selection=selection,
            node_mask=node_mask,
            edge_mask=edge_mask,
            multipath=True,
            dtype="float64",
        )
        dag_cache[cache_key] = entry
    return entry


def _place_cached(
    src_id: int,
    dst_id: int,
    volume: float,
    priority: int,
    preset: FlowPolicyPreset,
    dag_cache: dict[tuple, tuple[np.ndarray, Any]],
    ctx: "AnalysisContext",
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    flow_idx_start: int,
    include_cost_distribution: bool,
    include_used_edges: bool,
) -> tuple[_CachedPlacement, int]:
    """Place single demand with SPF caching."""
    selection, placement = _preset_modes(preset)
    is_te = preset in _CACHEABLE_TE
    lossy = placement == netgraph_core.FlowPlacement.EQUAL_BALANCED_LOSSY
    # Hop-by-hop presets share one cost-only EdgeSelection; TE presets share
    # the capacity-aware one. Keying by selection family (not preset) lets
    # mixed workloads reuse the same base SPF DAG.
    cache_key = (src_id, is_te)

    outcome = _CachedPlacement()
    flow_indices: list[netgraph_core.FlowIndex] = []
    flow_costs: list[tuple[float, float]] = []
    raw_drops: list[tuple[int, float]] = []
    flow_idx_counter = flow_idx_start
    remaining = volume

    dists, dag = _base_dag(
        cache_key, src_id, selection, dag_cache, ctx, node_mask, edge_mask
    )

    if dists[dst_id] == float("inf"):
        return outcome, flow_idx_counter

    cost = float(dists[dst_id])

    flow_idx = netgraph_core.FlowIndex(src_id, dst_id, priority, flow_idx_counter)
    flow_idx_counter += 1
    if lossy:
        amount, drops = flow_graph.place_with_drops(
            flow_idx, src_id, dst_id, dag, remaining, placement
        )
        raw_drops.extend(drops)
        # Volume carried part of the way and dropped downstream still occupies
        # the links it crossed, so the flow counts as using them.
        if amount > _MIN_FLOW or drops:
            flow_indices.append(flow_idx)
    else:
        amount = flow_graph.place(flow_idx, src_id, dst_id, dag, remaining, placement)
        if amount > _MIN_FLOW:
            flow_indices.append(flow_idx)

    if amount > _MIN_FLOW:
        flow_costs.append((cost, amount))
        outcome.placed += amount
        remaining -= amount

    if is_te and remaining > _MIN_FLOW:
        # Reroute the remainder tier by tier. Every iteration either
        # saturates at least one edge of the residual DAG it placed on (a
        # proportional placement runs a max-flow over the DAG) or makes no
        # progress and stops, so the edge count bounds the iterations.
        max_iterations = ctx.multidigraph.num_edges()
        for _ in range(max_iterations):
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
            outcome.placed += additional
            remaining -= additional

            if remaining < _MIN_FLOW:
                break
        else:
            logger.warning(
                "TE rerouting for demand %s->%s stopped at the edge-count bound "
                "(%d iterations) with %.6g still unplaced; this should not happen "
                "and indicates an engine invariant violation",
                ctx.node_mapper.to_name(src_id),
                ctx.node_mapper.to_name(dst_id),
                max_iterations,
                remaining,
            )

    if include_cost_distribution:
        for c, amt in flow_costs:
            outcome.cost_distribution[c] = outcome.cost_distribution.get(c, 0.0) + amt
        if raw_drops:
            ext_ids = ctx.multidigraph.ext_edge_ids_view()
            for edge_id, amt in raw_drops:
                label = _edge_label(ctx, ext_ids, edge_id)
                if label:
                    outcome.dropped_edges[label] = outcome.dropped_edges.get(
                        label, 0.0
                    ) + float(amt)

    if include_used_edges:
        ext_ids = ctx.multidigraph.ext_edge_ids_view()
        for fidx in flow_indices:
            for edge_id, _ in flow_graph.get_flow_edges(fidx):
                label = _edge_label(ctx, ext_ids, edge_id)
                if label:
                    outcome.used_edges.add(label)

    return outcome, flow_idx_counter


def _place_cached_fanout(
    root_id: int,
    dst_id: int,
    member_ids: Sequence[int],
    volume: float,
    priority: int,
    preset: FlowPolicyPreset,
    dag_cache: dict[tuple, tuple[np.ndarray, Any]],
    ctx: "AnalysisContext",
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    flow_idx_start: int,
    include_cost_distribution: bool,
    include_used_edges: bool,
) -> tuple[_CachedPlacement, int]:
    """Place a combine-mode demand in one pass with an even origination split.

    The DAG fans out from the pseudo source ``root_id`` over every attachment
    edge regardless of cost and then follows the shortest paths of each source
    toward ``dst_id``. Equal-balanced placement over it splits the volume
    evenly across the sources and admits the demand at one global scale, so a
    source that cannot carry its share throttles every source alike. The
    virtual source is a pool: a source with no path to any target is not a
    member of the split, and the others share the volume evenly.

    The DAG is cached per destination (one reverse SPF per demand per mask
    state) rather than per source.
    """
    selection, placement = _preset_modes(preset)
    cache_key = (dst_id, "fanout")
    outcome = _CachedPlacement()
    flow_idx_counter = flow_idx_start

    if cache_key not in dag_cache:
        graph = ctx.multidigraph
        row = graph.row_offsets_view()
        fanout = graph.adj_edge_index_view()[int(row[root_id]) : int(row[root_id + 1])]
        dists, dag = ctx.algorithms.spf_to(
            ctx.handle,
            dst_id,
            selection=selection,
            node_mask=node_mask,
            edge_mask=edge_mask,
            multipath=True,
            fanout_edges=[int(e) for e in fanout],
            dtype="float64",
        )
        dag_cache[cache_key] = (dists, dag)

    dists, dag = dag_cache[cache_key]
    # Members with no path to any target are not in the fan-out (spf_to skips
    # their attachment edge), so the split is over the reachable ones only.
    member_costs = [
        c for c in (float(dists[m]) for m in member_ids) if c != float("inf")
    ]
    if not member_costs:
        return outcome, flow_idx_counter

    flow_idx = netgraph_core.FlowIndex(root_id, dst_id, priority, flow_idx_counter)
    flow_idx_counter += 1
    amount = flow_graph.place(flow_idx, root_id, dst_id, dag, volume, placement)
    if amount <= _MIN_FLOW:
        return outcome, flow_idx_counter
    outcome.placed = amount

    if include_cost_distribution:
        # The fan-out is an equal split and lossless admission keeps the
        # ratios, so every source carries the same share.
        share = amount / len(member_costs)
        for c in member_costs:
            outcome.cost_distribution[c] = outcome.cost_distribution.get(c, 0.0) + share

    if include_used_edges:
        ext_ids = ctx.multidigraph.ext_edge_ids_view()
        for edge_id, _ in flow_graph.get_flow_edges(flow_idx):
            label = _edge_label(ctx, ext_ids, edge_id)
            if label:
                outcome.used_edges.add(label)

    return outcome, flow_idx_counter


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
) -> _CachedPlacement:
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

    outcome = _CachedPlacement(placed=placed)

    if include_cost_distribution or include_used_edges:
        ext_ids = ctx.multidigraph.ext_edge_ids_view()
        for flow_key, flow_data in policy.flows.items():
            if include_cost_distribution:
                cost, flow_vol = float(flow_data[2]), float(flow_data[3])
                if flow_vol > 0:
                    outcome.cost_distribution[cost] = (
                        outcome.cost_distribution.get(cost, 0.0) + flow_vol
                    )

            if include_used_edges:
                fidx = netgraph_core.FlowIndex(
                    flow_key[0], flow_key[1], flow_key[2], flow_key[3]
                )
                for edge_id, _ in flow_graph.get_flow_edges(fidx):
                    label = _edge_label(ctx, ext_ids, edge_id)
                    if label:
                        outcome.used_edges.add(label)

    return outcome
