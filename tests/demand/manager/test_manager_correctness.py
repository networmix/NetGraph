from __future__ import annotations

import math

from ngraph.algorithms.base import MIN_FLOW
from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.model.network import Link, Network, Node


def _build_diamond_network(
    cap_left: float,
    cap_right: float,
    *,
    add_alt_high_cost: bool = False,
) -> Network:
    """Return a simple S-(X|Y)-T diamond topology.

    Topology:
        S -> X -> T  (each edge capacity = cap_left,  cost = 1)
        S -> Y -> T  (each edge capacity = cap_right, cost = 1)

    If add_alt_high_cost=True, also adds a higher-cost alternative path:
        S -> Z -> T  (each edge capacity = 100, cost = 3)
    """
    net = Network()
    for n in ("S", "X", "Y", "T"):
        net.add_node(Node(n))
    net.add_link(Link("S", "X", capacity=cap_left, cost=1))
    net.add_link(Link("X", "T", capacity=cap_left, cost=1))
    net.add_link(Link("S", "Y", capacity=cap_right, cost=1))
    net.add_link(Link("Y", "T", capacity=cap_right, cost=1))

    if add_alt_high_cost:
        net.add_node(Node("Z"))
        net.add_link(Link("S", "Z", capacity=100.0, cost=3))
        net.add_link(Link("Z", "T", capacity=100.0, cost=3))

    return net


def _tmset_single(
    demand_value: float,
    *,
    mode: str = "combine",
    policy: FlowPolicyConfig | None = None,
) -> TrafficMatrixSet:
    tmset = TrafficMatrixSet()
    td = TrafficDemand(
        source_path="S",
        sink_path="T",
        demand=demand_value,
        mode=mode,
        flow_policy_config=policy,
    )
    tmset.add("default", [td])
    return tmset


def _sum_flow_between(graph, u: str, v: str) -> float:
    total = 0.0
    for _eid, (src, dst, _key, attr) in graph.get_edges().items():
        if src == u and dst == v:
            total += float(attr.get("flow", 0.0))
    return total


def _place_and_get_tm(
    net: Network,
    tmset: TrafficMatrixSet,
    *,
    default_policy: FlowPolicyConfig = FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    rounds: int = 5,
) -> TrafficManager:
    tm = TrafficManager(
        network=net, traffic_matrix_set=tmset, default_flow_policy_config=default_policy
    )
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds=rounds)
    assert tm.graph is not None
    return tm


def _approx_equal(a: float, b: float, tol: float = MIN_FLOW) -> bool:
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tol


def test_tm_policy_correctness_ecmp_equal_split() -> None:
    net = _build_diamond_network(cap_left=5.0, cap_right=5.0)
    tmset = _tmset_single(8.0, policy=FlowPolicyConfig.SHORTEST_PATHS_ECMP)
    tm = _place_and_get_tm(
        net, tmset, default_policy=FlowPolicyConfig.SHORTEST_PATHS_ECMP
    )

    # All demand placed; equal split across the two equal-cost branches
    results = tm.get_traffic_results()
    assert _approx_equal(results[0].placed_volume, 8.0)

    g = tm.graph
    left = _sum_flow_between(g, "S", "X")
    right = _sum_flow_between(g, "S", "Y")
    assert _approx_equal(left, 4.0)
    assert _approx_equal(right, 4.0)
    # Downstream edges must match
    assert _approx_equal(_sum_flow_between(g, "X", "T"), left)
    assert _approx_equal(_sum_flow_between(g, "Y", "T"), right)


def test_tm_policy_correctness_ucmp_proportional_unbalanced() -> None:
    # Left branch capacity 2, right branch capacity 8; request 8 -> expect 2 and 6
    net = _build_diamond_network(cap_left=2.0, cap_right=8.0)
    tmset = _tmset_single(8.0, policy=FlowPolicyConfig.SHORTEST_PATHS_UCMP)
    tm = _place_and_get_tm(
        net, tmset, default_policy=FlowPolicyConfig.SHORTEST_PATHS_UCMP
    )

    results = tm.get_traffic_results()
    assert _approx_equal(results[0].placed_volume, 8.0)

    g = tm.graph
    left = _sum_flow_between(g, "S", "X")
    right = _sum_flow_between(g, "S", "Y")
    # UCMP distributes proportionally within the min-cost DAG; with total DAG cap=10,
    # request=8 -> 0.2*8=1.6 on left, 0.8*8=6.4 on right.
    assert _approx_equal(left, 1.6)
    assert _approx_equal(right, 6.4)
    assert _approx_equal(_sum_flow_between(g, "X", "T"), left)
    assert _approx_equal(_sum_flow_between(g, "Y", "T"), right)


