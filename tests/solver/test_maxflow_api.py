"""Tests for max-flow analysis via AnalysisContext.

These tests focus on the API behavior (group selection, overlap handling,
shortest-path mode, saturated edges, and sensitivity) rather than re-testing
algorithm internals.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from ngraph import Link, Mode, Network, Node, analyze


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
    result: Dict[Tuple[str, str], float] = analyze(net).max_flow(
        "^A$", "^C$", mode=Mode.COMBINE
    )
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

    res = analyze(net).max_flow(r"^(S\d)$", r"^(T\d)$", mode=Mode.PAIRWISE)

    # All pairwise problems are solved independently on the same topology.
    # Valid paths exist for all pairs with the following capacities.
    assert pytest.approx(res[("S1", "T1")], rel=0, abs=1e-9) == 3.0
    assert pytest.approx(res[("S1", "T2")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T1")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T2")], rel=0, abs=1e-9) == 1.0


def test_overlap_groups_yield_zero_flow() -> None:
    net = _simple_network()
    # Selecting the same node as both source and sink should yield zero
    res = analyze(net).max_flow("^S$", "^S$", mode=Mode.COMBINE)
    assert pytest.approx(res[("^S$", "^S$")], rel=0, abs=1e-9) == 0.0


def test_empty_selection_raises() -> None:
    net = _simple_network()
    with pytest.raises(ValueError):
        _ = analyze(net).max_flow("^Z$", "^T$")
    with pytest.raises(ValueError):
        _ = analyze(net).max_flow("^S$", "^Z$")


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
    full = analyze(net).max_flow("^S$", "^T$", mode=Mode.COMBINE, shortest_path=False)
    sp = analyze(net).max_flow("^S$", "^T$", mode=Mode.COMBINE, shortest_path=True)

    # Full max-flow should use both paths
    assert pytest.approx(full[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0

    # shortest_path=True should use all equal-cost paths (both S->A->T and S->B->T)
    assert pytest.approx(sp[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0


def test_max_flow_with_details_total_matches() -> None:
    net = _simple_network()
    res = analyze(net).max_flow_detailed("^S$", "^T$", mode=Mode.COMBINE)
    summary = res[("^S$", "^T$")]
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 2.0


def test_max_flow_with_details_include_min_cut() -> None:
    """Test that include_min_cut correctly returns saturated edges.

    Uses the simple network with two parallel paths S->A->T and S->B->T.
    All 4 edges should be saturated (form the min-cut).
    """
    net = _simple_network()

    # Without include_min_cut, min_cut should be None
    res_no_cut = analyze(net).max_flow_detailed("^S$", "^T$", mode=Mode.COMBINE)
    assert res_no_cut[("^S$", "^T$")].min_cut is None

    # With include_min_cut=True, min_cut should contain saturated edges
    res_with_cut = analyze(net).max_flow_detailed(
        "^S$", "^T$", mode=Mode.COMBINE, include_min_cut=True
    )
    summary = res_with_cut[("^S$", "^T$")]

    assert summary.min_cut is not None
    assert len(summary.min_cut) == 4  # All 4 edges are saturated

    # Verify edge refs have expected structure
    link_ids = {e.link_id for e in summary.min_cut}
    # Each link appears once (forward direction)
    assert len(link_ids) == 4

    # Verify total flow is still correct
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

    res = analyze(net).max_flow(r"^A/dc$", r"^B/dc$", mode=Mode.COMBINE)
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


def test_sensitivity_shortest_path_parameter_accepted() -> None:
    """Test that sensitivity analysis correctly uses shortest_path parameter.

    The shortest_path parameter controls routing semantics:
    - shortest_path=False (default): Full max-flow (SDN/TE mode). Reports all
      edges critical for achieving maximum possible flow.
    - shortest_path=True: Shortest-path-only (IP/IGP mode). Reports only edges
      critical for flow under ECMP routing; edges on unused longer paths are
      not reported.

    Network topology (_two_cost_tier_network):
        S --[cost=1]--> A --[cost=1]--> T  (shorter path, cost=2)
        S --[cost=2]--> B --[cost=2]--> T  (longer path, cost=4)

    With shortest_path=False: All 4 edges are saturated in full max-flow.
    With shortest_path=True: Only 2 edges on the shortest path (S->A, A->T).
    """
    net = _two_cost_tier_network()

    res_false = analyze(net).sensitivity(
        "^S$", "^T$", mode=Mode.COMBINE, shortest_path=False
    )
    res_true = analyze(net).sensitivity(
        "^S$", "^T$", mode=Mode.COMBINE, shortest_path=True
    )

    assert ("^S$", "^T$") in res_false
    assert ("^S$", "^T$") in res_true

    # Full max-flow (shortest_path=False): all 4 edges are critical
    assert len(res_false[("^S$", "^T$")]) == 4

    # Shortest-path-only (shortest_path=True): only 2 edges on shortest path
    assert len(res_true[("^S$", "^T$")]) == 2

    # Results should differ because shortest_path changes which edges are analyzed
    assert res_false != res_true


def test_require_capacity_parameter() -> None:
    """Test require_capacity parameter for true IP/IGP semantics.

    With require_capacity=True (default):
        If shortest path has no capacity, uses next-best available path.

    With require_capacity=False (true IP):
        Routes on cost only. If shortest path has no capacity, flow is 0.
    """
    net = Network()
    for n in ["S", "A", "B", "T"]:
        net.add_node(Node(n))

    # Shortest path S->A->T: cost 2, but S->A has 0 capacity!
    net.add_link(Link("S", "A", capacity=0.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))

    # Longer path S->B->T: cost 4, has capacity
    net.add_link(Link("S", "B", capacity=100.0, cost=2.0))
    net.add_link(Link("B", "T", capacity=100.0, cost=2.0))

    # Default: require_capacity=True, finds available path
    result_default = analyze(net).max_flow(
        "^S$", "^T$", mode=Mode.COMBINE, shortest_path=True, require_capacity=True
    )
    assert result_default[("^S$", "^T$")] == pytest.approx(100.0, abs=1e-6)

    # True IP: require_capacity=False, tries shortest path (no capacity) -> 0
    result_ip = analyze(net).max_flow(
        "^S$", "^T$", mode=Mode.COMBINE, shortest_path=True, require_capacity=False
    )
    assert result_ip[("^S$", "^T$")] == pytest.approx(0.0, abs=1e-6)
