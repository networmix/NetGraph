"""Tests for max_flow_with_details cost distribution validation.

These tests ensure that cost_distribution values are correct, not just present.
They validate the actual flow volumes at different path costs.
"""

from __future__ import annotations

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.maxflow import max_flow_with_details
from ngraph.types.base import FlowPlacement


def _diamond_network() -> Network:
    """Build a diamond network with two paths of different costs.

    Topology:
        A -> B (cap 3, cost 1) -> D (cap 3, cost 1)
        A -> C (cap 3, cost 2) -> D (cap 3, cost 2)

    Total cost: path via B = 2, path via C = 4
    Max flow = 6 (3 via B + 3 via C)
    """
    net = Network()
    for name in ["A", "B", "C", "D"]:
        net.add_node(Node(name))

    net.add_link(Link("A", "B", capacity=3.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=3.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=3.0, cost=2.0))
    net.add_link(Link("C", "D", capacity=3.0, cost=2.0))

    return net


def _parallel_paths_network() -> Network:
    """Build network with multiple parallel paths at same cost.

    Topology:
        S -> A (cap 1, cost 1) -> T (cap 1, cost 1)
        S -> B (cap 2, cost 1) -> T (cap 2, cost 1)

    All paths have cost 2, max flow = 3
    """
    net = Network()
    for name in ["S", "A", "B", "T"]:
        net.add_node(Node(name))

    net.add_link(Link("S", "A", capacity=1.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=1.0, cost=1.0))
    net.add_link(Link("S", "B", capacity=2.0, cost=1.0))
    net.add_link(Link("B", "T", capacity=2.0, cost=1.0))

    return net


def _three_tier_network() -> Network:
    """Build network with three different cost tiers.

    Topology:
        S -> A (cap 1, cost 1) -> T (cap 1, cost 1)  [total cost 2]
        S -> B (cap 1, cost 2) -> T (cap 1, cost 2)  [total cost 4]
        S -> C (cap 1, cost 3) -> T (cap 1, cost 3)  [total cost 6]

    Max flow = 3 (1 at each cost tier)
    """
    net = Network()
    for name in ["S", "A", "B", "C", "T"]:
        net.add_node(Node(name))

    net.add_link(Link("S", "A", capacity=1.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=1.0, cost=1.0))
    net.add_link(Link("S", "B", capacity=1.0, cost=2.0))
    net.add_link(Link("B", "T", capacity=1.0, cost=2.0))
    net.add_link(Link("S", "C", capacity=1.0, cost=3.0))
    net.add_link(Link("C", "T", capacity=1.0, cost=3.0))

    return net


def test_cost_distribution_two_paths_different_costs() -> None:
    """Validate cost distribution with two paths of different costs."""
    net = _diamond_network()
    result = max_flow_with_details(net, "^A$", "^D$", mode="combine")

    assert ("^A$", "^D$") in result
    summary = result[("^A$", "^D$")]

    # Total flow should be 6.0
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 6.0

    # Cost distribution should show flow at two different costs
    assert len(summary.cost_distribution) == 2

    # 3 units at cost 2 (via B)
    assert 2.0 in summary.cost_distribution
    assert pytest.approx(summary.cost_distribution[2.0], rel=0, abs=1e-9) == 3.0

    # 3 units at cost 4 (via C)
    assert 4.0 in summary.cost_distribution
    assert pytest.approx(summary.cost_distribution[4.0], rel=0, abs=1e-9) == 3.0

    # Sum of cost distribution should equal total flow
    total_from_dist = sum(summary.cost_distribution.values())
    assert pytest.approx(total_from_dist, rel=0, abs=1e-9) == summary.total_flow


def test_cost_distribution_parallel_paths_same_cost() -> None:
    """Validate cost distribution when all paths have the same cost."""
    net = _parallel_paths_network()
    result = max_flow_with_details(net, "^S$", "^T$", mode="combine")

    summary = result[("^S$", "^T$")]

    # Total flow should be 3.0
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 3.0

    # All flow at cost 2 (both paths have cost 1+1=2)
    assert len(summary.cost_distribution) == 1
    assert 2.0 in summary.cost_distribution
    assert pytest.approx(summary.cost_distribution[2.0], rel=0, abs=1e-9) == 3.0


