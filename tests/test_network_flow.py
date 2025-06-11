"""
Tests for flow analysis methods in the network module.

This module contains tests for:
- Maximum flow calculations (max_flow)
- Saturated edges identification (saturated_edges)
- Sensitivity analysis (sensitivity_analysis)
- Flow-related edge cases and overlapping patterns
"""

import pytest

from ngraph.network import Link, Network, Node


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

        flow_value = net.max_flow("A", "C")
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

        flow_value = net.max_flow("A", "C")
        assert flow_value == {("A", "C"): 10.0}

    def test_max_flow_no_source(self):
        """Test max flow when no source nodes match the pattern."""
        net = Network()
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("B", "C", capacity=10))

        with pytest.raises(ValueError, match="No source nodes found matching 'A'"):
            net.max_flow("A", "C")

    def test_max_flow_no_sink(self):
        """Test max flow when no sink nodes match the pattern."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="No sink nodes found matching 'C'"):
            net.max_flow("A", "C")

    def test_max_flow_invalid_mode(self):
        """Test max flow with invalid mode parameter."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        with pytest.raises(ValueError, match="Invalid mode 'foobar'"):
            net.max_flow("A", "B", mode="foobar")

    def test_max_flow_overlap_detection_coverage(self):
        """Test specific overlap detection logic in max_flow combine mode for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        # Create a scenario where there are valid groups but they overlap
        flow_result = net.max_flow(
            source_path=r"^(A|B)$",  # Matches A and B
            sink_path=r"^(B|C)$",  # Matches B and C (B overlaps!)
            mode="combine",
        )

        # Should return 0 flow due to B being in both source and sink groups
        assert len(flow_result) == 1
        assert list(flow_result.values())[0] == 0.0

    def test_max_flow_invalid_mode_error(self):
        """Test that invalid mode properly raises ValueError."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="Invalid mode 'totally_invalid'"):
            net.max_flow("A", "B", mode="totally_invalid")

    def test_max_flow_disabled_nodes_coverage(self):
        """Test max_flow with disabled source nodes for coverage."""
        net = Network()
        net.add_node(Node("A", disabled=True))  # Disabled source
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=5.0))

        # This should trigger the empty sources condition
        flow_result = net.max_flow("A", "B")
        assert flow_result[("A", "B")] == 0.0

    def test_saturated_edges_empty_combine_coverage(self):
        """Test saturated_edges with empty nodes in combine mode for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C", disabled=True))
        net.add_link(Link("A", "B", capacity=5.0))

        # This should create empty combined sink nodes
        saturated = net.saturated_edges("A", "B|C", mode="combine")
        key = ("A", "B|C")
        assert key in saturated
        assert saturated[key] == []

    def test_saturated_edges_invalid_mode_error(self):
        """Test that saturated_edges with invalid mode properly raises ValueError."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="Invalid mode 'bad_mode'"):
            net.saturated_edges("A", "B", mode="bad_mode")

    def test_sensitivity_analysis_empty_combine_coverage(self):
        """Test sensitivity_analysis with empty nodes in combine mode for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C", disabled=True))
        net.add_link(Link("A", "B", capacity=5.0))

        # This should create empty combined sink nodes
        sensitivity = net.sensitivity_analysis("A", "B|C", mode="combine")
        key = ("A", "B|C")
        assert key in sensitivity
        assert sensitivity[key] == {}

    def test_sensitivity_analysis_invalid_mode_error(self):
        """Test that sensitivity_analysis with invalid mode properly raises ValueError."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10))

        with pytest.raises(ValueError, match="Invalid mode 'wrong_mode'"):
            net.sensitivity_analysis("A", "B", mode="wrong_mode")

    def test_flow_methods_overlap_conditions_coverage(self):
        """Test overlap conditions in flow methods for coverage."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        # Test overlap condition in saturated_edges pairwise mode
        saturated = net.saturated_edges("A", "A", mode="pairwise")
        assert saturated[("A", "A")] == []

        # Test overlap condition in sensitivity_analysis pairwise mode
        sensitivity = net.sensitivity_analysis("A", "A", mode="pairwise")
        assert sensitivity[("A", "A")] == {}

    def test_private_method_coverage_flow_placement(self):
        """Test private method calls with None flow_placement for coverage."""
        network = Network()
        network.add_node(Node("S"))
        network.add_node(Node("T"))
        network.add_link(Link("S", "T", capacity=10))

        # Test _compute_flow_single_group with None flow_placement explicitly
        sources = [network.nodes["S"]]
        sinks = [network.nodes["T"]]
        result = network._compute_flow_single_group(sources, sinks, False, None)
        assert isinstance(result, float)

        # Test with disabled nodes to trigger private method conditions
        network.add_node(Node("X"))
        network.add_node(Node("Y", disabled=True))
        network.add_link(Link("X", "Y", capacity=5))

        # This should call private methods with None flow_placement
        sat_result = network.saturated_edges("X", "Y")
        assert sat_result[("X", "Y")] == []

        sens_result = network.sensitivity_analysis("X", "Y", change_amount=0.1)
        assert sens_result[("X", "Y")] == {}


class TestMaxFlowOverlapping:
    """Tests for maximum flow with overlapping source/sink patterns."""

    def test_max_flow_overlapping_patterns_combine_mode(self):
        """Test overlapping source/sink patterns in combine mode return 0 flow."""
        net = Network()
        net.add_node(Node("N1"))
        net.add_node(Node("N2"))
        net.add_link(Link("N1", "N2", capacity=5.0))

        flow_result = net.max_flow(
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

        flow_result = net.max_flow(
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

        flow_result = net.max_flow(
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

        flow_result = net.max_flow(
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


class TestSaturatedEdges:
    """Tests for saturated edges identification."""

    @pytest.fixture
    def bottleneck_network(self):
        """Fixture providing a network with a clear bottleneck."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=10.0))
        net.add_link(Link("B", "C", capacity=5.0))  # bottleneck
        return net

    def test_saturated_edges_simple(self, bottleneck_network):
        """Test saturated_edges method with a simple bottleneck scenario."""
        saturated = bottleneck_network.saturated_edges("A", "C")

        assert len(saturated) == 1
        key = ("A", "C")
        assert key in saturated

        edge_list = saturated[key]
        assert len(edge_list) == 1

        edge = edge_list[0]
        assert edge[0] == "B"  # source
        assert edge[1] == "C"  # target

    def test_saturated_edges_no_bottleneck(self):
        """Test saturated_edges when there's no clear bottleneck."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=100.0))

        saturated = net.saturated_edges("A", "B")

        assert len(saturated) == 1
        key = ("A", "B")
        assert key in saturated

    def test_saturated_edges_pairwise_mode(self):
        """Test saturated_edges with pairwise mode using regex patterns."""
        net = Network()
        for node in ["A1", "A2", "B", "C1", "C2"]:
            net.add_node(Node(node))

        net.add_link(Link("A1", "B", capacity=3.0))
        net.add_link(Link("A2", "B", capacity=4.0))
        net.add_link(Link("B", "C1", capacity=2.0))
        net.add_link(Link("B", "C2", capacity=3.0))

        saturated = net.saturated_edges("A(.*)", "C(.*)", mode="pairwise")

        assert len(saturated) >= 1

        for (_src_label, _sink_label), edge_list in saturated.items():
            assert isinstance(edge_list, list)

    def test_saturated_edges_error_cases(self, bottleneck_network):
        """Test error cases for saturated_edges."""
        with pytest.raises(ValueError, match="No source nodes found matching"):
            bottleneck_network.saturated_edges("NONEXISTENT", "C")

        with pytest.raises(ValueError, match="No sink nodes found matching"):
            bottleneck_network.saturated_edges("A", "NONEXISTENT")

        with pytest.raises(ValueError, match="Invalid mode 'invalid'"):
            bottleneck_network.saturated_edges("A", "C", mode="invalid")

    def test_saturated_edges_disabled_nodes(self):
        """Test saturated_edges with disabled nodes."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        saturated = net.saturated_edges("A", "C")

        key = ("A", "C")
        assert key in saturated
        assert saturated[key] == []

    def test_saturated_edges_overlapping_groups(self):
        """Test saturated_edges when source and sink groups overlap."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=5.0))

        saturated = net.saturated_edges("A|B", "A|B")

        key = ("A|B", "A|B")
        assert key in saturated
        assert saturated[key] == []

    def test_saturated_edges_tolerance_parameter(self, bottleneck_network):
        """Test saturated_edges with different tolerance values."""
        saturated_strict = bottleneck_network.saturated_edges("A", "C", tolerance=1e-15)
        saturated_loose = bottleneck_network.saturated_edges("A", "C", tolerance=1.0)

        assert ("A", "C") in saturated_strict
        assert ("A", "C") in saturated_loose


class TestSensitivityAnalysis:
    """Tests for sensitivity analysis."""

    @pytest.fixture
    def bottleneck_network(self):
        """Fixture providing a network with a clear bottleneck."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=10.0))
        net.add_link(Link("B", "C", capacity=5.0))  # bottleneck
        return net

    def test_sensitivity_analysis_simple(self, bottleneck_network):
        """Test sensitivity_analysis method with a simple bottleneck scenario."""
        sensitivity = bottleneck_network.sensitivity_analysis(
            "A", "C", change_amount=1.0
        )

        assert len(sensitivity) == 1
        key = ("A", "C")
        assert key in sensitivity

        sens_dict = sensitivity[key]
        assert isinstance(sens_dict, dict)

        if sens_dict:
            for edge, flow_change in sens_dict.items():
                assert isinstance(edge, tuple)
                assert len(edge) == 3
                assert isinstance(flow_change, (int, float))

    def test_sensitivity_analysis_negative_change(self, bottleneck_network):
        """Test sensitivity_analysis with negative capacity change."""
        sensitivity = bottleneck_network.sensitivity_analysis(
            "A", "C", change_amount=-1.0
        )

        assert ("A", "C") in sensitivity
        sens_dict = sensitivity[("A", "C")]
        assert isinstance(sens_dict, dict)

    def test_sensitivity_analysis_pairwise_mode(self):
        """Test sensitivity_analysis with pairwise mode."""
        net = Network()
        for node in ["A1", "A2", "B", "C1", "C2"]:
            net.add_node(Node(node))

        net.add_link(Link("A1", "B", capacity=3.0))
        net.add_link(Link("A2", "B", capacity=4.0))
        net.add_link(Link("B", "C1", capacity=2.0))
        net.add_link(Link("B", "C2", capacity=3.0))

        sensitivity = net.sensitivity_analysis("A(.*)", "C(.*)", mode="pairwise")

        assert len(sensitivity) >= 1

        for (_src_label, _sink_label), sens_dict in sensitivity.items():
            assert isinstance(sens_dict, dict)

    def test_sensitivity_analysis_error_cases(self, bottleneck_network):
        """Test error cases for sensitivity_analysis."""
        with pytest.raises(ValueError, match="No source nodes found matching"):
            bottleneck_network.sensitivity_analysis("NONEXISTENT", "C")

        with pytest.raises(ValueError, match="No sink nodes found matching"):
            bottleneck_network.sensitivity_analysis("A", "NONEXISTENT")

        with pytest.raises(ValueError, match="Invalid mode 'invalid'"):
            bottleneck_network.sensitivity_analysis("A", "C", mode="invalid")

    def test_sensitivity_analysis_disabled_nodes(self):
        """Test sensitivity_analysis with disabled nodes."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C"))
        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("B", "C", capacity=3.0))

        sensitivity = net.sensitivity_analysis("A", "C")

        key = ("A", "C")
        assert key in sensitivity
        assert sensitivity[key] == {}

    def test_sensitivity_analysis_overlapping_groups(self):
        """Test sensitivity_analysis when source and sink groups overlap."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=5.0))

        sensitivity = net.sensitivity_analysis("A|B", "A|B")

        key = ("A|B", "A|B")
        assert key in sensitivity
        assert sensitivity[key] == {}

    def test_sensitivity_analysis_zero_change(self, bottleneck_network):
        """Test sensitivity_analysis with zero capacity change."""
        sensitivity = bottleneck_network.sensitivity_analysis(
            "A", "C", change_amount=0.0
        )

        assert ("A", "C") in sensitivity
        sens_dict = sensitivity[("A", "C")]
        assert isinstance(sens_dict, dict)


