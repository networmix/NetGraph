import pytest
from pytest import approx

from ngraph.algorithms.base import FlowPlacement
from ngraph.algorithms.max_flow import calc_max_flow
from ngraph.algorithms.types import FlowSummary
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


class TestMaxFlowBasic:
    """
    Tests that directly verify specific flow values on known small graphs.
    """

    def test_max_flow_line1_full_flow(self, line1):
        """
        On line1 fixture:
         - Full iterative max flow from A to C should be 5.
        """
        max_flow = calc_max_flow(line1, "A", "C")
        assert max_flow == 5

    def test_max_flow_line1_shortest_path(self, line1):
        """
        On line1 fixture:
         - With shortest_path=True (single augmentation), expect flow=4.
        """
        max_flow = calc_max_flow(line1, "A", "C", shortest_path=True)
        assert max_flow == 4

    def test_max_flow_square4_full_flow(self, square4):
        """
        On square4 fixture:
         - Full iterative max flow from A to B should be 350 by default.
        """
        max_flow = calc_max_flow(square4, "A", "B")
        assert max_flow == 350

    def test_max_flow_square4_shortest_path(self, square4):
        """
        On square4 fixture:
         - With shortest_path=True, only one flow augmentation => 100.
        """
        max_flow = calc_max_flow(square4, "A", "B", shortest_path=True)
        assert max_flow == 100

    def test_max_flow_graph5_full_flow(self, graph5):
        """
        On graph5 (fully connected 5 nodes with capacity=1 on each edge):
         - Full iterative max flow from A to B = 4.
        """
        max_flow = calc_max_flow(graph5, "A", "B")
        assert max_flow == 4

    def test_max_flow_graph5_shortest_path(self, graph5):
        """
        On graph5:
         - With shortest_path=True => flow=1 for a single augmentation.
        """
        max_flow = calc_max_flow(graph5, "A", "B", shortest_path=True)
        assert max_flow == 1


class TestMaxFlowCopyBehavior:
    """
    Tests verifying how flow is (or isn't) preserved when copy_graph=False.
    """

    def test_max_flow_graph_copy_disabled(self, graph5):
        """
        - The first call saturates flow from A to B => 4.
        - A second call on the same graph (copy_graph=False) expects 0
          because the flow is already placed.
        """
        graph5_copy = graph5.copy()
        max_flow1 = calc_max_flow(graph5_copy, "A", "B", copy_graph=False)
        assert max_flow1 == 4

        max_flow2 = calc_max_flow(graph5_copy, "A", "B", copy_graph=False)
        assert max_flow2 == 0

    def test_max_flow_reset_flow(self, line1):
        """
        Ensures that reset_flow_graph=True zeroes out existing flow
        before computing again.
        """
        # First run places flow on line1:
        calc_max_flow(line1, "A", "C", copy_graph=False)

        # Now run again with reset_flow_graph=True:
        max_flow_after_reset = calc_max_flow(
            line1, "A", "C", copy_graph=False, reset_flow_graph=True
        )
        # Should return the same result as a fresh run (5)
        assert max_flow_after_reset == 5


class TestMaxFlowShortestPathRepeated:
    """
    Verifies that repeated shortest-path calls do not accumulate flow
    when copy_graph=False.
    """

    def test_shortest_path_repeated_calls(self, line1):
        """
        First call with shortest_path=True => 4
        Second call => 1 (since there is a longer path found after saturation of the shortest).
        """
        flow1 = calc_max_flow(line1, "A", "C", shortest_path=True, copy_graph=False)
        assert flow1 == 4

        flow2 = calc_max_flow(line1, "A", "C", shortest_path=True, copy_graph=False)
        assert flow2 == 1


@pytest.mark.parametrize(
    "placement", [FlowPlacement.PROPORTIONAL, FlowPlacement.EQUAL_BALANCED]
)
def test_square4_flow_placement(square4, placement):
    """
    Example showing how to test different FlowPlacement modes on the same fixture.
    For square4, the PROPORTIONAL and EQUAL_BALANCED results might differ,
    but here we simply check if we get the original tested value or not.
    Adjust as needed if the EQUAL_BALANCED result is known to differ.
    """
    max_flow = calc_max_flow(square4, "A", "B", flow_placement=placement)

    if placement == FlowPlacement.PROPORTIONAL:
        # Known from above
        assert max_flow == 350
    else:
        # If equal-balanced yields a different known answer, verify that here.
        # If it's actually the same, use the same assertion or approx check:
        assert max_flow == approx(350, abs=1e-9)


