"""Comprehensive tests validating IP and TE flow placement semantics with ECMP and WCMP.

This test suite validates that NetGraph correctly implements the distinct behavioral
semantics of IP routing vs Traffic Engineering, and ECMP vs WCMP flow placement.

Key distinctions tested:
1. IP routing (shortest_path=True): Uses only lowest-cost paths
2. TE routing (shortest_path=False): Uses multiple cost tiers progressively
3. ECMP (EQUAL_BALANCED): Equal splitting across equal-cost paths
4. WCMP (PROPORTIONAL): Capacity-proportional splitting across equal-cost paths

Tests use a shared topology where different settings produce measurably different results,
validating actual placement behavior (not just API correctness).
"""

from __future__ import annotations

import pytest

from ngraph import FlowPlacement, Link, Mode, Network, Node, analyze


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
        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        assert result[("^S$", "^T$")] == pytest.approx(30.0, abs=1e-6), (
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
        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=True,
        )

        assert result[("^S$", "^T$")] == pytest.approx(90.0, abs=1e-6), (
            "WCMP with proportional splitting should fully utilize all paths"
        )

    def test_ecmp_vs_wcmp_utilization_gap(self):
        """Verify that WCMP achieves higher utilization than ECMP on unbalanced paths."""
        net = _unbalanced_parallel_paths()

        ecmp_result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        wcmp_result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=True,
        )

        ecmp_flow = ecmp_result[("^S$", "^T$")]
        wcmp_flow = wcmp_result[("^S$", "^T$")]

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
        result_ip_ecmp = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=True,
        )

        result_ip_wcmp = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=True,
        )

        # ECMP on tier 1: limited by smallest path (20)
        # Equal split: 2 * 20 = 40 units
        assert result_ip_ecmp[("^S$", "^T$")] == pytest.approx(40.0, abs=1e-6), (
            "IP ECMP should use only tier 1 with equal splitting"
        )

        # WCMP on tier 1: proportional split
        # 20 + 40 = 60 units (full tier 1 utilization)
        assert result_ip_wcmp[("^S$", "^T$")] == pytest.approx(60.0, abs=1e-6), (
            "IP WCMP should use only tier 1 with proportional splitting"
        )

    def test_te_progressive_multi_tier(self):
        """TE shortest_path=False should use multiple tiers when lower tiers saturate."""
        net = _multi_tier_unbalanced()

        # TE mode: shortest_path=False, progressive fill across tiers
        # Tier 1: 60 units (fills first)
        # Tier 2: 90 units (fills next)
        # Total: 150 units
        result_te_wcmp = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=False,
        )

        assert result_te_wcmp[("^S$", "^T$")] == pytest.approx(150.0, abs=1e-6), (
            "TE WCMP should progressively fill all cost tiers"
        )

        # Verify cost distribution shows both tiers were used
        result_details = analyze(net).max_flow_detailed(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=False,
        )

        summary = result_details[("^S$", "^T$")]

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

        result_te_ecmp = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            shortest_path=False,
        )

        # Progressive ECMP fills tiers sequentially with equal splitting per tier:
        # Round 1 (Tier 1): 2 paths with equal splitting -> fills both (20 + 40 = 60)
        # Round 2 (Tier 2): 2 paths with equal splitting -> fills both (30 + 60 = 90)
        # Total: 150 units (full utilization achieved via multiple rounds)
        assert result_te_ecmp[("^S$", "^T$")] == pytest.approx(150.0, abs=1e-6), (
            "TE ECMP progressive mode should achieve full utilization via multi-round placement"
        )


