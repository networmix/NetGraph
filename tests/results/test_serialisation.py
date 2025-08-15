import json

from ngraph.results import Results
from ngraph.results.artifacts import CapacityEnvelope


def test_results_to_dict_converts_objects():
    """Test that Results.to_dict() converts objects with to_dict() method."""
    res = Results()
    res.enter_step("S")
    res.put("metadata", {})
    res.put(
        "data",
        {
            "scalar": 1.23,
            "env": CapacityEnvelope.from_values("X", "Y", "combine", [4]),
        },
    )
    res.exit_step()

    d = res.to_dict()

    # Check scalar value is preserved
    assert d["steps"]["S"]["data"]["scalar"] == 1.23

    # Check that CapacityEnvelope was converted to dict
    assert isinstance(d["steps"]["S"]["data"]["env"], dict)
    assert d["steps"]["S"]["data"]["env"]["max"] == 4
    assert d["steps"]["S"]["data"]["env"]["source"] == "X"
    assert d["steps"]["S"]["data"]["env"]["sink"] == "Y"


def test_results_to_dict_empty():
    """Test Results.to_dict() with empty results."""
    res = Results()
    d = res.to_dict()
    assert d == {"workflow": {}, "steps": {}}


def test_results_to_dict_json_serializable():
    """Test that Results.to_dict() output is JSON serializable."""
    res = Results()
    res.enter_step("Analysis")
    res.put("metadata", {"version": "1.0", "timestamp": "2025-06-13"})
    res.put(
        "data",
        {
            "baseline": 100.0,
            "envelope": CapacityEnvelope.from_values(
                "src", "dst", "combine", [1, 5, 10]
            ),
        },
    )
    res.exit_step()

    d = res.to_dict()

    # Should be JSON serializable without errors
    json_str = json.dumps(d)

    # Should be able to round-trip
    parsed = json.loads(json_str)
    assert parsed["steps"]["Analysis"]["data"]["baseline"] == 100.0
    assert parsed["steps"]["Analysis"]["data"]["envelope"]["source"] == "src"
    assert parsed["steps"]["Analysis"]["metadata"]["version"] == "1.0"

    # Construct an envelope back from dict and validate
    env2 = CapacityEnvelope.from_dict(parsed["steps"]["Analysis"]["data"]["envelope"])
    assert env2.source_pattern == "src"
    assert env2.sink_pattern == "dst"
    assert env2.mode == "combine"
    assert env2.total_samples == 3
