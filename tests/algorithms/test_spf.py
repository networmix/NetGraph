# pylint: disable=protected-access,invalid-name
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf
from ngraph.algorithms.common import resolve_to_paths


def test_spf_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=10)
    g.add_edge("B", "C", metric=10)
    g.add_edge("C", "D", metric=10)

    costs, pred = spf(g, "A")
    assert costs == {"A": 0, "B": 10, "C": 20, "D": 30}
    assert pred == {"A": {}, "B": {"A": [0]}, "C": {"B": [1]}, "D": {"C": [2]}}


def test_spf_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=10)
    g.add_edge("A", "C", metric=10)
    g.add_edge("A", "D", metric=10)
    g.add_edge("B", "D", metric=10)
    g.add_edge("C", "D", metric=10)

    costs, pred = spf(g, "A")

    assert costs == {"A": 0, "B": 10, "C": 10, "D": 10}
    assert pred == {"A": {}, "B": {"A": [0]}, "C": {"A": [1]}, "D": {"A": [2]}}


def test_spf_3():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11)
    g.add_edge("B", "A", metric=11)
    g.add_edge("A", "B", metric=10)
    g.add_edge("B", "A", metric=10)

    g.add_edge("A", "C", metric=10)
    g.add_edge("C", "A", metric=10)
    g.add_edge("A", "C", metric=11)
    g.add_edge("C", "A", metric=11)

    g.add_edge("A", "D", metric=10)
    g.add_edge("D", "A", metric=10)

    g.add_edge("B", "D", metric=10)
    g.add_edge("D", "B", metric=10)

    g.add_edge("C", "D", metric=10)
    g.add_edge("D", "C", metric=10)

    costs, pred = spf(g, "A")

    assert costs == {"A": 0, "B": 10, "C": 10, "D": 10}
    assert pred == {"A": {}, "B": {"A": [2]}, "C": {"A": [4]}, "D": {"A": [8]}}


def test_spf_4():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11)
    g.add_edge("B", "A", metric=11)
    g.add_edge("A", "B", metric=10)
    g.add_edge("B", "A", metric=10)

    g.add_edge("A", "C", metric=10)
    g.add_edge("C", "A", metric=10)
    g.add_edge("A", "C", metric=10)
    g.add_edge("C", "A", metric=10)

    g.add_edge("A", "D", metric=20)
    g.add_edge("D", "A", metric=20)

    g.add_edge("B", "D", metric=10)
    g.add_edge("D", "B", metric=10)

    g.add_edge("C", "D", metric=10)
    g.add_edge("D", "C", metric=10)

    costs, pred = spf(g, "A")

    assert costs == {"A": 0, "B": 10, "C": 10, "D": 20}
    assert pred == {
        "A": {},
        "B": {"A": [2]},
        "C": {"A": [4, 6]},
        "D": {"A": [8], "B": [10], "C": [12]},
    }


def test_resolve_paths_from_predecessors_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11)
    g.add_edge("B", "A", metric=11)
    g.add_edge("A", "B", metric=10)
    g.add_edge("B", "A", metric=10)

    g.add_edge("A", "C", metric=10)
    g.add_edge("C", "A", metric=10)
    g.add_edge("A", "C", metric=10)
    g.add_edge("C", "A", metric=10)

    g.add_edge("A", "D", metric=20)
    g.add_edge("D", "A", metric=20)

    g.add_edge("B", "D", metric=10)
    g.add_edge("D", "B", metric=10)

    g.add_edge("C", "D", metric=10)
    g.add_edge("D", "C", metric=10)

    costs, pred = spf(g, "A")

    assert list(resolve_to_paths("A", "D", pred)) == [
        (("A", (8,)), ("D", tuple())),
        (("A", (2,)), ("B", (10,)), ("D", tuple())),
        (("A", (4, 6)), ("C", (12,)), ("D", tuple())),
    ]
    assert list(resolve_to_paths("A", "E", pred)) == []
