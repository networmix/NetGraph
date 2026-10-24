"""Nonempty units diagnostics retain exact errors, constraints and probe locations."""

from copy import deepcopy
from fractions import Fraction

import jsonschema
import netgraph_core as ngc
import pytest

import ngraph.export as exporting
from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    place,
    prepare,
)
from ngraph.results import UnitsReport
from tests.results.test_analysis_wire import project
from tests.results.test_native_field_plants import at
from tests.results.test_report_field_plants import change, exact, field_paths


def fraction(value):
    value = Fraction(value)
    return {"numerator": value.numerator, "denominator": value.denominator}


def input_bound(label, amount, precision):
    bound = 2 * Fraction(precision) * Fraction(amount)
    return {
        "kind": "input",
        "label": label,
        "q_upper_bound": fraction(bound),
        "met": Fraction(1) <= bound,
    }


def sample(label, kind):
    return {
        "label": label,
        "kind": kind,
        "binary64_value": 0.25,
        "binary64_hex": "0x1.0000000000000p-2",
        "units": 0,
        "error": fraction(Fraction(-1, 4)),
        "relative_error": fraction(-1),
    }


def oracle(variant):
    if variant == "opaque":
        return opaque_oracle()
    network = Network(
        nodes={
            name: Node(name)
            for name in (("a", "b", "t") if variant == "split" else ("s", "t"))
        }
    )
    precision = 1e-18 if variant == "range" else 0.125
    volume = 1 if variant == "split" else 0.25
    if variant == "split":
        network.add_link(Link("a", "t", 4, 1))
        network.add_link(Link("b", "t", 4, 3))
    else:
        network.add_link(Link("s", "t", 2**60 if variant == "range" else 0.25, 3))
    demand_set = DemandSet(
        "load",
        (
            DemandSpec(
                Selector("^[ab]$" if variant == "split" else "^s$"),
                Selector("^t$"),
                volume,
            ),
        ),
    )
    context = prepare(
        Scenario(
            network,
            demand_sets={"load": demand_set},
            units=UnitsSettings("auto" if variant == "range" else 1, precision),
        ),
        demand_sets=("load",),
    )
    analysis = place(
        context,
        PlacementQuery(
            context.demand_sets["load"],
            alpha=4 if variant == "rounding" else 1,
            workers=1,
        ),
    )
    demand_label = "demand.load|0.volume"
    nominal_constraints = [input_bound(demand_label, volume, precision)]
    observed_constraints = [
        input_bound(demand_label, 1 if variant == "rounding" else volume, precision)
    ]
    nominal_splits = []
    nominal_examples = [sample(demand_label, "demand")] if variant != "split" else []
    observed_examples = []
    if variant == "rounding":
        label = "link.s|t|0.capacity"
        nominal_constraints.append(input_bound(label, 0.25, precision))
        observed_constraints.append(input_bound(label, 0.25, precision))
        nominal_examples.append(sample(label, "capacity"))
        observed_examples.append(sample(label, "capacity"))
    if variant == "split":
        # Each capacity4 binds at q1: 2*p*4=1 meets q1, fails q2.
        nominal_constraints.extend(
            input_bound(f"link.{source}|t|0.capacity", 4, precision)
            for source in ("a", "b")
        )
        # One combined two-source leaf gives one equal-source split of y1.
        # q bound=(1/8)*1/(2-1)=1/8, independent of integer admission.
        split = {
            "kind": "source",
            "label": "demand.load|0|0.sources",
            "incoming_physical": fraction(1),
            "basis": "declared",
            "members": 2,
            "q_upper_bound": fraction(Fraction(1, 8)),
            "met": False,
        }
        nominal_splits.append(split)
        nominal_constraints.append(split)
        observed_constraints.append(split)
    if variant == "range":
        # q1 fits directed sum2^61; q1/2 reaches the excluded2^62 bound.
        nominal_constraints.append(
            {
                "kind": "capacity_sum",
                "label": "topology.augmented_capacity_sum",
                "tested_q": 0.5,
                "units_value": 2**62,
                "exclusive_limit": 2**62,
                "met": False,
            }
        )
        observed_examples = [sample(demand_label, "demand")]
    expected = {
        "q": 1.0,
        "exponent": 0,
        "mode": "auto" if variant == "range" else "manual",
        "precision": precision,
        "target_met": False,
        "input_convention": "promoted_binary64_half_up",
        "display_convention": "units_authoritative_binary64_display",
        "scope": {
            "workflow_steps": [],
            "workflow_demand_sets": [],
            "library_demand_sets": ["load"],
        },
        "binding_constraints": nominal_constraints,
        "input_count": 3 if variant == "split" else 2,
        "inexact_inputs": len(nominal_examples),
        "zeroed_inputs": len(nominal_examples),
        "inexact_examples": nominal_examples,
        "zeroed_examples": nominal_examples,
        "max_absolute_input_error": fraction(Fraction(1, 4) if nominal_examples else 0),
        "max_relative_input_error": fraction(1 if nominal_examples else 0),
        "augmented_capacity_sum_units": {"rounding": 0, "split": 16, "range": 2**61}[
            variant
        ],
        "augmented_cost_sum": 8 if variant == "split" else 6,
        "nominal_split_count": len(nominal_splits),
        "nominal_splits": nominal_splits,
        "misses": [
            {
                "location": {"step": None, "case_id": "baseline", "probe_index": None},
                "constraints": observed_constraints,
                "inexact_inputs": len(observed_examples),
                "zeroed_inputs": len(observed_examples),
                "examples": observed_examples,
            }
        ],
        "weight_approximations": [],
    }
    exact(project(analysis)["units_report"], expected)


