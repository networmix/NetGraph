# pylint: disable=protected-access,invalid-name
import pytest
import networkx as nx

from ngraph.lib.graph import MultiDiGraph


def test_graph_init_1():
    MultiDiGraph()


def test_graph_add_node_1():
    g = MultiDiGraph()
    g.add_node("A")
    assert "A" in g


def test_graph_add_node_2():
    g = MultiDiGraph()
    g.add_node("A", test_attr="TEST")
    assert g.nodes["A"] == {"test_attr": "TEST"}


def test_modify_node_1():
    g = MultiDiGraph()
    g.add_node("A", test_attr="TEST")
    assert g.nodes["A"] == {"test_attr": "TEST"}
    g.nodes["A"]["test_attr"] = "TEST2"
    assert g.nodes["A"] == {"test_attr": "TEST2"}
    g.nodes["A"]["test_attr2"] = "TEST3"
    assert g.nodes["A"] == {"test_attr": "TEST2", "test_attr2": "TEST3"}


def test_graph_len_1():
    g = MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    assert len(g) == len(g.nodes)


def test_graph_contains_1():
    g = MultiDiGraph()
    nodes = set(["A", "B", "C"])
    for node in nodes:
        g.add_node(node)
        assert node in g


def test_graph_iter_1():
    g = MultiDiGraph()
    nodes = set(["A", "B", "C"])
    res = set()
    for node in nodes:
        g.add_node(node)
    for node in g:
        res.add(node)
    assert nodes == res


def test_graph_add_edge_1():
    g = MultiDiGraph()
    edge_id = g.add_edge("A", "B", test_attr="TEST_edge")
    assert "A" in g
    assert "B" in g
    assert edge_id == 0
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge"})
    assert "B" in g.succ["A"]
    assert "A" in g.pred["B"]
    assert g.succ["A"]["B"] == {0: {"test_attr": "TEST_edge"}}
    assert g.pred["B"]["A"] == {0: {"test_attr": "TEST_edge"}}


def test_graph_add_edge_2():
    g = MultiDiGraph()
    g.add_node("A", test_attr="TEST_nodeA")
    g.add_node("B", test_attr="TEST_nodeB")
    g.add_edge("A", "B", test_attr="TEST_edge")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge"})
    assert "B" in g.succ["A"]
    assert "A" in g.pred["B"]
    assert g.succ["A"]["B"] == {0: {"test_attr": "TEST_edge"}}
    assert g.pred["B"]["A"] == {0: {"test_attr": "TEST_edge"}}


def test_graph_add_edge_3():
    g = MultiDiGraph()
    edge1_id = g.add_edge("A", "B", test_attr="TEST_edge1")
    edge2_id = g.add_edge("A", "B", test_attr="TEST_edge2")
    assert "A" in g
    assert "B" in g
    assert edge1_id == 0
    assert edge2_id == 1
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert "B" in g.succ["A"]
    assert "A" in g.pred["B"]
    assert g.succ["A"]["B"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }
    assert g.pred["B"]["A"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }


def test_graph_add_edges_from_1():
    g = MultiDiGraph()
    g.add_edges_from([("A", "B"), ("B", "C")])
    assert "A" in g
    assert "B" in g
    assert "C" in g
    assert g._edges[0] == ("A", "B", 0, {})
    assert g._edges[1] == ("B", "C", 1, {})
    assert "B" in g.succ["A"]
    assert "A" in g.pred["B"]
    assert "C" in g.succ["B"]
    assert "B" in g.pred["C"]
    assert g.succ["A"]["B"] == {0: {}}
    assert g.pred["B"]["A"] == {0: {}}
    assert g.succ["B"]["C"] == {1: {}}
    assert g.pred["C"]["B"] == {1: {}}


def test_modify_edge_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge")
    assert g["A"]["B"][0] == {"test_attr": "TEST_edge"}
    g["A"]["B"][0]["test_attr"] = "TEST_edge2"
    assert g["A"]["B"][0] == {"test_attr": "TEST_edge2"}
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge2"})


def test_graph_remove_edge_1():
    """
    Expectations:
        Method remove_edge removes all edges between given nodes (obeying direction)
    """
    g = MultiDiGraph()
    g.add_edge("A", "B")
    g.add_edge("A", "B")
    g.add_edge("B", "A")

    assert g._edges[0] == ("A", "B", 0, {})
    assert g._edges[1] == ("A", "B", 1, {})
    assert g._edges[2] == ("B", "A", 2, {})

    assert g.succ["A"]["B"] == {0: {}, 1: {}}
    assert g.pred["B"]["A"] == {0: {}, 1: {}}

    assert g.succ["B"]["A"] == {2: {}}
    assert g.pred["A"]["B"] == {2: {}}

    g.remove_edge("A", "B")

    assert 0 not in g._edges
    assert 1 not in g._edges
    assert 2 in g._edges
    assert g.succ["A"] == {}
    assert g.pred["B"] == {}
    assert g.succ["B"]["A"] == {2: {}}
    assert g.pred["A"]["B"] == {2: {}}


