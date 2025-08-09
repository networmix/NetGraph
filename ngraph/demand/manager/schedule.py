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

        for round_idx in range(placement_rounds):
            placed_in_this_round = 0.0
            rounds_left = placement_rounds - round_idx

            for demand in demands_in_class:
                leftover = demand.volume - demand.placed_demand
                if leftover < base.MIN_FLOW:
                    continue

                step_to_place = leftover / float(rounds_left)
                placed_now, _remain = demand.place(
                    flow_graph=graph,
                    max_placement=step_to_place,
                )
                total_placed += placed_now
                placed_in_this_round += placed_now

            if reoptimize_after_each_round and placed_in_this_round > 0.0:
                _reoptimize_priority_demands(graph, demands_in_class)

            # If no progress was made, no need to continue extra rounds
            if placed_in_this_round < base.MIN_FLOW:
                break

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
        dmd.flow_policy.place_demand(
            graph,
            dmd.src_node,
            dmd.dst_node,
            dmd.demand_class,
            placed_volume,
        )
        dmd.placed_demand = dmd.flow_policy.placed_demand
