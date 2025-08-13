from __future__ import annotations

from ngraph.algorithms.base import EdgeSelect, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.algorithms.placement import FlowPlacement
from ngraph.demand import Demand
from ngraph.demand.manager.schedule import place_demands_round_robin
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def _graph_bottleneck_then_alt() -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    for n in ("A", "B", "C", "D"):
        g.add_node(n)
    # Preferred low-cost path A->B->D has tight capacity on B->D
    g.add_edge("A", "B", cost=1, capacity=1)
    g.add_edge("B", "D", cost=1, capacity=0.001)
    # Alternate slightly higher-cost path A->C->D has enough capacity
    g.add_edge("A", "C", cost=2, capacity=1)
    g.add_edge("C", "D", cost=2, capacity=1)
    return g


def _policy_capacity_aware() -> FlowPolicy:
    return FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=False,
        reoptimize_flows_on_each_placement=False,
        max_flow_count=2,
    )


def test_reopt_on_stall_unlocks_alt_paths() -> None:
    g = _graph_bottleneck_then_alt()
    init_flow_graph(g)
    d = Demand("A", "D", 0.5, demand_class=0, flow_policy=_policy_capacity_aware())
    # With reoptization after rounds enabled, scheduler should avoid stalling
    total = place_demands_round_robin(
        g, [d], placement_rounds=5, reoptimize_after_each_round=True
    )
    # At least more than the tight bottleneck should be placed via alternative path
    assert total > 0.001
