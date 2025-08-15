from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Tuple

from ngraph.demand.manager.schedule import place_demands_round_robin
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


@dataclass
class _Policy:
    def place_demand(
        self, graph: Any, src: str, dst: str, flow_class_key: Any, vol: float
    ) -> None:  # pragma: no cover - no-op
        return None

    def remove_demand(self, graph: Any) -> None:  # pragma: no cover - no-op
        return None


@dataclass
class _Demand:
    src_node: str
    dst_node: str
    volume: float
    demand_class: int
    placed_demand: float = 0.0
    flow_policy: _Policy | None = None

    def place(self, flow_graph: StrictMultiDiGraph) -> Tuple[float, float]:
        leftover = self.volume - self.placed_demand
        if leftover <= 0:
            return (0.0, 0.0)
        self.placed_demand += leftover
        return (leftover, 0.0)


def _graph() -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_edge("A", "B", capacity=1.0, cost=1.0)
    g.add_edge("B", "A", capacity=1.0, cost=1.0)
    return g


def test_schedule_debug_logging_smoke(caplog) -> None:
    # Enable DEBUG level for the scheduler module
    caplog.set_level(logging.DEBUG, logger="ngraph.demand.manager.schedule")

    g = _graph()
    demands = [
        _Demand("A", "B", 1.0, demand_class=0, flow_policy=_Policy()),
        _Demand("A", "B", 0.5, demand_class=1, flow_policy=_Policy()),
    ]

    total = place_demands_round_robin(
        g, demands, placement_rounds=1, reoptimize_after_each_round=False
    )
    assert total > 0.0

    # Ensure some DEBUG records emitted from the scheduler logger
    assert any(
        r.levelno == logging.DEBUG
        and r.name.startswith("ngraph.demand.manager.schedule")
        for r in caplog.records
    )
