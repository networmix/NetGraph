from __future__ import annotations

import time

from ngraph.algorithms.base import EdgeSelect, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.algorithms.placement import FlowPlacement
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def _grid_graph(n: int) -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    # Build n x n grid with unit capacity/cost edges right/down
    for i in range(n):
        for j in range(n):
            g.add_node((i, j))
    for i in range(n):
        for j in range(n):
            if j + 1 < n:
                g.add_edge((i, j), (i, j + 1), capacity=1, cost=1)
            if i + 1 < n:
                g.add_edge((i, j), (i + 1, j), capacity=1, cost=1)
    return g


def test_policy_spf_fastpath_is_used_for_common_selectors() -> None:
    g = _grid_graph(20)  # 400 nodes, ~760 edges
    init_flow_graph(g)

    policy = FlowPolicy(
        path_alg=PathAlg.SPF,
        flow_placement=FlowPlacement.PROPORTIONAL,
        edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
        multipath=True,
    )

    t0 = time.perf_counter()
    placed, rem = policy.place_demand(g, (0, 0), (19, 19), "cls", 1.0)
    t1 = time.perf_counter()

    # Sanity checks
    assert placed >= 0.0 and rem >= 0.0

    # Heuristic perf guardrail: should complete within a reasonable bound on a grid
    # (ensures we aren't accidentally using the generic edge_select path)
    assert (t1 - t0) < 0.5
