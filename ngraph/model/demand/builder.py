"""Builders for demand sets.

Construct `DemandSet` from raw dictionaries (e.g. parsed YAML).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ngraph.dsl.expansion import ExpansionSpec, expand_block
from ngraph.model.demand.matrix import DemandSet
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys


def build_demand_set(raw: Dict[str, List[dict]]) -> DemandSet:
    """Build a `DemandSet` from a mapping of name -> list of dicts.

    Args:
        raw: Mapping where each key is a demand set name and each value is a list of
            dictionaries with `TrafficDemand` constructor fields.

    Returns:
        Initialized `DemandSet` with constructed `TrafficDemand` objects.

    Raises:
        ValueError: If ``raw`` is not a mapping of name -> list[dict],
            or if required fields are missing.
    """
    if not isinstance(raw, dict):
        raise ValueError("'demands' must be a mapping of name -> list[TrafficDemand]")

    normalized_raw = normalize_yaml_dict_keys(raw)
    ds = DemandSet()
    for name, td_list in normalized_raw.items():
        if not isinstance(td_list, list):
            raise ValueError(
                f"Demand set '{name}' must map to a list of TrafficDemand dicts"
            )
        coerced: List[TrafficDemand] = []
        for d in td_list:
            if not isinstance(d, dict):
                raise ValueError(
                    f"Entries in demand set '{name}' must be dicts, "
                    f"got {type(d).__name__}"
                )

            # Handle expand block
            expand_spec = ExpansionSpec.from_dict(d)
            if expand_spec and not expand_spec.is_empty():
                for expanded in expand_block(d, expand_spec):
                    coerced.append(_build_demand(expanded, name))
            else:
                coerced.append(_build_demand(d, name))

        ds.add(name, coerced)

    return ds


def _build_demand(d: Dict[str, Any], set_name: str) -> TrafficDemand:
    """Build a single TrafficDemand from a dict."""
    # Validate required fields
    if "source" not in d or "target" not in d:
        raise ValueError(
            f"Each demand in set '{set_name}' requires 'source' and 'target' fields"
        )

    # Build normalized dict for TrafficDemand constructor
    td_kwargs: Dict[str, Any] = {
        "source": d["source"],
        "target": d["target"],
        "volume": d.get("volume", 0.0),
        "priority": d.get("priority", 0),
        "mode": d.get("mode", "combine"),
        "group_mode": d.get("group_mode", "flatten"),
        "attrs": d.get("attrs", {}),
    }

    # Optional id
    if "id" in d:
        td_kwargs["id"] = d["id"]

    # Coerce flow_policy into FlowPolicyPreset enum when provided
    if "flow_policy" in d:
        td_kwargs["flow_policy"] = _coerce_flow_policy(d["flow_policy"])

    return TrafficDemand(**td_kwargs)


def _coerce_flow_policy(value: Any) -> Optional[FlowPolicyPreset]:
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
            raise ValueError(f"Unknown flow policy value: {value}") from exc
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Allow numeric strings
        if s.isdigit():
            try:
                return FlowPolicyPreset(int(s))
            except Exception as exc:
                raise ValueError(f"Unknown flow policy value: {s}") from exc
        # Enum name lookup (case-insensitive)
        try:
            return FlowPolicyPreset[s.upper()]
        except KeyError as exc:
            raise ValueError(f"Unknown flow policy: {value}") from exc

    # Preserve other structural forms (e.g., dict) for callers that support them
    return value  # type: ignore[return-value]
