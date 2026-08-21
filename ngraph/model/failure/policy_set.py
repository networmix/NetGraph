"""Failure policy containers.

Provides `FailurePolicySet`, a named collection of `FailurePolicy` objects
used as input to failure analysis workflows. This module contains input
containers, not analysis results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ngraph.model.failure.policy import FailurePolicy


@dataclass
class FailurePolicySet:
    """Named collection of FailurePolicy objects.

    Attributes:
        policies: Dictionary mapping failure policy names to FailurePolicy objects.
    """

    policies: dict[str, FailurePolicy] = field(default_factory=dict)

    def add(self, name: str, policy: FailurePolicy) -> None:
        """Add a policy, replacing any policy already stored under `name`.

        Args:
            name: Failure policy name identifier.
            policy: FailurePolicy to store; kept by reference, not copied.
        """
        self.policies[name] = policy

    def get_policy(self, name: str) -> FailurePolicy:
        """Get a specific failure policy by name.

        Args:
            name: Name of the policy to retrieve.

        Returns:
            FailurePolicy object for the named policy.

        Raises:
            KeyError: If the policy name doesn't exist.
        """
        return self.policies[name]

    def get_all_policies(self) -> list[FailurePolicy]:
        """Get all failure policies from the collection.

        Returns:
            A new list of the stored policies, in insertion order.
        """
        return list(self.policies.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary mapping failure policy names to FailurePolicy dictionaries.
        """
        return {name: policy.to_dict() for name, policy in self.policies.items()}
