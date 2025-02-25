import pytest
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.algorithms.place_flow import (
    place_flow_on_graph,
    remove_flow_from_graph,
)
from ngraph.lib.algorithms.calc_capacity import FlowPlacement

from ngraph.lib.algorithms.spf import spf
from tests.lib.algorithms.sample_graphs import *


class TestPlaceFlowOnGraph:
    def test_place_flow_on_graph_line1_proportional(self, line1):
        """
        Place flow from A->C on line1 using PROPORTIONAL flow placement.
        Verifies the final distribution does not exceed capacity
        and checks metadata (placed_flow, remaining_flow, edges/nodes touched).
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Asserting exact final edge attributes:
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "cost": 1,
                    "capacity": 5,
                    "flow": 4.0,
                    "flows": {("A", "C", "TEST"): 4.0},
                },
            ),
            1: ("B", "A", 1, {"cost": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: (
                "B",
                "C",
                2,
                {
                    "cost": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                },
            ),
            3: ("C", "B", 3, {"cost": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: (
                "B",
                "C",
                4,
                {
                    "cost": 1,
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", "TEST"): 3.0},
                },
            ),
            5: ("C", "B", 5, {"cost": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }
        assert flow_placement_meta.nodes == {"A", "C", "B"}
        assert flow_placement_meta.edges == {0, 2, 4}

    def test_place_flow_on_graph_line1_equal(self, line1):
        """
        Place flow using EQUAL_BALANCED on line1. Checks that
        flow is split evenly among parallel edges from B->C.
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow_index=("A", "C", "TEST"),
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert flow_placement_meta.placed_flow == 2
        assert flow_placement_meta.remaining_flow == float("inf")
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Check final flows match expectations:
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 5,
                    "flow": 2.0,
                    "flows": {("A", "C", "TEST"): 2.0},
                    "cost": 1,
                },
            ),
            1: ("B", "A", 1, {"capacity": 5, "flow": 0, "flows": {}, "cost": 1}),
            2: (
                "B",
                "C",
                2,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                    "cost": 1,
                },
            ),
            3: ("C", "B", 3, {"capacity": 1, "flow": 0, "flows": {}, "cost": 1}),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 3,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                    "cost": 1,
                },
            ),
            5: ("C", "B", 5, {"capacity": 3, "flow": 0, "flows": {}, "cost": 1}),
            6: ("B", "C", 6, {"capacity": 7, "flow": 0, "flows": {}, "cost": 2}),
            7: ("C", "B", 7, {"capacity": 7, "flow": 0, "flows": {}, "cost": 2}),
        }
        assert flow_placement_meta.nodes == {"A", "C", "B"}
        assert flow_placement_meta.edges == {0, 2, 4}

    def test_place_flow_on_graph_line1_proportional(self, line1):
        """
        In two steps, place 3 units of flow, then attempt another 3.
        Check partial flow placement when capacity is partially exhausted.
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

        # First attempt: place 3 units
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

        # Second attempt: place another 3 units (only 1 unit left)
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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Check final distribution
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "cost": 1,
                    "capacity": 5,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                },
            ),
            1: ("B", "A", 1, {"cost": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: (
                "B",
                "C",
                2,
                {
                    "cost": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            3: ("C", "B", 3, {"cost": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: (
                "B",
                "C",
                4,
                {
                    "cost": 1,
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", None): 3.0},
                },
            ),
            5: ("C", "B", 5, {"cost": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_graph3_proportional_1(self, graph3):
        """
        Place flow from A->C on 'graph3' with PROPORTIONAL distribution.
        Ensures the total feasible flow is 10 and that edges do not exceed capacity.
        """
        _, pred = spf(graph3, "A")
        r = init_flow_graph(graph3)

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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Check the final edges, as given below:
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                    "cost": 1,
                },
            ),
            1: (
                "A",
                "B",
                1,
                {
                    "capacity": 4,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                    "cost": 1,
                },
            ),
            2: (
                "A",
                "B",
                2,
                {
                    "capacity": 6,
                    "flow": 3.0,
                    "flows": {("A", "C", None): 3.0},
                    "cost": 1,
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                    "cost": 1,
                },
            ),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                    "cost": 1,
                },
            ),
            5: (
                "B",
                "C",
                5,
                {
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "C", None): 3.0},
                    "cost": 1,
                },
            ),
            6: ("C", "D", 6, {"capacity": 3, "flow": 0, "flows": {}, "cost": 2}),
            7: (
                "A",
                "E",
                7,
                {
                    "capacity": 5,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                    "cost": 1,
                },
            ),
            8: (
                "E",
                "C",
                8,
                {
                    "capacity": 4,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                    "cost": 1,
                },
            ),
            9: ("A", "D", 9, {"capacity": 2, "flow": 0, "flows": {}, "cost": 4}),
            10: ("C", "F", 10, {"capacity": 1, "flow": 0, "flows": {}, "cost": 1}),
            11: ("F", "D", 11, {"capacity": 2, "flow": 0, "flows": {}, "cost": 1}),
        }
        assert flow_placement_meta.nodes == {"A", "E", "B", "C"}
        assert flow_placement_meta.edges == {0, 1, 2, 3, 4, 5, 7, 8}

    def test_place_flow_on_graph_graph3_proportional_2(self, graph3):
        """
        Another flow on 'graph3', from A->D. Checks partial flows
        split among multiple edges and the correctness of the final distribution.
        """
        _, pred = spf(graph3, "A")
        r = init_flow_graph(graph3)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "D",
            pred,
            flow_index=("A", "D", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        assert flow_placement_meta.placed_flow == 6
        assert flow_placement_meta.remaining_flow == float("inf")
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Confirm final distribution:
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 2,
                    "flow": 0.6666666666666666,
                    "flows": {("A", "D", None): 0.6666666666666666},
                    "cost": 1,
                },
            ),
            1: (
                "A",
                "B",
                1,
                {
                    "capacity": 4,
                    "flow": 1.3333333333333333,
                    "flows": {("A", "D", None): 1.3333333333333333},
                    "cost": 1,
                },
            ),
            2: (
                "A",
                "B",
                2,
                {
                    "capacity": 6,
                    "flow": 2.0,
                    "flows": {("A", "D", None): 2.0},
                    "cost": 1,
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "capacity": 1,
                    "flow": 0.6666666666666666,
                    "flows": {("A", "D", None): 0.6666666666666666},
                    "cost": 1,
                },
            ),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 2,
                    "flow": 1.3333333333333333,
                    "flows": {("A", "D", None): 1.3333333333333333},
                    "cost": 1,
                },
            ),
            5: (
                "B",
                "C",
                5,
                {
                    "capacity": 3,
                    "flow": 2.0,
                    "flows": {("A", "D", None): 2.0},
                    "cost": 1,
                },
            ),
            6: (
                "C",
                "D",
                6,
                {
                    "capacity": 3,
                    "flow": 3.0,
                    "flows": {("A", "D", None): 3.0},
                    "cost": 2,
                },
            ),
            7: ("A", "E", 7, {"capacity": 5, "flow": 0, "flows": {}, "cost": 1}),
            8: ("E", "C", 8, {"capacity": 4, "flow": 0, "flows": {}, "cost": 1}),
            9: (
                "A",
                "D",
                9,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "D", None): 2.0},
                    "cost": 4,
                },
            ),
            10: (
                "C",
                "F",
                10,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "D", None): 1.0},
                    "cost": 1,
                },
            ),
            11: (
                "F",
                "D",
                11,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "D", None): 1.0},
                    "cost": 1,
                },
            ),
        }

    def test_place_flow_on_graph_line1_balanced_1(self, line1):
        """
        Place flow using EQUAL_BALANCED on line1, verifying capacity usage
        and final flows from A->C.
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Check final state
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "cost": 1,
                    "capacity": 5,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                },
            ),
            1: ("B", "A", 1, {"cost": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: (
                "B",
                "C",
                2,
                {
                    "cost": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            3: ("C", "B", 3, {"cost": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: (
                "B",
                "C",
                4,
                {
                    "cost": 1,
                    "capacity": 3,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            5: ("C", "B", 5, {"cost": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_line1_balanced_2(self, line1):
        """
        Place flow in two steps (1, then 2) using EQUAL_BALANCED.
        The second step can only place 1 more unit due to capacity constraints.
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

        # Place 1 unit first
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

        # Attempt to place 2 more
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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        # Check final distribution
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "cost": 1,
                    "capacity": 5,
                    "flow": 2.0,
                    "flows": {("A", "C", None): 2.0},
                },
            ),
            1: ("B", "A", 1, {"cost": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: (
                "B",
                "C",
                2,
                {
                    "cost": 1,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            3: ("C", "B", 3, {"cost": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: (
                "B",
                "C",
                4,
                {
                    "cost": 1,
                    "capacity": 3,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                },
            ),
            5: ("C", "B", 5, {"cost": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"cost": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

    def test_place_flow_on_graph_graph4_balanced(self, graph4):
        """
        EQUAL_BALANCED flow on graph4 from A->C, placing 1 unit total.
        Verifies correct edges and final flow distribution.
        """
        _, pred = spf(graph4, "A")
        r = init_flow_graph(graph4)

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
        assert not any(
            edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
        )
        assert flow_placement_meta.nodes == {"C", "B", "A"}
        assert flow_placement_meta.edges == {0, 1}
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                    "cost": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                    "cost": 1,
                },
            ),
            2: ("A", "B1", 2, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
            3: ("B1", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
            4: ("A", "B2", 4, {"capacity": 3, "flow": 0, "flows": {}, "cost": 3}),
            5: ("B2", "C", 5, {"capacity": 3, "flow": 0, "flows": {}, "cost": 3}),
        }


#
# Tests for removing flow from the graph, fully or partially.
#


class TestRemoveFlowFromGraph:
    def test_remove_flow_from_graph_4(self, graph4):
        """
        Place a large flow from A->C on 'graph4' (only 1 feasible),
        then remove it entirely using remove_flow_from_graph(r).
        Verifies that all edges are cleared.
        """
        _, pred = spf(graph4, "A")
        r = init_flow_graph(graph4)

        flow_placement_meta = place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            10,
            flow_index=("A", "C", None),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        assert flow_placement_meta.placed_flow == 1
        assert flow_placement_meta.remaining_flow == 9

        # Remove all flows
        remove_flow_from_graph(r)

        for _, edata in r.get_edges().items():
            assert edata[3]["flow"] == 0
            assert edata[3]["flows"] == {}

        # Or check exact dictionary:
        assert r.get_edges() == {
            0: ("A", "B", 0, {"capacity": 1, "flow": 0, "flows": {}, "cost": 1}),
            1: ("B", "C", 1, {"capacity": 1, "flow": 0, "flows": {}, "cost": 1}),
            2: ("A", "B1", 2, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
            3: ("B1", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "cost": 2}),
            4: ("A", "B2", 4, {"capacity": 3, "flow": 0, "flows": {}, "cost": 3}),
            5: ("B2", "C", 5, {"capacity": 3, "flow": 0, "flows": {}, "cost": 3}),
        }

    def test_remove_specific_flow(self, graph4):
        """
        Demonstrates removing only a specific flow_index (e.g., flowA).
        Another flow (flowB) remains intact.
        """
        _, pred = spf(graph4, "A")
        r = init_flow_graph(graph4)

        # Place two flows
        place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=1,
            flow_index=("A", "C", "flowA"),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=2,
            flow_index=("A", "C", "flowB"),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        # Remove only flowA
        remove_flow_from_graph(r, flow_index=("A", "C", "flowA"))

        # flowA should be gone, flowB remains
        for _, (_, _, _, edge_attr) in r.get_edges().items():
            assert ("A", "C", "flowA") not in edge_attr["flows"]
            # If flowB is present, it has > 0
            if ("A", "C", "flowB") in edge_attr["flows"]:
                assert edge_attr["flows"][("A", "C", "flowB")] > 0

        # Now remove all flows
        remove_flow_from_graph(r)
        for _, (_, _, _, edge_attr) in r.get_edges().items():
            assert edge_attr["flow"] == 0
            assert edge_attr["flows"] == {}

    def test_remove_flow_zero_flow_placed(self, line1):
        """
        If no flow was placed (e.g., 0 flow or unreachable), removing flow should be safe
        and simply leave edges as-is.
        """
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

        # Place zero flow:
        place_flow_on_graph(
            r,
            "A",
            "C",
            pred,
            flow=0,
            flow_index=("A", "C", "empty"),
            flow_placement=FlowPlacement.PROPORTIONAL,
        )
        # Remove flows (none effectively exist)
        remove_flow_from_graph(r, flow_index=("A", "C", "empty"))

        # Ensure edges remain at zero flow
        for _, edata in r.get_edges().items():
            assert edata[3]["flow"] == 0
            assert edata[3]["flows"] == {}
