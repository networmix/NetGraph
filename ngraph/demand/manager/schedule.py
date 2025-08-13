"""Scheduling utilities for demand placement rounds.

Provides the simple priority-aware round-robin scheduler that was previously
implemented in `TrafficManager`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from ngraph.algorithms import base
from ngraph.demand import Demand
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def place_demands_round_robin(
    graph: StrictMultiDiGraph,
    demands: List[Demand],
    placement_rounds: int,
    reoptimize_after_each_round: bool = False,
) -> float:
    """Place demands using priority buckets and round-robin within each bucket.

    Args:
        graph: Active flow graph.
        demands: Expanded demands to place.
        placement_rounds: Number of passes per priority class.
        reoptimize_after_each_round: Whether to re-run placement for each demand
            after a round to better share capacity.

    Returns:
        Total volume successfully placed across all demands.
    """
    # Group demands by priority class
    prio_map: Dict[int, List[Demand]] = defaultdict(list)
    for dmd in demands:
        prio_map[dmd.demand_class].append(dmd)

    total_placed = 0.0
    sorted_priorities = sorted(prio_map.keys())

    for priority_class in sorted_priorities:
        demands_in_class = prio_map[priority_class]
        placed_before_class = sum(d.placed_demand for d in demands_in_class)

        # Unified fairness loop: attempt to place full leftover per demand each round.
        # For rounds > 0, reorder by least-served ratio to improve fairness.
        reopt_attempted = False
        for round_idx in range(placement_rounds):
            placed_in_this_round = 0.0

            if round_idx == 0:
                iteration_order = list(demands_in_class)
            else:
                iteration_order = sorted(
                    demands_in_class,
                    key=lambda d: (
                        (d.placed_demand / d.volume) if d.volume > 0 else 1.0,
                        d.placed_demand,
                    ),
                )

            for demand in iteration_order:
                leftover = demand.volume - demand.placed_demand
                if leftover < base.MIN_FLOW:
                    continue

                placed_now, _remain = demand.place(flow_graph=graph)
                placed_in_this_round += placed_now

            if reoptimize_after_each_round and placed_in_this_round > 0.0:
                _reoptimize_priority_demands(graph, demands_in_class)

            if placed_in_this_round < base.MIN_FLOW:
                any_leftover = any(
                    (d.volume - d.placed_demand) >= base.MIN_FLOW
                    for d in demands_in_class
                )
                if not any_leftover:
                    break
                if not reopt_attempted:
                    _reoptimize_priority_demands(graph, demands_in_class)
                    reopt_attempted = True
                    continue
                break

        # Add only the net increase for this class to avoid double counting
        placed_after_class = sum(d.placed_demand for d in demands_in_class)
        total_placed += max(0.0, placed_after_class - placed_before_class)

    return total_placed


def _reoptimize_priority_demands(
    graph: StrictMultiDiGraph, demands_in_prio: List[Demand]
) -> None:
    """Re-run placement for each demand in the same priority class.

    Allows the policy to adjust to capacity changes due to other demands.
    """
    for dmd in demands_in_prio:
        if not dmd.flow_policy:
            continue
        placed_volume = dmd.placed_demand
        dmd.flow_policy.remove_demand(graph)
        # Use a demand-unique flow_class key to keep policy flows consistent
        flow_class_key = (
            dmd.demand_class,
            dmd.src_node,
            dmd.dst_node,
            id(dmd),
        )
        dmd.flow_policy.place_demand(
            graph,
            dmd.src_node,
            dmd.dst_node,
            flow_class_key,
            placed_volume,
        )
        dmd.placed_demand = dmd.flow_policy.placed_demand
