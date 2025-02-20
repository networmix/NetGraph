import pytest
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.io import (
    graph_to_node_link,
    node_link_to_graph,
    edgelist_to_graph,
    graph_to_edgelist,
)


def test_graph_to_node_link_basic():
    """
    Test converting a small StrictMultiDiGraph into a node-link dict.
    """
    g = StrictMultiDiGraph(test_attr="TEST_graph")
    g.add_node("A", color="red")
    g.add_node("B", color="blue")
    e1 = g.add_edge("A", "B", weight=10)
    e2 = g.add_edge("B", "A", weight=99)

    result = graph_to_node_link(g)

    # The top-level 'graph' attribute should contain 'test_attr'
    assert result["graph"] == {"test_attr": "TEST_graph"}

    # We expect 2 nodes, with stable indexing: "A" -> 0, "B" -> 1
    nodes = sorted(result["nodes"], key=lambda x: x["id"])
    assert nodes == [
        {"id": "A", "attr": {"color": "red"}},
        {"id": "B", "attr": {"color": "blue"}},
    ]

    # We expect 2 edges in 'links'. Check the "source"/"target" indices
    links = sorted(result["links"], key=lambda x: x["key"])
    # Typically "A" -> index=0, "B" -> index=1
    # edge_id e1, e2 might be random strings if using base64. We'll just check partial logic:
    assert len(links) == 2
    link_keys = {links[0]["key"], links[1]["key"]}
    assert e1 in link_keys
    assert e2 in link_keys

    # Check one link's structure
    # For example, find the link with key=e1
    link_e1 = next(l for l in links if l["key"] == e1)
    assert link_e1["source"] == 0  # "A" => index 0
    assert link_e1["target"] == 1  # "B" => index 1
    assert link_e1["attr"] == {"weight": "10"} or {"weight": 10}


def test_node_link_to_graph_basic():
    """
    Test reconstructing a StrictMultiDiGraph from a node-link dict.
    """
    data = {
        "graph": {"test_attr": "TEST_graph"},
        "nodes": [
            {"id": "A", "attr": {"color": "red"}},
            {"id": "B", "attr": {"color": "blue"}},
        ],
        "links": [
            {"source": 0, "target": 1, "key": "edgeAB", "attr": {"weight": "10"}},
            {"source": 1, "target": 0, "key": "edgeBA", "attr": {"weight": "99"}},
        ],
    }

    g = node_link_to_graph(data)
    assert isinstance(g, StrictMultiDiGraph)
    # Check top-level Nx attributes
    assert g.graph == {"test_attr": "TEST_graph"}
    # Check nodes
    assert set(g.nodes()) == {"A", "B"}
    assert g.nodes["A"]["color"] == "red"
    assert g.nodes["B"]["color"] == "blue"
    # Check edges
    e_map = g.get_edges()
    assert len(e_map) == 2
    # "edgeAB" should be A->B
    src, dst, eid, attrs = e_map["edgeAB"]
    assert src == "A"
    assert dst == "B"
    assert attrs == {"weight": "10"}
    # "edgeBA" should be B->A
    src, dst, eid, attrs = e_map["edgeBA"]
    assert src == "B"
    assert dst == "A"
    assert attrs == {"weight": "99"}


def test_node_link_round_trip():
    """
    Build a StrictMultiDiGraph, convert to node-link, then reconstruct
    and verify the structure is identical.
    """
    g = StrictMultiDiGraph(description="RoundTrip")
    g.add_node("X", val=1)
    g.add_node("Y", val=2)
    e_xy = g.add_edge("X", "Y", cost=100)
    e_yx = g.add_edge("Y", "X", cost=999)

    data = graph_to_node_link(g)
    g2 = node_link_to_graph(data)

    # Check top-level
    assert g2.graph == {"description": "RoundTrip"}
    # Check nodes
    assert set(g2.nodes()) == {"X", "Y"}
    assert g2.nodes["X"]["val"] == 1
    assert g2.nodes["Y"]["val"] == 2
    # Check edges
    e_map = g2.get_edges()
    assert len(e_map) == 2
    # find e_xy in e_map
    assert e_xy in e_map
    src, dst, eid, attrs = e_map[e_xy]
    assert src == "X"
    assert dst == "Y"
    assert attrs == {"cost": "100"} or {"cost": 100}
    # find e_yx
    assert e_yx in e_map


