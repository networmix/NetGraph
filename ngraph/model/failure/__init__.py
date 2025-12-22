"""Failure modeling package.

Provides primitives to define failure selection rules for Monte Carlo
failure analyses. The `policy` module defines data classes for expressing
selection logic over nodes, links, and risk groups.

Public entry points:

- `ngraph.model.failure.policy` - failure selection rules and policy application
- `ngraph.model.failure.policy_set` - named collection of failure policies
- `ngraph.model.failure.validation` - risk group reference validation
- `ngraph.model.failure.membership` - risk group membership rule resolution
- `ngraph.model.failure.generate` - dynamic risk group generation
- `ngraph.analysis.failure_manager` - `FailureManager` for running Monte Carlo analyses
"""

from .generate import GenerateSpec, generate_risk_groups, parse_generate_spec
from .membership import MembershipSpec, resolve_membership_rules
from .policy import FailureCondition, FailureMode, FailurePolicy, FailureRule
from .policy_set import FailurePolicySet
from .validation import validate_risk_group_hierarchy, validate_risk_group_references

__all__ = [
    # Policy classes
    "FailurePolicy",
    "FailureRule",
    "FailureMode",
    "FailureCondition",
    "FailurePolicySet",
    # Generation
    "GenerateSpec",
    "generate_risk_groups",
    "parse_generate_spec",
    # Membership
    "MembershipSpec",
    "resolve_membership_rules",
    # Validation
    "validate_risk_group_hierarchy",
    "validate_risk_group_references",
]
