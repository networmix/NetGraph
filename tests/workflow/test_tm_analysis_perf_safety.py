from __future__ import annotations

from typing import Any

from ngraph.workflow.traffic_matrix_placement_analysis import (
    TrafficMatrixPlacementAnalysis,
)


class _ScenarioStub:
    def __init__(
        self, network: Any, tmset: Any, results: Any, failure_policy_set: Any
    ) -> None:
        self.network = network
        self.traffic_matrix_set = tmset
        self.results = results
        self.failure_policy_set = failure_policy_set


def test_tm_analysis_basic_behavior_unchanged(monkeypatch):
    # Small sanity test that the step runs end-to-end and stores new outputs
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
            return {}

    class _FailurePolicySetStub:
        pass

    scenario = _ScenarioStub(net, tmset, _ResultsStore(), _FailurePolicySetStub())

    step = TrafficMatrixPlacementAnalysis(
        matrix_name="default",
        iterations=2,
        baseline=True,
        placement_rounds="auto",
        include_flow_details=False,
    )
    step.name = "tm_placement"
    # The run signature expects a Scenario; this smoke test uses a light stub
    # compatible enough for runtime execution.
    step.run(scenario)  # type: ignore[arg-type]

    placed_envs = scenario.results.get("tm_placement", "placed_gbps_envelopes")
    samples = scenario.results.get("tm_placement", "delivered_gbps_samples")
    assert isinstance(placed_envs, dict)
    assert isinstance(samples, list)
