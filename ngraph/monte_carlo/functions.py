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

from typing import TYPE_CHECKING, Any

from ngraph.algorithms.base import FlowPlacement
from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.monte_carlo.types import FlowResult, FlowStats

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
) -> list[FlowResult]:
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
        List of FlowResult dicts with metric="capacity". When include_flow_summary
        is True, each entry includes compact stats with cost_distribution and
        min-cut edges (as strings).
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
        results: list[FlowResult] = []
        for (src, dst), (val, summary) in flows.items():
            cost_dist = getattr(summary, "cost_distribution", {}) or {}
            min_cut = getattr(summary, "min_cut", []) or []
            stats: FlowStats = {
                "cost_distribution": {float(k): float(v) for k, v in cost_dist.items()},
                "edges": [str(e) for e in min_cut],
                "edges_kind": "min_cut",
            }
            results.append(
                {
                    "src": src,
                    "dst": dst,
                    "metric": "capacity",
                    "value": float(val),
                    "stats": stats,
                }
            )
        return results
    else:
        # Use regular max_flow for capacity-only analysis (existing behavior)
        flows = network_view.max_flow(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )
        # Convert to FlowResult format for inter-process communication
        return [
            {"src": src, "dst": dst, "metric": "capacity", "value": float(val)}
            for (src, dst), val in flows.items()
        ]


def demand_placement_analysis(
    network_view: "NetworkView",
    demands_config: list[dict[str, Any]],
    placement_rounds: int | str = "auto",
    include_flow_details: bool = False,
    **kwargs,
) -> dict[str, Any]:
    """Analyze traffic demand placement success rates.

    Returns a structured dictionary per iteration containing per-demand offered
    and placed volumes (in Gbit/s) and an iteration-level summary. This shape
    is designed for downstream computation of delivered bandwidth percentiles
    without having to reconstruct per-iteration joint distributions.

    Args:
        network_view: NetworkView with potential exclusions applied.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds.
        include_flow_details: If True, include edges used per demand.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        Dict with keys:
          - "demands": list of per-demand dicts with fields
              {src,dst,priority,offered_gbps,placed_gbps,placement_ratio,edges?}
          - "summary": {total_offered_gbps,total_placed_gbps,overall_ratio}
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
    tm.place_all_demands(placement_rounds=placement_rounds)

    # Build per-demand records and overall summary
    per_demand: list[dict[str, Any]] = []
    total_offered = 0.0
    total_placed = 0.0
    for dmd in tm.demands:
        offered_gbps = float(getattr(dmd, "volume", 0.0))
        placed_gbps = float(getattr(dmd, "placed_demand", 0.0))
        ratio = (placed_gbps / offered_gbps) if offered_gbps > 0 else 0.0
        priority = int(getattr(dmd, "priority", getattr(dmd, "demand_class", 0)))

        record: dict[str, Any] = {
            "src": str(getattr(dmd, "src_node", "")),
            "dst": str(getattr(dmd, "dst_node", "")),
            "priority": priority,
            "offered_gbps": offered_gbps,
            "placed_gbps": placed_gbps,
            "placement_ratio": ratio,
        }

        if include_flow_details and getattr(dmd, "flow_policy", None) is not None:
            # Collect edges used for this demand
            edge_strings: set[str] = set()
            for flow in dmd.flow_policy.flows.values():  # type: ignore[union-attr]
                for eid in getattr(flow.path_bundle, "edges", set()):
                    edge_strings.add(str(eid))
            if edge_strings:
                record["edges"] = sorted(edge_strings)

        per_demand.append(record)
        total_offered += offered_gbps
        total_placed += placed_gbps

    summary = {
        "total_offered_gbps": total_offered,
        "total_placed_gbps": total_placed,
        "overall_ratio": (total_placed / total_offered) if total_offered > 0 else 1.0,
    }

    return {"demands": per_demand, "summary": summary}


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
