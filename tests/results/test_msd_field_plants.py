"""Exact search histories/statuses and every emitted MSD helper field near miss."""

import math
from copy import deepcopy
from fractions import Fraction

import jsonschema
import pytest

import ngraph.export as exporting
from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    MSDQuery,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    maximum_supported_demand,
    prepare,
)
from ngraph.analysis import msd
from ngraph.analysis.units import UnitRangeError
from tests.analysis.test_persistent_msd import prepared
from tests.results.test_analysis_wire import project
from tests.results.test_native_field_plants import at
from tests.results.test_report_field_plants import change, exact, field_paths

# One physical link, capacity4, cost3, q1. These are requested probes from the
# declared search controls, not a recording of production output.
CASES = [
    (
        2**90,
        {"alpha_start": 1e300, "alpha_max": 1e300},
        "range",
        "offer_range",
        (1e300,),
        None,
    ),
    (
        4,
        {"alpha_tolerance": 1, "export_probe_rows": True},
        "feasible",
        "tolerance",
        (1, 2),
        0,
    ),
    (4, {"max_bracket_iters": 1}, "limit", "bracket_limit", (1,), 0),
    (
        4,
        {"alpha_start": 2, "max_bracket_iters": 1},
        "none_feasible",
        "bracket_limit",
        (2,),
        None,
    ),
    (4, {"alpha_start": 2, "alpha_min": 2}, "none_feasible", "alpha_bound", (2,), None),
    (
        4,
        {"max_bracket_iters": 2, "max_bisect_iters": 1},
        "limit",
        "bisect_limit",
        (1, 2, 1.5),
        0,
    ),
    (1, {"alpha_max": 2}, "limit", "alpha_bound", (1, 2), 1),
    (0, {"alpha_max": 4}, "trivial", "declared_zero", (4,), 0),
    (
        1,
        {
            "alpha_start": math.ulp(0.0),
            "alpha_min": math.ulp(0.0),
            "alpha_max": 2 * math.ulp(0.0),
            "growth_factor": math.nextafter(1.0, 2.0),
        },
        "stagnation",
        "representable_limit",
        (math.ulp(0.0),),
        None,
    ),
    (
        1,
        {"alpha_start": float(2**63), "alpha_max": float(2**63)},
        "range",
        "offer_range",
        (float(2**63),),
        None,
    ),
]


def alpha(value):
    numerator, denominator = float(value).as_integer_ratio()
    return {"value": float(value), "numerator": numerator, "denominator": denominator}


def request(volume, scale):
    amount = Fraction(float(volume) * float(scale))
    return (2 * amount.numerator + amount.denominator) // (2 * amount.denominator)


def native_row(units):
    delivered = min(4, units)
    return {
        "kind": "placement",
        "id": "load|0|0",
        "base_id": "load|0",
        "endpoints": {"sources": ["s"], "destinations": ["t"]},
        "pool": None,
        "reference_request_units": units,
        "reference_shortfall_units": units - delivered,
        "result": {
            "request_kind": "finite",
            "requested_units": units,
            "call_delivered_units": delivered,
            "call_undelivered_units": units - delivered,
            "delivery_delta_units": delivered,
            "call_edge_drops": [],
            "call_source_drop_units": 0,
            "termination": "complete" if units <= 4 else "exhausted",
            "offered_units": None,
            "admitted_units": delivered,
            "delivered_units": delivered,
            "unadmitted_units": units - delivered,
            "source_drop_units": 0,
            "edge_drops": [],
            "edge_drop_units": 0,
            "by_source": [
                {
                    "source": "s",
                    "offered_units": None,
                    "admitted_units": delivered,
                    "delivered_units": delivered,
                    "source_drop_units": 0,
                    "total_edge_drop_units": 0,
                }
            ],
            "by_tunnel": [],
            "plan": None,
            "total_cost": None,
        },
    }


