# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.algorithms.common import init_flow_graph
from ngraph.algorithms.place_flow import (
    FlowPlacement,
    FlowPlacementMeta,
    place_flow_on_graph,
)

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf


@pytest.fixture
def line_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=5)
    g.add_edge("B", "A", metric=1, capacity=5)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "B", metric=1, capacity=3)
    g.add_edge("B", "C", metric=2, capacity=7)
    g.add_edge("C", "B", metric=2, capacity=7)
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
def graph_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("A", "B", metric=1, capacity=0)
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


class TestPlaceFlowGraph:
    def test_place_flow_on_graph_prop_1(self, line_1):
        _, pred = spf(line_1, "A")
        r = init_flow_graph(line_1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow_index=("A", "C", "TEST"),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 4
        assert flow_placement_meta.remaining_flow == float("inf")
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
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }
        assert flow_placement_meta.nodes == {"A", "C", "B"}
        assert flow_placement_meta.edges == {0, 2, 4}

    def test_place_flow_on_graph_prop_2(self, line_1):
        _, pred = spf(line_1, "A")
        r = init_flow_graph(line_1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=3,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 3
        assert flow_placement_meta.remaining_flow == 0

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=3,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 1
        assert flow_placement_meta.remaining_flow == 2
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
                    "flows": {("A", "C", None): 4.0},
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
                    "flows": {("A", "C", None): 1.0},
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
                    "flows": {("A", "C", None): 3.0},
                },
            ),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_prop_3(self, graph_1):
        _, pred = spf(graph_1, "A")
        r = init_flow_graph(graph_1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 10
        assert flow_placement_meta.remaining_flow == float("inf")
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
                    "capacity": 2,
                    "flow": 1.1764705882352942,
                    "flows": {("A", "C", None): 1.1764705882352942},
                },
            ),
            1: (
                "A",
                "B",
                1,
                {
                    "metric": 1,
                    "capacity": 4,
                    "flow": 2.3529411764705883,
                    "flows": {("A", "C", None): 2.3529411764705883},
                },
            ),
            2: (
                "A",
                "B",
                2,
                {
                    "metric": 1,
                    "capacity": 6,
                    "flow": 3.5294117647058822,
                    "flows": {("A", "C", None): 3.5294117647058822},
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "metric": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            4: (
                "B",
                "C",
                4,
                {
                    "metric": 1,
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                },
            ),
            5: (
                "B",
                "C",
                5,
                {
                    "metric": 1,
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", None): 3.0},
                },
            ),
            6: ("C", "D", 6, {"metric": 2, "capacity": 3, "flow": 0, "flows": {}}),
            7: (
                "A",
                "E",
                7,
                {
                    "metric": 1,
                    "capacity": 5,
                    "flow": 2.9411764705882355,
                    "flows": {("A", "C", None): 2.9411764705882355},
                },
            ),
            8: (
                "E",
                "C",
                8,
                {
                    "metric": 1,
                    "capacity": 4,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                },
            ),
            9: ("A", "D", 9, {"metric": 4, "capacity": 2, "flow": 0, "flows": {}}),
            10: ("C", "F", 10, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            11: ("F", "D", 11, {"metric": 1, "capacity": 2, "flow": 0, "flows": {}}),
        }
        assert flow_placement_meta.nodes == {"A", "E", "B", "C"}
        assert flow_placement_meta.edges == {0, 1, 2, 3, 4, 5, 7, 8}

    def test_place_flow_on_graph_prop_4(self, graph_2):
        _, pred = spf(graph_2, "A")
        r = init_flow_graph(graph_2)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 10
        assert flow_placement_meta.remaining_flow == float("inf")
        assert (
            any(
                edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
            )
            == False
        )
        print(r.get_edges())
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 1,
                    "capacity": 2,
                    "flow": 1.5384615384615385,
                    "flows": {("A", "C", None): 1.5384615384615385},
                },
            ),
            1: ("A", "B", 1, {"metric": 1, "capacity": 0, "flow": 0, "flows": {}}),
            2: (
                "A",
                "B",
                2,
                {
                    "metric": 1,
                    "capacity": 6,
                    "flow": 4.615384615384616,
                    "flows": {("A", "C", None): 4.615384615384616},
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "metric": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            4: (
                "B",
                "C",
                4,
                {
                    "metric": 1,
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                },
            ),
            5: (
                "B",
                "C",
                5,
                {
                    "metric": 1,
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", None): 3.0},
                },
            ),
            6: ("C", "D", 6, {"metric": 2, "capacity": 3, "flow": 0, "flows": {}}),
            7: (
                "A",
                "E",
                7,
                {
                    "metric": 1,
                    "capacity": 5,
                    "flow": 3.8461538461538463,
                    "flows": {("A", "C", None): 3.8461538461538463},
                },
            ),
            8: (
                "E",
                "C",
                8,
                {
                    "metric": 1,
                    "capacity": 4,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                },
            ),
            9: ("A", "D", 9, {"metric": 4, "capacity": 2, "flow": 0, "flows": {}}),
            10: ("C", "F", 10, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            11: ("F", "D", 11, {"metric": 1, "capacity": 2, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_balanced_1(self, line_1):
        _, pred = spf(line_1, "A")
        r = init_flow_graph(line_1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )
        assert flow_placement_meta.placed_flow == 2
        assert flow_placement_meta.remaining_flow == float("inf")
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
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
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
                    "flows": {("A", "C", None): 1.0},
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
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_balanced_2(self, line_1):
        _, pred = spf(line_1, "A")
        r = init_flow_graph(line_1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=1,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )
        assert flow_placement_meta.placed_flow == 1
        assert flow_placement_meta.remaining_flow == 0

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=2,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )
        assert flow_placement_meta.placed_flow == 1
        assert flow_placement_meta.remaining_flow == 1
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
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
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
                    "flows": {("A", "C", None): 1.0},
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
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_balanced_3(self, graph_2):
        _, pred = spf(graph_2, "A")
        r = init_flow_graph(graph_2)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=1,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )
        assert flow_placement_meta.placed_flow == 0
        assert flow_placement_meta.remaining_flow == 1
        assert (
            any(
                edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
            )
            == False
        )
        assert flow_placement_meta.nodes == set()
        assert flow_placement_meta.edges == set()
        assert r.get_edges() == {
            0: ("A", "B", 0, {"metric": 1, "capacity": 2, "flow": 0, "flows": {}}),
            1: ("A", "B", 1, {"metric": 1, "capacity": 0, "flow": 0, "flows": {}}),
            2: ("A", "B", 2, {"metric": 1, "capacity": 6, "flow": 0, "flows": {}}),
            3: ("B", "C", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: ("B", "C", 4, {"metric": 1, "capacity": 2, "flow": 0, "flows": {}}),
            5: ("B", "C", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("C", "D", 6, {"metric": 2, "capacity": 3, "flow": 0, "flows": {}}),
            7: ("A", "E", 7, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            8: ("E", "C", 8, {"metric": 1, "capacity": 4, "flow": 0, "flows": {}}),
            9: ("A", "D", 9, {"metric": 4, "capacity": 2, "flow": 0, "flows": {}}),
            10: ("C", "F", 10, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            11: ("F", "D", 11, {"metric": 1, "capacity": 2, "flow": 0, "flows": {}}),
        }
