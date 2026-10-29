"""Independent amount/label oracles and closed wire validation for native analyses."""

import json
from copy import deepcopy
from dataclasses import replace
from importlib.resources import files
from io import StringIO

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
    PathQuery,
    PlacementQuery,
    Scenario,
    Selector,
    SensitivityQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    maximum_supported_demand,
    paths,
    place,
    prepare,
    run,
    write_json,
)
from ngraph.results import StepOutput
from ngraph.workflow.base import WorkflowStep
from ngraph.workflow.build_graph import BuildGraph
from tests.question import asked

SCHEMA = json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def project(value):
    output = StringIO()
    write_json(value, output)
    wire = json.loads(output.getvalue())
    VALIDATOR.validate(wire)
    return wire


def graph():
    network = Network()
    for name in ("a", "b", "t"):
        network.add_node(Node(name))
    for source, target, cap, cost in (
        ("a", "b", 2, 1),
        ("b", "t", 2, 2),
        ("a", "t", 3, 5),
    ):
        network.add_link(Link(source, target, cap, cost))
    return network


def prepared(volumes=(4, 3)):
    demands = DemandSet(
        "load",
        tuple(
            DemandSpec(
                Selector("^a$"), Selector("^t$"), v, FlowPolicyPreset.TE_MAXFLOW_UNLIM
            )
            for v in volumes
        ),
    )
    return prepare(
        Scenario(graph(), demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )


def edge(link, direction="forward"):
    return {"link": link, "direction": direction}


def test_capacity_native_wire_all_amounts_arrays_cuts_and_requested_curve():
    context = prepared()
    outputs = ngc.OutputOptions(
        edge_flows=True,
        residual=True,
        edge_reservations=True,
        saturated_boundary_edges=True,
        min_cut=True,
    )
    analysis = capacity(
        context,
        CapacityQuery(
            Selector("^a$"),
            Selector("^t$"),
            workers=1,
            outputs=outputs,
            export_cost_distribution=True,
            export_details=True,
        ),
    )
    wire = project(analysis)
    row = wire["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    native = row["result"]
    expected = {
        "request_kind": "unlimited",
        "requested_units": None,
        "call_delivered_units": 5,
        "call_undelivered_units": None,
        "delivery_delta_units": 5,
        "call_edge_drops": [],
        "call_source_drop_units": 0,
        "termination": "exhausted",
        "offered_units": None,
        "admitted_units": 5,
        "delivered_units": 5,
        "unadmitted_units": None,
        "source_drop_units": 0,
        "edge_drops": [],
        "edge_drop_units": 0,
        "by_source": [
            {
                "source": "a",
                "offered_units": None,
                "admitted_units": 5,
                "delivered_units": 5,
                "source_drop_units": 0,
                "total_edge_drop_units": 0,
            }
        ],
        "by_tunnel": [
            {
                "entry_id": 0,
                "head": "a",
                "status": "up",
                "assigned_units": 2,
                "delivered_units": 2,
                "total_edge_drop_units": 0,
            },
            {
                "entry_id": 1,
                "head": "a",
                "status": "up",
                "assigned_units": 3,
                "delivered_units": 3,
                "total_edge_drop_units": 0,
            },
        ],
        "plan": None,
        "total_cost": 21,
    }
    declared_edges = [
        edge("a|b|0"),
        edge("a|b|0", "reverse"),
        edge("a|t|0"),
        edge("a|t|0", "reverse"),
        edge("b|t|0"),
        edge("b|t|0", "reverse"),
    ]
    ordered_edges = [
        declared_edges[int(i)] for i in context.topology.graph.input_positions()
    ]
    carried = {
        ("a|b|0", "forward"): 2,
        ("a|t|0", "forward"): 3,
        ("b|t|0", "forward"): 2,
    }
    capacities = {"a|b|0": 2, "a|t|0": 3, "b|t|0": 2}
    flow = [carried.get((ref["link"], ref["direction"]), 0) for ref in ordered_edges]
    for key, amounts in (
        ("edge_flows", flow),
        (
            "residual",
            [
                capacities[ref["link"]] - units
                for ref, units in zip(ordered_edges, flow, strict=True)
            ],
        ),
        ("edge_reservations", (0, 0, 0, 0, 0, 0)),
    ):
        expected[key] = [
            {"edge": ref, "units": units}
            for ref, units in zip(ordered_edges, amounts, strict=True)
        ]
    expected["min_cut"] = [edge("a|b|0"), edge("a|t|0")]
    expected["saturated_boundary_edges"] = [edge("a|b|0"), edge("a|t|0")]
    assert native == expected
    assert row["cost_distribution"] == {
        "kind": "marginal_curve",
        "cost_domain": "physical_network",
        "bins": [{"marginal_cost": 3, "units": 2}, {"marginal_cost": 5, "units": 3}],
    }
    assert row["endpoints"] == {"sources": ["a"], "destinations": ["t"]}
    assert (
        row["id"] == "pair-000000" and row["pool"] is None and row["kind"] == "capacity"
    )
    assert wire["analysis"]["cases"][0]["states"]["converged"]["totals"] is None
    assert wire["analysis"]["question"] == "lossless_bound"
    assert wire["analysis"]["offer_source"] == "unlimited"
    assert wire["analysis"]["query"]["offer"] is None


def test_default_outputs_are_absent_finite_zero_is_not_unlimited():
    context = prepared()
    wire = project(
        capacity(
            context, CapacityQuery(Selector("^a$"), Selector("^t$"), offer=0, workers=1)
        )
    )
    row = wire["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    assert not set(row) & {"cost_distribution", "unavailable_outputs"}
    result = row["result"]
    assert result["request_kind"] == "finite" and result["requested_units"] == 0
    assert result["delivered_units"] == result["unadmitted_units"] == 0
    assert result["termination"] == "complete"
    assert not set(result) & {
        "edge_flows",
        "residual",
        "edge_reservations",
        "min_cut",
        "saturated_boundary_edges",
        "marginal_cost_curve",
        "synthetic_ingress",
    }


def test_placement_and_msd_exact_totals_history_and_declared_query():
    context = prepared()
    wire = project(
        place(context, PlacementQuery(context.demand_sets["load"], workers=1))
    )
    state = wire["analysis"]["cases"][0]["states"]["converged"]
    assert state["totals"] == {
        "reference_request_units": 7,
        "delivered_units": 5,
        "unadmitted_units": 2,
        "source_drop_units": 0,
        "edge_drop_units": 0,
        "reference_shortfall_units": 2,
        "delivery_ratio": {"numerator": 5, "denominator": 7},
        "feasible": False,
    }
    assert [r["reference_shortfall_units"] for r in state["rows"]] == [0, 2]
    assert [r["result"]["total_cost"] for r in state["rows"]] == [16, 5]
    analysis = maximum_supported_demand(
        context,
        MSDQuery(
            context.demand_sets["load"],
            alpha_min=0.25,
            alpha_max=2,
            alpha_tolerance=0.125,
        ),
    )
    msd = project(analysis)["analysis"]
    assert "probe_rows" not in msd and msd["query"]["export_probe_rows"] is False
    assert len(msd["history"]) == len(analysis.history)
    assert [p["index"] for p in msd["history"]] == list(range(len(msd["history"])))
    for probe in msd["history"]:
        assert set(probe) == {"index", "alpha", "outcome", "totals", "range_refusal"}
        assert probe["alpha"]["value"].as_integer_ratio() == (
            probe["alpha"]["numerator"],
            probe["alpha"]["denominator"],
        )
        assert probe["totals"]["feasible"] == (probe["outcome"] == "feasible")
    best = msd["history"][msd["best_probe_index"]]
    assert msd["alpha_feasible"] == best["alpha"]
    assert best["alpha"]["value"] == max(
        p["alpha"]["value"] for p in msd["history"] if p["outcome"] == "feasible"
    )


def test_path_question_effective_min_residual_and_ksp_null_with_wire_refusals():
    context = prepared()
    for minimum, expected_cost in ((1, 3), (3, 5)):
        analysis = paths(
            context,
            PathQuery(
                Selector("^a$"),
                Selector("^t$"),
                options=ngc.SpfOptions(
                    ngc.Direction.FORWARD,
                    residual=context.topology.graph.edge_capacity_units(),
                    min_residual=minimum,
                ),
            ),
        )
        assert asked(analysis)["min_residual"] == minimum
        wire = project(analysis)
        assert wire["analysis"]["query"]["min_residual"] == minimum
        assert wire["analysis"]["rows"][0]["cost"] == expected_cost
        for value in (None, 0, "1"):
            broken = deepcopy(wire)
            broken["analysis"]["query"]["min_residual"] = value
            with pytest.raises(jsonschema.ValidationError):
                VALIDATOR.validate(broken)
        broken = deepcopy(wire)
        del broken["analysis"]["query"]["min_residual"]
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(broken)
    ksp = project(
        paths(
            context,
            PathQuery(Selector("^a$"), Selector("^t$"), options=ngc.KspOptions(k=2)),
        )
    )
    assert ksp["analysis"]["query"]["min_residual"] is None
    assert ksp["analysis"]["query"]["residual_units"] is None


def test_sensitivity_retains_native_baseline_and_wire_omits_exact_zero_entries():
    context = prepared()
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    analysis = edge_sensitivity(
        context,
        SensitivityQuery(Selector("^a$"), Selector("^t$"), config, workers=1),
    )
    wire = project(analysis)["analysis"]
    assert wire["baseline"]["delivered_units"] == 5
    assert {
        tuple(row["edge"].values()): row["delivery_reduction_units"]
        for row in wire["entries"]
    } == {("a|b|0", "forward"): 2, ("a|t|0", "forward"): 3, ("b|t|0", "forward"): 2}
    assert all(row["delivery_reduction_units"] != 0 for row in wire["entries"])


def test_big_integer_totals_and_costs_never_round_through_float():
    context = prepared((*(2**61 for _ in range(9)), 3))
    result = place(context, PlacementQuery(context.demand_sets["load"], workers=1))
    totals = project(result)["analysis"]["cases"][0]["states"]["converged"]["totals"]
    assert totals["reference_request_units"] == 9 * 2**61 + 3 > 2**64
    assert type(totals["reference_request_units"]) is int
    assert totals["unadmitted_units"] == 9 * 2**61 - 2
    network = Network()
    for name in ("s", "t"):
        network.add_node(Node(name))
    network.add_link(Link("s", "t", 2**40, 2**30))
    context = prepare(Scenario(network, units=UnitsSettings(1)))
    result = capacity(context, CapacityQuery(Selector("s"), Selector("t"), workers=1))
    native = project(result)["analysis"]["cases"][0]["states"]["converged"]["rows"][0][
        "result"
    ]
    assert type(native["total_cost"]) is int and native["total_cost"] == 2**70


def test_closed_schema_rejects_bad_builtin_fields_in_run_and_analysis():
    wire = project(run(prepare(Scenario(Network(), [BuildGraph()]))))
    for mutation in (
        lambda row: row.pop("node_count"),
        lambda row: row.update(node_count=None),
        lambda row: row.update(extra=True),
    ):
        broken = deepcopy(wire)
        mutation(broken["steps"][0]["result"])
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(broken)


def test_run_rejects_a_forged_report_without_mutating_preparation():
    context = prepared()
    value = capacity(context, CapacityQuery(Selector("a"), Selector("t"), workers=1))

    class Step(WorkflowStep):
        def run(self, context):
            return StepOutput(value.query, value)

    for bad in (replace(value.units_report, exponent=value.units_report.exponent + 1),):
        forged = replace(context, units_report=bad)

        class Bad(WorkflowStep):
            def run(self, context, forged=forged):
                return StepOutput(value.query, replace(value, prepared=forged))

        target = replace(
            context,
            scenario=Scenario(context.scenario.network, [Bad()]),
            _steps=(("Bad", None, "none"),),
        )
        with pytest.raises(ValueError, match="units/topology do not belong"):
            run(target)
    target = replace(
        context,
        scenario=Scenario(context.scenario.network, [Step()]),
        _steps=(("Step", None, "none"),),
    )
    assert run(target).steps[0].result is value
