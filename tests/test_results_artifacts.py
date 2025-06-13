"""Tests for results_artifacts module."""

import json
from collections import namedtuple

from ngraph.results_artifacts import (
    CapacityEnvelope,
    PlacementResultSet,
    TrafficMatrixSet,
)
from ngraph.traffic_demand import TrafficDemand


def test_capacity_envelope_stats():
    """Test CapacityEnvelope statistical computations."""
    env = CapacityEnvelope("A", "B", capacity_values=[1, 2, 5])
    assert env.min_capacity == 1
    assert env.max_capacity == 5
    assert env.mean_capacity == 8 / 3
    # stdev ≈ 2.081…, just check >0:
    assert env.stdev_capacity > 0

    # Test serialization
    as_dict = env.to_dict()
    assert "source" in as_dict
    assert "values" in as_dict
    json.dumps(as_dict)  # Must be JSON-serializable


def test_capacity_envelope_edge_cases():
    """Test CapacityEnvelope edge cases."""
    # Empty list should default to [0.0]
    env_empty = CapacityEnvelope("A", "B", capacity_values=[])
    assert env_empty.min_capacity == 0.0
    assert env_empty.max_capacity == 0.0
    assert env_empty.mean_capacity == 0.0
    assert env_empty.stdev_capacity == 0.0

    # Single value should have zero stdev
    env_single = CapacityEnvelope("A", "B", capacity_values=[5.0])
    assert env_single.min_capacity == 5.0
    assert env_single.max_capacity == 5.0
    assert env_single.mean_capacity == 5.0
    assert env_single.stdev_capacity == 0.0


def test_traffic_matrix_set_roundtrip():
    """Test TrafficMatrixSet addition and serialization."""
    td = TrafficDemand(source_path="^A$", sink_path="^B$", demand=10.0)
    tms = TrafficMatrixSet()
    tms.add("matrix1", [td])

    as_dict = tms.to_dict()
    assert "matrix1" in as_dict
    assert as_dict["matrix1"][0]["demand"] == 10.0
    json.dumps(as_dict)  # Must be JSON-serializable


def test_traffic_matrix_set_multiple_matrices():
    """Test TrafficMatrixSet with multiple matrices."""
    td1 = TrafficDemand(source_path="^A$", sink_path="^B$", demand=10.0)
    td2 = TrafficDemand(source_path="^C$", sink_path="^D$", demand=5.0)

    tms = TrafficMatrixSet()
    tms.add("matrix1", [td1])
    tms.add("matrix2", [td2])

    as_dict = tms.to_dict()
    assert len(as_dict) == 2
    assert "matrix1" in as_dict
    assert "matrix2" in as_dict
    assert as_dict["matrix1"][0]["demand"] == 10.0
    assert as_dict["matrix2"][0]["demand"] == 5.0


def test_placement_result_set_serialization():
    """Test PlacementResultSet serialization with fake TrafficResult."""
    FakeTrafficResult = namedtuple(
        "TrafficResult", "priority src dst total_volume placed_volume unplaced_volume"
    )

    fake_result = FakeTrafficResult(0, "A", "B", 1, 1, 0)
    prs = PlacementResultSet(results_by_case={"case": [fake_result]})

    js = prs.to_dict()
    json.dumps(js)  # Must be JSON-serializable
    assert js["cases"]["case"][0]["src"] == "A"


def test_placement_result_set_demand_stats():
    """Test PlacementResultSet with demand statistics."""
    FakeTrafficResult = namedtuple(
        "TrafficResult", "priority src dst total_volume placed_volume unplaced_volume"
    )

    fake_result = FakeTrafficResult(1, "A", "B", 10, 8, 2)
    demand_stats = {("A", "B", 1): {"utilization": 0.8, "success_rate": 0.8}}
    overall_stats = {"total_placed": 8.0, "total_unplaced": 2.0}

    prs = PlacementResultSet(
        results_by_case={"test_case": [fake_result]},
        overall_stats=overall_stats,
        demand_stats=demand_stats,
    )

    js = prs.to_dict()
    json.dumps(js)  # Must be JSON-serializable

    # Check structure
    assert "overall_stats" in js
    assert "cases" in js
    assert "demand_stats" in js

    # Check demand stats formatting
    assert "A->B|prio=1" in js["demand_stats"]
    assert js["demand_stats"]["A->B|prio=1"]["utilization"] == 0.8
