# pylint: disable=protected-access,invalid-name
import pytest

from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.calc_capacity import calc_graph_capacity, FlowPlacement
from tests.lib.algorithms.sample_graphs import *


class TestGraphCapacity:
    def test_calc_graph_capacity_empty_graph(self):
        r = init_flow_graph(StrictMultiDiGraph())

        # Expected an exception ValueError because the graph is empty
        with pytest.raises(ValueError):
            max_flow, flow_dict = calc_graph_capacity(
                r, "A", "C", {}, flow_placement=FlowPlacement.PROPORTIONAL
            )

    def test_calc_graph_capacity_empty_pred(self):
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        g.add_edge("A", "B", capacity=1)
        g.add_edge("B", "C", capacity=1)
        r = init_flow_graph(g)

        # Expected max_flow = 0 because the path is invalid
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", {}, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 0

    def test_calc_graph_capacity_no_cap(self):
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        g.add_edge("A", "B", key=0, capacity=0)
        g.add_edge("B", "C", key=1, capacity=1)
        r = init_flow_graph(g)
        pred = {"A": {}, "B": {"A": [0]}, "C": {"B": [1]}}

        # Expected max_flow = 0 because there is no capacity along the path
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 0

    def test_calc_graph_capacity_line1(self, line1):
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 4
        assert flow_dict == {
            "A": {"B": 1.0},
            "B": {"A": -1.0, "C": 1.0},
            "C": {"B": -1.0},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 2
        assert flow_dict == {
            "A": {"B": 1.0},
            "B": {"A": -1.0, "C": 1.0},
            "C": {"B": -1.0},
        }

    def test_calc_graph_capacity_triangle1(self, triangle1):
        _, pred = spf(triangle1, "A")
        r = init_flow_graph(triangle1)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 5
        assert flow_dict == {"A": {"C": 1.0}, "C": {"A": -1.0}}

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 5
        assert flow_dict == {"A": {"C": 1.0}, "C": {"A": -1.0}}

    def test_calc_graph_capacity_square1(self, square1):
        _, pred = spf(square1, "A")
        r = init_flow_graph(square1)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 1
        assert flow_dict == {
            "C": {"B": -1.0},
            "B": {"C": 1.0, "A": -1.0},
            "A": {"B": 1.0},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 1
        assert flow_dict == {
            "C": {"B": -1.0},
            "B": {"C": 1.0, "A": -1.0},
            "A": {"B": 1.0},
        }

    def test_calc_graph_capacity_square2_1(self, square2):
        _, pred = spf(square2, "A")
        r = init_flow_graph(square2)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 3
        assert flow_dict == {
            "A": {"B": 0.3333333333333333, "D": 0.6666666666666666},
            "B": {"A": -0.3333333333333333, "C": 0.3333333333333333},
            "C": {"B": -0.3333333333333333, "D": -0.6666666666666666},
            "D": {"A": -0.6666666666666666, "C": 0.6666666666666666},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 2
        assert flow_dict == {
            "A": {"B": 0.5, "D": 0.5},
            "B": {"A": -0.5, "C": 0.5},
            "C": {"B": -0.5, "D": -0.5},
            "D": {"A": -0.5, "C": 0.5},
        }

    def test_calc_graph_capacity_square2_2(self, square2):
        _, pred = spf(square2, "A")
        r = init_flow_graph(square2)
        r["A"]["B"][0]["flow"] = 1

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 2
        assert flow_dict == {
            "A": {"B": -0.0, "D": 1.0},
            "B": {"A": -0.0, "C": -0.0},
            "C": {"B": -0.0, "D": -1.0},
            "D": {"A": -1.0, "C": 1.0},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 0
        assert flow_dict == {
            "A": {"B": 0.5, "D": 0.5},
            "B": {"A": -0.5, "C": 0.5},
            "C": {"B": -0.5, "D": -0.5},
            "D": {"A": -0.5, "C": 0.5},
        }

    def test_calc_graph_capacity_square3(self, square3):
        _, pred = spf(square3, "A")
        r = init_flow_graph(square3)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 150
        assert flow_dict == {
            "A": {"B": 0.6666666666666666, "D": 0.3333333333333333},
            "B": {"A": -0.6666666666666666, "C": 0.6666666666666666},
            "C": {"B": -0.6666666666666666, "D": -0.3333333333333333},
            "D": {"A": -0.3333333333333333, "C": 0.3333333333333333},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 100
        assert flow_dict == {
            "A": {"B": 0.5, "D": 0.5},
            "B": {"A": -0.5, "C": 0.5},
            "C": {"B": -0.5, "D": -0.5},
            "D": {"A": -0.5, "C": 0.5},
        }

    def test_calc_graph_capacity_square4(self, square4):
        _, pred = spf(square4, "A")
        r = init_flow_graph(square4)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 150
        assert flow_dict == {
            "A": {"B": 0.6666666666666666, "D": 0.3333333333333333},
            "B": {"A": -0.6666666666666666, "C": 0.6666666666666666},
            "C": {"B": -0.6666666666666666, "D": -0.3333333333333333},
            "D": {"A": -0.3333333333333333, "C": 0.3333333333333333},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 100
        assert flow_dict == {
            "A": {"B": 0.5, "D": 0.5},
            "B": {"A": -0.5, "C": 0.5},
            "C": {"B": -0.5, "D": -0.5},
            "D": {"A": -0.5, "C": 0.5},
        }

    def test_calc_graph_capacity_square5(self, square5):
        _, pred = spf(square5, "A")
        r = init_flow_graph(square5)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "D", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 2
        assert flow_dict == {
            "A": {"B": 0.5, "C": 0.5},
            "B": {"A": -0.5, "D": 0.5},
            "C": {"A": -0.5, "D": 0.5},
            "D": {"B": -0.5, "C": -0.5},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "D", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 2
        assert flow_dict == {
            "A": {"B": 0.5, "C": 0.5},
            "B": {"A": -0.5, "D": 0.5},
            "C": {"A": -0.5, "D": 0.5},
            "D": {"B": -0.5, "C": -0.5},
        }

    def test_calc_graph_capacity_graph1(self, graph1):
        _, pred = spf(graph1, "A")
        r = init_flow_graph(graph1)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "E", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 1
        assert flow_dict == {
            "A": {"B": 1.0, "C": -0.0},
            "B": {"A": -1.0, "D": 1.0},
            "C": {"A": -0.0, "D": -0.0},
            "D": {"B": -1.0, "C": -0.0, "E": 1.0},
            "E": {"D": -1.0},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "E", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 1
        assert flow_dict == {
            "E": {"D": -1.0},
            "D": {"E": 1.0, "B": -0.5, "C": -0.5},
            "B": {"D": 0.5, "A": -0.5},
            "C": {"D": 0.5, "A": -0.5},
            "A": {"B": 0.5, "C": 0.5},
        }

    def test_calc_graph_capacity_graph3(self, graph3):
        _, pred = spf(graph3, "A")
        r = init_flow_graph(graph3)

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "D", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 6
        assert flow_dict == {
            "A": {"B": 0.6666666666666666, "D": 0.3333333333333333, "E": -0.0},
            "B": {"A": -0.6666666666666666, "C": 0.6666666666666666},
            "C": {
                "B": -0.6666666666666666,
                "D": 0.5,
                "E": -0.0,
                "F": 0.16666666666666666,
            },
            "D": {"A": -0.3333333333333333, "C": -0.5, "F": -0.16666666666666666},
            "E": {"A": -0.0, "C": -0.0},
            "F": {"C": -0.16666666666666666, "D": 0.16666666666666666},
        }

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "D", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert max_flow == 2.5
        assert flow_dict == {
            "A": {"B": 0.6, "D": 0.2, "E": 0.2},
            "B": {"A": -0.6, "C": 0.6},
            "C": {"B": -0.6, "D": 0.4, "E": -0.2, "F": 0.4},
            "D": {"A": -0.2, "C": -0.4, "F": -0.4},
            "E": {"A": -0.2, "C": 0.2},
            "F": {"C": -0.4, "D": 0.4},
        }