class TestMaxFlowEdgeCases:
    """
    Additional tests for error conditions or graphs with no feasible flow.
    """

    def test_missing_src_node(self, line1):
        """
        Trying to compute flow with a non-existent source raises KeyError.
        """
        with pytest.raises(KeyError):
            calc_max_flow(line1, "Z", "C")

    def test_missing_dst_node(self, line1):
        """
        Trying to compute flow with a non-existent destination raises ValueError.
        """
        with pytest.raises(ValueError):
            calc_max_flow(line1, "A", "Z")

    def test_zero_capacity_edges(self):
        """
        Graph with edges that all have zero capacity => max flow=0.
        """
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_edge("A", "B", capacity=0.0, cost=1)
        max_flow = calc_max_flow(g, "A", "B")
        assert max_flow == 0.0

    def test_disconnected_graph(self):
        """
        Graph with no edges => disconnected => max flow=0.
        """
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        max_flow = calc_max_flow(g, "A", "B")
        assert max_flow == 0.0

    def test_very_small_capacity_precision(self):
        """Capacities near MIN_CAP threshold are honored precisely."""
        from ngraph.algorithms.base import MIN_CAP

        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")

        # Capacity slightly above MIN_CAP
        g.add_edge("A", "B", capacity=MIN_CAP * 2, cost=1)
        flow = calc_max_flow(g, "A", "B")
        assert flow == MIN_CAP * 2

        # Set capacity at MIN_CAP using the actual edge key
        edge_key = list(g.edges("A", keys=True))[0][2]
        g.edges["A", "B", edge_key]["capacity"] = MIN_CAP
        flow = calc_max_flow(g, "A", "B")
        assert flow == MIN_CAP


