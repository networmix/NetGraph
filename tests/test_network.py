import pytest
from ngraph.network import (
    Network,
    Node,
    Link,
    new_base64_uuid
)


def test_new_base64_uuid_length_and_uniqueness():
    # Generate two Base64-encoded UUIDs
    uuid1 = new_base64_uuid()
    uuid2 = new_base64_uuid()
    
    # They should be strings without any padding characters
    assert isinstance(uuid1, str)
    assert isinstance(uuid2, str)
    assert '=' not in uuid1
    assert '=' not in uuid2
    
    # They are typically 22 characters long (Base64 without padding)
    assert len(uuid1) == 22
    assert len(uuid2) == 22
    
    # The two generated UUIDs should be unique
    assert uuid1 != uuid2

def test_node_creation_default_attrs():
    # Create a Node with default attributes
    node = Node("A")
    assert node.name == "A"
    assert node.attrs == {}

def test_node_creation_custom_attrs():
    # Create a Node with custom attributes
    custom_attrs = {"key": "value", "number": 42}
    node = Node("B", attrs=custom_attrs)
    assert node.name == "B"
    assert node.attrs == custom_attrs

def test_link_defaults_and_id_generation():
    # Create a Link; __post_init__ should auto-generate the id.
    link = Link("A", "B")
    
    # Check default parameters are set correctly.
    assert link.capacity == 1.0
    assert link.latency == 1.0
    assert link.cost == 1.0
    assert link.attrs == {}
    
    # Verify the link ID is correctly formatted and starts with "A-B-"
    assert link.id.startswith("A-B-")
    # Ensure there is a random UUID part appended after the prefix
    assert len(link.id) > len("A-B-")

def test_link_custom_values():
    # Create a Link with custom values
    custom_attrs = {"color": "red"}
    link = Link("X", "Y", capacity=2.0, latency=3.0, cost=4.0, attrs=custom_attrs)
    
    assert link.source == "X"
    assert link.target == "Y"
    assert link.capacity == 2.0
    assert link.latency == 3.0
    assert link.cost == 4.0
    assert link.attrs == custom_attrs
    # Check that the ID has the proper format
    assert link.id.startswith("X-Y-")

def test_link_id_uniqueness():
    # Two links between the same nodes should have different IDs.
    link1 = Link("A", "B")
    link2 = Link("A", "B")
    assert link1.id != link2.id

def test_network_add_node_and_link():
    # Create a network and add two nodes
    network = Network()
    node_a = Node("A")
    node_b = Node("B")
    network.add_node(node_a)
    network.add_node(node_b)
    
    # The nodes should be present in the network
    assert "A" in network.nodes
    assert "B" in network.nodes
    
    # Create a link between the nodes and add it to the network
    link = Link("A", "B")
    network.add_link(link)
    
    # Check that the link is stored in the network using its auto-generated id.
    assert link.id in network.links
    # Verify that the stored link is the same object
    assert network.links[link.id] is link

def test_network_add_link_missing_source():
    # Create a network with only the target node
    network = Network()
    node_b = Node("B")
    network.add_node(node_b)
    
    # Try to add a link whose source node does not exist.
    link = Link("A", "B")
    with pytest.raises(ValueError, match="Source node 'A' not found in network."):
        network.add_link(link)

def test_network_add_link_missing_target():
    # Create a network with only the source node
    network = Network()
    node_a = Node("A")
    network.add_node(node_a)
    
    # Try to add a link whose target node does not exist.
    link = Link("A", "B")
    with pytest.raises(ValueError, match="Target node 'B' not found in network."):
        network.add_link(link)

def test_network_attrs():
    # Test that extra network metadata can be stored in attrs.
    network = Network(attrs={"network_type": "test"})
    assert network.attrs["network_type"] == "test"

def test_duplicate_node_overwrite():
    # When adding nodes with the same name, the latter should overwrite the former.
    network = Network()
    node1 = Node("A", attrs={"data": 1})
    node2 = Node("A", attrs={"data": 2})
    
    network.add_node(node1)
    network.add_node(node2)  # This should overwrite node1
    assert network.nodes["A"].attrs["data"] == 2
