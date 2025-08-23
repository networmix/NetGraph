from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.solver import paths as sol_paths


@dataclass
class _NodeStub:
    name: str
    disabled: bool = False


class _Context:
    def __init__(
        self,
        select_map: Dict[str, Dict[str, List[_NodeStub]]],
        nodes: List[str] | None = None,
        edges: List[tuple[str, str, float, float]] | None = None,
    ) -> None:
        self._select_map = select_map
        self._nodes = nodes or []
        # edges: (u, v, capacity, cost)
        self._edges = edges or []

    def select_node_groups_by_path(self, path: str) -> Dict[str, List[_NodeStub]]:
        return self._select_map.get(path, {})

    def to_strict_multidigraph(
        self, add_reverse: bool = True, *, compact: bool = False
    ) -> StrictMultiDiGraph:
        g = StrictMultiDiGraph()
        for n in self._nodes:
            if n not in g:
                g.add_node(n)
        for u, v, cap, cost in self._edges:
            g.add_edge(u, v, capacity=cap, cost=cost)
            if add_reverse:
                g.add_edge(v, u, capacity=cap, cost=cost)
        return g


def _ctx_simple() -> _Context:
    # Triangle: S -> X -> T, with costs 1 + 1, and direct S->T cost 5
    nodes = ["S", "X", "T"]
    edges = [("S", "X", 10.0, 1.0), ("X", "T", 10.0, 1.0), ("S", "T", 10.0, 5.0)]
    return _Context(select_map={}, nodes=nodes, edges=edges)


def test_shortest_path_costs_combine_and_pairwise() -> None:
    ctx = _ctx_simple()
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T")]},
    }
    res_c = sol_paths.shortest_path_costs(ctx, "S", "T", mode="combine")
    assert res_c[("SRC", "DST")] == 2.0

    res_p = sol_paths.shortest_path_costs(ctx, "S", "T", mode="pairwise")
    assert res_p[("SRC", "DST")] == 2.0


def test_shortest_paths_returns_paths_and_respects_parallel_edges() -> None:
    ctx = _ctx_simple()
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T")]},
    }
    res = sol_paths.shortest_paths(ctx, "S", "T", mode="combine")
    paths = res[("SRC", "DST")]
    assert paths, "expected at least one path"
    # Best cost is 2.0 via S->X->T
    assert math.isclose(paths[0].cost, 2.0, rel_tol=1e-9)


def test_shortest_paths_split_parallel_edges_enumeration() -> None:
    # S->A has 2 parallel equal-cost edges, A->T has 2 parallel equal-cost edges
    # Without splitting, get a single abstract path; with splitting, expect 2*2=4 paths
    nodes = ["S", "A", "T"]
    edges = [
        ("S", "A", 10.0, 1.0),
        ("S", "A", 10.0, 1.0),
        ("A", "T", 10.0, 1.0),
        ("A", "T", 10.0, 1.0),
    ]
    ctx = _Context(select_map={}, nodes=nodes, edges=edges)
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T")]},
    }
    # No split: one grouped path, nodes S->A->T, each hop may have multiple parallel edges
    no_split = sol_paths.shortest_paths(ctx, "S", "T", split_parallel_edges=False)
    paths0 = no_split[("SRC", "DST")]
    assert len(paths0) == 1
    p0 = paths0[0]
    assert p0.nodes_seq == ("S", "A", "T")
    # edges_seq has 2 segments (S->A, A->T); each segment includes grouped parallel edges
    assert len(p0.edges_seq) == 2
    assert all(len(seg) == 2 for seg in p0.edges_seq)

    # Split: enumerate concrete permutations => 4 paths
    split = sol_paths.shortest_paths(ctx, "S", "T", split_parallel_edges=True)
    paths1 = split[("SRC", "DST")]
    assert len(paths1) == 4
    assert all(p.nodes_seq == ("S", "A", "T") for p in paths1)
    # Each concrete path has exactly one chosen edge per hop
    assert all(len(seg) == 1 for p in paths1 for seg in p.edges_seq)


def test_unreachable_and_overlap_yield_inf_or_empty() -> None:
    # Disconnected graph: S and T not connected
    ctx = _Context(select_map={}, nodes=["S", "T"], edges=[])
    ctx._select_map = {"S": {"SRC": [_NodeStub("S")]}, "T": {"DST": [_NodeStub("T")]}}
    res = sol_paths.shortest_path_costs(ctx, "S", "T")
    assert math.isinf(res[("SRC", "DST")])
    resp = sol_paths.shortest_paths(ctx, "S", "T")
    assert resp[("SRC", "DST")] == []

    # Overlap
    n = _NodeStub("X")
    ctx2 = _Context(
        select_map={"S": {"A": [n]}, "T": {"B": [n]}}, nodes=["X"], edges=[]
    )
    res2 = sol_paths.shortest_path_costs(ctx2, "S", "T")
    assert math.isinf(res2[("A", "B")])
    resp2 = sol_paths.shortest_paths(ctx2, "S", "T")
    assert resp2[("A", "B")] == []


