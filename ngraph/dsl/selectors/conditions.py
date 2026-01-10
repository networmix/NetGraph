"""Condition evaluation for node/entity filtering.

Provides evaluation logic for attribute conditions used in selectors
and failure policies. Supports operators: ==, !=, <, <=, >, >=,
contains, not_contains, in, not_in, exists, not_exists.

Supports dot-notation for nested attribute access (e.g., "hardware.vendor").
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, Tuple

if TYPE_CHECKING:
    from .schema import Condition

__all__ = [
    "evaluate_condition",
    "evaluate_conditions",
    "resolve_attr_path",
]


def resolve_attr_path(attrs: Dict[str, Any], path: str) -> Tuple[bool, Any]:
    """Resolve a dot-notation attribute path.

    Supports nested attribute access like "hardware.vendor" which resolves
    to attrs["hardware"]["vendor"].

    Args:
        attrs: Attribute dict (may contain nested dicts).
        path: Attribute path, optionally with dots for nesting.

    Returns:
        Tuple of (found, value). If found is False, value is None.

    Examples:
        >>> resolve_attr_path({"role": "spine"}, "role")
        (True, "spine")
        >>> resolve_attr_path({"hardware": {"vendor": "Acme"}}, "hardware.vendor")
        (True, "Acme")
        >>> resolve_attr_path({"role": "spine"}, "missing")
        (False, None)
    """
    parts = path.split(".")
    current: Any = attrs

    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return (False, None)

    return (True, current)


def evaluate_condition(attrs: Dict[str, Any], cond: "Condition") -> bool:
    """Evaluate a single condition against an attribute dict.

    Supports dot-notation for nested attribute access (e.g., "hardware.vendor").

    Args:
        attrs: Mapping of entity attributes (may contain nested dicts).
        cond: Condition to evaluate.

    Returns:
        True if condition passes, False otherwise.

    Raises:
        ValueError: If operator is unknown or value type is invalid.
    """
    has_attr, attr_value = resolve_attr_path(attrs, cond.attr)
    op = cond.op
    expected = cond.value

    # Existence operators
    if op == "exists":
        return has_attr and attr_value is not None
    if op == "not_exists":
        return (not has_attr) or (attr_value is None)

    # For all other operators, missing/None attribute means no match
    if attr_value is None:
        return False

    # Equality operators
    if op == "==":
        return attr_value == expected
    if op == "!=":
        return attr_value != expected

    # Numeric comparisons
    if op in ("<", "<=", ">", ">="):
        try:
            left = float(attr_value)
            right = float(expected)
        except (TypeError, ValueError):
            return False
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right

    # String/collection containment
    if op == "contains":
        if isinstance(attr_value, str):
            return str(expected) in attr_value
        if isinstance(attr_value, (list, tuple, set)):
            return expected in attr_value
        return False

    if op == "not_contains":
        if isinstance(attr_value, str):
            return str(expected) not in attr_value
        if isinstance(attr_value, (list, tuple, set)):
            return expected not in attr_value
        return True

    # List membership operators
    if op == "in":
        if not isinstance(expected, (list, tuple, set)):
            raise ValueError(f"'in' operator requires list value, got {type(expected)}")
        return attr_value in expected

    if op == "not_in":
        if not isinstance(expected, (list, tuple, set)):
            raise ValueError(
                f"'not_in' operator requires list value, got {type(expected)}"
            )
        return attr_value not in expected

    raise ValueError(f"Unknown operator: {op}")


def evaluate_conditions(
    attrs: Dict[str, Any],
    conditions: Iterable["Condition"],
    logic: str = "or",
) -> bool:
    """Evaluate multiple conditions with AND/OR logic.

    Args:
        attrs: Flat mapping of entity attributes.
        conditions: Iterable of Condition objects.
        logic: "and" (all must match) or "or" (any must match).

    Returns:
        True if combined predicate passes.

    Raises:
        ValueError: If logic is not "and" or "or".
    """
    cond_list = list(conditions)
    if not cond_list:
        return True

    if logic == "and":
        return all(evaluate_condition(attrs, c) for c in cond_list)
    if logic == "or":
        return any(evaluate_condition(attrs, c) for c in cond_list)

    raise ValueError(f"Unsupported logic: {logic}")
