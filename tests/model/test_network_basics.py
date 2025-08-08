"""
Tests for basic network construction, utilities, nodes, and links.

This module contains tests for the fundamental building blocks of the network:
- Utility functions (UUID generation)
- Node creation and management
- Link creation and management
- Basic network construction
- Node/link enabling/disabling
"""

import pytest

from ngraph.model.network import Link, Network, Node, new_base64_uuid


class TestUtilities:
    """Tests for utility functions."""

    def test_new_base64_uuid_length_and_uniqueness(self):
        """Generate two Base64-encoded UUIDs and confirm they are 22 chars and unique."""
        uuid1 = new_base64_uuid()
        uuid2 = new_base64_uuid()

        assert isinstance(uuid1, str)
        assert isinstance(uuid2, str)
        assert "=" not in uuid1
        assert "=" not in uuid2
        assert len(uuid1) == 22
        assert len(uuid2) == 22
        assert uuid1 != uuid2


class TestNodeCreation:
    """Tests for Node creation and attributes."""

    def test_node_creation_default_attrs(self):
        """A new Node with no attrs should have an empty dict for attrs."""
        node = Node("A")
        assert node.name == "A"
        assert node.attrs == {}
        assert node.risk_groups == set()
        assert node.disabled is False

    def test_node_creation_custom_attrs(self):
        """A new Node can be created with custom attributes that are stored as-is."""
        custom_attrs = {"key": "value", "number": 42}
        node = Node("B", attrs=custom_attrs)
        assert node.name == "B"
        assert node.attrs == custom_attrs
        assert node.risk_groups == set()
        assert node.disabled is False


class TestLinkCreation:
    """Tests for Link creation and attributes."""

    def test_link_defaults_and_id_generation(self):
        """A Link without custom parameters should default capacity/cost to 1.0."""
        link = Link("A", "B")

        assert link.capacity == 1.0
        assert link.cost == 1.0
        assert link.attrs == {}
        assert link.risk_groups == set()
        assert link.disabled is False
        assert link.id.startswith("A|B|")
        assert len(link.id) > len("A|B|")

    def test_link_custom_values(self):
        """A Link can be created with custom capacity/cost/attrs."""
        custom_attrs = {"color": "red"}
        link = Link("X", "Y", capacity=2.0, cost=4.0, attrs=custom_attrs)

        assert link.source == "X"
        assert link.target == "Y"
        assert link.capacity == 2.0
        assert link.cost == 4.0
        assert link.attrs == custom_attrs
        assert link.risk_groups == set()
        assert link.disabled is False
        assert link.id.startswith("X|Y|")

    def test_link_id_uniqueness(self):
        """Even if two Links have the same source and target, the auto-generated IDs should differ."""
        link1 = Link("A", "B")
        link2 = Link("A", "B")
        assert link1.id != link2.id


class TestNetworkConstruction:
    """Tests for Network construction and basic operations."""

    @pytest.fixture
    def empty_network(self):
        """Fixture providing an empty network."""
        return Network()

    @pytest.fixture
    def simple_network(self):
        """Fixture providing a simple A->B network."""
        network = Network()
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B"))
        return network

    def test_network_add_node_and_link(self, empty_network):
        """Adding nodes and links to a Network should store them correctly."""
        node_a = Node("A")
        node_b = Node("B")

        empty_network.add_node(node_a)
        empty_network.add_node(node_b)

        assert "A" in empty_network.nodes
        assert "B" in empty_network.nodes

        link = Link("A", "B")
        empty_network.add_link(link)

        assert link.id in empty_network.links
        assert empty_network.links[link.id] is link

    def test_network_add_link_missing_source(self, empty_network):
        """Attempting to add a Link whose source node is not in the Network should raise an error."""
        node_b = Node("B")
        empty_network.add_node(node_b)

        link = Link("A", "B")  # 'A' doesn't exist

        with pytest.raises(ValueError, match="Source node 'A' not found in network."):
            empty_network.add_link(link)

    def test_network_add_link_missing_target(self, empty_network):
        """Attempting to add a Link whose target node is not in the Network should raise an error."""
        node_a = Node("A")
        empty_network.add_node(node_a)

        link = Link("A", "B")  # 'B' doesn't exist
        with pytest.raises(ValueError, match="Target node 'B' not found in network."):
            empty_network.add_link(link)

    def test_network_attrs(self):
        """The Network's 'attrs' dictionary can store arbitrary metadata."""
        network = Network(attrs={"network_type": "test"})
        assert network.attrs["network_type"] == "test"

    def test_add_duplicate_node_raises_valueerror(self, empty_network):
        """Adding a second Node with the same name should raise ValueError."""
        node1 = Node("A", attrs={"data": 1})
        node2 = Node("A", attrs={"data": 2})

        empty_network.add_node(node1)
        with pytest.raises(ValueError, match="Node 'A' already exists in the network."):
            empty_network.add_node(node2)


class TestNodeLinkManagement:
    """Tests for enabling/disabling nodes and links."""

    @pytest.fixture
    def basic_network(self):
        """Fixture providing a basic A->B network."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B")
        net.add_link(link)
        return net, link

    def test_disable_enable_node(self, basic_network):
        """Test disabling and enabling a single node."""
        net, _ = basic_network

        assert net.nodes["A"].disabled is False
        assert net.nodes["B"].disabled is False

        net.disable_node("A")
        assert net.nodes["A"].disabled is True
        assert net.nodes["B"].disabled is False

        net.enable_node("A")
        assert net.nodes["A"].disabled is False

    def test_disable_node_does_not_exist(self):
        """Test that disabling/enabling a non-existent node raises ValueError."""
        net = Network()
        with pytest.raises(ValueError, match="Node 'A' does not exist."):
            net.disable_node("A")

        with pytest.raises(ValueError, match="Node 'B' does not exist."):
            net.enable_node("B")

    def test_disable_enable_link(self, basic_network):
        """Test disabling and enabling a single link."""
        net, link = basic_network

        assert net.links[link.id].disabled is False

        net.disable_link(link.id)
        assert net.links[link.id].disabled is True

        net.enable_link(link.id)
        assert net.links[link.id].disabled is False

    def test_disable_link_does_not_exist(self):
        """Test that disabling/enabling a non-existent link raises ValueError."""
        net = Network()
        with pytest.raises(ValueError, match="Link 'xyz' does not exist."):
            net.disable_link("xyz")
        with pytest.raises(ValueError, match="Link 'xyz' does not exist."):
            net.enable_link("xyz")

    def test_enable_all_disable_all(self, basic_network):
        """Test enable_all and disable_all correctly toggle all nodes and links."""
        net, link = basic_network

        # Everything enabled by default
        assert net.nodes["A"].disabled is False
        assert net.nodes["B"].disabled is False
        assert net.links[link.id].disabled is False

        # Disable all
        net.disable_all()
        assert net.nodes["A"].disabled is True
        assert net.nodes["B"].disabled is True
        assert net.links[link.id].disabled is True

        # Enable all
        net.enable_all()
        assert net.nodes["A"].disabled is False
        assert net.nodes["B"].disabled is False
        assert net.links[link.id].disabled is False


class TestLinkUtilities:
    """Minimal link utility tests; full coverage lives in tests/model/test_selection.py."""

    def test_get_links_between(self):
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        link_ab1 = Link("A", "B")
        link_ab2 = Link("A", "B")
        link_bc = Link("B", "C")
        net.add_link(link_ab1)
        net.add_link(link_ab2)
        net.add_link(link_bc)

        ab_links = net.get_links_between("A", "B")
        assert set(ab_links) == {link_ab1.id, link_ab2.id}
