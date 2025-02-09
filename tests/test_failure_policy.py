import pytest
from unittest.mock import patch

from ngraph.failure_policy import (
    FailurePolicy,
    FailureRule,
    FailureCondition,
    _evaluate_condition,
)


def test_empty_policy_no_failures():
    """
    Verify that if no rules are present, no entities fail.
    """
    policy = FailurePolicy(rules=[])

    # Suppose we have 2 nodes, 1 link
    nodes = {
        "N1": {"type": "node", "capacity": 100},
        "N2": {"type": "node", "capacity": 200},
    }
    links = {
        "N1-N2-abc123": {"type": "link", "capacity": 50},
    }

    failed = policy.apply_failures(nodes, links)
    assert failed == [], "No rules => no entities fail."


def test_single_rule_all_matched():
    """
    If we have a rule that matches all entities and selects 'all',
    then everything fails.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="!=", value="")],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"N1": {"type": "node"}, "N2": {"type": "node"}}
    links = {
        "L1": {"type": "link"},
        "L2": {"type": "link"},
    }

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N2", "L1", "L2"}


def test_single_rule_choice():
    """
    Test rule_type='choice': it picks exactly 'count' entities from the matched set.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="and",
        rule_type="choice",
        count=2,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "SEA": {"type": "node", "capacity": 100},
        "SFO": {"type": "node", "capacity": 200},
        "DEN": {"type": "node", "capacity": 300},
    }
    links = {
        "SEA-SFO-xxx": {"type": "link", "capacity": 400},
    }

    with patch("ngraph.failure_policy.sample", return_value=["SEA", "DEN"]):
        failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"SEA", "DEN"}


@patch("ngraph.failure_policy.random")
def test_single_rule_random(mock_random):
    """
    For rule_type='random', each matched entity is selected if random() < probability.
    We'll mock out random() to test.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="link")],
        logic="and",
        rule_type="random",
        probability=0.5,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "SEA": {"type": "node"},
        "SFO": {"type": "node"},
    }
    links = {
        "L1": {"type": "link", "capacity": 100},
        "L2": {"type": "link", "capacity": 100},
        "L3": {"type": "link", "capacity": 100},
    }

    mock_random.side_effect = [0.4, 0.6, 0.3]
    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"L1", "L3"}, "Should fail those where random() < 0.5"


def test_operator_conditions():
    """
    Check that <, != conditions evaluate correctly in 'and' logic.
    (We also have coverage for ==, > in other tests.)
    """
    conditions = [
        FailureCondition(attr="capacity", operator="<", value=300),
        FailureCondition(attr="region", operator="!=", value="east"),
    ]
    rule = FailureRule(conditions=conditions, logic="and", rule_type="all")
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"type": "node", "capacity": 100, "region": "west"},  # matches
        "N2": {"type": "node", "capacity": 100, "region": "east"},  # fails !=
        "N3": {"type": "node", "capacity": 300, "region": "west"},  # fails <
    }
    links = {
        "L1": {"type": "link", "capacity": 200, "region": "east"},  # fails !=
    }

    failed = policy.apply_failures(nodes, links)
    assert failed == ["N1"]


def test_logic_or():
    """
    Check 'or' logic: an entity is matched if it satisfies at least one condition (>150 or region=east).
    """
    conditions = [
        FailureCondition(attr="capacity", operator=">", value=150),
        FailureCondition(attr="region", operator="==", value="east"),
    ]
    rule = FailureRule(conditions=conditions, logic="or", rule_type="all")
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"type": "node", "capacity": 100, "region": "west"},  # fails both
        "N2": {
            "type": "node",
            "capacity": 200,
            "region": "west",
        },  # passes capacity>150
        "N3": {"type": "node", "capacity": 100, "region": "east"},  # passes region=east
        "N4": {"type": "node", "capacity": 200, "region": "east"},  # passes both
    }
    links = {}
    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N2", "N3", "N4"}


def test_logic_any():
    """
    'any' logic means all entities are selected, ignoring conditions.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="capacity", operator="==", value=-999)],
        logic="any",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"N1": {"type": "node"}, "N2": {"type": "node"}}
    links = {"L1": {"type": "link"}, "L2": {"type": "link"}}

    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N2", "L1", "L2"}


