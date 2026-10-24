"""Compact summaries and native detail selection preserve the same observations."""

from dataclasses import replace

import jsonschema
import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
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
    SensitivityQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    maximum_supported_demand,
    place,
    prepare,
)
from tests.analysis.test_failure_states import ALL, e80, run
from tests.results.test_analysis_wire import VALIDATOR, project

COMPACT = {
    "request_kind",
    "requested_units",
    "offered_units",
    "delivered_units",
    "unadmitted_units",
    "source_drop_units",
    "edge_drop_units",
    "termination",
    "total_cost",
}
DETAILS = {
    "call_delivered_units",
    "call_undelivered_units",
    "delivery_delta_units",
    "call_edge_drops",
    "call_source_drop_units",
    "admitted_units",
    "edge_drops",
    "by_source",
    "by_tunnel",
    "plan",
}


def prepared(*, pooled=False):
    network = Network(nodes={name: Node(name) for name in ("a", "t")})
    network.add_link(Link("a", "t", 32, 3))
    load = DemandSet(
        "load",
        (
            DemandSpec(
                Selector("^a$"),
                Selector("^t$"),
                16,
                FlowPolicyPreset.TE_ECMP_16_LSP
                if pooled
                else FlowPolicyPreset.TE_MAXFLOW_UNLIM,
            ),
        ),
    )
    return prepare(
        Scenario(network, demand_sets={"load": load}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )


def observed(kind, details, *, flags=False, costs=False):
    p = prepared(pooled=kind == "pool")
    outputs = ngc.OutputOptions(edge_flows=flags, min_cut=flags)
    if kind == "capacity":
        value = capacity(
            p,
            CapacityQuery(
                Selector("^a$"),
                Selector("^t$"),
                workers=1,
                outputs=outputs,
                export_cost_distribution=costs,
                export_details=details,
            ),
        )
    elif kind == "sensitivity":
        value = edge_sensitivity(
            p,
            SensitivityQuery(
                Selector("^a$"),
                Selector("^t$"),
                ngc.FlowPolicyConfig(
                    routing=ngc.CentralizedTE(
                        source_allocation=ngc.SourceAllocation.OPTIMIZED
                    )
                ),
                workers=1,
                outputs=outputs,
                export_details=details,
            ),
        )
    elif kind == "msd":
        value = maximum_supported_demand(
            p, MSDQuery(p.demand_sets["load"], export_details=details)
        )
    else:
        value = place(
            p,
            PlacementQuery(
                p.demand_sets["load"],
                workers=1,
                outputs=outputs,
                export_cost_distribution=costs,
                export_details=details,
                states=("converged",),
            ),
        )
    wire = project(value)["analysis"]
    if kind == "sensitivity":
        row, native = None, wire["baseline"]
    elif kind == "msd":
        row = wire["best_rows"][0]
        native = row["result"]
    else:
        row = wire["cases"][0]["states"]["converged"]["rows"][0]
        native = row["result"]
    return value, wire, row, native


@pytest.mark.parametrize(
    "kind", ["capacity", "placement", "pool", "sensitivity", "msd"]
)
@pytest.mark.parametrize("details", [False, True])
def test_compact_and_detailed_rows_keep_native_values_and_pool_cost_domain(
    kind, details
):
    value, wire, row, native = observed(kind, details)
    assert set(native) == COMPACT | (DETAILS if details else set())
    assert wire["outputs"]["details"] is details
    assert native["edge_drop_units"] == native["source_drop_units"] == 0
    assert native["delivered_units"] == (16 if kind in ("placement", "pool") else 32)
    if row is not None:
        assert "pool" in row
        if kind == "pool":
            assert row["pool"] == {
                "head": {"pool_id": "load|0|0", "physical_sources": ["a"]},
                "offer_limit_units": 0,
                "synthetic_ingress_cost": 1,
            }
        else:
            assert row["pool"] is None
    if details:
        assert isinstance(native["by_source"], list) and isinstance(
            native["by_tunnel"], list
        )
    if kind == "sensitivity":
        snapshot = value.result.baseline
    elif kind == "msd":
        snapshot = value.best_rows[0].result
    else:
        snapshot = value.cases[0].states["converged"].rows[0].result
    assert snapshot.by_source[0].delivered == native["delivered_units"]
    assert snapshot.plan is not None if kind == "pool" else snapshot.plan is None


@pytest.mark.parametrize("details", [False, True])
@pytest.mark.parametrize("flags", [False, True])
@pytest.mark.parametrize("costs", [False, True])
def test_detail_native_flags_and_cost_report_are_independent(details, flags, costs):
    _, _, row, native = observed("capacity", details, flags=flags, costs=costs)
    assert ("by_source" in native) is details
    assert ("min_cut" in native) is flags
    assert ("edge_flows" in native) is flags
    assert ("cost_distribution" in row) is costs
    assert native["total_cost"] == 96


@pytest.mark.parametrize("details", [False, True])
@pytest.mark.parametrize("retained", [False, True])
def test_msd_details_do_not_change_probe_retention(details, retained):
    p = prepared()
    value = maximum_supported_demand(
        p,
        MSDQuery(
            p.demand_sets["load"], export_details=details, export_probe_rows=retained
        ),
    )
    wire = project(value)["analysis"]
    assert ("probe_rows" in wire) is retained
    assert all(
        set(probe) == {"index", "alpha", "outcome", "totals", "range_refusal"}
        for probe in wire["history"]
    )
    rows = wire["best_rows"] + [
        row for probe in wire.get("probe_rows", []) for row in probe["rows"]
    ]
    assert all(("by_source" in row["result"]) is details for row in rows)


def test_compact_projection_reads_only_required_native_fields(monkeypatch):
    value, _, _, _ = observed("placement", False)
    getter = ngc.PlacementResult.edge_drops
    calls = []

    def drops(result):
        calls.append(result)
        return getter.__get__(result)

    def forbidden(result):
        raise AssertionError("unrequested native detail")

    with monkeypatch.context() as patch:
        patch.setattr(ngc.PlacementResult, "edge_drops", property(drops))
        for field in (
            "by_source",
            "by_tunnel",
            "plan",
            "admitted",
            "call_delivered",
            "call_undelivered",
            "call_edge_drops",
            "call_source_drops",
            "delivery_delta",
        ):
            patch.setattr(ngc.PlacementResult, field, property(forbidden))
        assert (
            project(value)["analysis"]["cases"][0]["states"]["converged"]["rows"][0][
                "result"
            ]["delivered_units"]
            == 16
        )
        assert len(calls) == 1
        detailed = replace(value, outputs=replace(value.outputs, details=True))
        with pytest.raises(AssertionError, match="unrequested native detail"):
            project(detailed)
    assert project(detailed)["analysis"]["outputs"]["details"] is True


def test_schema_refuses_detail_presence_swapped_with_selection():
    for details in (False, True):
        value, _, _, _ = observed("capacity", details)
        wire = project(value)
        wire["analysis"]["outputs"]["details"] = not details
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(wire)


@pytest.mark.parametrize("details", [False, True])
def test_compact_loss_totals_are_observed_exactly_and_poison_is_caught(
    monkeypatch, details
):
    import ngraph.export as exporting

    network = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    network.add_link(Link("a", "b", 10, 1))
    network.add_link(Link("b", "t", 4, 1))
    p = prepare(Scenario(network, units=UnitsSettings(1)))
    value = capacity(
        p,
        CapacityQuery(
            Selector("^a$"),
            Selector("^t$"),
            config=ngc.FlowPolicyConfig(
                routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
            ),
            offer=10,
            workers=1,
            export_details=details,
        ),
    )

    def oracle():
        native = project(value)["analysis"]["cases"][0]["states"]["converged"]["rows"][
            0
        ]["result"]
        # The first link injects10; the second carries4 and loses6, with no source loss.
        assert native["requested_units"] == native["offered_units"] == 10
        assert native["delivered_units"] == 4
        assert native["source_drop_units"] == native["unadmitted_units"] == 0
        assert native["edge_drop_units"] == 6
        if details:
            assert native["edge_drops"] == [
                {"edge": {"link": "b|t|0", "direction": "forward"}, "units": 6}
            ]

    oracle()
    original = exporting._native

    def poison(*args, **kwargs):
        result = original(*args, **kwargs)
        result["edge_drop_units"] = 0
        return result

    with monkeypatch.context() as patch:
        patch.setattr(exporting, "_native", poison)
        with pytest.raises(AssertionError):
            oracle()
    oracle()


@pytest.mark.parametrize("bad", [None, 0, 1, "true", [], {}])
def test_query_details_requires_actual_boolean(bad):
    p = prepared()
    for ctor, args in [
        (CapacityQuery, (Selector("a"), Selector("t"))),
        (PlacementQuery, (p.demand_sets["load"],)),
        (MSDQuery, (p.demand_sets["load"],)),
        (
            SensitivityQuery,
            (
                Selector("a"),
                Selector("t"),
                ngc.FlowPolicyConfig(
                    routing=ngc.CentralizedTE(
                        source_allocation=ngc.SourceAllocation.OPTIMIZED
                    )
                ),
            ),
        ),
    ]:
        with pytest.raises((TypeError, ValueError), match="export_details"):
            ctor(*args, export_details=bad)


@pytest.mark.parametrize("details", [False, True])
def test_every_placement_state_follows_the_detail_selection(details):
    # Detailed rows carry the replay plan in every state, compact rows in none, and
    # the schema refuses either swapped in any state.
    wire = project(run(e80(), states=ALL, export_details=details))
    VALIDATOR.validate(wire)
    for state in ALL:
        rows = wire["analysis"]["cases"][0]["states"][state]["rows"]
        assert all(("plan" in row["result"]) is details for row in rows)
        result = rows[0]["result"]
        if details:
            plan = result.pop("plan")
        else:
            result["plan"] = None
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(wire)
        if details:
            result["plan"] = plan
        else:
            del result["plan"]
