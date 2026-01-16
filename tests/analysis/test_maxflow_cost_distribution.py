"""Tests for cost distribution in max-flow results.

These tests verify that max_flow_detailed correctly computes and reports
the distribution of flow across different cost tiers.
"""

from __future__ import annotations

import pytest

from ngraph import FlowPlacement, Link, Mode, Network, Node, analyze
from tests.conftest import make_asymmetric_diamond


def _parallel_equal_cost_network() -> Network:
    """Build a network with parallel equal-cost paths.

    Topology:
        S -> A (cost 1, cap 5) -> T (cost 1, cap 5)
        S -> B (cost 1, cap 3) -> T (cost 1, cap 3)

    Both paths have same cost (2), total capacity 8.
    """
    net = Network()
    for name in ["S", "A", "B", "T"]:
        net.add_node(Node(name))

    net.add_link(Link("S", "A", capacity=5.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=5.0, cost=1.0))
    net.add_link(Link("S", "B", capacity=3.0, cost=1.0))
    net.add_link(Link("B", "T", capacity=3.0, cost=1.0))

    return net


def _single_path_network() -> Network:
    """Build a simple single-path network.

    Topology: S -> A -> T (cost 2 total, cap 10)
    """
    net = Network()
    for name in ["S", "A", "T"]:
        net.add_node(Node(name))

    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))

    return net


class TestCostDistributionBasic:
    """Basic cost distribution tests."""

    def test_multi_tier_distribution(self) -> None:
        """Test that flow is distributed across cost tiers correctly."""
        net = make_asymmetric_diamond()

        result = analyze(net).max_flow_detailed("^A$", "^D$", mode=Mode.COMBINE)

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 8.0

        # Should have two cost tiers
        assert len(summary.cost_distribution) == 2
        assert (
            pytest.approx(summary.cost_distribution.get(2.0, 0), abs=1e-9) == 5.0
        )  # tier 1
        assert (
            pytest.approx(summary.cost_distribution.get(4.0, 0), abs=1e-9) == 3.0
        )  # tier 2

    def test_parallel_equal_cost_distribution(self) -> None:
        """Test that parallel equal-cost paths share same cost tier."""
        net = _parallel_equal_cost_network()

        result = analyze(net).max_flow_detailed("^S$", "^T$", mode=Mode.COMBINE)

        summary = result[("^S$", "^T$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 8.0

        # All flow should be in single cost tier (cost 2)
        assert len(summary.cost_distribution) == 1
        assert pytest.approx(summary.cost_distribution.get(2.0, 0), abs=1e-9) == 8.0

    def test_single_path_distribution(self) -> None:
        """Test cost distribution for single-path network."""
        net = _single_path_network()

        result = analyze(net).max_flow_detailed("^S$", "^T$", mode=Mode.COMBINE)

        summary = result[("^S$", "^T$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 10.0

        # Single cost tier
        assert len(summary.cost_distribution) == 1
        assert pytest.approx(summary.cost_distribution.get(2.0, 0), abs=1e-9) == 10.0


class TestShortestPathMode:
    """Tests for shortest_path mode cost distribution."""

    def test_shortest_path_mode_uses_only_best_tier(self) -> None:
        """Test that shortest_path=True only uses lowest cost tier."""
        net = make_asymmetric_diamond()

        # make_asymmetric_diamond has nodes A, B, C, D
        result = analyze(net).max_flow_detailed(
            "^A$", "^D$", mode=Mode.COMBINE, shortest_path=True
        )

        summary = result[("^A$", "^D$")]

        # Should only use tier 1 (cost 2)
        assert len(summary.cost_distribution) == 1
        assert 2.0 in summary.cost_distribution
        assert pytest.approx(summary.cost_distribution[2.0], abs=1e-9) == 5.0


class TestPairwiseMode:
    """Tests for pairwise mode cost distribution."""

    def test_pairwise_mode_distribution(self) -> None:
        """Test that pairwise mode returns distribution per pair."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(Node("S2"))
        net.add_node(Node("X"))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "X", capacity=5.0, cost=1.0))
        net.add_link(Link("S2", "X", capacity=3.0, cost=2.0))
        net.add_link(Link("X", "T1", capacity=10.0, cost=1.0))
        net.add_link(Link("X", "T2", capacity=10.0, cost=2.0))

        result = analyze(net).max_flow_detailed(
            r"^(S\d)$", r"^(T\d)$", mode=Mode.PAIRWISE
        )

        # Each pair should have its own distribution
        s1_t1 = result[("S1", "T1")]
        assert pytest.approx(s1_t1.total_flow, abs=1e-9) == 5.0
        assert 2.0 in s1_t1.cost_distribution  # cost 1+1=2


class TestFlowPlacement:
    """Tests for flow placement strategies affecting distribution."""

    def test_proportional_placement(self) -> None:
        """Test PROPORTIONAL flow placement."""
        net = make_asymmetric_diamond()

        result = analyze(net).max_flow_detailed(
            "^A$", "^D$", mode=Mode.COMBINE, flow_placement=FlowPlacement.PROPORTIONAL
        )

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 8.0


class TestEdgeCases:
    """Edge case tests for cost distribution."""

    def test_no_flow_empty_distribution(self) -> None:
        """Test that zero flow results in empty distribution."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        # No link between A and B

        result = analyze(net).max_flow_detailed("^A$", "^B$", mode=Mode.COMBINE)

        summary = result[("^A$", "^B$")]
        assert summary.total_flow == 0.0
        assert len(summary.cost_distribution) == 0

    def test_zero_capacity_path(self) -> None:
        """Test that zero-capacity paths don't contribute."""
        net = Network()
        for name in ["A", "B", "C"]:
            net.add_node(Node(name))

        net.add_link(Link("A", "B", capacity=0.0, cost=1.0))  # Zero capacity
        net.add_link(Link("B", "C", capacity=10.0, cost=1.0))
        net.add_link(Link("A", "C", capacity=5.0, cost=3.0))

        result = analyze(net).max_flow_detailed("^A$", "^C$", mode=Mode.COMBINE)

        summary = result[("^A$", "^C$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 5.0

        # Only the direct path (cost 3) should contribute
        assert len(summary.cost_distribution) == 1
        assert 3.0 in summary.cost_distribution
