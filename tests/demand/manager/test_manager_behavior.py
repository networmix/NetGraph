from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pytest

from ngraph.demand.manager.manager import TrafficManager
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand


@dataclass
class _Node:
    name: str
    disabled: bool = False


class _Network:
    def __init__(self, groups: Dict[str, Dict[str, List[_Node]]]) -> None:
        self._groups = groups

    def select_node_groups_by_path(self, pattern: str) -> Dict[str, List[_Node]]:
        return self._groups.get(pattern, {})

    def to_strict_multidigraph(
        self, add_reverse: bool = True
    ):  # pragma: no cover - light stub
        from ngraph.graph.strict_multidigraph import StrictMultiDiGraph

        g = StrictMultiDiGraph()
        for label_map in self._groups.values():
            for nodes in label_map.values():
                for n in nodes:
                    if n.name not in g:
                        g.add_node(n.name)
        return g


def _tm_with_single(td: TrafficDemand) -> TrafficMatrixSet:
    tms = TrafficMatrixSet()
    tms.add("default", [td])
    return tms


def test_build_expand_and_place_auto_rounds_and_results_update() -> None:
    # Two nodes connected implicitly in mock graph
    net = _Network({"A": {"GA": [_Node("A")]}, "B": {"GB": [_Node("B")]}})
    td = TrafficDemand(source_path="A", sink_path="B", demand=5.0, mode="pairwise")
    tm = TrafficManager(network=net, traffic_matrix_set=_tm_with_single(td))

    tm.build_graph()
    tm.expand_demands()
    placed = tm.place_all_demands(placement_rounds=1)
    assert placed >= 0.0  # placement with empty edges just no-ops

    # Results reflect placements per top-level demand
    res = tm.get_traffic_results(detailed=False)
    assert len(res) == 1 and res[0].total_volume == 5.0

    # Detailed returns per expanded demand
    det = tm.get_traffic_results(detailed=True)
    assert isinstance(det, list)


def test_place_all_demands_requires_graph() -> None:
    net = _Network({})
    tm = TrafficManager(network=net, traffic_matrix_set=TrafficMatrixSet())
    with pytest.raises(RuntimeError):
        tm.place_all_demands(1)


def test_reset_and_summarize_link_usage() -> None:
    net = _Network({"A": {"GA": [_Node("A")]}})
    tm = TrafficManager(network=net, traffic_matrix_set=TrafficMatrixSet())
    tm.build_graph()
    tm.expand_demands()
    # Summarize on empty graph
    usage = tm.summarize_link_usage()
    assert isinstance(usage, dict)
    # Reset flows should not error
    tm.reset_all_flow_usages()


def test_estimate_rounds_variants_and_get_flow_details() -> None:
    # Build a tiny graph with two nodes and one link to provide capacities
    net = _Network({"A": {"GA": [_Node("A")]}, "B": {"GB": [_Node("B")]}})
    tms = TrafficMatrixSet()
    # Two demands so median demand is between them
    tms.add(
        "default",
        [
            TrafficDemand(source_path="A", sink_path="B", demand=10.0, mode="pairwise"),
            TrafficDemand(source_path="A", sink_path="B", demand=30.0, mode="pairwise"),
        ],
    )
    tm = TrafficManager(network=net, traffic_matrix_set=tms)
    tm.build_graph()
    tm.expand_demands()
    # _estimate_rounds returns an int; we just assert it does not throw and returns > 0
    rounds = tm._estimate_rounds()
    assert isinstance(rounds, int) and rounds > 0

    # Attach a minimal fake policy/flow to exercise get_flow_details
    class Flow:
        def __init__(self) -> None:
            self.placed_flow = 1.0
            self.src_node = "A"
            self.dst_node = "B"

            class Bundle:
                def __init__(self) -> None:
                    self.edges = {"e1"}

            self.path_bundle = Bundle()

    class FP:
        def __init__(self) -> None:
            self.flows = {0: Flow()}

    for d in tm.demands:
        d.flow_policy = FP()
    details = tm.get_flow_details()
    assert details and list(details.values())[0]["edges"] == ["e1"]
