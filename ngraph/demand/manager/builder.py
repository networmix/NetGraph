"""Builders for traffic matrices.

Construct `TrafficMatrixSet` from raw dictionaries (e.g. parsed YAML).
This logic was previously embedded in `Scenario.from_yaml`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.yaml_utils import normalize_yaml_dict_keys


def build_traffic_matrix_set(raw: Dict[str, List[dict]]) -> TrafficMatrixSet:
    """Build a `TrafficMatrixSet` from a mapping of name -> list of dicts.

    Args:
        raw: Mapping where each key is a matrix name and each value is a list of
            dictionaries with `TrafficDemand` constructor fields.

    Returns:
        Initialized `TrafficMatrixSet` with constructed `TrafficDemand` objects.

    Raises:
        ValueError: If ``raw`` is not a mapping of name -> list[dict].
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

            # Coerce flow_policy_config into FlowPolicyConfig enum when provided
            if "flow_policy_config" in d:
                d = dict(d)  # shallow copy to avoid mutating caller data
                d["flow_policy_config"] = _coerce_flow_policy_config(
                    d.get("flow_policy_config")
                )

            coerced.append(TrafficDemand(**d))

        tms.add(name, coerced)

    return tms


def _coerce_flow_policy_config(value: Any) -> Optional[FlowPolicyConfig]:
    """Return a FlowPolicyConfig from various user-friendly forms.

    Accepts:
      - None: returns None
      - FlowPolicyConfig: returned as-is
      - int: mapped by value (e.g., 1 -> SHORTEST_PATHS_ECMP)
      - str: name of enum (case-insensitive); numeric strings are allowed

    Any other type is returned unchanged to preserve backwards-compat behavior
    for advanced usages (e.g., dict configs handled elsewhere).
    """
    if value is None:
        return None
    if isinstance(value, FlowPolicyConfig):
        return value
    if isinstance(value, int):
        try:
            return FlowPolicyConfig(value)
        except Exception as exc:  # pragma: no cover - validated by enum
            raise ValueError(f"Unknown flow policy config value: {value}") from exc
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Allow numeric strings
        if s.isdigit():
            try:
                return FlowPolicyConfig(int(s))
            except Exception as exc:
                raise ValueError(f"Unknown flow policy config value: {s}") from exc
        # Enum name lookup (case-insensitive)
        try:
            return FlowPolicyConfig[s.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown flow policy config: {value}") from exc

    # Preserve other structural forms (e.g., dict) for callers that support them
    return value  # type: ignore[return-value]
