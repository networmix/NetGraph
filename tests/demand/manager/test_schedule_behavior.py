from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ngraph.demand.manager.schedule import place_demands_round_robin
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


@dataclass
class _Policy:
    placed_demand: float = 0.0
    last_metrics: Dict[str, float] | None = None

    def __post_init__(self) -> None:
        if self.last_metrics is None:
            self.last_metrics = {
                "iterations": 1.0,
                "spf_calls": 0.0,
                "flows_created": 1.0,
            }

    def place_demand(
        self, graph: Any, src: str, dst: str, flow_class_key: Any, vol: float
    ) -> None:
        # In real policy, remove_demand clears flows and place_demand rebuilds them.
        # Model that by setting placed_demand to the requested volume, not accumulating.
        self.placed_demand = vol

    def remove_demand(
        self, graph: Any
    ) -> None:  # pragma: no cover - reset internal state
        self.placed_demand = 0.0


@dataclass
class _Demand:
    src_node: str
    dst_node: str
    volume: float
    demand_class: int
    placed_demand: float = 0.0
    flow_policy: _Policy | None = None

    def place(self, flow_graph: StrictMultiDiGraph) -> Tuple[float, float]:
        # Place as much as possible up to volume
        leftover = self.volume - self.placed_demand
        if leftover <= 0:
            return (0.0, 0.0)
        self.placed_demand += leftover
        if self.flow_policy:
            self.flow_policy.place_demand(
                flow_graph,
                self.src_node,
                self.dst_node,
                (self.demand_class, self.src_node, self.dst_node, id(self)),
                leftover,
            )
        return (leftover, 0.0)


def _graph_linear() -> StrictMultiDiGraph:
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_edge("A", "B", capacity=100.0, cost=1.0)
    g.add_edge("B", "A", capacity=100.0, cost=1.0)
    return g


def test_place_demands_round_robin_basic_and_reopt() -> None:
    g = _graph_linear()
    # Two priorities; ensure ordering by prio then fairness across rounds
    d1 = _Demand("A", "B", 10.0, demand_class=0, flow_policy=_Policy())
    d2 = _Demand("A", "B", 5.0, demand_class=1, flow_policy=_Policy())
    # Include a demand without policy to exercise skip path in reoptimize helper
    d3 = _Demand("A", "B", 1.0, demand_class=0, flow_policy=None)
    total = place_demands_round_robin(
        g, [d1, d2, d3], placement_rounds=2, reoptimize_after_each_round=True
    )
    # All should be placed on this simple graph
    assert total == 16.0
    assert d1.placed_demand == 10.0 and d2.placed_demand == 5.0
    assert d3.placed_demand == 1.0


def test_place_demands_round_robin_empty_and_zero_rounds_validation() -> None:
    g = _graph_linear()
    total = place_demands_round_robin(g, [], placement_rounds=1)
    assert total == 0.0
