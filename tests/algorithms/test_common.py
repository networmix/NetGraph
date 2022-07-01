# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf
from ngraph.algorithms.common import (
    EdgeSelect,
    edge_select_fabric,
    init_flow_graph,
    resolve_to_paths,
)


@pytest.fixture
def line_1() -> MultiDiGraph:
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
def square_1() -> MultiDiGraph:
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
    return g


@pytest.fixture
def square_2() -> MultiDiGraph:
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=2)
    g.add_edge("D", "C", metric=1, capacity=2)
    return g


@pytest.fixture
def square_3() -> MultiDiGraph:
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "B", metric=2, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=2)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=1, capacity=2)
    return g


@pytest.fixture
def graph_1() -> MultiDiGraph:
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


class TestInitFlowGraph:
    def test_init_flow_graph_1(self, line_1):

        r = init_flow_graph(line_1)
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
    def test_edge_select_fabric_1(self, square_3):
        edges = square_3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)

        assert func(graph_1, "A", "B", edges) == (1, [0])

    def test_edge_select_fabric_2(self, graph_1):
        edges = graph_1["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST)

        assert func(graph_1, "A", "B", edges) == (1, [0, 1, 2])

    def test_edge_select_fabric_3(self, graph_1):
        edges = graph_1["A"]["B"]
        func = edge_select_fabric(EdgeSelect.SINGLE_MIN_COST)

        assert func(graph_1, "A", "B", edges) == (1, [0])

    def test_edge_select_fabric_4(self, graph_1):
        edges = graph_1["A"]["B"]
        user_def_func = lambda graph, src_node, dst_node, edges: (1, list(edges.keys()))
        func = edge_select_fabric(
            EdgeSelect.USER_DEFINED, edge_select_func=user_def_func
        )
        assert func(graph_1, "A", "B", edges) == (1, [0, 1, 2])

    def test_edge_select_fabric_5(self, line_1):
        line_1 = init_flow_graph(line_1)
        edges = line_1["B"]["C"]
        func = edge_select_fabric(EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING)

        assert func(square_3, "B", "C", edges) == (1, [2, 4])

    def test_edge_select_fabric_6(self, square_3):
        square_3 = init_flow_graph(square_3)
        edges = square_3["A"]["B"]
        func = edge_select_fabric(EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING)

        assert func(square_3, "A", "B", edges) == (1, [0, 1])


class TestResolvePaths:
    def test_resolve_paths_from_predecessors_1(self, line_1):
        _, pred = spf(line_1, "A")

        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (2, 4)), ("C", ()))
        ]

    def test_resolve_paths_from_predecessors_2(self, line_1):
        _, pred = spf(line_1, "A")
        assert list(resolve_to_paths("A", "D", pred)) == []

    def test_resolve_paths_from_predecessors_3(self, square_1):
        _, pred = spf(square_1, "A")

        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (1,)), ("C", ()))
        ]

    def test_resolve_paths_from_predecessors_4(self, square_2):
        _, pred = spf(square_2, "A")

        print(list(resolve_to_paths("A", "C", pred)))
        assert list(resolve_to_paths("A", "C", pred)) == [
            (("A", (0,)), ("B", (1,)), ("C", ())),
            (("A", (2,)), ("D", (3,)), ("C", ())),
        ]

    def test_resolve_paths_from_predecessors_5(self, graph_1):
        _, pred = spf(graph_1, "A")

        assert list(resolve_to_paths("A", "D", pred)) == [
            (("A", (9,)), ("D", ())),
            (("A", (0, 1, 2)), ("B", (3, 4, 5)), ("C", (6,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (6,)), ("D", ())),
            (("A", (0, 1, 2)), ("B", (3, 4, 5)), ("C", (10,)), ("F", (11,)), ("D", ())),
            (("A", (7,)), ("E", (8,)), ("C", (10,)), ("F", (11,)), ("D", ())),
        ]

    def test_resolve_paths_from_predecessors_6(self, graph_1):
        _, pred = spf(graph_1, "A")

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
