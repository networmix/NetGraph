from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.solver import paths as sol_paths


@dataclass
class _Node:
    name: str
    disabled: bool = False


class _Ctx:
    def __init__(
        self,
        select_map: Dict[str, Dict[str, List[_Node]]],
        nodes: List[str],
        edges: List[tuple[str, str, float, float]],
    ) -> None:
        self._select_map = select_map
        self._nodes = nodes
        self._edges = edges

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[_Node]]:
        return self._select_map.get(path, {})

    def to_strict_multidigraph(self, add_reverse: bool = True) -> StrictMultiDiGraph:
        g = StrictMultiDiGraph()
        for n in self._nodes:
            if n not in g:
                g.add_node(n)
        for u, v, cap, cost in self._edges:
            g.add_edge(u, v, capacity=cap, cost=cost)
            if add_reverse:
                g.add_edge(v, u, capacity=cap, cost=cost)
        return g


def test_shortest_path_costs_pairwise_disabled_and_overlap() -> None:
    # Disabled sink node -> inf cost for that pair
    nodes = ["S", "T"]
    ctx = _Ctx(
        {"S": {"G": [_Node("S")]}, "T": {"H": [_Node("T", disabled=True)]}},
        nodes,
        [],
    )
    res = sol_paths.shortest_path_costs(ctx, "S", "T", mode="pairwise")
    assert math.isinf(res[("G", "H")])

    # Overlap in pairwise mode -> inf cost
    ctx2 = _Ctx(
        {
            "S": {"A": [_Node("X")]},
            "T": {"B": [_Node("X")]},
        },
        ["X"],
        [],
    )
    res2 = sol_paths.shortest_path_costs(ctx2, "S", "T", mode="pairwise")
    assert math.isinf(res2[("A", "B")])


def test_shortest_paths_combine_collects_equal_cost_paths_from_multiple_sources() -> (
    None
):
    # S1->T cost 2, S2->T cost 2 => both should appear when combine mode picks best cost
    nodes = ["S1", "S2", "T"]
    edges = [("S1", "T", 10.0, 2.0), ("S2", "T", 10.0, 2.0)]
    ctx = _Ctx(
        {
            "S": {"SRC1": [_Node("S1")], "SRC2": [_Node("S2")]},
            "T": {"DST": [_Node("T")]},
        },
        nodes,
        edges,
    )
    paths_map = sol_paths.shortest_paths(ctx, "S", "T", mode="combine")
    label = ("SRC1|SRC2", "DST")
    paths = paths_map[label]
    node_seqs = {p.nodes_seq for p in paths}
    # Expect two single-hop paths S1->T and S2->T
    assert ("S1", "T") in node_seqs and ("S2", "T") in node_seqs
