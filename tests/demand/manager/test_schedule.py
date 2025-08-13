from __future__ import annotations

from ngraph.algorithms.base import MIN_FLOW, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.demand import Demand
from ngraph.demand.manager.schedule import place_demands_round_robin
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def _graph_square() -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)
    # Two disjoint paths A->B->C and A->D->C
    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("B", "C", key=1, cost=1, capacity=1)
    g.add_edge("A", "D", key=2, cost=1, capacity=1)
    g.add_edge("D", "C", key=3, cost=1, capacity=1)
    return g


def _policy() -> FlowPolicy:
    # Defaults require additional params; set minimal working configuration
    from ngraph.algorithms.base import EdgeSelect
    from ngraph.algorithms.placement import FlowPlacement

    return FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST,
        multipath=True,
    )


def test_round_robin_places_all_when_capacity_sufficient() -> None:
    g = _graph_square()
    init_flow_graph(g)
    demands = [
        Demand("A", "C", 1.0, demand_class=0, flow_policy=_policy()),
        Demand("A", "C", 1.0, demand_class=0, flow_policy=_policy()),
    ]

    total = place_demands_round_robin(g, demands, placement_rounds=5)
    assert abs(total - 2.0) < 1e-9
    assert all(abs(d.placed_demand - 1.0) < 1e-9 for d in demands)


def test_round_robin_stops_when_no_progress() -> None:
    g = _graph_square()
    # Reduce capacity on one edge to limit placement
    # Set B->C capacity to 0 to enforce single path usage only
    g.add_edge("B", "C", key=10, cost=1, capacity=0)
    init_flow_graph(g)

    d1 = Demand("A", "C", 2.0, demand_class=0, flow_policy=_policy())
    d2 = Demand("A", "C", 2.0, demand_class=0, flow_policy=_policy())
    total = place_demands_round_robin(g, [d1, d2], placement_rounds=50)
    # The two available links should allow at most 2 units total
    assert abs(total - 2.0) < 1e-9


def test_round_robin_small_demand_with_many_rounds_places_full_volume() -> None:
    """Ensure tiny but valid demand does not stall across many rounds.

    This guards against step sizes dropping below MIN_FLOW when rounds_left is large.
    """
    g = _graph_square()
    init_flow_graph(g)

    tiny = MIN_FLOW * 1.1
    demands = [Demand("A", "C", tiny, demand_class=0, flow_policy=_policy())]

    total = place_demands_round_robin(g, demands, placement_rounds=100)
    # May leave remainder < MIN_FLOW due to threshold semantics
    assert abs(total - tiny) <= MIN_FLOW
    assert abs(demands[0].placed_demand - tiny) <= MIN_FLOW
