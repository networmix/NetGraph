import pytest
import networkx as nx

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.util import to_digraph, from_digraph, to_graph, from_graph


def create_sample_graph(with_attrs: bool = False) -> StrictMultiDiGraph:
    """Helper to create a sample StrictMultiDiGraph with multiple edges and optional attributes."""
    graph = StrictMultiDiGraph()
    # Add nodes.
    graph.add_node(1)
    graph.add_node(2)

    if with_attrs:
        # Add edges with attributes.
        graph.add_edge(1, 2, 1, cost=1, capacity=1)
        graph.add_edge(1, 2, 2, cost=2, capacity=2)
        graph.add_edge(1, 2, 3, cost=3, capacity=3)
        graph.add_edge(2, 1, 4, cost=4, capacity=4)
        graph.add_edge(2, 1, 5, cost=5, capacity=5)
        graph.add_edge(2, 1, 6, cost=6, capacity=6)
        graph.add_edge(1, 1, 7, cost=7, capacity=7)
        graph.add_edge(1, 1, 8, cost=8, capacity=8)
        graph.add_edge(1, 1, 9, cost=9, capacity=9)
        graph.add_edge(2, 2, 10, cost=10, capacity=10)
        graph.add_edge(2, 2, 11, cost=11, capacity=11)
        graph.add_edge(2, 2, 12, cost=12, capacity=12)
    else:
        # Add edges without attributes.
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
    return graph


# ---------------------------
# Tests for DiGraph conversion
# ---------------------------


def test_to_digraph_basic():
    """Test converting a basic StrictMultiDiGraph to a revertible NetworkX DiGraph."""
    graph = create_sample_graph(with_attrs=False)
    nx_graph = to_digraph(graph)
    # Check that nodes are correctly added.
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    # Expected consolidated edges with stored original multi-edge data.
    expected_edges = {
        (1, 2): {"_uv_edges": [(1, 2, {1: {}, 2: {}, 3: {}})]},
        (2, 1): {"_uv_edges": [(2, 1, {4: {}, 5: {}, 6: {}})]},
        (1, 1): {"_uv_edges": [(1, 1, {7: {}, 8: {}, 9: {}})]},
        (2, 2): {"_uv_edges": [(2, 2, {10: {}, 11: {}, 12: {}})]},
    }
    assert dict(nx_graph.edges) == expected_edges


def test_to_digraph_with_edge_func():
    """Test converting a StrictMultiDiGraph to a DiGraph with a custom edge function."""
    graph = create_sample_graph(with_attrs=True)
    # Consolidate edges using a custom function.
    nx_graph = to_digraph(
        graph,
        edge_func=lambda g, u, v, edges: {
            "cost": min(edge["cost"] for edge in edges.values()),
            "capacity": sum(edge["capacity"] for edge in edges.values()),
        },
    )
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    expected_edges = {
        (1, 2): {
            "cost": 1,
            "capacity": 6,
            "_uv_edges": [
                (
                    1,
                    2,
                    {
                        1: {"cost": 1, "capacity": 1},
                        2: {"cost": 2, "capacity": 2},
                        3: {"cost": 3, "capacity": 3},
                    },
                ),
            ],
        },
        (2, 1): {
            "cost": 4,
            "capacity": 15,
            "_uv_edges": [
                (
                    2,
                    1,
                    {
                        4: {"cost": 4, "capacity": 4},
                        5: {"cost": 5, "capacity": 5},
                        6: {"cost": 6, "capacity": 6},
                    },
                ),
            ],
        },
        (1, 1): {
            "cost": 7,
            "capacity": 24,
            "_uv_edges": [
                (
                    1,
                    1,
                    {
                        7: {"cost": 7, "capacity": 7},
                        8: {"cost": 8, "capacity": 8},
                        9: {"cost": 9, "capacity": 9},
                    },
                ),
            ],
        },
        (2, 2): {
            "cost": 10,
            "capacity": 33,
            "_uv_edges": [
                (
                    2,
                    2,
                    {
                        10: {"cost": 10, "capacity": 10},
                        11: {"cost": 11, "capacity": 11},
                        12: {"cost": 12, "capacity": 12},
                    },
                ),
            ],
        },
    }
    assert dict(nx_graph.edges) == expected_edges


def test_to_digraph_non_revertible():
    """Test converting a StrictMultiDiGraph to a DiGraph with revertible set to False."""
    graph = create_sample_graph(with_attrs=False)
    nx_graph = to_digraph(graph, revertible=False)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    # With revertible=False, no original edge data should be stored.
    expected_edges = {
        (1, 2): {},
        (2, 1): {},
        (1, 1): {},
        (2, 2): {},
    }
    assert dict(nx_graph.edges) == expected_edges


