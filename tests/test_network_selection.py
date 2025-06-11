"""
Tests for node selection and pattern matching in the network module.

This module contains tests for:
- Node selection by path patterns (exact, prefix, wildcard, regex)
- Link finding by source/target patterns
- Network traversal and search operations
"""

import pytest

from ngraph.network import Link, Network, Node


class TestNodeSelection:
    """Tests for node selection by path patterns."""

    @pytest.fixture
    def complex_network(self):
        """Fixture providing a network with hierarchical node names."""
        net = Network()
        net.add_node(Node("SEA/spine/myspine-1"))
        net.add_node(Node("SEA/spine/myspine-2"))
        net.add_node(Node("SEA/leaf1/leaf-1"))
        net.add_node(Node("SEA/leaf1/leaf-2"))
        net.add_node(Node("SEA/leaf2/leaf-1"))
        net.add_node(Node("SEA/leaf2/leaf-2"))
        net.add_node(Node("SEA-other"))
        net.add_node(Node("SFO"))
        return net

    def test_select_node_groups_exact_match(self, complex_network):
        """Test exact match node selection."""
        node_groups = complex_network.select_node_groups_by_path("SFO")
        assert len(node_groups) == 1
        nodes = node_groups["SFO"]
        assert len(nodes) == 1
        assert nodes[0].name == "SFO"

    def test_select_node_groups_prefix_match(self, complex_network):
        """Test prefix match node selection."""
        node_groups = complex_network.select_node_groups_by_path("SEA/spine")
        assert len(node_groups) == 1
        nodes = node_groups["SEA/spine"]
        assert len(nodes) == 2
        found = {n.name for n in nodes}
        assert found == {"SEA/spine/myspine-1", "SEA/spine/myspine-2"}

    def test_select_node_groups_wildcard_match(self, complex_network):
        """Test wildcard match node selection."""
        node_groups = complex_network.select_node_groups_by_path("SEA/leaf*")
        assert len(node_groups) == 1
        nodes = node_groups["SEA/leaf*"]
        assert len(nodes) == 4
        found = {n.name for n in nodes}
        assert found == {
            "SEA/leaf1/leaf-1",
            "SEA/leaf1/leaf-2",
            "SEA/leaf2/leaf-1",
            "SEA/leaf2/leaf-2",
        }

    def test_select_node_groups_capture_groups(self, complex_network):
        """Test regex capture groups in node selection."""
        node_groups = complex_network.select_node_groups_by_path("(SEA/leaf\\d)")
        assert len(node_groups) == 2

        nodes = node_groups["SEA/leaf1"]
        assert len(nodes) == 2
        found = {n.name for n in nodes}
        assert found == {"SEA/leaf1/leaf-1", "SEA/leaf1/leaf-2"}

        nodes = node_groups["SEA/leaf2"]
        assert len(nodes) == 2
        found = {n.name for n in nodes}
        assert found == {"SEA/leaf2/leaf-1", "SEA/leaf2/leaf-2"}

    def test_select_node_groups_no_matches(self, complex_network):
        """Test node selection when pattern matches no nodes."""
        node_groups = complex_network.select_node_groups_by_path("NYC/.*")
        assert len(node_groups) == 0

    def test_select_node_groups_complex_regex(self, complex_network):
        """Test complex regex patterns in node selection."""
        # Match all SEA nodes except SEA-other
        node_groups = complex_network.select_node_groups_by_path("SEA/.*")
        assert len(node_groups) == 1
        nodes = node_groups["SEA/.*"]
        assert len(nodes) == 6  # All except SEA-other and SFO

    def test_select_node_groups_multiple_capture_groups(self, complex_network):
        """Test multiple capture groups in regex patterns."""
        # Capture spine/leaf type and number
        pattern = "SEA/(spine|leaf\\d)/.*-(\\d)"
        node_groups = complex_network.select_node_groups_by_path(pattern)

        # Should have groups for each combination found
        assert len(node_groups) >= 2


