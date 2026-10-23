"""The packaged results schema is generated from the record declarations."""

import json
import runpy
from importlib import resources
from pathlib import Path

import pytest

GENERATOR = Path(__file__).resolve().parents[2] / "dev/generate_results_schema.py"


def generator():
    return runpy.run_path(str(GENERATOR), run_name="generator")


def test_packaged_schema_equals_the_generated_schema():
    packaged = resources.files("ngraph.schemas").joinpath("results.json").read_text()
    assert packaged == generator()["generate"]()


def test_plain_record_definitions_follow_their_declared_fields():
    tools = generator()
    from ngraph.results import ExactAlpha, SelfPair, SplitConstraint

    alpha = tools["record"](ExactAlpha)
    assert list(alpha["properties"]) == ["value", "numerator", "denominator"]
    assert alpha["properties"]["value"] == {"type": "number", "exclusiveMinimum": 0}
    assert alpha["properties"]["denominator"] == {"type": "integer", "minimum": 1}
    assert tools["record"](SelfPair)["properties"] == {
        "kind": {"enum": ["self"]},
        "id": {"type": "string"},
        "node": {"type": "string"},
        "capacity_units": {"enum": [0]},
    }
    split = tools["record"](SplitConstraint)
    assert split["required"] == [
        "kind",
        "label",
        "incoming_physical",
        "basis",
        "members",
        "q_upper_bound",
        "met",
    ]
    assert split["additionalProperties"] is False


def test_an_undeclared_type_has_no_silent_schema():
    with pytest.raises(TypeError, match="no schema"):
        generator()["schema"](complex)
    schema = json.loads(generator()["generate"]())
    assert "SelectorJSON" in schema["$defs"] and "ModelJSON" in schema["$defs"]
