# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.lib.common import init_flow_graph
from ngraph.lib.place_flow import (
    FlowPlacement,
    place_flow_on_graph,
    remove_flow_from_graph,
)

from ngraph.lib.spf import spf
from ..sample_data.sample_graphs import *


class TestPlaceFlowOnGraph:
    def test_place_flow_on_graph_line1_proportional(self, line1):
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

    def test_place_flow_on_graph_line1_equal(self, line1):
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
                    "capacity": 5,
                    "flow": 2.0,
                    "flows": {("A", "C", "TEST"): 2.0},
                    "metric": 1,
                },
            ),
            1: ("B", "A", 1, {"capacity": 5, "flow": 0, "flows": {}, "metric": 1}),
            2: (
                "B",
                "C",
                2,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                    "metric": 1,
                },
            ),
            3: ("C", "B", 3, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 3,
                    "flow": 1.0,
                    "flows": {("A", "C", "TEST"): 1.0},
                    "metric": 1,
                },
            ),
            5: ("C", "B", 5, {"capacity": 3, "flow": 0, "flows": {}, "metric": 1}),
            6: ("B", "C", 6, {"capacity": 7, "flow": 0, "flows": {}, "metric": 2}),
            7: ("C", "B", 7, {"capacity": 7, "flow": 0, "flows": {}, "metric": 2}),
        }
        assert flow_placement_meta.nodes == {"A", "C", "B"}
        assert flow_placement_meta.edges == {0, 2, 4}

    def test_place_flow_on_graph_line1_proportional(self, line1):
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

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

    def test_place_flow_on_graph_graph3_proportional_1(self, graph3):
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
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", None): 1.0},
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
                },
            ),
            6: ("C", "D", 6, {"capacity": 3, "flow": 0, "flows": {}, "metric": 2}),
            7: (
                "A",
                "E",
                7,
                {
                    "capacity": 5,
                    "flow": 4.0,
                    "flows": {("A", "C", None): 4.0},
                    "metric": 1,
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
                    "metric": 1,
                },
            ),
            9: ("A", "D", 9, {"capacity": 2, "flow": 0, "flows": {}, "metric": 4}),
            10: ("C", "F", 10, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            11: ("F", "D", 11, {"capacity": 2, "flow": 0, "flows": {}, "metric": 1}),
        }
        assert flow_placement_meta.nodes == {"A", "E", "B", "C"}
        assert flow_placement_meta.edges == {0, 1, 2, 3, 4, 5, 7, 8}

    def test_place_flow_on_graph_graph3_proportional_2(self, graph3):
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
                    "capacity": 2,
                    "flow": 0.6666666666666666,
                    "flows": {("A", "D", None): 0.6666666666666666},
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 1,
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
                    "metric": 2,
                },
            ),
            7: ("A", "E", 7, {"capacity": 5, "flow": 0, "flows": {}, "metric": 1}),
            8: ("E", "C", 8, {"capacity": 4, "flow": 0, "flows": {}, "metric": 1}),
            9: (
                "A",
                "D",
                9,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "D", None): 2.0},
                    "metric": 4,
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
                    "metric": 1,
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
                    "metric": 1,
                },
            ),
        }

    def test_place_flow_on_graph_line1_balanced_1(self, line1):
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

    def test_place_flow_on_graph_line1_balanced_2(self, line1):
        _, pred = spf(line1, "A")
        r = init_flow_graph(line1)

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

    def test_place_flow_on_graph_graph4_balanced(self, graph4):
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
        assert (
            any(
                edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
            )
            == False
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
                    "metric": 1,
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
                    "metric": 1,
                },
            ),
            2: ("A", "B1", 2, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
            3: ("B1", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
            4: ("A", "B2", 4, {"capacity": 3, "flow": 0, "flows": {}, "metric": 3}),
            5: ("B2", "C", 5, {"capacity": 3, "flow": 0, "flows": {}, "metric": 3}),
        }


class TestRemoveFlowFromGraph:
    def test_remove_flow_from_graph_4(self, graph4):
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

        remove_flow_from_graph(r)

        assert r.get_edges() == {
            0: ("A", "B", 0, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            1: ("B", "C", 1, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            2: ("A", "B1", 2, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
            3: ("B1", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
            4: ("A", "B2", 4, {"capacity": 3, "flow": 0, "flows": {}, "metric": 3}),
            5: ("B2", "C", 5, {"capacity": 3, "flow": 0, "flows": {}, "metric": 3}),
        }
