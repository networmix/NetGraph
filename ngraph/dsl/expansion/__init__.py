"""Variable and pattern expansion for NetGraph DSL.

This module provides template expansion with $var syntax and
bracket pattern expansion for name generation.

Usage:
    from ngraph.dsl.expansion import expand_templates, expand_name_patterns, ExpansionSpec

    # Variable expansion
    spec = ExpansionSpec(expand_vars={"dc": [1, 2, 3]})
    for result in expand_templates({"path": "dc${dc}/leaf"}, spec):
        print(result)  # {"path": "dc1/leaf"}, {"path": "dc2/leaf"}, ...

    # Bracket expansion
    names = expand_name_patterns("leaf[1-4]")  # ["leaf1", "leaf2", "leaf3", "leaf4"]
"""

from .brackets import expand_name_patterns, expand_risk_group_refs
from .schema import ExpansionSpec
from .variables import expand_templates, substitute_vars

__all__ = [
    # Schema
    "ExpansionSpec",
    # Variable expansion
    "expand_templates",
    "substitute_vars",
    # Bracket expansion
    "expand_name_patterns",
    "expand_risk_group_refs",
]
