"""Failure modeling package.

Provides primitives to define failure selection rules and to run Monte Carlo
failure analyses. The `policy` module defines data classes for expressing
selection logic over nodes, links, and risk groups. The `manager` subpackage
contains the engine that applies those policies to a `Network` and runs
iterative analyses.

Public entry points:

- `ngraph.failure.policy` - failure selection rules and policy application
- `ngraph.failure.manager` - `FailureManager` for running analyses
- `ngraph.failure.validation` - risk group reference validation
- `ngraph.failure.membership` - risk group membership rule resolution
- `ngraph.failure.generate` - dynamic risk group generation
"""

from .generate import GenerateSpec, generate_risk_groups, parse_generate_spec
from .membership import MembershipSpec, resolve_membership_rules
from .validation import validate_risk_group_hierarchy, validate_risk_group_references

__all__ = [
    "GenerateSpec",
    "generate_risk_groups",
    "parse_generate_spec",
    "MembershipSpec",
    "resolve_membership_rules",
    "validate_risk_group_hierarchy",
    "validate_risk_group_references",
]
