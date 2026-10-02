"""Selector parsing and normalization.

Converts raw selector values (strings or dicts) into NodeSelector objects.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Union

from ngraph.model.selectors import NodeSelector, parse_match_spec
from ngraph.utils.yaml_utils import check_no_extra_keys

__all__ = ["normalize_selector"]

# Default active_only for each selector usage context
_ACTIVE_ONLY_DEFAULTS: Dict[str, bool] = {
    "link": False,
    "rule": False,
    "demand": True,
    "workflow": True,
}


def normalize_selector(
    raw: Union[str, Dict[str, Any], NodeSelector],
    context: str,
) -> NodeSelector:
    """Normalize a raw selector (string or dict) to a NodeSelector.

    All downstream code works with NodeSelector objects only.

    Args:
        raw: Either a regex string, selector dict, or existing NodeSelector.
        context: Usage context ("link", "rule", "demand", "workflow").
            Determines the default for active_only.

    Returns:
        NodeSelector with active_only set, from the selector or the context
        default.

    Raises:
        ValueError: If the selector is neither a string nor a dict, a selector
            dict carries an unrecognized key, or the context is unknown.
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
    """Parse a selector dictionary into a NodeSelector.

    NodeSelector.__post_init__ validates that at least one selection
    mechanism (path, group_by, or match) is present.
    """
    check_no_extra_keys(raw, {"path", "group_by", "match", "active_only"}, "selector")
    match_spec = None
    if "match" in raw:
        match_spec = parse_match_spec(raw["match"])

    return NodeSelector(
        path=raw.get("path"),
        group_by=raw.get("group_by"),
        match=match_spec,
        active_only=raw.get("active_only", default_active_only),
    )
