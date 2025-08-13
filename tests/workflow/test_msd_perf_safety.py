from __future__ import annotations

from typing import Any

from ngraph.workflow.maximum_supported_demand import MaximumSupportedDemandAnalysis


class _ScenarioStub:
    def __init__(self, network: Any, tmset: Any, results: Any) -> None:
        self.network = network
        self.traffic_matrix_set = tmset
        self.results = results


def test_msd_reuse_tm_across_seeds_is_behaviorally_identical(monkeypatch):
    # Build a tiny scenario
    from ngraph.demand.matrix import TrafficMatrixSet
    from ngraph.demand.spec import TrafficDemand
    from ngraph.model.network import Link, Network, Node

    net = Network()
    for n in ("A", "B", "C"):
        net.add_node(Node(n))
    net.add_link(Link("A", "B", capacity=5, cost=1))
    net.add_link(Link("B", "C", capacity=5, cost=1))

    tmset = TrafficMatrixSet()
    tmset.add(
        "default",
        [TrafficDemand(source_path="A", sink_path="C", demand=2.0, mode="pairwise")],
    )

    class _ResultsStore:
        def __init__(self) -> None:
            self._data = {}

        def put(self, step: str, key: str, value: Any) -> None:
            self._data.setdefault(step, {})[key] = value

        def get(self, step: str, key: str) -> Any:
            return self._data.get(step, {}).get(key)

        def get_all_step_metadata(self):
            class _MD:
                def __init__(self, execution_order: int, step_type: str) -> None:
                    self.execution_order = execution_order
                    self.step_type = step_type

            return {"msd": _MD(0, "MaximumSupportedDemandAnalysis")}

    scenario = _ScenarioStub(net, tmset, _ResultsStore())

    # Run MSD with seeds=2; this exercises repeated evaluation within one TM build
    msd = MaximumSupportedDemandAnalysis(
        matrix_name="default",
        seeds_per_alpha=2,
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.1,
        max_bracket_iters=2,
        max_bisect_iters=2,
    )

    msd.name = "msd"
    msd.run(scenario)

    # Expect alpha_star >= 1 because demand=2 fits capacity 5
    alpha_star = scenario.results.get("msd", "alpha_star")
    assert alpha_star is not None
    assert float(alpha_star) >= 1.0
