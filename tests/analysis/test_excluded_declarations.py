"""Whole-declaration exclusions retain their own reason and never own traffic pools."""

import json
from fractions import Fraction
from importlib.resources import files
from io import StringIO

import jsonschema
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    MSDQuery,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    maximum_supported_demand,
    place,
    prepare,
    run,
    write_json,
)
from ngraph.analysis.demands import scaled_expansion
from ngraph.results import ExpansionLeaf
from ngraph.workflow import TrafficMatrixPlacement, TunnelCountAnalysis

TE = FlowPolicyPreset.TE_ECMP_16_LSP


def network():
    value = Network(nodes={n: Node(n) for n in ("A", "B", "C")})
    value.add_link(Link("A", "B", 100, 1))
    value.add_link(Link("B", "C", 100, 2))
    return value


def wire(value):
    sink = StringIO()
    write_json(value, sink)
    document = json.loads(sink.getvalue())
    jsonschema.Draft202012Validator(
        json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
    ).validate(document)
    return document


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("order", ["self_first", "filtered_first", "nonempty_mixed"])
def test_wholly_excluded_mixed_root_uses_first_canonical_exclusion(mode, order):
    if order == "nonempty_mixed":
        net = Network(
            nodes={
                "x": Node("x", attrs={"s": "m", "t": "z"}),
                "y": Node("y", attrs={"s": "other", "t": "m"}),
            }
        )
        source, target = Selector("^x$", group_by="s"), Selector("^[xy]$", group_by="t")
        reason = "filtered"
    else:
        net = Network(
            nodes={"C": Node("C", attrs={"h": "A"}), "A": Node("A", attrs={"h": "C"})}
        )
        source = Selector("^A$" if order == "self_first" else "^C$", group_by="h")
        target = Selector("^(A|C)$")
        reason = "self_pair" if order == "self_first" else "filtered"
    spec = DemandSpec(source, target, 11, mode=mode, group_mode="group_pairwise")
    prepared = prepare(
        Scenario(
            net, demand_sets={"d": DemandSet("d", (spec,))}, units=UnitsSettings(1)
        ),
        demand_sets=("d",),
    )
    ds = prepared.demand_sets["d"]
    assert ds.demands == ()
    root = ds.expansion_template[0].root
    assert isinstance(root, ExpansionLeaf)
    assert (root.id, root.order, root.endpoints, root.discard_reason) == (
        "d|0|0",
        0,
        None,
        reason,
    )
    for alpha in (1, 4):
        amounts, (accounting,) = scaled_expansion(ds, alpha, 1)
        assert dict(amounts) == {}
        assert (
            accounting.base_id,
            accounting.declared_units,
            accounting.resolved_units,
            accounting.discarded_units,
        ) == ("d|0", 11 * alpha, 0, 11 * alpha)
        assert [(s.label, s.units, s.reason) for s in accounting.discards] == [
            ("d|0|0", 11 * alpha, reason)
        ]
        exported = wire(place(prepared, PlacementQuery(ds, alpha=alpha, workers=1)))[
            "analysis"
        ]
        assert exported["accounting"] == [
            {
                "base_id": "d|0",
                "declared_units": 11 * alpha,
                "resolved_units": 0,
                "discarded_units": 11 * alpha,
                "discards": [{"label": "d|0|0", "units": 11 * alpha, "reason": reason}],
            }
        ]
        assert exported["cases"][0]["states"]["converged"]["rows"] == []


