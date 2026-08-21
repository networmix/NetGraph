"""Tests for Scenario.run step_hook and pre-run validation semantics."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, ContextManager, Iterator, List

import pytest

from ngraph.model.network import Network
from ngraph.scenario import Scenario
from ngraph.workflow.base import WorkflowStep


@dataclass
class _EventStep(WorkflowStep):
    """Workflow step that records its execution into a shared event list."""

    events: List[str] = field(default_factory=list)

    def run(self, scenario: Scenario) -> None:
        """Record that this step executed."""
        self.events.append(f"execute:{self.name}")


@dataclass
class _FailingStep(WorkflowStep):
    """Workflow step that raises to exercise exception propagation."""

    events: List[str] = field(default_factory=list)

    def run(self, scenario: Scenario) -> None:
        """Record execution, then fail."""
        self.events.append(f"execute:{self.name}")
        raise RuntimeError("boom")


def _make_hook(
    events: List[str],
) -> Callable[[WorkflowStep], ContextManager[None]]:
    """Return a step hook that records enter/exit events around each step."""

    @contextmanager
    def hook(step: WorkflowStep) -> Iterator[None]:
        events.append(f"enter:{step.name}")
        yield
        events.append(f"exit:{step.name}")

    return hook


def test_run_without_hook_executes_steps() -> None:
    events: List[str] = []
    scenario = Scenario(
        network=Network(),
        workflow=[_EventStep(name="s1", events=events)],
    )

    scenario.run()

    assert events == ["execute:s1"]


def test_step_hook_wraps_each_step_in_order() -> None:
    events: List[str] = []
    scenario = Scenario(
        network=Network(),
        workflow=[
            _EventStep(name="s1", events=events),
            _EventStep(name="s2", events=events),
        ],
    )

    scenario.run(step_hook=_make_hook(events))

    assert events == [
        "enter:s1",
        "execute:s1",
        "exit:s1",
        "enter:s2",
        "execute:s2",
        "exit:s2",
    ]


def test_step_hook_exception_propagates_and_skips_post_yield() -> None:
    """A step failure propagates through the hook and skips its exit code.

    Code after the hook's ``yield`` (e.g., profile merging) must not run for
    a failed step, and remaining steps must not execute.
    """
    events: List[str] = []
    scenario = Scenario(
        network=Network(),
        workflow=[
            _FailingStep(name="bad", events=events),
            _EventStep(name="after", events=events),
        ],
    )

    with pytest.raises(RuntimeError, match="boom"):
        scenario.run(step_hook=_make_hook(events))

    assert events == ["enter:bad", "execute:bad"]


def test_run_resets_execution_counter_between_runs() -> None:
    """Repeated runs restart execution_order from zero, also with a hook."""
    events: List[str] = []
    scenario = Scenario(
        network=Network(),
        workflow=[
            _EventStep(name="s1", events=events),
            _EventStep(name="s2", events=events),
        ],
    )

    scenario.run(step_hook=_make_hook(events))
    scenario.run(step_hook=_make_hook(events))

    workflow_metadata = scenario.results.to_dict()["workflow"]
    assert workflow_metadata["s1"]["execution_order"] == 0
    assert workflow_metadata["s2"]["execution_order"] == 1


def test_run_validates_unique_step_names_before_any_execution() -> None:
    """Duplicate effective step names fail before any step or hook runs."""
    events: List[str] = []
    scenario = Scenario(
        network=Network(),
        workflow=[
            _EventStep(name="dup", events=events),
            _EventStep(name="dup", events=events),
        ],
    )

    with pytest.raises(ValueError, match="Duplicate workflow step name"):
        scenario.run(step_hook=_make_hook(events))

    assert events == []
