"""
Tests for graph conversion and operations.

This module contains tests for:
- Converting Network to StrictMultiDiGraph
- Graph operations with enabled/disabled nodes and links
- Reverse edge handling in graph conversion
"""

import pytest

from ngraph.network import Link, Network, Node


class TestGraphConversion:
    """Tests for converting Network to StrictMultiDiGraph."""

    @pytest.fixture
    def linear_network(self):
        """Fixture providing a linear A->B->C network."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        link_ab = Link("A", "B")
        link_bc = Link("B", "C")
        net.add_link(link_ab)
        net.add_link(link_bc)
        return net, link_ab, link_bc

    def test_to_strict_multidigraph_add_reverse_true(self, linear_network):
        """Test graph conversion with reverse edges enabled."""
        net, link_ab, link_bc = linear_network
        graph = net.to_strict_multidigraph(add_reverse=True)

        assert set(graph.nodes()) == {"A", "B", "C"}

        edges = list(graph.edges(keys=True))
        forward_keys = {link_ab.id, link_bc.id}
        reverse_keys = {f"{link_ab.id}_rev", f"{link_bc.id}_rev"}
        all_keys = forward_keys.union(reverse_keys)
        found_keys = {e[2] for e in edges}

        assert found_keys == all_keys

    def test_to_strict_multidigraph_add_reverse_false(self):
        """Test graph conversion with reverse edges disabled."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))

        link_ab = Link("A", "B")
        net.add_link(link_ab)

        graph = net.to_strict_multidigraph(add_reverse=False)

        assert set(graph.nodes()) == {"A", "B"}

        edges = list(graph.edges(keys=True))
        assert len(edges) == 1
        assert edges[0][0] == "A"
        assert edges[0][1] == "B"
        assert edges[0][2] == link_ab.id

    def test_to_strict_multidigraph_excludes_disabled(self):
        """Test that disabled nodes or links are excluded from graph conversion."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link_ab = Link("A", "B")
        net.add_link(link_ab)

        # Disable node A
        net.disable_node("A")
        graph = net.to_strict_multidigraph()
        assert "A" not in graph.nodes
        assert "B" in graph.nodes
        assert len(graph.edges()) == 0

        # Enable node A, disable link
        net.enable_all()
        net.disable_link(link_ab.id)
        graph = net.to_strict_multidigraph()
        assert "A" in graph.nodes
        assert "B" in graph.nodes
        assert len(graph.edges()) == 0

    def test_to_strict_multidigraph_with_disabled_target_node(self):
        """Test graph conversion when target node is disabled."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        link_ab = Link("A", "B")
        link_bc = Link("B", "C")
        net.add_link(link_ab)
        net.add_link(link_bc)

        # Disable target node B
        net.disable_node("B")
        graph = net.to_strict_multidigraph()

        # Only nodes A and C should be in graph, no edges
        assert set(graph.nodes()) == {"A", "C"}
        assert len(graph.edges()) == 0

    def test_to_strict_multidigraph_empty_network(self):
        """Test graph conversion with empty network."""
        net = Network()
        graph = net.to_strict_multidigraph()

        assert len(graph.nodes()) == 0
        assert len(graph.edges()) == 0

    def test_to_strict_multidigraph_isolated_nodes(self):
        """Test graph conversion with isolated nodes (no links)."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        graph = net.to_strict_multidigraph()

        assert set(graph.nodes()) == {"A", "B", "C"}
        assert len(graph.edges()) == 0