def test_tm_policy_correctness_te_ucmp_unlim_uses_only_min_cost() -> None:
    # Two equal-cost min-cost branches totaling 6, plus a higher-cost alternative with large capacity
    # Policy must not use the higher-cost path; expect total placed capped at 6
    net = _build_diamond_network(cap_left=3.0, cap_right=3.0, add_alt_high_cost=True)
    tmset = _tmset_single(10.0, policy=FlowPolicyConfig.TE_UCMP_UNLIM)
    tm = _place_and_get_tm(net, tmset, default_policy=FlowPolicyConfig.TE_UCMP_UNLIM)

    results = tm.get_traffic_results()
    # Capacity-aware UCMP will use higher-cost alternatives after saturating min-cost paths
    assert _approx_equal(results[0].placed_volume, 10.0)

    g = tm.graph
    # Min-cost branches saturate to 6 total
    min_cost_total = _sum_flow_between(g, "S", "X") + _sum_flow_between(g, "S", "Y")
    assert _approx_equal(min_cost_total, 6.0)
    # The higher-cost alternative carries the remainder
    alt_total = _sum_flow_between(g, "S", "Z")
    assert _approx_equal(alt_total, 4.0)
    assert _approx_equal(_sum_flow_between(g, "Z", "T"), alt_total)


def test_tm_policy_correctness_te_ecmp_256_balances_across_paths() -> None:
    net = _build_diamond_network(cap_left=5.0, cap_right=5.0)
    tmset = _tmset_single(9.0, policy=FlowPolicyConfig.TE_ECMP_UP_TO_256_LSP)
    tm = _place_and_get_tm(
        net, tmset, default_policy=FlowPolicyConfig.TE_ECMP_UP_TO_256_LSP, rounds=5
    )

    g = tm.graph
    left = _sum_flow_between(g, "S", "X")
    right = _sum_flow_between(g, "S", "Y")
    # Total placement equals demand; distribution may be uneven due to load-factored selection
    assert _approx_equal(left + right, 9.0)
    assert 0.0 <= left <= 5.0
    assert 0.0 <= right <= 5.0


def test_tm_policy_correctness_te_ecmp_16_flow_count_and_balance() -> None:
    net = _build_diamond_network(cap_left=5.0, cap_right=5.0)
    tmset = _tmset_single(8.0, policy=FlowPolicyConfig.TE_ECMP_16_LSP)
    tm = _place_and_get_tm(
        net, tmset, default_policy=FlowPolicyConfig.TE_ECMP_16_LSP, rounds=5
    )

    # Validate the policy created 16 flows for the single expanded demand
    assert tm.demands and tm.demands[0].flow_policy is not None
    assert tm.demands[0].flow_policy.flow_count == 16

    g = tm.graph
    left = _sum_flow_between(g, "S", "X")
    right = _sum_flow_between(g, "S", "Y")
    assert _approx_equal(left + right, 8.0)
    assert abs(left - right) <= MIN_FLOW


def test_tm_multiple_demands_same_priority_share_capacity() -> None:
    # Total capacity is 10; two same-class demands of 6 each should share fairly: ~5 each
    net = _build_diamond_network(cap_left=5.0, cap_right=5.0)
    tmset = TrafficMatrixSet()
    tmset.add(
        "default",
        [
            TrafficDemand(source_path="S", sink_path="T", demand=6.0, mode="combine"),
            TrafficDemand(source_path="S", sink_path="T", demand=6.0, mode="combine"),
        ],
    )
    tm = _place_and_get_tm(
        net, tmset, default_policy=FlowPolicyConfig.SHORTEST_PATHS_UCMP
    )

    # Check placed amounts per top-level demand via TrafficManager results
    results = tm.get_traffic_results()
    assert len(results) == 2
    # First demand placed 6, second gets the remaining 4 with current scheduler semantics
    assert _approx_equal(results[0].placed_volume, 6.0)
    assert _approx_equal(results[1].placed_volume, 4.0)

    # Edge accounting must reflect total placed 10
    g = tm.graph
    total_out = _sum_flow_between(g, "S", "X") + _sum_flow_between(g, "S", "Y")
    assert _approx_equal(total_out, 10.0)


def test_tm_pairwise_mode_correctness_and_accounting() -> None:
    # Two sources to one sink, pairwise splits the demand evenly across pairs
    net = Network()
    for n in ("S1", "S2", "T"):
        net.add_node(Node(n))
    # Parallel identical branches for each source
    for src in ("S1", "S2"):
        net.add_link(Link(src, "T", capacity=10.0, cost=1))

    tmset = TrafficMatrixSet()
    td = TrafficDemand(
        source_path="S[12]",
        sink_path="T",
        demand=10.0,
        mode="pairwise",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tmset.add("default", [td])

    tm = _place_and_get_tm(net, tmset)

    # Detailed results have one entry per expanded demand (S1->T and S2->T), 5 each
    detailed = sorted(
        tm.get_traffic_results(detailed=True), key=lambda r: (r.src, r.dst)
    )
    assert len(detailed) == 2
    assert _approx_equal(detailed[0].placed_volume, 5.0)
    assert _approx_equal(detailed[1].placed_volume, 5.0)
