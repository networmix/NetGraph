"""Regression tests for seed provenance metadata in WorkflowStep.execute().

The recorded seed_source/active_seed must reflect the seed the step actually
uses (self.seed), not the scenario-level seed it never consumes.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.workflow.base import WorkflowStep


@dataclass
class _Dummy(WorkflowStep):
    def run(self, scenario) -> None:
        scenario.results.put("metadata", {})


def _scenario(seed=None) -> MagicMock:
    scen = MagicMock(spec=Scenario)
    scen.results = Results()
    scen.seed = seed
    scen._execution_counter = 0
    return scen


def test_unseeded_step_with_scenario_seed_reports_none() -> None:
    # The step runs with self.seed=None, so claiming "scenario-derived"
    # would falsely advertise reproducibility.
    scen = _scenario(seed=42)
    _Dummy(name="d1").execute(scen)

    md = scen.results.get_step_metadata("d1")
    assert md is not None
    assert md.scenario_seed == 42
    assert md.step_seed is None
    assert md.seed_source == "none"
    assert md.active_seed is None


def test_directly_seeded_step_reports_explicit() -> None:
    scen = _scenario(seed=None)
    _Dummy(name="d2", seed=99).execute(scen)

    md = scen.results.get_step_metadata("d2")
    assert md is not None
    assert md.scenario_seed is None
    assert md.step_seed == 99
    assert md.seed_source == "explicit-step"
    assert md.active_seed == 99


def test_scenario_derived_seed_reports_derived() -> None:
    scen = _scenario(seed=7)
    step = _Dummy(name="d3", seed=1234)
    step._seed_source = "scenario-derived"
    step.execute(scen)

    md = scen.results.get_step_metadata("d3")
    assert md is not None
    assert md.scenario_seed == 7
    assert md.step_seed == 1234
    assert md.seed_source == "scenario-derived"
    assert md.active_seed == 1234
