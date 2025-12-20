"""Schema definitions for unified node selection.

Provides dataclasses for node selection configuration used across
adjacency, demands, overrides, and workflow steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Literal, Optional


@dataclass
class Condition:
    """A single attribute condition for filtering.

    Attributes:
        attr: Attribute name to match.
        operator: Comparison operator.
        value: Right-hand operand (unused for any_value/no_value).
    """

    attr: str
    operator: Literal[
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
        "any_value",
        "no_value",
    ]
    value: Any = None


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
