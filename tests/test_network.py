import pytest
from ngraph.network import Network, Node, Link, new_base64_uuid
from ngraph.lib.graph import StrictMultiDiGraph


def test_new_base64_uuid_length_and_uniqueness():
    """
    Generate two Base64-encoded UUIDs and confirm:
      - they are strings with no '=' padding
      - they are 22 chars long
      - they differ from each other
    """
    uuid1 = new_base64_uuid()
    uuid2 = new_base64_uuid()

    assert isinstance(uuid1, str)
    assert isinstance(uuid2, str)
    assert "=" not in uuid1
    assert "=" not in uuid2

    # 22 characters for a UUID in unpadded Base64
    assert len(uuid1) == 22
    assert len(uuid2) == 22

    # They should be unique
    assert uuid1 != uuid2


def test_node_creation_default_attrs():
    """
    A new Node with no attrs should have an empty dict for attrs.
    """
    node = Node("A")
    assert node.name == "A"
    assert node.attrs == {}


def test_node_creation_custom_attrs():
    """
    A new Node can be created with custom attributes that are stored as-is.
    """
    custom_attrs = {"key": "value", "number": 42}
    node = Node("B", attrs=custom_attrs)
    assert node.name == "B"
    assert node.attrs == custom_attrs


def test_link_defaults_and_id_generation():
    """
    A Link without custom parameters should default capacity/cost to 1.0,
    have an empty attrs dict, and generate a unique ID like 'A|B|<uuid>'.
    """
    link = Link("A", "B")

    assert link.capacity == 1.0
    assert link.cost == 1.0
    assert link.attrs == {}

    # ID should start with 'A|B|' and have a random suffix
    assert link.id.startswith("A|B|")
    assert len(link.id) > len("A|B|")


def test_link_custom_values():
    """
    A Link can be created with custom capacity/cost/attrs,
    and the ID is generated automatically.
    """
    custom_attrs = {"color": "red"}
    link = Link("X", "Y", capacity=2.0, cost=4.0, attrs=custom_attrs)

    assert link.source == "X"
    assert link.target == "Y"
    assert link.capacity == 2.0
    assert link.cost == 4.0
    assert link.attrs == custom_attrs
    assert link.id.startswith("X|Y|")


def test_link_id_uniqueness():
    """
    Even if two Links have the same source and target, the auto-generated IDs
    should differ because of the random UUID portion.
    """
    link1 = Link("A", "B")
    link2 = Link("A", "B")
    assert link1.id != link2.id


def test_network_add_node_and_link():
    """
    Adding nodes and links to a Network should store them in dictionaries
    keyed by node name and link ID, respectively.
    """
    network = Network()
    node_a = Node("A")
    node_b = Node("B")

    network.add_node(node_a)
    network.add_node(node_b)

    assert "A" in network.nodes
    assert "B" in network.nodes

    link = Link("A", "B")
    network.add_link(link)

    # Link is stored under link.id
    assert link.id in network.links
    assert network.links[link.id] is link


def test_network_add_link_missing_source():
    """
    Attempting to add a Link whose source node is not in the Network should raise an error.
    """
    network = Network()
    node_b = Node("B")
    network.add_node(node_b)

    link = Link("A", "B")  # 'A' doesn't exist

    with pytest.raises(ValueError, match="Source node 'A' not found in network."):
        network.add_link(link)


def test_network_add_link_missing_target():
    """
    Attempting to add a Link whose target node is not in the Network should raise an error.
    """
    network = Network()
    node_a = Node("A")
    network.add_node(node_a)

    link = Link("A", "B")  # 'B' doesn't exist
    with pytest.raises(ValueError, match="Target node 'B' not found in network."):
        network.add_link(link)


def test_network_attrs():
    """
    The Network's 'attrs' dictionary can store arbitrary metadata about the network.
    """
    network = Network(attrs={"network_type": "test"})
    assert network.attrs["network_type"] == "test"


def test_add_duplicate_node_raises_valueerror():
    """
    Adding a second Node with the same name should raise ValueError
    rather than overwriting the existing node.
    """
    network = Network()
    node1 = Node("A", attrs={"data": 1})
    node2 = Node("A", attrs={"data": 2})

    network.add_node(node1)
    with pytest.raises(ValueError, match="Node 'A' already exists in the network."):
        network.add_node(node2)


