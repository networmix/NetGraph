# pylint: disable=protected-access,invalid-name
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.flow import edmonds_karp


def test_edmonds_karp_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=1)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=1)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=1)

    r = edmonds_karp(g, "A", "D")
    assert r.get_attr()["flow_value"] == 3


def test_edmonds_karp_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=3)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=1)

    r = edmonds_karp(g, "A", "D")
    assert r.get_attr()["flow_value"] == 3


def test_edmonds_karp_3():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=3)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=5)

    r = edmonds_karp(g, "A", "D")
    assert r.get_attr()["flow_value"] == 6


def test_edmonds_karp_4():
    g = MultiDiGraph()

    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=3)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=5)

    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("B", "A", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=1)
    g.add_edge("B", "A", metric=10, capacity=1)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("C", "A", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("C", "A", metric=10, capacity=1)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("D", "A", metric=20, capacity=1)

    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("D", "B", metric=10, capacity=1)

    g.add_edge("C", "D", metric=10, capacity=1)
    g.add_edge("D", "C", metric=10, capacity=1)

    r = edmonds_karp(g, "A", "D")
    assert r.get_attr()["flow_value"] == 10
