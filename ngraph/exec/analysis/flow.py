"""Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager and follow the
AnalysisFunction protocol: analysis_func(network: Network, excluded_nodes: Set[str],
excluded_links: Set[str], **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems.

This module provides only computation functions. Visualization and notebook
analysis live in external packages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Set

import netgraph_core

from ngraph.exec.demand.expand import expand_demands
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.solver.maxflow import (
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
    **kwargs,
) -> FlowIterationResult:
    """Analyze maximum flow capacity between node groups.

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
    # Optional pre-built graph components for performance
    _graph_handle: Any = None,
    _multidigraph: Any = None,
    _edge_mapper: Any = None,
    _node_mapper: Any = None,
    _algorithms: Any = None,
    **kwargs,
) -> FlowIterationResult:
    """Analyze traffic demand placement success rates using Core directly.

    This function:
    1. Builds Core infrastructure (graph, algorithms, flow_graph) OR uses pre-built components
    2. Expands demands into concrete (src, dst, volume) tuples
    3. Places each demand using Core's FlowPolicy
    4. Aggregates results into FlowIterationResult

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds (unused - Core handles internally).
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        _graph_handle: Optional pre-built graph handle (for performance in repeated calls).
        _multidigraph: Optional pre-built multidigraph (for performance in repeated calls).
        _edge_mapper: Optional pre-built edge mapper (for performance in repeated calls).
        _node_mapper: Optional pre-built node mapper (for performance in repeated calls).
        _algorithms: Optional pre-built algorithms instance (for performance in repeated calls).
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

    # Phase 2: Build or reuse graph infrastructure
    if _graph_handle is None or _multidigraph is None:
        # Build graph with augmentations (pseudo nodes, etc.)
        from ngraph.adapters.core import build_graph

        graph_handle, multidigraph, edge_mapper, node_mapper = build_graph(
            network,
            augmentations=expansion.augmentations,
            excluded_nodes=set(),  # Don't filter during build - use masks instead
            excluded_links=set(),
        )
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
    else:
        # Reuse pre-built components
        graph_handle = _graph_handle
        multidigraph = _multidigraph
        edge_mapper = _edge_mapper
        node_mapper = _node_mapper
        algorithms = _algorithms

    # Build masks for exclusions (if any)
    from ngraph.adapters.core import build_edge_mask, build_node_mask

    node_mask = None
    edge_mask = None
    if excluded_nodes or excluded_links:
        node_mask = build_node_mask(network, node_mapper, excluded_nodes)
        edge_mask = build_edge_mask(network, multidigraph, edge_mapper, excluded_links)

    flow_graph = netgraph_core.FlowGraph(multidigraph)

    # Phase 3: Place demands using Core FlowPolicy
    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    for demand in expansion.demands:
        # Resolve node names to IDs (now includes pseudo nodes from augmentations)
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
        data={},  # No iteration metrics for now
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
    **kwargs,
) -> dict[str, dict[str, float]]:
    """Analyze component sensitivity to failures.

    Identifies critical edges (saturated edges) and computes the flow reduction
    caused by removing each one.

    Args:
        network: Network instance.
        excluded_nodes: Set of node names to exclude temporarily.
        excluded_links: Set of link IDs to exclude temporarily.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only (ignored by sensitivity).
        flow_placement: Flow placement strategy.
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
        flow_placement=flow_placement,
        excluded_nodes=excluded_nodes,
        excluded_links=excluded_links,
    )

    # Remap keys from tuple (src, dst) to string "src->dst"
    out = {}
    for (src, dst), components in results.items():
        key = f"{src}->{dst}"
        out[key] = components

    return out
