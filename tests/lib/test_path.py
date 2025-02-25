import pytest
from ngraph.lib.graph import StrictMultiDiGraph, EdgeID
from ngraph.lib.algorithms.base import PathTuple
from ngraph.lib.path import Path


def test_path_init():
    """Test basic initialization of a Path and derived sets."""
    path_tuple: PathTuple = (
        ("A", ("edgeA-B",)),
        ("B", ("edgeB-C",)),
        ("C", ()),
    )
    p = Path(path_tuple, cost=10.0)

    assert p.path_tuple == path_tuple
    assert p.cost == 10.0
    assert p.nodes == {"A", "B", "C"}
    assert p.edges == {"edgeA-B", "edgeB-C"}
    # The last element has an empty tuple, so we have exactly 2 edge_tuples
    assert len(p.edge_tuples) == 3  # Includes the empty tuple for "C"
    assert ("edgeA-B",) in p.edge_tuples
    assert ("edgeB-C",) in p.edge_tuples
    assert () in p.edge_tuples


def test_path_repr():
    """Test string representation of Path."""
    p = Path((("A", ("edgeA-B",)), ("B", ())), cost=5)
    assert "Path" in repr(p)
    assert "edgeA-B" in repr(p)
    assert "cost=5" in repr(p)


def test_path_indexing_and_iteration():
    """Test __getitem__ and __iter__ for accessing path elements."""
    path_tuple: PathTuple = (
        ("N1", ("e1", "e2")),
        ("N2", ()),
    )
    p = Path(path_tuple, 3)
    assert p[0] == ("N1", ("e1", "e2"))
    assert p[1] == ("N2", ())
    # Test iteration
    items = list(p)
    assert len(items) == 2
    assert items[0][0] == "N1"
    assert items[1][0] == "N2"


def test_path_len():
    """Test __len__ for number of elements in path."""
    p = Path((("A", ("eA-B",)), ("B", ("eB-C",)), ("C", ())), cost=4)
    assert len(p) == 3


def test_path_src_node_and_dst_node():
    """Test src_node and dst_node properties."""
    p = Path((("X", ("e1",)), ("Y", ("e2",)), ("Z", ())), cost=2)
    assert p.src_node == "X"
    assert p.dst_node == "Z"


def test_path_comparison():
    """Test __lt__ (less than) for cost-based comparison."""
    p1 = Path((("A", ("e1",)), ("B", ())), cost=10)
    p2 = Path((("A", ("e1",)), ("B", ())), cost=20)
    assert p1 < p2
    assert not (p2 < p1)


def test_path_equality():
    """Test equality and hash usage for Path."""
    p1 = Path((("A", ("e1",)), ("B", ())), cost=5)
    p2 = Path((("A", ("e1",)), ("B", ())), cost=5)
    p3 = Path((("A", ("e1",)), ("C", ())), cost=5)
    p4 = Path((("A", ("e1",)), ("B", ())), cost=6)

    assert p1 == p2
    assert p1 != p3
    assert p1 != p4

    s = {p1, p2, p3}
    # p1 and p2 are the same, so set should have only two unique items
    assert len(s) == 2


def test_path_edges_seq():
    """Test edges_seq cached_property."""
    p = Path((("A", ("eA-B",)), ("B", ("eB-C",)), ("C", ())), cost=7)
    # edges_seq should exclude the last element's parallel-edges (often empty)
    assert p.edges_seq == (("eA-B",), ("eB-C",))

    p_single = Path((("A", ()),), cost=0)
    # If length <= 1, it should return an empty tuple
    assert p_single.edges_seq == ()


def test_path_nodes_seq():
    """Test nodes_seq cached_property."""
    p = Path((("X", ("eX-Y",)), ("Y", ())), cost=1)
    assert p.nodes_seq == ("X", "Y")

    p2 = Path((("N1", ("e1",)), ("N2", ("e2",)), ("N3", ())), cost=10)
    assert p2.nodes_seq == ("N1", "N2", "N3")


def test_get_sub_path_success():
    """Test get_sub_path for a valid dst_node with edge cost summation."""
    # Build a small graph
    g = StrictMultiDiGraph()
    for node_id in ("A", "B", "C", "D"):
        g.add_node(node_id)

    # Add edges with 'cost' attributes
    eAB = g.add_edge("A", "B", cost=5)
    eBC = g.add_edge("B", "C", cost=7)
    eCD = g.add_edge("C", "D", cost=2)

    # Path is A->B->C->D
    path_tuple: PathTuple = (
        ("A", (eAB,)),
        ("B", (eBC,)),
        ("C", (eCD,)),
        ("D", ()),
    )
    p = Path(path_tuple, cost=14.0)

    # Subpath: A->B->C
    sub_p = p.get_sub_path("C", g, cost_attr="cost")
    assert sub_p.dst_node == "C"
    # Check that the cost is sum of edges (A->B=5) + (B->C=7) = 12
    assert sub_p.cost == 12
    # Check sub_path elements
    assert len(sub_p) == 3
    assert sub_p[2][0] == "C"
    # Ensure last node is C with empty edges
    assert sub_p.path_tuple[-1] == ("C", ())


def test_get_sub_path_not_found():
    """Test get_sub_path raises ValueError if dst_node not in path."""
    g = StrictMultiDiGraph()
    g.add_node("X")
    g.add_node("Y")

    path_tuple: PathTuple = (("X", ()),)
    p = Path(path_tuple, cost=0)
    with pytest.raises(ValueError, match="Node 'Y' not found in path."):
        _ = p.get_sub_path("Y", g)


def test_get_sub_path_empty_parallel_edges():
    """Test that get_sub_path cost calculation handles empty edge sets."""
    g = StrictMultiDiGraph()
    for n in ("N1", "N2"):
        g.add_node(n)

    # Add an edge between N1->N2
    e12 = g.add_edge("N1", "N2", cost=10)

    # A path where the second to last step has an empty parallel edge set
    # just to confirm we skip cost addition for that step
    path_tuple: PathTuple = (
        ("N1", (e12,)),
        ("N2", ()),
    )
    p = Path(path_tuple, cost=10.0)

    # get_sub_path("N2") should not raise an error,
    # and cost is 10 from the single edge
    sub = p.get_sub_path("N2", g)
    assert sub.cost == 10
    assert len(sub) == 2
