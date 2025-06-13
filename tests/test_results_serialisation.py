import json

from ngraph.results import Results
from ngraph.results_artifacts import CapacityEnvelope


def test_results_to_dict_converts_objects():
    """Test that Results.to_dict() converts objects with to_dict() method."""
    res = Results()
    res.put("S", "scalar", 1.23)
    res.put("S", "env", CapacityEnvelope("X", "Y", capacity_values=[4]))

    d = res.to_dict()

    # Check scalar value is preserved
    assert d["S"]["scalar"] == 1.23

    # Check that CapacityEnvelope was converted to dict
    assert isinstance(d["S"]["env"], dict)
    assert d["S"]["env"]["max"] == 4
    assert d["S"]["env"]["source"] == "X"
    assert d["S"]["env"]["sink"] == "Y"


def test_results_to_dict_mixed_values():
    """Test Results.to_dict() with mix of primitive and object values."""
    res = Results()

    # Add various types of values
    res.put("Step1", "number", 42)
    res.put("Step1", "string", "hello")
    res.put("Step1", "list", [1, 2, 3])
    res.put("Step1", "dict", {"key": "value"})
    res.put(
        "Step1", "capacity_env", CapacityEnvelope("A", "B", capacity_values=[10, 20])
    )

    res.put("Step2", "another_env", CapacityEnvelope("C", "D", capacity_values=[5]))
    res.put("Step2", "bool", True)

    d = res.to_dict()

    # Check primitives are preserved
    assert d["Step1"]["number"] == 42
    assert d["Step1"]["string"] == "hello"
    assert d["Step1"]["list"] == [1, 2, 3]
    assert d["Step1"]["dict"] == {"key": "value"}
    assert d["Step2"]["bool"] is True

    # Check objects were converted
    assert isinstance(d["Step1"]["capacity_env"], dict)
    assert d["Step1"]["capacity_env"]["min"] == 10
    assert d["Step1"]["capacity_env"]["max"] == 20

    assert isinstance(d["Step2"]["another_env"], dict)
    assert d["Step2"]["another_env"]["min"] == 5
    assert d["Step2"]["another_env"]["max"] == 5


def test_results_to_dict_json_serializable():
    """Test that Results.to_dict() output is JSON serializable."""
    res = Results()
    res.put("Analysis", "baseline", 100.0)
    res.put(
        "Analysis",
        "envelope",
        CapacityEnvelope("src", "dst", capacity_values=[1, 5, 10]),
    )
    res.put("Analysis", "metadata", {"version": "1.0", "timestamp": "2025-06-13"})

    d = res.to_dict()

    # Should be JSON serializable without errors
    json_str = json.dumps(d)

    # Should be able to round-trip
    parsed = json.loads(json_str)
    assert parsed["Analysis"]["baseline"] == 100.0
    assert parsed["Analysis"]["envelope"]["source"] == "src"
    assert parsed["Analysis"]["envelope"]["mean"] == 5.333333333333333
    assert parsed["Analysis"]["metadata"]["version"] == "1.0"


def test_results_to_dict_empty():
    """Test Results.to_dict() with empty results."""
    res = Results()
    d = res.to_dict()
    assert d == {}


def test_results_to_dict_no_to_dict_method():
    """Test Results.to_dict() with objects that don't have to_dict() method."""

    class SimpleObject:
        def __init__(self, value):
            self.value = value

    res = Results()
    obj = SimpleObject(42)
    res.put("Test", "object", obj)
    res.put("Test", "primitive", "text")

    d = res.to_dict()

    # Object without to_dict() should be stored as-is
    assert d["Test"]["object"] is obj
    assert d["Test"]["primitive"] == "text"


