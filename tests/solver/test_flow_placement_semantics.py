"""Comprehensive tests validating IP and TE flow placement semantics with ECMP and WCMP.

This test suite validates that NetGraph correctly implements the distinct behavioral
semantics of IP routing vs Traffic Engineering, and ECMP vs WCMP flow placement.

Key distinctions tested:
1. IP routing (require_capacity=False): Routes based on costs only, ignoring capacity
2. TE routing (require_capacity=True): Routes adapt to residual capacity
3. ECMP (EQUAL_BALANCED): Equal splitting across equal-cost paths
4. WCMP (PROPORTIONAL): Capacity-proportional splitting across equal-cost paths

Tests use a shared topology where different settings produce measurably different results,
validating actual placement behavior (not just API correctness).
"""

from __future__ import annotations

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.maxflow import max_flow, max_flow_with_details
from ngraph.types.base import FlowPlacement


def _unbalanced_parallel_paths() -> Network:
    """Create network with parallel paths of equal cost but different capacities.

    This topology is specifically designed to expose differences between:
    - ECMP vs WCMP: Different capacities mean WCMP can utilize more flow
    - IP vs TE: Multiple augmentations will behave differently

    Topology:
        S -> A (cap 10, cost 1) -> T (cap 10, cost 1)  [path 1: cost 2, cap 10]
        S -> B (cap 30, cost 1) -> T (cap 30, cost 1)  [path 2: cost 2, cap 30]
        S -> C (cap 50, cost 1) -> T (cap 50, cost 1)  [path 3: cost 2, cap 50]

    All paths have equal cost (2), but different capacities (10, 30, 50).
    Total capacity: 90
    """
    net = Network()
    for name in ["S", "A", "B", "C", "T"]:
        net.add_node(Node(name))

    # Path 1: S -> A -> T (cap 10)
    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))

    # Path 2: S -> B -> T (cap 30)
    net.add_link(Link("S", "B", capacity=30.0, cost=1.0))
    net.add_link(Link("B", "T", capacity=30.0, cost=1.0))

    # Path 3: S -> C -> T (cap 50)
    net.add_link(Link("S", "C", capacity=50.0, cost=1.0))
    net.add_link(Link("C", "T", capacity=50.0, cost=1.0))

    return net


def _multi_tier_unbalanced() -> Network:
    """Create network with multiple cost tiers and unbalanced capacities within each tier.

    This topology tests:
    - IP shortest_path mode: should only use tier 1
    - TE progressive mode: should use multiple tiers when tier 1 saturates
    - ECMP vs WCMP within each tier

    Topology:
        Tier 1 (cost 10):
            S -> A1 (cap 20, cost 5) -> T (cap 20, cost 5)
            S -> A2 (cap 40, cost 5) -> T (cap 40, cost 5)
        Tier 2 (cost 20):
            S -> B1 (cap 30, cost 10) -> T (cap 30, cost 10)
            S -> B2 (cap 60, cost 10) -> T (cap 60, cost 10)
    """
    net = Network()
    for name in ["S", "A1", "A2", "B1", "B2", "T"]:
        net.add_node(Node(name))

    # Tier 1: cost 10, total cap 60
    net.add_link(Link("S", "A1", capacity=20.0, cost=5.0))
    net.add_link(Link("A1", "T", capacity=20.0, cost=5.0))
    net.add_link(Link("S", "A2", capacity=40.0, cost=5.0))
    net.add_link(Link("A2", "T", capacity=40.0, cost=5.0))

    # Tier 2: cost 20, total cap 90
    net.add_link(Link("S", "B1", capacity=30.0, cost=10.0))
    net.add_link(Link("B1", "T", capacity=30.0, cost=10.0))
    net.add_link(Link("S", "B2", capacity=60.0, cost=10.0))
    net.add_link(Link("B2", "T", capacity=60.0, cost=10.0))

    return net


