from __future__ import annotations

import pytest

from ngraph.solver import paths as sol_paths


class _Ctx:
    def __init__(self) -> None:
        self._map: dict[str, dict[str, list[object]]] = {}

    def select_node_groups_by_path(self, path: str) -> dict[str, list[object]]:
        return self._map.get(path, {})

    def to_strict_multidigraph(
        self, add_reverse: bool = True, *, compact: bool = False
    ):  # pragma: no cover - type shape only
        from ngraph.graph.strict_multidigraph import StrictMultiDiGraph

        g = StrictMultiDiGraph()
        return g


def test_shortest_path_costs_invalid_inputs() -> None:
    ctx = _Ctx()
    with pytest.raises(ValueError):
        sol_paths.shortest_path_costs(ctx, "S", "T")
    ctx._map["S"] = {"A": []}
    with pytest.raises(ValueError):
        sol_paths.shortest_path_costs(ctx, "S", "T")
    ctx._map["T"] = {"B": []}
    with pytest.raises(ValueError):
        sol_paths.shortest_path_costs(ctx, "S", "T", mode="bad")


def test_k_shortest_paths_invalid_mode_raises() -> None:
    ctx = _Ctx()
    ctx._map = {"S": {"SRC": [object()]}, "T": {"DST": [object()]}}
    with pytest.raises(ValueError):
        sol_paths.k_shortest_paths(ctx, "S", "T", mode="invalid")
