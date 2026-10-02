"""Tests for analysis.functions module."""

import pytest

from ngraph.analysis.functions import (
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
        for node in ["datacenter1", "datacenter2", "edge1", "edge2", "router"]:
            network.add_node(Node(node))

        network.add_link(Link("datacenter1", "router", capacity=100.0, cost=1.0))
        network.add_link(Link("datacenter2", "router", capacity=80.0, cost=1.0))
        network.add_link(Link("router", "edge1", capacity=120.0, cost=1.0))
        network.add_link(Link("router", "edge2", capacity=60.0, cost=1.0))

        return network

    def test_max_flow_analysis_rejects_unbound_context(
        self, simple_network: Network
    ) -> None:
        """An unbound context cannot serve a max-flow analysis; it raises."""
        from ngraph.analysis import analyze

        with pytest.raises(ValueError, match="Provided context is unbound"):
            max_flow_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source="datacenter.*",
                target="edge.*",
                context=analyze(simple_network),
            )

    def test_max_flow_analysis_basic(self, simple_network: Network) -> None:
        """Combine mode returns one flow whose demand equals the placed max flow."""
        result = max_flow_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source="datacenter.*",
            target="edge.*",
            mode="combine",
        )

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
            source="datacenter.*",
            target="edge.*",
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
            source="datacenter.*",
            target="edge.*",
            mode="pairwise",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert isinstance(result, FlowIterationResult)
        # In pairwise mode with 2 datacenters and 2 edges, we get 4 pairs
        assert len(result.flows) >= 1
        # Every flow's endpoints come from the source and target selectors
        for flow in result.flows:
            assert flow.source.startswith("datacenter")
            assert flow.destination.startswith("edge")

    def test_max_flow_analysis_rejects_unknown_params(
        self, simple_network: Network
    ) -> None:
        """Test that unknown parameters raise TypeError."""
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            max_flow_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source="datacenter.*",
                target="edge.*",
                unknown_param="should_fail",
            )

    def test_max_flow_analysis_empty_result(self, simple_network: Network) -> None:
        """Test max_flow_analysis with no matching nodes raises an error."""
        # Unmatched selectors raise ValueError instead of returning an empty result
        with pytest.raises(ValueError, match="No source nodes found"):
            max_flow_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source="nonexistent.*",
                target="also_nonexistent.*",
            )


