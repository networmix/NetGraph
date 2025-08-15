from __future__ import annotations

import math

import pytest

from ngraph.demand.manager.manager import TrafficResult
from ngraph.results.artifacts import (
    CapacityEnvelope,
    FailurePatternResult,
    PlacementEnvelope,
    PlacementResultSet,
)


def test_placement_result_set_to_dict_shapes() -> None:
    res = PlacementResultSet(
        results_by_case={
            "case1": [
                TrafficResult(0, 10.0, 7.0, 3.0, "A", "B"),
                TrafficResult(0, 5.0, 5.0, 0.0, "A", "C"),
            ]
        },
        overall_stats={"mean": 0.7},
        demand_stats={("A", "B", 0): {"ratio": 0.7}},
    )
    d = res.to_dict()
    assert "cases" in d and "overall_stats" in d and "demand_stats" in d
    assert d["cases"]["case1"][0]["src"] == "A"
    # demand_stats keys are stringified
    assert any(key.startswith("A->B|prio=") for key in d["demand_stats"].keys())


def test_capacity_envelope_from_values_and_percentile_roundtrip() -> None:
    values = [1.0, 1.0, 2.0, 10.0]
    env = CapacityEnvelope.from_values("A", "B", "combine", values)
    assert env.total_samples == 4
    assert env.frequencies[1.0] == 2
    assert math.isclose(env.get_percentile(50), 1.0)
    assert math.isclose(env.get_percentile(100), 10.0)
    # to_dict/from_dict
    env2 = CapacityEnvelope.from_dict(env.to_dict())
    assert env2.frequencies == env.frequencies
    assert math.isclose(env2.mean_capacity, env.mean_capacity)


def test_capacity_envelope_expand_to_values() -> None:
    env = CapacityEnvelope(
        source_pattern="A",
        sink_pattern="B",
        mode="combine",
        frequencies={1.0: 2, 2.0: 1},
        min_capacity=1.0,
        max_capacity=2.0,
        mean_capacity=1.3333333,
        stdev_capacity=0.4714,
        total_samples=3,
    )
    vals = sorted(env.expand_to_values())
    assert vals == [1.0, 1.0, 2.0]


def test_capacity_envelope_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        CapacityEnvelope.from_values("A", "B", "pairwise", [])
    with pytest.raises(ValueError):
        # percentile outside range
        env = CapacityEnvelope.from_values("A", "B", "combine", [1.0])
        env.get_percentile(-1)


def test_failure_pattern_result_key_and_dict() -> None:
    fpr = FailurePatternResult(
        excluded_nodes=["n1"],
        excluded_links=["e1"],
        capacity_matrix={"A->B": 1.0},
        count=2,
        is_baseline=False,
    )
    k1 = fpr.pattern_key
    k2 = fpr.pattern_key
    assert k1 == k2 and k1.startswith("pattern_")
    d = fpr.to_dict()
    assert d["count"] == 2 and d["capacity_matrix"]["A->B"] == 1.0
    # baseline has fixed key
    base = FailurePatternResult(["n1"], ["e1"], {}, 1, is_baseline=True)
    assert base.pattern_key == "baseline"


def test_placement_envelope_roundtrip_and_stats() -> None:
    pe = PlacementEnvelope.from_values(
        source="A",
        sink="B",
        mode="pairwise",
        priority=0,
        ratios=[0.1, 0.1, 0.2, 1.0],
        rounding_decimals=2,
    )
    assert pe.total_samples == 4
    d = pe.to_dict()
    pe2 = PlacementEnvelope.from_dict(d)
    assert pe2.frequencies == pe.frequencies
    assert pe2.priority == 0 and pe2.mode == "pairwise"
