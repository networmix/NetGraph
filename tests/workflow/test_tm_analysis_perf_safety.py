from __future__ import annotations

from typing import Any

from ngraph.workflow.traffic_matrix_placement_step import (
    TrafficMatrixPlacement,
)


class _ScenarioStub:
    def __init__(
        self, network: Any, demand_set: Any, results: Any, failures: Any
    ) -> None:
        self.network = network
        self.demand_set = demand_set
        self.results = results
        self.failure_policy_set = failures
        self._execution_counter = 0


def test_tm_basic_behavior_unchanged(monkeypatch):
    # Small sanity test that the step runs end-to-end and stores outputs
    from ngraph.model.demand.matrix import DemandSet
    from ngraph.model.demand.spec import TrafficDemand
    from ngraph.model.network import Link, Network, Node

    net = Network()
    for n in ("A", "B", "C"):
        net.add_node(Node(n))
    net.add_link(Link("A", "B", capacity=5, cost=1))
    net.add_link(Link("B", "C", capacity=5, cost=1))

    demand_set = DemandSet()
    demand_set.add(
        "default",
        [TrafficDemand(source="A", target="C", volume=2.0, mode="pairwise")],
    )

    class _ResultsStore:
        def __init__(self) -> None:
            self._store = {}
            self._meta = {}
            self._active = None

        def enter_step(self, name: str) -> None:
            self._active = name
            self._store.setdefault(name, {})

        def exit_step(self) -> None:
            self._active = None

        def put(self, key: str, value: Any) -> None:
            assert self._active is not None
            self._store[self._active][key] = value

        def get_all_step_metadata(self):
            # Return empty mapping; caller code should handle gracefully
            return {}

    class _FailurePolicySetStub:
        pass

    scenario = _ScenarioStub(net, demand_set, _ResultsStore(), _FailurePolicySetStub())

    step = TrafficMatrixPlacement(
        demand_set="default",
        iterations=2,
        placement_rounds="auto",
        include_flow_details=False,
    )
    step.name = "tm_placement"
    # The run signature expects a Scenario; this smoke test uses a light stub
    # compatible enough for runtime execution.
    scenario.results.enter_step("tm_placement")
    step.run(scenario)  # type: ignore[arg-type]
    scenario.results.exit_step()

    exported = {
        "steps": {"tm_placement": scenario.results._store.get("tm_placement", {})}
    }
    data = exported["steps"]["tm_placement"].get("data")
    assert isinstance(data, dict)
    assert isinstance(data.get("flow_results"), list)