class TestMaxFlowExtended:
    """
    Tests for the extended max flow functionality with return_summary and return_graph flags.
    """

    def test_max_flow_return_summary_basic(self, line1):
        """Test return_summary=True returns flow value and FlowSummary."""
        result = calc_max_flow(line1, "A", "C", return_summary=True)

        # Should return a tuple
        assert isinstance(result, tuple)
        assert len(result) == 2

        flow_value, summary = result
        assert flow_value == 5
        assert isinstance(summary, FlowSummary)
        assert summary.total_flow == 5

        # Check that we have edge flows
        assert len(summary.edge_flow) > 0
        assert len(summary.residual_cap) > 0

        # Check that source is reachable
        assert "A" in summary.reachable

        # Check min-cut is properly identified
        assert isinstance(summary.min_cut, list)

    def test_max_flow_return_graph_basic(self, line1):
        """Test return_graph=True returns flow value and flow graph."""
        result = calc_max_flow(line1, "A", "C", return_graph=True)

        # Should return a tuple
        assert isinstance(result, tuple)
        assert len(result) == 2

        flow_value, flow_graph = result
        assert flow_value == 5
        assert isinstance(flow_graph, StrictMultiDiGraph)

        # Flow graph should have flow attributes on edges
        for _, _, _, d in flow_graph.edges(data=True, keys=True):
            assert "flow" in d
            assert "capacity" in d

    def test_max_flow_return_both_flags(self, line1):
        """Test both return_summary=True and return_graph=True."""
        result = calc_max_flow(line1, "A", "C", return_summary=True, return_graph=True)

        # Should return a tuple with 3 elements
        assert isinstance(result, tuple)
        assert len(result) == 3

        flow_value, summary, flow_graph = result
        assert flow_value == 5
        assert isinstance(summary, FlowSummary)
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert summary.total_flow == 5

    def test_max_flow_backward_compatibility(self, line1):
        """Test that default behavior (no flags) maintains backward compatibility."""
        result = calc_max_flow(line1, "A", "C")

        # Should return just the flow value as a scalar
        assert isinstance(result, (int, float))
        assert result == 5

    def test_flow_summary_edge_flows(self, line1):
        """Test that FlowSummary contains correct edge flow information."""
        _, summary = calc_max_flow(line1, "A", "C", return_summary=True)

        # Verify edge flows sum to total flow at source
        total_outflow = sum(
            flow for (u, _, _), flow in summary.edge_flow.items() if u == "A"
        )
        assert total_outflow == summary.total_flow

        # Verify residual capacities are non-negative
        for residual in summary.residual_cap.values():
            assert residual >= 0

    def test_flow_summary_min_cut_identification(self, square4):
        """Test min-cut identification on a more complex graph."""
        _, summary = calc_max_flow(square4, "A", "B", return_summary=True)

        # Min-cut should be non-empty for a bottleneck graph
        assert len(summary.min_cut) > 0

        # All min-cut edges should be saturated (zero residual capacity)
        for edge in summary.min_cut:
            assert summary.residual_cap[edge] == 0

    def test_flow_summary_reachable_nodes(self, line1):
        """Test that reachable nodes are correctly identified."""
        _, summary = calc_max_flow(line1, "A", "C", return_summary=True)

        # Source should always be reachable
        assert "A" in summary.reachable

        # If there's flow to destination, intermediate nodes should be reachable
        if summary.total_flow > 0:
            # At least the source should be reachable
            assert len(summary.reachable) >= 1

    def test_shortest_path_with_summary(self, line1):
        """Test return_summary works with shortest_path=True."""
        result = calc_max_flow(line1, "A", "C", shortest_path=True, return_summary=True)

        flow_value, summary = result
        assert flow_value == 4  # Single path flow
        assert summary.total_flow == 4
        assert isinstance(summary.edge_flow, dict)
        assert isinstance(summary.min_cut, list)

    def test_empty_graph_with_summary(self):
        """Test behavior with disconnected nodes."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")

        flow_value, summary = calc_max_flow(g, "A", "B", return_summary=True)

        assert flow_value == 0
        assert summary.total_flow == 0
        assert len(summary.edge_flow) == 0
        assert len(summary.residual_cap) == 0
        assert "A" in summary.reachable
        assert "B" not in summary.reachable
        assert len(summary.min_cut) == 0

    def test_saturated_edges_helper(self, line1):
        """Test the saturated_edges helper function."""
        from ngraph.algorithms.max_flow import saturated_edges

        saturated = saturated_edges(line1, "A", "C")

        # Should return a list of edge tuples
        assert isinstance(saturated, list)

        # All saturated edges should have zero residual capacity
        _, summary = calc_max_flow(line1, "A", "C", return_summary=True)
        for edge in saturated:
            assert summary.residual_cap[edge] <= 1e-10

    def test_sensitivity_analysis_helper(self, line1):
        """Test the run_sensitivity helper function."""
        from ngraph.algorithms.max_flow import run_sensitivity

        sensitivity = run_sensitivity(line1, "A", "C", change_amount=1.0)

        # Should return a dictionary mapping edges to flow increases
        assert isinstance(sensitivity, dict)

        # All sensitivity values should be non-negative
        for edge, flow_increase in sensitivity.items():
            assert isinstance(edge, tuple)
            assert len(edge) == 3  # (u, v, k)
            assert flow_increase >= 0

    def test_sensitivity_analysis_identifies_bottlenecks(self, square4):
        """Test that sensitivity analysis identifies meaningful bottlenecks."""
        from ngraph.algorithms.max_flow import run_sensitivity

        sensitivity = run_sensitivity(square4, "A", "B", change_amount=10.0)

        # Should have some edges with positive sensitivity
        positive_impacts = [impact for impact in sensitivity.values() if impact > 0]
        assert len(positive_impacts) > 0

        # Highest impact edges should be meaningful bottlenecks
        if sensitivity:
            max_impact = max(sensitivity.values())
            assert max_impact > 0

    def test_sensitivity_analysis_negative_capacity_protection(self, line1):
        """Test that sensitivity analysis sets capacity to zero instead of negative values."""
        from ngraph.algorithms.max_flow import run_sensitivity

        # Test with a large negative change that would make capacities negative
        sensitivity = run_sensitivity(line1, "A", "C", change_amount=-100.0)

        # Should still return results (not skip edges)
        assert isinstance(sensitivity, dict)
        assert len(sensitivity) > 0

        # All sensitivity values should be negative (flow reduction)
        for edge, flow_change in sensitivity.items():
            assert isinstance(edge, tuple)
            assert len(edge) == 3  # (u, v, k)
            assert flow_change <= 0  # Should reduce or maintain flow

    def test_sensitivity_analysis_zero_capacity_behavior(self):
        """Test specific behavior when edge capacity is reduced to zero."""
        from ngraph.algorithms.max_flow import run_sensitivity

        # Create a simple graph with known capacities
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")

        # Add edges: A->B (capacity 10), B->C (capacity 5)
        g.add_edge("A", "B", capacity=10.0, flow=0.0, flows={}, cost=1.0)
        bc_edge_key = g.add_edge("B", "C", capacity=5.0, flow=0.0, flows={}, cost=1.0)

        # Test reducing edge B->C capacity by 10 (more than its current capacity of 5)
        sensitivity = run_sensitivity(g, "A", "C", change_amount=-10.0)

        # Should reduce flow to zero (complete bottleneck removal)
        bc_edge = ("B", "C", bc_edge_key)
        assert bc_edge in sensitivity
        assert sensitivity[bc_edge] == -5.0  # Should reduce flow by 5 (from 5 to 0)

    def test_sensitivity_analysis_partial_capacity_reduction(self):
        """Test behavior when capacity is partially reduced but not to zero."""
        from ngraph.algorithms.max_flow import run_sensitivity

        # Create a simple graph
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")

        # Add edges with specific capacities
        g.add_edge("A", "B", capacity=10.0, flow=0.0, flows={}, cost=1.0)
        bc_edge_key = g.add_edge("B", "C", capacity=8.0, flow=0.0, flows={}, cost=1.0)

        # Test reducing edge B->C capacity by 3 (from 8 to 5)
        sensitivity = run_sensitivity(g, "A", "C", change_amount=-3.0)

        # Should reduce flow by 3 (the bottleneck reduction)
        bc_edge = ("B", "C", bc_edge_key)
        assert bc_edge in sensitivity
        assert sensitivity[bc_edge] == -3.0

    def test_sensitivity_analysis_capacity_increase_and_decrease(self):
        """Test that both positive and negative changes work correctly."""
        from ngraph.algorithms.max_flow import run_sensitivity

        # Create a bottleneck graph
        g = StrictMultiDiGraph()
        for node in ["A", "B", "C", "D"]:
            g.add_node(node)

        g.add_edge("A", "B", capacity=20.0, flow=0.0, flows={}, cost=1.0)
        g.add_edge("A", "C", capacity=20.0, flow=0.0, flows={}, cost=1.0)
        g.add_edge("B", "D", capacity=10.0, flow=0.0, flows={}, cost=1.0)  # Bottleneck
        g.add_edge("C", "D", capacity=15.0, flow=0.0, flows={}, cost=1.0)

        # Test capacity increase
        sensitivity_increase = run_sensitivity(g, "A", "D", change_amount=5.0)

        # Test capacity decrease
        sensitivity_decrease = run_sensitivity(g, "A", "D", change_amount=-3.0)

        # Both should return results
        assert len(sensitivity_increase) > 0
        assert len(sensitivity_decrease) > 0

        # Increases should be positive or zero
        for flow_change in sensitivity_increase.values():
            assert flow_change >= 0

        # Decreases should be negative or zero
        for flow_change in sensitivity_decrease.values():
            assert flow_change <= 0

    def test_max_flow_overlapping_source_sink_simple(self):
        """Test max flow with overlapping source/sink nodes that caused infinite loops."""
        g = StrictMultiDiGraph()
        g.add_node("N1")
        g.add_node("N2")

        # Simple topology: N1 -> N2
        g.add_edge("N1", "N2", capacity=1.0, flow=0.0, flows={}, cost=1)

        # Test all combinations that would occur in pairwise mode with overlapping patterns
        # N1 -> N1 (self-loop)
        max_flow_n1_n1 = calc_max_flow(g, "N1", "N1")
        assert max_flow_n1_n1 == 0.0

        # N1 -> N2 (valid path)
        max_flow_n1_n2 = calc_max_flow(g, "N1", "N2")
        assert max_flow_n1_n2 == 1.0

        # N2 -> N1 (no path)
        max_flow_n2_n1 = calc_max_flow(g, "N2", "N1")
        assert max_flow_n2_n1 == 0.0

        # N2 -> N2 (self-loop)
        max_flow_n2_n2 = calc_max_flow(g, "N2", "N2")
        assert max_flow_n2_n2 == 0.0

    def test_max_flow_overlapping_source_sink_with_bidirectional(self):
        """Test overlapping source/sink with bidirectional edges."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")

        # Bidirectional edges
        g.add_edge("A", "B", capacity=5.0, flow=0.0, flows={}, cost=1)
        g.add_edge("B", "A", capacity=3.0, flow=0.0, flows={}, cost=1)

        # Test all combinations
        # A -> A (self-loop)
        max_flow_a_a = calc_max_flow(g, "A", "A")
        assert max_flow_a_a == 0.0

        # A -> B (forward direction)
        max_flow_a_b = calc_max_flow(g, "A", "B")
        assert max_flow_a_b == 5.0

        # B -> A (reverse direction)
        max_flow_b_a = calc_max_flow(g, "B", "A")
        assert max_flow_b_a == 3.0

        # B -> B (self-loop)
        max_flow_b_b = calc_max_flow(g, "B", "B")
        assert max_flow_b_b == 0.0

    def test_max_flow_self_loop_all_return_modes(self):
        """
        Test self-loop (s == t) behavior with all possible return value combinations.
        Ensures that our optimization properly handles all return modes.
        """
        # Create a simple graph with a self-loop
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_edge("A", "A", capacity=10.0, flow=0.0, flows={}, cost=1)

        # Test 1: Basic scalar return (return_summary=False, return_graph=False)
        flow_scalar = calc_max_flow(g, "A", "A")
        assert flow_scalar == 0.0
        assert isinstance(flow_scalar, float)

        # Test 2: With summary only (return_summary=True, return_graph=False)
        flow_with_summary = calc_max_flow(g, "A", "A", return_summary=True)
        assert isinstance(flow_with_summary, tuple)
        assert len(flow_with_summary) == 2
        flow, summary = flow_with_summary
        assert flow == 0.0
        assert isinstance(summary, FlowSummary)
        assert summary.total_flow == 0.0
        assert "A" in summary.reachable  # Source should be reachable from itself
        assert len(summary.min_cut) == 0  # No min-cut edges for self-loop

        # Test 3: With graph only (return_summary=False, return_graph=True)
        flow_with_graph = calc_max_flow(g, "A", "A", return_graph=True)
        assert isinstance(flow_with_graph, tuple)
        assert len(flow_with_graph) == 2
        flow, flow_graph = flow_with_graph
        assert flow == 0.0
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert flow_graph.has_node("A")
        assert flow_graph.has_edge("A", "A")

        # Test 4: With both summary and graph (return_summary=True, return_graph=True)
        flow_with_both = calc_max_flow(
            g, "A", "A", return_summary=True, return_graph=True
        )
        assert isinstance(flow_with_both, tuple)
        assert len(flow_with_both) == 3
        flow, summary, flow_graph = flow_with_both
        assert flow == 0.0
        assert isinstance(summary, FlowSummary)
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert summary.total_flow == 0.0
        assert "A" in summary.reachable
        assert len(summary.min_cut) == 0
        assert flow_graph.has_node("A")
        assert flow_graph.has_edge("A", "A")

        # Verify that the flow on the self-loop edge is 0
        self_loop_edges = list(flow_graph.edges(nbunch="A", data=True, keys=True))
        a_to_a_edges = [
            (u, v, k, d) for u, v, k, d in self_loop_edges if u == "A" and v == "A"
        ]
        assert len(a_to_a_edges) >= 1
        for _u, _v, _k, data in a_to_a_edges:
            assert data.get("flow", 0.0) == 0.0


