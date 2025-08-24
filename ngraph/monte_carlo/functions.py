"""Picklable Monte Carlo analysis functions for FailureManager simulations.

These functions are designed for use with FailureManager.run_monte_carlo_analysis()
and follow the pattern: analysis_func(network_view: NetworkView, **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems for Monte Carlo
failure analysis scenarios.

This module provides only computation functions. Visualization and notebook
analysis live in external packages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ngraph.algorithms.base import FlowPlacement
from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary

if TYPE_CHECKING:
    from ngraph.model.view import NetworkView


def max_flow_analysis(
    network_view: "NetworkView",
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
        network_view: NetworkView with potential exclusions applied.
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
        flows = network_view.max_flow_with_summary(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
        )
        for (src, dst), (val, summary) in flows.items():
            value = float(val)
            cost_dist = getattr(summary, "cost_distribution", {}) or {}
            min_cut = getattr(summary, "min_cut", []) or []
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
        flows = network_view.max_flow(
            source_regex,
            sink_regex,
            mode=mode,
            shortest_path=shortest_path,
            flow_placement=flow_placement,
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
    network_view: "NetworkView",
    demands_config: list[dict[str, Any]],
    placement_rounds: int | str = "auto",
    include_flow_details: bool = False,
    include_used_edges: bool = False,
    **kwargs,
) -> FlowIterationResult:
    """Analyze traffic demand placement success rates.

    Produces per-demand FlowEntry records and an iteration-level summary suitable
    for downstream statistics (e.g., delivered percentiles) without reconstructing
    joint distributions.

    Additionally exposes placement engine counters to aid performance analysis:
    - Per-demand: ``FlowEntry.data.policy_metrics`` (dict) with totals collected by
      the active FlowPolicy (e.g., ``spf_calls_total``, ``flows_created_total``,
      ``reopt_calls_total``, ``place_iterations_total``).
    - Per-iteration: ``FlowIterationResult.data.iteration_metrics`` aggregating the
      same counters across all demands in the iteration. Use
      ``FlowIterationResult.summary.total_placed`` for placed volume totals.

    Args:
        network_view: NetworkView with potential exclusions applied.
        demands_config: List of demand configurations (serializable dicts).
        placement_rounds: Number of placement optimization rounds.
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data
            as ``FlowEntry.data.edges`` with ``edges_kind='used'``.
        **kwargs: Ignored. Accepted for interface compatibility.

    Returns:
        FlowIterationResult describing this iteration. The ``data`` field contains
        ``{"iteration_metrics": { ... }}``.
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

    # Build per-demand entries and overall summary
    flow_entries: list[FlowEntry] = []
    total_demand = 0.0
    total_placed = 0.0

    # Aggregate iteration-level engine metrics across all demands
    iteration_metrics: dict[str, float] = {
        "spf_calls_total": 0.0,
        "flows_created_total": 0.0,
        "reopt_calls_total": 0.0,
        "place_iterations_total": 0.0,
    }

    for dmd in tm.demands:
        offered = float(getattr(dmd, "volume", 0.0))
        placed = float(getattr(dmd, "placed_demand", 0.0))
        priority = int(getattr(dmd, "priority", getattr(dmd, "demand_class", 0)))
        dropped = offered - placed
        extra: dict[str, Any] = {}
        cost_distribution: dict[float, float] = {}
        if (include_flow_details or include_used_edges) and getattr(
            dmd, "flow_policy", None
        ) is not None:
            edge_strings: set[str] = set()
            for flow in dmd.flow_policy.flows.values():  # type: ignore[union-attr]
                # Accumulate placed volume by path cost
                bundle = getattr(flow, "path_bundle", None)
                if (
                    include_flow_details
                    and bundle is not None
                    and hasattr(bundle, "cost")
                ):
                    cost_val = float(bundle.cost)
                    vol_val = float(getattr(flow, "placed_flow", 0.0))
                    if vol_val > 0.0:
                        cost_distribution[cost_val] = (
                            cost_distribution.get(cost_val, 0.0) + vol_val
                        )
                # Collect used edges for reference
                if include_used_edges:
                    for eid in getattr(flow.path_bundle, "edges", set()):
                        edge_strings.add(str(eid))
            if include_used_edges and edge_strings:
                extra["edges"] = sorted(edge_strings)
                extra["edges_kind"] = "used"

        # Always expose per-demand FlowPolicy metrics when available
        fp = getattr(dmd, "flow_policy", None)
        if fp is not None:
            try:
                # Cumulative totals over the policy's lifetime within this iteration
                totals: dict[str, float] = fp.get_metrics()  # type: ignore[assignment]
            except Exception:
                totals = {}
            if totals:
                extra["policy_metrics"] = {k: float(v) for k, v in totals.items()}
                # Accumulate iteration-level totals across demands on known keys
                for key in iteration_metrics.keys():
                    if key in totals:
                        try:
                            iteration_metrics[key] += float(totals[key])
                        except Exception:
                            pass

        entry = FlowEntry(
            source=str(getattr(dmd, "src_node", "")),
            destination=str(getattr(dmd, "dst_node", "")),
            priority=priority,
            demand=offered,
            placed=placed,
            dropped=dropped,
            cost_distribution=(cost_distribution if include_flow_details else {}),
            data=extra,
        )
        flow_entries.append(entry)
        total_demand += offered
        total_placed += placed

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
        data={"iteration_metrics": iteration_metrics},
    )


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
