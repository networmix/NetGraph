import json

from ngraph.results import Results
from ngraph.results.artifacts import CapacityEnvelope


def test_results_to_dict_converts_objects():
    """Test that Results.to_dict() converts objects with to_dict() method."""
    res = Results()
    res.put("S", "scalar", 1.23)
    res.put("S", "env", CapacityEnvelope.from_values("X", "Y", "combine", [4]))

    d = res.to_dict()

    # Check scalar value is preserved
    assert d["S"]["scalar"] == 1.23

    # Check that CapacityEnvelope was converted to dict
    assert isinstance(d["S"]["env"], dict)
    assert d["S"]["env"]["max"] == 4
    assert d["S"]["env"]["source"] == "X"
    assert d["S"]["env"]["sink"] == "Y"


def test_results_to_dict_empty():
    """Test Results.to_dict() with empty results."""
    res = Results()
    d = res.to_dict()
    assert d == {"workflow": {}}


def test_results_to_dict_json_serializable():
    """Test that Results.to_dict() output is JSON serializable."""
    res = Results()
    res.put("Analysis", "baseline", 100.0)
    res.put(
        "Analysis",
        "envelope",
        CapacityEnvelope.from_values("src", "dst", "combine", [1, 5, 10]),
    )
    res.put("Analysis", "metadata", {"version": "1.0", "timestamp": "2025-06-13"})

    d = res.to_dict()

    # Should be JSON serializable without errors
    json_str = json.dumps(d)

    # Should be able to round-trip
    parsed = json.loads(json_str)
    assert parsed["Analysis"]["baseline"] == 100.0
    assert parsed["Analysis"]["envelope"]["source"] == "src"
    assert parsed["Analysis"]["metadata"]["version"] == "1.0"
