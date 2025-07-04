"""Tests for FailurePolicySet class."""

import pytest

from ngraph.failure_policy import FailurePolicy, FailureRule
from ngraph.results_artifacts import FailurePolicySet


class TestFailurePolicySet:
    """Test cases for FailurePolicySet functionality."""

    def test_empty_policy_set(self):
        """Test empty failure policy set."""
        fps = FailurePolicySet()
        assert len(fps.policies) == 0
        assert fps.get_default_policy() is None
        assert fps.get_all_policies() == []

    def test_add_and_get_policy(self):
        """Test adding and retrieving policies."""
        fps = FailurePolicySet()
        policy = FailurePolicy(rules=[])

        fps.add("test_policy", policy)
        assert len(fps.policies) == 1
        assert fps.get_policy("test_policy") is policy

    def test_get_nonexistent_policy(self):
        """Test getting a policy that doesn't exist."""
        fps = FailurePolicySet()
        with pytest.raises(KeyError):
            fps.get_policy("nonexistent")

    def test_default_policy_explicit(self):
        """Test explicit default policy."""
        fps = FailurePolicySet()
        default_policy = FailurePolicy(rules=[])
        other_policy = FailurePolicy(rules=[])

        fps.add("default", default_policy)
        fps.add("other", other_policy)

        assert fps.get_default_policy() is default_policy

    def test_default_policy_single(self):
        """Test default policy when only one policy exists."""
        fps = FailurePolicySet()
        policy = FailurePolicy(rules=[])

        fps.add("only_one", policy)
        assert fps.get_default_policy() is policy

    def test_default_policy_multiple_no_default(self):
        """Test default policy with multiple policies but no 'default' key."""
        fps = FailurePolicySet()
        policy1 = FailurePolicy(rules=[])
        policy2 = FailurePolicy(rules=[])

        fps.add("policy1", policy1)
        fps.add("policy2", policy2)

        with pytest.raises(ValueError) as exc_info:
            fps.get_default_policy()

        assert "Multiple failure policies exist" in str(exc_info.value)
        assert "no 'default' policy" in str(exc_info.value)

    def test_get_all_policies(self):
        """Test getting all policies."""
        fps = FailurePolicySet()
        policy1 = FailurePolicy(rules=[])
        policy2 = FailurePolicy(rules=[])

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
        rule = FailureRule(entity_scope="node", rule_type="choice", count=1)
        policy = FailurePolicy(
            rules=[rule],
            attrs={"name": "test_policy", "description": "Test policy"},
            fail_risk_groups=True,
            use_cache=False,
        )

        fps.add("test", policy)

        result = fps.to_dict()

        assert "test" in result
        assert "rules" in result["test"]
        assert "attrs" in result["test"]
        assert result["test"]["fail_risk_groups"] is True
        assert result["test"]["use_cache"] is False
        assert len(result["test"]["rules"]) == 1

        # Check rule serialization
        rule_dict = result["test"]["rules"][0]
        assert rule_dict["entity_scope"] == "node"
        assert rule_dict["rule_type"] == "choice"
        assert rule_dict["count"] == 1

    def test_to_dict_multiple_policies(self):
        """Test serialization with multiple policies."""
        fps = FailurePolicySet()

        policy1 = FailurePolicy(rules=[], attrs={"name": "policy1"})
        policy2 = FailurePolicy(rules=[], attrs={"name": "policy2"})

        fps.add("first", policy1)
        fps.add("second", policy2)

        result = fps.to_dict()

        assert len(result) == 2
        assert "first" in result
        assert "second" in result
        assert result["first"]["attrs"]["name"] == "policy1"
        assert result["second"]["attrs"]["name"] == "policy2"
