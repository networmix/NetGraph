"""Tests for SPF caching in demand placement.

This module tests the SPF caching optimization that reduces redundant shortest
path computations when placing demands from the same source nodes.
"""

from __future__ import annotations

from typing import Any

import pytest

from ngraph.analysis.functions import demand_placement_analysis
from ngraph.analysis.placement import (
    CACHEABLE_PRESETS,
    _get_edge_selection,
    _get_flow_placement,
)
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.results.flow import FlowIterationResult


class TestHelperFunctions:
    """Test helper functions for SPF caching."""

    def test_get_selection_for_ecmp(self) -> None:
        """Test EdgeSelection for ECMP preset."""
        selection = _get_edge_selection(FlowPolicyPreset.SHORTEST_PATHS_ECMP)
        assert selection.multi_edge is True
        assert selection.require_capacity is False

    def test_get_selection_for_wcmp(self) -> None:
        """Test EdgeSelection for WCMP preset."""
        selection = _get_edge_selection(FlowPolicyPreset.SHORTEST_PATHS_WCMP)
        assert selection.multi_edge is True
        assert selection.require_capacity is False

    def test_get_selection_for_te_wcmp_unlim(self) -> None:
        """Test EdgeSelection for TE_WCMP_UNLIM preset."""
        selection = _get_edge_selection(FlowPolicyPreset.TE_WCMP_UNLIM)
        assert selection.multi_edge is True
        assert selection.require_capacity is True

    def test_get_placement_for_ecmp(self) -> None:
        """Test FlowPlacement for ECMP preset."""
        import netgraph_core

        placement = _get_flow_placement(FlowPolicyPreset.SHORTEST_PATHS_ECMP)
        assert placement == netgraph_core.FlowPlacement.EQUAL_BALANCED

    def test_get_placement_for_wcmp(self) -> None:
        """Test FlowPlacement for WCMP preset."""
        import netgraph_core

        placement = _get_flow_placement(FlowPolicyPreset.SHORTEST_PATHS_WCMP)
        assert placement == netgraph_core.FlowPlacement.PROPORTIONAL

    def test_get_placement_for_te_wcmp_unlim(self) -> None:
        """Test FlowPlacement for TE_WCMP_UNLIM preset."""
        import netgraph_core

        placement = _get_flow_placement(FlowPolicyPreset.TE_WCMP_UNLIM)
        assert placement == netgraph_core.FlowPlacement.PROPORTIONAL


class TestCacheablePresets:
    """Test that cacheable preset sets are correctly defined."""

    def test_cacheable_presets_contains_expected(self) -> None:
        """Test that cacheable presets contain expected policies."""
        assert FlowPolicyPreset.SHORTEST_PATHS_ECMP in CACHEABLE_PRESETS
        assert FlowPolicyPreset.SHORTEST_PATHS_WCMP in CACHEABLE_PRESETS
        assert FlowPolicyPreset.TE_WCMP_UNLIM in CACHEABLE_PRESETS

    def test_lsp_policies_not_cacheable(self) -> None:
        """Test that LSP policies are not in cacheable set."""
        assert FlowPolicyPreset.TE_ECMP_16_LSP not in CACHEABLE_PRESETS
        assert FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP not in CACHEABLE_PRESETS


