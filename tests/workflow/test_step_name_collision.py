"""Regression tests for workflow step-name collision detection.

Effective step names must be unique before preparation or execution publishes data.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from ngraph.model.network import Network
from ngraph.results import StepContext, StepOutput
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.base import WorkflowStep, validate_unique_step_names


@dataclass
class _DummyStep(WorkflowStep):
    def run(self, context: StepContext) -> StepOutput:
        return StepOutput({}, {"ran": True})


def _make_scenario(workflow: list[WorkflowStep]) -> Scenario:
    return Scenario(network=Network(), workflow=workflow)


def test_duplicate_unnamed_steps_raise() -> None:
    scenario = _make_scenario([_DummyStep(), _DummyStep()])
    with pytest.raises(ValueError, match="Duplicate workflow step name"):
        prepare(scenario)


def test_duplicate_explicit_names_raise() -> None:
    scenario = _make_scenario([_DummyStep(name="x"), _DummyStep(name="x")])
    with pytest.raises(ValueError, match="name: x"):
        prepare(scenario)


def test_unique_names_run_and_rerun() -> None:
    scenario = _make_scenario([_DummyStep(name="a"), _DummyStep(name="b")])
    prepared = prepare(scenario)
    result = run(prepared)
    # Re-running the same scenario object must not trigger the collision check
    repeated = run(prepared)
    assert [step.name for step in result.steps] == ["a", "b"]
    assert [step.result for step in repeated.steps] == [{"ran": True}, {"ran": True}]


def test_direct_step_execute_reuse_not_flagged() -> None:
    # Executing the same step twice directly (test/REPL pattern) is allowed;
    # only duplicates within scenario.workflow are rejected.
    scenario = prepare(_make_scenario([]))
    step = _DummyStep(name="solo")
    context = StepContext(scenario, {}, "solo", 0, None, "none")
    first, second = step.execute(context), step.execute(context)
    assert first.result == second.result == {"ran": True}


def test_validate_unique_step_names_accepts_unique() -> None:
    validate_unique_step_names([_DummyStep(name="a"), _DummyStep(name="b")])
