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
    env = CapacityEnvelope.from_values("A", "B", "combine", [1, 2, 5])
    assert env.min_capacity == 1
    assert env.max_capacity == 5
    assert env.mean_capacity == 8 / 3
    # stdev ≈ 2.081…, just check >0:
    assert env.stdev_capacity > 0

    # Test serialization
    as_dict = env.to_dict()
    assert "source" in as_dict
    assert "frequencies" in as_dict
    json.dumps(as_dict)  # Must be JSON-serializable


def test_capacity_envelope_edge_cases():
    """Test CapacityEnvelope edge cases."""
    # Note: CapacityEnvelope.from_values() doesn't accept empty lists
    # Test with minimal single value instead
    env_minimal = CapacityEnvelope.from_values("A", "B", "combine", [0.0])
    assert env_minimal.min_capacity == 0.0
    assert env_minimal.max_capacity == 0.0
    assert env_minimal.mean_capacity == 0.0
    assert env_minimal.stdev_capacity == 0.0

    # Single value should have zero stdev
    env_single = CapacityEnvelope.from_values("A", "B", "combine", [5.0])
    assert env_single.min_capacity == 5.0
    assert env_single.max_capacity == 5.0
    assert env_single.mean_capacity == 5.0
    assert env_single.stdev_capacity == 0.0

    # Two identical values should have zero stdev
    env_identical = CapacityEnvelope.from_values("C", "D", "combine", [10.0, 10.0])
    assert env_identical.min_capacity == 10.0
    assert env_identical.max_capacity == 10.0
    assert env_identical.mean_capacity == 10.0
    assert env_identical.stdev_capacity == 0.0


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


def test_traffic_matrix_set_comprehensive():
    """Test TrafficMatrixSet with multiple complex scenarios."""
    from ngraph.traffic_demand import TrafficDemand

    tms = TrafficMatrixSet()

    # Peak hour scenario with multiple demands
    peak_demands = [
        TrafficDemand(
            source_path="servers.*", sink_path="storage.*", demand=200.0, priority=1
        ),
        TrafficDemand(source_path="web.*", sink_path="db.*", demand=50.0, priority=0),
        TrafficDemand(
            source_path="cache.*", sink_path="origin.*", demand=75.0, priority=2
        ),
    ]
    tms.add("peak_hour", peak_demands)

    # Off-peak scenario
    off_peak_demands = [
        TrafficDemand(
            source_path="backup.*", sink_path="archive.*", demand=25.0, priority=3
        ),
        TrafficDemand(
            source_path="sync.*", sink_path="replica.*", demand=10.0, priority=2
        ),
    ]
    tms.add("off_peak", off_peak_demands)

    # Emergency scenario
    emergency_demands = [
        TrafficDemand(
            source_path="critical.*",
            sink_path="backup.*",
            demand=500.0,
            priority=0,
            mode="full_mesh",
        )
    ]
    tms.add("emergency", emergency_demands)

    # Test serialization
    d = tms.to_dict()
    json.dumps(d)  # Must be JSON-serializable

    # Verify structure
    assert len(d) == 3
    assert "peak_hour" in d
    assert "off_peak" in d
    assert "emergency" in d

    # Verify content
    assert len(d["peak_hour"]) == 3
    assert len(d["off_peak"]) == 2
    assert len(d["emergency"]) == 1

    # Verify demand details
    assert d["peak_hour"][0]["demand"] == 200.0
    assert d["peak_hour"][0]["priority"] == 1
    assert d["emergency"][0]["mode"] == "full_mesh"
    assert d["off_peak"][1]["source_path"] == "sync.*"


def test_capacity_envelope_comprehensive_stats():
    """Test CapacityEnvelope with various statistical scenarios."""
    # Test with normal distribution-like values
    env1 = CapacityEnvelope.from_values(
        "A", "B", "combine", [10, 12, 15, 18, 20, 22, 25]
    )
    assert env1.min_capacity == 10
    assert env1.max_capacity == 25
    assert abs(env1.mean_capacity - 17.428571428571427) < 0.001
    assert env1.stdev_capacity > 0

    # Test with identical values
    env2 = CapacityEnvelope.from_values("C", "D", "combine", [100, 100, 100, 100])
    assert env2.min_capacity == 100
    assert env2.max_capacity == 100
    assert env2.mean_capacity == 100
    assert env2.stdev_capacity == 0.0

    # Test with extreme outliers
    env3 = CapacityEnvelope.from_values("E", "F", "combine", [1, 1000])
    assert env3.min_capacity == 1
    assert env3.max_capacity == 1000
    assert env3.mean_capacity == 500.5

    # Test serialization of all variants
    for env in [env1, env2, env3]:
        d = env.to_dict()
        json.dumps(d)
        assert "source" in d
        assert "sink" in d
        assert "frequencies" in d
        assert "min" in d
        assert "max" in d
        assert "mean" in d
        assert "stdev" in d


