from __future__ import annotations

from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.model.network import Link, Network, Node


def _build_net() -> Network:
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=1.0, cost=1))
    return net


def test_reset_all_flow_usages_keeps_flows_but_resets_graph_usage() -> None:
    net = _build_net()
    tmset = TrafficMatrixSet()
    tmset.add(
        "default",
        [TrafficDemand(source_path="A", sink_path="B", demand=1.0, mode="combine")],
    )

    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds=5)
    assert tm.demands and tm.demands[0].placed_demand > 0.0

    tm.reset_all_flow_usages()
    # Graph usage reset
    edges = tm.graph.get_edges() if tm.graph else {}
    assert all(attr[3].get("flow", 0.0) == 0.0 for attr in edges.values())
    # Internal flows structure should remain (enabling reopt later)
    assert (
        tm.demands
        and tm.demands[0].flow_policy
        and tm.demands[0].flow_policy.flow_count >= 1
    )
