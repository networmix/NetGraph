import pytest
import networkx as nx

from ngraph.lib.graph import StrictMultiDiGraph


def test_init_empty_graph():
    """Ensure a newly initialized graph has no nodes or edges."""
    g = StrictMultiDiGraph()
    assert len(g) == 0  # No nodes
    assert g.get_edges() == {}
    assert g._edges == {}  # internal mapping is empty


def test_add_node():
    """Test adding a single node."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    assert "A" in g
    assert g.get_nodes() == {"A": {}}


def test_add_node_duplicate():
    """Adding a node that already exists should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    with pytest.raises(ValueError, match="already exists"):
        g.add_node("A")  # Duplicate node -> ValueError


def test_remove_node_basic():
    """Ensure node removal also cleans up node attributes and reduces graph size."""
    g = StrictMultiDiGraph()
    g.add_node("A", test_attr="NODE_A")
    g.add_node("B")
    assert len(g) == 2
    assert g.get_nodes()["A"]["test_attr"] == "NODE_A"

    g.remove_node("A")
    assert "A" not in g
    assert len(g) == 1
    assert g.get_nodes() == {"B": {}}

    # removing second node
    g.remove_node("B")
    assert len(g) == 0


def test_remove_node_missing():
    """Removing a non-existent node should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    with pytest.raises(ValueError, match="does not exist"):
        g.remove_node("B")


def test_add_edge_basic():
    """Add an edge when both source and target nodes exist."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    e_id = g.add_edge("A", "B", weight=10)
    assert e_id in g._edges
    assert g.get_edge_attr(e_id) == {"weight": 10}
    assert g._edges[e_id] == ("A", "B", e_id, {"weight": 10})

    # Nx adjacency check
    assert "B" in g.succ["A"]
    assert "A" in g.pred["B"]


def test_add_edge_with_custom_key():
    """Add an edge with a user-supplied new key and confirm it is preserved."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    custom_key = "my_custom_edge_id"
    returned_key = g.add_edge("A", "B", key=custom_key, weight=999)

    # Verify the returned key matches what we passed in
    assert returned_key == custom_key

    # Confirm the edge exists in the internal mapping
    assert custom_key in g.get_edges()

    # Check attributes
    assert g.get_edge_attr(custom_key) == {"weight": 999}


def test_add_edge_nonexistent_nodes():
    """Adding an edge where either node doesn't exist should fail."""
    g = StrictMultiDiGraph()
    g.add_node("A")

    with pytest.raises(ValueError, match="Target node 'B' does not exist"):
        g.add_edge("A", "B")

    with pytest.raises(ValueError, match="Source node 'X' does not exist"):
        g.add_edge("X", "A")


def test_add_edge_duplicate_id():
    """Forbid reusing an existing edge ID."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    e1 = g.add_edge("A", "B")
    # Attempt to add a second edge with the same key
    with pytest.raises(ValueError, match="already exists"):
        g.add_edge("A", "B", key=e1)


def test_remove_edge_basic():
    """Remove a specific edge by key, then remove all edges from u->v."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    e1 = g.add_edge("A", "B", label="E1")
    e2 = g.add_edge("A", "B", label="E2")  # parallel edge
    assert e1 in g.get_edges()
    assert e2 in g.get_edges()

    # Remove e1 by ID
    g.remove_edge("A", "B", key=e1)
    assert e1 not in g.get_edges()
    assert e2 in g.get_edges()

    # Now remove the remaining edges from A->B
    g.remove_edge("A", "B")
    assert e2 not in g.get_edges()
    assert "B" not in g.succ["A"]


def test_remove_edge_wrong_pair_key():
    """
    Ensure that if we try to remove an edge using the wrong (u, v) pair
    while specifying key, we get a ValueError about mismatched src/dst.
    """
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B")

    # Attempt remove edge using reversed node pair from the actual one
    with pytest.raises(ValueError, match="is actually from A to B, not from B to A"):
        g.remove_edge("B", "A", key=e1)


def test_remove_edge_missing_nodes():
    """Removing an edge should fail if source or target node doesn't exist."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B")

    with pytest.raises(ValueError, match="Source node 'X' does not exist"):
        g.remove_edge("X", "B")

    with pytest.raises(ValueError, match="Target node 'Y' does not exist"):
        g.remove_edge("A", "Y")

    # e1 is still present
    assert e1 in g.get_edges()


def test_remove_edge_nonexistent_id():
    """Removing a specific edge that doesn't exist should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B")
    with pytest.raises(ValueError, match="No edge with id='999' found"):
        g.remove_edge("A", "B", key="999")
    assert e1 in g.get_edges()


def test_remove_edge_no_edges():
    """Removing all edges from A->B when none exist should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    with pytest.raises(ValueError, match="No edges from 'A' to 'B' to remove"):
        g.remove_edge("A", "B")


def test_remove_edge_by_id():
    """Remove edges by their unique ID."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B", label="E1")
    e2 = g.add_edge("A", "B", label="E2")

    g.remove_edge_by_id(e1)
    assert e1 not in g.get_edges()
    assert e2 in g.get_edges()

    g.remove_edge_by_id(e2)
    assert e2 not in g.get_edges()
    assert "B" not in g.succ["A"]


