"""Selector parsing and normalization.

Provides the single entry point for converting raw selector values
(strings or dicts) into NodeSelector objects.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Union

from .schema import Condition, MatchSpec, NodeSelector

__all__ = [
    "normalize_selector",
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


def _parse_match(raw: Dict[str, Any]) -> MatchSpec:
    """Parse a match specification dict."""
    conditions = []
    for cond_dict in raw.get("conditions", []):
        if not isinstance(cond_dict, dict):
            raise ValueError(
                f"Each condition must be a dict, got {type(cond_dict).__name__}"
            )
        if "attr" not in cond_dict or "operator" not in cond_dict:
            raise ValueError("Each condition must have 'attr' and 'operator'")

        conditions.append(
            Condition(
                attr=cond_dict["attr"],
                operator=cond_dict["operator"],
                value=cond_dict.get("value"),
            )
        )

    return MatchSpec(
        conditions=conditions,
        logic=raw.get("logic", "or"),
    )