def test_multiple_rules_union():
    """
    If multiple rules exist, the final set of failed entities is the union
    of each rule's selection.
    """
    rule1 = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="and",
        rule_type="all",
    )
    rule2 = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="link")],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[rule1, rule2])

    nodes = {"N1": {"type": "node"}, "N2": {"type": "node"}}
    links = {"L1": {"type": "link"}, "L2": {"type": "link"}}

    with patch("ngraph.failure_policy.sample", return_value=["L1"]):
        failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"N1", "N2", "L1"}


def test_unsupported_logic():
    """
    Ensure that if a rule specifies an unsupported logic string,
    _evaluate_conditions() raises ValueError.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="UNSUPPORTED",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"A": {"type": "node"}}
    links = {}
    with pytest.raises(ValueError, match="Unsupported logic: UNSUPPORTED"):
        policy.apply_failures(nodes, links)


def test_unsupported_rule_type():
    """
    Ensure that if a rule has an unknown rule_type,
    _select_entities() raises ValueError.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="and",
        rule_type="UNKNOWN",
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"A": {"type": "node"}}
    links = {}
    with pytest.raises(ValueError, match="Unsupported rule_type: UNKNOWN"):
        policy.apply_failures(nodes, links)


def test_unsupported_operator():
    """
    If a condition has an unknown operator, _evaluate_condition() raises ValueError.
    """
    cond = FailureCondition(attr="capacity", operator="??", value=100)
    with pytest.raises(ValueError, match="Unsupported operator: "):
        _evaluate_condition({"capacity": 100}, cond)


def test_no_conditions_with_non_any_logic():
    """
    If logic is not 'any' but conditions is empty,
    we expect _evaluate_conditions() to return False.
    """
    rule = FailureRule(conditions=[], logic="and", rule_type="all")
    policy = FailurePolicy(rules=[rule])

    nodes = {"N1": {"type": "node"}}
    links = {}
    failed = policy.apply_failures(nodes, links)
    assert failed == [], "No conditions => no match => no failures."


def test_choice_larger_count_than_matched():
    """
    If rule.count > number of matched entities, we pick all matched.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="and",
        rule_type="choice",
        count=10,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"A": {"type": "node"}, "B": {"type": "node"}}
    links = {"L1": {"type": "link"}}
    failed = policy.apply_failures(nodes, links)
    assert set(failed) == {"A", "B"}


def test_choice_zero_count():
    """
    If rule.count=0, we select none from the matched entities.
    """
    rule = FailureRule(
        conditions=[FailureCondition(attr="type", operator="==", value="node")],
        logic="and",
        rule_type="choice",
        count=0,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {"A": {"type": "node"}, "B": {"type": "node"}, "C": {"type": "node"}}
    links = {}
    failed = policy.apply_failures(nodes, links)
    assert failed == [], "count=0 => no entities chosen."


def test_operator_condition_le_ge():
    """
    Verify that the '<=' and '>=' operators in _evaluate_condition are correctly handled.
    """
    cond_le = FailureCondition(attr="capacity", operator="<=", value=100)
    cond_ge = FailureCondition(attr="capacity", operator=">=", value=100)

    # Entity with capacity=100 => passes both <=100 and >=100
    e1 = {"capacity": 100}
    assert _evaluate_condition(e1, cond_le) is True
    assert _evaluate_condition(e1, cond_ge) is True

    # capacity=90 => pass <=100, fail >=100
    e2 = {"capacity": 90}
    assert _evaluate_condition(e2, cond_le) is True
    assert _evaluate_condition(e2, cond_ge) is False

    # capacity=110 => fail <=100, pass >=100
    e3 = {"capacity": 110}
    assert _evaluate_condition(e3, cond_le) is False
    assert _evaluate_condition(e3, cond_ge) is True
