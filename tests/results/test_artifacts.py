import json

import pytest

from ngraph.demand.manager.manager import TrafficResult
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.results.artifacts import (
    CapacityEnvelope,
    PlacementEnvelope,
    PlacementResultSet,
)


def test_capacity_envelope_percentile_and_expand():
    """Validate percentile computation and frequency expansion."""
    env = CapacityEnvelope.from_values("A", "B", "combine", [1, 1, 2, 3, 5, 8])
    # expand_to_values should reconstruct the multiset
    values = sorted(env.expand_to_values())
    assert values == [1, 1, 2, 3, 5, 8]

    # Percentiles on discrete frequency distribution
    assert env.get_percentile(0) == 1
    assert env.get_percentile(50) == 2
    assert env.get_percentile(100) == 8
    with pytest.raises(ValueError):
        env.get_percentile(-1)
    with pytest.raises(ValueError):
        env.get_percentile(101)


def test_traffic_matrix_set_comprehensive():
    """Test TrafficMatrixSet with multiple complex scenarios."""
    from ngraph.demand.spec import TrafficDemand

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
            mode="pairwise",
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
    assert d["emergency"][0]["mode"] == "pairwise"
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
    # Multiple test cases with different results
    results_by_case = {
        "baseline": [
            TrafficResult(0, 100, 95, 5, "A", "B"),
            TrafficResult(1, 50, 45, 5, "C", "D"),
            TrafficResult(0, 200, 180, 20, "E", "F"),
        ],
        "optimized": [
            TrafficResult(0, 100, 100, 0, "A", "B"),
            TrafficResult(1, 50, 50, 0, "C", "D"),
            TrafficResult(0, 200, 200, 0, "E", "F"),
        ],
        "degraded": [
            TrafficResult(0, 100, 80, 20, "A", "B"),
            TrafficResult(1, 50, 30, 20, "C", "D"),
            TrafficResult(0, 200, 150, 50, "E", "F"),
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
    from ngraph.demand.spec import TrafficDemand
    from ngraph.results.artifacts import PlacementResultSet

    # Create instances of all artifact types
    env = CapacityEnvelope.from_values("src", "dst", "combine", [100, 150, 200])

    tms = TrafficMatrixSet()
    td = TrafficDemand(source_path="^test.*", sink_path="^dest.*", demand=42.0)
    tms.add("test_matrix", [td])

    prs = PlacementResultSet(
        results_by_case={"test": [TrafficResult(0, 10, 8, 2, "A", "B")]},
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


def test_placement_envelope_from_values_basic():
    env = PlacementEnvelope.from_values(
        source="A",
        sink="B",
        mode="pairwise",
        priority=1,
        ratios=[1.0, 0.8, 0.8],
    )
    assert env.source == "A"
    assert env.sink == "B"
    assert env.mode == "pairwise"
    assert env.priority == 1
    assert env.frequencies.get(1.0) == 1
    assert env.frequencies.get(0.8) == 2
    assert env.total_samples == 3
    d = env.to_dict()
    json.dumps(d)


def test_traffic_matrix_set_get_default_single_matrix():
    """Test get_default() with only one matrix."""
    matrix_set = TrafficMatrixSet()
    demand1 = TrafficDemand(source_path="A", sink_path="B", demand=100)
    matrix_set.add("single", [demand1])

    # Should return the single matrix even though it's not named 'default'
    result = matrix_set.get_default_matrix()
    assert result == [demand1]


def test_traffic_matrix_set_get_default_multiple_matrices_no_default():
    """Test get_default_matrix() with multiple matrices but no 'default' matrix."""
    matrix_set = TrafficMatrixSet()
    demand1 = TrafficDemand(source_path="A", sink_path="B", demand=100)
    demand2 = TrafficDemand(source_path="C", sink_path="D", demand=200)

    matrix_set.add("matrix1", [demand1])
    matrix_set.add("matrix2", [demand2])

    # Should raise ValueError since multiple matrices exist but no 'default'
    with pytest.raises(ValueError, match="Multiple matrices exist"):
        matrix_set.get_default_matrix()


def test_traffic_matrix_set_get_all_demands():
    """Test get_all_demands() method."""
    matrix_set = TrafficMatrixSet()
    demand1 = TrafficDemand(source_path="A", sink_path="B", demand=100)
    demand2 = TrafficDemand(source_path="C", sink_path="D", demand=200)
    demand3 = TrafficDemand(source_path="E", sink_path="F", demand=300)

    matrix_set.add("matrix1", [demand1, demand2])
    matrix_set.add("matrix2", [demand3])

    all_demands = matrix_set.get_all_demands()
    assert len(all_demands) == 3
    assert demand1 in all_demands
    assert demand2 in all_demands
    assert demand3 in all_demands


def test_capacity_envelope_from_values_empty_list():
    """Test CapacityEnvelope.from_values() with empty values list."""
    with pytest.raises(
        ValueError, match="Cannot create envelope from empty values list"
    ):
        CapacityEnvelope.from_values("A", "B", "combine", [])