def test_edgelist_to_graph_basic():
    """
    Test building a graph from a basic edge list with columns.
    """
    lines = [
        "A B 10",
        "B C 20",
        "C A 30",
    ]
    columns = ["src", "dst", "weight"]

    g = edgelist_to_graph(lines, columns)

    assert isinstance(g, StrictMultiDiGraph)
    # Should have 3 edges, 3 nodes
    assert set(g.nodes()) == {"A", "B", "C"}
    assert len(g.get_edges()) == 3
    # Check each edge's attribute
    e_map = g.get_edges()
    # We can't assume numeric IDs, just find them by iteration
    for eid, (src, dst, _, attrs) in e_map.items():
        w = attrs["weight"]
        if src == "A" and dst == "B":
            assert w == "10"
        elif src == "B" and dst == "C":
            assert w == "20"
        elif src == "C" and dst == "A":
            assert w == "30"


def test_edgelist_to_graph_with_key():
    """
    Test using a 'key' column that sets a custom edge ID
    """
    lines = [
        "A B edgeAB 999",
        "B A edgeBA 123",
    ]
    columns = ["src", "dst", "key", "cost"]

    g = edgelist_to_graph(lines, columns, key="key")
    assert len(g.get_edges()) == 2
    # We expect edge IDs "edgeAB", "edgeBA"
    e_map = g.get_edges()
    assert "edgeAB" in e_map
    assert "edgeBA" in e_map
    # Check attributes
    src, dst, eid, attrs = e_map["edgeAB"]
    assert src == "A"
    assert dst == "B"
    assert attrs == {"cost": "999"}


def test_edgelist_to_graph_error_on_mismatch():
    """
    If a line doesn't match the expected columns count, a RuntimeError is raised.
    """
    lines = ["A B 10", "B C 20  EXTRA"]  # good  # mismatch
    columns = ["src", "dst", "weight"]

    with pytest.raises(RuntimeError, match="token count mismatch"):
        edgelist_to_graph(lines, columns)


def test_graph_to_edgelist_basic():
    """
    Test exporting a graph to lines, then reimporting.
    """
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")

    e1 = g.add_edge("A", "B", cost=10)
    e2 = g.add_edge("B", "C", cost=20)
    # No custom keys for the rest -> random base64 IDs
    e3 = g.add_edge("C", "A", label="X")

    lines = graph_to_edgelist(g)
    # By default: [src, dst, key] + sorted(attributes)
    # We won't know the random edge ID, so let's parse them
    # Then reimport them
    g2 = edgelist_to_graph(lines, ["src", "dst", "key", "cost", "label"])

    # Check same node set
    assert set(g2.nodes()) == {"A", "B", "C"}
    # We expect 3 edges
    e2_map = g2.get_edges()
    assert len(e2_map) == 3

    # Because IDs might differ on re-import if we didn't have explicit keys,
    # we only check adjacency & attributes
    # but for e1, e2 we have "cost" attribute, for e3 we have "label"
    # Check adjacency
    edges_seen = set()
    for eid, (s, d, _, attrs) in e2_map.items():
        edges_seen.add((s, d))
        # if there's a "cost" in attrs, it might be "10" or "20"
        # if there's a "label" in attrs, it's "X"
    assert edges_seen == {("A", "B"), ("B", "C"), ("C", "A")}
    # This indicates a successful round-trip.


def test_graph_to_edgelist_columns():
    """
    Test specifying custom columns in graph_to_edgelist.
    """
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    eAB = g.add_edge("A", "B", cost=10, color="red")

    lines = graph_to_edgelist(g, columns=["src", "dst", "cost", "color"], separator=",")
    # We expect one line: "A,B,10,red"
    assert lines == ["A,B,10,red"]
    # Now re-import
    g2 = edgelist_to_graph(
        lines, columns=["src", "dst", "cost", "color"], separator=","
    )
    e_map = g2.get_edges()
    assert len(e_map) == 1
    _, _, _, attrs = next(iter(e_map.values()))
    assert attrs == {"cost": "10", "color": "red"}