class TestCombinedSemantics:
    """Test combinations of IP/TE and ECMP/WCMP semantics."""

    @pytest.mark.parametrize(
        "shortest_path,flow_placement,expected_flow",
        [
            # IP ECMP: single tier, equal split -> limited by smallest path
            (True, FlowPlacement.EQUAL_BALANCED, 40.0),
            # IP WCMP: single tier, proportional split -> full tier utilization
            (True, FlowPlacement.PROPORTIONAL, 60.0),
            # TE ECMP: multi-tier, multi-round equal splitting -> full utilization
            (False, FlowPlacement.EQUAL_BALANCED, 150.0),
            # TE WCMP: multi-tier, progressive proportional splitting -> full utilization
            (False, FlowPlacement.PROPORTIONAL, 150.0),
        ],
    )
    def test_semantic_combinations_on_multi_tier(
        self, shortest_path, flow_placement, expected_flow
    ):
        """Test all four combinations of IP/TE and ECMP/WCMP semantics."""
        net = _multi_tier_unbalanced()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
        )

        assert result[("^S$", "^T$")] == pytest.approx(expected_flow, abs=1e-6), (
            f"Expected {expected_flow} for shortest_path={shortest_path}, "
            f"flow_placement={flow_placement.name}"
        )

    @pytest.mark.parametrize(
        "shortest_path,flow_placement,expected_flow",
        [
            # IP ECMP: single tier (all equal cost), equal split -> limited by smallest
            (True, FlowPlacement.EQUAL_BALANCED, 30.0),
            # IP WCMP: single tier (all equal cost), proportional split -> full utilization
            (True, FlowPlacement.PROPORTIONAL, 90.0),
            # TE ECMP: multi-round on single tier -> achieves full utilization
            (False, FlowPlacement.EQUAL_BALANCED, 90.0),
            # TE WCMP: progressive on single tier -> full utilization
            (False, FlowPlacement.PROPORTIONAL, 90.0),
        ],
    )
    def test_semantic_combinations_on_parallel_paths(
        self, shortest_path, flow_placement, expected_flow
    ):
        """Test all four combinations on parallel paths topology."""
        net = _unbalanced_parallel_paths()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
        )

        assert result[("^S$", "^T$")] == pytest.approx(expected_flow, abs=1e-6), (
            f"Expected {expected_flow} for shortest_path={shortest_path}, "
            f"flow_placement={flow_placement.name}"
        )


