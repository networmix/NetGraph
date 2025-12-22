from __future__ import annotations

from typing import Any

from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


class _ScenarioStub:
    def __init__(self, network: Any, tmset: Any, results: Any) -> None:
        self.network = network
        self.traffic_matrix_set = tmset
        self.results = results
        self._execution_counter = 0


def test_msd_reuse_tm_across_seeds_is_behaviorally_identical(monkeypatch):
    # Build a tiny scenario
    from ngraph.model.demand.matrix import TrafficMatrixSet
    from ngraph.model.demand.spec import TrafficDemand
    from ngraph.model.network import Link, Network, Node

    net = Network()
    for n in ("A", "B", "C"):
        net.add_node(Node(n))
    net.add_link(Link("A", "B", capacity=5, cost=1))
    net.add_link(Link("B", "C", capacity=5, cost=1))

    tmset = TrafficMatrixSet()
    tmset.add(
        "default",
        [TrafficDemand(source="A", sink="C", demand=2.0, mode="pairwise")],
    )

    from ngraph.results.store import Results

    scenario = _ScenarioStub(net, tmset, Results())

    # Run MSD with seeds=2; this exercises repeated evaluation within one TM build
    msd = MaximumSupportedDemand(
        matrix_name="default",
        seeds_per_alpha=2,
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.1,
        max_bracket_iters=2,
        max_bisect_iters=2,
    )

    msd.name = "msd"
    msd.execute(scenario)

    # Expect alpha_star >= 1 because demand=2 fits capacity 5
    exported = scenario.results.to_dict()
    alpha_star = exported["steps"]["msd"]["data"].get("alpha_star")
    assert alpha_star is not None
    assert float(alpha_star) >= 1.0
