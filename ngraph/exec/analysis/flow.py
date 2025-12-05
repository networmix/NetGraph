"""Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager and follow the
AnalysisFunction protocol: analysis_func(network: Network, excluded_nodes: Set[str],
excluded_links: Set[str], **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph once and using O(|excluded|) masks for exclusions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Set

import netgraph_core

from ngraph.analysis import AnalysisContext, analyze
from ngraph.exec.demand.expand import expand_demands
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.types.base import FlowPlacement, Mode

if TYPE_CHECKING:
    from ngraph.model.network import Network


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
    3. Places each demand using Core's FlowPolicy with exclusion masks
    4. Aggregates results into FlowIterationResult

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

    # Phase 3: Place demands using Core FlowPolicy
    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    for demand in expansion.demands:
        # Resolve node names to IDs (includes pseudo nodes from augmentations)
        src_id = node_mapper.to_id(demand.src_name)
        dst_id = node_mapper.to_id(demand.dst_name)

        # Create FlowPolicy for this demand with masks
        policy = create_flow_policy(
            algorithms,
            handle,
            demand.policy_preset,
            node_mask=node_mask,
            edge_mask=edge_mask,
        )

        # Place demand using Core
        placed, flow_count = policy.place_demand(
            flow_graph,
            src_id,
            dst_id,
            demand.priority,  # flowClass
            demand.volume,
        )

        # Collect flow details if requested
        cost_distribution: dict[float, float] = {}
        used_edges: set[str] = set()

        if include_flow_details or include_used_edges:
            # Get flows from policy
            flows_dict = policy.flows
            for flow_key, flow_data in flows_dict.items():
                # flow_key is (src, dst, flowClass, flowId)
                # flow_data is (src, dst, cost, placed_flow)
                if include_flow_details:
                    cost = float(flow_data[2])
                    flow_vol = float(flow_data[3])
                    if flow_vol > 0:
                        cost_distribution[cost] = (
                            cost_distribution.get(cost, 0.0) + flow_vol
                        )

                if include_used_edges:
                    # Get edges for this flow
                    flow_idx = netgraph_core.FlowIndex(
                        flow_key[0], flow_key[1], flow_key[2], flow_key[3]
                    )
                    edges = flow_graph.get_flow_edges(flow_idx)
                    for edge_id, _ in edges:
                        edge_ref = edge_mapper.to_ref(edge_id, multidigraph)
                        if edge_ref is not None:
                            used_edges.add(f"{edge_ref.link_id}:{edge_ref.direction}")

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
