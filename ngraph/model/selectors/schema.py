"""Selector schema dataclasses.

Shared by network rules, demands, failure policies, and workflow steps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Optional, get_args

from ngraph.utils.values import frozen_json, own_scalars

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
        own_scalars(self, "condition", ("attr", "op"))
        if self.op not in VALID_OPERATORS:
            raise ValueError(
                f"Invalid operator '{self.op}'. "
                f"Valid operators: {sorted(VALID_OPERATORS)}"
            )
        object.__setattr__(
            self, "value", frozen_json(self.value, f"condition {self.attr}.value")
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
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if not all(isinstance(c, Condition) for c in self.conditions):
            raise TypeError("match conditions: expected Condition values")
        own_scalars(self, "match", ("logic",))


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
        own_scalars(self, "selector", ("path", "group_by", "active_only"))
        if self.path is None and self.group_by is None and self.match is None:
            raise ValueError(
                "Selector requires at least one of: path, group_by, or match"
            )
        if self.path is not None and not isinstance(self.path, str):
            raise ValueError(
                f"Selector 'path' must be a string, got {type(self.path).__name__}"
            )
        if self.group_by is not None and (
            not isinstance(self.group_by, str) or not self.group_by
        ):
            raise ValueError("Selector 'group_by' must be a nonempty string")
        if self.active_only is not None and not isinstance(self.active_only, bool):
            raise ValueError("Selector 'active_only' must be bool or None")
        if self.match is not None and not isinstance(self.match, MatchSpec):
            raise TypeError("Selector 'match' must be MatchSpec or None")
