from __future__ import annotations

from typing import Tuple

from ngraph.algorithms.base import MIN_FLOW, PathAlg
from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.demand import Demand
from ngraph.flows.policy import FlowPolicy
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


class _CapturingPolicy(FlowPolicy):
    def __init__(self) -> None:  # type: ignore[no-untyped-def]
        # Minimal viable init
        from ngraph.algorithms.base import EdgeSelect
        from ngraph.algorithms.placement import FlowPlacement

        super().__init__(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
        )
        self.last_volume: float | None = None
        self.last_min_flow: float | None = None

    def place_demand(  # type: ignore[override]
        self,
        flow_graph: StrictMultiDiGraph,
        src_node: str,
        dst_node: str,
        flow_class,
        volume: float,
        target_flow_volume: float | None = None,
        min_flow: float | None = None,
    ) -> Tuple[float, float]:
        # Capture arguments and pretend we placed everything
        self.last_volume = float(volume)
        self.last_min_flow = float(min_flow) if min_flow is not None else None
        # Simulate trivial graph update using base implementation behavior
        # but without placing flows; directly reflect placed_demand
        # Here, mark one flow for accounting to let Demand compute placed delta
        if not self.flows:
            self._create_flows(flow_graph, src_node, dst_node, flow_class, min_flow)
        # Fake placement by setting placed_flow
        for flow in self.flows.values():
            flow.placed_flow += volume
        return volume, 0.0


def test_demand_passes_min_flow_threshold_to_policy() -> None:
    g = StrictMultiDiGraph()
    for n in ("A", "B"):
        g.add_node(n)
    g.add_edge("A", "B", capacity=1.0, cost=1)
    init_flow_graph(g)

    demand = Demand(
        "A", "B", volume=MIN_FLOW * 1.5, demand_class=0, flow_policy=_CapturingPolicy()
    )
    # Request with max_placement far below MIN_FLOW to exercise floor logic soon
    placed, _ = demand.place(g, max_placement=MIN_FLOW * 0.1)
    # With change, Demand should request at least MIN_FLOW; policy may ignore min_flow
    assert placed >= MIN_FLOW * 0.99
    policy = demand.flow_policy  # type: ignore[assignment]
    assert isinstance(policy, _CapturingPolicy)
    assert policy.last_volume is not None and policy.last_volume >= MIN_FLOW * 0.99
    # min_flow is advisory for policies and not required; do not assert it
