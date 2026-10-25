"""YAML loader + schema validation for Scenario DSL.

`load_scenario_yaml` parses a YAML string, validates it against the packaged
JSON schema, and returns the dictionary for expansion and parsing.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict

from jsonschema.exceptions import best_match
from jsonschema.validators import validator_for

from ngraph.utils.values import _diagnostic_value, _shown
from ngraph.utils.yaml_load import _load_yaml


def load_scenario_yaml(yaml_str: str) -> Dict[str, Any]:
    """Load and validate a Scenario YAML string.

    Returns the parsed dictionary with schema shape enforced. Section builders
    normalize YAML-specific quirks such as boolean-like keys.

    Raises:
        ValueError: If the top level is not a mapping, or a network, link, or
            risk group entry has the wrong shape (checked before the schema
            for clearer messages).
        ValueError: If the data does not match the packaged schema, including
            unrecognized top-level keys. The schema error is retained as the cause.
    """
    data = _load_yaml(yaml_str, "scenario")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(
            f"scenario = {_shown(data)}: The provided YAML must map to a dictionary at top-level."
        )

    # Early shape checks give better error messages than schema validation would
    network_section = data.get("network")
    if isinstance(network_section, dict):
        if "nodes" in network_section and not isinstance(
            network_section["nodes"], dict
        ):
            raise ValueError(
                f"network.nodes = {_shown(network_section['nodes'])}: 'nodes' must be a mapping"
            )
        if "links" in network_section and not isinstance(
            network_section["links"], list
        ):
            raise ValueError(
                f"network.links = {_shown(network_section['links'])}: 'links' must be a list"
            )
        if isinstance(network_section.get("links"), list):
            for index, entry in enumerate(network_section["links"]):
                if not isinstance(entry, dict):
                    raise ValueError(
                        f"network.links[{index}] = {_shown(entry)}: Each link definition must be a mapping with 'source' and 'target'"
                    )
                if "source" not in entry or "target" not in entry:
                    raise ValueError(
                        f"network.links[{index}] = {_shown(entry)}: Each link definition must include 'source' and 'target'"
                    )

    if isinstance(data.get("risk_groups"), list):
        for index, rg in enumerate(data["risk_groups"]):
            # String shorthand is allowed: "GroupName" == {name: "GroupName"}
            if isinstance(rg, str):
                continue
            # Generate block is allowed: {generate: {...}}
            if isinstance(rg, dict) and "generate" in rg:
                continue
            if not isinstance(rg, dict) or "name" not in rg:
                raise ValueError(
                    f"risk_groups[{index}] = {_shown(rg)}: RiskGroup entry must be a string, dict with 'name' field, "
                    "or dict with 'generate' field"
                )

    # JSON Schema validation (also rejects unknown top-level keys)
    schema_text = (
        resources.files("ngraph.schemas")
        .joinpath("scenario.json")
        .read_text(encoding="utf-8")
    )
    schema = json.loads(schema_text)
    # The packaged schema is checked by the schema gate. Per-load validation
    # keeps jsonschema.validate's instance-error selection without repeatedly
    # validating that fixed schema against its metaschema.
    validator = validator_for(schema)(schema)
    try:
        error = best_match(validator.iter_errors(data))
    except ValueError:
        # jsonschema formats values while creating errors; Python may refuse
        # decimal rendering of a huge integer before an error has a path.
        error = best_match(validator.iter_errors(_diagnostic_value(data)))
    if error is not None:
        # Name the field and its value, as a constructor's refusal does.
        where = _where(error.absolute_path, data)
        raise ValueError(
            f"{where} = {_shown(error.instance)}: {error.message}"
        ) from error

    return data


def _where(path, data) -> str:
    """A field path as the docs write it: network.links[0].cost.

    A link entry also shows its endpoints, as a link's own refusal does:
    network.links[0] (A->B).capacity.
    """
    text, node = "", data
    for part in path:
        text += f"[{part}]" if isinstance(part, int) else f".{part}"
        node = node[part] if isinstance(node, (dict, list)) else None
        if (
            isinstance(part, int)
            and text.endswith(f"links[{part}]")
            and isinstance(node, dict)
            and isinstance(node.get("source"), str)
            and isinstance(node.get("target"), str)
        ):
            text += f" ({node['source']}->{node['target']})"
    return text.lstrip(".") or "scenario"