def test_graph_remove_edge_2():
    """
    Expectations:
        Method remove_edge does nothing if either src or dst node does not exist
        Method remove_edge does nothing if the edge with given id does not exist
        Method remove_edge removes only the edge with the given id if it exists
        If the last edge removed - clean-up _adj_in and _adj_out accordingly
    """
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge1")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g.succ["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g.pred["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    g.remove_edge("A", "C")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g.succ["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g.pred["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    with pytest.raises(ValueError):
        g.remove_edge("A", "B", edge_id=10)  # edge_id does not exist

    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g.succ["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g.pred["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    g.remove_edge("A", "B", edge_id=0)
    assert "A" in g
    assert "B" in g
    assert 0 not in g._edges
    assert g.succ["A"] == {}
    assert g.pred["B"] == {}


def test_graph_remove_edge_3():
    """
    Expectations:
        Method remove_edge removes only the edge with the given id if it exists
        If the last edge removed - clean-up _adj_in and _adj_out accordingly
    """
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge1")
    g.add_edge("A", "B", test_attr="TEST_edge2")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert g.succ["A"]["B"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }
    assert g.pred["B"]["A"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }

    g.remove_edge("A", "B", edge_id=0)
    assert "A" in g
    assert "B" in g
    assert 0 not in g._edges
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert g.succ["A"]["B"] == {1: {"test_attr": "TEST_edge2"}}
    assert g.pred["B"]["A"] == {1: {"test_attr": "TEST_edge2"}}

    g.remove_edge("A", "B", edge_id=1)
    assert "A" in g
    assert "B" in g
    assert g._edges == {}
    assert g.succ["A"] == {}
    assert g.pred["B"] == {}


def test_graph_remove_edge_by_id_1():
    """
    Expectations:
        Method remove_edge_by_id removes only the edge with the given id if it exists
        If the last edge removed - clean-up _adj_in and _adj_out accordingly
    """
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge1")
    g.add_edge("A", "B", test_attr="TEST_edge2")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert g.succ["A"]["B"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }
    assert g.pred["B"]["A"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }

    g.remove_edge_by_id(0)
    assert "A" in g
    assert "B" in g
    assert 0 not in g._edges
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert g.succ["A"]["B"] == {1: {"test_attr": "TEST_edge2"}}
    assert g.pred["B"]["A"] == {1: {"test_attr": "TEST_edge2"}}

    g.remove_edge_by_id(1)
    assert "A" in g
    assert "B" in g
    assert g._edges == {}
    assert g.succ["A"] == {}
    assert g.pred["B"] == {}


def test_graph_remove_edge_by_id_2():
    """
    try removing non-existent edge
    """
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge1")
    g.add_edge("A", "B", test_attr="TEST_edge2")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert g.succ["A"]["B"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }
    assert g.pred["B"]["A"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }

    with pytest.raises(ValueError):
        g.remove_edge_by_id(2)  # edge_id does not exist


def test_graph_remove_node_1():
    """
    Expectations:
    """
    g = MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_edge("A", "B", test_attr="TEST_edge1a")
    g.add_edge("B", "A", test_attr="TEST_edge1a")
    g.add_edge("A", "B", test_attr="TEST_edge1b")
    g.add_edge("B", "A", test_attr="TEST_edge1b")
    g.add_edge("B", "C", test_attr="TEST_edge2")
    g.add_edge("C", "B", test_attr="TEST_edge2")
    g.add_edge("C", "A", test_attr="TEST_edge3")
    g.add_edge("A", "C", test_attr="TEST_edge3")

    assert "A" in g
    assert "B" in g
    assert "C" in g

    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1a"})
    assert g._edges[1] == ("B", "A", 1, {"test_attr": "TEST_edge1a"})
    assert g._edges[2] == ("A", "B", 2, {"test_attr": "TEST_edge1b"})
    assert g._edges[3] == ("B", "A", 3, {"test_attr": "TEST_edge1b"})
    assert g._edges[4] == ("B", "C", 4, {"test_attr": "TEST_edge2"})
    assert g._edges[5] == ("C", "B", 5, {"test_attr": "TEST_edge2"})
    assert g._edges[6] == ("C", "A", 6, {"test_attr": "TEST_edge3"})
    assert g._edges[7] == ("A", "C", 7, {"test_attr": "TEST_edge3"})

    g.remove_node("A")
    assert "A" not in g
    for edge in g._edges.values():
        assert "A" not in edge

    g.remove_node("B")
    assert "B" not in g
    assert len(g._edges) == 0

    g.remove_node("C")
    assert len(g.nodes) == 0
    assert len(g.succ) == 0
    assert len(g.pred) == 0


def test_graph_remove_node_2():
    """
    Remove non-existent node. Expect no changes.
    """
    g = MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_edge("A", "B", test_attr="TEST_edge1a")
    g.add_edge("B", "A", test_attr="TEST_edge1a")
    g.add_edge("A", "B", test_attr="TEST_edge1b")
    g.add_edge("B", "A", test_attr="TEST_edge1b")
    g.add_edge("B", "C", test_attr="TEST_edge2")
    g.add_edge("C", "B", test_attr="TEST_edge2")
    g.add_edge("C", "A", test_attr="TEST_edge3")
    g.add_edge("A", "C", test_attr="TEST_edge3")

    assert "A" in g
    assert "B" in g
    assert "C" in g

    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1a"})
    assert g._edges[1] == ("B", "A", 1, {"test_attr": "TEST_edge1a"})
    assert g._edges[2] == ("A", "B", 2, {"test_attr": "TEST_edge1b"})
    assert g._edges[3] == ("B", "A", 3, {"test_attr": "TEST_edge1b"})
    assert g._edges[4] == ("B", "C", 4, {"test_attr": "TEST_edge2"})
    assert g._edges[5] == ("C", "B", 5, {"test_attr": "TEST_edge2"})
    assert g._edges[6] == ("C", "A", 6, {"test_attr": "TEST_edge3"})
    assert g._edges[7] == ("A", "C", 7, {"test_attr": "TEST_edge3"})

    g.remove_node("D")
    assert "A" in g
    assert "B" in g
    assert "C" in g

    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1a"})
    assert g._edges[1] == ("B", "A", 1, {"test_attr": "TEST_edge1a"})


def test_graph_copy_1():
    """
    Expectations:
        method copy() returns a deep copy of the graph
    """
    g = MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_edge("A", "B", test_attr="TEST_edge1a")
    g.add_edge("B", "A", test_attr="TEST_edge1a")
    g.add_edge("A", "B", test_attr="TEST_edge1b")
    g.add_edge("B", "A", test_attr="TEST_edge1b")
    g.add_edge("B", "C", test_attr="TEST_edge2")
    g.add_edge("C", "B", test_attr="TEST_edge2")
    g.add_edge("C", "A", test_attr="TEST_edge3")
    g.add_edge("A", "C", test_attr="TEST_edge3")

    j = g.copy()

    assert "A" in g
    assert "B" in g
    assert "C" in g

    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1a"})
    assert g._edges[1] == ("B", "A", 1, {"test_attr": "TEST_edge1a"})
    assert g._edges[2] == ("A", "B", 2, {"test_attr": "TEST_edge1b"})
    assert g._edges[3] == ("B", "A", 3, {"test_attr": "TEST_edge1b"})
    assert g._edges[4] == ("B", "C", 4, {"test_attr": "TEST_edge2"})
    assert g._edges[5] == ("C", "B", 5, {"test_attr": "TEST_edge2"})
    assert g._edges[6] == ("C", "A", 6, {"test_attr": "TEST_edge3"})
    assert g._edges[7] == ("A", "C", 7, {"test_attr": "TEST_edge3"})

    g.remove_node("A")
    assert "A" not in g
    for edge in g._edges.values():
        assert "A" not in edge

    g.remove_node("B")
    assert "B" not in g
    assert len(g._edges) == 0

    g.remove_node("C")
    assert len(g.nodes) == 0
    assert len(g.succ) == 0
    assert len(g.pred) == 0

    assert "A" in j
    assert "B" in j
    assert "C" in j

    assert j._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1a"})
    assert j._edges[1] == ("B", "A", 1, {"test_attr": "TEST_edge1a"})
    assert j._edges[2] == ("A", "B", 2, {"test_attr": "TEST_edge1b"})
    assert j._edges[3] == ("B", "A", 3, {"test_attr": "TEST_edge1b"})
    assert j._edges[4] == ("B", "C", 4, {"test_attr": "TEST_edge2"})
    assert j._edges[5] == ("C", "B", 5, {"test_attr": "TEST_edge2"})
    assert j._edges[6] == ("C", "A", 6, {"test_attr": "TEST_edge3"})
    assert j._edges[7] == ("A", "C", 7, {"test_attr": "TEST_edge3"})


def test_networkx_all_shortest_paths_1():
    graph = MultiDiGraph()
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


def test_get_nodes_1():
    """
    self._nodes[node_id] = attr
    """
    graph = MultiDiGraph()
    graph.add_node("A", attr="TEST")
    graph.add_node("B", attr="TEST")

    assert graph.get_nodes() == {"A": {"attr": "TEST"}, "B": {"attr": "TEST"}}


def test_get_edges_1():
    """
    self._edges[edge_id] = (src_node, dst_node, edge_id, attr)
    """
    graph = MultiDiGraph()
    graph.add_edge("A", "B", metric=10)
    graph.add_edge("A", "B", metric=20)

    assert graph.get_edges() == {
        0: ("A", "B", 0, {"metric": 10}),
        1: ("A", "B", 1, {"metric": 20}),
    }


def test_get_edge_attr():
    graph = MultiDiGraph()
    edge1_id = graph.add_edge("A", "B", metric=10)
    edge2_id = graph.add_edge("A", "B", metric=20)

    assert graph.get_edge_attr(edge1_id) == {"metric": 10}
    assert graph.get_edge_attr(edge2_id) == {"metric": 20}
