from __future__ import annotations

import math

import pytest

from ngraph.results.flow import (
    FlowEntry,
    FlowIterationResult,
    FlowSummary,
    _ensure_json_safe,
)


def test_flowentry_valid_and_to_dict_normalizes_cost_keys() -> None:
    e = FlowEntry(
        source="A",
        destination="B",
        priority=0,
        demand=10.0,
        placed=7.5,
        dropped=2.5,
        cost_distribution={1: 5.0, 2.0000000001: 2.5},
        data={"x": [1, 2, 3]},
    )
    d = e.to_dict()
    assert d["source"] == "A"
    # Keys must be strings
    assert set(d["cost_distribution"].keys()) == {"1", "2"}
    assert d["data"] == {"x": [1, 2, 3]}


@pytest.mark.parametrize(
    "field,value,exc",
    [
        ("source", "", TypeError),
        ("destination", "", TypeError),
        ("priority", -1, TypeError),
        ("demand", float("nan"), ValueError),
        ("placed", float("inf"), ValueError),
        ("dropped", -0.1, ValueError),
    ],
)
def test_flowentry_invalid_fields_raise(
    field: str, value: object, exc: type[Exception]
) -> None:
    kwargs = dict(
        source="A",
        destination="B",
        priority=0,
        demand=1.0,
        placed=1.0,
        dropped=0.0,
        cost_distribution={},
        data={},
    )
    kwargs[field] = value  # type: ignore[index]
    with pytest.raises(exc):
        FlowEntry(**kwargs)  # type: ignore[arg-type]


def test_flowentry_inconsistent_drop_raises() -> None:
    with pytest.raises(ValueError):
        FlowEntry(
            source="A",
            destination="B",
            priority=0,
            demand=5.0,
            placed=3.0,
            dropped=1.0,  # should be 2.0
        )


def test_flowentry_cost_distribution_validation() -> None:
    with pytest.raises(TypeError):
        FlowEntry(
            source="A",
            destination="B",
            priority=0,
            demand=1.0,
            placed=1.0,
            dropped=0.0,
            cost_distribution=[],  # type: ignore[arg-type]
        )
    # Non-finite value
    with pytest.raises(ValueError):
        FlowEntry(
            source="A",
            destination="B",
            priority=0,
            demand=1.0,
            placed=1.0,
            dropped=0.0,
            cost_distribution={1.0: float("inf")},
        )


def test_flowsummary_validation_and_ratio() -> None:
    s = FlowSummary(
        total_demand=10.0,
        total_placed=7.5,
        overall_ratio=0.75,
        dropped_flows=1,
        num_flows=3,
    )
    assert math.isclose(s.overall_ratio, 0.75)
    with pytest.raises(ValueError):
        FlowSummary(
            total_demand=10.0,
            total_placed=5.0,
            overall_ratio=0.6,  # inconsistent
            dropped_flows=0,
            num_flows=0,
        )


def test_flow_iteration_result_validation_and_to_dict() -> None:
    e1 = FlowEntry(
        source="A",
        destination="B",
        priority=0,
        demand=1.0,
        placed=0.5,
        dropped=0.5,
    )
    s = FlowSummary(
        total_demand=1.0,
        total_placed=0.5,
        overall_ratio=0.5,
        dropped_flows=1,
        num_flows=1,
    )
    it = FlowIterationResult(failure_id="baseline", flows=[e1], summary=s)
    d = it.to_dict()
    assert d["failure_id"] == "baseline"
    assert d["summary"]["total_placed"] == 0.5

    # failure_state structure validation
    with pytest.raises(ValueError):
        FlowIterationResult(
            flows=[e1],
            summary=s,
            failure_state={"excluded_nodes": [1]},  # type: ignore[list-item]
        )

    # Non-FlowEntry in flows
    with pytest.raises(TypeError):
        FlowIterationResult(flows=["bad"], summary=s)  # type: ignore[list-item]

    # Summary mismatch
    with pytest.raises(ValueError):
        FlowIterationResult(flows=[e1, e1], summary=s)


def test_flowentry_negative_dropped_due_to_rounding_is_clamped() -> None:
    # Introduce a tiny negative dropped within tolerance due to rounding
    e = FlowEntry(
        source="S",
        destination="D",
        priority=0,
        demand=100.0,
        placed=100.0 + 5e-12,  # implies dropped ~ -5e-12
        dropped=-5e-12,
    )
    assert e.dropped == 0.0


def test_ensure_json_safe_errors() -> None:
    with pytest.raises(TypeError):
        _ensure_json_safe({"k": {1, 2, 3}})
    with pytest.raises(ValueError):
        _ensure_json_safe({"k": float("inf")})
