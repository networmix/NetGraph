"""YAML loader + schema validation for Scenario DSL.

Provides a single entrypoint to parse a YAML string, normalize keys where
needed, validate against the packaged JSON schema, and return a canonical
dictionary suitable for downstream expansion/parsing.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import Any, Dict

import yaml

from ngraph.utils.yaml_utils import normalize_yaml_dict_keys


def load_scenario_yaml(yaml_str: str) -> Dict[str, Any]:
    """Load, normalize, and validate a Scenario YAML string.

    Returns a canonical dictionary representation that downstream parsers can
    consume without worrying about YAML-specific quirks (e.g., boolean-like
    keys) and with schema shape already enforced.
    """
    data = yaml.safe_load(yaml_str)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("The provided YAML must map to a dictionary at top-level.")

    # Normalize known sections that suffer from YAML key ambiguities
    if isinstance(data.get("traffic_matrix_set"), dict):
        data["traffic_matrix_set"] = normalize_yaml_dict_keys(
            data["traffic_matrix_set"]  # type: ignore[arg-type]
        )

    # Early shape checks helpful for better error messages prior to schema validation
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
        if isinstance(network_section.get("nodes"), dict):
            for _node_name, node_def in network_section["nodes"].items():
                if isinstance(node_def, dict):
                    allowed = {"attrs", "disabled", "risk_groups"}
                    for k in node_def.keys():
                        if k not in allowed:
                            raise ValueError(
                                f"Unrecognized key '{k}' in node '{_node_name}'"
                            )

    if isinstance(data.get("risk_groups"), list):
        for rg in data["risk_groups"]:
            if not isinstance(rg, dict) or "name" not in rg:
                raise ValueError("RiskGroup entry missing 'name' field")

    # JSON Schema validation
    try:
        import jsonschema  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "jsonschema is required for scenario validation. Install dev extras or add 'jsonschema' to dependencies."
        ) from exc

    try:
        with (
            resources.files("ngraph.schemas")
            .joinpath("scenario.json")
            .open("r", encoding="utf-8")
        ) as f:  # type: ignore[attr-defined]
            schema_data = json.load(f)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Failed to locate packaged NetGraph scenario schema 'ngraph/schemas/scenario.json'."
        ) from exc

    jsonschema.validate(data, schema_data)  # type: ignore[arg-type]

    # Enforce allowed top-level keys
    recognized_keys = {
        "vars",
        "blueprints",
        "network",
        "failure_policy_set",
        "traffic_matrix_set",
        "workflow",
        "components",
        "risk_groups",
        "seed",
    }
    extra = set(data.keys()) - recognized_keys
    if extra:
        raise ValueError(
            f"Unrecognized top-level key(s) in scenario: {', '.join(sorted(extra))}. "
            f"Allowed keys are {sorted(recognized_keys)}"
        )

    return data
