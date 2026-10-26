"""Parsing of match specifications from plain dicts.

Builds model schema types (`Condition`, `MatchSpec`) from raw dict input.
Lives in the model layer so failure-policy and membership parsing can use
it without a runtime dependency on the DSL package.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, Literal, Union

from ngraph.utils.values import _located_error, _shown, flag
from ngraph.utils.yaml_utils import check_no_extra_keys, declared

from .schema import Condition, MatchSpec, Selector


def parse_match_spec(
    raw: Dict[str, Any],
    *,
    default_logic: Literal["and", "or"] = "or",
    require_conditions: bool = False,
    context: str = "match",
) -> MatchSpec:
    """Parse a match specification from raw dict.

    Shared by link definitions, demands, membership rules, and failure policies.

    Args:
        raw: Dict with 'conditions' list and optional 'logic'. Both keys are
            optional; a missing 'conditions' yields an empty condition list.
        default_logic: Used when 'logic' is absent.
        require_conditions: If True, raise when conditions list is empty.
        context: Name of the enclosing construct, quoted in error messages.

    Returns:
        Parsed MatchSpec.

    Raises:
        ValueError: If the spec or a condition carries an unrecognized key,
            'logic' is not 'and'/'or', 'conditions' is not a list, a
            condition is not a dict or lacks 'attr'/'op', 'in'/'not_in' is
            given a non-list value, or conditions are required but empty.
    """
    require_conditions = flag(require_conditions, "parse_match_spec.require_conditions")
    check_no_extra_keys(raw, {"conditions", "logic"}, context)
    logic = raw.get("logic", default_logic)
    if logic not in ("and", "or"):
        raise ValueError(
            f"Invalid logic {_shown(logic)} in {context}. Must be 'and' or 'or'."
        )

    conditions_raw = raw.get("conditions", [])
    if not isinstance(conditions_raw, list):
        raise ValueError(f"'conditions' in {context} must be a list")
    if require_conditions and not conditions_raw:
        raise ValueError(
            f"{context}.conditions: expected at least one condition, got {_shown(conditions_raw)}"
        )

    conditions = []
    for cond_dict in conditions_raw:
        if not isinstance(cond_dict, dict):
            raise ValueError(
                f"Condition in {context} must be a dict, got {type(cond_dict).__name__}"
            )
        if "attr" not in cond_dict or "op" not in cond_dict:
            raise ValueError(f"Condition in {context} must have 'attr' and 'op'")
        check_no_extra_keys(
            cond_dict, {"attr", "op", "value"}, f"condition in {context}"
        )
        conditions.append(
            declared(
                f"{context}.conditions[{len(conditions)}]",
                lambda cond_dict=cond_dict: Condition(
                    attr=cond_dict["attr"],
                    op=cond_dict["op"],
                    value=cond_dict.get("value"),
                ),
                f"condition {cond_dict['attr']}",
            )
        )

    return MatchSpec(conditions=conditions, logic=logic)


# Default active_only for each selector usage context
_ACTIVE_ONLY_DEFAULTS: Dict[str, bool] = {
    "link": False,
    "rule": False,
    "demand": True,
    "workflow": True,
}


def normalize_selector(
    raw: Union[str, Dict[str, Any], Selector],
    context: str,
) -> Selector:
    """Normalize a raw selector (string or dict) to a Selector.

    All downstream code works with Selector objects only.

    Args:
        raw: Either a regex string, selector dict, or existing Selector.
        context: Usage context ("link", "rule", "demand", "workflow").
            Determines the default for active_only.

    Returns:
        Selector with active_only set, from the selector or the context
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

    if isinstance(raw, Selector):
        if raw.active_only is None:
            return replace(raw, active_only=default_active_only)
        return raw

    if isinstance(raw, str):
        return Selector(path=raw, active_only=default_active_only)

    if isinstance(raw, dict):
        return _parse_dict(raw, default_active_only)

    raise ValueError(f"Selector must be string or dict, got {type(raw).__name__}")


def _parse_dict(raw: Dict[str, Any], default_active_only: bool) -> Selector:
    """Parse a selector dictionary into a Selector.

    Selector.__post_init__ validates that at least one selection
    mechanism (path, group_by, or match) is present.
    """
    check_no_extra_keys(raw, {"path", "group_by", "match", "active_only"}, "selector")
    match_spec = None
    if raw.get("match") is not None:
        try:
            match_spec = parse_match_spec(raw["match"])
        except (ValueError, TypeError) as exc:
            label = getattr(exc, "_input_label", "")
            if label == "match" or label.startswith("match."):
                exc.__dict__["_input_label"] = "selector." + label
            elif label.startswith("condition."):
                location = getattr(exc, "_relative_declaration_path", "match")
                exc.__dict__["_input_label"] = (
                    "selector." + location + label[len("condition") :]
                )
            else:
                _located_error(exc, "selector.match", raw["match"])
            raise

    return Selector(
        path=raw.get("path"),
        group_by=raw.get("group_by"),
        match=match_spec,
        active_only=default_active_only
        if raw.get("active_only") is None
        else raw["active_only"],
    )
