"""Independent binary64 and declared-total arithmetic checks."""

from dataclasses import FrozenInstanceError
from fractions import Fraction

import numpy as np
import pytest

from ngraph.analysis.precision import split_constraint
from ngraph.analysis.units import (
    RESOLUTIONS,
    UnitsSettings,
    input_constraint,
    input_samples,
    quantize,
    scaled_units,
    split_units,
)


def half_up(value: float, q: float) -> int:
    exact = Fraction(float(value)) / Fraction(q)
    return (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)


@pytest.mark.parametrize(
    "value", [0, 0.25, 0.5, 0.75, 1.5, 2**53 + 1, 2**53 + 3, np.float32(0.1)]
)
@pytest.mark.parametrize("q", [1.0, 2**-12, 2**10])
def test_promoted_binary64_half_up(value, q):
    expected = half_up(value, q)
    if expected >= 2**62:
        with pytest.raises(ValueError, match="amount"):
            quantize(value, q, "amount")
        assert quantize(value, 1, "amount") == half_up(value, 1)
    else:
        assert quantize(value, q, "amount") == expected


def test_scale_physical_before_quantization():
    assert quantize(0.25, 1, "small") == quantize(0.375, 1, "other") == 0
    assert scaled_units(0.25, 4, 1, "small") == 1
    assert scaled_units(0.375, 4, 1, "other") == 2


def test_nested_total_split_and_zero_leaves():
    outer = split_units(10, 2)
    assert outer == (5, 5)
    assert split_units(outer[1], 3) == (2, 2, 1)
    assert outer[0] + sum(split_units(outer[1], 3)) == 10
    assert split_units(1, 2) == (1, 0)
    assert split_units(0, 4) == (0, 0, 0, 0)


@pytest.mark.parametrize("bad", [True, False, -1, float("nan"), float("inf"), "1"])
def test_physical_refusal_has_label_and_legal_control(bad):
    with pytest.raises(ValueError, match="labelled"):
        quantize(bad, 1, "labelled")
    assert quantize(1, 1, "labelled") == 1


@pytest.mark.parametrize("bad", [True, 0, 3, 2**-33, 2**33, float("nan")])
def test_resolution_refusal_has_legal_control(bad):
    with pytest.raises(ValueError, match="units.resolution"):
        UnitsSettings(resolution=bad)
    assert UnitsSettings(resolution=2**-32).resolution == 2**-32


def test_resolution_domain_and_settings_immutability():
    assert len(RESOLUTIONS) == 65
    assert RESOLUTIONS[0] == 2**32
    assert RESOLUTIONS[-1] == 2**-32
    settings = UnitsSettings()
    with pytest.raises(FrozenInstanceError):
        settings.precision = 0.2
    assert UnitsSettings(precision=0.2).precision == 0.2


def test_error_sign_relative_zero_and_exact_large_units():
    samples = input_samples(
        {"up": ("offer", 0.5), "down": ("demand", 0.25), "zero": ("capacity", 0)}, 1
    )
    down, up, zero = samples
    assert down.label == "down" and down.units == 0 and down.error == Fraction(-1, 4)
    assert down.relative_error == -1
    assert up.units == 1 and up.error == Fraction(1, 2) and up.relative_error == 1
    assert zero.error == 0 and zero.relative_error is None
    big = input_samples({"big": ("offer", 2**54)}, 1)[0]
    assert big.units == 2**54 and isinstance(big.units, int)
    assert big.error == 0


def test_positive_rounded_zero_still_constrains_and_split_bound_is_exact():
    c = input_constraint("tiny", 0.25, 1, 0.125)
    assert c is not None and c.q_upper_bound == Fraction(1, 16) and not c.met
    assert input_constraint("zero", 0, 1, 0.125) is None
    s = split_constraint("expansion", "three", Fraction(5), 3, 1, 0.125)
    assert s.q_upper_bound == Fraction(5, 16) and s.members == 3 and not s.met
    assert input_constraint("tiny", 0.25, 2**-4, 0.125).met


def test_scaled_nonfinite_and_native_range_have_controls():
    with pytest.raises(ValueError, match="scaled_nonfinite"):
        scaled_units(1e308, 2, 1, "overflow")
    assert scaled_units(1, 2, 1, "overflow") == 2
    with pytest.raises(ValueError, match="range-case"):
        quantize(float(2**62), 1, "range-case")
    assert quantize(float(2**61), 1, "range-case") == 2**61


