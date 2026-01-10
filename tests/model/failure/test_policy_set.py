"""Tests for FailurePolicySet class."""

import pytest

from ngraph.model.failure.policy import FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet


class TestFailurePolicySet:
    """Test cases for FailurePolicySet functionality."""

    def test_empty_policy_set(self):
        """Test empty failure policy set."""
        fps = FailurePolicySet()
        assert len(fps.policies) == 0
        assert fps.get_all_policies() == []

    def test_add_and_get_policy(self):
        """Test adding and retrieving policies."""
        fps = FailurePolicySet()
        from ngraph.model.failure.policy import FailureMode

        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])

        fps.add("test_policy", policy)
        assert len(fps.policies) == 1
        assert fps.get_policy("test_policy") is policy

    def test_get_nonexistent_policy(self):
        """Test getting a policy that doesn't exist."""
        fps = FailurePolicySet()
        with pytest.raises(KeyError):
            fps.get_policy("nonexistent")

    def test_get_all_policies(self):
        """Test getting all policies."""
        fps = FailurePolicySet()
        from ngraph.model.failure.policy import FailureMode

        policy1 = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])
        policy2 = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])

        fps.add("policy1", policy1)
        fps.add("policy2", policy2)

        all_policies = fps.get_all_policies()
        assert len(all_policies) == 2
        assert policy1 in all_policies
        assert policy2 in all_policies

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        fps = FailurePolicySet()

        # Create a policy with some rules and attributes
        rule = FailureRule(scope="node", mode="choice", count=1)
        from ngraph.model.failure.policy import FailureMode

        policy = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[rule])],
            attrs={"name": "test_policy", "description": "Test policy"},
            expand_groups=True,
        )

        fps.add("test", policy)

        result = fps.to_dict()

        assert "test" in result
        assert "modes" in result["test"]
        assert "attrs" in result["test"]
        assert result["test"]["expand_groups"] is True
        # Modes present
        assert "modes" in result["test"] and len(result["test"]["modes"]) == 1

        # Check rule serialization inside modes
        mode = result["test"]["modes"][0]
        assert len(mode["rules"]) == 1
        rule_dict = mode["rules"][0]
        assert rule_dict["scope"] == "node"
        assert rule_dict["mode"] == "choice"
        assert rule_dict["count"] == 1

    def test_to_dict_multiple_policies(self):
        """Test serialization with multiple policies."""
        fps = FailurePolicySet()

        from ngraph.model.failure.policy import FailureMode

        policy1 = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[])], attrs={"name": "policy1"}
        )
        policy2 = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[])], attrs={"name": "policy2"}
        )

        fps.add("first", policy1)
        fps.add("second", policy2)

        result = fps.to_dict()

        assert len(result) == 2
        assert "first" in result
        assert "second" in result
        assert result["first"]["attrs"]["name"] == "policy1"
        assert result["second"]["attrs"]["name"] == "policy2"
