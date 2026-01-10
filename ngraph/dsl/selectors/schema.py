"""Schema definitions for unified node selection.

Provides dataclasses for node selection configuration used across
network rules, demands, and workflow steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Literal, Optional

# Type alias for entity scope used in condition-based selection
EntityScope = Literal["node", "link", "risk_group"]
"""Type of network entity for condition-based selection."""


# Valid operators for conditions
VALID_OPERATORS: frozenset[str] = frozenset(
    {
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
    }
)


@dataclass
class Condition:
    """A single attribute condition for filtering.

    Supports dot-notation for nested attribute access (e.g., "hardware.vendor"
    resolves to attrs["hardware"]["vendor"]).

    Attributes:
        attr: Attribute name to match (supports dot-notation for nested attrs).
        op: Comparison operator.
        value: Right-hand operand (unused for exists/not_exists).
    """

    attr: str
    op: Literal[
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
    value: Any = None

    def __post_init__(self) -> None:
        if self.op not in VALID_OPERATORS:
            raise ValueError(
                f"Invalid operator '{self.op}'. "
                f"Valid operators: {sorted(VALID_OPERATORS)}"
            )


@dataclass
class MatchSpec:
    """Specification for filtering nodes by attribute conditions.

    Attributes:
        conditions: List of conditions to evaluate.
        logic: How to combine conditions ("and" = all, "or" = any).
    """

    conditions: List[Condition] = field(default_factory=list)
    logic: Literal["and", "or"] = "or"


@dataclass
class NodeSelector:
    """Unified node selection specification.

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
                "NodeSelector requires at least one of: path, group_by, or match"
            )
