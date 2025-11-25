"""
Tests for flow analysis using the functional max_flow API.

This module tests maximum flow calculations using the new functional API from
ngraph.solver.maxflow after NetGraph-Core migration.

Note: saturated_edges and sensitivity_analysis tests have been removed as these
methods no longer exist in NetGraph-Core. These capabilities may be added back
through different APIs in future versions.
"""

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.maxflow import max_flow


class TestMaxFlow:
    """Tests for maximum flow calculations."""

    def test_max_flow_simple(self):
        """Test max flow on a simple bottleneck scenario."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=3))

        flow_value = max_flow(net, "A", "C")
        assert flow_value == {("A", "C"): 3.0}

    def test_max_flow_multi_parallel(self):
        """Test max flow with parallel paths."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_node(Node("D"))

        net.add_link(Link("A", "B", capacity=5))
        net.add_link(Link("B", "C", capacity=5))
        net.add_link(Link("A", "D", capacity=5))
        net.add_link(Link("D", "C", capacity=5))

        flow_value = max_flow(net, "A", "C")
        assert flow_value == {("A", "C"): 10.0}

    def test_max_flow_no_source(self):
        """Test max flow when no source nodes match the pattern."""
        net = Network()
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("B", "C", capacity=10))

        with pytest.raises(ValueError, match="No source nodes found matching 'A'"):
            max_flow(net, "A", "C")

    def test_max_flow_no_sink(self):
        """Test max flow when no sink nodes match the pattern."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="No sink nodes found matching 'C'"):
            max_flow(net, "A", "C")

    def test_max_flow_invalid_mode(self):
        """Invalid mode must raise ValueError."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        with pytest.raises(ValueError):
            max_flow(net, "A", "B", mode="foobar")

    def test_max_flow_with_attribute_grouping_combine(self):
        """Test max flow when grouping sources/sinks by attribute directive."""
        net = Network()
        # Sources group: src_group=src
        net.add_node(Node("S1", attrs={"src_group": "src"}))
        net.add_node(Node("S2", attrs={"src_group": "src"}))
        # Sink group: dst_group=dst
        net.add_node(Node("T1", attrs={"dst_group": "dst"}))

        net.add_link(Link("S1", "T1", capacity=5.0))
        net.add_link(Link("S2", "T1", capacity=3.0))

        flow = max_flow(net, "attr:src_group", "attr:dst_group", mode="combine")
        assert flow == {("src", "dst"): 8.0}

    def test_max_flow_with_mixed_attr_and_regex(self):
        """Mix attribute directive with regex path selection."""
        net = Network()
        net.add_node(Node("S1", attrs={"role": "edge"}))
        net.add_node(Node("S2", attrs={"role": "edge"}))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "T1", capacity=2.0))
        net.add_link(Link("S2", "T2", capacity=3.0))

        flow = max_flow(net, "attr:role", r"^T\d$", mode="pairwise")
        # Groups: sources -> {"edge": [S1, S2]}, sinks -> {"^T\\d$": [T1, T2]}
        # Expect pairs (edge, ^T\d$)
        assert ("edge", r"^T\d$") in flow
        # Total flow for pairwise is computed per pair entries; here two sink nodes
        # but pairwise returns individual (src_label, sink_label) results already aggregated by labels
        # We just ensure numeric result and non-negative
        assert isinstance(flow[("edge", r"^T\d$")], (int, float))
        assert flow[("edge", r"^T\d$")] >= 0.0

    def test_max_flow_overlap_detection_coverage(self):
        """Test specific overlap detection logic in max_flow combine mode for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        # Create a scenario where there are valid groups but they overlap
        flow_result = max_flow(
            net,
            source_path=r"^(A|B)$",  # Matches A and B
            sink_path=r"^(B|C)$",  # Matches B and C (B overlaps!)
            mode="combine",
        )

        # Should return 0 flow due to B being in both source and sink groups
        assert len(flow_result) == 1
        assert list(flow_result.values())[0] == 0.0

    def test_max_flow_invalid_mode_error(self):
        """Invalid mode raises ValueError (duplicate scenario collapsed)."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError):
            max_flow(net, "A", "B", mode="totally_invalid")

    def test_max_flow_disabled_nodes_coverage(self):
        """Test max_flow with disabled source nodes for coverage."""
        net = Network()
        net.add_node(Node("A", disabled=True))  # Disabled source
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=5.0))

        # This should trigger the empty sources condition
        flow_result = max_flow(net, "A", "B")
        assert flow_result[("A", "B")] == 0.0

    def test_no_private_method_calls(self):
        """Ensure public API suffices; don't rely on private helpers in tests."""
        network = Network()
        network.add_node(Node("S"))
        network.add_node(Node("T"))
        network.add_link(Link("S", "T", capacity=10))

        flow = max_flow(network, "S", "T")
        assert flow[("S", "T")] == 10.0


