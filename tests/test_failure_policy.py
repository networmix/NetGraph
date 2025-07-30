from unittest.mock import patch

import pytest

from ngraph.failure_policy import (
    FailureCondition,
    FailurePolicy,
    FailureRule,
)


def test_failure_rule_invalid_probability():
    """Test FailureRule validation for invalid probability values."""
    # Test probability > 1.0
    with pytest.raises(ValueError, match="probability=1.5 must be within \\[0,1\\]"):
        FailureRule(
            entity_scope="node",
            conditions=[FailureCondition(attr="type", operator="==", value="router")],
            logic="and",
            rule_type="random",
            probability=1.5,
        )

    # Test probability < 0.0
    with pytest.raises(ValueError, match="probability=-0.1 must be within \\[0,1\\]"):
        FailureRule(
            entity_scope="node",
            conditions=[FailureCondition(attr="type", operator="==", value="router")],
            logic="and",
            rule_type="random",
            probability=-0.1,
        )


def test_failure_policy_evaluate_conditions_or_logic():
    """Test FailurePolicy._evaluate_conditions with 'or' logic."""
    conditions = [
        FailureCondition(attr="vendor", operator="==", value="cisco"),
        FailureCondition(attr="location", operator="==", value="dallas"),
    ]

    # Should pass if either condition is true
    attrs1 = {"vendor": "cisco", "location": "houston"}  # First condition true
    assert FailurePolicy._evaluate_conditions(attrs1, conditions, "or") is True

    attrs2 = {"vendor": "juniper", "location": "dallas"}  # Second condition true
    assert FailurePolicy._evaluate_conditions(attrs2, conditions, "or") is True

    attrs3 = {"vendor": "cisco", "location": "dallas"}  # Both conditions true
    assert FailurePolicy._evaluate_conditions(attrs3, conditions, "or") is True

    attrs4 = {"vendor": "juniper", "location": "houston"}  # Neither condition true
    assert FailurePolicy._evaluate_conditions(attrs4, conditions, "or") is False


def test_failure_policy_evaluate_conditions_invalid_logic():
    """Test FailurePolicy._evaluate_conditions with invalid logic."""
    conditions = [FailureCondition(attr="vendor", operator="==", value="cisco")]
    attrs = {"vendor": "cisco"}

    with pytest.raises(ValueError, match="Unsupported logic: invalid"):
        FailurePolicy._evaluate_conditions(attrs, conditions, "invalid")


def test_node_scope_all():
    """Rule with entity_scope='node' and rule_type='all' => fails all matched nodes."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    # 3 nodes, 2 links
    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},
        "N2": {"equipment_vendor": "juniper", "location": "houston"},
        "N3": {"equipment_vendor": "cisco"},
    }
    links = {
        "L1": {"link_type": "fiber", "installation": "aerial"},
        "L2": {"link_type": "radio_relay"},
    }
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    # 3 nodes, 2 links
    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},
        "N2": {"equipment_vendor": "juniper", "location": "houston"},
        "N3": {"equipment_vendor": "cisco", "location": "austin"},
    }
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N3"}


def test_node_scope_random():
    """Rule with entity_scope='node' and rule_type='random' => random node failure."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="random",
        probability=0.5,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
        "N3": {"equipment_vendor": "cisco"},
    }
    links = {}

    # Mock random number generation to ensure deterministic results
    with patch("random.random", return_value=0.3):  # < 0.5, so should fail
        failed = policy.apply_failures(nodes, links)
        assert len(failed) == 2  # Both cisco nodes should fail

    with patch("random.random", return_value=0.7):  # > 0.5, so should NOT fail
        failed = policy.apply_failures(nodes, links)
        assert failed == []