@pytest.mark.parametrize("first_reason", ["self_pair", "filtered"])
def test_each_declaration_owns_its_exclusion_reason(first_reason):
    first = DemandSpec(
        Selector("^(A)$"),
        Selector("^(A|B)$"),
        4,
        mode="pairwise",
        group_mode="flatten" if first_reason == "self_pair" else "group_pairwise",
    )
    second_reason = "filtered" if first_reason == "self_pair" else "self_pair"
    second = DemandSpec(
        Selector("^(C)$"),
        Selector("^(C)$"),
        6,
        group_mode="group_pairwise" if second_reason == "filtered" else "flatten",
    )
    prepared = prepare(
        Scenario(
            network(),
            demand_sets={"d": DemandSet("d", (first, second))},
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )
    ds = prepared.demand_sets["d"]
    assert [(d.id, d.base_id, d.nominal_units) for d in ds.demands] == [
        ("d|0|0", "d|0", 4)
    ]
    assert [
        (
            a.base_id,
            a.declared_units,
            a.resolved_units,
            a.discarded_units,
            [(s.label, s.units, s.reason) for s in a.discards],
        )
        for a in ds.accounting
    ] == [("d|0", 4, 4, 0, []), ("d|1", 6, 0, 6, [("d|1|0", 6, second_reason)])]


@pytest.mark.parametrize("interaction", ["ordered", "simultaneous"])
@pytest.mark.parametrize("excluded", ["self_pair", "filtered", "empty_selection"])
def test_wholly_excluded_pooled_declaration_owns_no_pool_or_budget(
    interaction, excluded
):
    dead = DemandSpec(
        Selector("^missing$" if excluded == "empty_selection" else "^(A)$"),
        Selector("^(A)$"),
        6,
        TE,
        id="dead",
        group_mode="group_pairwise" if excluded == "filtered" else "flatten",
    )
    live = DemandSpec(Selector("^B$"), Selector("^C$"), 6, TE, id="live")
    workflow = (
        TrafficMatrixPlacement(
            name="p", demand_set="d", interaction=interaction, workers=2
        ),
        TunnelCountAnalysis(
            name="counts",
            demand_set="d",
            counts=(1,),
            design_demand=1,
            offer=2,
            workers=2,
        ),
    )

    def prepared(specs):
        return prepare(
            Scenario(
                network(),
                workflow,
                demand_sets={"d": DemandSet("d", specs)},
                units=UnitsSettings(1),
                seed=42,
            )
        )

    control, augmented = prepared((live,)), prepared((dead, live))
    assert tuple(augmented.topology.pool_heads) == ("live|0",)
    ds = augmented.demand_sets["d"]
    assert [
        (d.id, d.nominal_units, d.pool.head.physical_sources, d.pool.offer_limit_units)
        for d in ds.demands
    ] == [("live|0", 6, ("B",), 6 if interaction == "simultaneous" else 2)]
    assert [(s.label, s.units, s.reason) for s in ds.accounting[0].discards] == [
        ("dead|0", 6, excluded)
    ]
    before, after = run(control), run(augmented)
    old_wire, new_wire = wire(before), wire(after)
    assert json.dumps(old_wire["steps"][0]["result"]["cases"]) == json.dumps(
        new_wire["steps"][0]["result"]["cases"]
    )
    assert json.dumps(old_wire["steps"][1]["result"]["rows"]) == json.dumps(
        new_wire["steps"][1]["result"]["rows"]
    )
    placement = after.steps[0].result.cases[0].states["converged"]
    assert (
        placement.totals.reference_request_units,
        placement.totals.delivered_units,
    ) == (6, 6)
    (count,) = after.steps[1].result.rows
    assert (
        count.id,
        count.result.requested,
        count.result.delivered,
        count.lossless_at_design_units,
        count.physical_tunnel_cost,
    ) == ("live|0", 2, 2, 1, 2)


@pytest.mark.parametrize(
    "kind",
    [
        "zero",
        "self_pair",
        "filtered",
        "empty_selection",
        "no_shared_labels",
        "empty_groups",
        "discarded_and_zero",
    ],
)
@pytest.mark.parametrize("retain", [False, True])
def test_msd_nothing_offered_is_one_trivial_probe_with_accounting(kind, retain):
    live_zero = DemandSpec(Selector("^B$"), Selector("^C$"), 0, id="zero")
    if kind == "zero":
        specs = (live_zero,)
    elif kind == "no_shared_labels":
        specs = (
            DemandSpec(
                Selector("^(A)$"),
                Selector("^(B)$"),
                6,
                id="dead",
                mode="pairwise",
                group_mode="per_group",
            ),
        )
    elif kind == "empty_groups":
        specs = (
            DemandSpec(
                Selector("^(A|B)$"),
                Selector("^missing$"),
                6,
                id="dead",
                group_mode="per_group",
            ),
        )
    else:
        dead = DemandSpec(
            Selector("^missing$" if kind == "empty_selection" else "^(A)$"),
            Selector("^(A)$"),
            6,
            id="dead",
            group_mode="group_pairwise" if kind == "filtered" else "flatten",
        )
        specs = (dead, live_zero) if kind == "discarded_and_zero" else (dead,)
    prepared = prepare(
        Scenario(
            network(), demand_sets={"d": DemandSet("d", specs)}, units=UnitsSettings(1)
        ),
        demand_sets=("d",),
    )
    ds = prepared.demand_sets["d"]
    result = maximum_supported_demand(
        prepared, MSDQuery(ds, alpha_max=4, export_probe_rows=retain)
    )
    assert (
        result.search_status,
        result.stop_reason,
        result.proof,
        result.monotone_proven,
    ) == ("trivial", "nothing_offered", "nothing_offered", True)
    assert result.best_probe_index == 0 and result.alpha_feasible.value == 4
    assert result.upper_certificate is None
    assert len(result.history) == 1
    probe = result.history[0]
    assert (probe.index, probe.alpha.value, probe.outcome, probe.range_refusal) == (
        0,
        4,
        "feasible",
        None,
    )
    totals = probe.totals
    assert (
        totals.reference_request_units,
        totals.delivered_units,
        totals.unadmitted_units,
        totals.source_drop_units,
        totals.edge_drop_units,
        totals.reference_shortfall_units,
        totals.delivery_ratio,
        totals.feasible,
    ) == (0, 0, 0, 0, 0, 0, Fraction(1), True)
    assert (
        [
            (r.id, r.reference_request_units, r.result.delivered)
            for r in result.best_rows
        ]
        == [("zero|0", 0, 0)]
        if kind in ("zero", "discarded_and_zero")
        else result.best_rows == ()
    )
    assert (dict(result.probe_rows) if retain else result.probe_rows) == (
        {0: result.best_rows} if retain else None
    )
    exported = wire(result)["analysis"]
    assert (
        exported["proof"],
        exported["stop_reason"],
        exported["search_status"],
        exported["best_probe_index"],
        exported["alpha_feasible"],
    ) == (
        "nothing_offered",
        "nothing_offered",
        "trivial",
        0,
        {"value": 4.0, "numerator": 4, "denominator": 1},
    )
    expected = []
    for spec in specs:
        declared = int(spec.volume) * 4
        reason = (
            "filtered"
            if kind == "filtered"
            else "empty_selection"
            if kind in ("empty_selection", "no_shared_labels", "empty_groups")
            else "self_pair"
        )
        discards = (
            []
            if spec.id == "zero"
            else (
                [
                    {"label": "dead|0", "units": 12, "reason": reason},
                    {"label": "dead|1", "units": 12, "reason": reason},
                ]
                if kind == "empty_groups"
                else [{"label": "dead|0", "units": declared, "reason": reason}]
            )
        )
        expected.append(
            {
                "base_id": spec.id,
                "declared_units": declared,
                "resolved_units": 0,
                "discarded_units": declared,
                "discards": discards,
            }
        )
    assert exported["best_accounting"] == expected


def test_msd_positive_rounded_zero_and_unreachable_traffic_still_offer_traffic():
    net = network()
    for source, target, volume in [("A", "C", 0.25), ("C", "missing", 6)]:
        if target == "missing":
            net = Network(nodes={n: Node(n) for n in ("A", "C")})
            target = "A"
        spec = DemandSpec(Selector(f"^{source}$"), Selector(f"^{target}$"), volume)
        prepared = prepare(
            Scenario(
                net, demand_sets={"d": DemandSet("d", (spec,))}, units=UnitsSettings(1)
            ),
            demand_sets=("d",),
        )
        result = maximum_supported_demand(
            prepared, MSDQuery(prepared.demand_sets["d"], alpha_max=4)
        )
        assert result.proof == "fixed_program" and result.search_status != "trivial"
        assert result.history[0].outcome == (
            "below_resolution" if volume == 0.25 else "infeasible"
        )