def test_max_flow_with_parallel_edges():
    """
    Tests max flow calculations on a graph with parallel edges.

    Graph topology (costs/capacities):

                 [1,1] & [1,2]     [1,1] & [1,2]
          A ──────────────────► B ─────────────► C
          │                                      ▲
          │    [2,3]                             │ [2,3]
          └───────────────────► D ───────────────┘

    Edges:
      - A→B: two parallel edges with (cost=1, capacity=1) and (cost=1, capacity=2)
      - B→C: two parallel edges with (cost=1, capacity=1) and (cost=1, capacity=2)
      - A→D: (cost=2, capacity=3)
      - D→C: (cost=2, capacity=3)

    The test computes:
      - The true maximum flow (expected flow: 6.0)
      - The flow along the shortest paths (expected flow: 3.0)
      - Flow placement using an equal-balanced strategy on the shortest paths (expected flow: 2.0)
    """
    from ngraph.algorithms.base import FlowPlacement
    from ngraph.algorithms.max_flow import calc_max_flow
    from ngraph.graph.strict_multidigraph import StrictMultiDiGraph

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    # Create parallel edges between A→B and B→C
    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("A", "B", key=1, cost=1, capacity=2)
    g.add_edge("B", "C", key=2, cost=1, capacity=1)
    g.add_edge("B", "C", key=3, cost=1, capacity=2)
    # Create an alternative path A→D→C
    g.add_edge("A", "D", key=4, cost=2, capacity=3)
    g.add_edge("D", "C", key=5, cost=2, capacity=3)

    # 1. The true maximum flow
    max_flow_prop = calc_max_flow(g, "A", "C")
    assert max_flow_prop == 6.0, f"Expected 6.0, got {max_flow_prop}"

    # 2. The flow along the shortest paths
    max_flow_sp = calc_max_flow(g, "A", "C", shortest_path=True)
    assert max_flow_sp == 3.0, f"Expected 3.0, got {max_flow_sp}"

    # 3. Flow placement using an equal-balanced strategy on the shortest paths
    max_flow_eq = calc_max_flow(
        g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
    )
    assert max_flow_eq == 2.0, f"Expected 2.0, got {max_flow_eq}"


