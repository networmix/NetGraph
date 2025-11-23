"""Tests for analysis.flow module."""

import pytest

from ngraph.exec.analysis.flow import (
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)
from ngraph.model.network import Link, Network, Node
from ngraph.results.flow import FlowIterationResult
from ngraph.types.base import FlowPlacement


class TestMaxFlowAnalysis:
    """Test max_flow_analysis function."""

    @pytest.fixture
    def simple_network(self) -> Network:
        """Create a simple test network with multiple paths."""
        network = Network()
        # Add nodes
        for node in ["datacenter1", "datacenter2", "edge1", "edge2", "router"]:
            network.add_node(Node(node))

        # Add links to create a network with capacity
        network.add_link(Link("datacenter1", "router", capacity=100.0, cost=1.0))
        network.add_link(Link("datacenter2", "router", capacity=80.0, cost=1.0))
        network.add_link(Link("router", "edge1", capacity=120.0, cost=1.0))
        network.add_link(Link("router", "edge2", capacity=60.0, cost=1.0))

        return network

    def test_max_flow_analysis_basic(self, simple_network: Network) -> None:
        """Test basic max_flow_analysis functionality."""
        result = max_flow_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source_regex="datacenter.*",
            sink_regex="edge.*",
            mode="combine",
        )

        # Verify return format
        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1
        # In combine mode, we get one aggregated flow
        flow = result.flows[0]
        assert flow.source == "datacenter.*"
        assert flow.destination == "edge.*"
        assert flow.placed > 0  # Should have some flow capacity
        assert flow.demand == flow.placed  # Max flow: demand equals placed

    def test_max_flow_analysis_with_summary(self, simple_network: Network) -> None:
        """Test include_flow_details and include_min_cut path and return shape."""
        result = max_flow_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source_regex="datacenter.*",
            sink_regex="edge.*",
            include_flow_details=True,
            include_min_cut=True,
        )

        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1
        flow = result.flows[0]

        # Should have cost distribution when include_flow_details=True
        assert isinstance(flow.cost_distribution, dict)

        # Should have min_cut edges when include_min_cut=True
        if flow.data and "edges_kind" in flow.data:
            assert flow.data["edges_kind"] == "min_cut"
            assert "edges" in flow.data

    def test_max_flow_analysis_with_optional_params(
        self, simple_network: Network
    ) -> None:
        """Test max_flow_analysis with optional parameters."""
        result = max_flow_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source_regex="datacenter.*",
            sink_regex="edge.*",
            mode="pairwise",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            extra_param="ignored",
        )

        assert isinstance(result, FlowIterationResult)
        # In pairwise mode with 2 datacenters and 2 edges, we get 4 pairs
        assert len(result.flows) >= 1
        # Check that all flows have proper source/destination matching the regex
        for flow in result.flows:
            assert flow.source.startswith("datacenter")
            assert flow.destination.startswith("edge")

    def test_max_flow_analysis_empty_result(self, simple_network: Network) -> None:
        """Test max_flow_analysis with no matching nodes raises an error."""
        # In NetGraph-Core, non-matching nodes raise ValueError (better UX than silent empty)
        with pytest.raises(ValueError, match="No source nodes found"):
            max_flow_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source_regex="nonexistent.*",
                sink_regex="also_nonexistent.*",
            )


class TestDemandPlacementAnalysis:
    """Test demand_placement_analysis function."""

    @pytest.fixture
    def diamond_network(self) -> Network:
        """Create a diamond network for testing demand placement."""
        network = Network()
        # Add nodes: A -> B,C -> D (diamond shape)
        for node in ["A", "B", "C", "D"]:
            network.add_node(Node(node))

        # Add links with limited capacity
        network.add_link(Link("A", "B", capacity=60.0, cost=1.0))
        network.add_link(Link("A", "C", capacity=60.0, cost=1.0))
        network.add_link(Link("B", "D", capacity=60.0, cost=1.0))
        network.add_link(Link("C", "D", capacity=60.0, cost=1.0))

        return network

    def test_demand_placement_analysis_basic(self, diamond_network: Network) -> None:
        """Test basic demand_placement_analysis functionality."""
        # Use a smaller demand that should definitely fit
        demands_config = [
            {
                "source_path": "A",
                "sink_path": "D",
                "demand": 50.0,
                "mode": "pairwise",
                "priority": 0,
            },
        ]

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            placement_rounds=1,
        )

        # Verify results structure
        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1

        flow = result.flows[0]
        assert flow.source == "A"
        assert flow.destination == "D"
        assert flow.priority == 0
        assert flow.demand == 50.0
        # With 50 demand and two paths of 60 capacity each, should place all
        assert flow.placed == 50.0
        assert flow.dropped == 0.0

        summary = result.summary
        assert summary.total_demand == 50.0
        assert summary.total_placed == 50.0
        assert summary.overall_ratio == 1.0

    def test_demand_placement_analysis_zero_total_demand(
        self, diamond_network: Network
    ) -> None:
        """Handles zero total demand without division by zero."""
        demands_config = [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 0.0,
            }
        ]

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            placement_rounds=1,
        )

        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1
        assert result.flows[0].placed == 0.0
        summary = result.summary
        assert summary.total_demand == 0.0
        assert summary.total_placed == 0.0
        assert summary.overall_ratio == 1.0


class TestSensitivityAnalysis:
    """Test sensitivity_analysis function."""

    @pytest.fixture
    def simple_network(self) -> Network:
        """Create a simple test network."""
        network = Network()
        for node in ["A", "B", "C"]:
            network.add_node(Node(node))
        network.add_link(Link("A", "B", capacity=10.0, cost=1.0))
        network.add_link(Link("B", "C", capacity=10.0, cost=1.0))
        return network

    def test_sensitivity_analysis_basic(self, simple_network: Network) -> None:
        """Test basic sensitivity_analysis functionality."""
        # Note: Current implementation returns empty dict as a placeholder
        # This is documented in the function - full implementation requires
        # additional Core API support for component criticality scores
        result = sensitivity_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source_regex="A",
            sink_regex="C",
            mode="combine",
        )

        # Current implementation returns empty dict
        assert isinstance(result, dict)

    def test_sensitivity_analysis_empty_result(self, simple_network: Network) -> None:
        """Test sensitivity_analysis with empty result."""
        with pytest.raises(ValueError, match="No source nodes found"):
            sensitivity_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source_regex="nonexistent.*",
                sink_regex="also_nonexistent.*",
            )
