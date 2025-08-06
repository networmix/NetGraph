"""Tests for max flow algorithm edge cases and error conditions."""

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.lib.algorithms.max_flow import calc_max_flow
from ngraph.lib.graph import StrictMultiDiGraph


class TestMaxFlowEdgeCases:
    """Test edge cases and error conditions for max flow algorithm."""

    def test_self_loop_zero_flow(self):
        """Test that flow from a node to itself is always zero."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")

        # Self-loop should always return 0 flow
        flow = calc_max_flow(graph, "A", "A")
        assert flow == 0.0

    def test_disconnected_nodes_zero_flow(self):
        """Test flow between disconnected nodes."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        # No edges between A and B

        flow = calc_max_flow(graph, "A", "B")
        assert flow == 0.0

    def test_zero_capacity_edge(self):
        """Test flow through zero-capacity edge."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", capacity=0.0, cost=1)

        flow = calc_max_flow(graph, "A", "B")
        assert flow == 0.0

    def test_very_small_capacity_precision(self):
        """Test flow with very small capacity values near MIN_CAP threshold."""
        from ngraph.lib.algorithms.base import MIN_CAP

        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")

        # Test capacity slightly above MIN_CAP
        graph.add_edge("A", "B", capacity=MIN_CAP * 2, cost=1)
        flow = calc_max_flow(graph, "A", "B")
        assert flow == MIN_CAP * 2

        # Test capacity at MIN_CAP threshold - get the actual edge key
        edge_key = list(graph.edges("A", keys=True))[0][2]  # Get the actual key
        graph.edges["A", "B", edge_key]["capacity"] = MIN_CAP
        flow = calc_max_flow(graph, "A", "B")
        assert flow == MIN_CAP

    def test_parallel_edges_flow_distribution(self):
        """Test flow distribution across parallel edges with different capacities."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")

        # Add parallel edges with different capacities
        graph.add_edge("A", "B", capacity=10.0, cost=1)
        graph.add_edge("A", "B", capacity=5.0, cost=1)
        graph.add_edge("A", "B", capacity=15.0, cost=1)

        flow = calc_max_flow(graph, "A", "B")
        assert flow == 30.0  # Total capacity

    def test_flow_placement_strategies(self):
        """Test different flow placement strategies."""
        graph = StrictMultiDiGraph()
        graph.add_nodes_from(["A", "B", "C"])

        # Create two parallel paths with equal cost
        graph.add_edge("A", "B", capacity=10.0, cost=1)
        graph.add_edge("B", "C", capacity=8.0, cost=1)
        graph.add_edge("A", "C", capacity=5.0, cost=2)  # Alternative path

        # Test proportional placement
        flow_prop = calc_max_flow(
            graph, "A", "C", flow_placement=FlowPlacement.PROPORTIONAL
        )

        # Test equal balanced placement
        flow_balanced = calc_max_flow(
            graph, "A", "C", flow_placement=FlowPlacement.EQUAL_BALANCED
        )

        # Both should find total max flow (8.0 through A→B→C + 5.0 through A→C = 13.0)
        assert flow_prop == 13.0
        assert flow_balanced == 13.0

    def test_invalid_nodes(self):
        """Test behavior with non-existent nodes."""
        import pytest

        graph = StrictMultiDiGraph()
        graph.add_node("A")

        # Source node doesn't exist - should raise KeyError
        with pytest.raises(
            KeyError, match="Source node 'NonExistent' is not in the graph"
        ):
            calc_max_flow(graph, "NonExistent", "A")

        # Destination node doesn't exist - should raise ValueError
        with pytest.raises(
            ValueError,
            match="Source node A or destination node NonExistent not found in the graph",
        ):
            calc_max_flow(graph, "A", "NonExistent")

    def test_shortest_path_mode(self):
        """Test shortest path mode (single iteration)."""
        graph = StrictMultiDiGraph()
        graph.add_nodes_from(["A", "B", "C", "D"])

        # Create multiple paths with different costs
        graph.add_edge("A", "B", capacity=10.0, cost=1)
        graph.add_edge("B", "D", capacity=10.0, cost=1)
        graph.add_edge("A", "C", capacity=10.0, cost=2)
        graph.add_edge("C", "D", capacity=10.0, cost=2)

        # shortest_path=True should use only one path
        flow = calc_max_flow(graph, "A", "D", shortest_path=True)
        assert flow <= 10.0  # Should use single path only

        # Normal mode should use both paths potentially
        flow_normal = calc_max_flow(graph, "A", "D", shortest_path=False)
        assert flow_normal >= flow

    def test_complex_bottleneck_network(self):
        """Test flow in a network with multiple potential bottlenecks."""
        graph = StrictMultiDiGraph()
        graph.add_nodes_from(["S", "A", "B", "C", "T"])

        # Diamond topology with bottlenecks
        graph.add_edge("S", "A", capacity=20.0, cost=1)
        graph.add_edge("S", "B", capacity=20.0, cost=1)
        graph.add_edge("A", "C", capacity=5.0, cost=1)  # Bottleneck
        graph.add_edge("B", "C", capacity=15.0, cost=1)
        graph.add_edge("C", "T", capacity=12.0, cost=1)  # Another bottleneck

        flow = calc_max_flow(graph, "S", "T")
        # Should be limited by the C->T bottleneck (12.0)
        assert flow == 12.0


class TestFlowSummaryAnalytics:
    """Test flow summary analytics and detailed results."""

    def test_flow_summary_basic(self):
        """Test basic flow summary information."""
        graph = StrictMultiDiGraph()
        graph.add_nodes_from(["A", "B", "C"])
        graph.add_edge("A", "B", capacity=10.0, cost=1)
        graph.add_edge("B", "C", capacity=5.0, cost=1)

        flow, summary = calc_max_flow(graph, "A", "C", return_summary=True)

        assert flow == 5.0
        assert summary.total_flow == 5.0
        assert len(summary.edge_flow) == 2  # A->B and B->C
        assert len(summary.min_cut) >= 1  # Should identify bottleneck edge
        assert "A" in summary.reachable
        assert len(summary.cost_distribution) > 0

    def test_min_cut_identification(self):
        """Test minimum cut identification in complex networks."""
        graph = StrictMultiDiGraph()
        graph.add_nodes_from(["S", "A", "B", "T"])

        # Create clear bottleneck
        graph.add_edge("S", "A", capacity=20.0, cost=1)
        graph.add_edge("S", "B", capacity=20.0, cost=1)
        graph.add_edge("A", "T", capacity=8.0, cost=1)  # Bottleneck
        graph.add_edge("B", "T", capacity=2.0, cost=1)  # Bottleneck

        flow, summary = calc_max_flow(graph, "S", "T", return_summary=True)

        assert flow == 10.0  # 8 + 2
        # Min cut should include the bottleneck edges
        min_cut_edges = set((edge[0], edge[1]) for edge in summary.min_cut)
        assert ("A", "T") in min_cut_edges
        assert ("B", "T") in min_cut_edges

    def test_residual_capacity_tracking(self):
        """Test residual capacity calculation after flow placement."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", capacity=10.0, cost=1)

        flow, summary = calc_max_flow(graph, "A", "B", return_summary=True)

        assert flow == 10.0
        # Residual capacity should be 0 for saturated edge
        # Get the actual edge key from the graph
        actual_edge_key = list(graph.edges("A", keys=True))[0][2]
        edge_key = ("A", "B", actual_edge_key)
        assert summary.residual_cap[edge_key] == 0.0
        assert summary.edge_flow[edge_key] == 10.0
