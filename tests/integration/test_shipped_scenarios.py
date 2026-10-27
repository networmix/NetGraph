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
@pytest.mark.timeout(900)
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


@pytest.mark.slow
def test_square_mesh_cost_bins_follow_each_pair_route():
    # square_mesh is K4, every cost 1; N1-N3 and N2-N4 have capacity 1, the others 2.
    # At MSD's alpha each pair asks r <= 1 (one pair per direction on the capacity-1
    # links). Baseline: every pair on its direct link, one bin at cost 1. With N1-N3
    # failed, N1->N3 and N3->N1 split over their two 2-hop routes (cost 2), r/2 <= 0.5 beside
    # the own pair's r <= 1 on capacity-2 links; every pair is delivered whole.
    value = run(
        prepare(Scenario.from_yaml(Path("scenarios/square_mesh.yaml").read_text()))
    )
    placement = next(s.result for s in value.steps if s.name == "tm_placement")

    def bins(case):
        rows = case.states["converged"].rows
        assert len(rows) == 12
        out = {}
        for row in rows:
            assert row.result.delivered == row.reference_request_units > 0
            assert row.cost_distribution.kind == "delivered_by_path_cost"
            pair = (row.endpoints.sources, row.endpoints.destinations)
            out[pair] = (
                [
                    (b.cost, b.physical_path_cost, b.delivered_units)
                    for b in row.cost_distribution.bins
                ],
                row.reference_request_units,
            )
        return out

    baseline = bins(placement.cases[0])
    assert all(found == [(1, 1, units)] for found, units in baseline.values())
    (failed,) = [
        c for c in placement.cases if c.case.pattern.excluded_links == ("N1|N3|0",)
    ]
    for (sources, destinations), (found, units) in bins(failed).items():
        cost = 2 if {sources, destinations} == {("N1",), ("N3",)} else 1
        assert found == [(cost, cost, units)], (sources, destinations)


@pytest.mark.slow
def test_square_mesh_divides_the_declared_total_among_twelve_pairs():
    from fractions import Fraction

    prepared = prepare(
        Scenario.from_yaml(Path("scenarios/square_mesh.yaml").read_text())
    )
    assert prepared.topology.q == 1 / 1024
    (demands,) = prepared.demand_sets.values()
    pairs = [
        (s, t)
        for s in ("N1", "N2", "N3", "N4")
        for t in ("N1", "N2", "N3", "N4")
        if s != t
    ]
    assert [
        (r.id, r.order, r.endpoints.sources, r.endpoints.destinations, r.nominal_units)
        for r in demands.demands
    ] == [
        (f"baseline_traffic_matrix|0|{i}", i, (s,), (t,), 1024)
        for i, (s, t) in enumerate(pairs)
    ]
    (accounting,) = demands.accounting
    assert (
        accounting.declared_units,
        accounting.resolved_units,
        accounting.discarded_units,
        accounting.discards,
    ) == (12288, 12288, 0, ())
    report = prepared.units_report
    assert (
        report.exponent,
        report.target_met,
        report.augmented_capacity_sum_units,
    ) == (-10, True, 20480)
    (split,) = [s for s in report.nominal_splits if s.kind == "expansion"]
    assert (split.members, split.incoming_physical, split.q_upper_bound, split.met) == (
        12,
        Fraction(12),
        Fraction(float(0.001)) * 12 / 11,
        True,
    )
    value = run(prepared)
    msd = next(s.result for s in value.steps if s.name == "msd_baseline")
    assert msd.alpha_feasible.value == 1
    assert msd.upper_certificate.upper.value == 33 / 32
    assert msd.best_probe_index == 0
    assert [(p.alpha.value, p.outcome) for p in msd.history] == [
        (1.0, "feasible"),
        (2.0, "infeasible"),
        (1.5, "infeasible"),
        (1.25, "infeasible"),
        (1.125, "infeasible"),
        (1.0625, "infeasible"),
        (1.03125, "infeasible"),
    ]
    placement = next(s.result for s in value.steps if s.name == "tm_placement")
    assert placement.alpha.value == 1
    for case in placement.cases:
        state = case.states["converged"]
        assert [(r.id, r.reference_request_units) for r in state.rows] == [
            (r.id, 1024) for r in demands.demands
        ]
        impaired = bool(set(case.case.pattern.excluded_links) - {"N1|N3|0", "N2|N4|0"})
        expected = (12288, 10240, 2048, 2048) if impaired else (12288, 12288, 0, 0)
        assert (
            state.totals.reference_request_units,
            state.totals.delivered_units,
            state.totals.unadmitted_units,
            state.totals.reference_shortfall_units,
        ) == expected
        assert state.totals.delivery_ratio == (
            Fraction(5, 6) if impaired else Fraction(1)
        )
        assert state.totals.source_drop_units == state.totals.edge_drop_units == 0
