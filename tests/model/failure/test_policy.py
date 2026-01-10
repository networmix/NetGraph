from unittest.mock import patch

import pytest

from ngraph.dsl.selectors.schema import Condition
from ngraph.model.failure.policy import (
    FailurePolicy,
    FailureRule,
)


def _single_mode_policy(rule: FailureRule, **kwargs) -> FailurePolicy:
    from ngraph.model.failure.policy import FailureMode

    return FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])], **kwargs)


def test_failure_rule_invalid_probability():
    """Test FailureRule validation for invalid probability values."""
    # Test probability > 1.0
    with pytest.raises(ValueError, match="probability=1.5 must be within \\[0,1\\]"):
        FailureRule(
            scope="node",
            conditions=[Condition(attr="type", op="==", value="router")],
            logic="and",
            mode="random",
            probability=1.5,
        )

    # Test probability < 0.0
    with pytest.raises(ValueError, match="probability=-0.1 must be within \\[0,1\\]"):
        FailureRule(
            scope="node",
            conditions=[Condition(attr="type", op="==", value="router")],
            logic="and",
            mode="random",
            probability=-0.1,
        )


def test_failure_policy_evaluate_conditions_or_logic():
    """Test condition evaluation with 'or' logic via shared evaluate_conditions."""
    from ngraph.dsl.selectors import evaluate_conditions

    conditions = [
        Condition(attr="vendor", op="==", value="cisco"),
        Condition(attr="location", op="==", value="dallas"),
    ]

    # Should pass if either condition is true
    attrs1 = {"vendor": "cisco", "location": "houston"}  # First condition true
    assert evaluate_conditions(attrs1, conditions, "or") is True

    attrs2 = {"vendor": "juniper", "location": "dallas"}  # Second condition true
    assert evaluate_conditions(attrs2, conditions, "or") is True

    attrs3 = {"vendor": "cisco", "location": "dallas"}  # Both conditions true
    assert evaluate_conditions(attrs3, conditions, "or") is True

    attrs4 = {"vendor": "juniper", "location": "houston"}  # Neither condition true
    assert evaluate_conditions(attrs4, conditions, "or") is False


def test_failure_policy_evaluate_conditions_invalid_logic():
    """Test condition evaluation with invalid logic via shared evaluate_conditions."""
    from ngraph.dsl.selectors import evaluate_conditions

    conditions = [Condition(attr="vendor", op="==", value="cisco")]
    attrs = {"vendor": "cisco"}

    with pytest.raises(ValueError, match="Unsupported logic: invalid"):
        evaluate_conditions(attrs, conditions, "invalid")


def test_node_scope_all():
    """Rule with scope='node' and mode='all' => fails all matched nodes."""
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="==", value="cisco")],
        logic="and",
        mode="all",
    )
    policy = _single_mode_policy(rule)

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
    """Rule with scope='node' and mode='random' => random node failure."""
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="==", value="cisco")],
        logic="and",
        mode="random",
        probability=0.5,
    )
    policy = _single_mode_policy(rule)

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
    """Rule with scope='node' and mode='choice' => limited node failures."""
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="==", value="cisco")],
        logic="and",
        mode="choice",
        count=1,
    )
    policy = _single_mode_policy(rule)

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
    """Rule with scope='link' and mode='all' => fails all matched links."""
    rule = FailureRule(
        scope="link",
        conditions=[Condition(attr="link_type", op="==", value="fiber")],
        logic="and",
        mode="all",
    )
    policy = _single_mode_policy(rule)

    nodes = {"N1": {}, "N2": {}}
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
        "L3": {"link_type": "fiber"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"L1", "L3"}


def test_link_scope_random():
    """Rule with scope='link' and mode='random' => random link failure."""
    rule = FailureRule(
        scope="link",
        conditions=[Condition(attr="link_type", op="==", value="fiber")],
        logic="and",
        mode="random",
        probability=0.4,
    )
    policy = _single_mode_policy(rule)

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
    """Rule with scope='link' and mode='choice' => limited link failures."""
    rule = FailureRule(
        scope="link",
        conditions=[Condition(attr="link_type", op="==", value="fiber")],
        logic="and",
        mode="choice",
        count=1,
    )
    policy = _single_mode_policy(rule)

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
        scope="node",
        conditions=[
            Condition(attr="equipment_vendor", op="==", value="cisco"),
            Condition(attr="location", op="==", value="dallas"),
        ],
        logic="and",
        mode="all",
    )
    policy = _single_mode_policy(rule)

    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},
        "N2": {"equipment_vendor": "cisco", "location": "houston"},
        "N3": {"equipment_vendor": "juniper", "location": "dallas"},
        "N4": {"equipment_vendor": "juniper", "location": "houston"},
    }
    links = {}

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1"}


