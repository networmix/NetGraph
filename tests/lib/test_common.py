# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.spf import spf
from ngraph.lib.common import (
    EdgeSelect,
    edge_select_fabric,
    init_flow_graph,
    resolve_to_paths,
)
from ..sample_data.sample_graphs import *


class TestInitFlowGraph:
    def test_init_flow_graph_1(self, line1):
        r = init_flow_graph(line1)
        assert r.get_edges() == {
            0: ("A", "B", 0, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            1: ("B", "A", 1, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: ("B", "C", 2, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            3: ("C", "B", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: ("B", "C", 4, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

        r["A"]["B"][0]["flow"] = 5
        r["A"]["B"][0]["flows"] = {("A", "B", 0): 5}
        init_flow_graph(r, reset_flow_graph=False)

        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 1,
                    "capacity": 5,
                    "flow": 5,
                    "flows": {("A", "B", 0): 5},
                },
            ),
            1: ("B", "A", 1, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: ("B", "C", 2, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            3: ("C", "B", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: ("B", "C", 4, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }

        init_flow_graph(r)
        assert r.get_edges() == {
            0: ("A", "B", 0, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            1: ("B", "A", 1, {"metric": 1, "capacity": 5, "flow": 0, "flows": {}}),
            2: ("B", "C", 2, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            3: ("C", "B", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: ("B", "C", 4, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            5: ("C", "B", 5, {"metric": 1, "capacity": 3, "flow": 0, "flows": {}}),
            6: ("B", "C", 6, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
            7: ("C", "B", 7, {"metric": 2, "capacity": 7, "flow": 0, "flows": {}}),
        }


class TestEdgeSelect:
    def test_edge_select_fabric_1(self, square3):
        edges = square3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)

        assert func(graph3, "A", "B", edges) == (1, [0])

    def test_edge_select_fabric_2(self, graph3):
        edges = graph3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)

        assert func(graph3, "A", "B", edges) == (1, [0, 1, 2])

    def test_edge_select_fabric_3(self, graph3):
        edges = graph3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.SINGLE_MIN_COST)

        assert func(graph3, "A", "B", edges) == (1, [0])

    def test_edge_select_fabric_4(self, graph3):
        edges = graph3["A"]["B"]
        user_def_func = lambda graph, src_node, dst_node, edges: (1, list(edges.keys()))
        func = edge_select_fabric(
            EdgeSelect.USER_DEFINED, edge_select_func=user_def_func
        )
        assert func(graph3, "A", "B", edges) == (1, [0, 1, 2])

    def test_edge_select_fabric_5(self, line1):
        line1 = init_flow_graph(line1)
        edges = line1["B"]["C"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING)

        assert func(square3, "B", "C", edges) == (1, [2, 4])

    def test_edge_select_fabric_6(self, graph3):
        graph3 = init_flow_graph(graph3)
        edges = graph3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING)

        assert func(graph3, "A", "B", edges) == (1, [0, 1, 2])


class TestResolvePaths:
    def test_resolve_paths_from_predecessors_1(self, line1):
        _, pred = spf(line1, "A")

        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (2, 4)), ("C", ()))
        ]

    def test_resolve_paths_from_predecessors_2(self, line1):
        _, pred = spf(line1, "A")
        assert list(resolve_to_paths("A", "D", pred)) == []

    def test_resolve_paths_from_predecessors_3(self, square1):
        _, pred = spf(square1, "A")

        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (1,)), ("C", ()))
        ]

    def test_resolve_paths_from_predecessors_4(self, square2):
        _, pred = spf(square2, "A")

        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (1,)), ("C", ())),
            (("A", (2,)), ("D", (3,)), ("C", ())),
        ]

    def test_resolve_paths_from_predecessors_5(self, graph3):
        _, pred = spf(graph3, "A")

        assert list(resolve_to_paths("A", "D", pred)) == [
            (("A", (9,)), ("D", ())),
            (("A", (0, 1, 2)), ("B", (3, 4, 5)), ("C", (6,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (6,)), ("D", ())),
            (("A", (0, 1, 2)), ("B", (3, 4, 5)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (10,)), ("F", (11,)), ("D", ())),
        ]

    def test_resolve_paths_from_predecessors_6(self, graph3):
        _, pred = spf(graph3, "A")

        assert list(resolve_to_paths("A", "D", pred, split_parallel_edges=True)) == [
            (("A", (9,)), ("D", ())),
            (("A", (0,)), ("B", (3,)), ("C", (6,)), ("D", ())),
            (("A", (0,)), ("B", (4,)), ("C", (6,)), ("D", ())),
            (("A", (0,)), ("B", (5,)), ("C", (6,)), ("D", ())),
            (("A", (1,)), ("B", (3,)), ("C", (6,)), ("D", ())),
            (("A", (1,)), ("B", (4,)), ("C", (6,)), ("D", ())),
            (("A", (1,)), ("B", (5,)), ("C", (6,)), ("D", ())),
            (("A", (2,)), ("B", (3,)), ("C", (6,)), ("D", ())),
            (("A", (2,)), ("B", (4,)), ("C", (6,)), ("D", ())),
            (("A", (2,)), ("B", (5,)), ("C", (6,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (6,)), ("D", ())),
            (("A", (0,)), ("B", (3,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (0,)), ("B", (4,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (0,)), ("B", (5,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (1,)), ("B", (3,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (1,)), ("B", (4,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (1,)), ("B", (5,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (2,)), ("B", (3,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (2,)), ("B", (4,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (2,)), ("B", (5,)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (10,)), ("F", (11,)), ("D", ())),
        ]
