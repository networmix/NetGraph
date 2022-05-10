# pylint: disable=protected-access,invalid-name
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.flow import edmonds_karp, init_residual_graph, place_flow


def test_init_residual_graph_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)

    g.add_edge("B", "C1", metric=1, capacity=1)
    g.add_edge("B", "C2", metric=2, capacity=1)

    g.add_edge("C1", "D", metric=1, capacity=1)
    g.add_edge("C2", "D", metric=1, capacity=1)

    r = init_residual_graph(g.copy())
    assert r.get_edges() == {
        0: ("A", "B", 0, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
        1: ("B", "C1", 1, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
        2: ("B", "C2", 2, {"metric": 2, "capacity": 1, "flow": 0, "flows": {}}),
        3: ("C1", "D", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
        4: ("C2", "D", 4, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
    }


def test_place_flow_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)

    g.add_edge("B", "C1", metric=1, capacity=1)
    g.add_edge("B", "C2", metric=2, capacity=1)

    g.add_edge("C1", "D", metric=1, capacity=1)
    g.add_edge("C2", "D", metric=1, capacity=1)

    r = init_residual_graph(g.copy())
    assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
        1,
        float("inf"),
    )


def test_place_flow_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)

    g.add_edge("B", "C1", metric=1, capacity=1)
    g.add_edge("B", "C2", metric=2, capacity=1)

    g.add_edge("C1", "D", metric=1, capacity=1)
    g.add_edge("C2", "D", metric=1, capacity=1)

    r = init_residual_graph(g.copy())
    assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
        1,
        float("inf"),
    )
    assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
        0,
        float("inf"),
    )


def test_edmonds_karp_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=2)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("B", "C", metric=10, capacity=1)
    g.add_edge("B", "C", metric=10, capacity=1)

    g.add_edge("C", "D", metric=20, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=1)

    max_flow, _ = edmonds_karp(g, "A", "D")
    assert max_flow == 2


def test_edmonds_karp_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=3)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=1)

    max_flow, _ = edmonds_karp(g, "A", "D")
    assert max_flow == 3


def test_edmonds_karp_3():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=11, capacity=1)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("A", "C", metric=10, capacity=1)
    g.add_edge("A", "C", metric=10, capacity=3)

    g.add_edge("A", "D", metric=20, capacity=1)
    g.add_edge("B", "D", metric=10, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=5)

    max_flow, _ = edmonds_karp(g, "A", "D")
    assert max_flow == 6


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

    max_flow, _ = edmonds_karp(g, "A", "D")
    assert max_flow == 10


def test_edmonds_karp_5():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)

    g.add_edge("B", "C1", metric=1, capacity=1)
    g.add_edge("B", "C2", metric=2, capacity=1)

    g.add_edge("C1", "D", metric=1, capacity=1)
    g.add_edge("C2", "D", metric=1, capacity=1)

    max_flow, _ = edmonds_karp(g, "A", "D")
    assert max_flow == 1


def test_edmonds_karp_spf_1():
    g = MultiDiGraph()

    g.add_edge("A", "B", metric=11, capacity=2)
    g.add_edge("A", "B", metric=10, capacity=2)

    g.add_edge("B", "C", metric=10, capacity=0)
    g.add_edge("B", "C", metric=11, capacity=1)

    g.add_edge("C", "D", metric=20, capacity=1)
    g.add_edge("C", "D", metric=10, capacity=1)

    max_flow, _ = edmonds_karp(g, "A", "D", shortest_path=True)
    assert max_flow == 1


def test_edmonds_karp_spf_2():
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

    max_flow, _ = edmonds_karp(g, "A", "D", shortest_path=True)
    assert max_flow == 10
