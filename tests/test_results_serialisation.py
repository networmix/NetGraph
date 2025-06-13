"""Tests for Results serialization functionality."""

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
