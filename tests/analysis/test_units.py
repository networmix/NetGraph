"""Independent binary64 and declared-total arithmetic checks."""

from dataclasses import FrozenInstanceError
from fractions import Fraction

import numpy as np
import pytest

from ngraph.analysis.units import (
    RESOLUTIONS,
    UnitsSettings,
    input_constraint,
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


def test_positive_rounded_zero_still_has_its_exact_input_bound():
    c = input_constraint("tiny", 0.25, 1, 0.125)
    assert c is not None and c.q_upper_bound == Fraction(1, 16) and not c.met
    assert input_constraint("zero", 0, 1, 0.125) is None
    assert input_constraint("tiny", 0.25, 2**-4, 0.125).met


def test_scaled_nonfinite_and_native_range_have_controls():
    with pytest.raises(ValueError, match="scaled_nonfinite"):
        scaled_units(1e308, 2, 1, "overflow")
    assert scaled_units(1, 2, 1, "overflow") == 2
    with pytest.raises(ValueError, match="range-case"):
        quantize(float(2**62), 1, "range-case")
    assert quantize(float(2**61), 1, "range-case") == 2**61
