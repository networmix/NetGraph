# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf
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