class TestLinkUtilities:
    """Tests for link utility methods."""

    def test_get_links_between(self):
        """Test retrieving all links that connect a specific source to a target."""
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

        # Two links from A->B
        ab_links = net.get_links_between("A", "B")
        assert len(ab_links) == 2
        assert set(ab_links) == {link_ab1.id, link_ab2.id}

        # One link from B->C
        bc_links = net.get_links_between("B", "C")
        assert len(bc_links) == 1
        assert bc_links[0] == link_bc.id

        # None from B->A
        ba_links = net.get_links_between("B", "A")
        assert ba_links == []

    def test_find_links(self):
        """Test finding links by optional source_regex, target_regex."""
        net = Network()
        net.add_node(Node("srcA"))
        net.add_node(Node("srcB"))
        net.add_node(Node("C"))
        link_a_c = Link("srcA", "C")
        link_b_c = Link("srcB", "C")
        net.add_link(link_a_c)
        net.add_link(link_b_c)

        # No filter => returns all
        all_links = net.find_links()
        assert len(all_links) == 2
        assert set(link.id for link in all_links) == {link_a_c.id, link_b_c.id}

        # Filter by source regex
        src_a_links = net.find_links(source_regex="srcA")
        assert len(src_a_links) == 1
        assert src_a_links[0].id == link_a_c.id

        # Filter by target regex
        to_c_links = net.find_links(target_regex="C")
        assert len(to_c_links) == 2
        assert set(link.id for link in to_c_links) == {link_a_c.id, link_b_c.id}

        # Filter by both source and target
        specific_links = net.find_links(source_regex="srcB", target_regex="C")
        assert len(specific_links) == 1
        assert specific_links[0].id == link_b_c.id

        # Filter that matches nothing
        no_links = net.find_links(source_regex="nonexistent")
        assert len(no_links) == 0

    def test_find_links_any_direction(self):
        """Test finding links in any direction (bidirectional search)."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        link_ab = Link("A", "B")
        link_bc = Link("B", "C")
        link_ca = Link("C", "A")
        net.add_link(link_ab)
        net.add_link(link_bc)
        net.add_link(link_ca)

        # Find links involving B in any direction
        b_links = net.find_links(source_regex="B", any_direction=True)
        assert len(b_links) == 2  # A->B and B->C
        found_ids = {link.id for link in b_links}
        assert found_ids == {link_ab.id, link_bc.id}

        # Find links involving A in any direction
        a_links = net.find_links(source_regex="A", any_direction=True)
        assert len(a_links) == 2  # A->B and C->A
        found_ids = {link.id for link in a_links}
        assert found_ids == {link_ab.id, link_ca.id}

    def test_find_links_with_disabled_links(self):
        """Test that find_links includes disabled links (no filtering by default)."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))

        link1 = Link("A", "B")
        link2 = Link("A", "B")
        net.add_link(link1)
        net.add_link(link2)

        # Initially both links found
        links = net.find_links()
        assert len(links) == 2

        # Disable one link - find_links still returns both (no filtering)
        net.disable_link(link1.id)
        links = net.find_links()
        assert len(links) == 2  # Still finds both links

        # Verify one is disabled and one is not
        found_states = [link.disabled for link in links]
        assert True in found_states and False in found_states

    def test_find_links_regex_patterns(self):
        """Test find_links with various regex patterns."""
        net = Network()
        nodes = ["router-1", "router-2", "switch-1", "switch-2"]
        for node in nodes:
            net.add_node(Node(node))

        # Create links between all routers and switches
        links = []
        for router in ["router-1", "router-2"]:
            for switch in ["switch-1", "switch-2"]:
                link = Link(router, switch)
                net.add_link(link)
                links.append(link)

        # Find all links from routers
        router_links = net.find_links(source_regex="router-.*")
        assert len(router_links) == 4

        # Find all links to switches
        switch_links = net.find_links(target_regex="switch-.*")
        assert len(switch_links) == 4

        # Find specific router to specific switch
        specific = net.find_links(source_regex="router-1", target_regex="switch-2")
        assert len(specific) == 1
