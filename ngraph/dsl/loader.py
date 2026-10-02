"""YAML loader + schema validation for Scenario DSL.

`load_scenario_yaml` parses a YAML string, validates it against the packaged
JSON schema, and returns the dictionary for expansion and parsing.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict

import jsonschema
import yaml


def load_scenario_yaml(yaml_str: str) -> Dict[str, Any]:
    """Load and validate a Scenario YAML string.

    Returns the parsed dictionary with schema shape enforced. Section builders
    normalize YAML-specific quirks such as boolean-like keys.

    Raises:
        ValueError: If the top level is not a mapping, or a network, link, or
            risk group entry has the wrong shape (checked before the schema
            for clearer messages).
        jsonschema.ValidationError: If the data does not match the packaged
            schema, including unrecognized top-level keys.
    """
    data = yaml.safe_load(yaml_str)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("The provided YAML must map to a dictionary at top-level.")

    # Early shape checks give better error messages than schema validation would
    network_section = data.get("network")
    if isinstance(network_section, dict):
        if "nodes" in network_section and not isinstance(
            network_section["nodes"], dict
        ):
            raise ValueError("'nodes' must be a mapping")
        if "links" in network_section and not isinstance(
            network_section["links"], list
        ):
            raise ValueError("'links' must be a list")
        if isinstance(network_section.get("links"), list):
            for entry in network_section["links"]:
                if not isinstance(entry, dict):
                    raise ValueError(
                        "Each link definition must be a mapping with 'source' and 'target'"
                    )
                if "source" not in entry or "target" not in entry:
                    raise ValueError(
                        "Each link definition must include 'source' and 'target'"
                    )

    if isinstance(data.get("risk_groups"), list):
        for rg in data["risk_groups"]:
            # String shorthand is allowed: "GroupName" == {name: "GroupName"}
            if isinstance(rg, str):
                continue
            # Generate block is allowed: {generate: {...}}
            if isinstance(rg, dict) and "generate" in rg:
                continue
            if not isinstance(rg, dict) or "name" not in rg:
                raise ValueError(
                    "RiskGroup entry must be a string, dict with 'name' field, "
                    "or dict with 'generate' field"
                )

    # JSON Schema validation (also rejects unknown top-level keys)
    schema_text = (
        resources.files("ngraph.schemas")
        .joinpath("scenario.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.validate(data, json.loads(schema_text))

    return data
