"""Schema definitions for variable expansion.

Provides dataclasses for template expansion configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass
class ExpansionSpec:
    """Specification for variable-based expansion.

    Attributes:
        expand_vars: Mapping of variable names to lists of values.
        expansion_mode: How to combine variable values.
            - "cartesian": All combinations (default)
            - "zip": Pair values by position
    """

    expand_vars: Dict[str, List[Any]] = field(default_factory=dict)
    expansion_mode: Literal["cartesian", "zip"] = "cartesian"

    def is_empty(self) -> bool:
        """Check if no variables are defined."""
        return not self.expand_vars
