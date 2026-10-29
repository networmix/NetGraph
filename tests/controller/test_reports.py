"""Weight approximations in the units report, faults while tables are built, workers."""

import json
from fractions import Fraction
from io import StringIO

import pytest
import yaml

import ngraph.analysis.controller as controller
from ngraph import (
    DemandSet,
    FlowPolicyPreset,
    PlacementQuery,
    Scenario,
    place,
    prepare,
    resolve_demands,
    run,
    write_json,
)
from tests.controller.helpers import delivered, demand, prepared
from tests.controller.test_declarations import FIXTURE
from tests.controller.test_tables import FIXTURE_LINKS, fixture

L = 1 << 62
TINY = (
    "1/1180591620717411303424"  # 2^-70: exact weights [2^70, 1] reach the native bound
)
SMALL = "1/1152921504606846976"  # 2^-60: exact weights [2^60, 1] stay below it
ERROR = Fraction((1 << 70) - L + 2, L - 1)


def scenario_text(share):
    data = yaml.safe_load(FIXTURE)
    data["forwarding_groups"]["ingress"]["groups"][1]["share"] = share
    data["workflow"].append(
        {"type": "MaximumSupportedDemand", "name": "msd", "demand_set": "ebb"}
    )
    return yaml.safe_dump(data)


def exported(result):
    output = StringIO()
    write_json(result, output)
    return json.loads(output.getvalue())


def test_an_approximation_travels_from_preparation_to_every_report():
    result = run(prepare(Scenario.from_yaml(scenario_text(TINY))))
    control = run(prepare(Scenario.from_yaml(scenario_text(SMALL))))
    entry = {
        "kind": "weight_approximation",
        "label": "controller.ebb.DC_B.router.DC_A",
        "max_relative_error": {
            "numerator": ERROR.numerator,
            "denominator": ERROR.denominator,
        },
    }
    wire = exported(result)
    assert wire["units_report"]["weight_approximations"] == [entry]
    assert exported(control)["units_report"]["weight_approximations"] == []
    # One entry per router, in each analysis too: no probe or case adds another.
    for step in result.steps:
        assert [e.label for e in step.result.units_report.weight_approximations] == [
            "controller.ebb.DC_B.router.DC_A"
        ]
    # The approximation changes neither the target nor the input/count bounds.
    for name in ("target_met", "input_bound", "split_bound", "achieved_precision"):
        assert getattr(result.units_report, name) == getattr(control.units_report, name)
    # The controller key reports the apportioned weights and nothing of the error.
    placed = wire["steps"][0]["result"]["controller"][0]["programmed"][0]["members"]
    assert [m["weight"] for m in placed] == [L - 2, 1]
    assert "max_relative_error" not in json.dumps(
        wire["steps"][0]["result"]["controller"]
    )
    rows = result.steps[0].result.cases[0].states["converged"].rows
    assert rows[0].result.delivered == 6400


def test_a_set_bound_after_preparation_brings_its_own_approximations():
    value = Scenario.from_yaml(scenario_text(TINY))
    late = DemandSet(
        "late",
        (
            demand(
                "^DC_A$", "^DC_B$", 50, FlowPolicyPreset.SHORTEST_PATHS_WCMP, id="late"
            ),
        ),
    )
    from dataclasses import replace

    value = replace(value, demand_sets={**value.demand_sets, "late": late})
    prep = prepare(value)
    assert [e.label for e in prep.units_report.weight_approximations] == [
        "controller.ebb.DC_B.router.DC_A"
    ]
    resolved = resolve_demands(prep, late)
    analysis = place(prep, PlacementQuery(resolved, workers=1))
    assert [e.label for e in analysis.units_report.weight_approximations] == [
        "controller.ebb.DC_B.router.DC_A",
        "controller.late.DC_B.router.DC_A",
    ]


@pytest.mark.parametrize(
    ("owner", "name"),
    [
        (controller, "destination_table"),
        (controller, "table_report"),
        (controller.ControllerSetup, "leaf_config"),
    ],
)
def test_a_failure_while_a_table_is_built_publishes_nothing_and_a_retry_succeeds(
    owner, name, monkeypatch
):
    value = Scenario.from_yaml(scenario_text("1"))
    before = (value.forwarding_groups, value.demand_sets, value.routing)
    original = getattr(owner, name)
    calls = []

    def failing(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise MemoryError("planted")
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, failing)
    with pytest.raises(MemoryError, match="planted"):
        prepare(value)
    assert (value.forwarding_groups, value.demand_sets, value.routing) == before
    retried = prepare(value)
    clean = prepare(Scenario.from_yaml(scenario_text("1")))
    assert retried.demand_sets["ebb"].controller == clean.demand_sets["ebb"].controller
    assert (
        retried.demand_sets["ebb"].controller_table("DC_B").weights
        == clean.demand_sets["ebb"].controller_table("DC_B").weights
    )


def test_workers_change_nothing():
    prep = fixture("next_hop")
    rows = [
        place(prep, PlacementQuery(prep.demand_sets["d"], workers=workers))
        .cases[0]
        .states["converged"]
        .rows[0]
        .result.delivered
        for workers in (1, 4)
    ]
    assert rows == [9600, 9600]


def test_the_fixture_at_its_lossless_bound_in_every_scope():
    assert delivered(fixture("all_routers"))[0] == {"dc|0": 9600}
    plain = prepare(
        Scenario(
            prepared(
                FIXTURE_LINKS,
                "^(A|B)[12]$",
                "^DC_",
                [demand("^DC_A$", "^DC_B$", 1, id="dc")],
            ).scenario.network,
            demand_sets={
                "d": DemandSet(
                    "d",
                    (
                        demand(
                            "^DC_A$",
                            "^DC_B$",
                            150,
                            FlowPolicyPreset.SHORTEST_PATHS_ECMP,
                            id="dc",
                        ),
                    ),
                )
            },
            units=fixture("next_hop").scenario.units,
        ),
        demand_sets=("d",),
    )
    # Native ECMP without a controller: H gives the odd unit to DC_A->A1, as group 1:1 does.
    assert delivered(plain)[0] == {"dc|0": 6401}