class TestDemandPlacementAnalysis:
    """Test demand_placement_analysis function."""

    # Uses diamond_network fixture from conftest.py

    def test_demand_placement_analysis_basic(self, diamond_network: Network) -> None:
        """A 50-unit pairwise demand on the diamond network is fully placed."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 50.0,
                "mode": "pairwise",
                "priority": 0,
            },
        ]

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

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
                "source": "A",
                "target": "B",
                "volume": 0.0,
            }
        ]

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1
        assert result.flows[0].placed == 0.0
        summary = result.summary
        assert summary.total_demand == 0.0
        assert summary.total_placed == 0.0
        assert summary.overall_ratio == 1.0


class TestDemandPlacementWithContextCaching:
    """Test demand_placement_analysis with pre-built context caching."""

    # Uses diamond_network fixture from conftest.py

    def test_context_caching_pairwise_mode(self, diamond_network: Network) -> None:
        """Context caching works with pairwise mode."""
        from ngraph.analysis.functions import build_demand_placement_inputs

        demands_config = [
            {
                "id": "stable-pairwise-id",
                "source": "A",
                "target": "D",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        # Build context once
        ctx, _, _ = build_demand_placement_inputs(diamond_network, demands_config)

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            context=ctx,
        )

        assert result.summary.total_placed == 50.0
        assert result.summary.overall_ratio == 1.0

    def test_context_caching_combine_mode(self, diamond_network: Network) -> None:
        """Context caching works with combine mode (uses pseudo nodes)."""
        from ngraph.analysis.functions import build_demand_placement_inputs

        demands_config = [
            {
                "id": "stable-combine-id",
                "source": "[AB]",
                "target": "[CD]",
                "volume": 50.0,
                "mode": "combine",
            },
        ]

        # Build context once
        ctx, _, _ = build_demand_placement_inputs(diamond_network, demands_config)

        # Combine mode needs the pre-built context's pseudo nodes to match this run
        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            context=ctx,
        )

        assert result.summary.total_placed == 50.0
        assert result.summary.overall_ratio == 1.0

    def test_context_caching_combine_multiple_iterations(
        self, diamond_network: Network
    ) -> None:
        """Context can be reused for multiple analysis iterations."""
        from ngraph.analysis.functions import build_demand_placement_inputs

        demands_config = [
            {
                "id": "reusable-id",
                "source": "[AB]",
                "target": "[CD]",
                "volume": 50.0,
                "mode": "combine",
            },
        ]

        ctx, _, _ = build_demand_placement_inputs(diamond_network, demands_config)

        # Run multiple iterations with different exclusions
        for excluded in [set(), {"B"}, {"C"}]:
            result = demand_placement_analysis(
                network=diamond_network,
                excluded_nodes=excluded,
                excluded_links=set(),
                demands_config=demands_config,
                context=ctx,
            )
            assert isinstance(result, FlowIterationResult)

    def test_context_caching_without_id_works(self, diamond_network: Network) -> None:
        """Context caching works without explicit IDs (deterministic ids).

        A config without "id" must not get a fresh uuid on every
        reconstruction: pseudo node names would diverge from the pre-built
        context and analysis would fail with KeyError. IDs derived from
        source/target/position keep them stable.
        """
        from ngraph.analysis.functions import build_demand_placement_inputs

        # Config without explicit ID - deterministic ID is derived
        demands_config = [
            {
                "source": "[AB]",
                "target": "[CD]",
                "volume": 50.0,
                "mode": "combine",
            },
        ]

        ctx, _, _ = build_demand_placement_inputs(diamond_network, demands_config)

        result = demand_placement_analysis(
            network=diamond_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            context=ctx,
        )

        assert result.summary.total_placed == 50.0
        assert result.summary.overall_ratio == 1.0


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
        """A 2-link chain reports max flow 10 and both saturated links as critical."""
        result = sensitivity_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source="A",
            target="C",
            mode="combine",
        )

        # Returns FlowIterationResult with sensitivity data
        assert isinstance(result, FlowIterationResult)
        assert len(result.flows) == 1

        entry = result.flows[0]
        assert entry.source == "A"
        assert entry.destination == "C"
        assert entry.demand == entry.placed == 10.0  # max flow value
        assert entry.dropped == 0.0

        assert "sensitivity" in entry.data
        sensitivity = entry.data["sensitivity"]
        assert isinstance(sensitivity, dict)
        # Both edges A->B and B->C are critical (saturated)
        assert len(sensitivity) == 2

    def test_sensitivity_analysis_empty_result(self, simple_network: Network) -> None:
        """Test sensitivity_analysis with empty result."""
        with pytest.raises(ValueError, match="No source nodes found"):
            sensitivity_analysis(
                network=simple_network,
                excluded_nodes=set(),
                excluded_links=set(),
                source="nonexistent.*",
                target="also_nonexistent.*",
            )

    def test_sensitivity_analysis_single_pass(
        self, simple_network: Network, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Computes flow and sensitivity in one pass (one mask pair per call)."""
        from ngraph.analysis.context import AnalysisContext
        from ngraph.analysis.functions import build_maxflow_context

        ctx = build_maxflow_context(simple_network, "A", "C", mode="combine")

        calls = {"node_mask": 0}
        original = AnalysisContext.build_node_mask

        def counting(self: AnalysisContext, excluded_nodes=None):
            calls["node_mask"] += 1
            return original(self, excluded_nodes)

        monkeypatch.setattr(AnalysisContext, "build_node_mask", counting)

        result = sensitivity_analysis(
            network=simple_network,
            excluded_nodes=set(),
            excluded_links=set(),
            source="A",
            target="C",
            context=ctx,
        )

        # One combined pass (max_flow + sensitivity) builds a single mask.
        assert calls["node_mask"] == 1
        entry = result.flows[0]
        assert entry.demand == entry.placed == 10.0
        assert len(entry.data["sensitivity"]) == 2
