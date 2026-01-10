"""Schema definitions for variable expansion.

Provides dataclasses for template expansion configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional


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
