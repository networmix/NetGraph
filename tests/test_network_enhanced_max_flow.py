"""Tests for the new enhanced max_flow methods."""

import pytest

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.types import FlowSummary
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.network import Link, Network, Node


class TestEnhancedMaxFlowMethods:
    """Test the new max_flow_with_summary, max_flow_with_graph, and max_flow_detailed methods."""

    def test_max_flow_with_summary_basic(self):
        """Test max_flow_with_summary returns correct types and values."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=3))

        result = net.max_flow_with_summary("A", "C")

        # Check return type and structure
        assert isinstance(result, dict)
        assert len(result) == 1

        key = ("A", "C")
        assert key in result

        flow_val, summary = result[key]
        assert isinstance(flow_val, (int, float))
        assert isinstance(summary, FlowSummary)
        assert flow_val == 3.0
        assert summary.total_flow == 3.0
        assert len(summary.edge_flow) > 0
        assert len(summary.residual_cap) > 0

    def test_max_flow_with_graph_basic(self):
        """Test max_flow_with_graph returns correct types and values."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=5))

        result = net.max_flow_with_graph("A", "B")

        # Check return type and structure
        assert isinstance(result, dict)
        assert len(result) == 1

        key = ("A", "B")
        assert key in result

        flow_val, flow_graph = result[key]
        assert isinstance(flow_val, (int, float))
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert flow_val == 5.0
        assert flow_graph.number_of_nodes() >= 2

    def test_max_flow_detailed_basic(self):
        """Test max_flow_detailed returns correct types and values."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        result = net.max_flow_detailed("A", "B")

        # Check return type and structure
        assert isinstance(result, dict)
        assert len(result) == 1

        key = ("A", "B")
        assert key in result

        flow_val, summary, flow_graph = result[key]
        assert isinstance(flow_val, (int, float))
        assert isinstance(summary, FlowSummary)
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert flow_val == 10.0
        assert summary.total_flow == 10.0

    def test_consistency_with_original_max_flow(self):
        """Test that new methods return consistent flow values with original method."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=8))
        net.add_link(Link("B", "C", capacity=6))

        # Get results from all methods
        original = net.max_flow("A", "C")
        with_summary = net.max_flow_with_summary("A", "C")
        with_graph = net.max_flow_with_graph("A", "C")
        detailed = net.max_flow_detailed("A", "C")

        key = ("A", "C")
        original_flow = original[key]
        summary_flow = with_summary[key][0]
        graph_flow = with_graph[key][0]
        detailed_flow = detailed[key][0]

        # All should return the same flow value
        assert original_flow == summary_flow == graph_flow == detailed_flow == 6.0

    def test_flow_placement_parameter(self):
        """Test that flow_placement parameter works with new methods."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        # Create parallel paths
        net.add_link(Link("A", "B", capacity=5, cost=1))
        net.add_link(Link("A", "C", capacity=3, cost=1))
        net.add_link(Link("B", "C", capacity=8, cost=1))

        # Test with different flow placement strategies
        for placement in [FlowPlacement.PROPORTIONAL, FlowPlacement.EQUAL_BALANCED]:
            result = net.max_flow_with_summary("A", "C", flow_placement=placement)
            flow_val, summary = result[("A", "C")]

            assert isinstance(flow_val, (int, float))
            assert flow_val > 0
            assert summary.total_flow == flow_val

    def test_shortest_path_parameter(self):
        """Test that shortest_path parameter works with new methods."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        # Short path A->B->D and longer path A->C->D
        net.add_link(Link("A", "B", capacity=5, cost=1))
        net.add_link(Link("B", "D", capacity=3, cost=1))
        net.add_link(Link("A", "C", capacity=4, cost=2))
        net.add_link(Link("C", "D", capacity=6, cost=2))

        # Test with shortest_path=True
        result = net.max_flow_with_summary("A", "D", shortest_path=True)
        flow_val, summary = result[("A", "D")]

        assert isinstance(flow_val, (int, float))
        assert flow_val > 0
        assert summary.total_flow == flow_val

    def test_pairwise_mode(self):
        """Test pairwise mode with new methods."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))
        net.add_link(Link("A", "C", capacity=5))
        net.add_link(Link("B", "D", capacity=3))

        result = net.max_flow_with_summary("^([AB])$", "^([CD])$", mode="pairwise")

        # Should have 4 combinations: A->C, A->D, B->C, B->D
        assert len(result) == 4

        # Check specific pairs
        assert ("A", "C") in result
        assert ("A", "D") in result
        assert ("B", "C") in result
        assert ("B", "D") in result

        # A->C should have flow, B->D should have flow, others should be 0
        assert result[("A", "C")][0] == 5.0
        assert result[("B", "D")][0] == 3.0
        assert result[("A", "D")][0] == 0.0
        assert result[("B", "C")][0] == 0.0

    def test_combine_mode(self):
        """Test combine mode with new methods."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "C", capacity=5))
        net.add_link(Link("B", "C", capacity=3))

        result = net.max_flow_with_summary("^([AB])$", "C", mode="combine")

        # Should have 1 combined result
        assert len(result) == 1

        key = ("A|B", "C")
        assert key in result

        flow_val, summary = result[key]
        assert flow_val == 8.0  # Both A and B can send to C

    def test_empty_results_handling(self):
        """Test handling of cases with no flow."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        # No link between A and B

        result = net.max_flow_with_summary("A", "B")
        flow_val, summary = result[("A", "B")]

        assert flow_val == 0.0
        assert summary.total_flow == 0.0
        assert len(summary.min_cut) == 0

    def test_disabled_nodes_handling(self):
        """Test handling of disabled nodes."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=3))

        result = net.max_flow_with_summary("A", "C")
        flow_val, summary = result[("A", "C")]

        # Should be 0 because B is disabled
        assert flow_val == 0.0
        assert summary.total_flow == 0.0

    def test_error_cases(self):
        """Test error handling for invalid inputs."""
        net = Network()
        net.add_node(Node("A"))

        # Test invalid mode
        with pytest.raises(ValueError, match="Invalid mode"):
            net.max_flow_with_summary("A", "A", mode="invalid")

        # Test no matching sources
        with pytest.raises(ValueError, match="No source nodes found"):
            net.max_flow_with_summary("X", "A")

        # Test no matching sinks
        with pytest.raises(ValueError, match="No sink nodes found"):
            net.max_flow_with_summary("A", "X")

    def test_min_cut_identification(self):
        """Test that min-cut edges are correctly identified."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=10))
        net.add_link(Link("B", "C", capacity=5))  # This should be the bottleneck

        result = net.max_flow_with_summary("A", "C")
        flow_val, summary = result[("A", "C")]

        assert flow_val == 5.0
        assert len(summary.min_cut) == 1

        # The min-cut should include the B->C edge
        min_cut_edges = summary.min_cut
        assert any(u == "B" and v == "C" for u, v, k in min_cut_edges)

    def test_reachability_analysis(self):
        """Test that reachable nodes are correctly identified."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))
        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=3))
        # D is isolated

        result = net.max_flow_with_summary("A", "C")
        flow_val, summary = result[("A", "C")]

        # A and B should be reachable from source, C might be reachable depending on flow
        assert "A" in summary.reachable
        # D should not be reachable since it's isolated
        assert "D" not in summary.reachable
