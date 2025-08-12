"""Tests for solver-layer max-flow APIs bound to the model layer.

These tests focus on the wrapper behavior (group selection, overlap handling,
shortest-path mode, saturated edges, and sensitivity) rather than re-testing
algorithm internals.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from ngraph.model.network import Link, Network, Node


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
    result: Dict[Tuple[str, str], float] = net.max_flow("^A$", "^C$", mode="combine")
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

    res = net.max_flow(r"^(S\d)$", r"^(T\d)$", mode="pairwise")

    # All pairwise problems are solved independently on the same topology.
    # Valid paths exist for all pairs with the following capacities.
    assert pytest.approx(res[("S1", "T1")], rel=0, abs=1e-9) == 3.0
    assert pytest.approx(res[("S1", "T2")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T1")], rel=0, abs=1e-9) == 1.0
    assert pytest.approx(res[("S2", "T2")], rel=0, abs=1e-9) == 1.0


def test_overlap_groups_yield_zero_flow() -> None:
    net = _simple_network()
    # Selecting the same node as both source and sink should yield zero
    res = net.max_flow("^S$", "^S$", mode="combine")
    assert pytest.approx(res[("^S$", "^S$")], rel=0, abs=1e-9) == 0.0


def test_empty_selection_raises() -> None:
    net = _simple_network()
    with pytest.raises(ValueError):
        _ = net.max_flow("^Z$", "^T$")
    with pytest.raises(ValueError):
        _ = net.max_flow("^S$", "^Z$")


def test_shortest_path_vs_full_max_flow() -> None:
    net = _simple_network()
    full = net.max_flow("^S$", "^T$", mode="combine", shortest_path=False)
    sp = net.max_flow("^S$", "^T$", mode="combine", shortest_path=True)

    # In this implementation, a single augmentation can place flow across all
    # equal-cost shortest paths; shortest_path matches full in this topology.
    assert pytest.approx(full[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0
    assert pytest.approx(sp[("^S$", "^T$")], rel=0, abs=1e-9) == 2.0


def test_max_flow_with_summary_total_matches() -> None:
    net = _simple_network()
    res = net.max_flow_with_summary("^S$", "^T$", mode="combine")
    (flow, summary) = res[("^S$", "^T$")]
    assert pytest.approx(flow, rel=0, abs=1e-9) == 2.0
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 2.0
    # Sanity on summary structure
    assert isinstance(summary.edge_flow, dict)
    assert isinstance(summary.residual_cap, dict)


def test_max_flow_with_graph_contains_pseudo_nodes() -> None:
    net = _simple_network()
    res = net.max_flow_with_graph("^S$", "^T$", mode="combine")
    flow, graph = res[("^S$", "^T$")]
    assert pytest.approx(flow, rel=0, abs=1e-9) == 2.0
    assert "source" in graph
    assert "sink" in graph


def test_max_flow_detailed_consistency() -> None:
    net = _simple_network()
    res = net.max_flow_detailed("^S$", "^T$", mode="combine")
    flow, summary, graph = res[("^S$", "^T$")]
    assert pytest.approx(flow, rel=0, abs=1e-9) == 2.0
    assert pytest.approx(summary.total_flow, rel=0, abs=1e-9) == 2.0
    assert "source" in graph and "sink" in graph


def test_saturated_edges_identification() -> None:
    # Single path S->A->T with unit capacities: both edges are saturated at max flow 1
    net = Network()
    for name in ["S", "A", "T"]:
        net.add_node(Node(name))
    net.add_link(Link("S", "A", capacity=1.0))
    net.add_link(Link("A", "T", capacity=1.0))

    sat = net.saturated_edges("^S$", "^T$", mode="combine")
    edges = sat[("^S$", "^T$")]
    # Expect at least one saturated edge along S->A or A->T
    assert any(u == "S" and v == "A" for (u, v, _k) in edges) or any(
        u == "A" and v == "T" for (u, v, _k) in edges
    )


def test_sensitivity_analysis_keys_align_with_saturated_edges() -> None:
    # Wrapper should report sensitivity for saturated edges; values are numeric.
    net = Network()
    for name in ["S", "A", "T"]:
        net.add_node(Node(name))
    net.add_link(Link("S", "A", capacity=2.0))
    net.add_link(Link("A", "T", capacity=1.0))

    sens = net.sensitivity_analysis("^S$", "^T$", mode="combine", change_amount=1.0)
    delta_by_edge = sens[("^S$", "^T$")]
    assert delta_by_edge, "Expected sensitivity results on saturated edges"

    sat = net.saturated_edges("^S$", "^T$", mode="combine")[("^S$", "^T$")]
    assert set((u, v, k) for (u, v, k) in sat) == set(delta_by_edge.keys())
    assert all(isinstance(delta, (int, float)) for delta in delta_by_edge.values())


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

    res = net.max_flow(r"^A/dc$", r"^B/dc$", mode="combine")
    assert (r"^A/dc$", r"^B/dc$") in res
    assert res[(r"^A/dc$", r"^B/dc$")] == 10.0
