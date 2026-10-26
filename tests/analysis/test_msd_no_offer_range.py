"""Discarded totals still obey both numeric domains in the single MSD probe."""

import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    MSDQuery,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    maximum_supported_demand,
    prepare,
    run,
)
from ngraph.workflow import MaximumSupportedDemand, TrafficMatrixPlacement
from tests.analysis.test_excluded_declarations import wire

CASES = [
    (
        1e9,
        "native_units_range",
        "demand.large.volume: to_units: the amount is at or above the bound of the units domain (2^62 units)",
        float(10**19).hex(),
    ),
    (1e308, "scaled_nonfinite", "demand.large.volume: scaled_nonfinite", "inf"),
]


def scenario(kind="self_pair", workflow=()):
    specs = [
        DemandSpec(
            Selector("^missing$" if kind == "empty_selection" else "^(A)$"),
            Selector("^(A)$"),
            1e10,
            FlowPolicyPreset.TE_ECMP_16_LSP
            if kind == "pooled_self"
            else FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            id="large",
            group_mode="group_pairwise" if kind == "filtered" else "flatten",
        )
    ]
    if kind == "discarded_and_zero":
        specs.append(DemandSpec(Selector("^A$"), Selector("^B$"), 0, id="zero"))
    return Scenario(
        Network(nodes={n: Node(n) for n in ("A", "B")}),
        workflow,
        demand_sets={"d": DemandSet("d", tuple(specs))},
        units=UnitsSettings(1),
    )


@pytest.mark.parametrize("bound,reason,message,hex_value", CASES)
@pytest.mark.parametrize(
    "kind",
    ["self_pair", "filtered", "empty_selection", "pooled_self", "discarded_and_zero"],
)
@pytest.mark.parametrize("retain", [False, True])
def test_nothing_offered_probe_refusals_are_range_results(
    bound, reason, message, hex_value, kind, retain
):
    prepared = prepare(scenario(kind), demand_sets=("d",))
    demands = prepared.demand_sets["d"]
    control = maximum_supported_demand(prepared, MSDQuery(demands, alpha_max=4))
    assert (control.search_status, control.stop_reason, control.proof) == (
        "trivial",
        "nothing_offered",
        "nothing_offered",
    )
    assert control.alpha_feasible.value == 4 and len(control.history) == 1
    assert control.history[0].outcome == "feasible"
    assert control.best_accounting[0].declared_units == 40_000_000_000
    assert control.best_accounting[0].discarded_units == 40_000_000_000

    result = maximum_supported_demand(
        prepared, MSDQuery(demands, alpha_max=bound, export_probe_rows=retain)
    )
    assert (result.search_status, result.stop_reason, result.proof) == (
        "range",
        "offer_range",
        "nothing_offered",
    )
    assert result.monotone_proven is True
    assert (
        result.alpha_feasible
        is result.best_probe_index
        is result.best_rows
        is result.best_accounting
        is result.upper_certificate
        is None
    )
    assert len(result.history) == 1
    (probe,) = result.history
    assert (probe.index, probe.alpha.value, probe.outcome, probe.totals) == (
        0,
        bound,
        "range",
        None,
    )
    refusal = probe.range_refusal
    assert (refusal.label, refusal.reason, refusal.message, refusal.binary64_hex) == (
        "demand.large.volume",
        reason,
        message,
        hex_value,
    )
    assert (dict(result.probe_rows) if retain else result.probe_rows) == (
        {} if retain else None
    )
    data = wire(result)["analysis"]
    assert (data["search_status"], data["stop_reason"], data["proof"]) == (
        "range",
        "offer_range",
        "nothing_offered",
    )
    for name in (
        "alpha_feasible",
        "best_probe_index",
        "best_rows",
        "best_accounting",
        "upper_certificate",
    ):
        assert name in data and data[name] is None
    numerator, denominator = bound.as_integer_ratio()
    assert data["history"] == [
        {
            "index": 0,
            "alpha": {
                "value": bound,
                "numerator": numerator,
                "denominator": denominator,
            },
            "outcome": "range",
            "totals": None,
            "range_refusal": {
                "label": "demand.large.volume",
                "reason": reason,
                "message": message,
                "binary64_hex": hex_value,
            },
        }
    ]
    if retain:
        assert data["probe_rows"] == []
    else:
        assert "probe_rows" not in data
    # A refused scale does not damage the prepared input or a later safe query.
    retry = maximum_supported_demand(prepared, MSDQuery(demands, alpha_max=4))
    assert wire(retry) == wire(control)


@pytest.mark.parametrize("bound,reason,message,hex_value", CASES)
@pytest.mark.parametrize("interaction", ["ordered", "simultaneous"])
def test_range_without_a_feasible_scale_refuses_alpha_from_step(
    bound, reason, message, hex_value, interaction
):
    steps = (
        MaximumSupportedDemand(name="m", demand_set="d", alpha_max=bound),
        TrafficMatrixPlacement(
            name="p", demand_set="d", alpha_from_step="m", interaction=interaction
        ),
    )
    with pytest.raises(ValueError) as caught:
        run(prepare(scenario(workflow=steps)))
    assert str(caught.value) == "alpha_from_step 'm': no tested feasible alpha"
    safe_steps = (
        MaximumSupportedDemand(name="m", demand_set="d", alpha_max=4),
        steps[1],
    )
    result = run(prepare(scenario(workflow=safe_steps)))
    assert result.steps[0].result.search_status == "trivial"
    placement = result.steps[1].result
    assert placement.alpha.value == 4
    assert placement.accounting[0].discarded_units == 40_000_000_000
    assert placement.cases[0].states["converged"].rows == ()
