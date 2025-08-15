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


def test_combine_mode_respects_overlap_semantics() -> None:
    # When overlap exists between active src and dst groups, result must be inf/empty
    nodes = ["X"]
    edges: List[tuple[str, str, float, float]] = []
    ctx = _Ctx({"S": {"G": [_Node("X")]}, "T": {"H": [_Node("X")]}}, nodes, edges)
    costs = sol_paths.shortest_path_costs(ctx, "S", "T", mode="combine")
    assert math.isinf(costs[("G", "H")])
    paths = sol_paths.shortest_paths(ctx, "S", "T", mode="combine")[("G", "H")]
    assert paths == []