def test_placement_result_set_complex_scenarios():
    """Test PlacementResultSet with complex multi-case scenarios."""
    from collections import namedtuple

    FakeResult = namedtuple(
        "TrafficResult", "priority src dst total_volume placed_volume unplaced_volume"
    )

    # Multiple test cases with different results
    results_by_case = {
        "baseline": [
            FakeResult(0, "A", "B", 100, 95, 5),
            FakeResult(1, "C", "D", 50, 45, 5),
            FakeResult(0, "E", "F", 200, 180, 20),
        ],
        "optimized": [
            FakeResult(0, "A", "B", 100, 100, 0),
            FakeResult(1, "C", "D", 50, 50, 0),
            FakeResult(0, "E", "F", 200, 200, 0),
        ],
        "degraded": [
            FakeResult(0, "A", "B", 100, 80, 20),
            FakeResult(1, "C", "D", 50, 30, 20),
            FakeResult(0, "E", "F", 200, 150, 50),
        ],
    }

    # Complex statistics
    overall_stats = {
        "total_improvement": 15.0,
        "avg_utilization": 0.92,
        "worst_case_loss": 0.25,
    }

    # Per-demand statistics
    demand_stats = {
        ("A", "B", 0): {"success_rate": 0.95, "avg_latency": 1.2},
        ("C", "D", 1): {"success_rate": 0.90, "avg_latency": 2.1},
        ("E", "F", 0): {"success_rate": 0.88, "avg_latency": 1.8},
    }

    prs = PlacementResultSet(
        results_by_case=results_by_case,
        overall_stats=overall_stats,
        demand_stats=demand_stats,
    )

    # Test serialization
    d = prs.to_dict()
    json.dumps(d)  # Must be JSON-serializable

    # Verify structure
    assert len(d["cases"]) == 3
    assert "baseline" in d["cases"]
    assert "optimized" in d["cases"]
    assert "degraded" in d["cases"]

    # Verify case data
    assert len(d["cases"]["baseline"]) == 3
    assert d["cases"]["optimized"][0]["unplaced_volume"] == 0
    assert d["cases"]["degraded"][2]["placed_volume"] == 150

    # Verify statistics
    assert d["overall_stats"]["total_improvement"] == 15.0
    assert len(d["demand_stats"]) == 3
    assert "A->B|prio=0" in d["demand_stats"]
    assert d["demand_stats"]["A->B|prio=0"]["success_rate"] == 0.95


def test_all_artifacts_json_roundtrip():
    """Test that all result artifacts can roundtrip through JSON."""
    from collections import namedtuple

    from ngraph.results_artifacts import PlacementResultSet, TrafficMatrixSet
    from ngraph.traffic_demand import TrafficDemand

    # Create instances of all artifact types
    env = CapacityEnvelope.from_values("src", "dst", "combine", [100, 150, 200])

    tms = TrafficMatrixSet()
    td = TrafficDemand(source_path="^test.*", sink_path="^dest.*", demand=42.0)
    tms.add("test_matrix", [td])

    FakeResult = namedtuple(
        "TrafficResult", "priority src dst total_volume placed_volume unplaced_volume"
    )
    prs = PlacementResultSet(
        results_by_case={"test": [FakeResult(0, "A", "B", 10, 8, 2)]},
        overall_stats={"efficiency": 0.8},
        demand_stats={("A", "B", 0): {"rate": 0.8}},
    )

    # Test individual serialization and JSON roundtrip
    artifacts = [env, tms, prs]
    for artifact in artifacts:
        # Serialize to dict
        d = artifact.to_dict()

        # Convert to JSON and back
        json_str = json.dumps(d)
        parsed = json.loads(json_str)

        # Verify structure is preserved
        assert isinstance(parsed, dict)
        assert len(parsed) > 0

        # Verify no objects remain (all primitives)
        def check_primitives(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    check_primitives(v)
            elif isinstance(obj, list):
                for item in obj:
                    check_primitives(item)
            else:
                # Should be a primitive type
                assert obj is None or isinstance(obj, (str, int, float, bool))

        check_primitives(parsed)
