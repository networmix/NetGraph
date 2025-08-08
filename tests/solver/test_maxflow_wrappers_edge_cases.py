"""Edge-case coverage for solver-layer maxflow wrappers.

Covers invalid modes, empty selections, overlapping groups, pairwise empties,
and disabled-node handling using a minimal test context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import pytest

from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.solver import maxflow as sol


@dataclass
class _NodeStub:
    name: str
    disabled: bool = False


class _Context:
    """Minimal context with controllable groups and graph.

    select_map: mapping from path -> dict[label -> list[_NodeStub]]
    edges: list of (u, v, capacity)
    nodes: iterable of node names to pre-create in graph
    """

    def __init__(
        self,
        select_map: Dict[str, Dict[str, List[_NodeStub]]],
        nodes: List[str] | None = None,
        edges: List[tuple[str, str, float]] | None = None,
    ) -> None:
        self._select_map = select_map
        self._nodes = nodes or []
        self._edges = edges or []

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[_NodeStub]]:
        return self._select_map.get(path, {})

    def to_strict_multidigraph(self, add_reverse: bool = True) -> StrictMultiDiGraph:
        g = StrictMultiDiGraph()
        for n in self._nodes:
            if n not in g:
                g.add_node(n)
        for u, v, cap in self._edges:
            # forward
            g.add_edge(u, v, capacity=cap, cost=1)
            if add_reverse:
                # reverse with same capacity to match model defaults
                g.add_edge(v, u, capacity=cap, cost=1)
        return g


def _base_graph(nodes: list[str], edges: list[tuple[str, str, float]]) -> _Context:
    return _Context(select_map={}, nodes=nodes, edges=edges)


def test_invalid_mode_raises_all_wrappers() -> None:
    ctx = _base_graph(["A", "B"], [("A", "B", 1.0)])
    # Non-empty groups to pass initial validation
    s_groups = {"S": [_NodeStub("A")]}
    t_groups = {"T": [_NodeStub("B")]}
    ctx._select_map = {"S": s_groups, "T": t_groups}

    with pytest.raises(ValueError):
        sol.max_flow(ctx, "S", "T", mode="invalid")
    with pytest.raises(ValueError):
        sol.max_flow_with_summary(ctx, "S", "T", mode="invalid")
    with pytest.raises(ValueError):
        sol.max_flow_with_graph(ctx, "S", "T", mode="invalid")
    with pytest.raises(ValueError):
        sol.max_flow_detailed(ctx, "S", "T", mode="invalid")
    with pytest.raises(ValueError):
        sol.saturated_edges(ctx, "S", "T", mode="invalid")
    with pytest.raises(ValueError):
        sol.sensitivity_analysis(ctx, "S", "T", mode="invalid")


def test_combine_empty_groups_return_zero_or_empty() -> None:
    # Provide labels with empty lists to avoid early ValueError and exercise empty-branch
    ctx = _base_graph(["A", "B"], [("A", "B", 1.0)])
    ctx._select_map = {"S": {"S": []}, "T": {"T": []}}

    assert sol.max_flow(ctx, "S", "T", mode="combine") == {("S", "T"): 0.0}
    flow, graph = sol.max_flow_with_graph(ctx, "S", "T", mode="combine")[("S", "T")]
    assert flow == 0.0 and isinstance(graph, StrictMultiDiGraph)
    flow, summary = sol.max_flow_with_summary(ctx, "S", "T", mode="combine")[("S", "T")]
    assert flow == 0.0 and summary.total_flow == 0.0
    flow, summary, graph = sol.max_flow_detailed(ctx, "S", "T", mode="combine")[
        ("S", "T")
    ]
    assert (
        flow == 0.0
        and summary.total_flow == 0.0
        and isinstance(graph, StrictMultiDiGraph)
    )
    assert sol.saturated_edges(ctx, "S", "T", mode="combine") == {("S", "T"): []}
    assert sol.sensitivity_analysis(ctx, "S", "T", mode="combine") == {("S", "T"): {}}


def test_combine_overlap_groups_yield_zero_or_empty() -> None:
    # Overlap: same node in both groups
    n = _NodeStub("X")
    ctx = _base_graph(["X"], [])
    ctx._select_map = {"S": {"G1": [n]}, "T": {"G2": [n]}}

    assert sol.max_flow(ctx, "S", "T", mode="combine") == {("G1", "G2"): 0.0}
    flow, graph = sol.max_flow_with_graph(ctx, "S", "T", mode="combine")[("G1", "G2")]
    assert flow == 0.0 and isinstance(graph, StrictMultiDiGraph)
    flow, summary = sol.max_flow_with_summary(ctx, "S", "T", mode="combine")[
        ("G1", "G2")
    ]
    assert flow == 0.0 and summary.total_flow == 0.0
    flow, summary, graph = sol.max_flow_detailed(ctx, "S", "T", mode="combine")[
        ("G1", "G2")
    ]
    assert (
        flow == 0.0
        and summary.total_flow == 0.0
        and isinstance(graph, StrictMultiDiGraph)
    )
    assert sol.saturated_edges(ctx, "S", "T", mode="combine") == {("G1", "G2"): []}
    assert sol.sensitivity_analysis(ctx, "S", "T", mode="combine") == {("G1", "G2"): {}}


def test_pairwise_with_empty_and_overlap_entries() -> None:
    # Setup nodes and a single usable edge S2->T1
    ctx = _base_graph(["S2", "T1", "X"], [("S2", "T1", 5.0)])
    s1_empty: list[_NodeStub] = []
    s2 = [_NodeStub("S2")]
    s3_overlap = [_NodeStub("X")]
    t1 = [_NodeStub("T1")]
    t2_empty: list[_NodeStub] = []
    t3_overlap = [_NodeStub("X")]
    ctx._select_map = {
        "S": {"S1": s1_empty, "S2": s2, "S3": s3_overlap},
        "T": {"T1": t1, "T2": t2_empty, "T3": t3_overlap},
    }

    res = sol.max_flow(ctx, "S", "T", mode="pairwise")
    # Empty entries -> zero
    assert res[("S1", "T1")] == 0.0
    assert res[("S2", "T2")] == 0.0
    # Overlap -> zero
    assert res[("S3", "T3")] == 0.0
    # Valid pair uses the only available path
    assert res[("S2", "T1")] == 5.0


def test_disabled_nodes_become_inactive_and_yield_zero() -> None:
    # Both groups non-empty but all nodes disabled -> helper returns 0.0
    s = _NodeStub("S", disabled=True)
    t = _NodeStub("T", disabled=True)
    ctx = _base_graph(["S", "T"], [("S", "T", 10.0)])
    ctx._select_map = {"S": {"S": [s]}, "T": {"T": [t]}}

    assert sol.max_flow(ctx, "S", "T", mode="combine") == {("S", "T"): 0.0}
    # Saturated/sensitivity also reduce to empty because no active nodes
    assert sol.saturated_edges(ctx, "S", "T", mode="combine") == {("S", "T"): []}
    assert sol.sensitivity_analysis(ctx, "S", "T", mode="combine") == {("S", "T"): {}}