class TestECMPvsWCMPSemantics:
    """Test ECMP vs WCMP placement on unbalanced parallel paths."""

    def test_ecmp_equal_split_on_unbalanced_paths(self):
        """ECMP should split flow equally across paths, leaving capacity unused on larger paths."""
        net = _unbalanced_parallel_paths()

        # ECMP: equal split across 3 paths
        # With equal splitting, the smallest path (cap 10) becomes the bottleneck
        # Each path can carry at most 10 units (limited by smallest path)
        # Total: 3 * 10 = 30 units
        result = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        assert result[("S", "T")] == pytest.approx(30.0, abs=1e-6), (
            "ECMP with equal splitting should be limited by smallest path capacity"
        )

    def test_wcmp_proportional_split_on_unbalanced_paths(self):
        """WCMP should split flow proportionally to capacity, fully utilizing all paths."""
        net = _unbalanced_parallel_paths()

        # WCMP: proportional split based on capacity
        # Path 1: 10 units (10 / 90 = 11.1%)
        # Path 2: 30 units (30 / 90 = 33.3%)
        # Path 3: 50 units (50 / 90 = 55.6%)
        # Total: 90 units (full utilization)
        result = max_flow(
            net, "S", "T", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        assert result[("S", "T")] == pytest.approx(90.0, abs=1e-6), (
            "WCMP with proportional splitting should fully utilize all paths"
        )

    def test_ecmp_vs_wcmp_utilization_gap(self):
        """Verify that WCMP achieves higher utilization than ECMP on unbalanced paths."""
        net = _unbalanced_parallel_paths()

        ecmp_result = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        wcmp_result = max_flow(
            net, "S", "T", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        ecmp_flow = ecmp_result[("S", "T")]
        wcmp_flow = wcmp_result[("S", "T")]

        # WCMP should achieve 3x the flow of ECMP on this topology
        assert wcmp_flow == pytest.approx(3.0 * ecmp_flow, abs=1e-6), (
            f"Expected WCMP ({wcmp_flow}) to be 3x ECMP ({ecmp_flow})"
        )

        # Verify specific values
        assert ecmp_flow == pytest.approx(30.0, abs=1e-6)
        assert wcmp_flow == pytest.approx(90.0, abs=1e-6)


class TestIPvsTE_Semantics:
    """Test IP routing vs Traffic Engineering semantics."""

    def test_ip_shortest_path_single_tier(self):
        """IP shortest_path=True should only use lowest cost tier."""
        net = _multi_tier_unbalanced()

        # IP mode: shortest_path=True, uses only tier 1 (cost 10)
        # Tier 1 capacity: 60 units
        result_ip_ecmp = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        result_ip_wcmp = max_flow(
            net, "S", "T", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        # ECMP on tier 1: limited by smallest path (20)
        # Equal split: 2 * 20 = 40 units
        assert result_ip_ecmp[("S", "T")] == pytest.approx(40.0, abs=1e-6), (
            "IP ECMP should use only tier 1 with equal splitting"
        )

        # WCMP on tier 1: proportional split
        # 20 + 40 = 60 units (full tier 1 utilization)
        assert result_ip_wcmp[("S", "T")] == pytest.approx(60.0, abs=1e-6), (
            "IP WCMP should use only tier 1 with proportional splitting"
        )

    def test_te_progressive_multi_tier(self):
        """TE shortest_path=False should use multiple tiers when lower tiers saturate."""
        net = _multi_tier_unbalanced()

        # TE mode: shortest_path=False, progressive fill across tiers
        # Tier 1: 60 units (fills first)
        # Tier 2: 90 units (fills next)
        # Total: 150 units
        result_te_wcmp = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=False,
        )

        assert result_te_wcmp[("S", "T")] == pytest.approx(150.0, abs=1e-6), (
            "TE WCMP should progressively fill all cost tiers"
        )

        # Verify cost distribution shows both tiers were used
        result_details = max_flow_with_details(
            net,
            "S",
            "T",
            mode="combine",
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=False,
        )

        summary = result_details[("S", "T")]

        # Should have flow at two different cost levels
        assert len(summary.cost_distribution) == 2, "TE mode should use both cost tiers"

        # Tier 1 (cost 10) should have 60 units
        assert 10.0 in summary.cost_distribution
        assert summary.cost_distribution[10.0] == pytest.approx(60.0, abs=1e-6)

        # Tier 2 (cost 20) should have 90 units
        assert 20.0 in summary.cost_distribution
        assert summary.cost_distribution[20.0] == pytest.approx(90.0, abs=1e-6)

    def test_te_ecmp_progressive_multi_tier(self):
        """TE ECMP progressive mode achieves full utilization via multi-round equal splitting.

        In progressive mode with EQUAL_BALANCED, each tier is filled independently in
        separate augmentation rounds. Within each round, EQUAL_BALANCED constrains splitting,
        but across rounds, full capacity is utilized.
        """
        net = _multi_tier_unbalanced()

        result_te_ecmp = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=False,
        )

        # Progressive ECMP fills tiers sequentially with equal splitting per tier:
        # Round 1 (Tier 1): 2 paths with equal splitting → fills both (20 + 40 = 60)
        # Round 2 (Tier 2): 2 paths with equal splitting → fills both (30 + 60 = 90)
        # Total: 150 units (full utilization achieved via multiple rounds)
        assert result_te_ecmp[("S", "T")] == pytest.approx(150.0, abs=1e-6), (
            "TE ECMP progressive mode should achieve full utilization via multi-round placement"
        )


class TestCombinedSemantics:
    """Test combinations of IP/TE and ECMP/WCMP semantics."""

    @pytest.mark.parametrize(
        "shortest_path,flow_placement,expected_flow",
        [
            # IP ECMP: single tier, equal split → limited by smallest path
            (True, FlowPlacement.EQUAL_BALANCED, 40.0),
            # IP WCMP: single tier, proportional split → full tier utilization
            (True, FlowPlacement.PROPORTIONAL, 60.0),
            # TE ECMP: multi-tier, multi-round equal splitting → full utilization
            (False, FlowPlacement.EQUAL_BALANCED, 150.0),
            # TE WCMP: multi-tier, progressive proportional splitting → full utilization
            (False, FlowPlacement.PROPORTIONAL, 150.0),
        ],
    )
    def test_semantic_combinations_on_multi_tier(
        self, shortest_path, flow_placement, expected_flow
    ):
        """Test all four combinations of IP/TE and ECMP/WCMP semantics."""
        net = _multi_tier_unbalanced()

        result = max_flow(
            net, "S", "T", flow_placement=flow_placement, shortest_path=shortest_path
        )

        assert result[("S", "T")] == pytest.approx(expected_flow, abs=1e-6), (
            f"Expected {expected_flow} for shortest_path={shortest_path}, "
            f"flow_placement={flow_placement.name}"
        )

    @pytest.mark.parametrize(
        "shortest_path,flow_placement,expected_flow",
        [
            # IP ECMP: single tier (all equal cost), equal split → limited by smallest
            (True, FlowPlacement.EQUAL_BALANCED, 30.0),
            # IP WCMP: single tier (all equal cost), proportional split → full utilization
            (True, FlowPlacement.PROPORTIONAL, 90.0),
            # TE ECMP: multi-round on single tier → achieves full utilization
            (False, FlowPlacement.EQUAL_BALANCED, 90.0),
            # TE WCMP: progressive on single tier → full utilization
            (False, FlowPlacement.PROPORTIONAL, 90.0),
        ],
    )
    def test_semantic_combinations_on_parallel_paths(
        self, shortest_path, flow_placement, expected_flow
    ):
        """Test all four combinations on parallel paths topology."""
        net = _unbalanced_parallel_paths()

        result = max_flow(
            net, "S", "T", flow_placement=flow_placement, shortest_path=shortest_path
        )

        assert result[("S", "T")] == pytest.approx(expected_flow, abs=1e-6), (
            f"Expected {expected_flow} for shortest_path={shortest_path}, "
            f"flow_placement={flow_placement.name}"
        )


class TestAccountingValidation:
    """Validate that flow accounting is correct across all modes."""

    @pytest.mark.parametrize("shortest_path", [True, False])
    @pytest.mark.parametrize(
        "flow_placement", [FlowPlacement.EQUAL_BALANCED, FlowPlacement.PROPORTIONAL]
    )
    def test_cost_distribution_sums_to_total_flow(self, shortest_path, flow_placement):
        """Verify cost distribution values sum to total flow."""
        net = _multi_tier_unbalanced()

        result = max_flow_with_details(
            net,
            "S",
            "T",
            mode="combine",
            flow_placement=flow_placement,
            shortest_path=shortest_path,
        )

        summary = result[("S", "T")]

        # Sum of cost distribution should equal total flow
        cost_dist_sum = sum(summary.cost_distribution.values())
        assert cost_dist_sum == pytest.approx(summary.total_flow, abs=1e-9), (
            f"Cost distribution sum ({cost_dist_sum}) != total flow ({summary.total_flow})"
        )

    @pytest.mark.parametrize("shortest_path", [True, False])
    @pytest.mark.parametrize(
        "flow_placement", [FlowPlacement.EQUAL_BALANCED, FlowPlacement.PROPORTIONAL]
    )
    def test_flow_results_are_deterministic(self, shortest_path, flow_placement):
        """Verify that flow results are deterministic across multiple runs."""
        net = _unbalanced_parallel_paths()

        results = []
        for _ in range(3):
            result = max_flow(
                net,
                "S",
                "T",
                flow_placement=flow_placement,
                shortest_path=shortest_path,
            )
            results.append(result[("S", "T")])

        # All runs should produce identical results
        assert all(r == pytest.approx(results[0], abs=1e-9) for r in results), (
            f"Non-deterministic results: {results}"
        )


class TestTELSPLimits:
    """Test TE LSP scenarios with limited flow counts.

    These tests validate the behavior when the number of TE LSPs (tunnels) is limited
    while multiple diverse paths exist. Key semantic: with multipath=False and a max
    flow count, each LSP is a distinct tunnel using a single path (MPLS LSP semantics).

    Expected behavior: LSPs should be allocated to maximize throughput by selecting
    the highest-capacity paths.
    """

    def test_4_lsps_on_8_diverse_paths(self):
        """With 4 LSPs and 8 diverse paths, should use the 4 highest-capacity paths.

        This tests the core TE LSP allocation strategy: when LSPs are limited,
        they should be allocated to maximize total throughput by selecting the
        highest-capacity paths.
        """
        import netgraph_core

        from ngraph.adapters.core import build_graph

        # Create 8 diverse paths with different capacities
        # Capacities: 10, 15, 20, 25, 30, 35, 40, 45
        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(8)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        capacities = [10, 15, 20, 25, 30, 35, 40, 45]
        for i, cap in enumerate(capacities):
            # Create path S -> Mi -> T with given capacity
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        # Use netgraph_core directly to create custom FlowPolicy with 4 LSPs
        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        # Create TE LSP config with custom max_flow_count
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False  # Each LSP uses a single path
        config.min_flow_count = 4
        config.max_flow_count = 4  # Exactly 4 LSPs
        config.reoptimize_flows_on_each_placement = True

        policy = netgraph_core.FlowPolicy(algs, graph_handle, config)
        fg = netgraph_core.FlowGraph(multidigraph)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        placed, remaining = policy.place_demand(
            fg, src_id, dst_id, flowClass=0, volume=1000.0
        )

        # With 4 LSPs on 8 paths, should use the 4 highest-capacity paths
        # Highest 4 capacities: 45, 40, 35, 30
        # With ECMP constraint (EQUAL_BALANCED), all LSPs must carry equal volume
        # Limited by smallest selected path: 4 × 30 = 120
        assert placed == pytest.approx(120.0, abs=1e-3), (
            f"Expected 4 LSPs with ECMP constraint (4×30=120), got {placed}"
        )
        assert policy.flow_count() == 4

    def test_2_lsps_on_5_diverse_paths(self):
        """With 2 LSPs and 5 diverse paths, should use the 2 highest-capacity paths."""
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(5)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        # Capacities: 10, 20, 30, 40, 50
        capacities = [10, 20, 30, 40, 50]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False
        config.min_flow_count = 2
        config.max_flow_count = 2
        config.reoptimize_flows_on_each_placement = True

        policy = netgraph_core.FlowPolicy(algs, graph_handle, config)
        fg = netgraph_core.FlowGraph(multidigraph)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        placed, remaining = policy.place_demand(
            fg, src_id, dst_id, flowClass=0, volume=500.0
        )

        # Should use 2 highest-capacity paths: 50, 40
        # With ECMP constraint, all LSPs carry equal volume: 2 × 40 = 80
        assert placed == pytest.approx(80.0, abs=1e-3), (
            f"Expected 2 LSPs with ECMP constraint (2×40=80), got {placed}"
        )
        assert policy.flow_count() == 2

    def test_lsps_equal_to_path_count(self):
        """When LSP count equals path count, should utilize all paths."""
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S", "M1", "M2", "M3", "T"]
        for node in nodes:
            net.add_node(Node(node))

        # 3 paths with capacities 20, 30, 40
        capacities = [20, 30, 40]
        for i, cap in enumerate(capacities, 1):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False
        config.min_flow_count = 3
        config.max_flow_count = 3
        config.reoptimize_flows_on_each_placement = True

        policy = netgraph_core.FlowPolicy(algs, graph_handle, config)
        fg = netgraph_core.FlowGraph(multidigraph)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        placed, remaining = policy.place_demand(
            fg, src_id, dst_id, flowClass=0, volume=500.0
        )

        # Should utilize all 3 paths with capacities 20, 30, 40
        # With ECMP constraint, all LSPs carry equal volume: 3 × 20 = 60
        assert placed == pytest.approx(60.0, abs=1e-3), (
            f"Expected 3 LSPs with ECMP constraint (3×20=60), got {placed}"
        )
        assert policy.flow_count() == 3

    def test_lsp_vs_unlimited_te_comparison(self):
        """Compare limited LSP allocation vs unlimited TE on same topology."""
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(6)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        # 6 paths: 10, 20, 30, 40, 50, 60
        capacities = [10, 20, 30, 40, 50, 60]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        # Test with 3 LSPs
        config_3lsp = netgraph_core.FlowPolicyConfig()
        config_3lsp.path_alg = netgraph_core.PathAlg.SPF
        config_3lsp.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config_3lsp.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config_3lsp.multipath = False
        config_3lsp.min_flow_count = 3
        config_3lsp.max_flow_count = 3
        config_3lsp.reoptimize_flows_on_each_placement = True

        policy_3lsp = netgraph_core.FlowPolicy(algs, graph_handle, config_3lsp)
        fg_3lsp = netgraph_core.FlowGraph(multidigraph)
        placed_3lsp, _ = policy_3lsp.place_demand(
            fg_3lsp, src_id, dst_id, flowClass=0, volume=1000.0
        )

        # Test with unlimited TE
        config_unlim = netgraph_core.FlowPolicyConfig()
        config_unlim.path_alg = netgraph_core.PathAlg.SPF
        config_unlim.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config_unlim.selection = netgraph_core.EdgeSelection(
            multi_edge=True,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config_unlim.min_flow_count = 1
        # max_flow_count defaults to None (unlimited)

        policy_unlim = netgraph_core.FlowPolicy(algs, graph_handle, config_unlim)
        fg_unlim = netgraph_core.FlowGraph(multidigraph)
        placed_unlim, _ = policy_unlim.place_demand(
            fg_unlim, src_id, dst_id, flowClass=0, volume=1000.0
        )

        # 3 LSPs with ECMP constraint on top 3 paths (60, 50, 40): 3 × 40 = 120
        assert placed_3lsp == pytest.approx(120.0, abs=1e-3)
        assert policy_3lsp.flow_count() == 3

        # Unlimited TE: all paths = 10 + 20 + 30 + 40 + 50 + 60 = 210
        assert placed_unlim == pytest.approx(210.0, abs=1e-3)

        # Verify that limited LSPs achieve less than unlimited
        assert placed_3lsp < placed_unlim


class TestTELSPLimitsWCMP:
    """Test TE LSP scenarios with WCMP (proportional splitting).

    These tests validate WCMP behavior with limited LSPs. Unlike ECMP, WCMP allows
    each LSP to carry different volumes proportional to path capacity, achieving
    better utilization without the equal-splitting constraint.
    """

    def test_4_lsps_wcmp_on_8_diverse_paths(self):
        """With 4 WCMP LSPs and 8 diverse paths, should fully utilize 4 highest-capacity paths.

        Unlike ECMP, WCMP allows each LSP to carry volume proportional to its path capacity,
        so total = sum of the 4 highest capacities.
        """
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(8)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        capacities = [10, 15, 20, 25, 30, 35, 40, 45]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        # WCMP TE LSP config
        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL  # WCMP
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False
        config.min_flow_count = 4
        config.max_flow_count = 4
        config.reoptimize_flows_on_each_placement = True

        policy = netgraph_core.FlowPolicy(algs, graph_handle, config)
        fg = netgraph_core.FlowGraph(multidigraph)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        placed, remaining = policy.place_demand(
            fg, src_id, dst_id, flowClass=0, volume=1000.0
        )

        # WCMP: 4 LSPs on top 4 paths can each utilize full path capacity
        # Top 4: 45, 40, 35, 30 → total = 150
        assert placed == pytest.approx(150.0, abs=1e-3), (
            f"Expected 4 WCMP LSPs to fully utilize 4 highest paths (45+40+35+30=150), "
            f"got {placed}"
        )
        assert policy.flow_count() == 4

    def test_wcmp_vs_ecmp_utilization_with_limited_lsps(self):
        """Compare WCMP vs ECMP with limited LSPs to validate utilization difference."""
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(5)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        capacities = [10, 20, 30, 40, 50]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        # Test with ECMP (3 LSPs)
        config_ecmp = netgraph_core.FlowPolicyConfig()
        config_ecmp.path_alg = netgraph_core.PathAlg.SPF
        config_ecmp.flow_placement = netgraph_core.FlowPlacement.EQUAL_BALANCED
        config_ecmp.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config_ecmp.multipath = False
        config_ecmp.min_flow_count = 3
        config_ecmp.max_flow_count = 3
        config_ecmp.reoptimize_flows_on_each_placement = True

        policy_ecmp = netgraph_core.FlowPolicy(algs, graph_handle, config_ecmp)
        fg_ecmp = netgraph_core.FlowGraph(multidigraph)
        placed_ecmp, _ = policy_ecmp.place_demand(
            fg_ecmp, src_id, dst_id, flowClass=0, volume=500.0
        )

        # Test with WCMP (3 LSPs)
        config_wcmp = netgraph_core.FlowPolicyConfig()
        config_wcmp.path_alg = netgraph_core.PathAlg.SPF
        config_wcmp.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config_wcmp.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config_wcmp.multipath = False
        config_wcmp.min_flow_count = 3
        config_wcmp.max_flow_count = 3
        config_wcmp.reoptimize_flows_on_each_placement = True

        policy_wcmp = netgraph_core.FlowPolicy(algs, graph_handle, config_wcmp)
        fg_wcmp = netgraph_core.FlowGraph(multidigraph)
        placed_wcmp, _ = policy_wcmp.place_demand(
            fg_wcmp, src_id, dst_id, flowClass=0, volume=500.0
        )

        # ECMP: 3 LSPs on top 3 paths (50, 40, 30) with equal constraint: 3 × 30 = 90
        assert placed_ecmp == pytest.approx(90.0, abs=1e-3)

        # WCMP: 3 LSPs on top 3 paths with proportional splitting: 50 + 40 + 30 = 120
        assert placed_wcmp == pytest.approx(120.0, abs=1e-3)

        # WCMP should achieve better utilization than ECMP
        assert placed_wcmp > placed_ecmp

        # Verify the utilization ratio
        utilization_ratio = placed_wcmp / placed_ecmp
        assert utilization_ratio == pytest.approx(120.0 / 90.0, abs=0.01), (
            f"Expected WCMP to achieve ~1.33x ECMP utilization, got {utilization_ratio}"
        )

    def test_2_wcmp_lsps_on_5_diverse_paths(self):
        """With 2 WCMP LSPs, should fully utilize 2 highest-capacity paths."""
        import netgraph_core

        from ngraph.adapters.core import build_graph

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(5)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        capacities = [10, 20, 30, 40, 50]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        backend = netgraph_core.Backend.cpu()
        algs = netgraph_core.Algorithms(backend)
        graph_handle, multidigraph, _, node_mapper = build_graph(net)

        config = netgraph_core.FlowPolicyConfig()
        config.path_alg = netgraph_core.PathAlg.SPF
        config.flow_placement = netgraph_core.FlowPlacement.PROPORTIONAL
        config.selection = netgraph_core.EdgeSelection(
            multi_edge=False,
            require_capacity=True,
            tie_break=netgraph_core.EdgeTieBreak.PREFER_HIGHER_RESIDUAL,
        )
        config.multipath = False
        config.min_flow_count = 2
        config.max_flow_count = 2
        config.reoptimize_flows_on_each_placement = True

        policy = netgraph_core.FlowPolicy(algs, graph_handle, config)
        fg = netgraph_core.FlowGraph(multidigraph)

        src_id = node_mapper.to_id("S")
        dst_id = node_mapper.to_id("T")

        placed, _ = policy.place_demand(fg, src_id, dst_id, flowClass=0, volume=500.0)

        # WCMP: 2 LSPs on top 2 paths (50, 40) → 50 + 40 = 90
        assert placed == pytest.approx(90.0, abs=1e-3), (
            f"Expected 2 WCMP LSPs to fully utilize 2 highest paths (50+40=90), got {placed}"
        )
        assert policy.flow_count() == 2


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_path_ecmp_equals_wcmp(self):
        """When there's only one path, ECMP and WCMP should behave identically."""
        net = Network()
        for name in ["A", "B", "C"]:
            net.add_node(Node(name))

        net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
        net.add_link(Link("B", "C", capacity=5.0, cost=1.0))

        result_ecmp = max_flow(
            net,
            "A",
            "C",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        result_wcmp = max_flow(
            net, "A", "C", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        # Both should be limited by bottleneck capacity (5.0)
        assert result_ecmp[("A", "C")] == pytest.approx(5.0, abs=1e-9)
        assert result_wcmp[("A", "C")] == pytest.approx(5.0, abs=1e-9)
        assert result_ecmp[("A", "C")] == pytest.approx(
            result_wcmp[("A", "C")], abs=1e-9
        )

    def test_balanced_parallel_paths_ecmp_equals_wcmp(self):
        """When parallel paths have equal capacity, ECMP and WCMP should produce same results."""
        net = Network()
        for name in ["S", "A", "B", "T"]:
            net.add_node(Node(name))

        # Two paths with equal capacity
        net.add_link(Link("S", "A", capacity=20.0, cost=1.0))
        net.add_link(Link("A", "T", capacity=20.0, cost=1.0))
        net.add_link(Link("S", "B", capacity=20.0, cost=1.0))
        net.add_link(Link("B", "T", capacity=20.0, cost=1.0))

        result_ecmp = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        result_wcmp = max_flow(
            net, "S", "T", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        # Both should achieve full utilization (40.0)
        assert result_ecmp[("S", "T")] == pytest.approx(40.0, abs=1e-9)
        assert result_wcmp[("S", "T")] == pytest.approx(40.0, abs=1e-9)

    def test_zero_capacity_path_ignored(self):
        """Paths with zero capacity should be ignored in both ECMP and WCMP."""
        net = Network()
        for name in ["S", "A", "B", "T"]:
            net.add_node(Node(name))

        # One path with capacity, one with zero capacity
        net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
        net.add_link(Link("A", "T", capacity=10.0, cost=1.0))
        net.add_link(Link("S", "B", capacity=0.0, cost=1.0))
        net.add_link(Link("B", "T", capacity=0.0, cost=1.0))

        result_ecmp = max_flow(
            net,
            "S",
            "T",
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        result_wcmp = max_flow(
            net, "S", "T", flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )

        # Both should only use the path with capacity
        assert result_ecmp[("S", "T")] == pytest.approx(10.0, abs=1e-9)
        assert result_wcmp[("S", "T")] == pytest.approx(10.0, abs=1e-9)
