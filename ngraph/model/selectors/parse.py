"""Parsing of match specifications from plain dicts.

Builds model schema types (`Condition`, `MatchSpec`) from raw dict input.
Lives in the model layer so failure-policy and membership parsing can use
it without a runtime dependency on the DSL package.
"""

from __future__ import annotations

from typing import Any, Dict, Literal

from .schema import Condition, MatchSpec


def parse_match_spec(
    raw: Dict[str, Any],
    *,
    default_logic: Literal["and", "or"] = "or",
    require_conditions: bool = False,
    context: str = "match",
) -> MatchSpec:
    """Parse a match specification from raw dict.

    Shared by adjacency, demands, membership rules, and failure policies.

    Args:
        raw: Dict with 'conditions' list and optional 'logic'. Both keys are
            optional; a missing 'conditions' yields an empty condition list.
        default_logic: Used when 'logic' is absent.
        require_conditions: If True, raise when conditions list is empty.
        context: Name of the enclosing construct, quoted in error messages.

    Returns:
        Parsed MatchSpec.

    Raises:
        ValueError: If 'logic' is not 'and'/'or', 'conditions' is not a list,
            a condition is not a dict or lacks 'attr'/'op', 'in'/'not_in' is
            given a non-list value, or conditions are required but empty.
    """
    logic = raw.get("logic", default_logic)
    if logic not in ("and", "or"):
        raise ValueError(
            f"Invalid logic '{logic}' in {context}. Must be 'and' or 'or'."
        )

    conditions_raw = raw.get("conditions", [])
    if not isinstance(conditions_raw, list):
        raise ValueError(f"'conditions' in {context} must be a list")
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
        if cond_dict["op"] in ("in", "not_in") and not isinstance(
            cond_dict.get("value"), list
        ):
            raise ValueError(
                f"Condition in {context}: operator '{cond_dict['op']}' "
                "requires a list value"
            )

        conditions.append(
            Condition(
                attr=cond_dict["attr"],
                op=cond_dict["op"],
                value=cond_dict.get("value"),
            )
        )

    return MatchSpec(conditions=conditions, logic=logic)
