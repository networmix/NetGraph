"""Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager and follow the
AnalysisFunction protocol: analysis_func(network: Network, excluded_nodes: Set[str],
excluded_links: Set[str], **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph once and using O(|excluded|) masks for exclusions.

SPF caching enables efficient demand placement by computing shortest paths once
per unique source node rather than once per demand. For networks with many demands
sharing the same sources, this can reduce SPF computations by an order of magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional, Set

import netgraph_core
import numpy as np

from ngraph.analysis import AnalysisContext, analyze
from ngraph.exec.demand.expand import ExpandedDemand, expand_demands
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.types.base import FlowPlacement, Mode

if TYPE_CHECKING:
    from ngraph.model.network import Network

# Minimum flow threshold for placement decisions
_MIN_FLOW = 1e-9

# Policies that support SPF caching with simple single-flow placement
_CACHEABLE_SIMPLE: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
    }
)

# Policies that support SPF caching with fallback for capacity-aware routing
_CACHEABLE_TE: frozenset[FlowPolicyPreset] = frozenset(
    {
        FlowPolicyPreset.TE_WCMP_UNLIM,
    }
)

# All cacheable policies
_CACHEABLE_PRESETS: frozenset[FlowPolicyPreset] = _CACHEABLE_SIMPLE | _CACHEABLE_TE


def _get_selection_for_preset(
    preset: FlowPolicyPreset,
) -> netgraph_core.EdgeSelection:
    """Get EdgeSelection configuration for a cacheable policy preset.

    Args:
        preset: Flow policy preset.

    Returns:
        EdgeSelection configured for the preset.

    Raises:
        ValueError: If preset is not cacheable.
    """
    if preset in _CACHEABLE_SIMPLE:
        return netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=False,
            tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
        )
    elif preset == FlowPolicyPreset.TE_WCMP_UNLIM:
        return netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
    raise ValueError(f"Preset {preset} is not cacheable")


def _get_placement_for_preset(preset: FlowPolicyPreset) -> netgraph_core.FlowPlacement:
    """Get FlowPlacement strategy for a cacheable policy preset.

    Args:
        preset: Flow policy preset.

    Returns:
        FlowPlacement strategy for the preset.
    """
    if preset == FlowPolicyPreset.SHORTEST_PATHS_ECMP:
        return netgraph_core.FlowPlacement.EQUAL_BALANCED
    # WCMP and TE policies use PROPORTIONAL
    return netgraph_core.FlowPlacement.PROPORTIONAL


@dataclass
class _CachedPlacementResult:
    """Result of placing a demand using cached SPF."""

    total_placed: float
    next_flow_idx: int
    cost_distribution: dict[float, float]
    used_edges: set[str]
    flow_indices: list[netgraph_core.FlowIndex] = field(default_factory=list)


def _place_demand_cached(
    demand: ExpandedDemand,
    src_id: int,
    dst_id: int,
    dag_cache: dict[tuple[int, FlowPolicyPreset], tuple[np.ndarray, Any]],
    algorithms: netgraph_core.Algorithms,
    handle: netgraph_core.Graph,
    flow_graph: netgraph_core.FlowGraph,
    node_mask: np.ndarray,
    edge_mask: np.ndarray,
    flow_idx_start: int,
    include_flow_details: bool,
    include_used_edges: bool,
    edge_mapper: Any,
    multidigraph: netgraph_core.StrictMultiDiGraph,
) -> _CachedPlacementResult:
    """Place a demand using cached SPF DAG with fallback for TE policies.

    This function implements SPF caching to reduce redundant shortest path
    computations. For demands sharing the same source node and policy preset,
    the SPF result is computed once and reused.

    For simple policies (ECMP/WCMP), the cached DAG is always valid.
    For TE policies, the DAG may become stale as edges saturate. In this case,
    a fallback loop recomputes SPF with current residuals until the demand is
    placed or no more progress can be made.

    Args:
        demand: Expanded demand to place.
        src_id: Source node ID.
        dst_id: Destination node ID.
        dag_cache: Cache mapping (src_id, preset) to (distances, DAG).
        algorithms: Core Algorithms instance.
        handle: Core Graph handle.
        flow_graph: FlowGraph for placement.
        node_mask: Node inclusion mask.
        edge_mask: Edge inclusion mask.
        flow_idx_start: Starting flow index counter.
        include_flow_details: Whether to collect cost distribution.
        include_used_edges: Whether to collect used edges.
        edge_mapper: Edge ID mapper for edge name resolution.
        multidigraph: Graph for edge lookup.

    Returns:
        _CachedPlacementResult with placement details.
    """
    cache_key = (src_id, demand.policy_preset)
    selection = _get_selection_for_preset(demand.policy_preset)
    placement = _get_placement_for_preset(demand.policy_preset)
    is_te = demand.policy_preset in _CACHEABLE_TE

    flow_indices: list[netgraph_core.FlowIndex] = []
    flow_costs: list[tuple[float, float]] = []  # (cost, placed_amount)
    flow_idx_counter = flow_idx_start
    demand_placed = 0.0
    remaining = demand.volume

    # Get or compute initial DAG
    if cache_key not in dag_cache:
        # Initial computation without residual - on a fresh graph all edges
        # have full capacity, so residual-aware selection is not needed yet
        dists, dag = algorithms.spf(
            handle,
            src=src_id,
            dst=None,  # Full DAG to all destinations
            selection=selection,
            node_mask=node_mask,
            edge_mask=edge_mask,
            multipath=True,
            dtype="float64",
        )
        dag_cache[cache_key] = (dists, dag)

    dists, dag = dag_cache[cache_key]

    # Check if destination is reachable
    if dists[dst_id] == float("inf"):
        # Destination unreachable - return zero placement
        return _CachedPlacementResult(
            total_placed=0.0,
            next_flow_idx=flow_idx_counter,
            cost_distribution={},
            used_edges=set(),
            flow_indices=[],
        )

    cost = float(dists[dst_id])

    # First placement attempt with cached DAG
    flow_idx = netgraph_core.FlowIndex(
        src_id, dst_id, demand.priority, flow_idx_counter
    )
    flow_idx_counter += 1
    placed = flow_graph.place(flow_idx, src_id, dst_id, dag, remaining, placement)

    if placed > _MIN_FLOW:
        flow_indices.append(flow_idx)
        flow_costs.append((cost, placed))
        demand_placed += placed
        remaining -= placed

    # For TE policies, use fallback loop if partial placement
    if is_te and remaining > _MIN_FLOW:
        max_fallback_iterations = 100
        iterations = 0

        while remaining > _MIN_FLOW and iterations < max_fallback_iterations:
            iterations += 1

            # Recompute DAG with current residuals
            residual = np.ascontiguousarray(
                flow_graph.residual_view(), dtype=np.float64
            )
            fresh_dists, fresh_dag = algorithms.spf(
                handle,
                src=src_id,
                dst=None,
                selection=selection,
                residual=residual,
                node_mask=node_mask,
                edge_mask=edge_mask,
                multipath=True,
                dtype="float64",
            )

            # Update cache with fresh DAG
            dag_cache[cache_key] = (fresh_dists, fresh_dag)

            # Check if destination still reachable
            if fresh_dists[dst_id] == float("inf"):
                break  # No more paths available

            fresh_cost = float(fresh_dists[dst_id])

            flow_idx = netgraph_core.FlowIndex(
                src_id, dst_id, demand.priority, flow_idx_counter
            )
            flow_idx_counter += 1
            additional = flow_graph.place(
                flow_idx, src_id, dst_id, fresh_dag, remaining, placement
            )

            if additional < _MIN_FLOW:
                break  # No progress, stop

            flow_indices.append(flow_idx)
            flow_costs.append((fresh_cost, additional))
            demand_placed += additional
            remaining -= additional

    # Collect cost distribution if requested
    cost_distribution: dict[float, float] = {}
    if include_flow_details:
        for c, amount in flow_costs:
            cost_distribution[c] = cost_distribution.get(c, 0.0) + amount

    # Collect used edges if requested
    used_edges: set[str] = set()
    if include_used_edges:
        for fidx in flow_indices:
            edges = flow_graph.get_flow_edges(fidx)
            for edge_id, _ in edges:
                edge_ref = edge_mapper.to_ref(edge_id, multidigraph)
                if edge_ref is not None:
                    used_edges.add(f"{edge_ref.link_id}:{edge_ref.direction}")

    return _CachedPlacementResult(
        total_placed=demand_placed,
        next_flow_idx=flow_idx_counter,
        cost_distribution=cost_distribution,
        used_edges=used_edges,
        flow_indices=flow_indices,
    )


def max_flow_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    source_path: str,
    sink_path: str,
    mode: str = "combine",
    shortest_path: bool = False,
    require_capacity: bool = True,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    include_flow_details: bool = False,
    include_min_cut: bool = False,
    context: Optional[AnalysisContext] = None,
    **kwargs,
) -> FlowIterationResult:
    """Analyze maximum flow capacity between node groups.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source_path: Selection expression for source node groups.
        sink_path: Selection expression for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        require_capacity: If True (default), path selection considers available
            capacity. If False, path selection is cost-only (true IP/IGP semantics).
        flow_placement: Flow placement strategy.
        include_flow_details: Whether to collect cost distribution and similar details.
        include_min_cut: Whether to include min-cut edge list in entry data.
        context: Pre-built AnalysisContext for efficient repeated analysis.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        FlowIterationResult describing this iteration.
    """
    # Convert string mode to Mode enum
    mode_enum = Mode.COMBINE if mode == "combine" else Mode.PAIRWISE

    # Use provided context or create a new one
    if context is not None:
        ctx = context
    else:
        ctx = analyze(network, source=source_path, sink=sink_path, mode=mode_enum)

    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    if include_flow_details or include_min_cut:
        flows = ctx.max_flow_detailed(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            include_min_cut=include_min_cut,
        )
        for (src, dst), summary in flows.items():
            value = float(summary.total_flow)
            cost_dist = summary.cost_distribution or {}
            min_cut_edges = summary.min_cut or ()
            entry = FlowEntry(
                source=str(src),
                destination=str(dst),
                priority=0,
                demand=value,
                placed=value,
                dropped=0.0,
                cost_distribution=(
                    {float(k): float(v) for k, v in cost_dist.items()}
                    if include_flow_details
                    else {}
                ),
                data=(
                    {
                        "edges": [f"{e.link_id}:{e.direction}" for e in min_cut_edges],
                        "edges_kind": "min_cut",
                    }
                    if include_min_cut and min_cut_edges
                    else {}
                ),
            )
            flow_entries.append(entry)
            total_demand += value
            total_placed += value
    else:
        flows = ctx.max_flow(
            shortest_path=shortest_path,
            require_capacity=require_capacity,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
        )
        for (src, dst), val in flows.items():
            value = float(val)
            entry = FlowEntry(
                source=str(src),
                destination=str(dst),
                priority=0,
                demand=value,
                placed=value,
                dropped=0.0,
            )
            flow_entries.append(entry)
            total_demand += value
            total_placed += value

    overall_ratio = (total_placed / total_demand) if total_demand > 0 else 1.0
    dropped_flows = sum(1 for e in flow_entries if e.dropped > 0.0)
    summary = FlowSummary(
        total_demand=total_demand,
        total_placed=total_placed,
        overall_ratio=overall_ratio,
        dropped_flows=dropped_flows,
        num_flows=len(flow_entries),
    )
    return FlowIterationResult(flows=flow_entries, summary=summary)


def demand_placement_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    demands_config: list[dict[str, Any]],
    placement_rounds: int | str = "auto",
    include_flow_details: bool = False,
    include_used_edges: bool = False,
    context: Optional[AnalysisContext] = None,
    **kwargs,
) -> FlowIterationResult:
    """Analyze traffic demand placement success rates using Core directly.

    This function:
    1. Builds Core infrastructure (graph, algorithms, flow_graph) or uses cached
    2. Expands demands into concrete (src, dst, volume) tuples
    3. Places each demand using SPF caching for cacheable policies
    4. Falls back to FlowPolicy for complex multi-flow policies
    5. Aggregates results into FlowIterationResult

    SPF Caching Optimization:
        For cacheable policies (ECMP, WCMP, TE_WCMP_UNLIM), SPF results are
        cached by source node. This reduces SPF computations from O(demands)
        to O(unique_sources), typically a 5-10x reduction for workloads with
        many demands sharing the same sources.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds (unused - Core handles internally).
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        context: Pre-built AnalysisContext for fast repeated analysis.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        FlowIterationResult describing this iteration.
    """
    # Reconstruct TrafficDemand objects from config
    traffic_demands = []
    for config in demands_config:
        demand = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
            mode=config.get("mode", "pairwise"),
            flow_policy_config=config.get("flow_policy_config"),
            priority=config.get("priority", 0),
        )
        traffic_demands.append(demand)

    # Phase 1: Expand demands (pure logic, returns names + augmentations)
    expansion = expand_demands(
        network,
        traffic_demands,
        default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
    )

    # Phase 2: Use cached context infrastructure or build fresh
    if context is not None:
        ctx = context
    else:
        # Build fresh context with augmentations
        ctx = AnalysisContext.from_network(
            network, augmentations=expansion.augmentations
        )

    # Extract infrastructure from context
    handle = ctx.handle
    multidigraph = ctx.multidigraph
    node_mapper = ctx.node_mapper
    edge_mapper = ctx.edge_mapper
    algorithms = ctx.algorithms
    node_mask = ctx._build_node_mask(excluded_nodes)
    edge_mask = ctx._build_edge_mask(excluded_links)

    flow_graph = netgraph_core.FlowGraph(multidigraph)

    # Phase 3: Place demands with SPF caching for cacheable policies
    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    # SPF cache: (src_id, policy_preset) -> (distances, DAG)
    dag_cache: dict[tuple[int, FlowPolicyPreset], tuple[np.ndarray, Any]] = {}
    flow_idx_counter = 0

    for demand in expansion.demands:
        # Resolve node names to IDs (includes pseudo nodes from augmentations)
        src_id = node_mapper.to_id(demand.src_name)
        dst_id = node_mapper.to_id(demand.dst_name)

        # Use cached placement for cacheable policies, FlowPolicy for others
        if demand.policy_preset in _CACHEABLE_PRESETS:
            result = _place_demand_cached(
                demand=demand,
                src_id=src_id,
                dst_id=dst_id,
                dag_cache=dag_cache,
                algorithms=algorithms,
                handle=handle,
                flow_graph=flow_graph,
                node_mask=node_mask,
                edge_mask=edge_mask,
                flow_idx_start=flow_idx_counter,
                include_flow_details=include_flow_details,
                include_used_edges=include_used_edges,
                edge_mapper=edge_mapper,
                multidigraph=multidigraph,
            )
            flow_idx_counter = result.next_flow_idx
            placed = result.total_placed
            cost_distribution = result.cost_distribution
            used_edges = result.used_edges
        else:
            # Complex policies (multi-flow LSP variants): use FlowPolicy
            policy = create_flow_policy(
                algorithms,
                handle,
                demand.policy_preset,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

            placed, flow_count = policy.place_demand(
                flow_graph,
                src_id,
                dst_id,
                demand.priority,
                demand.volume,
            )

            # Collect flow details if requested
            cost_distribution = {}
            used_edges = set()

            if include_flow_details or include_used_edges:
                flows_dict = policy.flows
                for flow_key, flow_data in flows_dict.items():
                    if include_flow_details:
                        cost = float(flow_data[2])
                        flow_vol = float(flow_data[3])
                        if flow_vol > 0:
                            cost_distribution[cost] = (
                                cost_distribution.get(cost, 0.0) + flow_vol
                            )

                    if include_used_edges:
                        flow_idx = netgraph_core.FlowIndex(
                            flow_key[0], flow_key[1], flow_key[2], flow_key[3]
                        )
                        edges = flow_graph.get_flow_edges(flow_idx)
                        for edge_id, _ in edges:
                            edge_ref = edge_mapper.to_ref(edge_id, multidigraph)
                            if edge_ref is not None:
                                used_edges.add(
                                    f"{edge_ref.link_id}:{edge_ref.direction}"
                                )

        # Build entry data
        entry_data: dict[str, Any] = {}
        if include_used_edges and used_edges:
            entry_data["edges"] = sorted(used_edges)
            entry_data["edges_kind"] = "used"

        # Create flow entry
        entry = FlowEntry(
            source=demand.src_name,
            destination=demand.dst_name,
            priority=demand.priority,
            demand=demand.volume,
            placed=placed,
            dropped=demand.volume - placed,
            cost_distribution=cost_distribution if include_flow_details else {},
            data=entry_data,
        )
        flow_entries.append(entry)
        total_demand += demand.volume
        total_placed += placed

    # Build summary
    overall_ratio = (total_placed / total_demand) if total_demand > 0 else 1.0
    dropped_flows = sum(1 for e in flow_entries if e.dropped > 0.0)
    summary = FlowSummary(
        total_demand=total_demand,
        total_placed=total_placed,
        overall_ratio=overall_ratio,
        dropped_flows=dropped_flows,
        num_flows=len(flow_entries),
    )

    return FlowIterationResult(
        flows=flow_entries,
        summary=summary,
        data={},
    )


def sensitivity_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    source_path: str,
    sink_path: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    context: Optional[AnalysisContext] = None,
    **kwargs,
) -> FlowIterationResult:
    """Analyze component sensitivity to failures.

    Identifies critical edges (saturated edges) and computes the flow reduction
    caused by removing each one. Returns a FlowIterationResult where each
    FlowEntry represents a source/sink pair with:
    - demand/placed = max flow value (the capacity being analyzed)
    - dropped = 0.0 (baseline analysis, no failures applied)
    - data["sensitivity"] = {link_id:direction: flow_reduction} for critical edges

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source_path: Selection expression for source node groups.
        sink_path: Selection expression for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: If True, use single-tier shortest-path flow (IP/IGP mode).
            Reports only edges used under ECMP routing. If False (default), use
            full iterative max-flow (SDN/TE mode) and report all saturated edges.
        flow_placement: Flow placement strategy.
        context: Pre-built AnalysisContext for efficient repeated analysis.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        FlowIterationResult with sensitivity data in each FlowEntry.data.
    """
    # Convert string mode to Mode enum
    mode_enum = Mode.COMBINE if mode == "combine" else Mode.PAIRWISE

    # Use provided context or create a new one
    if context is not None:
        ctx = context
    else:
        ctx = analyze(network, source=source_path, sink=sink_path, mode=mode_enum)

    # Get max flow values for each pair
    flow_values = ctx.max_flow(
        shortest_path=shortest_path,
        flow_placement=flow_placement,
        excluded_nodes=excluded_nodes,
        excluded_links=excluded_links,
    )

    # Get sensitivity (critical edges) for each pair
    sensitivity_results = ctx.sensitivity(
        shortest_path=shortest_path,
        flow_placement=flow_placement,
        excluded_nodes=excluded_nodes,
        excluded_links=excluded_links,
    )

    # Build FlowEntry for each pair
    flow_entries: list[FlowEntry] = []
    total_flow = 0.0

    for (src, dst), flow_value in flow_values.items():
        sensitivity_map = sensitivity_results.get((src, dst), {})
        entry = FlowEntry(
            source=str(src),
            destination=str(dst),
            priority=0,
            demand=flow_value,
            placed=flow_value,
            dropped=0.0,
            data={"sensitivity": sensitivity_map},
        )
        flow_entries.append(entry)
        total_flow += flow_value

    # Build summary
    summary = FlowSummary(
        total_demand=total_flow,
        total_placed=total_flow,
        overall_ratio=1.0,
        dropped_flows=0,
        num_flows=len(flow_entries),
    )

    return FlowIterationResult(flows=flow_entries, summary=summary)


def build_demand_context(
    network: "Network",
    demands_config: list[dict[str, Any]],
) -> AnalysisContext:
    """Build an AnalysisContext for repeated demand placement analysis.

    Pre-computes the graph with augmentations (pseudo source/sink nodes) for
    efficient repeated analysis with different exclusion sets.

    Args:
        network: Network instance.
        demands_config: List of demand configurations (same format as demand_placement_analysis).

    Returns:
        AnalysisContext ready for use with demand_placement_analysis.
    """
    # Reconstruct TrafficDemand objects
    traffic_demands = []
    for config in demands_config:
        demand = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
            mode=config.get("mode", "pairwise"),
            flow_policy_config=config.get("flow_policy_config"),
            priority=config.get("priority", 0),
        )
        traffic_demands.append(demand)

    # Expand demands to get augmentations
    expansion = expand_demands(
        network,
        traffic_demands,
        default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
    )

    # Build context with augmentations
    return analyze(network, augmentations=expansion.augmentations)


def build_maxflow_context(
    network: "Network",
    source_path: str,
    sink_path: str,
    mode: str = "combine",
) -> AnalysisContext:
    """Build an AnalysisContext for repeated max-flow analysis.

    Pre-computes the graph with pseudo source/sink nodes for all source/sink
    pairs, enabling O(|excluded|) mask building per iteration.

    Args:
        network: Network instance.
        source_path: Selection expression for source node groups.
        sink_path: Selection expression for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").

    Returns:
        AnalysisContext ready for use with max_flow_analysis or sensitivity_analysis.
    """
    mode_enum = Mode.COMBINE if mode == "combine" else Mode.PAIRWISE
    return analyze(network, source=source_path, sink=sink_path, mode=mode_enum)
