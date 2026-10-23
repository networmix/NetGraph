"""Step seed provenance records the concrete seed used by the context."""

from dataclasses import dataclass

from ngraph.model.network import Network
from ngraph.results import StepContext, StepOutput
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.base import WorkflowStep


@dataclass
class _Dummy(WorkflowStep):
    def run(self, context: StepContext) -> StepOutput:
        return StepOutput(
            {},
            {"seed": context.seed, "source": context.seed_source},
        )


def _scenario(seed=None, step=None):
    return prepare(
        Scenario(Network(), [_Dummy(name="d") if step is None else step], seed=seed)
    )


def test_unseeded_step_with_scenario_seed_reports_none():
    (step,) = run(_scenario(seed=42)).steps
    assert step.scenario_seed == 42
    assert step.step_seed is None and step.seed_source == "none"
    assert step.result == {"seed": None, "source": "none"}


def test_directly_seeded_step_reports_explicit():
    (step,) = run(_scenario(step=_Dummy(name="d2", seed=99))).steps
    assert step.scenario_seed is None
    assert step.step_seed == 99 and step.seed_source == "explicit-step"
    assert step.result == {"seed": 99, "source": "explicit-step"}


def test_scenario_derived_seed_reports_derived():
    producer = _Dummy(name="d3", seed=1234, derived_seed=1234)
    (step,) = run(_scenario(seed=7, step=producer)).steps
    assert step.scenario_seed == 7
    assert step.step_seed == 1234 and step.seed_source == "scenario-derived"
    assert step.result == {"seed": 1234, "source": "scenario-derived"}
