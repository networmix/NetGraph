"""Dataclasses describing template expansion configuration."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, cast

from ngraph.utils.values import json_copy, text

MAX_TEMPLATE_EXPANSIONS = 10_000


@dataclass
class ExpansionSpec:
    """Specification for variable-based expansion.

    Attributes:
        vars: Mapping of variable names to lists of values.
        mode: How to combine variable values.
            - "cartesian": All combinations (default)
            - "zip": Pair values by position
    """

    vars: Dict[str, List[Any]] = field(default_factory=dict)
    mode: Literal["cartesian", "zip"] = "cartesian"

    def __post_init__(self) -> None:
        self.mode = cast(Literal["cartesian", "zip"], text(self.mode, "expand.mode"))
        if self.mode not in ("cartesian", "zip"):
            raise ValueError(
                f"expand.mode: expected cartesian or zip, got {self.mode!r}"
            )
        if not isinstance(self.vars, Mapping):
            raise ValueError(
                f"expand.vars: expected a mapping of lists, got {self.vars!r}"
            )
        values = {}
        for name, items in self.vars.items():
            name = text(name, "expand.vars key")
            if not isinstance(items, list):
                raise ValueError(f"expand.vars.{name}: expected a list, got {items!r}")
            values[name] = json_copy(items, f"expand.vars.{name}")
        self.vars = values
        lengths = [len(items) for items in self.vars.values()]
        if self.mode == "zip" and len(set(lengths)) > 1:
            raise ValueError(
                f"expand.vars: zip expansion requires equal-length lists; got lengths {lengths}"
            )
        size = (
            (lengths[0] if lengths else 0) if self.mode == "zip" else math.prod(lengths)
        )
        if size > MAX_TEMPLATE_EXPANSIONS:
            raise ValueError(
                f"expand.vars: Template expansion would create {size} items "
                f"(limit: {MAX_TEMPLATE_EXPANSIONS}). "
                "Consider using fewer variables or splitting into multiple entries."
            )

    def is_empty(self) -> bool:
        """Check if no variables are defined."""
        return not self.vars

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["ExpansionSpec"]:
        """Extract expand: block from dict.

        Args:
            data: Dict that may contain an 'expand' key.

        Returns:
            ExpansionSpec if 'expand' block present, None otherwise.
        """
        if "expand" not in data:
            return None
        expand = data["expand"]
        return cls(
            vars=expand.get("vars", {}),
            mode=expand.get("mode", "cartesian"),
        )
