from pprint import pprint

import networkx as nx

from ngraph.graphnx import MultiDiGraphNX


def test_graphnx_init_1():
    MultiDiGraphNX()


def test_graphnx_all_shortest_paths_1():
    graph = MultiDiGraphNX()
    graph.add_edge("A", "B", weight=10)
    graph.add_edge("A", "BB", weight=10)
    graph.add_edge("B", "C", weight=10)
    graph.add_edge("BB", "C", weight=5)
    pprint(nx.all_shortest_paths(graph, "A", "C"))
