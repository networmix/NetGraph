"""Exact physical conversion, unit reports and the choice of one resolution."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from fractions import Fraction
from types import MappingProxyType
from typing import Literal, TypeAlias, TypeVar

import netgraph_core as ngc

from ngraph.results import (
    InputConstraint,
    InputQuantization,
    PrecisionMiss,
    RangeConstraint,
    UnitsReport,
    UnverifiedConstraint,
)
from ngraph.utils.values import integer, physical

LIMIT = 1 << 62
_InputKind: TypeAlias = Literal[
    "capacity", "demand", "offer", "design", "min_unreserved"
]
RESOLUTIONS = tuple(2.0**exponent for exponent in range(32, -33, -1))


class UnitRangeError(ValueError):
    """A validated physical amount exceeded the fixed native units domain."""

    def __init__(
        self,
        label: str,
        reason: Literal["scaled_nonfinite", "native_units_range"],
        message: str,
        binary64_hex: str,
    ):
        super().__init__(f"{label}: {message}")
        self.label = label
        self.reason: Literal["scaled_nonfinite", "native_units_range"] = reason
        self.binary64_hex = binary64_hex


@dataclass(frozen=True)
class UnitsSettings:
    """One physical unit and the local relative precision target."""

    resolution: float | Literal["auto"] = "auto"
    precision: float = 0.001

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "precision",
            physical(self.precision, "units.precision", positive=True),
        )
        if self.resolution != "auto":
            object.__setattr__(self, "resolution", validate_resolution(self.resolution))


def validate_resolution(q: float) -> float:
    value = physical(q, "units.resolution", positive=True)
    if value not in RESOLUTIONS:
        raise ValueError(
            "units.resolution: expected a power of two from 2^-32 through 2^32"
        )
    return value


def quantize(value: float, q: float, label: str) -> int:
    """Quantize the promoted binary64 amount using Core's half-up rule."""
    number = physical(value, label)
    validate_resolution(q)
    try:
        result = ngc.to_units(number, q)
    except (OverflowError, ValueError) as exc:
        raise UnitRangeError(
            label, "native_units_range", str(exc), number.hex()
        ) from exc
    return int(result)


def scaled_units(volume: float, alpha: float, q: float, label: str) -> int:
    """Scale the original physical total once, then quantize once."""
    amount = physical(volume, label)
    factor = physical(alpha, "alpha", positive=True)
    scaled = amount * factor
    if not math.isfinite(scaled):
        raise UnitRangeError(
            label, "scaled_nonfinite", "scaled_nonfinite", scaled.hex()
        )
    return quantize(scaled, q, label)


def split_units(total: int, members: int) -> tuple[int, ...]:
    """Allocate a declared total in canonical quotient/remainder order."""
    integer(total, "expansion total")
    integer(members, "expansion members", minimum=1)
    quotient, remainder = divmod(total, members)
    return tuple(quotient + (i < remainder) for i in range(members))


def input_samples(
    inputs: Mapping[str, tuple[_InputKind, float]], q: float
) -> tuple[InputQuantization, ...]:
    """Describe all input errors exactly, before truncating report examples."""
    samples = []
    for label, (kind, raw) in sorted(inputs.items()):
        value = physical(raw, label)
        units = quantize(value, q, label)
        exact = Fraction(value)
        error = units * Fraction(q) - exact
        samples.append(
            InputQuantization(
                label,
                kind,
                value,
                value.hex(),
                units,
                error,
                error / exact if exact else None,
            )
        )
    return tuple(samples)


def input_constraint(
    label: str, value: float, q: float, precision: float
) -> InputConstraint | None:
    """Positive inputs retain their precision constraint even if rounded to zero."""
    amount = physical(value, label)
    target = physical(precision, "units.precision", positive=True)
    if not amount:
        return None
    bound = 2 * Fraction(target) * Fraction(amount)
    return InputConstraint(label, bound, Fraction(q) <= bound)


def input_observations(inputs, q, precision):
    """Own one complete set of exact input samples and constraints per unit."""
    return MappingProxyType(
        {
            sample.label: (
                sample,
                input_constraint(sample.label, sample.binary64_value, q, precision),
            )
            for sample in input_samples(inputs, q)
        }
    )


def _binding(q, constraints):
    """Constraints that are unverified, missed, or would miss at twice q."""
    return tuple(
        c
        for c in constraints
        if isinstance(c, UnverifiedConstraint)
        or not c.met
        or (hasattr(c, "q_upper_bound") and Fraction(q) * 2 > c.q_upper_bound)
    )


def _met(constraints) -> bool:
    return all(not isinstance(c, UnverifiedConstraint) and c.met for c in constraints)


def with_splits(report, splits, extra):
    """Complete the existing input report without observing its inputs again."""
    constraints = (*splits, *extra)
    return replace(
        report,
        binding_constraints=(
            *report.binding_constraints,
            *_binding(report.q, constraints),
        ),
        target_met=report.target_met and _met(constraints),
        nominal_split_count=len(splits),
        nominal_splits=tuple(splits),
    )


