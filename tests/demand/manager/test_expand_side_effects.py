from __future__ import annotations

from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.model.network import Link, Network, Node


def _build_line() -> Network:
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1))
    return net


def _sum_flow_between(graph, u: str, v: str) -> float:
    total = 0.0
    for _eid, (src, dst, _key, attr) in graph.get_edges().items():
        if src == u and dst == v:
            total += float(attr.get("flow", 0.0))
    return total


def test_expand_combine_twice_preserves_existing_flows_and_is_idempotent() -> None:
    net = _build_line()
    tmset = TrafficMatrixSet()
    td1 = TrafficDemand(
        source_path="A",
        sink_path="B",
        demand=5.0,
        mode="combine",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_UCMP,
    )
    tmset.add("default", [td1])

    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds=3)

    assert tm.graph is not None
    g = tm.graph
    before = _sum_flow_between(g, "A", "B")
    assert before > 0.0

    # Re-expand the same demands again on the existing graph
    # Expected: no exception, no flow reset, and no duplicate pseudo connectors
    tm.expand_demands()

    after = _sum_flow_between(g, "A", "B")
    assert after == before

    # Verify the pseudo nodes/connectors were not duplicated
    ps = f"combine_src::{td1.id}"
    pk = f"combine_snk::{td1.id}"
    # Exactly one connector per direction should exist
    assert len(g.edges_between(ps, "A")) == 1
    assert len(g.edges_between("B", pk)) == 1


def test_expand_combine_adds_new_demand_without_resetting_flows() -> None:
    net = _build_line()
    tmset = TrafficMatrixSet()
    td1 = TrafficDemand(
        source_path="A",
        sink_path="B",
        demand=3.0,
        mode="combine",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tmset.add("default", [td1])

    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds=2)

    g = tm.graph
    assert g is not None
    flow_before = _sum_flow_between(g, "A", "B")
    assert flow_before > 0.0

    # Add another demand and expand again: flows should remain, no reset
    td2 = TrafficDemand(
        source_path="A",
        sink_path="B",
        demand=2.0,
        mode="combine",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tmset.get_default_matrix().append(td2)

    # Must not raise and must not zero out prior flows
    tm.expand_demands()
    flow_after = _sum_flow_between(g, "A", "B")
    assert flow_after == flow_before


def test_reset_after_reexpand_clears_stray_flows() -> None:
    # Place with one demand, then re-expand (losing references to old demand/policy).
    # reset_all_flow_usages must clear all graph usage, including flows that belong
    # to previously expanded demands.
    net = _build_line()
    tmset = TrafficMatrixSet()
    td1 = TrafficDemand(
        source_path="A",
        sink_path="B",
        demand=4.0,
        mode="combine",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )
    tmset.add("default", [td1])

    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds=2)

    g = tm.graph
    assert g is not None
    assert _sum_flow_between(g, "A", "B") > 0.0

    # Re-expand by replacing matrix contents (typical when updating inputs)
    tmset.matrices["default"] = [
        TrafficDemand(
            source_path="A",
            sink_path="B",
            demand=1.0,
            mode="combine",
            flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
        )
    ]
    tm.expand_demands()

    # Now reset: must clear all flows from graph, including those from the old demand
    tm.reset_all_flow_usages()
    assert _sum_flow_between(g, "A", "B") == 0.0
