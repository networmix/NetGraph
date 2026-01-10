"""Selector parsing and normalization.

Provides the single entry point for converting raw selector values
(strings or dicts) into NodeSelector objects.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Literal, Union

from .schema import Condition, MatchSpec, NodeSelector

__all__ = [
    "normalize_selector",
    "parse_match_spec",
]

# Context-aware defaults for active_only
_ACTIVE_ONLY_DEFAULTS: Dict[str, bool] = {
    "adjacency": False,
    "override": False,
    "demand": True,
    "workflow": True,
}


def normalize_selector(
    raw: Union[str, Dict[str, Any], NodeSelector],
    context: str,
) -> NodeSelector:
    """Normalize a raw selector (string or dict) to a NodeSelector.

    This is the single entry point for all selector parsing. All downstream
    code works with NodeSelector objects only.

    Args:
        raw: Either a regex string, selector dict, or existing NodeSelector.
        context: Usage context ("adjacency", "demand", "override", "workflow").
            Determines the default for active_only.

    Returns:
        Normalized NodeSelector instance.

    Raises:
        ValueError: If selector format is invalid or context is unknown.
    """
    default_active_only = _ACTIVE_ONLY_DEFAULTS.get(context)
    if default_active_only is None:
        raise ValueError(
            f"Unknown context '{context}'. "
            f"Expected one of: {list(_ACTIVE_ONLY_DEFAULTS.keys())}"
        )

    if isinstance(raw, NodeSelector):
        if raw.active_only is None:
            return replace(raw, active_only=default_active_only)
        return raw

    if isinstance(raw, str):
        return NodeSelector(path=raw, active_only=default_active_only)

    if isinstance(raw, dict):
        return _parse_dict(raw, default_active_only)

    raise ValueError(f"Selector must be string or dict, got {type(raw).__name__}")


def _parse_dict(raw: Dict[str, Any], default_active_only: bool) -> NodeSelector:
    """Parse a selector dictionary into a NodeSelector."""
    match_spec = None
    if "match" in raw:
        match_spec = _parse_match(raw["match"])

    path = raw.get("path")
    group_by = raw.get("group_by")
    active_only = raw.get("active_only", default_active_only)

    # Validate at least one selection mechanism
    if path is None and group_by is None and match_spec is None:
        raise ValueError(
            "Selector dict requires at least one of: path, group_by, or match"
        )

    return NodeSelector(
        path=path,
        group_by=group_by,
        match=match_spec,
        active_only=active_only,
    )


def parse_match_spec(
    raw: Dict[str, Any],
    *,
    default_logic: Literal["and", "or"] = "or",
    require_conditions: bool = False,
    context: str = "match",
) -> MatchSpec:
    """Parse a match specification from raw dict.

    Unified match specification parser for use across adjacency, demands,
    membership rules, and failure policies.

    Args:
        raw: Dict with 'conditions' list and optional 'logic'.
        default_logic: Default when 'logic' not specified.
        require_conditions: If True, raise when conditions list is empty.
        context: Used in error messages.

    Returns:
        Parsed MatchSpec.

    Raises:
        ValueError: If validation fails.
    """
    logic = raw.get("logic", default_logic)
    if logic not in ("and", "or"):
        raise ValueError(
            f"Invalid logic '{logic}' in {context}. Must be 'and' or 'or'."
        )

    conditions_raw = raw.get("conditions", [])
    if require_conditions and not conditions_raw:
        raise ValueError(f"{context} requires at least one condition")

    conditions = []
    for cond_dict in conditions_raw:
        if not isinstance(cond_dict, dict):
            raise ValueError(
                f"Condition in {context} must be a dict, got {type(cond_dict).__name__}"
            )
        if "attr" not in cond_dict or "op" not in cond_dict:
            raise ValueError(f"Condition in {context} must have 'attr' and 'op'")

        conditions.append(
            Condition(
                attr=cond_dict["attr"],
                op=cond_dict["op"],
                value=cond_dict.get("value"),
            )
        )

    return MatchSpec(conditions=conditions, logic=logic)


def _parse_match(raw: Dict[str, Any]) -> MatchSpec:
    """Parse a match specification dict (internal helper).

    Uses parse_match_spec with selector defaults (logic="or", conditions optional).
    """
    return parse_match_spec(raw, default_logic="or", require_conditions=False)