class TestFlowIntegration:
    """Integration tests for flow analysis methods."""

    def test_saturated_edges_and_sensitivity_consistency(self):
        """Test that saturated_edges and sensitivity_analysis are consistent."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        net.add_link(Link("A", "B", capacity=10.0))
        net.add_link(Link("B", "C", capacity=5.0))

        saturated = net.saturated_edges("A", "C")
        sensitivity = net.sensitivity_analysis("A", "C")

        key = ("A", "C")
        saturated_edges_list = saturated[key]
        sensitivity_dict = sensitivity[key]

        for _edge in saturated_edges_list:
            assert isinstance(sensitivity_dict, dict)

    def test_complex_network_analysis(self):
        """Test both methods on a more complex network topology."""
        net = Network()

        for node in ["A", "B", "C", "D"]:
            net.add_node(Node(node))

        net.add_link(Link("A", "B", capacity=5.0))
        net.add_link(Link("A", "C", capacity=3.0))
        net.add_link(Link("B", "D", capacity=4.0))
        net.add_link(Link("C", "D", capacity=6.0))

        saturated = net.saturated_edges("A", "D")
        sensitivity = net.sensitivity_analysis("A", "D", change_amount=1.0)

        key = ("A", "D")
        assert key in saturated
        assert key in sensitivity

        assert isinstance(saturated[key], list)
        assert isinstance(sensitivity[key], dict)

    def test_flow_placement_parameter(self):
        """Test that different flow_placement parameters work with both methods."""
        from ngraph.lib.algorithms.base import FlowPlacement

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
            saturated = net.saturated_edges("A", "C", flow_placement=flow_placement)
            sensitivity = net.sensitivity_analysis(
                "A", "C", flow_placement=flow_placement
            )

            key = ("A", "C")
            assert key in saturated
            assert key in sensitivity

    def test_shortest_path_parameter(self):
        """Test that shortest_path parameter works with both methods."""
        net = Network()

        for node in ["A", "B", "C", "D"]:
            net.add_node(Node(node))

        # Short path: A -> B -> D (cost 2)
        net.add_link(Link("A", "B", capacity=5.0, cost=1))
        net.add_link(Link("B", "D", capacity=3.0, cost=1))

        # Long path: A -> C -> D (cost 4)
        net.add_link(Link("A", "C", capacity=4.0, cost=2))
        net.add_link(Link("C", "D", capacity=6.0, cost=2))

        # Test with shortest_path=True
        saturated_sp = net.saturated_edges("A", "D", shortest_path=True)
        sensitivity_sp = net.sensitivity_analysis("A", "D", shortest_path=True)

        key = ("A", "D")
        assert key in saturated_sp
        assert key in sensitivity_sp

        # Test with shortest_path=False
        saturated_all = net.saturated_edges("A", "D", shortest_path=False)
        sensitivity_all = net.sensitivity_analysis("A", "D", shortest_path=False)

        assert key in saturated_all
        assert key in sensitivity_all
