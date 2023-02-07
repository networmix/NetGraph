# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf, ksp
from ngraph.algorithms.common import EdgeSelect, edge_select_fabric


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
def square_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
    return g


@pytest.fixture
def square_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=2)
    g.add_edge("D", "C", metric=1, capacity=2)
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
    """Fully connected graph with 5 nodes"""
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=1)
    g.add_edge("A", "E", metric=1, capacity=1)
    g.add_edge("B", "A", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("B", "E", metric=1, capacity=1)
    g.add_edge("C", "A", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("C", "E", metric=1, capacity=1)
    g.add_edge("D", "A", metric=1, capacity=1)
    g.add_edge("D", "B", metric=1, capacity=1)
    g.add_edge("D", "C", metric=1, capacity=1)
    g.add_edge("D", "E", metric=1, capacity=1)
    g.add_edge("E", "A", metric=1, capacity=1)
    g.add_edge("E", "B", metric=1, capacity=1)
    g.add_edge("E", "C", metric=1, capacity=1)
    g.add_edge("E", "D", metric=1, capacity=1)
    return g


@pytest.fixture
def graph_3():
    """Rombus graph with 4 nodes and a cross link"""
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    return g


class TestSPF:
    def test_spf_1(self, line_1):
        costs, pred = spf(line_1, "A")
        assert costs == {"A": 0, "B": 1, "C": 2}
        assert pred == {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}}

    def test_spf_2(self, square_1):
        costs, pred = spf(square_1, "A")
        assert costs == {"A": 0, "B": 1, "D": 2, "C": 2}
        assert pred == {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1]}}

    def test_spf_3(self, square_2):
        costs, pred = spf(square_2, "A")
        assert costs == {"A": 0, "B": 1, "D": 1, "C": 2}
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "D": {"A": [2]},
            "C": {"B": [1], "D": [3]},
        }

    def test_spf_4(self, graph_1):
        costs, pred = spf(graph_1, "A")
        assert costs == {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3}
        assert pred == {
            "A": {},
            "B": {"A": [0, 1, 2]},
            "E": {"A": [7]},
            "D": {"A": [9], "C": [6], "F": [11]},
            "C": {"B": [3, 4, 5], "E": [8]},
            "F": {"C": [10]},
        }

    def test_spf_5(self, graph_1):
        costs, pred = spf(
            graph_1,
            "A",
            edge_select_func=edge_select_fabric(EdgeSelect.SINGLE_MIN_COST),
            multipath=False,
        )
        assert costs == {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3}
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "E": {"A": [7]},
            "D": {"A": [9]},
            "C": {"B": [3]},
            "F": {"C": [10]},
        }


class TestKSP:
    def test_ksp_1(self, line_1):
        paths = list(ksp(line_1, "A", "C", multipath=True))

        assert paths == [
            ({"A": 0, "B": 1, "C": 2}, {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}}),
            ({"A": 0, "B": 1, "C": 3}, {"A": {}, "B": {"A": [0]}, "C": {"B": [6]}}),
        ]

    def test_ksp_2(self, square_1):
        paths = list(ksp(square_1, "A", "C", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "D": 2, "C": 2},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1]}},
            ),
            (
                {"A": 0, "B": 1, "D": 2, "C": 4},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"D": [3]}},
            ),
        ]

    def test_ksp_3(self, square_2):
        paths = list(ksp(square_2, "A", "C", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "D": 1, "C": 2},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1], "D": [3]}},
            )
        ]

    def test_ksp_4(self, graph_1):
        paths = list(ksp(graph_1, "A", "D", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3},
                {
                    "A": {},
                    "B": {"A": [0, 1, 2]},
                    "E": {"A": [7]},
                    "D": {"A": [9], "C": [6], "F": [11]},
                    "C": {"B": [3, 4, 5], "E": [8]},
                    "F": {"C": [10]},
                },
            )
        ]

    def test_ksp_5(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=True))

        visited = set()
        for path in paths:
            costs, pred = path
            edge_ids = tuple(
                sorted(
                    [
                        edge_id
                        for _, v1 in pred.items()
                        for _, edge_list in v1.items()
                        for edge_id in edge_list
                    ]
                )
            )
            if edge_ids not in visited:
                visited.add(edge_ids)
            else:
                raise Exception(f"Duplicate path found: {edge_ids}")
        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 1, "D": 2, "E": 2},
                {
                    "A": {},
                    "B": {"D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"C": [10]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 1, "E": 2},
                {
                    "A": {},
                    "B": {"C": [9], "E": [17]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13]},
                    "C": {"E": [18]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 1, "D": 2, "E": 3},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"A": [1]},
                    "D": {"C": [10]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 1, "D": 3, "E": 2},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"A": [1]},
                    "D": {"E": [19]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 2, "D": 1, "E": 3},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 3, "D": 1, "E": 2},
                {
                    "A": {},
                    "B": {"C": [9]},
                    "C": {"E": [18]},
                    "D": {"A": [2]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 2, "D": 3, "E": 1},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"E": [18]},
                    "D": {"C": [10]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 3, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9]},
                    "C": {"D": [14]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_6(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=True, max_k=2))

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_7(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=True, max_path_cost=2))

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_8(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=True, max_path_cost_factor=3))

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 1, "D": 2, "E": 2},
                {
                    "A": {},
                    "B": {"D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"C": [10]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 1, "E": 2},
                {
                    "A": {},
                    "B": {"C": [9], "E": [17]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13]},
                    "C": {"E": [18]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_9(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=True, max_path_cost=0.5))

        assert paths == []

    def test_ksp_10(self, graph_2):
        paths = list(ksp(graph_2, "A", "B", multipath=False, max_path_cost=2))

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 2, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 2, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"E": [18]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_11(self, graph_3):
        paths = list(ksp(graph_3, "A", "D", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 2},
                {"A": {}, "B": {"A": [0]}, "C": {"A": [1]}, "D": {"B": [2], "C": [3]}},
            ),
            (
                {"A": 0, "B": 1, "C": 2, "D": 3},
                {"A": {}, "B": {"A": [0]}, "C": {"B": [4]}, "D": {"C": [3]}},
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 3},
                {"A": {}, "B": {"C": [5]}, "C": {"A": [1]}, "D": {"B": [2]}},
            ),
        ]

    def test_ksp_12(self, graph_3):
        paths = list(ksp(graph_3, "A", "E", multipath=True))

        assert paths == []
