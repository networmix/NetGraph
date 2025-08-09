from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol

from ngraph.demand.manager.expand import expand_demands
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


@dataclass
class _NodeStub:
    name: str


class _NetworkLike(Protocol):
    def select_node_groups_by_path(self, path: str) -> Dict[str, List[_NodeStub]]: ...


class _NetworkStub:
    def __init__(self, mapping: Dict[str, Dict[str, List[_NodeStub]]]):
        self._mapping = mapping

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[_NodeStub]]:  # noqa: D401 - simple stub
        return self._mapping.get(path, {})


def test_expand_pairwise_multiple_pairs() -> None:
    # Two sources x two sinks -> four demands
    mapping = {
        "src": {"S": [_NodeStub("A"), _NodeStub("B")]},
        "dst": {"T": [_NodeStub("C"), _NodeStub("D")]},
    }
    net: _NetworkLike = _NetworkStub(mapping)
    graph = StrictMultiDiGraph()
    # The expansion logic connects pseudo nodes to real nodes; ensure real nodes exist
    for n in ("A", "B", "C", "D"):
        graph.add_node(n)

    td = TrafficDemand(
        source_path="src", sink_path="dst", demand=100.0, mode="pairwise"
    )
    expanded, td_map = expand_demands(
        network=net,  # type: ignore[arg-type]
        graph=graph,
        traffic_demands=[td],
        default_flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )

    assert len(expanded) == 4
    assert len(td_map[td.id]) == 4
    # Equal split across pairs
    assert all(abs(d.volume - 25.0) < 1e-9 for d in expanded)
    assert all(d.demand_class == td.priority for d in expanded)


def test_expand_combine_uses_pseudo_nodes_and_single_demand() -> None:
    # Combine mode should create a single Demand via pseudo nodes and edges
    mapping = {
        "src": {"S": [_NodeStub("A"), _NodeStub("B")]},
        "dst": {"T": [_NodeStub("C"), _NodeStub("D")]},
    }
    net: _NetworkLike = _NetworkStub(mapping)
    graph = StrictMultiDiGraph()
    for n in ("A", "B", "C", "D"):
        graph.add_node(n)

    td = TrafficDemand(source_path="src", sink_path="dst", demand=42.0, mode="combine")
    expanded, td_map = expand_demands(
        network=net,  # type: ignore[arg-type]
        graph=graph,
        traffic_demands=[td],
        default_flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )

    assert len(expanded) == 1
    assert len(td_map[td.id]) == 1
    d = expanded[0]
    assert d.volume == 42.0
    assert str(d.src_node).startswith("combine_src::")
    assert str(d.dst_node).startswith("combine_snk::")
    # Pseudo nodes and link edges should exist
    assert d.src_node in graph.nodes
    assert d.dst_node in graph.nodes
