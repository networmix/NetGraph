"""Builders for traffic matrices.

Construct `TrafficMatrixSet` from raw dictionaries (e.g. parsed YAML).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ngraph.model.demand.matrix import TrafficMatrixSet
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys


def build_traffic_matrix_set(raw: Dict[str, List[dict]]) -> TrafficMatrixSet:
    """Build a `TrafficMatrixSet` from a mapping of name -> list of dicts.

    Args:
        raw: Mapping where each key is a matrix name and each value is a list of
            dictionaries with `TrafficDemand` constructor fields.

    Returns:
        Initialized `TrafficMatrixSet` with constructed `TrafficDemand` objects.

    Raises:
        ValueError: If ``raw`` is not a mapping of name -> list[dict],
            or if required fields are missing.
    """
    if not isinstance(raw, dict):
        raise ValueError(
            "'traffic_matrix_set' must be a mapping of name -> list[TrafficDemand]"
        )

    normalized_raw = normalize_yaml_dict_keys(raw)
    tms = TrafficMatrixSet()
    for name, td_list in normalized_raw.items():
        if not isinstance(td_list, list):
            raise ValueError(
                f"Matrix '{name}' must map to a list of TrafficDemand dicts"
            )
        coerced: List[TrafficDemand] = []
        for d in td_list:
            if not isinstance(d, dict):
                raise ValueError(
                    f"Entries in matrix '{name}' must be dicts, got {type(d).__name__}"
                )

            # Validate required fields
            if "source" not in d or "sink" not in d:
                raise ValueError(
                    f"Each demand in matrix '{name}' requires 'source' and 'sink' fields"
                )

            # Build normalized dict for TrafficDemand constructor
            td_kwargs: Dict[str, Any] = {
                "source": d["source"],
                "sink": d["sink"],
                "demand": d.get("demand", 0.0),
                "priority": d.get("priority", 0),
                "mode": d.get("mode", "combine"),
                "group_mode": d.get("group_mode", "flatten"),
                "expand_vars": d.get("expand_vars", {}),
                "expansion_mode": d.get("expansion_mode", "cartesian"),
                "attrs": d.get("attrs", {}),
            }

            # Optional id
            if "id" in d:
                td_kwargs["id"] = d["id"]

            # Coerce flow_policy_config into FlowPolicyPreset enum when provided
            if "flow_policy_config" in d:
                td_kwargs["flow_policy_config"] = _coerce_flow_policy_config(
                    d["flow_policy_config"]
                )

            coerced.append(TrafficDemand(**td_kwargs))

        tms.add(name, coerced)

    return tms


def _coerce_flow_policy_config(value: Any) -> Optional[FlowPolicyPreset]:
    """Return a FlowPolicyPreset from various user-friendly forms.

    Accepts:
      - None: returns None
      - FlowPolicyPreset: returned as-is
      - int: mapped by value (e.g., 1 -> SHORTEST_PATHS_ECMP)
      - str: name of enum (case-insensitive); numeric strings are allowed

    Any other type is returned unchanged for advanced usages
    (e.g., dict configs handled elsewhere).
    """
    if value is None:
        return None
    if isinstance(value, FlowPolicyPreset):
        return value
    if isinstance(value, int):
        try:
            return FlowPolicyPreset(value)
        except Exception as exc:  # pragma: no cover - validated by enum
            raise ValueError(f"Unknown flow policy config value: {value}") from exc
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Allow numeric strings
        if s.isdigit():
            try:
                return FlowPolicyPreset(int(s))
            except Exception as exc:
                raise ValueError(f"Unknown flow policy config value: {s}") from exc
        # Enum name lookup (case-insensitive)
        try:
            return FlowPolicyPreset[s.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown flow policy config: {value}") from exc

    # Preserve other structural forms (e.g., dict) for callers that support them
    return value  # type: ignore[return-value]
