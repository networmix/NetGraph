# pylint: disable=protected-access,invalid-name
from ngraph.graph import MultiDiGraph


def test_graph_init_1():
    MultiDiGraph()


def test_graph_add_node_1():
    g = MultiDiGraph()
    g.add_node("A")
    assert "A" in g._nodes
    assert "A" in g._adj_in
    assert "A" in g._adj_out


def test_graph_add_node_2():
    g = MultiDiGraph()
    g.add_node("A", test_attr="TEST")
    assert g._nodes["A"] == {"test_attr": "TEST"}


def test_graph_len_1():
    g = MultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    assert len(g) == len(g._nodes)


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
    g.add_edge("A", "B", test_attr="TEST_edge")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge"})
    assert "B" in g._adj_out["A"]
    assert "A" in g._adj_in["B"]
    assert g._adj_out["A"]["B"] == {0: {"test_attr": "TEST_edge"}}
    assert g._adj_in["B"]["A"] == {0: {"test_attr": "TEST_edge"}}


def test_graph_add_edge_2():
    g = MultiDiGraph()
    g.add_node("A", test_attr="TEST_nodeA")
    g.add_node("B", test_attr="TEST_nodeB")
    g.add_edge("A", "B", test_attr="TEST_edge")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge"})
    assert "B" in g._adj_out["A"]
    assert "A" in g._adj_in["B"]
    assert g._adj_out["A"]["B"] == {0: {"test_attr": "TEST_edge"}}
    assert g._adj_in["B"]["A"] == {0: {"test_attr": "TEST_edge"}}


def test_graph_add_edge_3():
    g = MultiDiGraph()
    g.add_edge("A", "B", test_attr="TEST_edge1")
    g.add_edge("A", "B", test_attr="TEST_edge2")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._edges[1] == ("A", "B", 1, {"test_attr": "TEST_edge2"})
    assert "B" in g._adj_out["A"]
    assert "A" in g._adj_in["B"]
    assert g._adj_out["A"]["B"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }
    assert g._adj_in["B"]["A"] == {
        0: {"test_attr": "TEST_edge1"},
        1: {"test_attr": "TEST_edge2"},
    }


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

    assert g._adj_out["A"]["B"] == {0: {}, 1: {}}
    assert g._adj_in["B"]["A"] == {0: {}, 1: {}}

    assert g._adj_out["B"]["A"] == {2: {}}
    assert g._adj_in["A"]["B"] == {2: {}}

    g.remove_edge("A", "B")

    assert 0 not in g._edges
    assert 1 not in g._edges
    assert 2 in g._edges
    assert g._adj_out["A"] == {}
    assert g._adj_in["B"] == {}
    assert g._adj_out["B"]["A"] == {2: {}}
    assert g._adj_in["A"]["B"] == {2: {}}


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
    assert g._adj_out["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g._adj_in["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    g.remove_edge("A", "C")
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._adj_out["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g._adj_in["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    g.remove_edge("A", "B", edge_id=10)
    assert "A" in g
    assert "B" in g
    assert g._edges[0] == ("A", "B", 0, {"test_attr": "TEST_edge1"})
    assert g._adj_out["A"]["B"] == {0: {"test_attr": "TEST_edge1"}}
    assert g._adj_in["B"]["A"] == {0: {"test_attr": "TEST_edge1"}}

    g.remove_edge("A", "B", edge_id=0)
    assert "A" in g
    assert "B" in g
    assert 0 not in g._edges
    assert g._adj_out["A"] == {}
    assert g._adj_in["B"] == {}


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
    assert len(g._nodes) == 0
    assert len(g._adj_out) == 0
    assert len(g._adj_in) == 0


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
    assert len(g._nodes) == 0
    assert len(g._adj_out) == 0
    assert len(g._adj_in) == 0

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
