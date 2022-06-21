# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.algorithms.common import EdgeSelect, init_flow_graph
from ngraph.algorithms.place_flow import FlowPlacement

from ngraph.graph import MultiDiGraph
from ngraph.demand import Demand, FlowPolicy, PathAlg


@pytest.fixture
def line_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=5)
    g.add_edge("B", "A", metric=1, capacity=5)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "B", metric=1, capacity=3)
    return g


@pytest.fixture
def graph_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("A", "B", metric=1, capacity=4)
    g.add_edge("A", "B", metric=1, capacity=6)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "D", metric=2, capacity=3)
    g.add_edge("A", "E", metric=1, capacity=5)
    g.add_edge("E", "C", metric=1, capacity=4)
    g.add_edge("A", "D", metric=4, capacity=2)
    g.add_edge("C", "F", metric=1, capacity=1)
    g.add_edge("F", "D", metric=1, capacity=2)
    return g


@pytest.fixture
def graph_square_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
    return g


@pytest.fixture
def graph_square_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=2)
    g.add_edge("D", "C", metric=1, capacity=2)
    return g


class TestDemand:
    def test_demand_1(self):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
        )
        assert Demand("A", "C", float("inf"), flow_policy)

    def test_demand_place_1(self, line_1):
        r = init_flow_graph(line_1)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_flow, remaining_flow = d.place(r)

        assert placed_flow == 4
        assert remaining_flow == float("inf")
        assert d.placed_flow == placed_flow
        assert d.nodes == {"A", "B", "C"}
        assert d.edges == {0, 2, 4}
        assert (
            any(
                edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
            )
            == False
        )
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 1,
                    "capacity": 5,
                    "flow": 4.0,
                    "flows": {("A", "C", "TEST"): 4.0},
                },
            ),
            1: ("B", "A", 1, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                },
            ),
            3: ("C", "B", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: (
                "B",
                "C",
                4,
                {
                    "metric": 1,
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", "TEST"): 3.0},
                },
            ),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
        }

    def test_demand_place_2(self, graph_square_1):
        r = init_flow_graph(graph_square_1)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_flow, remaining_flow = d.place(r)
        assert placed_flow == 1
        assert remaining_flow == float("inf")

    def test_demand_place_3(self, graph_square_1):
        r = init_flow_graph(graph_square_1)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_flow, remaining_flow = d.place(r)
        assert placed_flow == 3
        assert remaining_flow == float("inf")

    def test_demand_place_4(self, graph_square_2):
        r = init_flow_graph(graph_square_2)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_flow, remaining_flow = d.place(r)
        assert placed_flow == 2
        assert remaining_flow == float("inf")
