from __future__ import annotations

import pytest

from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.model.network import Link, Network, Node


def _build_line_network() -> Network:
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_link(Link("A", "B", capacity=1.0, cost=1))
    net.add_link(Link("B", "C", capacity=1.0, cost=1))
    return net


def _tmset_single(demand_value: float) -> TrafficMatrixSet:
    tmset = TrafficMatrixSet()
    tds = [
        TrafficDemand(
            source_path="A", sink_path="C", demand=demand_value, mode="combine"
        )
    ]
    tmset.add("default", tds)
    return tmset


def test_place_all_demands_auto_rounds_clamped_by_granularity() -> None:
    net = _build_line_network()
    tmset = _tmset_single(0.001)
    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    placed = tm.place_all_demands(placement_rounds="auto")
    # Entire small demand should be placed up to MIN_FLOW tolerance; auto rounds must not stall
    assert placed > 0.0
    results = tm.get_traffic_results()
    from ngraph.algorithms.base import MIN_FLOW

    assert abs(results[0].placed_volume - results[0].total_volume) <= MIN_FLOW


def test_place_all_demands_rejects_non_positive_rounds() -> None:
    net = _build_line_network()
    tmset = _tmset_single(1.0)
    tm = TrafficManager(network=net, traffic_matrix_set=tmset)
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    with pytest.raises(ValueError):
        tm.place_all_demands(placement_rounds=0)
    with pytest.raises(ValueError):
        tm.place_all_demands(placement_rounds=-5)