def test_results_integration_all_artifact_types():
    """Test Results integration with all result artifact types."""
    from collections import namedtuple

    from ngraph.results_artifacts import PlacementResultSet, TrafficMatrixSet
    from ngraph.traffic_demand import TrafficDemand

    res = Results()

    # Add CapacityEnvelope
    env = CapacityEnvelope(
        "data_centers", "edge_sites", capacity_values=[1000, 1200, 1500]
    )
    res.put("CapacityAnalysis", "dc_to_edge_envelope", env)
    res.put("CapacityAnalysis", "analysis_time_sec", 12.5)

    # Add TrafficMatrixSet
    tms = TrafficMatrixSet()
    td1 = TrafficDemand(source_path="servers.*", sink_path="storage.*", demand=200.0)
    td2 = TrafficDemand(source_path="web.*", sink_path="db.*", demand=50.0)
    tms.add("peak_hour", [td1, td2])
    tms.add("off_peak", [td1])
    res.put("TrafficAnalysis", "matrices", tms)

    # Add PlacementResultSet
    FakeResult = namedtuple(
        "TrafficResult", "priority src dst total_volume placed_volume unplaced_volume"
    )
    prs = PlacementResultSet(
        results_by_case={
            "baseline": [FakeResult(0, "A", "B", 100, 95, 5)],
            "optimized": [FakeResult(0, "A", "B", 100, 100, 0)],
        },
        overall_stats={"improvement": 5.0, "efficiency": 0.95},
        demand_stats={("A", "B", 0): {"success_rate": 0.95}},
    )
    res.put("PlacementAnalysis", "results", prs)

    # Add regular metadata
    res.put("Metadata", "version", "2.0")
    res.put("Metadata", "timestamp", "2025-06-13T10:00:00Z")

    # Test serialization
    d = res.to_dict()

    # Verify CapacityEnvelope serialization
    assert isinstance(d["CapacityAnalysis"]["dc_to_edge_envelope"], dict)
    assert d["CapacityAnalysis"]["dc_to_edge_envelope"]["mean"] == 1233.3333333333333
    assert d["CapacityAnalysis"]["analysis_time_sec"] == 12.5

    # Verify TrafficMatrixSet serialization
    assert isinstance(d["TrafficAnalysis"]["matrices"], dict)
    assert "peak_hour" in d["TrafficAnalysis"]["matrices"]
    assert "off_peak" in d["TrafficAnalysis"]["matrices"]
    assert len(d["TrafficAnalysis"]["matrices"]["peak_hour"]) == 2
    assert len(d["TrafficAnalysis"]["matrices"]["off_peak"]) == 1
    assert d["TrafficAnalysis"]["matrices"]["peak_hour"][0]["demand"] == 200.0

    # Verify PlacementResultSet serialization
    assert isinstance(d["PlacementAnalysis"]["results"], dict)
    assert "cases" in d["PlacementAnalysis"]["results"]
    assert "overall_stats" in d["PlacementAnalysis"]["results"]
    assert d["PlacementAnalysis"]["results"]["overall_stats"]["improvement"] == 5.0
    assert "A->B|prio=0" in d["PlacementAnalysis"]["results"]["demand_stats"]

    # Verify metadata preservation
    assert d["Metadata"]["version"] == "2.0"
    assert d["Metadata"]["timestamp"] == "2025-06-13T10:00:00Z"

    # Verify JSON serialization works
    json_str = json.dumps(d)
    parsed = json.loads(json_str)
    assert parsed["CapacityAnalysis"]["dc_to_edge_envelope"]["source"] == "data_centers"


def test_results_workflow_simulation():
    """Test realistic workflow scenario with multiple analysis steps."""
    res = Results()

    # Step 1: Basic topology analysis
    res.put("TopologyAnalysis", "node_count", 100)
    res.put("TopologyAnalysis", "link_count", 250)
    res.put("TopologyAnalysis", "avg_degree", 5.0)

    # Step 2: Capacity analysis with envelopes
    envelope1 = CapacityEnvelope("pod1", "pod2", capacity_values=[800, 900, 1000])
    envelope2 = CapacityEnvelope(
        "core", "edge", capacity_values=[1500, 1600, 1700, 1800]
    )
    res.put("CapacityAnalysis", "pod_to_pod", envelope1)
    res.put("CapacityAnalysis", "core_to_edge", envelope2)
    res.put("CapacityAnalysis", "bottleneck_links", ["link_5", "link_23"])

    # Step 3: Performance metrics
    res.put("Performance", "latency_ms", {"p50": 1.2, "p95": 3.8, "p99": 8.5})
    res.put("Performance", "throughput_gbps", [10.5, 12.3, 11.8, 13.1])

    d = res.to_dict()

    # Verify structure and data types
    assert len(d) == 3  # Three analysis steps
    assert d["TopologyAnalysis"]["node_count"] == 100
    assert isinstance(d["CapacityAnalysis"]["pod_to_pod"], dict)
    assert isinstance(d["CapacityAnalysis"]["core_to_edge"], dict)
    assert d["CapacityAnalysis"]["bottleneck_links"] == ["link_5", "link_23"]
    assert d["Performance"]["latency_ms"]["p99"] == 8.5

    # Verify capacity envelope calculations
    assert d["CapacityAnalysis"]["pod_to_pod"]["min"] == 800
    assert d["CapacityAnalysis"]["pod_to_pod"]["max"] == 1000
    assert d["CapacityAnalysis"]["core_to_edge"]["mean"] == 1650.0

    # Verify JSON serialization
    json.dumps(d)  # Should not raise an exception