def test_shortest_path_costs_pairwise_labels_and_values() -> None:
    # Two sources and two sinks; only some pairs connected
    nodes = ["S1", "S2", "T1", "T2"]
    edges = [
        ("S1", "T1", 10.0, 3.0),  # cost 3
        ("S2", "T1", 10.0, 1.0),  # cost 1 (best)
        # T2 unreachable
    ]
    ctx = _Context(select_map={}, nodes=nodes, edges=edges)
    ctx._select_map = {
        "S": {"G1": [_NodeStub("S1")], "G2": [_NodeStub("S2")]},
        "T": {"H1": [_NodeStub("T1")], "H2": [_NodeStub("T2")]},
    }
    res = sol_paths.shortest_path_costs(ctx, "S", "T", mode="pairwise")
    assert res[("G1", "H1")] == 3.0
    assert res[("G2", "H1")] == 1.0
    assert math.isinf(res[("G1", "H2")])
    assert math.isinf(res[("G2", "H2")])


def test_k_shortest_paths_respects_cost_thresholds_and_order() -> None:
    # Two best paths of cost 2, one worse path of cost 4; factor=1.0 keeps only best-cost
    nodes = ["S", "A", "B", "C", "T"]
    edges = [
        ("S", "A", 10.0, 1.0),
        ("A", "T", 10.0, 1.0),  # S-A-T cost 2
        ("S", "B", 10.0, 1.0),
        ("B", "T", 10.0, 1.0),  # S-B-T cost 2
        ("S", "C", 10.0, 2.0),
        ("C", "T", 10.0, 2.0),  # S-C-T cost 4
    ]
    ctx = _Context(select_map={}, nodes=nodes, edges=edges)
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T")]},
    }
    res = sol_paths.k_shortest_paths(ctx, "S", "T", max_k=5, max_path_cost_factor=1.0)
    paths = res[("SRC", "DST")]
    # Only the two best-cost paths should be present
    assert len(paths) <= 2
    assert all(math.isclose(p.cost, 2.0, rel_tol=1e-9) for p in paths)
    # Ensure none of the paths go via C
    assert all("C" not in p.nodes_seq for p in paths)


def test_disabled_nodes_are_excluded() -> None:
    ctx = _Context(select_map={}, nodes=["S", "T"], edges=[("S", "T", 10.0, 1.0)])
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T", disabled=True)]},
    }
    res = sol_paths.shortest_path_costs(ctx, "S", "T")
    assert math.isinf(res[("SRC", "DST")])
    paths = sol_paths.shortest_paths(ctx, "S", "T")[("SRC", "DST")]
    assert paths == []


def test_combine_mode_selects_best_pair_and_paths_are_correct() -> None:
    # S1->T2 cost 10, S2->T1 cost 1 (best overall). Combine should pick S2->T1.
    nodes = ["S1", "S2", "T1", "T2"]
    edges = [
        ("S1", "T2", 10.0, 10.0),
        ("S2", "T1", 10.0, 1.0),
    ]
    ctx = _Context(select_map={}, nodes=nodes, edges=edges)
    ctx._select_map = {
        "S": {"A": [_NodeStub("S1")], "B": [_NodeStub("S2")]},
        "T": {"C": [_NodeStub("T1")], "D": [_NodeStub("T2")]},
    }
    label = ("A|B", "C|D")
    costs = sol_paths.shortest_path_costs(ctx, "S", "T", mode="combine")
    assert costs[label] == 1.0
    paths = sol_paths.shortest_paths(ctx, "S", "T", mode="combine")[label]
    assert paths, "expected at least one best path"
    # Best path must be S2->T1
    assert any(p.nodes_seq == ("S2", "T1") for p in paths)


def test_k_shortest_paths_limits_and_order() -> None:
    # Line with two equal-cost alternatives S->A->T and S->B->T
    nodes = ["S", "A", "B", "T"]
    edges = [
        ("S", "A", 10.0, 1.0),
        ("A", "T", 10.0, 1.0),
        ("S", "B", 10.0, 1.0),
        ("B", "T", 10.0, 1.0),
    ]
    ctx = _Context(select_map={}, nodes=nodes, edges=edges)
    ctx._select_map = {
        "S": {"SRC": [_NodeStub("S")]},
        "T": {"DST": [_NodeStub("T")]},
    }
    res = sol_paths.k_shortest_paths(ctx, "S", "T", max_k=2)
    paths = res[("SRC", "DST")]
    assert len(paths) <= 2
    assert all(math.isclose(p.cost, 2.0, rel_tol=1e-9) for p in paths)
