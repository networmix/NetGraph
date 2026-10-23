"""Every shipped workflow executes at its declared population and exports valid JSON."""

import json
from importlib import resources
from io import StringIO
from pathlib import Path

import jsonschema
import pytest

from ngraph.export import write_json
from ngraph.results import CapacityAnalysis, MSDAnalysis, PlacementAnalysis
from ngraph.scenario import Scenario, prepare, run

SCENARIOS = tuple(
    sorted((*Path("scenarios").glob("*.yaml"), *Path("scenarios").glob("*.yml")))
)


@pytest.fixture(scope="module")
def result_validator():
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("results.json").read_text()
    )
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    return validator(schema)


@pytest.mark.slow
@pytest.mark.timeout(300)
@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.stem)
def test_shipped_workflow_executes_and_exports(path, result_validator):
    scenario = Scenario.from_yaml(path.read_text())
    prepared = prepare(scenario)
    value = run(prepared)
    assert [step.name for step in value.steps] == [
        step.name for step in prepared.scenario.workflow
    ]
    assert [step.execution_order for step in value.steps] == list(
        range(len(value.steps))
    )
    assert value.topology.graph.uid() == prepared.topology.graph.uid()
    for step in value.steps:
        analysis = step.result
        if isinstance(analysis, (CapacityAnalysis, PlacementAnalysis)):
            assert analysis.units_report.q == prepared.topology.q
            assert analysis.cases[0].case.id == "baseline"
            patterns = [case.case.pattern for case in analysis.cases]
            assert len(patterns) == len(set(patterns))
            expected = (
                analysis.metadata.sampling.iterations
                if analysis.metadata.sampling is not None
                else 0
            )
            assert sum(case.case.occurrences for case in analysis.cases) == expected
            assert all(set(case.states) == {"converged"} for case in analysis.cases)
        elif isinstance(analysis, MSDAnalysis):
            feasible = [
                probe.alpha.value
                for probe in analysis.history
                if probe.outcome == "feasible"
            ]
            assert analysis.alpha_feasible is not None and feasible
            assert analysis.alpha_feasible.value == max(feasible)
    destination = StringIO()
    write_json(value, destination)
    wire = json.loads(destination.getvalue())
    result_validator.validate(wire)
    assert [step["name"] for step in wire["steps"]] == [
        step.name for step in value.steps
    ]
    assert wire["units_report"]["q"] == prepared.topology.q