def test_node_scope_choice():
    """Rule with entity_scope='node' and rule_type='choice' => limited node failures."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
        "N3": {"equipment_vendor": "cisco"},
    }
    links = {}

    # Mock random selection to be deterministic
    with patch("random.sample", return_value=["N1"]):
        failed = policy.apply_failures(nodes, links)
        assert len(failed) == 1  # Only 1 cisco node should fail
        assert "N1" in failed


def test_link_scope_all():
    """Rule with entity_scope='link' and rule_type='all' => fails all matched links."""
    rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="link_type", operator="==", value="fiber")],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"N1": {}, "N2": {}}
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
        "L3": {"link_type": "fiber"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"L1", "L3"}


def test_link_scope_random():
    """Rule with entity_scope='link' and rule_type='random' => random link failure."""
    rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="link_type", operator="==", value="fiber")],
        logic="and",
        rule_type="random",
        probability=0.4,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {}
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
        "L3": {"link_type": "fiber"},
    }

    # Mock random to ensure deterministic test
    with patch("random.random", return_value=0.3):  # < 0.4, so should fail
        failed = policy.apply_failures(nodes, links)
        assert len(failed) == 2  # Both fiber links should fail

    with patch("random.random", return_value=0.6):  # > 0.4, so should NOT fail
        failed = policy.apply_failures(nodes, links)
        assert failed == []


def test_link_scope_choice():
    """Rule with entity_scope='link' and rule_type='choice' => limited link failures."""
    rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="link_type", operator="==", value="fiber")],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {}
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
        "L3": {"link_type": "fiber"},
    }

    # Mock random selection to be deterministic
    with patch("random.sample", return_value=["L3"]):
        failed = policy.apply_failures(nodes, links)
        assert len(failed) == 1
        assert "L3" in failed


def test_complex_conditions_and_logic():
    """Multiple conditions with 'and' logic."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco"),
            FailureCondition(attr="location", operator="==", value="dallas"),
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},  # Matches both
        "N2": {"equipment_vendor": "cisco", "location": "houston"},  # Only vendor
        "N3": {"equipment_vendor": "juniper", "location": "dallas"},  # Only location
        "N4": {"equipment_vendor": "juniper", "location": "houston"},  # Neither
    }
    links = {}

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1"}  # Only node matching BOTH conditions


def test_complex_conditions_or_logic():
    """Multiple conditions with 'or' logic."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco"),
            FailureCondition(attr="location", operator="==", value="critical_site"),
        ],
        logic="or",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},  # Vendor match
        "N2": {
            "equipment_vendor": "juniper",
            "location": "critical_site",
        },  # Location match
        "N3": {"equipment_vendor": "juniper", "location": "houston"},  # No match
        "N4": {"equipment_vendor": "cisco", "location": "critical_site"},  # Both match
    }
    links = {}

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N2", "N4"}  # Nodes matching EITHER condition


def test_multiple_rules():
    """Policy with multiple rules affecting different entities."""
    node_rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    link_rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="link_type", operator="==", value="fiber")],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[node_rule, link_rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
    }
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "L1"}  # From both rules


def test_condition_operators():
    """Test various condition operators."""
    # Test '!=' operator
    rule_neq = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="!=", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    policy_neq = FailurePolicy(rules=[rule_neq])

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
        "N3": {"equipment_vendor": "arista"},
    }

    failed = policy_neq.apply_failures(nodes, {})
    assert set(failed) == {"N2", "N3"}  # All non-cisco nodes

    # Test missing attribute
    rule_missing = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="missing_attr", operator="==", value="some_value")
        ],
        logic="and",
        rule_type="all",
    )
    policy_missing = FailurePolicy(rules=[rule_missing])

    nodes = {
        "N1": {"vendor": "cisco"},  # No missing_attr
        "N2": {"vendor": "juniper"},  # No missing_attr
    }

    failed = policy_missing.apply_failures(nodes, {})
    assert failed == []  # No nodes should match


def test_serialization():
    """Test policy serialization."""
    condition = FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
    rule = FailureRule(
        entity_scope="node",
        conditions=[condition],
        logic="and",
        rule_type="random",
        probability=0.2,
        count=3,
    )
    policy = FailurePolicy(rules=[rule])

    # Test policy serialization
    policy_dict = policy.to_dict()
    assert len(policy_dict["rules"]) == 1

    # Check the rule was properly serialized
    rule_dict = policy_dict["rules"][0]
    assert rule_dict["entity_scope"] == "node"
    assert rule_dict["logic"] == "and"
    assert rule_dict["rule_type"] == "random"
    assert rule_dict["probability"] == 0.2
    assert rule_dict["count"] == 3
    assert len(rule_dict["conditions"]) == 1

    # Check the condition was properly serialized
    condition_dict = rule_dict["conditions"][0]
    assert condition_dict["attr"] == "equipment_vendor"
    assert condition_dict["operator"] == "=="
    assert condition_dict["value"] == "cisco"


def test_missing_attributes():
    """Test behavior when entities don't have required attributes."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="nonexistent_attr", operator="==", value="some_value")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"equipment_vendor": "cisco"},  # Missing 'nonexistent_attr'
        "N2": {"equipment_vendor": "juniper"},  # Missing 'nonexistent_attr'
    }

    # Should not fail any nodes since attribute doesn't exist
    failed = policy.apply_failures(nodes, {})
    assert failed == []


def test_empty_policy():
    """Test policy with no rules."""
    policy = FailurePolicy(rules=[])

    nodes = {"N1": {"equipment_vendor": "cisco"}}
    links = {"L1": {"link_type": "fiber"}}

    failed = policy.apply_failures(nodes, links)
    assert failed == []


def test_empty_entities():
    """Test policy applied to empty node/link sets."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    failed = policy.apply_failures({}, {})
    assert failed == []
