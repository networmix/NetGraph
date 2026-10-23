"""A narrow feasible window must be tested at its first resolvable multiplier."""

import math
from fractions import Fraction

import pytest

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


def prepared(small=100, capacity=7, q=1):
    n = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    n.add_link(Link("A", "B", capacity))
    n.add_link(Link("A", "C", 1000))
    d = DemandSet(
        "d",
        tuple(
            DemandSpec(Selector("^A$"), Selector(f"^{target}$"), volume)
            for target, volume in (("B", 1000), ("C", small))
        ),
    )
    return prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(q)), demand_sets=("d",)
    )


def units(volume, alpha, q):
    # Independent half-up oracle on the one physical binary64 multiplication.
    ratio = Fraction(float(volume * alpha)) / Fraction(q)
    return (2 * ratio.numerator + ratio.denominator) // (2 * ratio.denominator)


@pytest.mark.parametrize(
    "small,capacity,q,control", [(100, 7, 1, 0.006), (0.99, 1.01, "auto", 0.001)]
)
def test_narrow_feasible_window_probes_the_first_resolvable_alpha(
    small, capacity, q, control, monkeypatch
):
    import ngraph.analysis.msd as msd

    p = prepared(small, capacity, q)
    assert p.topology.q == (1 if q == 1 else 2**-9)
    calls = []
    original = msd._apply_matrix

    def observed(*args):
        result = original(*args)
        calls.append(result)
        return result

    monkeypatch.setattr(msd, "_apply_matrix", observed)
    answer = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], export_probe_rows=True)
    )
    assert len(calls) == len(answer.history)
    expected = 0.5 * p.topology.q / small
    while units(small, expected, p.topology.q) == 0:
        expected = math.nextafter(expected, math.inf)
    while units(small, math.nextafter(expected, 0), p.topology.q) >= 1:
        expected = math.nextafter(expected, 0)
    assert answer.search_status == "feasible" and answer.stop_reason == "tolerance"
    assert answer.alpha_feasible is not None and answer.alpha_feasible.value == expected
    best = answer.history[answer.best_probe_index]
    assert best.outcome == "feasible" and best.alpha.value == expected
    assert all(row.reference_request_units >= 1 for row in answer.best_rows)
    assert units(small, math.nextafter(expected, 0), p.topology.q) == 0
    assert answer.upper_certificate.lower_probe_index == answer.best_probe_index
    assert (
        answer.history[answer.upper_certificate.upper_probe_index].outcome
        == "infeasible"
    )
    check = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], alpha_start=control)
    )
    assert check.history[0].outcome == "feasible"


def test_below_resolution_bisection_midpoint_moves_the_lower_end_up():
    p = prepared(71.43)
    answer = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], alpha_tolerance=1e-6, export_probe_rows=True)
    )
    assert any(
        row.alpha.value == 0.005859375 and row.outcome == "below_resolution"
        for row in answer.history
    )
    assert answer.search_status == "feasible" and answer.stop_reason == "tolerance"
    assert 0.007 <= answer.alpha_feasible.value < 0.0075
    assert all(row.reference_request_units >= 1 for row in answer.best_rows)


@pytest.mark.parametrize("phase", ["bracket", "bisect", "bisect_closure"])
def test_below_resolution_history_preserves_the_iteration_limit_reason(phase):
    if phase == "bracket":
        n = Network(nodes={"A": Node("A"), "B": Node("B")})
        n.add_link(Link("A", "B", 1000))
        ds = DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^B$"), 0.001),))
        p = prepare(
            Scenario(n, demand_sets={"d": ds}, units=UnitsSettings(1)),
            demand_sets=("d",),
        )
        options = {"max_bracket_iters": 5}
    else:
        p = prepared(71.43)
        options = {
            "max_bisect_iters": 1,
            "alpha_tolerance": 0.002 if phase == "bisect_closure" else 1e-6,
        }
    answer = maximum_supported_demand(p, MSDQuery(p.demand_sets["d"], **options))
    assert answer.search_status == "none_feasible" and answer.stop_reason == (
        "bracket_limit" if phase == "bracket" else "bisect_limit"
    )
    assert answer.alpha_feasible is None and answer.upper_certificate is None
    assert any(row.outcome == "below_resolution" for row in answer.history)
    if phase == "bisect_closure":
        assert answer.history[-1].alpha.value == 0.005859375
        assert answer.history[-1].outcome == "below_resolution"
        assert 0.0078125 - 0.005859375 <= 0.002
    check = maximum_supported_demand(p, MSDQuery(p.demand_sets["d"]))
    assert check.alpha_feasible is not None
    if phase == "bracket":
        assert 1000499.98 <= check.alpha_feasible.value < 1000500


def test_alpha_max_below_resolution_has_no_verified_point():
    n = Network(nodes={"A": Node("A"), "B": Node("B")})
    n.add_link(Link("A", "B", 1000))
    ds = DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^B$"), 0.001),))
    p = prepare(
        Scenario(n, demand_sets={"d": ds}, units=UnitsSettings(1)), demand_sets=("d",)
    )
    answer = maximum_supported_demand(p, MSDQuery(p.demand_sets["d"], alpha_max=10))
    assert (
        answer.search_status == "none_feasible"
        and answer.stop_reason == "unit_resolution"
    )
    assert answer.alpha_feasible is None
    assert answer.history[-1].alpha.value == 10
    assert all(row.outcome == "below_resolution" for row in answer.history)


def test_unit_threshold_at_infeasible_upper_reuses_the_recorded_probe(monkeypatch):
    import ngraph.analysis.msd as msd

    n = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    n.add_link(Link("A", "C", 3))
    d = DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^B$"), 4),))
    p = prepare(Scenario(n, demand_sets={"d": d}), demand_sets=("d",))
    assert p.topology.q == 2**-8
    calls = []
    original = msd._apply_matrix

    def observed(*args):
        result = original(*args)
        calls.append(result)
        return result

    monkeypatch.setattr(msd, "_apply_matrix", observed)
    result = maximum_supported_demand(p, MSDQuery(p.demand_sets["d"]))
    # half-up(4*alpha/q) first reaches1 at alpha=2^-11, already tested infeasible.
    assert (
        result.search_status == "none_feasible"
        and result.stop_reason == "unit_resolution"
    )
    assert (
        result.alpha_feasible
        is result.best_probe_index
        is result.upper_certificate
        is None
    )
    assert [row.alpha.value for row in result.history] == [2.0**-i for i in range(13)]
    assert [row.outcome for row in result.history[-2:]] == [
        "infeasible",
        "below_resolution",
    ]
    assert len(calls) == len(result.history) == 13
