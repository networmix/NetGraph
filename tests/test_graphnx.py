from pprint import pprint

import networkx as nx

from ngraph.graphnx import MultiDiGraphNX


def test_graphnx_init_1():
    MultiDiGraphNX()


def test_graphnx_all_shortest_paths_1():
    graph = MultiDiGraphNX()
    graph.add_edge("A", "B", weight=10)
    graph.add_edge("A", "BB", weight=10)
    graph.add_edge("B", "C", weight=4)
    graph.add_edge("BB", "C", weight=12)
    graph.add_edge("BB", "C", weight=5)
    graph.add_edge("BB", "C", weight=4)

    assert list(
        nx.all_shortest_paths(
            graph,
            "A",
            "C",
            weight=lambda u, v, attrs: min(attr["weight"] for attr in attrs.values()),
        )
    ) == [["A", "B", "C"], ["A", "BB", "C"]]
