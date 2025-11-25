"""Tests for solver-layer max-flow APIs bound to the model layer.

These tests focus on the wrapper behavior (group selection, overlap handling,
shortest-path mode, saturated edges, and sensitivity) rather than re-testing
algorithm internals.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.maxflow import max_flow, max_flow_with_details, sensitivity_analysis


def _simple_network() -> Network:
    """Build a small network used by several tests.

    Topology:
        S -> A (cap 1) -> T (cap 1)
        S -> B (cap 1) -> T (cap 1)

    Returns:
        Network: Constructed network instance.
    """

    net = Network()
    for name in ["S", "A", "B", "T"]:
        net.add_node(Node(name))

    # Two disjoint unit-capacity paths from S to T
    net.add_link(Link("S", "A", capacity=1.0))
    net.add_link(Link("A", "T", capacity=1.0))
    net.add_link(Link("S", "B", capacity=1.0))
    net.add_link(Link("B", "T", capacity=1.0))

    return net


def _triangle_network() -> Network:
    """Build a small triangle network to exercise combine mode.

    Topology:
        A -> B (cap 2)
        B -> C (cap 1)
        A -> C (cap 1)

    Expected max flow A->C is 2 (1 direct + 1 via B).
    """

    net = Network()
    for name in ["A", "B", "C"]:
        net.add_node(Node(name))

    net.add_link(Link("A", "B", capacity=2.0))
    net.add_link(Link("B", "C", capacity=1.0))
    net.add_link(Link("A", "C", capacity=1.0))
    return net


def test_max_flow_combine_basic() -> None:
    net = _triangle_network()
    result: Dict[Tuple[str, str], float] = max_flow(net, "^A$", "^C$", mode="combine")
    assert ("^A$", "^C$") in result
    assert pytest.approx(result[("^A$", "^C$")], rel=0, abs=1e-9) == 2.0


def test_max_flow_pairwise_disjoint_groups() -> None:
    net = Network()
    # Two labeled source groups and two labeled sink groups
    for name in ["S1", "S2", "X", "T1", "T2"]:
        net.add_node(Node(name))

    # Paths: S1->X->T1 (3), S2->X->T2 (1)
    net.add_link(Link("S1", "X", capacity=3.0))
    net.add_link(Link("X", "T1", capacity=3.0))
    net.add_link(Link("S2", "X", capacity=1.0))
    net.add_link(Link("X", "T2", capacity=1.0))

    res = max_flow(net, r"^(S\d)$", r"^(T\d)$", mode="pairwise")

    # All pairwise problems are solved independently on the same topology.
    # Valid paths exist for all pairs with the following capacities.
    assert pytest.approx(res[("S1", "T1")], rel=0, abs=1e-9) == 3.0
    assert pytest.approx(res[("S1", "T2")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T1")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T2")], rel=0, abs=1e-9) == 1.0


def test_overlap_groups_yield_zero_flow() -> None:
    net = _simple_network()
    # Selecting the same node as both source and sink should yield zero
    res = max_flow(net, "^S$", "^S$", mode="combine")
    assert pytest.approx(res[("^S$", "^S$")], rel=0, abs=1e-9) == 0.0


def test_empty_selection_raises() -> None:
    net = _simple_network()
    with pytest.raises(ValueError):
        _ = max_flow(net, "^Z$", "^T$")
    with pytest.raises(ValueError):
        _ = max_flow(net, "^S$", "^Z$")


def test_shortest_path_vs_full_max_flow() -> None:
    """Test that shortest_path mode uses all equal-cost shortest paths.

    This is a regression test for a critical bug that was fixed in NetGraph-Core.
    The bug (flow_state.cpp line 233) caused shortest_path=True to break after
    one DFS push, using only 1 of N parallel equal-cost paths instead of saturating
    the entire equal-cost DAG.

    This test ensures shortest_path=True correctly saturates all equal-cost paths
    in the lowest-cost tier without going to higher-cost tiers.
    """
    net = _simple_network()
    full = max_flow(net, "^S$", "^T$", mode="combine", shortest_path=False)
    sp = max_flow(net, "^S$", "^T$", mode="combine", shortest_path=True)

    # Full max-flow should use both paths
    assert pytest.approx(full[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0

    # shortest_path=True should use all equal-cost paths (both S->A->T and S->B->T)
    assert pytest.approx(sp[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0


def test_max_flow_with_details_total_matches() -> None:
    net = _simple_network()
    res = max_flow_with_details(net, "^S$", "^T$", mode="combine")
    summary = res[("^S$", "^T$")]
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 2.0


def test_network_dc_to_dc_reverse_edge_first_hop() -> None:
    """Integration: DC->DC flow that requires a reverse edge on first hop.

    Nodes: A/dc, A/leaf, B/leaf, B/dc. Links (forward):
      A/leaf->A/dc (10), A/leaf->B/leaf (10), B/leaf->B/dc (10)

    The wrapper builds a StrictMultiDiGraph with add_reverse=True, creating
    reverse DC->leaf edges, so A/dc can reach B/dc via DC->leaf->leaf->DC.

    Expect positive flow (10.0) in combine mode.
    """
    net = Network()
    for name in ["A/dc", "A/leaf", "B/leaf", "B/dc"]:
        net.add_node(Node(name))

    # Forward links only; the graph builder will add reverse edges
    net.add_link(Link("A/leaf", "A/dc", capacity=10.0, cost=1.0))
    net.add_link(Link("A/leaf", "B/leaf", capacity=10.0, cost=1.0))
    net.add_link(Link("B/leaf", "B/dc", capacity=10.0, cost=1.0))

    res = max_flow(net, r"^A/dc$", r"^B/dc$", mode="combine")
    assert (r"^A/dc$", r"^B/dc$") in res
    assert res[(r"^A/dc$", r"^B/dc$")] == 10.0


def _two_cost_tier_network() -> Network:
    """Build a network with two cost tiers for shortest_path testing.

    Topology: S -> A -> T (cap 10, cost 1+1=2)
              S -> B -> T (cap 5, cost 2+2=4)

    With shortest_path=False: uses both paths, total flow = 15
    With shortest_path=True: uses only S->A->T path, total flow = 10
    """
    net = Network()
    for name in ["S", "A", "B", "T"]:
        net.add_node(Node(name))

    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))
    net.add_link(Link("S", "B", capacity=5.0, cost=2.0))
    net.add_link(Link("B", "T", capacity=5.0, cost=2.0))
    return net


def test_sensitivity_shortest_path_vs_full_max_flow() -> None:
    """Test that shortest_path parameter is forwarded to sensitivity analysis.

    This verifies the fix for an issue where shortest_path was accepted but
    never forwarded to the C++ backend.

    With full max-flow, all 4 edges are critical.
    With shortest_path=True, only S->A->T path edges are critical because
    the S->B->T path is unused under ECMP routing.
    """
    net = _two_cost_tier_network()

    # Full max-flow mode: all 4 edges should be critical
    res_full = sensitivity_analysis(
        net, "^S$", "^T$", mode="combine", shortest_path=False
    )
    assert ("^S$", "^T$") in res_full
    assert len(res_full[("^S$", "^T$")]) == 4, "Full max-flow should report all 4 edges"

    # Shortest-path mode: only 2 edges (S->A, A->T) should be critical
    res_sp = sensitivity_analysis(net, "^S$", "^T$", mode="combine", shortest_path=True)
    assert ("^S$", "^T$") in res_sp
    assert len(res_sp[("^S$", "^T$")]) == 2, (
        "Shortest-path mode should only report 2 edges"
    )

    # Verify the delta values (removing S->A or A->T forces traffic to S->B->T)
    for link_id, delta in res_sp[("^S$", "^T$")].items():
        assert pytest.approx(delta, rel=0, abs=1e-9) == 5.0, (
            f"Edge {link_id} should have delta 5.0 (baseline 10 -> 5 via alternate path)"
        )
