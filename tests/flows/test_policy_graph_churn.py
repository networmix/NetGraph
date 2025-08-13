from __future__ import annotations

from ngraph.algorithms.base import EdgeSelect, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.algorithms.placement import FlowPlacement
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def test_policy_handles_graph_rebuild_and_stale_flows() -> None:
    # Initial graph with path A->B->C
    g1 = StrictMultiDiGraph()
    for n in ("A", "B", "C"):
        g1.add_node(n)
    g1.add_edge("A", "B", capacity=5, cost=1)
    g1.add_edge("B", "C", capacity=5, cost=1)
    init_flow_graph(g1)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
    )

    placed, rem = policy.place_demand(g1, "A", "C", "cls", 3.0)
    assert placed == 3.0 and rem == 0.0
    assert len(policy.flows) > 0

    # Rebuild a new graph (e.g., different Network.to_strict_multidigraph) without edge keys from old graph
    g2 = StrictMultiDiGraph()
    for n in ("A", "B", "C"):
        g2.add_node(n)
    # Same topology but new edge ids
    g2.add_edge("A", "B", capacity=5, cost=1)
    g2.add_edge("B", "C", capacity=5, cost=1)
    init_flow_graph(g2)

    # Next placement on new graph must succeed; policy should drop stale flows and recreate
    placed2, rem2 = policy.place_demand(g2, "A", "C", "cls", 2.0)
    assert placed2 == 2.0 and rem2 == 0.0
