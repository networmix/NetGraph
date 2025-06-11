"""
Tests for integration scenarios and complex network operations.

This module contains tests for:
- Complex multi-component network scenarios
- Integration between different network features
- End-to-end workflow testing
- Performance and scalability edge cases
"""

import pytest

from ngraph.network import Link, Network, Node, RiskGroup


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

    def test_end_to_end_flow_analysis(self, diamond_network):
        """Test complete flow analysis workflow on diamond network."""
        # Basic max flow
        flow = diamond_network.max_flow("A", "D")
        assert flow[("A", "D")] == 2.0

        # Saturated edges analysis returns dict format
        saturated = diamond_network.saturated_edges("A", "D")
        assert isinstance(saturated, dict)
        assert len(saturated) > 0

        # Sensitivity analysis
        sensitivity = diamond_network.sensitivity_analysis("A", "D")
        assert len(sensitivity) > 0

        # All methods should work together consistently
        assert isinstance(flow, dict)
        assert isinstance(saturated, dict)  # dict format, not list
        assert isinstance(sensitivity, dict)

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
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 1.0

        # Flow should be 0 when critical nodes are disabled
        net.disable_risk_group("critical")
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 0.0

        # Flow should resume when risk group is re-enabled
        net.enable_risk_group("critical")
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 1.0

    def test_complex_network_construction(self):
        """Test building and analyzing a complex multi-tier network."""
        net = Network()

        # Create a 3-tier network: sources -> transit -> sinks
        sources = ["src-1", "src-2", "src-3"]
        transit = ["transit-1", "transit-2"]
        sinks = ["sink-1", "sink-2"]

        # Add all nodes
        for node in sources + transit + sinks:
            net.add_node(Node(node))

        # Connect sources to transit (full mesh)
        for src in sources:
            for t in transit:
                net.add_link(Link(src, t, capacity=2.0))

        # Connect transit to sinks (full mesh)
        for t in transit:
            for sink in sinks:
                net.add_link(Link(t, sink, capacity=3.0))

        # Analyze flow characteristics
        total_flow = 0
        for src in sources:
            for sink in sinks:
                flow = net.max_flow(src, sink)
                total_flow += flow[(src, sink)]

        # Should have meaningful flow through the network
        assert total_flow > 0

        # Network should have correct structure
        assert len(net.nodes) == 7
        assert len(net.links) == 10  # 3*2 + 2*2

    def test_disabled_node_propagation(self):
        """Test how disabled nodes affect complex network operations."""
        net = Network()

        # Create linear chain: A->B->C->D
        nodes = ["A", "B", "C", "D"]
        for node in nodes:
            net.add_node(Node(node))

        for i in range(len(nodes) - 1):
            net.add_link(Link(nodes[i], nodes[i + 1]))

        # Initially flow should exist
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 1.0

        # Disable middle node - should break flow
        net.disable_node("B")
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 0.0

        # Re-enable, flow should resume
        net.enable_node("B")
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 1.0

        # Disable different middle node
        net.disable_node("C")
        flow = net.max_flow("A", "D")
        assert flow[("A", "D")] == 0.0

    def test_network_with_mixed_capacities(self):
        """Test analysis of networks with varying link capacities."""
        net = Network()

        nodes = ["A", "B", "C", "D", "E"]
        for node in nodes:
            net.add_node(Node(node))

        # Create network with bottlenecks
        capacities = [
            ("A", "B", 10.0),
            ("A", "C", 5.0),
            ("B", "D", 2.0),  # bottleneck
            ("C", "D", 8.0),
            ("C", "E", 3.0),
            ("D", "E", 15.0),
        ]

        for src, tgt, cap in capacities:
            net.add_link(Link(src, tgt, capacity=cap))

        # Max flow should be limited by bottlenecks
        flow_ad = net.max_flow("A", "D")
        net.max_flow("A", "E")

        # A->D gets flow through multiple paths: A->B->D (2.0) + A->C->D (5.0) = 7.0
        # But limited by B->D capacity and C->D capacity
        assert flow_ad[("A", "D")] == 7.0  # A->B->D (2.0) + A->C->D (5.0) = 7.0

        # Test that saturated edges identify bottlenecks
        saturated = net.saturated_edges("A", "E")
        assert len(saturated) > 0

    def test_large_network_performance(self):
        """Test performance characteristics with larger networks."""
        net = Network()

        # Create a larger network (grid-like)
        size = 10
        for i in range(size):
            for j in range(size):
                net.add_node(Node(f"node-{i}-{j}"))

        # Add horizontal and vertical connections
        for i in range(size):
            for j in range(size - 1):
                # Horizontal links
                net.add_link(Link(f"node-{i}-{j}", f"node-{i}-{j + 1}"))
                # Vertical links
                net.add_link(Link(f"node-{j}-{i}", f"node-{j + 1}-{i}"))

        # Should be able to handle this size efficiently
        assert len(net.nodes) == size * size
        assert len(net.links) == 2 * size * (size - 1)

        # Basic operations should still work
        flow = net.max_flow("node-0-0", "node-9-9")
        assert len(flow) == 1
        assert flow[("node-0-0", "node-9-9")] > 0

    def test_network_modification_during_analysis(self):
        """Test network state consistency during complex operations."""
        net = Network()

        # Build initial network
        for node in ["A", "B", "C"]:
            net.add_node(Node(node))

        link_ab = Link("A", "B")
        link_bc = Link("B", "C")
        net.add_link(link_ab)
        net.add_link(link_bc)

        # Get initial flow
        initial_flow = net.max_flow("A", "C")
        assert initial_flow[("A", "C")] == 1.0

        # Modify network and verify consistency
        net.add_node(Node("D"))
        net.add_link(Link("A", "D"))
        net.add_link(Link("D", "C"))

        # Flow should increase with additional path
        new_flow = net.max_flow("A", "C")
        assert new_flow[("A", "C")] >= initial_flow[("A", "C")]

        # Network should maintain internal consistency
        assert len(net.nodes) == 4
        assert len(net.links) == 4

    def test_comprehensive_error_handling(self):
        """Test error handling in complex scenarios."""
        net = Network()

        # Empty network operations should raise errors for non-matching patterns
        with pytest.raises(ValueError, match="No source nodes found matching"):
            net.max_flow("nonexistent", "also_nonexistent")

        with pytest.raises(ValueError, match="No source nodes found matching"):
            net.saturated_edges("none", "zero")

        with pytest.raises(ValueError, match="No source nodes found matching"):
            net.sensitivity_analysis("void", "null")

        # Single node operations
        net.add_node(Node("lonely"))
        assert net.max_flow("lonely", "lonely") == {("lonely", "lonely"): 0}

        # Disconnected network
        net.add_node(Node("isolated"))
        assert net.max_flow("lonely", "isolated") == {("lonely", "isolated"): 0}
