# pylint: disable=protected-access,invalid-name
from typing import Dict, List

import pytest

from ngraph.algorithms.capacity import (
    FlowPlacement,
    _init_graph_data,
    calc_graph_capacity,
)
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.algorithms.spf import spf
from ngraph.graph.strict_multidigraph import EdgeID, NodeID, StrictMultiDiGraph

# Type alias to ensure consistency with library expectations
PredDict = Dict[NodeID, Dict[NodeID, List[EdgeID]]]


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
        pred: PredDict = {"A": {}, "B": {"A": [0]}, "C": {"B": [1]}}

        # Expected max_flow = 0 because there is no capacity along the path
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "C", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 0

    def test_calc_graph_capacity_line1(self, line1):
        _, pred = spf(line1, "A")
        pred: PredDict = pred  # Type annotation for clarity
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

    def test_calc_graph_capacity_self_loop_proportional(self):
        """
        Test self-loop behavior with PROPORTIONAL flow placement.
        When source equals destination, max flow should always be 0.
        """
        # Create a graph with a self-loop
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_edge("A", "A", key=0, capacity=10.0, flow=0.0, flows={}, cost=1)
        r = init_flow_graph(g)

        # Create a simple pred with self-loop
        pred: PredDict = {"A": {"A": [0]}}

        # Test PROPORTIONAL placement
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "A", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )

        assert max_flow == 0.0
        # flow_dict should be empty or contain only zero flows
        for node_flows in flow_dict.values():
            for flow_value in node_flows.values():
                assert flow_value == 0.0

    def test_calc_graph_capacity_self_loop_equal_balanced(self):
        """
        Test self-loop behavior with EQUAL_BALANCED flow placement.
        When source equals destination, max flow should always be 0.
        """
        # Create a graph with multiple self-loops
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_edge("A", "A", key=0, capacity=5.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "A", key=1, capacity=3.0, flow=0.0, flows={}, cost=1)
        r = init_flow_graph(g)

        # Create pred with multiple self-loop edges
        pred: PredDict = {"A": {"A": [0, 1]}}

        # Test EQUAL_BALANCED placement
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "A", pred, flow_placement=FlowPlacement.EQUAL_BALANCED
        )

        assert max_flow == 0.0
        # flow_dict should be empty or contain only zero flows
        for node_flows in flow_dict.values():
            for flow_value in node_flows.values():
                assert flow_value == 0.0

    def test_calc_graph_capacity_self_loop_with_other_edges(self):
        """
        Test self-loop behavior in a graph that also has regular edges.
        The self-loop itself should still return 0 flow.
        """
        # Create a graph with both self-loop and regular edges
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_edge("A", "A", key=0, capacity=10.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "B", key=1, capacity=5.0, flow=0.0, flows={}, cost=2)
        g.add_edge("B", "A", key=2, capacity=3.0, flow=0.0, flows={}, cost=2)
        r = init_flow_graph(g)

        # Test self-loop A->A
        pred_self: PredDict = {"A": {"A": [0]}}
        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "A", pred_self, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 0.0

        # Test regular flow A->B to verify graph still works for non-self-loops
        pred_regular: PredDict = {"A": {}, "B": {"A": [1]}}
        max_flow_regular, _ = calc_graph_capacity(
            r, "A", "B", pred_regular, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow_regular == 5.0  # Should be limited by A->B capacity

    def test_reverse_residual_init_graph_data_proportional(self):
        """_init_graph_data should expose dst->leaf residual capacity in PROPORTIONAL.

        Build a tiny graph with forward edges leaf->dc and dc->sink, and reverse dc->leaf.
        SPF pred contains dc predecessors (leaves) and sink predecessor (dc).
        The reversed residual must have positive capacity dc->leaf equal to sum(capacity - flow).
        """
        g = StrictMultiDiGraph()
        for n in ("source", "A/dc", "A/leaf", "sink"):
            g.add_node(n)
        # Forward edges
        e1 = g.add_edge("A/leaf", "A/dc", capacity=10.0, cost=1, flow=0.0, flows={})
        g.add_edge("A/dc", "sink", capacity=float("inf"), cost=0, flow=0.0, flows={})
        # Reverse edge to simulate bidirectional link
        g.add_edge("A/dc", "A/leaf", capacity=10.0, cost=1, flow=0.0, flows={})

        # SPF-like predecessor dict: include both directions present in graph
        # sink<-A/dc, A/dc<-A/leaf, and A/leaf<-A/dc (reverse link)
        pred: PredDict = {
            "source": {},
            "A/dc": {"A/leaf": [e1]},
            "A/leaf": {"A/dc": list(g.edges_between("A/dc", "A/leaf"))},
            "sink": {"A/dc": list(g.edges_between("A/dc", "sink"))},
        }

        # Run init
        succ, levels, residual_cap, flow_dict = _init_graph_data(
            g,
            pred,
            init_node="sink",
            flow_placement=FlowPlacement.PROPORTIONAL,
            capacity_attr="capacity",
            flow_attr="flow",
        )
        # residuals must reflect both forward directions, and zero-init must not overwrite
        assert residual_cap["A/dc"]["A/leaf"] == 10.0
        assert residual_cap["A/leaf"]["A/dc"] == 10.0

    def test_reverse_residual_init_graph_data_equal_balanced(self):
        """_init_graph_data should set reverse residual in EQUAL_BALANCED as min*count.

        With two parallel edges leaf->dc with caps (5, 7), min=5 and count=2 -> reverse cap = 10.
        """
        g = StrictMultiDiGraph()
        for n in ("source", "A/dc", "A/leaf", "sink"):
            g.add_node(n)
        # Two parallel forward edges leaf->dc
        e1 = g.add_edge("A/leaf", "A/dc", capacity=5.0, cost=1, flow=0.0, flows={})
        e2 = g.add_edge("A/leaf", "A/dc", capacity=7.0, cost=1, flow=0.0, flows={})
        g.add_edge("A/dc", "sink", capacity=float("inf"), cost=0, flow=0.0, flows={})
        # Reverse edge present too
        g.add_edge("A/dc", "A/leaf", capacity=7.0, cost=1, flow=0.0, flows={})

        pred: PredDict = {
            "source": {},
            "A/dc": {"A/leaf": [e1, e2]},
            "sink": {"A/dc": list(g.edges_between("A/dc", "sink"))},
        }

        succ, levels, residual_cap, flow_dict = _init_graph_data(
            g,
            pred,
            init_node="sink",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            capacity_attr="capacity",
            flow_attr="flow",
        )
        # In EQUAL_BALANCED, the reverse residual is assigned on leaf->dc orientation (adj->node)
        # i.e., residual_cap[leaf][dc] = min(capacities) * count = 5*2 = 10
        assert residual_cap["A/leaf"]["A/dc"] == 10.0
        # forward side initialized to 0 in reversed orientation
        assert residual_cap["A/dc"]["A/leaf"] == 0.0

    def test_dc_to_dc_reverse_edge_first_hop_proportional(self):
        """Reverse-edge-first hop at destination should yield positive flow.

        Topology (with reverse edges to simulate bidirectional links):
          A_leaf -> A_dc  (10)
          A_leaf -> B_leaf (10)
          B_leaf -> B_dc  (10)
          A_dc  -> A_leaf (10)  # reverse present
          B_dc  -> B_leaf (10)  # reverse present

        Pseudo nodes: source -> A_dc, B_dc -> sink
        Expected max_flow(source, sink) = 10.0 in PROPORTIONAL mode.
        """
        g = StrictMultiDiGraph()
        for n in ("A_dc", "A_leaf", "B_leaf", "B_dc", "source", "sink"):
            g.add_node(n)

        # Forward edges
        g.add_edge("A_leaf", "A_dc", capacity=10.0, cost=1)
        g.add_edge("A_leaf", "B_leaf", capacity=10.0, cost=1)
        g.add_edge("B_leaf", "B_dc", capacity=10.0, cost=1)
        # Reverse edges
        g.add_edge("A_dc", "A_leaf", capacity=10.0, cost=1)
        g.add_edge("B_dc", "B_leaf", capacity=10.0, cost=1)

        # Pseudo source/sink
        g.add_edge("source", "A_dc", capacity=float("inf"), cost=0)
        g.add_edge("B_dc", "sink", capacity=float("inf"), cost=0)

        r = init_flow_graph(g)
        # Compute SPF with dst_node to mirror real usage in calc_max_flow
        _costs, pred = spf(r, "source", dst_node="sink")
        max_flow, _flow_dict = calc_graph_capacity(
            r, "source", "sink", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 10.0

    def test_dc_to_dc_unidirectional_zero(self):
        """Without reverse edges, DC cannot send to leaf; flow must be zero."""
        g = StrictMultiDiGraph()
        for n in ("A_dc", "A_leaf", "B_leaf", "B_dc", "source", "sink"):
            g.add_node(n)

        # Forward edges only
        g.add_edge("A_leaf", "A_dc", capacity=10.0, cost=1)
        g.add_edge("A_leaf", "B_leaf", capacity=10.0, cost=1)
        g.add_edge("B_leaf", "B_dc", capacity=10.0, cost=1)

        # Pseudo source/sink
        g.add_edge("source", "A_dc", capacity=float("inf"), cost=0)
        g.add_edge("B_dc", "sink", capacity=float("inf"), cost=0)

        r = init_flow_graph(g)
        _costs, pred = spf(r, "source", dst_node="sink")
        max_flow, _flow_dict = calc_graph_capacity(
            r, "source", "sink", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 0.0

    def test_calc_graph_capacity_self_loop_empty_pred(self):
        """
        Test self-loop behavior when pred is empty.
        Should return 0 flow for self-loop even with empty pred.
        """
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_edge("A", "A", key=0, capacity=10.0, flow=0.0, flows={}, cost=1)
        r = init_flow_graph(g)

        # Empty pred
        pred: PredDict = {}

        max_flow, flow_dict = calc_graph_capacity(
            r, "A", "A", pred, flow_placement=FlowPlacement.PROPORTIONAL
        )

        assert max_flow == 0.0
        # flow_dict should be empty or contain only zero flows
        for node_flows in flow_dict.values():
            for flow_value in node_flows.values():
                assert flow_value == 0.0
