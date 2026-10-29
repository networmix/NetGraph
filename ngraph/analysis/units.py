"""Exact physical conversion, unit reports and the choice of one resolution."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, TypeAlias

import netgraph_core as ngc

from ngraph.model.demand import _DistributedTEInput, _ParsedModel
from ngraph.results import (
    InputConstraint,
    RangeConstraint,
    SplitCountConstraint,
    UnitsReport,
)
from ngraph.utils.values import _located_error, _shown, integer, physical

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
    """The bandwidth unit ``q`` (``resolution``: "auto" or a power of two) and the
    relative precision target."""

    resolution: float | Literal["auto"] = "auto"
    precision: float = 0.001

    def __post_init__(self) -> None:
        try:
            precision = physical(self.precision, "units.precision", positive=True)
            if precision > 0.5:
                raise ValueError
        except ValueError:
            raise ValueError(
                "units.precision: expected a number greater than 0 and at most 0.5, "
                f"got {_shown(self.precision)}"
            ) from None
        object.__setattr__(self, "precision", precision)
        if isinstance(self.resolution, str) and self.resolution == "auto":
            object.__setattr__(self, "resolution", "auto")
        else:
            object.__setattr__(self, "resolution", validate_resolution(self.resolution))


def validate_resolution(q: float) -> float:
    value = physical(q, "units.resolution", positive=True)
    if value not in RESOLUTIONS:
        raise ValueError(
            f"units.resolution: expected a power of two from 2^-32 through 2^32, got {q!r}"
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


def question_inputs(offer, design_demand, declaration):
    """A capacity question's physical atoms, by field, known before evaluation."""
    values = {}
    if offer is not None:
        values["offer"] = ("offer", offer)
    if design_demand is not None:
        values["design_demand"] = ("design", design_demand)
    if isinstance(declaration, _ParsedModel) and isinstance(
        declaration.routing, _DistributedTEInput
    ):
        values["min_unreserved"] = (
            "min_unreserved",
            declaration.routing.min_unreserved_bandwidth,
        )
    return values


def input_constraint(label, value, q, precision) -> InputConstraint | None:
    """The input bound of one positive binary64 amount, even if rounded to zero."""
    amount = physical(value, label)
    if not amount:
        return None
    bound = 2 * Fraction(precision) * Fraction(amount)
    return InputConstraint(label, bound, Fraction(q) <= bound)


def split_count(
    nodes: int, directed_links: int, groups: Iterable[tuple[str, int, int]]
):
    """Choose the largest static group count; the floor and then first group win ties."""
    floor = Fraction(nodes + directed_links, 4) + 2
    chosen = (None, 0, 0, floor)
    for name, demands, tunnels in groups:
        count = max(demands, 1) * floor + tunnels
        if count > chosen[3]:
            chosen = (name, demands, tunnels, count)
    return chosen


def _minimum(inputs, *, capacities=False):
    # min keeps the first equal value, preserving preparation's insertion order.
    return min(
        (
            (label, value)
            for label, (kind, value) in inputs.items()
            if value > 0
            and (not capacities or (kind == "capacity" and label.startswith("link.")))
        ),
        key=lambda atom: atom[1],
        default=None,
    )


def _bounds(inputs, precision, count):
    smallest = _minimum(inputs)
    capacity = _minimum(inputs, capacities=True)
    input_bound = 2 * Fraction(precision) * Fraction(smallest[1]) if smallest else None
    split_bound = (
        Fraction(precision) * Fraction(capacity[1]) / count if capacity else None
    )
    return smallest, capacity, input_bound, split_bound


def make_report(
    q,
    settings,
    scope,
    inputs,
    nodes,
    directed_links,
    group_count,
    limited_by,
    range_limit,
    capacity_sum,
    cost_sum,
):
    """Describe the selected unit's input/count budget and range; never observe traffic."""
    group, demands, tunnels, count = group_count
    smallest, capacity, _, upper = _bounds(inputs, settings.precision, count)
    split_bound = None
    if capacity is not None:
        assert upper is not None
        split_bound = SplitCountConstraint(
            capacity[0],
            capacity[1],
            nodes,
            directed_links,
            group,
            demands,
            tunnels,
            count,
            upper,
            Fraction(q) <= upper,
        )
    terms = []
    if smallest:
        terms.append(Fraction(q) / (2 * Fraction(smallest[1])))
    if capacity:
        terms.append(Fraction(q) * count / Fraction(capacity[1]))
    achieved = max(terms) if terms else None
    return UnitsReport(
        q=q,
        exponent=math.frexp(q)[1] - 1,
        mode="auto" if settings.resolution == "auto" else "manual",
        precision=settings.precision,
        target_met=achieved is None or achieved <= Fraction(settings.precision),
        scope=scope,
        limited_by=limited_by,
        achieved_precision=achieved,
        input_bound=input_constraint(*smallest, q, settings.precision)
        if smallest
        else None,
        split_bound=split_bound,
        range_limit=range_limit,
        augmented_capacity_sum_units=capacity_sum,
        augmented_cost_sum=cost_sum,
    )


def choose_resolution(
    settings: UnitsSettings,
    inputs: Mapping[str, tuple[_InputKind, float]],
    coefficients: Mapping[str, int],
    count: Fraction,
    extra: Callable[[float], int] | None = None,
):
    """Select the largest power below both static bounds, then coarsen only for range.

    ``coefficients`` counts each capacity's copies in the augmented graph;
    ``extra`` adds pool offer budgets above the sources' outgoing capacity.
    No graph or traffic candidate is constructed.
    """
    failures = {}

    def range_valid(q):
        try:
            units = {
                label: quantize(value, q, label)
                for label, (_, value) in sorted(inputs.items())
            }
            extra_units = extra(q) if extra else 0
        except UnitRangeError as exc:
            if exc.reason == "scaled_nonfinite":
                raise
            exact = Fraction(float.fromhex(exc.binary64_hex)) / Fraction(q)
            unit_estimate = (2 * exact.numerator + exact.denominator) // (
                2 * exact.denominator
            )
            failures[q] = RangeConstraint(
                "amount", exc.label, q, unit_estimate, LIMIT, False
            )
            return False
        capsum = extra_units + sum(
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

    if settings.resolution != "auto":
        q = validate_resolution(settings.resolution)
        limited_by = "declared"
    else:
        _, _, input_bound, split_bound = _bounds(inputs, settings.precision, count)
        bounds = [bound for bound in (input_bound, split_bound) if bound is not None]
        if not bounds:
            q, limited_by = RESOLUTIONS[0], "unbounded"
        else:
            bound = min(bounds)
            q = next((q for q in RESOLUTIONS if Fraction(q) <= bound), RESOLUTIONS[-1])
            if Fraction(q) > bound:
                limited_by = "resolution_floor"
            else:
                limited_by = (
                    "input"
                    if input_bound is not None and input_bound == bound
                    else "split_count"
                )
    while not range_valid(q):
        if settings.resolution != "auto" or q == RESOLUTIONS[0]:
            detail = failures[q]
            error = ValueError(
                f"{detail.label}: no legal resolution represents the complete prepared input/augmented graph"
            )
            if detail.kind == "amount":
                _located_error(error, detail.label, inputs[detail.label][1])
            raise error
        q *= 2
        limited_by = "range"
    return q, limited_by, failures.get(q / 2) if limited_by == "range" else None