def test_from_digraph():
    """Test restoring a StrictMultiDiGraph from a revertible NetworkX DiGraph."""
    nx_graph = nx.DiGraph()
    nx_graph.add_node(1)
    nx_graph.add_node(2)
    nx_graph.add_edge(1, 2, _uv_edges=[(1, 2, {1: {}, 2: {}, 3: {}})])
    nx_graph.add_edge(2, 1, _uv_edges=[(2, 1, {4: {}, 5: {}, 6: {}})])
    nx_graph.add_edge(1, 1, _uv_edges=[(1, 1, {7: {}, 8: {}, 9: {}})])
    nx_graph.add_edge(2, 2, _uv_edges=[(2, 2, {10: {}, 11: {}, 12: {}})])
    graph = from_digraph(nx_graph)
    assert dict(graph.nodes) == {1: {}, 2: {}}
    expected_edges = {
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
    assert dict(graph.edges) == expected_edges


# ---------------------------
# Tests for undirected Graph conversion
# ---------------------------


def test_to_graph_basic():
    """Test converting a basic StrictMultiDiGraph to a revertible NetworkX Graph."""
    graph = create_sample_graph(with_attrs=False)
    nx_graph = to_graph(graph)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    # In an undirected graph, edges from (1,2) and (2,1) are consolidated.
    expected_edges = {
        (1, 2): {
            "_uv_edges": [(1, 2, {1: {}, 2: {}, 3: {}}), (2, 1, {4: {}, 5: {}, 6: {}})]
        },
        (1, 1): {"_uv_edges": [(1, 1, {7: {}, 8: {}, 9: {}})]},
        (2, 2): {"_uv_edges": [(2, 2, {10: {}, 11: {}, 12: {}})]},
    }
    assert dict(nx_graph.edges) == expected_edges


def test_to_graph_with_edge_func():
    """Test converting a StrictMultiDiGraph to a Graph using a custom edge function."""
    graph = create_sample_graph(with_attrs=True)
    nx_graph = to_graph(
        graph,
        edge_func=lambda g, u, v, edges: {
            "cost": min(edge["cost"] for edge in edges.values()),
            "capacity": sum(edge["capacity"] for edge in edges.values()),
        },
    )
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    expected_edges = {
        (1, 2): {
            "cost": 4,
            "capacity": 15,
            "_uv_edges": [
                (
                    1,
                    2,
                    {
                        1: {"cost": 1, "capacity": 1},
                        2: {"cost": 2, "capacity": 2},
                        3: {"cost": 3, "capacity": 3},
                    },
                ),
                (
                    2,
                    1,
                    {
                        4: {"cost": 4, "capacity": 4},
                        5: {"cost": 5, "capacity": 5},
                        6: {"cost": 6, "capacity": 6},
                    },
                ),
            ],
        },
        (1, 1): {
            "cost": 7,
            "capacity": 24,
            "_uv_edges": [
                (
                    1,
                    1,
                    {
                        7: {"cost": 7, "capacity": 7},
                        8: {"cost": 8, "capacity": 8},
                        9: {"cost": 9, "capacity": 9},
                    },
                ),
            ],
        },
        (2, 2): {
            "cost": 10,
            "capacity": 33,
            "_uv_edges": [
                (
                    2,
                    2,
                    {
                        10: {"cost": 10, "capacity": 10},
                        11: {"cost": 11, "capacity": 11},
                        12: {"cost": 12, "capacity": 12},
                    },
                ),
            ],
        },
    }
    assert dict(nx_graph.edges) == expected_edges


def test_to_graph_non_revertible():
    """Test converting a StrictMultiDiGraph to a Graph with revertible set to False."""
    graph = create_sample_graph(with_attrs=False)
    nx_graph = to_graph(graph, revertible=False)
    assert dict(nx_graph.nodes) == {1: {}, 2: {}}
    expected_edges = {
        (1, 2): {},
        (1, 1): {},
        (2, 2): {},
    }
    assert dict(nx_graph.edges) == expected_edges


def test_from_graph():
    """Test restoring a StrictMultiDiGraph from a revertible NetworkX Graph."""
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
    expected_edges = {
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
    assert dict(graph.edges) == expected_edges


# ---------------------------
# Additional Round-Trip and Empty Graph Tests
# ---------------------------


def test_round_trip_digraph():
    """Test round-trip conversion: StrictMultiDiGraph -> DiGraph -> StrictMultiDiGraph."""
    original = create_sample_graph(with_attrs=True)
    nx_digraph = to_digraph(original)
    restored = from_digraph(nx_digraph)
    # Check that node sets match.
    assert dict(original.nodes) == dict(restored.nodes)
    # Check that edge sets (keys and attributes) match.
    assert dict(original.edges) == dict(restored.edges)


def test_round_trip_graph():
    """Test round-trip conversion: StrictMultiDiGraph -> Graph -> StrictMultiDiGraph."""
    original = create_sample_graph(with_attrs=True)
    nx_graph = to_graph(original)
    restored = from_graph(nx_graph)
    assert dict(original.nodes) == dict(restored.nodes)
    assert dict(original.edges) == dict(restored.edges)


def test_empty_graph_conversions():
    """Test conversion functions on an empty StrictMultiDiGraph."""
    empty = StrictMultiDiGraph()
    # Test DiGraph conversion.
    nx_digraph = to_digraph(empty)
    assert dict(nx_digraph.nodes) == {}
    assert dict(nx_digraph.edges) == {}
    restored_digraph = from_digraph(nx_digraph)
    assert dict(restored_digraph.nodes) == {}
    assert dict(restored_digraph.edges) == {}
    # Test Graph conversion.
    nx_graph = to_graph(empty)
    assert dict(nx_graph.nodes) == {}
    assert dict(nx_graph.edges) == {}
    restored_graph = from_graph(nx_graph)
    assert dict(restored_graph.nodes) == {}
    assert dict(restored_graph.edges) == {}
