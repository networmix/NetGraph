from __future__ import annotations

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


def test_k_shortest_paths_max_path_cost_factor_filters_worse_paths() -> None:
    nodes = ["S", "A", "B", "T"]
    edges = [
        ("S", "A", 10.0, 1.0),
        ("A", "T", 10.0, 1.0),  # cost 2
        ("S", "B", 10.0, 1.0),
        ("B", "T", 10.0, 2.0),  # cost 3 (filtered out)
    ]
    ctx = _Ctx(
        {
            "S": {"SRC": [_Node("S")]},
            "T": {"DST": [_Node("T")]},
        },
        nodes,
        edges,
    )
    res = sol_paths.k_shortest_paths(
        ctx,
        "S",
        "T",
        max_k=5,
        max_path_cost_factor=1.0,  # keep only best-cost paths
    )
    paths = res[("SRC", "DST")]
    assert all(p.cost == 2.0 for p in paths)