def test_cost_distribution_three_tiers() -> None:
    """Validate cost distribution with three different cost tiers."""
    net = _three_tier_network()
    result = max_flow_with_details(net, "^S$", "^T$", mode="combine")

    summary = result[("^S$", "^T$")]

    # Total flow should be 3.0
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 3.0

    # Should have three different costs
    assert len(summary.cost_distribution) == 3

    # 1 unit at each cost tier
    assert pytest.approx(summary.cost_distribution[2.0], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(summary.cost_distribution[4.0], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(summary.cost_distribution[6.0], rel=0, abs=1e-9) == 1.0


def test_cost_distribution_shortest_path_mode() -> None:
    """Validate cost distribution in shortest_path mode (only lowest cost tier)."""
    net = _three_tier_network()
    result = max_flow_with_details(
        net, "^S$", "^T$", mode="combine", shortest_path=True
    )

    summary = result[("^S$", "^T$")]

    # Should only use the lowest cost path
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 1.0

    # Should have only one cost tier (the lowest)
    assert len(summary.cost_distribution) == 1
    assert 2.0 in summary.cost_distribution
    assert pytest.approx(summary.cost_distribution[2.0], rel=0, abs=1e-9) == 1.0


def test_cost_distribution_pairwise_mode() -> None:
    """Validate cost distribution in pairwise mode."""
    net = Network()
    for name in ["S1", "S2", "M", "T1", "T2"]:
        net.add_node(Node(name))

    # S1 -> M -> T1: cost 2, capacity 2
    net.add_link(Link("S1", "M", capacity=2.0, cost=1.0))
    net.add_link(Link("M", "T1", capacity=2.0, cost=1.0))

    # S2 -> M -> T2: cost 4, capacity 1
    net.add_link(Link("S2", "M", capacity=1.0, cost=2.0))
    net.add_link(Link("M", "T2", capacity=1.0, cost=2.0))

    # Use capture group in regex to extract node names for pairwise keys
    result = max_flow_with_details(net, r"^(S\d)$", r"^(T\d)$", mode="pairwise")

    # Check S1 -> T1
    s1_t1 = result[("S1", "T1")]
    assert pytest.approx(s1_t1.total_flow, rel=0, abs=1e-9) == 2.0
    assert 2.0 in s1_t1.cost_distribution
    assert pytest.approx(s1_t1.cost_distribution[2.0], rel=0, abs=1e-9) == 2.0

    # Check S2 -> T2
    s2_t2 = result[("S2", "T2")]
    assert pytest.approx(s2_t2.total_flow, rel=0, abs=1e-9) == 1.0
    assert 4.0 in s2_t2.cost_distribution
    assert pytest.approx(s2_t2.cost_distribution[4.0], rel=0, abs=1e-9) == 1.0


def test_cost_distribution_with_flow_placement_proportional() -> None:
    """Validate cost distribution with proportional flow placement."""
    net = _diamond_network()
    result = max_flow_with_details(
        net, "^A$", "^D$", mode="combine", flow_placement=FlowPlacement.PROPORTIONAL
    )

    summary = result[("^A$", "^D$")]

    # Should still get correct total and distribution
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 6.0
    assert len(summary.cost_distribution) == 2
    assert pytest.approx(summary.cost_distribution[2.0], rel=0, abs=1e-9) == 3.0
    assert pytest.approx(summary.cost_distribution[4.0], rel=0, abs=1e-9) == 3.0


def test_cost_distribution_empty_when_no_flow() -> None:
    """Validate cost distribution is empty when there's no flow."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    # No links - no flow possible

    result = max_flow_with_details(net, "^A$", "^B$", mode="combine")
    summary = result[("^A$", "^B$")]

    assert summary.total_flow == 0.0
    assert len(summary.cost_distribution) == 0


def test_cost_distribution_weighted_average_latency() -> None:
    """Validate cost distribution enables correct latency analysis."""
    net = _diamond_network()
    result = max_flow_with_details(net, "^A$", "^D$", mode="combine")
    summary = result[("^A$", "^D$")]

    # Calculate weighted average latency
    total_flow = sum(summary.cost_distribution.values())
    weighted_avg = (
        sum(cost * flow for cost, flow in summary.cost_distribution.items())
        / total_flow
    )

    # With equal flow on both paths (3 at cost 2, 3 at cost 4)
    # weighted average = (2*3 + 4*3) / 6 = 18/6 = 3.0
    assert pytest.approx(weighted_avg, rel=0, abs=1e-9) == 3.0

    # Latency span
    min_latency = min(summary.cost_distribution.keys())
    max_latency = max(summary.cost_distribution.keys())
    latency_span = max_latency - min_latency

    assert min_latency == 2.0
    assert max_latency == 4.0
    assert latency_span == 2.0
