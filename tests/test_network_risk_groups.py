"""
Tests for risk group management in the network module.

This module contains tests for:
- Risk group creation and hierarchy
- Enabling/disabling risk groups (recursive and non-recursive)
- Multi-membership risk group scenarios
- Risk group effects on nodes and links
"""

from ngraph.network import Link, Network, Node, RiskGroup


class TestRiskGroups:
    """Tests for risk group management."""

    def test_disable_risk_group_nonexistent(self):
        """Test disabling nonexistent risk group does nothing."""
        net = Network()
        net.disable_risk_group("nonexistent_group")  # Should not raise

    def test_enable_risk_group_nonexistent(self):
        """Test enabling nonexistent risk group does nothing."""
        net = Network()
        net.enable_risk_group("nonexistent_group")  # Should not raise

    def test_disable_risk_group_recursive(self):
        """Test disabling a top-level group with recursive=True."""
        net = Network()

        net.add_node(Node("A", risk_groups={"top"}))
        net.add_node(Node("B", risk_groups={"child1"}))
        net.add_node(Node("C", risk_groups={"child2"}))
        link = Link("A", "C", risk_groups={"child2"})
        net.add_link(link)

        net.risk_groups["top"] = RiskGroup(
            "top", children=[RiskGroup("child1"), RiskGroup("child2")]
        )

        # Disable top group recursively
        net.disable_risk_group("top", recursive=True)

        assert net.nodes["A"].disabled is True
        assert net.nodes["B"].disabled is True
        assert net.nodes["C"].disabled is True
        assert net.links[link.id].disabled is True

    def test_disable_risk_group_non_recursive(self):
        """Test disabling a top-level group with recursive=False."""
        net = Network()
        net.add_node(Node("A", risk_groups={"top"}))
        net.add_node(Node("B", risk_groups={"child1"}))
        net.add_node(Node("C", risk_groups={"child2"}))

        net.risk_groups["top"] = RiskGroup(
            "top", children=[RiskGroup("child1"), RiskGroup("child2")]
        )

        net.disable_risk_group("top", recursive=False)

        assert net.nodes["A"].disabled is True
        assert net.nodes["B"].disabled is False
        assert net.nodes["C"].disabled is False

    def test_enable_risk_group_multi_membership(self):
        """Test enabling a risk group when node belongs to multiple groups."""
        net = Network()

        net.add_node(Node("X", risk_groups={"group1", "group2"}))
        net.risk_groups["group1"] = RiskGroup("group1")
        net.risk_groups["group2"] = RiskGroup("group2")

        assert net.nodes["X"].disabled is False

        net.disable_risk_group("group1")
        assert net.nodes["X"].disabled is True

        net.enable_risk_group("group2")
        assert net.nodes["X"].disabled is False

    def test_disable_risk_group_affects_links(self):
        """Test that disabling risk group affects links with that risk group."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))

        link = Link("A", "B", risk_groups={"critical"})
        net.add_link(link)
        net.risk_groups["critical"] = RiskGroup("critical")

        assert net.links[link.id].disabled is False

        net.disable_risk_group("critical")
        assert net.links[link.id].disabled is True

        net.enable_risk_group("critical")
        assert net.links[link.id].disabled is False

    def test_risk_group_hierarchy_deep_nesting(self):
        """Test deeply nested risk group hierarchies."""
        net = Network()
        net.add_node(Node("A", risk_groups={"level1"}))
        net.add_node(Node("B", risk_groups={"level2"}))
        net.add_node(Node("C", risk_groups={"level3"}))

        # Create 3-level hierarchy
        net.risk_groups["level1"] = RiskGroup(
            "level1", children=[RiskGroup("level2", children=[RiskGroup("level3")])]
        )

        # Disable top level recursively
        net.disable_risk_group("level1", recursive=True)

        assert net.nodes["A"].disabled is True
        assert net.nodes["B"].disabled is True
        assert net.nodes["C"].disabled is True

    def test_risk_group_partial_enablement(self):
        """Test partially enabling nested risk groups."""
        net = Network()
        net.add_node(Node("A", risk_groups={"parent"}))
        net.add_node(Node("B", risk_groups={"child1"}))
        net.add_node(Node("C", risk_groups={"child2"}))

        # Register all risk groups in the network's risk_groups dictionary
        net.risk_groups["parent"] = RiskGroup(
            "parent", children=[RiskGroup("child1"), RiskGroup("child2")]
        )
        net.risk_groups["child1"] = RiskGroup("child1")
        net.risk_groups["child2"] = RiskGroup("child2")

        # Disable all
        net.disable_risk_group("parent", recursive=True)
        assert all(node.disabled for node in net.nodes.values())

        # Enable only child1
        net.enable_risk_group("child1")
        assert (
            net.nodes["A"].disabled is True
        )  # parent still disabled (only has "parent" risk group)
        assert (
            net.nodes["B"].disabled is False
        )  # child1 enabled (has "child1" risk group)
        assert net.nodes["C"].disabled is True  # child2 still disabled

    def test_risk_group_mixed_membership(self):
        """Test nodes and links with overlapping risk group memberships."""
        net = Network()
        net.add_node(Node("A", risk_groups={"group1", "group2"}))
        net.add_node(Node("B", risk_groups={"group2", "group3"}))

        link = Link("A", "B", risk_groups={"group1", "group3"})
        net.add_link(link)

        net.risk_groups["group1"] = RiskGroup("group1")
        net.risk_groups["group2"] = RiskGroup("group2")
        net.risk_groups["group3"] = RiskGroup("group3")

        # Initially all enabled
        assert not net.nodes["A"].disabled
        assert not net.nodes["B"].disabled
        assert not net.links[link.id].disabled

        # Disable group1 - affects A and link
        net.disable_risk_group("group1")
        assert net.nodes["A"].disabled is True  # A has group1
        assert net.nodes["B"].disabled is False  # B doesn't have group1
        assert net.links[link.id].disabled is True  # link has group1

        # Disable group2 - affects A and B
        net.disable_risk_group("group2")
        assert net.nodes["A"].disabled is True  # A still disabled (group1)
        assert net.nodes["B"].disabled is True  # B now disabled (group2)
        assert net.links[link.id].disabled is True  # link still disabled (group1)

        # Enable group1 - A should be enabled because it has group1, link should be enabled
        net.enable_risk_group("group1")
        assert (
            net.nodes["A"].disabled is False
        )  # A enabled (has group1 which is now enabled)
        assert net.nodes["B"].disabled is True  # B still disabled (group2)
        assert (
            net.links[link.id].disabled is False
        )  # link enabled (has group1 which is enabled)