def oracle(case, monkeypatch):
    volume, controls, status, reason, alphas, best = case
    nonfinite = volume == 2**90
    if nonfinite:
        # q2^32 represents each2^90 input by2^58 units; directed sum2^59
        # is legal. Only multiplication by the finite requested alpha overflows.
        network = Network(nodes={name: Node(name) for name in ("s", "t")})
        network.add_link(Link("s", "t", 2**90, 3))
        demand_set = DemandSet(
            "load", (DemandSpec(Selector("^s$"), Selector("^t$"), volume),)
        )
        context = prepare(
            Scenario(
                network, demand_sets={"load": demand_set}, units=UnitsSettings(2**32)
            ),
            demand_sets=("load",),
        )
        demands = context.demand_sets["load"]
    else:
        context, demands = prepared(volume)
    label = "demand.load|0.volume"
    # Exercise the exception's declared diagnostic copy with known bytes; the
    # real native-units refusal is separately tested in test_persistent_msd.
    original = msd.scaled_expansion

    def scaling(demands, scale, q):
        if not nonfinite and scale >= 2**63:
            raise UnitRangeError(
                label,
                "native_units_range",
                "finite native boundary",
                float(scale).hex(),
            )
        return original(demands, scale, q)

    with monkeypatch.context() as patch:
        patch.setattr(msd, "scaled_expansion", scaling)
        value = maximum_supported_demand(
            context, MSDQuery(demands, **controls, export_details=True)
        )
    history, counts = [], []
    for index, scale in enumerate(alphas):
        if scale >= 2**63:
            counts.append(None)
            history.append(
                {
                    "index": index,
                    "alpha": alpha(scale),
                    "outcome": "range",
                    "totals": None,
                    "range_refusal": {
                        "label": label,
                        "reason": "scaled_nonfinite"
                        if nonfinite
                        else "native_units_range",
                        "message": label
                        + (
                            ": scaled_nonfinite"
                            if nonfinite
                            else ": finite native boundary"
                        ),
                        "binary64_hex": "inf" if nonfinite else float(scale).hex(),
                    },
                }
            )
            continue
        units = request(volume, scale)
        counts.append(units)
        delivered = min(units, 4)
        ratio = Fraction(delivered, units) if units else Fraction(1)
        history.append(
            {
                "index": index,
                "alpha": alpha(scale),
                "outcome": "below_resolution"
                if volume > 0 and units == 0
                else ("feasible" if units <= 4 else "infeasible"),
                "totals": {
                    "reference_request_units": units,
                    "delivered_units": delivered,
                    "unadmitted_units": units - delivered,
                    "source_drop_units": 0,
                    "edge_drop_units": 0,
                    "reference_shortfall_units": units - delivered,
                    "delivery_ratio": {
                        "numerator": ratio.numerator,
                        "denominator": ratio.denominator,
                    },
                    "feasible": units <= 4,
                },
                "range_refusal": None,
            }
        )
    certificate = None
    if best is not None:
        upper = min(
            (
                i
                for i, row in enumerate(history)
                if row["outcome"] == "infeasible" and alphas[i] > alphas[best]
            ),
            key=lambda i: (alphas[i], i),
            default=None,
        )
        if upper is not None:
            certificate = {
                "proof": "fixed_program",
                "lower": alpha(alphas[best]),
                "upper": alpha(alphas[upper]),
                "lower_probe_index": best,
                "upper_probe_index": upper,
            }
    expected = {
        "kind": "msd",
        "metadata": {"workers": 1, "sampling": None},
        "outputs": {
            "native": {
                key: False
                for key in (
                    "edge_flows",
                    "residual",
                    "edge_reservations",
                    "saturated_boundary_edges",
                    "min_cut",
                )
            },
            "cost_distribution": False,
            "details": True,
        },
        "alpha_feasible": None if best is None else alpha(alphas[best]),
        "best_probe_index": best,
        "monotone_proven": True,
        "proof": "declared_zero" if volume == 0 else "fixed_program",
        "upper_certificate": certificate,
        "search_status": status,
        "stop_reason": reason,
        "history": history,
        "best_rows": None if best is None else [native_row(counts[best])],
        "best_accounting": None
        if best is None
        else [
            {
                "base_id": "load|0",
                "declared_units": counts[best],
                "resolved_units": counts[best],
                "discarded_units": 0,
                "discards": [],
            }
        ],
    }
    if controls.get("export_probe_rows"):
        expected["probe_rows"] = [
            {"index": index, "rows": [native_row(units)]}
            for index, units in enumerate(counts)
        ]
    wire = project(value)["analysis"]
    del wire["query"]  # Normalized questions have their own complete hand oracle.
    exact(wire, expected)


@pytest.mark.parametrize("case", CASES)
def test_msd_full_fields_follow_declared_search(case, monkeypatch):
    oracle(case, monkeypatch)


@pytest.mark.parametrize("case", CASES)
def test_msd_projection_field_plants_are_caught(case, monkeypatch):
    original = exporting._msd
    observed = []

    def capture(*args, **kwargs):
        value = original(*args, **kwargs)
        observed.append(deepcopy(value))
        return value

    # Registered built-ins keep their explicit function, so patch the registry
    # entry as well as testing the helper itself.
    result_type = next(
        cls for cls, encoder in exporting._EXPORTERS.items() if encoder is original
    )
    with monkeypatch.context() as patch:
        patch.setitem(exporting._EXPORTERS, result_type, capture)
        oracle(case, monkeypatch)
    (baseline,) = observed
    paths = tuple(field_paths(baseline))
    caught = equivalent = 0
    for path in paths:
        for mode in ("missing", "null", "wrong"):
            if mode == "null" and at(baseline, path) is None:
                equivalent += 1
                continue

            def planted(*args, path=path, mode=mode, **kwargs):
                value = original(*args, **kwargs)
                change(value, path, mode)
                return value

            with monkeypatch.context() as patch:
                patch.setitem(exporting._EXPORTERS, result_type, planted)
                with pytest.raises((AssertionError, jsonschema.ValidationError)):
                    oracle(case, monkeypatch)
            caught += 1
    oracle(case, monkeypatch)
    assert caught + equivalent == 3 * len(paths)
    print(
        f"MSD FIELD PLANTS: {case[2]}/{case[3]}; {len(paths)} paths; {caught} caught; {equivalent} equivalent null->null"
    )
