"""Shared condition primitives and evaluators.

This module provides a small, dependency-free condition evaluation utility
that can be reused by failure policies and DSL selection filters.

Operators supported:
- ==, !=, <, <=, >, >=
- contains, not_contains
- any_value, no_value

The evaluator operates on a flat attribute mapping for an entity. Callers are
responsible for constructing that mapping (e.g. merging top-level fields with
``attrs`` and ensuring appropriate precedence rules).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "FailureCondition",
    "evaluate_condition",
    "evaluate_conditions",
]


@dataclass
class FailureCondition:
    """A single condition for matching an entity attribute.

    Args:
        attr: Attribute name to inspect in the entity mapping.
        operator: Comparison operator. See module docstring for the list.
        value: Right-hand operand for the comparison (unused for any_value/no_value).
    """

    attr: str
    operator: str
    value: Any | None = None


def evaluate_condition(entity_attrs: dict[str, Any], cond: FailureCondition) -> bool:
    """Evaluate a single condition against an entity attribute mapping.

    Args:
        entity_attrs: Flat mapping of attributes for the entity.
        cond: Condition to evaluate.

    Returns:
        True if the condition passes, False otherwise.
    """
    has_attr = cond.attr in entity_attrs
    derived_value = entity_attrs.get(cond.attr, None)
    op = cond.operator

    if op == "==":
        return derived_value == cond.value
    elif op == "!=":
        return derived_value != cond.value
    elif op == "<":
        return (derived_value is not None) and (derived_value < cond.value)
    elif op == "<=":
        return (derived_value is not None) and (derived_value <= cond.value)
    elif op == ">":
        return (derived_value is not None) and (derived_value > cond.value)
    elif op == ">=":
        return (derived_value is not None) and (derived_value >= cond.value)
    elif op == "contains":
        if derived_value is None:
            return False
        try:
            return cond.value in derived_value  # type: ignore[operator]
        except TypeError:
            return False
    elif op == "not_contains":
        if derived_value is None:
            return True
        try:
            return cond.value not in derived_value  # type: ignore[operator]
        except TypeError:
            return True
    elif op == "any_value":
        return has_attr
    elif op == "no_value":
        return (not has_attr) or (derived_value is None)
    else:
        raise ValueError(f"Unsupported operator: {op}")


def evaluate_conditions(
    entity_attrs: dict[str, Any],
    conditions: Iterable[FailureCondition],
    logic: str,
) -> bool:
    """Evaluate multiple conditions with AND/OR logic.

    Args:
        entity_attrs: Flat mapping of attributes for the entity.
        conditions: Iterable of conditions to evaluate.
        logic: "and" or "or".

    Returns:
        True if the combined predicate passes, False otherwise.
    """
    if logic == "and":
        return all(evaluate_condition(entity_attrs, c) for c in conditions)
    if logic == "or":
        return any(evaluate_condition(entity_attrs, c) for c in conditions)
    raise ValueError(f"Unsupported logic: {logic}")
