import pytest
from ngraph.network import Network, Node, Link, new_base64_uuid


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
    have an empty attrs dict, and generate a unique ID like 'A-B-<uuid>'.
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
    With the new behavior, adding a second Node with the same name should raise ValueError
    rather than overwriting the existing node.
    """
    network = Network()
    node1 = Node("A", attrs={"data": 1})
    node2 = Node("A", attrs={"data": 2})

    network.add_node(node1)
    with pytest.raises(ValueError, match="Node 'A' already exists in the network."):
        network.add_node(node2)
