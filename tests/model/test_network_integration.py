"""Tests for integration scenarios and complex network operations.

This module contains tests for:
- Complex multi-component network scenarios
- Integration between different network features
- End-to-end workflow testing
- Performance and scalability edge cases
"""

import pytest

from ngraph import Link, Mode, Network, Node, RiskGroup, analyze


class TestNetworkIntegration:
    """Tests for complex integration scenarios."""

    @pytest.fixture
    def diamond_network(self):
        """Fixture providing a diamond-shaped network A->B,C->D."""
        net = Network()
        for node_name in ["A", "B", "C", "D"]:
            net.add_node(Node(node_name))

        net.add_link(Link("A", "B"))
        net.add_link(Link("A", "C"))
        net.add_link(Link("B", "D"))
        net.add_link(Link("C", "D"))
        return net

    def test_risk_group_with_flow_analysis(self):
        """Test integration of risk groups with flow analysis."""
        net = Network()
        nodes = ["A", "B", "C", "D"]
        for node in nodes:
            net.add_node(Node(node, risk_groups={"critical"}))

        net.add_link(Link("A", "B"))
        net.add_link(Link("B", "C"))
        net.add_link(Link("C", "D"))

        net.risk_groups["critical"] = RiskGroup("critical")

        # Flow should work normally when risk group is enabled
        flow = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)
        assert flow[("^A$", "^D$")] == 1.0

        # No flow possible when all nodes are disabled - raises error
        net.disable_risk_group("critical")
        with pytest.raises(ValueError, match="No source nodes found"):
            analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)

        # Flow should resume when risk group is re-enabled
        net.enable_risk_group("critical")
        flow = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)
        assert flow[("^A$", "^D$")] == 1.0