def test_select_nodes_by_path():
    """
    Tests select_nodes_by_path for exact matches, slash-based prefix matches,
    and fallback prefix pattern.
    """
    net = Network()
    # Add some nodes
    net.add_node(Node("SEA/spine/myspine-1"))
    net.add_node(Node("SEA/leaf/leaf-1"))
    net.add_node(Node("SEA-other"))
    net.add_node(Node("SFO"))

    # 1) Exact match => "SFO"
    nodes = net.select_nodes_by_path("SFO")
    assert len(nodes) == 1
    assert nodes[0].name == "SFO"

    # 2) Slash prefix => "SEA/spine" matches "SEA/spine/myspine-1"
    nodes = net.select_nodes_by_path("SEA/spine")
    assert len(nodes) == 1
    assert nodes[0].name == "SEA/spine/myspine-1"

    # 3) Fallback: "SEA-other" won't be found by slash prefix "SEA/other",
    #    but if we search "SEA-other", we do an exact match, so we get 1 node
    nodes = net.select_nodes_by_path("SEA-other")
    assert len(nodes) == 1
    assert nodes[0].name == "SEA-other"

    # 4) If we search just "SEA", we match "SEA/spine/myspine-1" and "SEA/leaf/leaf-1"
    #    by slash prefix, so fallback never triggers, and "SEA-other" is not included.
    nodes = net.select_nodes_by_path("SEA")
    found = set(n.name for n in nodes)
    assert found == {
        "SEA/spine/myspine-1",
        "SEA/leaf/leaf-1",
    }


def test_select_nodes_by_path_partial_fallback():
    """
    Tests the partial prefix logic if both exact/slash-based and dash-based
    lookups fail, then partial prefix 'path...' is used.
    """
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("S2"))
    net.add_node(Node("SEA-spine"))
    net.add_node(Node("NOTMATCH"))

    # The path "S" won't match "S" exactly, won't match "S/" or "S-", so it should
    # return partial matches: "S1", "S2", and "SEA-spine".
    nodes = net.select_nodes_by_path("S")
    found = sorted([n.name for n in nodes])
    assert found == ["S1", "S2", "SEA-spine"]


def test_to_strict_multidigraph_add_reverse_true():
    """
    Tests to_strict_multidigraph with add_reverse=True, ensuring
    that both forward and reverse edges are added.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))

    link_ab = Link("A", "B")
    link_bc = Link("B", "C")
    net.add_link(link_ab)
    net.add_link(link_bc)

    graph = net.to_strict_multidigraph(add_reverse=True)

    # Check nodes
    assert set(graph.nodes()) == {"A", "B", "C"}

    # Each link adds two edges (forward + reverse)
    edges = list(graph.edges(keys=True))
    forward_keys = {link_ab.id, link_bc.id}
    reverse_keys = {f"{link_ab.id}_rev", f"{link_bc.id}_rev"}
    all_keys = forward_keys.union(reverse_keys)
    found_keys = {e[2] for e in edges}

    assert found_keys == all_keys


def test_to_strict_multidigraph_add_reverse_false():
    """
    Tests to_strict_multidigraph with add_reverse=False, ensuring
    that only forward edges are added.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    link_ab = Link("A", "B")
    net.add_link(link_ab)

    graph = net.to_strict_multidigraph(add_reverse=False)

    # Check nodes
    assert set(graph.nodes()) == {"A", "B"}

    # Only one forward edge should exist
    edges = list(graph.edges(keys=True))
    assert len(edges) == 1
    assert edges[0][0] == "A"  # source
    assert edges[0][1] == "B"  # target
    assert edges[0][2] == link_ab.id


def test_max_flow_simple():
    """
    Tests a simple chain A -> B -> C to verify the max_flow calculation.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))

    # Add links with capacities
    net.add_link(Link("A", "B", capacity=5))
    net.add_link(Link("B", "C", capacity=3))

    # Max flow from A to C is limited by the smallest capacity (3)
    flow_value = net.max_flow("A", "C")
    assert flow_value == 3.0


def test_max_flow_multi_parallel():
    """
    Tests a scenario where two parallel paths can carry flow.
    A -> B -> C and A -> D -> C, each with capacity 5.
    The total flow A to C should be 10.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("D"))

    net.add_link(Link("A", "B", capacity=5))
    net.add_link(Link("B", "C", capacity=5))
    net.add_link(Link("A", "D", capacity=5))
    net.add_link(Link("D", "C", capacity=5))

    flow_value = net.max_flow("A", "C")
    assert flow_value == 10.0


def test_max_flow_no_source():
    """
    If no node in the network matches the source path, it should raise ValueError.
    """
    net = Network()
    # Add only "B" and "C" nodes, no "A".
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_link(Link("B", "C", capacity=10))

    with pytest.raises(ValueError, match="No source nodes found matching path 'A'"):
        net.max_flow("A", "C")


def test_max_flow_no_sink():
    """
    If no node in the network matches the sink path, it should raise ValueError.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10))

    with pytest.raises(ValueError, match="No sink nodes found matching path 'C'"):
        net.max_flow("A", "C")