def _prepared_line(volume):
    from ngraph import (
        DemandSet,
        DemandSpec,
        Link,
        Network,
        Node,
        Scenario,
        Selector,
        prepare,
    )

    model = Network()
    model.add_node(Node("a"))
    model.add_node(Node("b"))
    model.add_link(Link("a", "b", 0.25, 1))
    spec = DemandSpec(Selector("^a$"), Selector("^b$"), volume, id="d")
    scenario = Scenario(
        model,
        demand_sets={"ds": DemandSet("ds", (spec,))},
        units=UnitsSettings(1),
    )
    return model, prepare(scenario, demand_sets=("ds",))


def test_prepared_atoms_are_owned_and_scaled_atoms_recomputed(monkeypatch):
    from ngraph.analysis import precision

    model, prepared = _prepared_line(0.5)
    atoms = dict(prepared._inputs)
    assert atoms == {
        "demand.d.volume": ("demand", 0.5),
        "link.a|b|0.capacity": ("capacity", 0.25),
    }
    expected_samples = input_samples(atoms, 1)
    expected_constraints = tuple(
        c
        for label, (_, value) in sorted(atoms.items())
        if (c := input_constraint(label, value, 1, prepared.units_report.precision))
        is not None
    )
    model.replace_link("a|b|0", capacity=99)
    with pytest.raises(TypeError):
        prepared._input_observations["new"] = None
    original = precision.input_samples
    calls = []

    def observe(inputs, q):
        calls.append(dict(inputs))
        return original(inputs, q)

    monkeypatch.setattr(precision, "input_samples", observe)
    samples, constraints = precision.observed_inputs(prepared, atoms)
    assert samples == expected_samples
    assert constraints == expected_constraints
    assert calls == []
    atoms["demand.d.volume"] = ("demand", 0.25)
    samples, constraints = precision.observed_inputs(prepared, atoms)
    assert calls == [{"demand.d.volume": ("demand", 0.25)}]
    assert samples[0].units == 0 and samples[0].error == Fraction(-1, 4)
    assert (
        constraints[0].q_upper_bound
        == 2 * Fraction(prepared.units_report.precision) / 4
    )
    assert prepared._input_observations["demand.d.volume"][0].units == 1


def test_observation_reuse_preserves_zero_sign():
    from ngraph.analysis.precision import observed_inputs

    _, prepared = _prepared_line(0.0)
    samples, constraints = observed_inputs(
        prepared, {"demand.d.volume": ("demand", -0.0)}
    )
    assert samples[0].binary64_hex == "-0x0.0p+0"
    assert constraints == ()
    assert prepared._input_observations["demand.d.volume"][0].binary64_hex == (
        "0x0.0p+0"
    )


def test_fixed_alpha_inputs_are_shared_by_cases_and_refreshed_for_next_question(
    monkeypatch,
):
    from ngraph import (
        DemandSet,
        DemandSpec,
        FailureMode,
        FailurePolicy,
        FailureRequest,
        FailureRule,
        Link,
        Network,
        Node,
        PlacementQuery,
        Scenario,
        Selector,
        place,
        prepare,
    )
    from ngraph.analysis import placement

    network = Network(nodes={name: Node(name) for name in ("s", "t", "N1", "N2")})
    network.add_link(Link("s", "t", 8, 1))
    prepared = prepare(
        Scenario(
            network,
            demand_sets={
                "load": DemandSet(
                    "load", (DemandSpec(Selector("^s$"), Selector("^t$"), 1),)
                )
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )
    failures = FailureRequest(
        FailurePolicy(
            modes=[FailureMode(1, [FailureRule("node", mode="choice", path="^N")])]
        ),
        32,
        42,
    )
    original = placement.placement_inputs
    built = []

    def observe(*args):
        value = original(*args)
        built.append(value)
        return value

    monkeypatch.setattr(placement, "placement_inputs", observe)
    old = place(
        prepared,
        PlacementQuery(prepared.demand_sets["load"], 1.5, failures, workers=2),
    )
    assert len(old.cases) == 3
    assert [case.states["converged"].totals.delivered_units for case in old.cases] == [
        2
    ] * 3
    assert len(built) == 1
    new = place(
        prepared,
        PlacementQuery(prepared.demand_sets["load"], 2.5, failures, workers=2),
    )
    assert [case.states["converged"].totals.delivered_units for case in new.cases] == [
        3
    ] * 3
    assert len(built) == 2 and built[0] is not built[1]
    assert next(s for s in built[0][0] if s.kind == "demand").binary64_value == 1.5
    assert next(s for s in built[1][0] if s.kind == "demand").binary64_value == 2.5
    assert [case.states["converged"].totals.delivered_units for case in old.cases] == [
        2
    ] * 3