class TestMaxFlowOverlapping:
    """Tests for maximum flow with overlapping source/sink patterns."""

    def test_max_flow_overlapping_patterns_combine_mode(self):
        """Test overlapping source/sink patterns in combine mode return 0 flow."""
        net = Network()
        net.add_node(Node("N1"))
        net.add_node(Node("N2"))
        net.add_link(Link("N1", "N2", capacity=5.0))

        flow_result = max_flow(
            net,
            source_path=r"^N(\d+)$",
            sink_path=r"^N(\d+)$",
            mode="combine",
        )

        assert len(flow_result) == 1
        flow_val = list(flow_result.values())[0]
        assert flow_val == 0.0

        expected_label = ("1|2", "1|2")
        assert expected_label in flow_result

    def test_max_flow_overlapping_patterns_pairwise_mode(self):
        """Test overlapping source/sink patterns in pairwise mode."""
        net = Network()
        net.add_node(Node("N1"))
        net.add_node(Node("N2"))
        net.add_link(Link("N1", "N2", capacity=3.0))

        flow_result = max_flow(
            net,
            source_path=r"^N(\d+)$",
            sink_path=r"^N(\d+)$",
            mode="pairwise",
        )

        assert len(flow_result) == 4

        expected_keys = {("1", "1"), ("1", "2"), ("2", "1"), ("2", "2")}
        assert set(flow_result.keys()) == expected_keys

        # Self-loops should have 0 flow
        assert flow_result[("1", "1")] == 0.0
        assert flow_result[("2", "2")] == 0.0

        # Valid paths should have flow > 0
        assert flow_result[("1", "2")] == 3.0
        assert flow_result[("2", "1")] == 3.0

    def test_max_flow_partial_overlap_pairwise(self):
        """Test pairwise mode where source and sink patterns have partial overlap."""
        net = Network()
        net.add_node(Node("SRC1"))
        net.add_node(Node("SINK1"))
        net.add_node(Node("BOTH1"))  # Node that matches both patterns
        net.add_node(Node("BOTH2"))  # Node that matches both patterns

        # Create some connections
        net.add_link(Link("SRC1", "SINK1", capacity=2.0))
        net.add_link(Link("SRC1", "BOTH1", capacity=1.0))
        net.add_link(Link("BOTH1", "SINK1", capacity=1.5))
        net.add_link(Link("BOTH2", "BOTH1", capacity=1.0))

        flow_result = max_flow(
            net,
            source_path=r"^(SRC\d+|BOTH\d+)$",  # Matches SRC1, BOTH1, BOTH2
            sink_path=r"^(SINK\d+|BOTH\d+)$",  # Matches SINK1, BOTH1, BOTH2 (partial overlap!)
            mode="pairwise",
        )

        # Should return results for all combinations
        assert len(flow_result) == 9  # 3 sources × 3 sinks

        # Self-loops for overlapping nodes should be 0
        assert flow_result[("BOTH1", "BOTH1")] == 0.0
        assert flow_result[("BOTH2", "BOTH2")] == 0.0

        # Non-overlapping combinations should have meaningful flows
        assert flow_result[("SRC1", "SINK1")] > 0.0

    def test_max_flow_overlapping_with_disabled_nodes(self):
        """Test overlapping patterns with some nodes disabled."""
        net = Network()
        net.add_node(Node("N1"))
        net.add_node(Node("N2", disabled=True))  # disabled node
        net.add_node(Node("N3"))

        # Add some links (N2 won't participate due to being disabled)
        net.add_link(Link("N1", "N3", capacity=2.0))
        net.add_link(Link("N2", "N3", capacity=1.0))  # This link won't be used

        flow_result = max_flow(
            net,
            source_path=r"^N(\d+)$",  # Matches N1, N2, N3
            sink_path=r"^N(\d+)$",  # Matches N1, N2, N3 (OVERLAPPING!)
            mode="pairwise",
        )

        # N1, N2, N3 create groups "1", "2", "3", so we get 3x3 = 9 combinations
        assert len(flow_result) == 9

        # Self-loops return 0 (including disabled node)
        assert flow_result[("1", "1")] == 0.0  # N1->N1 self-loop
        assert flow_result[("2", "2")] == 0.0  # N2->N2 self-loop (disabled)
        assert flow_result[("3", "3")] == 0.0  # N3->N3 self-loop

        # Flows involving disabled node N2 should be 0
        assert flow_result[("1", "2")] == 0.0  # N1->N2 (N2 disabled)
        assert flow_result[("2", "1")] == 0.0  # N2->N1 (N2 disabled)
        assert flow_result[("2", "3")] == 0.0  # N2->N3 (N2 disabled)
        assert flow_result[("3", "2")] == 0.0  # N3->N2 (N2 disabled)

        # Valid flows (N1->N3, N3->N1) should work
        assert flow_result[("1", "3")] == 2.0  # N1->N3
        assert flow_result[("3", "1")] == 2.0  # N3->N1 (due to reverse edges)


class TestFlowIntegration:
    """Integration tests for max_flow with various parameters."""

    def test_flow_placement_parameter(self):
        """Test that different flow_placement parameters work correctly."""
        from ngraph.types.base import FlowPlacement

        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        net.add_link(Link("A", "B", capacity=10.0))
        net.add_link(Link("B", "C", capacity=5.0))

        for flow_placement in [
            FlowPlacement.PROPORTIONAL,
            FlowPlacement.EQUAL_BALANCED,
        ]:
            result = max_flow(net, "A", "C", flow_placement=flow_placement)
            assert result == {("A", "C"): 5.0}

    def test_shortest_path_parameter(self):
        """Test that shortest_path parameter works correctly."""
        net = Network()

        for node in ["A", "B", "C", "D"]:
            net.add_node(Node(node))

        # Short path: A -> B -> D (cost 2, capacity 3)
        net.add_link(Link("A", "B", capacity=5.0, cost=1))
        net.add_link(Link("B", "D", capacity=3.0, cost=1))

        # Long path: A -> C -> D (cost 4, capacity 4)
        net.add_link(Link("A", "C", capacity=4.0, cost=2))
        net.add_link(Link("C", "D", capacity=6.0, cost=2))

        # Test with shortest_path=True (single augmentation on lowest cost path)
        result_sp = max_flow(net, "A", "D", shortest_path=True)
        assert result_sp == {("A", "D"): 3.0}  # Limited by B->D capacity

        # Test with shortest_path=False (full max flow using all paths)
        result_all = max_flow(net, "A", "D", shortest_path=False)
        assert result_all == {("A", "D"): 7.0}  # 3.0 via B + 4.0 via C
