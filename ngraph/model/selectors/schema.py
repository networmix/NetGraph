"""Selector schema dataclasses.

Shared by network rules, demands, failure policies, and workflow steps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Optional, get_args

from ngraph.utils.values import (
    _located_error,
    _shown,
    collection,
    frozen_json,
    optional_flag,
    optional_pattern,
    optional_text,
    own,
    text,
)

EntityScope = Literal["node", "link", "risk_group"]
"""Type of network entity for condition-based selection."""


ConditionOp = Literal[
    "==",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "contains",
    "not_contains",
    "in",
    "not_in",
    "exists",
    "not_exists",
]
"""Comparison operators supported by conditions."""

# Valid operators for conditions (derived from ConditionOp)
VALID_OPERATORS: frozenset[str] = frozenset(get_args(ConditionOp))


@dataclass(frozen=True)
class Condition:
    """A single attribute condition for filtering.

    Supports dot-notation for nested attribute access (e.g., "hardware.vendor"
    resolves to attrs["hardware"]["vendor"]).

    Attributes:
        attr: Attribute name to match (supports dot-notation for nested attrs).
        op: Comparison operator.
        value: Right-hand operand (unused for exists/not_exists): finite JSON
            data, stored read-only with accepted scalar subclasses normalized.
    """

    attr: str
    op: ConditionOp
    value: Any = None

    def __post_init__(self) -> None:
        attr = text(self.attr, "condition.attr")
        if not isinstance(self.op, str) or self.op not in VALID_OPERATORS:
            raise _located_error(
                ValueError(
                    f"condition.op: expected one of {sorted(VALID_OPERATORS)}, got {_shown(self.op)}"
                ),
                "condition.op",
                self.op,
            )
        if self.op in ("in", "not_in") and not isinstance(self.value, list):
            raise _located_error(
                ValueError(
                    f"condition {attr}.value: {_shown(self.op)} requires a list, got {_shown(self.value)}"
                ),
                f"condition {attr}.value",
                self.value,
            )
        own(
            self,
            attr=attr,
            op=str.__str__(self.op),
            value=frozen_json(self.value, f"condition {attr}.value"),
        )


@dataclass(frozen=True)
class MatchSpec:
    """Attribute conditions combined with "and" or "or" logic.

    Attributes:
        conditions: Conditions to evaluate, in order.
        logic: How to combine conditions ("and" = all, "or" = any).
    """

    conditions: Sequence[Condition] = ()
    logic: Literal["and", "or"] = "or"

    def __post_init__(self) -> None:
        conditions = collection(self.conditions, "match.conditions")
        if not all(isinstance(c, Condition) for c in conditions):
            raise TypeError(
                f"match.conditions: expected Condition values, got {_shown(conditions)}"
            )
        if not isinstance(self.logic, str) or self.logic not in ("and", "or"):
            raise ValueError(
                f"match.logic: expected and or or, got {_shown(self.logic)}"
            )
        own(self, conditions=conditions, logic=str.__str__(self.logic))


@dataclass(frozen=True)
class Selector:
    """Node selection by name regex, attribute conditions, and grouping.

    Evaluation order:
    1. Select nodes matching `path` regex (default ".*" if omitted)
    2. Filter by `match` conditions
    3. Filter by `active_only` flag
    4. Group by `group_by` attribute (if specified)

    At least one of path, group_by, or match must be specified.

    Attributes:
        path: Regex pattern on node.name.
        group_by: Attribute name to group nodes by.
        match: Attribute-based filtering conditions.
        active_only: Whether to exclude disabled nodes. None uses context default.
    """

    path: Optional[str] = None
    group_by: Optional[str] = None
    match: Optional[MatchSpec] = None
    active_only: Optional[bool] = None

    def __post_init__(self) -> None:
        if self.path is None and self.group_by is None and self.match is None:
            raise ValueError(
                "Selector requires at least one of: path, group_by, or match"
            )
        own(
            self,
            # An empty path matches every node name.
            path=optional_pattern(self.path, "selector.path", empty=True),
            group_by=optional_text(self.group_by, "selector.group_by"),
            active_only=optional_flag(self.active_only, "selector.active_only"),
        )
        if self.match is not None and not isinstance(self.match, MatchSpec):
            raise TypeError(
                f"Selector 'match' must be MatchSpec or None, got {_shown(self.match)}"
            )