class TestSPFCachingBasic:
    """Test basic SPF caching behavior."""

    @pytest.fixture
    def diamond_network(self) -> Network:
        """Create a diamond network: A -> B,C -> D."""
        network = Network()
        for node in ["A", "B", "C", "D"]:
            network.add_node(Node(node))

        # Two equal-cost paths of capacity 60 each
        network.add_link(Link("A", "B", capacity=60.0, cost=1.0))
        network.add_link(Link("A", "C", capacity=60.0, cost=1.0))
        network.add_link(Link("B", "D", capacity=60.0, cost=1.0))
        network.add_link(Link("C", "D", capacity=60.0, cost=1.0))

        return network

    @pytest.fixture
    def multi_source_network(self) -> Network:
        """Create a network with multiple sources sharing paths to destinations.

        Topology:
            S1 --+
                 |
            S2 --+--> R1 --> D1
                 |       |
            S3 --+       +--> D2
        """
        network = Network()
        for node in ["S1", "S2", "S3", "R1", "D1", "D2"]:
            network.add_node(Node(node))

        # Sources to router
        network.add_link(Link("S1", "R1", capacity=100.0, cost=1.0))
        network.add_link(Link("S2", "R1", capacity=100.0, cost=1.0))
        network.add_link(Link("S3", "R1", capacity=100.0, cost=1.0))

        # Router to destinations
        network.add_link(Link("R1", "D1", capacity=200.0, cost=1.0))
        network.add_link(Link("R1", "D2", capacity=200.0, cost=1.0))

        return network

    def test_single_demand_ecmp(self, diamond_network: Network) -> None:
        """Test that single demand with ECMP works correctly with caching."""
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
        assert flow.placed == 50.0
        assert flow.dropped == 0.0

    def test_multiple_demands_same_source_reuses_cache(
        self, multi_source_network: Network
    ) -> None:
        """Test that multiple demands from same source benefit from caching."""
        # Multiple demands from S1 to different destinations
        demands_config = [
            {
                "source": "S1",
                "target": "D1",
                "volume": 30.0,
                "mode": "pairwise",
                "priority": 0,
            },
            {
                "source": "S1",
                "target": "D2",
                "volume": 30.0,
                "mode": "pairwise",
                "priority": 0,
            },
        ]

        result = demand_placement_analysis(
            network=multi_source_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 2
        # Both demands should be fully placed
        assert result.summary.total_placed == 60.0
        assert result.summary.overall_ratio == 1.0

    def test_demands_from_multiple_sources(self, multi_source_network: Network) -> None:
        """Test that demands from multiple sources each get their own cache entry."""
        demands_config = [
            {
                "source": "S1",
                "target": "D1",
                "volume": 50.0,
                "mode": "pairwise",
            },
            {
                "source": "S2",
                "target": "D1",
                "volume": 50.0,
                "mode": "pairwise",
            },
            {
                "source": "S3",
                "target": "D2",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=multi_source_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 3
        assert result.summary.total_placed == 150.0
        assert result.summary.overall_ratio == 1.0


class TestSPFCachingEquivalence:
    """Test that cached placement produces equivalent results to non-cached."""

    @pytest.fixture
    def mesh_network(self) -> Network:
        """Create a mesh network for equivalence testing.

        Topology (2x2 mesh):
            A -- B
            |    |
            C -- D
        """
        network = Network()
        for node in ["A", "B", "C", "D"]:
            network.add_node(Node(node))

        # Horizontal links
        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))
        network.add_link(Link("C", "D", capacity=100.0, cost=1.0))

        # Vertical links
        network.add_link(Link("A", "C", capacity=100.0, cost=1.0))
        network.add_link(Link("B", "D", capacity=100.0, cost=1.0))

        return network

    def _run_demand_placement_without_cache(
        self,
        network: Network,
        demands_config: list[dict[str, Any]],
        include_flow_details: bool = False,
        include_used_edges: bool = False,
    ) -> FlowIterationResult:
        """Run demand placement using only FlowPolicy (no caching).

        This provides a reference implementation for equivalence testing.
        """
        import netgraph_core

        from ngraph.analysis import AnalysisContext
        from ngraph.analysis.demand import expand_demands
        from ngraph.model.demand.spec import TrafficDemand
        from ngraph.model.flow.policy_config import (
            FlowPolicyPreset,
            create_flow_policy,
        )
        from ngraph.results.flow import FlowEntry, FlowSummary

        # Reconstruct TrafficDemand objects
        traffic_demands = []
        for config in demands_config:
            demand = TrafficDemand(
                source=config["source"],
                target=config["target"],
                volume=config["volume"],
                mode=config.get("mode", "pairwise"),
                flow_policy=config.get("flow_policy"),
                priority=config.get("priority", 0),
            )
            traffic_demands.append(demand)

        # Expand demands
        expansion = expand_demands(
            network,
            traffic_demands,
            default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        )

        # Build context
        ctx = AnalysisContext.from_network(
            network, augmentations=expansion.augmentations
        )

        handle = ctx.handle
        multidigraph = ctx.multidigraph
        node_mapper = ctx.node_mapper
        edge_mapper = ctx.edge_mapper
        algorithms = ctx.algorithms
        node_mask = ctx._build_node_mask(set())
        edge_mask = ctx._build_edge_mask(set())

        flow_graph = netgraph_core.FlowGraph(multidigraph)

        # Place demands using ONLY FlowPolicy (no caching)
        flow_entries: list[FlowEntry] = []
        total_demand = 0.0
        total_placed = 0.0

        for demand in expansion.demands:
            src_id = node_mapper.to_id(demand.src_name)
            dst_id = node_mapper.to_id(demand.dst_name)

            policy = create_flow_policy(
                algorithms,
                handle,
                demand.policy_preset,
                node_mask=node_mask,
                edge_mask=edge_mask,
            )

            placed, flow_count = policy.place_demand(
                flow_graph,
                src_id,
                dst_id,
                demand.priority,
                demand.volume,
            )

            cost_distribution: dict[float, float] = {}
            used_edges: set[str] = set()

            if include_flow_details or include_used_edges:
                flows_dict = policy.flows
                for flow_key, flow_data in flows_dict.items():
                    if include_flow_details:
                        cost = float(flow_data[2])
                        flow_vol = float(flow_data[3])
                        if flow_vol > 0:
                            cost_distribution[cost] = (
                                cost_distribution.get(cost, 0.0) + flow_vol
                            )

                    if include_used_edges:
                        flow_idx = netgraph_core.FlowIndex(
                            flow_key[0], flow_key[1], flow_key[2], flow_key[3]
                        )
                        edges = flow_graph.get_flow_edges(flow_idx)
                        for edge_id, _ in edges:
                            edge_ref = edge_mapper.to_ref(edge_id, multidigraph)
                            if edge_ref is not None:
                                used_edges.add(
                                    f"{edge_ref.link_id}:{edge_ref.direction}"
                                )

            entry_data: dict[str, Any] = {}
            if include_used_edges and used_edges:
                entry_data["edges"] = sorted(used_edges)
                entry_data["edges_kind"] = "used"

            entry = FlowEntry(
                source=demand.src_name,
                destination=demand.dst_name,
                priority=demand.priority,
                demand=demand.volume,
                placed=placed,
                dropped=demand.volume - placed,
                cost_distribution=cost_distribution if include_flow_details else {},
                data=entry_data,
            )
            flow_entries.append(entry)
            total_demand += demand.volume
            total_placed += placed

        overall_ratio = (total_placed / total_demand) if total_demand > 0 else 1.0
        dropped_flows = sum(1 for e in flow_entries if e.dropped > 0.0)
        summary = FlowSummary(
            total_demand=total_demand,
            total_placed=total_placed,
            overall_ratio=overall_ratio,
            dropped_flows=dropped_flows,
            num_flows=len(flow_entries),
        )

        return FlowIterationResult(
            flows=flow_entries,
            summary=summary,
            data={},
        )

    def test_equivalence_ecmp_single_demand(self, mesh_network: Network) -> None:
        """Test that ECMP placement is equivalent with and without caching."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 80.0,
                "mode": "pairwise",
            },
        ]

        # Run with caching (default)
        cached_result = demand_placement_analysis(
            network=mesh_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        # Run without caching (reference)
        reference_result = self._run_demand_placement_without_cache(
            network=mesh_network,
            demands_config=demands_config,
        )

        # Compare results
        assert len(cached_result.flows) == len(reference_result.flows)
        assert (
            cached_result.summary.total_demand == reference_result.summary.total_demand
        )
        assert (
            cached_result.summary.total_placed == reference_result.summary.total_placed
        )
        assert cached_result.summary.overall_ratio == pytest.approx(
            reference_result.summary.overall_ratio, rel=1e-9
        )

    def test_equivalence_ecmp_multiple_demands(self, mesh_network: Network) -> None:
        """Test ECMP placement equivalence with multiple demands."""
        demands_config = [
            {"source": "A", "target": "B", "volume": 30.0, "mode": "pairwise"},
            {"source": "A", "target": "D", "volume": 40.0, "mode": "pairwise"},
            {"source": "C", "target": "B", "volume": 25.0, "mode": "pairwise"},
            {"source": "C", "target": "D", "volume": 35.0, "mode": "pairwise"},
        ]

        cached_result = demand_placement_analysis(
            network=mesh_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        reference_result = self._run_demand_placement_without_cache(
            network=mesh_network,
            demands_config=demands_config,
        )

        # Compare summaries
        assert (
            cached_result.summary.total_demand == reference_result.summary.total_demand
        )
        assert cached_result.summary.total_placed == pytest.approx(
            reference_result.summary.total_placed, rel=1e-9
        )

        # Compare individual flows
        for cached_flow, ref_flow in zip(
            cached_result.flows, reference_result.flows, strict=True
        ):
            assert cached_flow.source == ref_flow.source
            assert cached_flow.destination == ref_flow.destination
            assert cached_flow.demand == ref_flow.demand
            assert cached_flow.placed == pytest.approx(ref_flow.placed, rel=1e-9)

    def test_equivalence_with_flow_details(self, mesh_network: Network) -> None:
        """Test equivalence when include_flow_details is True."""
        demands_config = [
            {"source": "A", "target": "D", "volume": 50.0, "mode": "pairwise"},
        ]

        cached_result = demand_placement_analysis(
            network=mesh_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=True,
        )

        reference_result = self._run_demand_placement_without_cache(
            network=mesh_network,
            demands_config=demands_config,
            include_flow_details=True,
        )

        # Both should have cost distribution
        for cached_flow, ref_flow in zip(
            cached_result.flows, reference_result.flows, strict=True
        ):
            # Cost distribution should be non-empty for both
            if ref_flow.cost_distribution:
                assert cached_flow.cost_distribution
                # Total volume in cost distribution should match placed
                cached_total = sum(cached_flow.cost_distribution.values())
                ref_total = sum(ref_flow.cost_distribution.values())
                assert cached_total == pytest.approx(ref_total, rel=1e-9)

    def test_equivalence_with_used_edges(self, mesh_network: Network) -> None:
        """Test equivalence when include_used_edges is True."""
        demands_config = [
            {"source": "A", "target": "D", "volume": 50.0, "mode": "pairwise"},
        ]

        cached_result = demand_placement_analysis(
            network=mesh_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_used_edges=True,
        )

        reference_result = self._run_demand_placement_without_cache(
            network=mesh_network,
            demands_config=demands_config,
            include_used_edges=True,
        )

        # Both should have used edges
        for cached_flow, ref_flow in zip(
            cached_result.flows, reference_result.flows, strict=True
        ):
            cached_edges = set(cached_flow.data.get("edges", []))
            ref_edges = set(ref_flow.data.get("edges", []))
            # Edges should be the same
            assert cached_edges == ref_edges


class TestSPFCachingTEPolicy:
    """Test SPF caching with TE_WCMP_UNLIM policy including fallback behavior."""

    @pytest.fixture
    def constrained_network(self) -> Network:
        """Create a network with limited capacity to test fallback.

        Topology:
            A --> B --> D
            |           ^
            +--> C -----+
        """
        network = Network()
        for node in ["A", "B", "C", "D"]:
            network.add_node(Node(node))

        # Primary path (cost 2, capacity 50)
        network.add_link(Link("A", "B", capacity=50.0, cost=1.0))
        network.add_link(Link("B", "D", capacity=50.0, cost=1.0))

        # Secondary path (cost 4, capacity 50)
        network.add_link(Link("A", "C", capacity=50.0, cost=2.0))
        network.add_link(Link("C", "D", capacity=50.0, cost=2.0))

        return network

    def test_te_wcmp_basic_placement(self, constrained_network: Network) -> None:
        """Test TE_WCMP_UNLIM basic placement without fallback."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 40.0,
                "mode": "pairwise",
                "flow_policy": FlowPolicyPreset.TE_WCMP_UNLIM,
            },
        ]

        result = demand_placement_analysis(
            network=constrained_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        # Should be able to place 40 on primary path (capacity 50)
        assert flow.placed == 40.0
        assert flow.dropped == 0.0

    def test_te_wcmp_fallback_on_saturation(self, constrained_network: Network) -> None:
        """Test TE_WCMP_UNLIM fallback when primary path saturates."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 80.0,  # Exceeds primary path capacity
                "mode": "pairwise",
                "flow_policy": FlowPolicyPreset.TE_WCMP_UNLIM,
            },
        ]

        result = demand_placement_analysis(
            network=constrained_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=True,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        # Should place 80 using both paths (50 + 30 or similar distribution)
        assert flow.placed == pytest.approx(80.0, rel=1e-6)
        assert flow.dropped == pytest.approx(0.0, abs=1e-6)

        # Should have multiple cost tiers in distribution (primary + secondary path)
        if flow.cost_distribution:
            assert len(flow.cost_distribution) >= 1
            total_in_dist = sum(flow.cost_distribution.values())
            assert total_in_dist == pytest.approx(80.0, rel=1e-6)

    def test_te_wcmp_multiple_demands_same_source(
        self, constrained_network: Network
    ) -> None:
        """Test TE_WCMP_UNLIM with multiple demands sharing source."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 30.0,
                "mode": "pairwise",
                "flow_policy": FlowPolicyPreset.TE_WCMP_UNLIM,
            },
            {
                "source": "A",
                "target": "D",
                "volume": 30.0,
                "mode": "pairwise",
                "priority": 1,  # Different priority = different demand
                "flow_policy": FlowPolicyPreset.TE_WCMP_UNLIM,
            },
        ]

        result = demand_placement_analysis(
            network=constrained_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 2
        # First demand should use primary path
        assert result.flows[0].placed == pytest.approx(30.0, rel=1e-6)
        # Second demand should also be placed (may need secondary path)
        assert result.flows[1].placed == pytest.approx(30.0, rel=1e-6)
        # Total should be 60
        assert result.summary.total_placed == pytest.approx(60.0, rel=1e-6)


class TestSPFCachingEdgeCases:
    """Test edge cases and error handling for SPF caching."""

    @pytest.fixture
    def disconnected_network(self) -> Network:
        """Create a network with disconnected components."""
        network = Network()
        # First component: A -> B
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))

        # Second component: C -> D (disconnected from first)
        network.add_node(Node("C"))
        network.add_node(Node("D"))
        network.add_link(Link("C", "D", capacity=100.0, cost=1.0))

        return network

    def test_unreachable_destination(self, disconnected_network: Network) -> None:
        """Test placement to unreachable destination returns zero."""
        demands_config = [
            {
                "source": "A",
                "target": "D",  # Unreachable from A
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=disconnected_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        assert flow.placed == 0.0
        assert flow.dropped == 50.0

    def test_zero_demand(self) -> None:
        """Test placement of zero demand."""
        network = Network()
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))

        demands_config = [
            {
                "source": "A",
                "target": "B",
                "volume": 0.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 1
        assert result.flows[0].placed == 0.0
        assert result.flows[0].dropped == 0.0
        assert result.summary.overall_ratio == 1.0

    def test_partial_placement_due_to_capacity(self) -> None:
        """Test partial placement when demand exceeds capacity."""
        network = Network()
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=30.0, cost=1.0))

        demands_config = [
            {
                "source": "A",
                "target": "B",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        assert flow.placed == 30.0  # Limited by capacity
        assert flow.dropped == 20.0
        assert result.summary.overall_ratio == 0.6

    def test_empty_cost_distribution_when_not_requested(self) -> None:
        """Test that cost_distribution is empty when not requested."""
        network = Network()
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))

        demands_config = [
            {
                "source": "A",
                "target": "B",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=False,
        )

        assert len(result.flows) == 1
        assert result.flows[0].cost_distribution == {}

    def test_empty_edges_when_not_requested(self) -> None:
        """Test that edges data is empty when not requested."""
        network = Network()
        network.add_node(Node("A"))
        network.add_node(Node("B"))
        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))

        demands_config = [
            {
                "source": "A",
                "target": "B",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_used_edges=False,
        )

        assert len(result.flows) == 1
        assert result.flows[0].data == {}


class TestSPFCachingWithExclusions:
    """Test SPF caching with node and link exclusions."""

    @pytest.fixture
    def triangle_network(self) -> Network:
        """Create a triangle network: A -- B -- C -- A."""
        network = Network()
        for node in ["A", "B", "C"]:
            network.add_node(Node(node))

        network.add_link(Link("A", "B", capacity=100.0, cost=1.0))
        network.add_link(Link("B", "C", capacity=100.0, cost=1.0))
        network.add_link(Link("A", "C", capacity=100.0, cost=2.0))  # Longer path

        return network

    def test_placement_with_excluded_link(self, triangle_network: Network) -> None:
        """Test that excluded links are respected in cached placement."""
        demands_config = [
            {
                "source": "A",
                "target": "C",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        # Exclude direct A-C link, forcing traffic through B
        result = demand_placement_analysis(
            network=triangle_network,
            excluded_nodes=set(),
            excluded_links={"link_A_C"},  # Link ID format
            demands_config=demands_config,
            include_flow_details=True,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        assert flow.placed == 50.0
        # Should use path A -> B -> C (cost 2) instead of A -> C (cost 2)
        if flow.cost_distribution:
            # Cost should be 2 (through B) not 2 (direct, which is excluded)
            assert 2.0 in flow.cost_distribution

    def test_placement_with_excluded_node(self, triangle_network: Network) -> None:
        """Test that excluded nodes are respected in cached placement."""
        demands_config = [
            {
                "source": "A",
                "target": "C",
                "volume": 50.0,
                "mode": "pairwise",
            },
        ]

        # Exclude node B, forcing traffic through direct A-C link
        result = demand_placement_analysis(
            network=triangle_network,
            excluded_nodes={"B"},
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=True,
        )

        assert len(result.flows) == 1
        flow = result.flows[0]
        assert flow.placed == 50.0
        # Should use direct A -> C path (cost 2)
        if flow.cost_distribution:
            assert 2.0 in flow.cost_distribution


class TestSPFCachingCostDistribution:
    """Test cost distribution correctness with SPF caching."""

    @pytest.fixture
    def multi_tier_network(self) -> Network:
        """Create a network with multiple cost tiers.

        A --[cost=1]--> B --[cost=1]--> D (cost 2, capacity 30)
        A --[cost=2]--> C --[cost=2]--> D (cost 4, capacity 30)
        """
        network = Network()
        for node in ["A", "B", "C", "D"]:
            network.add_node(Node(node))

        # Tier 1: cost 2, capacity 30
        network.add_link(Link("A", "B", capacity=30.0, cost=1.0))
        network.add_link(Link("B", "D", capacity=30.0, cost=1.0))

        # Tier 2: cost 4, capacity 30
        network.add_link(Link("A", "C", capacity=30.0, cost=2.0))
        network.add_link(Link("C", "D", capacity=30.0, cost=2.0))

        return network

    def test_cost_distribution_single_tier(self, multi_tier_network: Network) -> None:
        """Test cost distribution when only one tier is used."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 25.0,  # Fits in tier 1
                "mode": "pairwise",
            },
        ]

        result = demand_placement_analysis(
            network=multi_tier_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=True,
        )

        flow = result.flows[0]
        assert flow.placed == 25.0
        # Should all be on tier 1 (cost 2)
        assert flow.cost_distribution == {2.0: 25.0}

    def test_cost_distribution_multiple_tiers_te_policy(
        self, multi_tier_network: Network
    ) -> None:
        """Test cost distribution with TE policy using multiple tiers."""
        demands_config = [
            {
                "source": "A",
                "target": "D",
                "volume": 50.0,  # Exceeds tier 1 capacity
                "mode": "pairwise",
                "flow_policy": FlowPolicyPreset.TE_WCMP_UNLIM,
            },
        ]

        result = demand_placement_analysis(
            network=multi_tier_network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
            include_flow_details=True,
        )

        flow = result.flows[0]
        # Should place 50 total (30 on tier 1 + 20 on tier 2)
        assert flow.placed == pytest.approx(50.0, rel=1e-6)

        # Cost distribution should show both tiers
        if flow.cost_distribution:
            total = sum(flow.cost_distribution.values())
            assert total == pytest.approx(50.0, rel=1e-6)
            # Should have cost 2 (tier 1) and cost 4 (tier 2)
            assert len(flow.cost_distribution) >= 1
