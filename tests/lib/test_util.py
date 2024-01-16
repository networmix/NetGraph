import pytest

import networkx as nx

from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.util import to_digraph, from_digraph, to_graph, from_graph


def test_to_digraph_1():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1)
    graph.add_edge(1, 2, 2)
    graph.add_edge(1, 2, 3)
    graph.add_edge(2, 1, 4)
    graph.add_edge(2, 1, 5)
    graph.add_edge(2, 1, 6)
    graph.add_edge(1, 1, 7)
    graph.add_edge(1, 1, 8)
    graph.add_edge(1, 1, 9)
    graph.add_edge(2, 2, 10)
    graph.add_edge(2, 2, 11)
    graph.add_edge(2, 2, 12)
    nx_graph = to_digraph(graph)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {"_uv_edges": [(1, 2, {1: {}, 2: {}, 3: {}})]},
        (2, 1): {"_uv_edges": [(2, 1, {4: {}, 5: {}, 6: {}})]},
        (1, 1): {"_uv_edges": [(1, 1, {7: {}, 8: {}, 9: {}})]},
        (2, 2): {"_uv_edges": [(2, 2, {10: {}, 11: {}, 12: {}})]},
    }


def test_to_digraph_2():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1, metric=1, capacity=1)
    graph.add_edge(1, 2, 2, metric=2, capacity=2)
    graph.add_edge(1, 2, 3, metric=3, capacity=3)
    graph.add_edge(2, 1, 4, metric=4, capacity=4)
    graph.add_edge(2, 1, 5, metric=5, capacity=5)
    graph.add_edge(2, 1, 6, metric=6, capacity=6)
    graph.add_edge(1, 1, 7, metric=7, capacity=7)
    graph.add_edge(1, 1, 8, metric=8, capacity=8)
    graph.add_edge(1, 1, 9, metric=9, capacity=9)
    graph.add_edge(2, 2, 10, metric=10, capacity=10)
    graph.add_edge(2, 2, 11, metric=11, capacity=11)
    graph.add_edge(2, 2, 12, metric=12, capacity=12)
    nx_graph = to_digraph(
        graph,
        edge_func=lambda graph, u, v, edges: {
            "metric": min(edge["metric"] for edge in edges.values()),
            "capacity": sum(edge["capacity"] for edge in edges.values()),
        },
    )
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {
            "metric": 1,
            "capacity": 6,
            "_uv_edges": [
                (
                    1,
                    2,
                    {
                        1: {"metric": 1, "capacity": 1},
                        2: {"metric": 2, "capacity": 2},
                        3: {"metric": 3, "capacity": 3},
                    },
                ),
            ],
        },
        (2, 1): {
            "metric": 4,
            "capacity": 15,
            "_uv_edges": [
                (
                    2,
                    1,
                    {
                        4: {"metric": 4, "capacity": 4},
                        5: {"metric": 5, "capacity": 5},
                        6: {"metric": 6, "capacity": 6},
                    },
                ),
            ],
        },
        (1, 1): {
            "metric": 7,
            "capacity": 24,
            "_uv_edges": [
                (
                    1,
                    1,
                    {
                        7: {"metric": 7, "capacity": 7},
                        8: {"metric": 8, "capacity": 8},
                        9: {"metric": 9, "capacity": 9},
                    },
                ),
            ],
        },
        (2, 2): {
            "metric": 10,
            "capacity": 33,
            "_uv_edges": [
                (
                    2,
                    2,
                    {
                        10: {"metric": 10, "capacity": 10},
                        11: {"metric": 11, "capacity": 11},
                        12: {"metric": 12, "capacity": 12},
                    },
                ),
            ],
        },
    }


def test_to_digraph_non_revertible():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1)
    graph.add_edge(1, 2, 2)
    graph.add_edge(1, 2, 3)
    graph.add_edge(2, 1, 4)
    graph.add_edge(2, 1, 5)
    graph.add_edge(2, 1, 6)
    graph.add_edge(1, 1, 7)
    graph.add_edge(1, 1, 8)
    graph.add_edge(1, 1, 9)
    graph.add_edge(2, 2, 10)
    graph.add_edge(2, 2, 11)
    graph.add_edge(2, 2, 12)
    nx_graph = to_digraph(graph, revertible=False)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {},
        (2, 1): {},
        (1, 1): {},
        (2, 2): {},
    }


def test_from_digraph():
    nx_graph = nx.DiGraph()
    nx_graph.add_node(1)
    nx_graph.add_node(2)
    nx_graph.add_edge(1, 2, _uv_edges=[(1, 2, {1: {}, 2: {}, 3: {}})])
    nx_graph.add_edge(2, 1, _uv_edges=[(2, 1, {4: {}, 5: {}, 6: {}})])
    nx_graph.add_edge(1, 1, _uv_edges=[(1, 1, {7: {}, 8: {}, 9: {}})])
    nx_graph.add_edge(2, 2, _uv_edges=[(2, 2, {10: {}, 11: {}, 12: {}})])
    graph = from_digraph(nx_graph)
    assert dict(graph.nodes) == {1: {}, 2: {}}
    assert dict(graph.edges) == {
        (1, 1, 7): {},
        (1, 1, 8): {},
        (1, 1, 9): {},
        (1, 2, 1): {},
        (1, 2, 2): {},
        (1, 2, 3): {},
        (2, 1, 4): {},
        (2, 1, 5): {},
        (2, 1, 6): {},
        (2, 2, 10): {},
        (2, 2, 11): {},
        (2, 2, 12): {},
    }