def opaque_oracle():
    network = Network(nodes={name: Node(name) for name in ("s", "t")})
    network.add_link(Link("s", "t", 4, 3))
    context = prepare(Scenario(network, units=UnitsSettings(1, 0.125)))
    graph = context.topology.graph
    dag = ngc.spf(graph, [0], ngc.SpfOptions(ngc.Direction.FORWARD)).dag
    program = ngc.ForwardingProgram.from_dag(graph, [0], [1], dag)
    result = capacity(
        context,
        CapacityQuery(
            Selector("^s$"),
            Selector("^t$"),
            ngc.FlowPolicyConfig(routing=ngc.Pinned(program)),
            offer=2,
            workers=1,
        ),
    )
    expected = {
        "q": 1.0,
        "exponent": 0,
        "mode": "manual",
        "precision": 0.125,
        "target_met": False,
        "input_convention": "promoted_binary64_half_up",
        "display_convention": "units_authoritative_binary64_display",
        "scope": {
            "workflow_steps": [],
            "workflow_demand_sets": [],
            "library_demand_sets": [],
        },
        "binding_constraints": [input_bound("link.s|t|0.capacity", 4, 0.125)],
        "input_count": 1,
        "inexact_inputs": 0,
        "zeroed_inputs": 0,
        "inexact_examples": [],
        "zeroed_examples": [],
        "max_absolute_input_error": fraction(0),
        "max_relative_input_error": fraction(0),
        "augmented_capacity_sum_units": 8,
        "augmented_cost_sum": 6,
        "nominal_split_count": 0,
        "nominal_splits": [],
        "misses": [
            {
                "location": {"step": None, "case_id": "baseline", "probe_index": None},
                "constraints": [
                    input_bound("capacity.offer", 2, 0.125),
                    {
                        "kind": "unverified",
                        "label": "capacity.pair[0]",
                        "reason": "opaque_program",
                    },
                ],
                "inexact_inputs": 0,
                "zeroed_inputs": 0,
                "examples": [],
            }
        ],
        "weight_approximations": [],
    }
    exact(project(result)["units_report"], expected)


@pytest.mark.parametrize("variant", ["rounding", "split", "range", "opaque"])
def test_nonempty_units_report_is_exact(variant):
    oracle(variant)


@pytest.mark.parametrize("variant", ["rounding", "split", "range", "opaque"])
def test_units_miss_helper_field_plants_are_caught(monkeypatch, variant):
    original = exporting.project
    observed = []

    def capture(value):
        projected = original(value)
        if type(value) is UnitsReport:
            observed.append(deepcopy(projected))
        return projected

    with monkeypatch.context() as patch:
        patch.setattr(exporting, "project", capture)
        oracle(variant)
    (baseline,) = observed
    caught = equivalent = 0
    paths = tuple(field_paths(baseline))
    for path in paths:
        for mode in ("missing", "null", "wrong"):
            if mode == "null" and at(baseline, path) is None:
                equivalent += 1
                continue

            def planted(value, path=path, mode=mode):
                projected = original(value)
                if type(value) is UnitsReport:
                    change(projected, path, mode)
                return projected

            with monkeypatch.context() as patch:
                patch.setattr(exporting, "project", planted)
                with pytest.raises((AssertionError, jsonschema.ValidationError)):
                    oracle(variant)
            caught += 1
    oracle(variant)
    assert caught + equivalent == len(paths) * 3
    print(
        f"UNITS MISS FIELD PLANTS: {variant}; {len(paths)} paths; {caught} caught; {equivalent} equivalent null->null"
    )