class TestMaxFlowCostDistribution:
    """Tests for cost distribution calculation in max flow analysis."""

    def test_cost_distribution_multiple_paths(self):
        """Test cost distribution with paths of different costs."""
        # Create graph with two path options at different costs
        g = StrictMultiDiGraph()
        for node in ["S", "A", "B", "T"]:
            g.add_node(node)

        # Path 1: S -> A -> T (cost = 1 + 1 = 2, capacity = 5)
        g.add_edge("S", "A", capacity=5.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "T", capacity=5.0, flow=0.0, flows={}, cost=1)

        # Path 2: S -> B -> T (cost = 2 + 2 = 4, capacity = 3)
        g.add_edge("S", "B", capacity=3.0, flow=0.0, flows={}, cost=2)
        g.add_edge("B", "T", capacity=3.0, flow=0.0, flows={}, cost=2)

        flow_value, summary = calc_max_flow(g, "S", "T", return_summary=True)

        # Algorithm should use lowest cost path first, then higher cost
        assert flow_value == 8.0
        assert summary.cost_distribution == {2.0: 5.0, 4.0: 3.0}

    def test_cost_distribution_single_path(self):
        """Test cost distribution with a single path."""
        g = StrictMultiDiGraph()
        for node in ["A", "B", "C"]:
            g.add_node(node)

        # Single path: A -> B -> C (cost = 3 + 2 = 5, capacity = 10)
        g.add_edge("A", "B", capacity=10.0, flow=0.0, flows={}, cost=3)
        g.add_edge("B", "C", capacity=10.0, flow=0.0, flows={}, cost=2)

        flow_value, summary = calc_max_flow(g, "A", "C", return_summary=True)

        assert flow_value == 10.0
        assert summary.cost_distribution == {5.0: 10.0}

    def test_cost_distribution_equal_cost_paths(self):
        """Test cost distribution with multiple equal-cost paths."""
        g = StrictMultiDiGraph()
        for node in ["S", "A", "B", "T"]:
            g.add_node(node)

        # Two paths with same cost but different capacities
        # Path 1: S -> A -> T (cost = 1 + 1 = 2, capacity = 4)
        g.add_edge("S", "A", capacity=4.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "T", capacity=4.0, flow=0.0, flows={}, cost=1)

        # Path 2: S -> B -> T (cost = 1 + 1 = 2, capacity = 6)
        g.add_edge("S", "B", capacity=6.0, flow=0.0, flows={}, cost=1)
        g.add_edge("B", "T", capacity=6.0, flow=0.0, flows={}, cost=1)

        flow_value, summary = calc_max_flow(g, "S", "T", return_summary=True)

        # Should aggregate all flow at the same cost
        assert flow_value == 10.0
        assert summary.cost_distribution == {2.0: 10.0}

    def test_cost_distribution_three_tiers(self):
        """Test cost distribution with three different cost tiers."""
        g = StrictMultiDiGraph()
        for node in ["S", "A", "B", "C", "T"]:
            g.add_node(node)

        # Path 1: S -> A -> T (cost = 1, capacity = 2)
        g.add_edge("S", "A", capacity=2.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "T", capacity=2.0, flow=0.0, flows={}, cost=0)

        # Path 2: S -> B -> T (cost = 3, capacity = 4)
        g.add_edge("S", "B", capacity=4.0, flow=0.0, flows={}, cost=2)
        g.add_edge("B", "T", capacity=4.0, flow=0.0, flows={}, cost=1)

        # Path 3: S -> C -> T (cost = 6, capacity = 3)
        g.add_edge("S", "C", capacity=3.0, flow=0.0, flows={}, cost=3)
        g.add_edge("C", "T", capacity=3.0, flow=0.0, flows={}, cost=3)

        flow_value, summary = calc_max_flow(g, "S", "T", return_summary=True)

        # Should use paths in cost order: cost 1, then 3, then 6
        assert flow_value == 9.0
        assert summary.cost_distribution == {1.0: 2.0, 3.0: 4.0, 6.0: 3.0}

    def test_cost_distribution_no_flow(self):
        """Test cost distribution when no flow is possible."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        # No edges - no path possible

        flow_value, summary = calc_max_flow(g, "A", "B", return_summary=True)

        assert flow_value == 0.0
        assert summary.cost_distribution == {}

    def test_cost_distribution_self_loop(self):
        """Test cost distribution for self-loop case."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_edge("A", "A", capacity=10.0, flow=0.0, flows={}, cost=5)

        flow_value, summary = calc_max_flow(g, "A", "A", return_summary=True)

        # Self-loop always returns 0 flow
        assert flow_value == 0.0
        assert summary.cost_distribution == {}

    def test_cost_distribution_shortest_path_mode(self):
        """Test cost distribution with shortest_path=True (single augmentation)."""
        g = StrictMultiDiGraph()
        for node in ["S", "A", "B", "T"]:
            g.add_node(node)

        # Path 1: S -> A -> T (cost = 2, capacity = 5)
        g.add_edge("S", "A", capacity=5.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "T", capacity=5.0, flow=0.0, flows={}, cost=1)

        # Path 2: S -> B -> T (cost = 4, capacity = 3)
        g.add_edge("S", "B", capacity=3.0, flow=0.0, flows={}, cost=2)
        g.add_edge("B", "T", capacity=3.0, flow=0.0, flows={}, cost=2)

        flow_value, summary = calc_max_flow(
            g, "S", "T", shortest_path=True, return_summary=True
        )

        # Should only use the first (lowest cost) path
        assert flow_value == 5.0
        assert summary.cost_distribution == {2.0: 5.0}

    def test_cost_distribution_capacity_bottleneck(self):
        """Test cost distribution when bottleneck limits flow on cheaper path."""
        g = StrictMultiDiGraph()
        for node in ["S", "A", "B", "T"]:
            g.add_node(node)

        # Path 1: S -> A -> T (cost = 1, but bottleneck capacity = 2)
        g.add_edge("S", "A", capacity=10.0, flow=0.0, flows={}, cost=1)
        g.add_edge("A", "T", capacity=2.0, flow=0.0, flows={}, cost=0)  # Bottleneck

        # Path 2: S -> B -> T (cost = 3, capacity = 5)
        g.add_edge("S", "B", capacity=5.0, flow=0.0, flows={}, cost=2)
        g.add_edge("B", "T", capacity=5.0, flow=0.0, flows={}, cost=1)

        flow_value, summary = calc_max_flow(g, "S", "T", return_summary=True)

        # Should use cheap path first (limited by bottleneck), then expensive path
        assert flow_value == 7.0
        assert summary.cost_distribution == {1.0: 2.0, 3.0: 5.0}