def test_to_graph_1():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1)
    graph.add_edge(1, 2, 2)
    graph.add_edge(1, 2, 3)
    graph.add_edge(2, 1, 4)
    graph.add_edge(2, 1, 5)
    graph.add_edge(2, 1, 6)
    graph.add_edge(1, 1, 7)
    graph.add_edge(1, 1, 8)
    graph.add_edge(1, 1, 9)
    graph.add_edge(2, 2, 10)
    graph.add_edge(2, 2, 11)
    graph.add_edge(2, 2, 12)
    nx_graph = to_graph(graph)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {
            "_uv_edges": [(1, 2, {1: {}, 2: {}, 3: {}}), (2, 1, {4: {}, 5: {}, 6: {}})]
        },
        (1, 1): {"_uv_edges": [(1, 1, {7: {}, 8: {}, 9: {}})]},
        (2, 2): {"_uv_edges": [(2, 2, {10: {}, 11: {}, 12: {}})]},
    }


def test_to_graph_2():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1, metric=1, capacity=1)
    graph.add_edge(1, 2, 2, metric=2, capacity=2)
    graph.add_edge(1, 2, 3, metric=3, capacity=3)
    graph.add_edge(2, 1, 4, metric=4, capacity=4)
    graph.add_edge(2, 1, 5, metric=5, capacity=5)
    graph.add_edge(2, 1, 6, metric=6, capacity=6)
    graph.add_edge(1, 1, 7, metric=7, capacity=7)
    graph.add_edge(1, 1, 8, metric=8, capacity=8)
    graph.add_edge(1, 1, 9, metric=9, capacity=9)
    graph.add_edge(2, 2, 10, metric=10, capacity=10)
    graph.add_edge(2, 2, 11, metric=11, capacity=11)
    graph.add_edge(2, 2, 12, metric=12, capacity=12)
    nx_graph = to_graph(
        graph,
        edge_func=lambda graph, u, v, edges: {
            "metric": min(edge["metric"] for edge in edges.values()),
            "capacity": sum(edge["capacity"] for edge in edges.values()),
        },
    )
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {
            "metric": 4,
            "capacity": 15,
            "_uv_edges": [
                (
                    1,
                    2,
                    {
                        1: {"metric": 1, "capacity": 1},
                        2: {"metric": 2, "capacity": 2},
                        3: {"metric": 3, "capacity": 3},
                    },
                ),
                (
                    2,
                    1,
                    {
                        4: {"metric": 4, "capacity": 4},
                        5: {"metric": 5, "capacity": 5},
                        6: {"metric": 6, "capacity": 6},
                    },
                ),
            ],
        },
        (1, 1): {
            "metric": 7,
            "capacity": 24,
            "_uv_edges": [
                (
                    1,
                    1,
                    {
                        7: {"metric": 7, "capacity": 7},
                        8: {"metric": 8, "capacity": 8},
                        9: {"metric": 9, "capacity": 9},
                    },
                ),
            ],
        },
        (2, 2): {
            "metric": 10,
            "capacity": 33,
            "_uv_edges": [
                (
                    2,
                    2,
                    {
                        10: {"metric": 10, "capacity": 10},
                        11: {"metric": 11, "capacity": 11},
                        12: {"metric": 12, "capacity": 12},
                    },
                ),
            ],
        },
    }


def test_to_graph_non_revertible():
    graph = MultiDiGraph()
    graph.add_node(1)
    graph.add_node(2)
    graph.add_edge(1, 2, 1)
    graph.add_edge(1, 2, 2)
    graph.add_edge(1, 2, 3)
    graph.add_edge(2, 1, 4)
    graph.add_edge(2, 1, 5)
    graph.add_edge(2, 1, 6)
    graph.add_edge(1, 1, 7)
    graph.add_edge(1, 1, 8)
    graph.add_edge(1, 1, 9)
    graph.add_edge(2, 2, 10)
    graph.add_edge(2, 2, 11)
    graph.add_edge(2, 2, 12)
    nx_graph = to_graph(graph, revertible=False)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    assert dict(nx_graph.edges) == {
        (1, 2): {},
        (1, 1): {},
        (2, 2): {},
    }


def test_from_graph():
    nx_graph = nx.Graph()
    nx_graph.add_node(1)
    nx_graph.add_node(2)
    nx_graph.add_edge(
        1, 2, _uv_edges=[(1, 2, {1: {}, 2: {}, 3: {}}), (2, 1, {4: {}, 5: {}, 6: {}})]
    )
    nx_graph.add_edge(1, 1, _uv_edges=[(1, 1, {7: {}, 8: {}, 9: {}})])
    nx_graph.add_edge(2, 2, _uv_edges=[(2, 2, {10: {}, 11: {}, 12: {}})])
    graph = from_graph(nx_graph)
    assert dict(graph.nodes) == {1: {}, 2: {}}
    assert dict(graph.edges) == {
        (1, 2, 1): {},
        (1, 2, 2): {},
        (1, 2, 3): {},
        (2, 1, 4): {},
        (2, 1, 5): {},
        (2, 1, 6): {},
        (1, 1, 7): {},
        (1, 1, 8): {},
        (1, 1, 9): {},
        (2, 2, 10): {},
        (2, 2, 11): {},
        (2, 2, 12): {},
    }
