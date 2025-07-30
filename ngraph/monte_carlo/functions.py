"""Picklable Monte Carlo analysis functions for FailureManager simulations.

These functions are designed to be used with FailureManager.run_monte_carlo_analysis()
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

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.results_artifacts import TrafficMatrixSet
from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficManager

if TYPE_CHECKING:
    from ngraph.network_view import NetworkView


def max_flow_analysis(
    network_view: "NetworkView",
    source_regex: str,
    sink_regex: str,
    mode: str = "combine",
    shortest_path: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    **kwargs,
) -> list[tuple[str, str, float]]:
    """Analyze maximum flow capacity between node groups.

    Args:
        network_view: NetworkView with potential exclusions applied.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.

    Returns:
        List of (source, sink, capacity) tuples.
    """
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
    placement_rounds: int = 50,
    **kwargs,
) -> dict[str, Any]:
    """Analyze traffic demand placement success rates.

    Args:
        network_view: NetworkView with potential exclusions applied.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds.

    Returns:
        Dictionary with placement statistics by priority.
    """
    # Reconstruct demands from config to avoid passing complex objects
    demands = []
    for config in demands_config:
        demand = TrafficDemand(
            source_path=config["source_path"],
            sink_path=config["sink_path"],
            demand=config["demand"],
            mode=config.get("mode", "full_mesh"),
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

    # Aggregate results by priority
    demand_stats = defaultdict(
        lambda: {"total_volume": 0.0, "placed_volume": 0.0, "count": 0}
    )
    for demand in tm.demands:
        priority = getattr(demand, "priority", 0)
        demand_stats[priority]["total_volume"] += demand.volume
        demand_stats[priority]["placed_volume"] += demand.placed_demand
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
) -> dict[str, float]:
    """Analyze component sensitivity to failures.

    Args:
        network_view: NetworkView with potential exclusions applied.
        source_regex: Regex pattern for source node groups.
        sink_regex: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.

    Returns:
        Dictionary mapping component IDs to sensitivity scores.
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