def test_results_get_methods_compatibility():
    """Test that enhanced to_dict() doesn't break existing get/get_all methods."""
    res = Results()

    # Store mixed data types
    env = CapacityEnvelope("A", "B", capacity_values=[100, 200])
    res.put("Step1", "envelope", env)
    res.put("Step1", "scalar", 42.0)
    res.put("Step2", "envelope", CapacityEnvelope("C", "D", capacity_values=[50]))
    res.put("Step2", "list", [1, 2, 3])

    # Test get method returns original objects
    retrieved_env = res.get("Step1", "envelope")
    assert isinstance(retrieved_env, CapacityEnvelope)
    assert retrieved_env.source_pattern == "A"
    assert retrieved_env.max_capacity == 200

    assert res.get("Step1", "scalar") == 42.0
    assert res.get("Step2", "list") == [1, 2, 3]
    assert res.get("NonExistent", "key", "default") == "default"

    # Test get_all method
    all_envelopes = res.get_all("envelope")
    assert len(all_envelopes) == 2
    assert isinstance(all_envelopes["Step1"], CapacityEnvelope)
    assert isinstance(all_envelopes["Step2"], CapacityEnvelope)

    all_scalars = res.get_all("scalar")
    assert len(all_scalars) == 1
    assert all_scalars["Step1"] == 42.0

    # Test to_dict converts objects but get methods return originals
    d = res.to_dict()
    assert isinstance(d["Step1"]["envelope"], dict)  # Converted in to_dict()
    assert isinstance(
        res.get("Step1", "envelope"), CapacityEnvelope
    )  # Original in get()


def test_results_complex_nested_structures():
    """Test Results with complex nested data structures."""
    from ngraph.results_artifacts import TrafficMatrixSet
    from ngraph.traffic_demand import TrafficDemand

    res = Results()

    # Create nested structure with multiple traffic scenarios
    tms = TrafficMatrixSet()

    # Peak traffic scenario
    peak_demands = [
        TrafficDemand(
            source_path="dc1.*", sink_path="dc2.*", demand=1000.0, priority=1
        ),
        TrafficDemand(
            source_path="edge.*", sink_path="core.*", demand=500.0, priority=2
        ),
        TrafficDemand(source_path="web.*", sink_path="db.*", demand=200.0, priority=0),
    ]
    tms.add("peak_traffic", peak_demands)

    # Low traffic scenario
    low_demands = [
        TrafficDemand(source_path="dc1.*", sink_path="dc2.*", demand=300.0, priority=1),
        TrafficDemand(
            source_path="backup.*", sink_path="storage.*", demand=100.0, priority=3
        ),
    ]
    tms.add("low_traffic", low_demands)

    # Store complex nested data
    res.put("Scenarios", "traffic_matrices", tms)
    res.put(
        "Scenarios",
        "capacity_envelopes",
        {
            "critical_links": CapacityEnvelope(
                "dc", "edge", capacity_values=[800, 900, 1000]
            ),
            "backup_links": CapacityEnvelope(
                "backup", "main", capacity_values=[100, 150]
            ),
        },
    )
    res.put(
        "Scenarios",
        "analysis_metadata",
        {"total_scenarios": 2, "max_priority": 3, "analysis_date": "2025-06-13"},
    )

    d = res.to_dict()

    # Verify traffic matrices serialization
    traffic_data = d["Scenarios"]["traffic_matrices"]
    assert "peak_traffic" in traffic_data
    assert "low_traffic" in traffic_data
    assert len(traffic_data["peak_traffic"]) == 3
    assert len(traffic_data["low_traffic"]) == 2
    assert traffic_data["peak_traffic"][0]["demand"] == 1000.0
    assert traffic_data["low_traffic"][1]["priority"] == 3

    # Verify capacity envelopes weren't auto-converted (they're in a dict, not direct values)
    cap_envs = d["Scenarios"]["capacity_envelopes"]
    assert isinstance(cap_envs["critical_links"], CapacityEnvelope)  # Still objects
    assert isinstance(cap_envs["backup_links"], CapacityEnvelope)

    # Verify metadata preservation
    assert d["Scenarios"]["analysis_metadata"]["total_scenarios"] == 2

    # Verify JSON serialization fails gracefully due to nested objects
    try:
        json.dumps(d)
        raise AssertionError(
            "Should have failed due to nested CapacityEnvelope objects"
        )
    except TypeError:
        pass  # Expected - nested objects in dict don't get auto-converted
