"""Typed workflow hook order, failure propagation and execution numbering."""

from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, dataclass, replace

import pytest

from ngraph.model.network import Network
from ngraph.results import StepContext, StepOutput
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.base import WorkflowStep


@dataclass
class _EventStep(WorkflowStep):
    emit: Callable[[str], None] = lambda event: None

    def run(self, context: StepContext) -> StepOutput:
        self.emit(f"execute:{context.step_name}")
        return StepOutput({"action": "event"}, {"ran": True})


@dataclass
class _FailingStep(WorkflowStep):
    emit: Callable[[str], None] = lambda event: None

    def run(self, context: StepContext) -> StepOutput:
        self.emit(f"execute:{context.step_name}")
        raise RuntimeError("boom")


def _make_hook(events):
    @contextmanager
    def hook(step):
        events.append(f"enter:{step.name}")
        yield
        events.append(f"exit:{step.name}")

    return hook


def test_run_without_hook_executes_steps():
    events = []
    prepared = prepare(Scenario(Network(), [_EventStep(name="s1", emit=events.append)]))
    result = run(prepared)
    assert events == ["execute:s1"]
    assert result.steps[0].result == {"ran": True}
    assert result.steps[0].question == {"action": "event"}


def test_step_hook_wraps_each_step_in_order():
    events = []
    prepared = prepare(
        Scenario(
            Network(),
            [
                _EventStep(name="s1", emit=events.append),
                _EventStep(name="s2", emit=events.append),
            ],
        )
    )
    result = run(prepared, step_hook=_make_hook(events))
    assert events == [
        "enter:s1",
        "execute:s1",
        "exit:s1",
        "enter:s2",
        "execute:s2",
        "exit:s2",
    ]
    assert [step.name for step in result.steps] == ["s1", "s2"]


def test_step_hook_exception_propagates_and_skips_post_yield():
    events = []
    prepared = prepare(
        Scenario(
            Network(),
            [
                _FailingStep(name="bad", emit=events.append),
                _EventStep(name="after", emit=events.append),
            ],
        )
    )
    with pytest.raises(RuntimeError, match="boom"):
        run(prepared, step_hook=_make_hook(events))
    assert events == ["enter:bad", "execute:bad"]
    with pytest.raises(FrozenInstanceError):
        prepared.scenario.workflow = (_EventStep(name="retry", emit=events.append),)
    retry = prepare(Scenario(Network(), [_EventStep(name="retry", emit=events.append)]))
    assert run(retry).steps[0].result == {"ran": True}


def test_repeated_runs_restart_execution_order():
    events = []
    prepared = prepare(
        Scenario(
            Network(),
            [
                _EventStep(name="s1", emit=events.append),
                _EventStep(name="s2", emit=events.append),
            ],
        )
    )
    first = run(prepared, step_hook=_make_hook(events))
    second = run(prepared, step_hook=_make_hook(events))
    assert [step.execution_order for step in first.steps] == [0, 1]
    assert [step.execution_order for step in second.steps] == [0, 1]
    assert first.steps == second.steps


def test_run_validates_unique_step_names_before_any_execution():
    events = []
    first = _EventStep(name="dup", emit=events.append)
    second = _EventStep(name="dup", emit=events.append)
    scenario = Scenario(Network(), [first, second])
    with pytest.raises(ValueError, match="Duplicate workflow step name"):
        prepare(scenario)
    assert events == []
    scenario = replace(scenario, workflow=(first,))
    prepared = prepare(scenario)
    with pytest.raises(FrozenInstanceError):
        prepared.scenario.workflow = (first, second)
    assert events == []
    assert run(prepared).steps[0].name == "dup"
    with pytest.raises(FrozenInstanceError):
        scenario.workflow = (first, second)
    with pytest.raises(ValueError, match="Duplicate workflow step name"):
        prepare(Scenario(Network(), (first, second)))
