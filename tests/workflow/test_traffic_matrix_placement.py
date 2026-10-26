"""Placement workflows retain native rows and their normalized question."""

import json
from io import StringIO

import netgraph_core as ngc
import pytest

from ngraph.export import write_json
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.scenario import prepare, run
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement
from tests.question import asked
from tests.workflow.test_alpha_resolution_errors import _scenario


def _placement(**controls):
    step = TrafficMatrixPlacement(name="tm", demand_set="load", workers=1, **controls)
    prepared = prepare(_scenario((step,)))
    return prepared, run(prepared).steps[0]


def test_traffic_matrix_placement_stores_core_outputs():
    _, step = _placement(iterations=2)
    assert step.result.kind == "placement" and step.question is step.result.query
    (case,) = step.result.cases
    assert set(case.states) == {"converged"}
    assert case.case.occurrences == 2
    state = case.states["converged"]
    assert state.totals.reference_request_units == state.totals.delivered_units == 4
    (row,) = state.rows
    assert row.result.requested == row.result.delivered == 4
    assert row.result.unadmitted == row.result.source_drops == 0
    assert row.result.edge_drops == []
    assert row.result.edge_flows is None and row.result.total_cost is None


def test_traffic_matrix_placement_flow_details_edges():
    prepared, step = _placement(outputs=ngc.OutputOptions(edge_flows=True))
    (row,) = step.result.cases[0].states["converged"].rows
    actual = {
        (ref.link, ref.direction): int(value)
        for ref, value in zip(
            prepared.topology.edge_refs, row.result.edge_flows, strict=True
        )
    }
    assert actual == {("A|B|0", "forward"): 4, ("A|B|0", "reverse"): 0}
    assert row.result.total_cost is None


def test_traffic_matrix_placement_alpha_scales_demands():
    _, step = _placement(alpha=2)
    state = step.result.cases[0].states["converged"]
    assert state.totals.reference_request_units == 8
    assert state.totals.delivered_units == 4
    assert state.totals.unadmitted_units == 4
    assert state.rows[0].result.requested == 8


def test_traffic_matrix_placement_question_includes_alpha():
    prepared, step = _placement(alpha=2)
    assert step.question.alpha == 2 and step.question.alpha_from_step is None
    output = StringIO()
    write_json(run(prepared), output)
    question = json.loads(output.getvalue())["steps"][0]["question"]
    assert question["alpha"] == {"value": 2, "numerator": 2, "denominator": 1}
    assert question["alpha_source"] == {"kind": "query", "step": None}


def test_traffic_matrix_placement_alpha_from_step_uses_msd():
    producer = MaximumSupportedDemand(name="msd", demand_set="load", alpha_tolerance=1)
    consumer = TrafficMatrixPlacement(
        name="tm", demand_set="load", alpha_from_step="msd", workers=1
    )
    producer_result, result = run(prepare(_scenario((producer, consumer)))).steps
    assert result.question.alpha == producer_result.result.alpha_feasible.value
    assert result.question.alpha_from_step == "msd"
    assert asked(result)["alpha_source"] == {"kind": "msd_step", "step": "msd"}
    assert asked(result)["alpha"] == {"value": 1.0, "numerator": 1, "denominator": 1}
    assert result.result.cases[0].states["converged"].totals.feasible


def test_traffic_matrix_placement_alpha_from_step_missing_msd_raises():
    step = TrafficMatrixPlacement(
        name="tm", demand_set="load", alpha_from_step="absent"
    )
    with pytest.raises(ValueError, match="alpha_from_step = 'absent':.*earlier MSD"):
        prepare(_scenario((step,)))
    assert _placement()[1].question.alpha == 1


def _failure_run(trace):
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("node", path="^B$")], {"label": "down"})]
    )
    step = TrafficMatrixPlacement(
        name="tm",
        demand_set="load",
        failure_policy="down",
        iterations=3,
        seed=42,
        failure_trace=trace,
        workers=2,
    )
    scenario = _scenario((step,), failure_policies={"down": policy})
    return run(prepare(scenario))


def test_traffic_matrix_placement_failure_trace_on_results():
    result = _failure_run(True)
    value = result.steps[0].result
    baseline, failed = value.cases
    assert baseline.case.trace is None and baseline.case.occurrences == 0
    assert baseline.states["converged"].totals.delivered_units == 4
    assert failed.case.occurrences == 3
    assert failed.case.trace.mode_index == 0
    assert failed.case.trace.selections[0].selected == ("B",)
    assert dict(failed.case.trace.mode_attrs) == {"label": "down"}
    assert failed.states["converged"].totals.delivered_units == 0
    assert result.steps[0].question.failures.policy_name == "down"
    output = StringIO()
    write_json(result, output)
    wire = json.loads(output.getvalue())["steps"][0]["result"]["cases"][1]
    assert wire["case"]["trace"]["mode_index"] == 0
    assert wire["case"]["trace"]["selections"][0]["selected"] == ["B"]


def test_traffic_matrix_placement_no_trace_when_disabled():
    result = _failure_run(False)
    assert all(case.case.trace is None for case in result.steps[0].result.cases)
    output = StringIO()
    write_json(result, output)
    wire = json.loads(output.getvalue())["steps"][0]["result"]["cases"]
    assert all("trace" not in case["case"] for case in wire)
    assert [case["case"]["occurrences"] for case in wire] == [0, 3]
