"""
Test code examples from API reference documentation.

This module tests examples from:
- docs/reference/api.md
- docs/reference/api-full.md

These are the low-level algorithmic examples that users might copy-paste.
"""

from ngraph.lib.algorithms.max_flow import (
    calc_max_flow,
    run_sensitivity,
    saturated_edges,
)
from ngraph.lib.algorithms.spf import spf
from ngraph.lib.graph import StrictMultiDiGraph


class TestApiMdExamples:
    """Test examples from docs/reference/api.md"""

    def test_graph_algorithms_section(self):
        """Test the Graph Algorithms section examples."""
        # Example from api.md Graph Algorithms section
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", capacity=10, cost=1)

        # Run shortest path algorithm
        costs, pred = spf(graph, "A")
        assert "A" in costs
        assert "B" in costs
        assert costs["A"] == 0
        assert costs["B"] == 1

        # Calculate maximum flow
        max_flow = calc_max_flow(graph, "A", "B")
        assert max_flow == 10.0

        # Sensitivity analysis - identify bottleneck edges and test capacity changes
        saturated = saturated_edges(graph, "A", "B")
        assert len(saturated) == 1
        assert saturated[0][:2] == ("A", "B")  # Check source and target

        sensitivity = run_sensitivity(graph, "A", "B", change_amount=1.0)
        assert len(sensitivity) == 1
        # Should show +1.0 flow increase when capacity increased by 1
        assert list(sensitivity.values())[0] == 1.0


class TestApiFullMdExamples:
    """Test examples from docs/reference/api-full.md"""

    def test_calc_max_flow_examples(self):
        """Test calc_max_flow examples from api-full.md docstring."""
        # Example from api-full.md calc_max_flow docstring
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        _ = g.add_edge("A", "B", capacity=10.0, flow=0.0, flows={}, cost=1)
        _ = g.add_edge("B", "C", capacity=5.0, flow=0.0, flows={}, cost=1)

        # Basic usage (scalar return)
        max_flow_value = calc_max_flow(g, "A", "C")
        assert max_flow_value == 5.0

        # With flow summary analytics
        flow, summary = calc_max_flow(g, "A", "C", return_summary=True)
        assert flow == 5.0
        assert summary.total_flow == 5.0
        assert len(summary.min_cut) == 1
        # The min-cut should be the B→C edge since it has lower capacity
        min_cut_edge = summary.min_cut[0]
        assert min_cut_edge[:2] == ("B", "C")

        # With both summary and mutated graph
        flow, summary, flow_graph = calc_max_flow(
            g, "A", "C", return_summary=True, return_graph=True
        )
        assert flow == 5.0
        assert isinstance(flow_graph, StrictMultiDiGraph)
        assert len(list(flow_graph.edges())) == 2

        # Verify flow assignments in the graph
        edge_flows = []
        for _u, _v, _k, data in flow_graph.edges(data=True, keys=True):
            edge_flows.append(data.get("flow", 0.0))

        # Both edges should have 5.0 flow
        assert all(flow == 5.0 for flow in edge_flows)

    def test_saturated_edges_examples(self):
        """Test saturated_edges function with a more complex example."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        g.add_node("C")
        g.add_node("D")

        # Create a network where B→C is the bottleneck
        _ = g.add_edge("A", "B", capacity=10.0, cost=1)
        _ = g.add_edge("B", "C", capacity=3.0, cost=1)  # Bottleneck
        _ = g.add_edge("A", "D", capacity=5.0, cost=1)
        _ = g.add_edge("D", "C", capacity=5.0, cost=1)

        # Find saturated edges
        saturated = saturated_edges(g, "A", "C")

        # Should find the bottleneck edge(s)
        assert len(saturated) >= 1

        # Verify the function works with tolerance parameter
        saturated_tight = saturated_edges(g, "A", "C", tolerance=1e-12)
        saturated_loose = saturated_edges(g, "A", "C", tolerance=0.1)

        # Tight tolerance should find exact saturated edges
        # Loose tolerance might find more edges
        assert len(saturated_tight) <= len(saturated_loose)

    def test_run_sensitivity_examples(self):
        """Test run_sensitivity function examples."""
        g = StrictMultiDiGraph()
        g.add_node("S")
        g.add_node("T")
        g.add_node("M")  # Middle node

        # Create a simple network with one bottleneck
        _ = g.add_edge("S", "M", capacity=10.0, cost=1)
        _ = g.add_edge("M", "T", capacity=5.0, cost=1)  # Bottleneck

        # Test capacity increase sensitivity
        sensitivity_up = run_sensitivity(g, "S", "T", change_amount=1.0)
        assert len(sensitivity_up) >= 1

        # Increasing bottleneck capacity should increase flow
        bottleneck_improvement = max(sensitivity_up.values())
        assert bottleneck_improvement > 0

        # Test capacity decrease sensitivity
        sensitivity_down = run_sensitivity(g, "S", "T", change_amount=-1.0)
        assert len(sensitivity_down) >= 1

        # Decreasing bottleneck capacity should decrease flow
        bottleneck_degradation = min(sensitivity_down.values())
        assert bottleneck_degradation < 0

        # Test zero-capacity behavior (negative change larger than capacity)
        sensitivity_zero = run_sensitivity(g, "S", "T", change_amount=-10.0)
        # Should not cause errors, capacities should be clamped to 0
        assert isinstance(sensitivity_zero, dict)

    def test_overload_return_types(self):
        """Test that calc_max_flow returns correct types based on parameters."""
        g = StrictMultiDiGraph()
        g.add_node("A")
        g.add_node("B")
        _ = g.add_edge("A", "B", capacity=5.0, cost=1)

        # Test scalar return (default)
        result1 = calc_max_flow(g, "A", "B")
        assert isinstance(result1, (int, float))
        assert result1 == 5.0

        # Test with return_summary=True
        result2 = calc_max_flow(g, "A", "B", return_summary=True)
        assert isinstance(result2, tuple)
        assert len(result2) == 2
        flow, summary = result2
        assert isinstance(flow, (int, float))
        assert hasattr(summary, "total_flow")

        # Test with return_graph=True
        result3 = calc_max_flow(g, "A", "B", return_graph=True)
        assert isinstance(result3, tuple)
        assert len(result3) == 2
        flow, graph = result3
        assert isinstance(flow, (int, float))
        assert isinstance(graph, StrictMultiDiGraph)

        # Test with both flags
        result4 = calc_max_flow(g, "A", "B", return_summary=True, return_graph=True)
        assert isinstance(result4, tuple)
        assert len(result4) == 3
        flow, summary, graph = result4
        assert isinstance(flow, (int, float))
        assert hasattr(summary, "total_flow")
        assert isinstance(graph, StrictMultiDiGraph)
