"""Picklable Monte Carlo analysis functions for FailureManager simulations.

These functions are designed for use with FailureManager.run_monte_carlo_analysis()
and follow the pattern: analysis_func(network_view: NetworkView, **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems for Monte Carlo
failure analysis scenarios.

Note: This module is distinct from ngraph.workflow.analysis, which provides
notebook visualization components for workflow results.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from ngraph.algorithms.base import FlowPlacement
from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand

if TYPE_CHECKING:
    from ngraph.model.view import NetworkView


def max_flow_analysis(
    network_view: "NetworkView",
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    include_flow_summary: bool = False,
    **kwargs,
) -> list[tuple]:
    """Analyze maximum flow capacity between node groups.

    Args:
        network_view: NetworkView with potential exclusions applied.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.
        include_flow_summary: Whether to collect detailed flow summary data.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        List of tuples. If include_flow_summary is False: (source, sink, capacity).
        If include_flow_summary is True: (source, sink, capacity, flow_summary).
    """
    if include_flow_summary:
        # Use max_flow_with_summary to get detailed flow analytics
        flows = network_view.max_flow_with_summary(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )
        # Return with complete FlowSummary data
        return [
            (src, dst, val, summary) for (src, dst), (val, summary) in flows.items()
        ]
    else:
        # Use regular max_flow for capacity-only analysis (existing behavior)
        flows = network_view.max_flow(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )
        # Convert to serializable format for inter-process communication
        return [(src, dst, val) for (src, dst), val in flows.items()]


def demand_placement_analysis(
    network_view: "NetworkView",
    demands_config: list[dict[str, Any]],
    placement_rounds: int | str = "auto",
    include_flow_details: bool = False,
    **kwargs,
) -> dict[str, Any]:
    """Analyze traffic demand placement success rates.

    Args:
        network_view: NetworkView with potential exclusions applied.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        Dictionary with placement statistics for this run, including:
        - total_placed: Total placed demand volume.
        - total_demand: Total demand volume.
        - overall_placement_ratio: total_placed / total_demand (0.0 if undefined).
        - demand_results: List of per-demand statistics preserving offered volume.
          When ``include_flow_details`` is True, each entry also includes
          ``cost_distribution`` mapping path cost to placed volume and
          ``edges_used`` as a list of edge identifiers seen in the placed flows.
        - priority_results: Mapping from priority to aggregated statistics with
          keys total_volume, placed_volume, unplaced_volume, placement_ratio,
          and demand_count.
    """
    # Reconstruct demands from config to avoid passing complex objects
    demands = []
    for config in demands_config:
        demand = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
            mode=config.get("mode", "pairwise"),
            flow_policy_config=config.get("flow_policy_config"),
            priority=config.get("priority", 0),
        )
        demands.append(demand)

    traffic_matrix_set = TrafficMatrixSet()
    traffic_matrix_set.add("main", demands)

    tm = TrafficManager(
        network=network_view,
        traffic_matrix_set=traffic_matrix_set,
        matrix_name="main",
    )
    tm.build_graph()
    tm.expand_demands()
    total_placed = tm.place_all_demands(placement_rounds=placement_rounds)

    # Build per-demand results from expanded demands to preserve offered volumes
    demand_results: list[dict[str, Any]] = []
    # Aggregate by priority as well
    demand_stats = defaultdict(
        lambda: {"total_volume": 0.0, "placed_volume": 0.0, "count": 0}
    )
    for dmd in tm.demands:
        offered = float(getattr(dmd, "volume", 0.0))
        placed = float(getattr(dmd, "placed_demand", 0.0))
        unplaced = offered - placed
        priority = int(getattr(dmd, "priority", getattr(dmd, "demand_class", 0)))

        entry: dict[str, Any] = {
            "src": str(getattr(dmd, "src_node", "")),
            "dst": str(getattr(dmd, "dst_node", "")),
            "priority": priority,
            "offered_demand": offered,
            "placed_demand": placed,
            "unplaced_demand": unplaced,
            "placement_ratio": (placed / offered) if offered > 0 else 0.0,
        }

        if include_flow_details and getattr(dmd, "flow_policy", None) is not None:
            # Summarize placed flows by path cost and collect edges used
            cost_distribution: dict[float, float] = {}
            edge_strings: set[str] = set()
            try:
                for flow in dmd.flow_policy.flows.values():  # type: ignore[union-attr]
                    # Path cost for the flow
                    cost_val = float(getattr(flow.path_bundle, "cost", 0.0))
                    placed_flow = float(getattr(flow, "placed_flow", 0.0))
                    if placed_flow > 0.0:
                        cost_distribution[cost_val] = (
                            cost_distribution.get(cost_val, 0.0) + placed_flow
                        )
                    # Record edges used by this flow
                    for eid in getattr(flow.path_bundle, "edges", set()):
                        edge_strings.add(str(eid))
            except Exception:
                # Be defensive: omit details if anything unexpected occurs
                cost_distribution = {}
                edge_strings = set()

            if cost_distribution:
                entry["cost_distribution"] = cost_distribution
            if edge_strings:
                entry["edges_used"] = sorted(edge_strings)

        demand_results.append(entry)

        demand_stats[priority]["total_volume"] += offered
        demand_stats[priority]["placed_volume"] += placed
        demand_stats[priority]["count"] += 1

    priority_results = {}
    for priority, stats in demand_stats.items():
        placement_ratio = (
            stats["placed_volume"] / stats["total_volume"]
            if stats["total_volume"] > 0
            else 0.0
        )
        priority_results[priority] = {
            "total_volume": stats["total_volume"],
            "placed_volume": stats["placed_volume"],
            "unplaced_volume": stats["total_volume"] - stats["placed_volume"],
            "placement_ratio": placement_ratio,
            "demand_count": stats["count"],
        }

    total_demand = sum(stats["total_volume"] for stats in demand_stats.values())
    overall_placement_ratio = total_placed / total_demand if total_demand > 0 else 0.0

    return {
        "total_placed": total_placed,
        "total_demand": total_demand,
        "overall_placement_ratio": overall_placement_ratio,
        "demand_results": demand_results,
        "priority_results": priority_results,
    }


def sensitivity_analysis(
    network_view: "NetworkView",
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    **kwargs,
) -> dict[str, dict[str, float]]:
    """Analyze component sensitivity to failures.

    Args:
        network_view: NetworkView with potential exclusions applied.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        Dictionary mapping flow keys ("src->dst") to dictionaries of component
        identifiers mapped to sensitivity scores.
    """
    sensitivity = network_view.sensitivity_analysis(
        source_regex,
        sink_regex,
        mode=mode,
        shortest_path=shortest_path,
        flow_placement=flow_placement,
    )

    # Convert to serializable format - sensitivity returns nested dict structure
    # sensitivity is Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]
    result = {}
    for flow_pair, sensitivity_dict in sensitivity.items():
        flow_key = f"{flow_pair[0]}->{flow_pair[1]}"
        result[flow_key] = {
            str(component): float(score)
            for component, score in sensitivity_dict.items()
        }
    return result