class TestTrueIPSemantics:
    """Test true IP routing semantics with require_capacity=False.

    True IP/IGP routing:
    - Routes based on cost only, ignores available capacity
    - If shortest path has no capacity, traffic is "lost" (flow=0)
    - ECMP splits equally regardless of capacity
    - WCMP splits proportionally to original capacity (not residual)
    """

    def _saturated_shortest_path_network(self) -> Network:
        """Network where shortest path has zero capacity.

        Topology:
            Shortest path: S -> A -> T (cost 2, S->A has cap 0!)
            Longer path:   S -> B -> T (cost 4, cap 100)

        True IP routes on cost only -> 0 flow.
        """
        net = Network()
        for n in ["S", "A", "B", "T"]:
            net.add_node(Node(n))

        net.add_link(Link("S", "A", capacity=0.0, cost=1.0))
        net.add_link(Link("A", "T", capacity=10.0, cost=1.0))
        net.add_link(Link("S", "B", capacity=100.0, cost=2.0))
        net.add_link(Link("B", "T", capacity=100.0, cost=2.0))

        return net

    def test_true_ip_ecmp_with_saturated_shortest_path(self):
        """True IP ECMP: routes on cost only, gets 0 if shortest path saturated."""
        net = self._saturated_shortest_path_network()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=False,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert result[("^S$", "^T$")] == pytest.approx(0.0, abs=1e-6), (
            "True IP ECMP should return 0 when shortest path is saturated"
        )

    def test_true_ip_wcmp_with_saturated_shortest_path(self):
        """True IP WCMP: routes on cost only, gets 0 if shortest path saturated."""
        net = self._saturated_shortest_path_network()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=False,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        assert result[("^S$", "^T$")] == pytest.approx(0.0, abs=1e-6), (
            "True IP WCMP should return 0 when shortest path is saturated"
        )

    def test_true_ip_ecmp_on_unbalanced_paths(self):
        """True IP ECMP on paths with available capacity.

        Uses _unbalanced_parallel_paths: 3 equal-cost paths with caps 10, 30, 50.
        ECMP splits equally, limited by smallest capacity: 3 * 10 = 30.
        """
        net = _unbalanced_parallel_paths()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=False,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert result[("^S$", "^T$")] == pytest.approx(30.0, abs=1e-6), (
            "True IP ECMP should achieve 30 (3 paths * 10 min capacity)"
        )

    def test_true_ip_wcmp_on_unbalanced_paths(self):
        """True IP WCMP on paths with available capacity.

        Uses _unbalanced_parallel_paths: 3 equal-cost paths with caps 10, 30, 50.
        WCMP splits proportionally: 10 + 30 + 50 = 90.
        """
        net = _unbalanced_parallel_paths()

        result = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=False,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        assert result[("^S$", "^T$")] == pytest.approx(90.0, abs=1e-6), (
            "True IP WCMP should achieve 90 (full utilization)"
        )

    def test_progressive_ip_vs_true_ip(self):
        """Compare progressive IP (require_capacity=True) vs true IP."""
        net = self._saturated_shortest_path_network()

        # Progressive IP: finds available path when shortest is saturated
        result_progressive = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        # True IP: routes on cost only, gets 0 if saturated
        result_true_ip = analyze(net).max_flow(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            shortest_path=True,
            require_capacity=False,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert result_progressive[("^S$", "^T$")] == pytest.approx(100.0, abs=1e-6)
        assert result_true_ip[("^S$", "^T$")] == pytest.approx(0.0, abs=1e-6)


class TestAccountingValidation:
    """Validate that flow accounting is correct across all modes."""

    @pytest.mark.parametrize("shortest_path", [True, False])
    @pytest.mark.parametrize(
        "flow_placement", [FlowPlacement.EQUAL_BALANCED, FlowPlacement.PROPORTIONAL]
    )
    def test_cost_distribution_sums_to_total_flow(self, shortest_path, flow_placement):
        """Verify cost distribution values sum to total flow."""
        net = _multi_tier_unbalanced()

        result = analyze(net).max_flow_detailed(
            "^S$",
            "^T$",
            mode=Mode.COMBINE,
            flow_placement=flow_placement,
            shortest_path=shortest_path,
        )

        summary = result[("^S$", "^T$")]

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
            result = analyze(net).max_flow(
                "^S$",
                "^T$",
                mode=Mode.COMBINE,
                flow_placement=flow_placement,
                shortest_path=shortest_path,
            )
            results.append(result[("^S$", "^T$")])

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

        from ngraph.analysis import AnalysisContext

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
        ctx = AnalysisContext.from_network(net)
        graph_handle = ctx.handle
        multidigraph = ctx.multidigraph
        node_mapper = ctx.node_mapper
        algs = ctx.algorithms

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
        # Limited by smallest selected path: 4 x 30 = 120
        assert placed == pytest.approx(120.0, abs=1e-3), (
            f"Expected 4 LSPs with ECMP constraint (4x30=120), got {placed}"
        )
        assert policy.flow_count() == 4

    def test_2_lsps_on_5_diverse_paths(self):
        """With 2 LSPs and 5 diverse paths, should use the 2 highest-capacity paths."""
        import netgraph_core

        from ngraph.analysis import AnalysisContext

        net = Network()
        nodes = ["S"] + [f"M{i}" for i in range(5)] + ["T"]
        for node in nodes:
            net.add_node(Node(node))

        # Capacities: 10, 20, 30, 40, 50
        capacities = [10, 20, 30, 40, 50]
        for i, cap in enumerate(capacities):
            net.add_link(Link("S", f"M{i}", capacity=cap, cost=1.0))
            net.add_link(Link(f"M{i}", "T", capacity=cap, cost=1.0))

        ctx = AnalysisContext.from_network(net)
        graph_handle = ctx.handle
        multidigraph = ctx.multidigraph
        node_mapper = ctx.node_mapper
        algs = ctx.algorithms

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

        # With 2 LSPs and ECMP constraint
        # Highest 2 capacities: 50, 40
        # Limited by smallest selected path: 2 x 40 = 80
        assert placed == pytest.approx(80.0, abs=1e-3), (
            f"Expected 2 LSPs with ECMP constraint (2x40=80), got {placed}"
        )
        assert policy.flow_count() == 2


class TestContextReuse:
    """Test that AnalysisContext can be reused efficiently."""

    def test_multiple_flow_calls_same_context(self):
        """Test that the same context can compute multiple flows."""
        net = _multi_tier_unbalanced()

        ctx = analyze(net, source="^S$", sink="^T$", mode=Mode.COMBINE)

        # Multiple calls with different parameters
        result1 = ctx.max_flow(
            flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=True
        )
        result2 = ctx.max_flow(
            flow_placement=FlowPlacement.EQUAL_BALANCED, shortest_path=True
        )
        result3 = ctx.max_flow(
            flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=False
        )

        assert result1[("^S$", "^T$")] == pytest.approx(60.0, abs=1e-6)
        assert result2[("^S$", "^T$")] == pytest.approx(40.0, abs=1e-6)
        assert result3[("^S$", "^T$")] == pytest.approx(150.0, abs=1e-6)

    def test_exclusions_with_same_context(self):
        """Test that the same context works with different exclusions."""
        net = _multi_tier_unbalanced()

        ctx = analyze(net, source="^S$", sink="^T$", mode=Mode.COMBINE)

        # Full flow
        full = ctx.max_flow(
            flow_placement=FlowPlacement.PROPORTIONAL, shortest_path=False
        )

        # Exclude tier 1 middle node A1
        partial = ctx.max_flow(
            flow_placement=FlowPlacement.PROPORTIONAL,
            shortest_path=False,
            excluded_nodes={"A1"},
        )

        # Full should be 150, partial should be 130 (150 - 20)
        assert full[("^S$", "^T$")] == pytest.approx(150.0, abs=1e-6)
        assert partial[("^S$", "^T$")] == pytest.approx(130.0, abs=1e-6)