def test_complex_conditions_or_logic():
    """Multiple conditions with 'or' logic."""
    rule = FailureRule(
        scope="node",
        conditions=[
            Condition(attr="equipment_vendor", op="==", value="cisco"),
            Condition(attr="location", op="==", value="critical_site"),
        ],
        logic="or",
        mode="all",
    )
    policy = _single_mode_policy(rule)

    nodes = {
        "N1": {"equipment_vendor": "cisco", "location": "dallas"},
        "N2": {
            "equipment_vendor": "juniper",
            "location": "critical_site",
        },
        "N3": {"equipment_vendor": "juniper", "location": "houston"},
        "N4": {"equipment_vendor": "cisco", "location": "critical_site"},
    }
    links = {}

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N2", "N4"}


def test_multiple_rules():
    """Policy with multiple rules affecting different entities."""
    node_rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="==", value="cisco")],
        logic="and",
        mode="all",
    )
    link_rule = FailureRule(
        scope="link",
        conditions=[Condition(attr="link_type", op="==", value="fiber")],
        logic="and",
        mode="all",
    )
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[node_rule, link_rule])]
    )

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
    }
    links = {
        "L1": {"link_type": "fiber"},
        "L2": {"link_type": "radio_relay"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "L1"}


def test_condition_operators():
    """Test various condition operators."""
    # Test '!=' operator
    rule_neq = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="!=", value="cisco")],
        logic="and",
        mode="all",
    )
    policy_neq = _single_mode_policy(rule_neq)

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
        "N3": {"equipment_vendor": "arista"},
    }

    failed = policy_neq.apply_failures(nodes, {})
    assert set(failed) == {"N2", "N3"}

    # Test missing attribute
    rule_missing = FailureRule(
        scope="node",
        conditions=[Condition(attr="missing_attr", op="==", value="some_value")],
        logic="and",
        mode="all",
    )
    policy_missing = _single_mode_policy(rule_missing)

    nodes = {
        "N1": {"vendor": "cisco"},
        "N2": {"vendor": "juniper"},
    }

    failed = policy_missing.apply_failures(nodes, {})
    assert failed == []


def test_serialization():
    """Test policy serialization."""
    condition = Condition(attr="equipment_vendor", op="==", value="cisco")
    rule = FailureRule(
        scope="node",
        conditions=[condition],
        logic="and",
        mode="random",
        probability=0.2,
        count=3,
    )
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

    policy_dict = policy.to_dict()
    assert "modes" in policy_dict and len(policy_dict["modes"]) == 1
    mode_dict = policy_dict["modes"][0]
    assert len(mode_dict["rules"]) == 1

    rule_dict = mode_dict["rules"][0]
    assert rule_dict["scope"] == "node"
    assert rule_dict["logic"] == "and"
    assert rule_dict["mode"] == "random"
    assert rule_dict["probability"] == 0.2
    assert rule_dict["count"] == 3
    assert len(rule_dict["conditions"]) == 1

    condition_dict = rule_dict["conditions"][0]
    assert condition_dict["attr"] == "equipment_vendor"
    assert condition_dict["op"] == "=="
    assert condition_dict["value"] == "cisco"


def test_missing_attributes():
    """Test behavior when entities don't have required attributes."""
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="nonexistent_attr", op="==", value="some_value")],
        logic="and",
        mode="all",
    )
    policy = _single_mode_policy(rule)

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
    }

    failed = policy.apply_failures(nodes, {})
    assert failed == []


def test_empty_policy():
    """Test policy with no rules."""
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[])])

    nodes = {"N1": {"equipment_vendor": "cisco"}}
    links = {"L1": {"link_type": "fiber"}}

    failed = policy.apply_failures(nodes, links)
    assert failed == []


def test_empty_entities():
    """Test policy applied to empty node/link sets."""
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="equipment_vendor", op="==", value="cisco")],
        logic="and",
        mode="all",
    )
    policy = _single_mode_policy(rule)

    failed = policy.apply_failures({}, {})
    assert failed == []