def test_remove_edge_by_id_missing():
    """Removing an edge by ID that doesn't exist should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_edge("A", "B")

    with pytest.raises(ValueError, match="Edge with id='999' not found"):
        g.remove_edge_by_id("999")


def test_copy_deep():
    """Test the pickle-based deep copy logic."""
    g = StrictMultiDiGraph()
    g.add_node("A", nattr="NA")
    g.add_node("B", nattr="NB")
    e1 = g.add_edge("A", "B", label="E1", meta={"x": 123})
    e2 = g.add_edge("B", "A", label="E2")

    g2 = g.copy()  # pickle-based deep copy by default
    # Ensure it's a distinct object
    assert g2 is not g
    # Structure check
    assert set(g2.nodes) == {"A", "B"}
    assert set(g2.get_edges()) == {e1, e2}

    # Remove node from original
    g.remove_node("A")
    # The copy should remain unchanged
    assert "A" in g2
    assert e1 in g2.get_edges()

    # Attributes carried over
    assert g2.nodes["A"]["nattr"] == "NA"
    assert g2.get_edge_attr(e1) == {"label": "E1", "meta": {"x": 123}}


def test_copy_as_view():
    """Test copying as a view rather than deep copy."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B")

    # as_view requires pickle=False
    g_view = g.copy(as_view=True, pickle=False)
    assert g_view is not g

    # Because it's a view, changes to g should reflect in g_view
    g.remove_edge_by_id(e1)
    assert e1 not in g_view.get_edges()


def test_get_nodes_and_edges():
    """Check the convenience getters for nodes and edges."""
    g = StrictMultiDiGraph()
    g.add_node("A", color="red")
    g.add_node("B", color="blue")
    e1 = g.add_edge("A", "B", weight=10)
    e2 = g.add_edge("B", "A", weight=20)

    assert g.get_nodes() == {"A": {"color": "red"}, "B": {"color": "blue"}}

    edges = g.get_edges()
    assert e1 in edges
    assert e2 in edges
    assert edges[e1] == ("A", "B", e1, {"weight": 10})
    assert edges[e2] == ("B", "A", e2, {"weight": 20})


def test_get_edge_attr():
    """Check retrieving attributes of a specific edge."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    e1 = g.add_edge("A", "B", cost=123)
    assert g.get_edge_attr(e1) == {"cost": 123}


def test_get_edge_attr_missing_key():
    """Calling get_edge_attr with an unknown key should raise ValueError."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_edge("A", "B", cost=123)

    with pytest.raises(ValueError, match="Edge with id='999' not found"):
        g.get_edge_attr("999")


def test_has_edge_by_id():
    """Verify the has_edge_by_id method behavior."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    # No edges yet, should return False
    assert not g.has_edge_by_id("nonexistent_key")

    # Add edge
    e1 = g.add_edge("A", "B")
    assert g.has_edge_by_id(e1) is True

    # Remove edge
    g.remove_edge_by_id(e1)
    assert not g.has_edge_by_id(e1)


def test_edges_between():
    """Test listing all edge IDs from node u to node v."""
    g = StrictMultiDiGraph()
    for node in ["A", "B", "C"]:
        g.add_node(node)

    # No edges yet
    assert g.edges_between("A", "B") == []

    # Add a single edge A->B
    e1 = g.add_edge("A", "B")
    assert g.edges_between("A", "B") == [e1]
    assert g.edges_between("B", "C") == []

    # Add two parallel edges A->B
    e2 = g.add_edge("A", "B")
    edges_ab = g.edges_between("A", "B")
    # order may vary, so compare as a set
    assert set(edges_ab) == {e1, e2}

    # Node 'X' does not exist in graph, or no edges from B->A
    assert g.edges_between("B", "A") == []
    assert g.edges_between("X", "B") == []


def test_update_edge_attr():
    """Check that update_edge_attr adds or changes attributes on an existing edge."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")

    e1 = g.add_edge("A", "B", color="red")
    assert g.get_edge_attr(e1) == {"color": "red"}

    # Update with new attributes
    g.update_edge_attr(e1, weight=10, color="blue")
    assert g.get_edge_attr(e1) == {"color": "blue", "weight": 10}

    # Attempt to update a non-existent edge
    with pytest.raises(ValueError, match="Edge with id='fake_id' not found"):
        g.update_edge_attr("fake_id", cost=999)


def test_networkx_algorithm():
    """Demonstrate that standard NetworkX algorithms function as expected."""
    g = StrictMultiDiGraph()
    for node in ["A", "B", "BB", "C"]:
        g.add_node(node)
    g.add_edge("A", "B", weight=10)
    g.add_edge("A", "BB", weight=10)
    g.add_edge("B", "C", weight=4)
    g.add_edge("BB", "C", weight=12)
    g.add_edge("BB", "C", weight=5)
    g.add_edge("BB", "C", weight=4)

    # Because we have multi-edges from BB->C, define cost as the min of any parallel edge's weight
    all_sp = list(
        nx.all_shortest_paths(
            G=g,
            source="A",
            target="C",
            weight=lambda u, v, multi_attrs: min(
                d["weight"] for d in multi_attrs.values()
            ),
        )
    )
    # Expect two equally short paths: A->B->C (10+4=14) and A->BB->C (10+4=14)
    assert sorted(all_sp) == sorted([["A", "B", "C"], ["A", "BB", "C"]])
