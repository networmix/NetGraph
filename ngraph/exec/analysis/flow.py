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

from ngraph.adapters.core import (
    GraphCache,
    build_edge_mask,
    build_graph_cache,
    build_node_mask,
)
from ngraph.exec.demand.expand import expand_demands
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.solver.maxflow import (
    MaxFlowGraphCache,
    build_maxflow_cache,
    max_flow,
    max_flow_with_details,
)
from ngraph.solver.maxflow import (
    sensitivity_analysis as solver_sensitivity_analysis,
)
from ngraph.types.base import FlowPlacement

if TYPE_CHECKING:
    from ngraph.model.network import Network


def max_flow_analysis(
    network: "Network",
    excluded_nodes: Set[str],
    excluded_links: Set[str],
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    include_flow_details: bool = False,
    include_min_cut: bool = False,
    _graph_cache: Optional[MaxFlowGraphCache] = None,
    **kwargs,
) -> FlowIterationResult:
    """Analyze maximum flow capacity between node groups.

    When `_graph_cache` is provided, uses O(|excluded|) mask building instead
    of O(V+E) graph reconstruction for efficient repeated analysis.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.
        include_flow_details: Whether to collect cost distribution and similar details.
        include_min_cut: Whether to include min-cut edge list in entry data.
        _graph_cache: Pre-built cache for efficient repeated analysis.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        FlowIterationResult describing this iteration.
    """
    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    if include_flow_details or include_min_cut:
        flows = max_flow_with_details(
            network,
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            _cache=_graph_cache,
        )
        for (src, dst), summary in flows.items():
            value = float(summary.total_flow)
            cost_dist = getattr(summary, "cost_distribution", {}) or {}
            min_cut = getattr(summary, "saturated_edges", []) or []
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
                    {"edges": [str(e) for e in min_cut], "edges_kind": "min_cut"}
                    if include_min_cut and min_cut
                    else {}
                ),
            )
            flow_entries.append(entry)
            total_demand += value
            total_placed += value
    else:
        flows = max_flow(
            network,
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
            excluded_nodes=excluded_nodes,
            excluded_links=excluded_links,
            _cache=_graph_cache,
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
    _graph_cache: Optional[GraphCache] = None,
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
        _graph_cache: Pre-built graph cache for fast repeated analysis.
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

    # Phase 2: Use cached graph infrastructure or build fresh
    if _graph_cache is not None:
        cache = _graph_cache
    else:
        # Build fresh cache (slower path for direct calls without pre-built cache)
        cache = build_graph_cache(network, augmentations=expansion.augmentations)

    graph_handle = cache.graph_handle
    multidigraph = cache.multidigraph
    edge_mapper = cache.edge_mapper
    node_mapper = cache.node_mapper
    algorithms = cache.algorithms

    # Build masks for exclusions (consistent behavior for both paths)
    node_mask = None
    edge_mask = None
    if excluded_nodes or excluded_links:
        node_mask = build_node_mask(cache, excluded_nodes)
        edge_mask = build_edge_mask(cache, excluded_links)

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
            graph_handle,
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
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    _graph_cache: Optional[MaxFlowGraphCache] = None,
    **kwargs,
) -> dict[str, dict[str, float]]:
    """Analyze component sensitivity to failures.

    Identifies critical edges (saturated edges) and computes the flow reduction
    caused by removing each one.

    When `_graph_cache` is provided, uses O(|excluded|) mask building instead
    of O(V+E) graph reconstruction for efficient repeated analysis.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: If True, use single-tier shortest-path flow (IP/IGP mode).
            Reports only edges used under ECMP routing. If False (default), use
            full iterative max-flow (SDN/TE mode) and report all saturated edges.
        flow_placement: Flow placement strategy.
        _graph_cache: Pre-built cache for efficient repeated analysis.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        Dictionary mapping flow keys ("src->dst") to dictionaries of component
        identifiers mapped to sensitivity scores.
    """
    results = solver_sensitivity_analysis(
        network,
        source_regex,
        sink_regex,
        mode=mode,
        shortest_path=shortest_path,
        flow_placement=flow_placement,
        excluded_nodes=excluded_nodes,
        excluded_links=excluded_links,
        _cache=_graph_cache,
    )

    # Remap keys from tuple (src, dst) to string "src->dst"
    out = {}
    for (src, dst), components in results.items():
        key = f"{src}->{dst}"
        out[key] = components

    return out


def build_demand_graph_cache(
    network: "Network",
    demands_config: list[dict[str, Any]],
) -> GraphCache:
    """Build a graph cache for repeated demand placement analysis.

    Pre-computes the graph with augmentations (pseudo source/sink nodes) for
    efficient repeated analysis with different exclusion sets.

    Args:
        network: Network instance.
        demands_config: List of demand configurations (same format as demand_placement_analysis).

    Returns:
        GraphCache ready for use with demand_placement_analysis.
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

    # Build cache with augmentations
    return build_graph_cache(network, augmentations=expansion.augmentations)


def build_maxflow_graph_cache(
    network: "Network",
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
) -> MaxFlowGraphCache:
    """Build a graph cache for repeated max-flow analysis.

    Pre-computes the graph with pseudo source/sink nodes for all source/sink
    pairs, enabling O(|excluded|) mask building per iteration.

    Args:
        network: Network instance.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").

    Returns:
        MaxFlowGraphCache ready for use with max_flow_analysis or sensitivity_analysis.
    """
    return build_maxflow_cache(network, source_regex, sink_regex, mode=mode)
