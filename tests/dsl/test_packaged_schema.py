"""The fixed schema is checked by a gate; every load still validates its input."""

import json
from importlib import resources

import jsonschema
import pytest

from ngraph.dsl.loader import load_scenario_yaml


def test_packaged_scenario_and_results_schemas_are_valid():
    for name in ("scenario.json", "results.json"):
        schema = json.loads(
            resources.files("ngraph.schemas").joinpath(name).read_text()
        )
        jsonschema.validators.validator_for(schema).check_schema(schema)


def test_loader_keeps_best_instance_error_without_rechecking_fixed_schema(monkeypatch):
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    validator = jsonschema.validators.validator_for(schema)

    def unexpected_schema_check(*args, **kwargs):
        raise AssertionError("fixed schema was checked in the instance path")

    monkeypatch.setattr(validator, "check_schema", unexpected_schema_check)
    assert load_scenario_yaml("network: {nodes: {}, links: []}") == {
        "network": {"nodes": {}, "links": []}
    }
    with pytest.raises(jsonschema.ValidationError, match="unknown_option") as error:
        load_scenario_yaml("network: {nodes: {}, links: []}\nunknown_option: true")
    assert error.value.validator == "additionalProperties"
    assert list(error.value.path) == []
    assert list(error.value.schema_path) == ["additionalProperties"]
