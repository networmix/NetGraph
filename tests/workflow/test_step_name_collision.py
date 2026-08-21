"""Regression tests for workflow step-name collision detection.

Programmatic scenarios with two unnamed steps of the same type previously
wrote to the same results namespace, silently dropping the first step's data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ngraph.model.network import Network
from ngraph.scenario import Scenario
from ngraph.workflow.base import WorkflowStep, validate_unique_step_names


@dataclass
class _DummyStep(WorkflowStep):
    def run(self, scenario) -> None:
        scenario.results.put("metadata", {})
        scenario.results.put("data", {"ran": True})


def _make_scenario(workflow: list[WorkflowStep]) -> Scenario:
    return Scenario(network=Network(), workflow=workflow)


def test_duplicate_unnamed_steps_raise() -> None:
    scenario = _make_scenario([_DummyStep(), _DummyStep()])
    with pytest.raises(ValueError, match="Duplicate workflow step name"):
        scenario.run()


def test_duplicate_explicit_names_raise() -> None:
    scenario = _make_scenario([_DummyStep(name="x"), _DummyStep(name="x")])
    with pytest.raises(ValueError, match="'x'"):
        scenario.run()


def test_unique_names_run_and_rerun() -> None:
    scenario = _make_scenario([_DummyStep(name="a"), _DummyStep(name="b")])
    scenario.run()
    # Re-running the same scenario object must not trigger the collision check
    scenario.run()
    exported = scenario.results.to_dict()
    assert exported["steps"]["a"]["data"]["ran"] is True
    assert exported["steps"]["b"]["data"]["ran"] is True


def test_direct_step_execute_reuse_not_flagged() -> None:
    # Executing the same step twice directly (test/REPL pattern) is allowed;
    # only duplicates within scenario.workflow are rejected.
    scenario = _make_scenario([])
    step = _DummyStep(name="solo")
    step.execute(scenario)
    step.execute(scenario)
    assert scenario.results.to_dict()["steps"]["solo"]["data"]["ran"] is True


def test_validate_unique_step_names_accepts_unique() -> None:
    validate_unique_step_names([_DummyStep(name="a"), _DummyStep(name="b")])