def make_report(
    q,
    settings,
    scope,
    inputs,
    capacity_sum,
    cost_sum,
    splits=(),
    extra=(),
    misses=(),
    *,
    observations=None,
):
    """Build a report from complete observations; examples are only a sample."""
    if observations is None:
        observations = input_observations(inputs, q, settings.precision)
    samples = tuple(sample for sample, _ in observations.values())
    constraints = tuple(c for _, c in observations.values() if c is not None)
    all_constraints = (*constraints, *splits, *extra)
    inexact = tuple(s for s in samples if s.error)
    zeroed = tuple(s for s in samples if s.binary64_value > 0 and s.units == 0)
    positive = tuple(s for s in samples if s.binary64_value > 0)
    return UnitsReport(
        q=q,
        exponent=math.frexp(q)[1] - 1,
        mode="auto" if settings.resolution == "auto" else "manual",
        precision=float(settings.precision),
        target_met=not misses and _met(all_constraints),
        scope=scope,
        binding_constraints=_binding(q, all_constraints),
        input_count=len(samples),
        inexact_inputs=len(inexact),
        zeroed_inputs=len(zeroed),
        inexact_examples=inexact[:16],
        zeroed_examples=zeroed[:16],
        max_absolute_input_error=max(
            (abs(s.error) for s in positive), default=Fraction(0)
        ),
        max_relative_input_error=max(
            (abs(s.relative_error) for s in positive if s.relative_error is not None),
            default=Fraction(0),
        ),
        augmented_capacity_sum_units=capacity_sum,
        augmented_cost_sum=cost_sum,
        nominal_split_count=len(splits),
        nominal_splits=tuple(splits),
        misses=tuple(misses),
    )


def precision_miss(location, samples, constraints) -> PrecisionMiss | None:
    """One observation's missed local targets, or None when all are met."""
    missed = tuple(
        c for c in constraints if isinstance(c, UnverifiedConstraint) or not c.met
    )
    if not missed:
        return None
    inexact = tuple(s for s in samples if s.error)
    zeroed = tuple(s for s in samples if s.binary64_value > 0 and s.units == 0)
    return PrecisionMiss(location, missed, len(inexact), len(zeroed), inexact[:16])


Candidate = TypeVar("Candidate")


def choose_resolution(
    settings: UnitsSettings,
    inputs: Mapping[str, tuple[_InputKind, float]],
    coefficients: Mapping[str, int],
    split_bounds: Iterable[Fraction],
    candidate: Callable[[float], tuple[Candidate, bool]],
) -> tuple[Candidate, RangeConstraint | None]:
    """Choose q by the fixed recipe and return the chosen candidate.

    ``coefficients`` counts each link capacity's directed copies in the
    augmented graph; ``split_bounds`` are the declared expansion bounds, which
    like the input bounds do not depend on q. ``candidate(q)`` prepares one
    resolution and says whether it meets the target. Automatic choice takes the
    coarsest range-valid q within the declared bounds that meets the target,
    else the finest range-valid one. The second value is the range failure of
    the next finer q, which the caller reports as binding.
    """
    failures = {}
    candidates = (
        RESOLUTIONS
        if settings.resolution == "auto"
        else (validate_resolution(settings.resolution),)
    )
    declared_limit = None
    if settings.resolution == "auto":
        input_bounds = (
            c.q_upper_bound
            for label, (_, value) in inputs.items()
            if (c := input_constraint(label, value, 1.0, settings.precision))
            is not None
        )
        declared_limit = min((*input_bounds, *split_bounds), default=None)

    def range_valid(q):
        try:
            units = {
                label: quantize(value, q, label)
                for label, (_, value) in sorted(inputs.items())
            }
        except UnitRangeError as exc:
            exact = Fraction(float(inputs[exc.label][1])) / Fraction(q)
            unit_estimate = (2 * exact.numerator + exact.denominator) // (
                2 * exact.denominator
            )
            failures[q] = RangeConstraint(
                "amount", exc.label, q, unit_estimate, LIMIT, False
            )
            return False
        capsum = sum(
            units[f"link.{link_id}.capacity"] * multiplier
            for link_id, multiplier in coefficients.items()
        )
        if capsum >= LIMIT:
            failures[q] = RangeConstraint(
                "capacity_sum",
                "topology.augmented_capacity_sum",
                q,
                capsum,
                LIMIT,
                False,
            )
            return False
        return True

    valid, skipped = [], []
    last = None
    for q in candidates:
        if declared_limit is not None and Fraction(q) > declared_limit:
            skipped.append(q)
            continue
        if not range_valid(q):
            continue
        valid.append(q)
        value, met = candidate(q)
        last = (q, value)
        if settings.resolution != "auto" or met:
            return value, None
    if not valid:
        # Precision may conflict with range. Find the finest range-valid excluded
        # candidate, without doing its input conversions on the normal path.
        for q in reversed(skipped):
            if range_valid(q):
                valid.append(q)
                break
    if not valid:
        detail = failures[max(failures)]
        raise ValueError(
            f"{detail.label}: no legal resolution represents the complete prepared input/augmented graph"
        )
    q = valid[-1]
    value = last[1] if last is not None and last[0] == q else candidate(q)[0]
    return value, failures.get(q / 2)
