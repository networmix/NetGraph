import pytest
from unittest.mock import patch

from ngraph.failure_policy import (
    FailurePolicy,
    FailureRule,
    FailureCondition,
    _evaluate_condition,
)


def test_node_scope_all():
    """Rule with entity_scope='node' and rule_type='all' => fails all matched nodes."""
    rule = FailureRule(
        entity_scope="node",
        conditions=[FailureCondition(attr="capacity", operator=">", value=50)],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule])

    # 3 nodes, 2 links
    nodes = {
        "N1": {"capacity": 100, "region": "west"},
        "N2": {"capacity": 40, "region": "east"},
        "N3": {"capacity": 60},
    }
    links = {
        "L1": {"capacity": 999},
        "L2": {"capacity": 10},
    }

    failed = policy.apply_failures(nodes, links)
    # Should fail nodes with capacity>50 => N1(100), N3(60)
    # Does not consider links at all
    assert set(failed) == {"N1", "N3"}


def test_link_scope_choice():
    """Rule with entity_scope='link' => only matches links, ignoring nodes."""
    rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="capacity", operator="==", value=100)],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"capacity": 100},
        "N2": {"capacity": 100},
    }
    links = {
        "L1": {"capacity": 100, "risk_groups": ["RG1"]},
        "L2": {"capacity": 100},
        "L3": {"capacity": 50},
    }

    with patch("ngraph.failure_policy.sample", return_value=["L2"]):
        failed = policy.apply_failures(nodes, links)
    # Matches L1, L2 (capacity=100), picks exactly 1 => "L2"
    assert set(failed) == {"L2"}


def test_risk_group_scope_random():
    """
    Rule with entity_scope='risk_group' => matches risk groups by cost>100 and selects
    each match with probability=0.5. We mock random() calls so the first match is picked,
    the second match is skipped, but the iteration order is not guaranteed. Therefore, we
    only verify that exactly one of the matched RGs is selected.
    """
    rule = FailureRule(
        entity_scope="risk_group",
        conditions=[FailureCondition(attr="cost", operator=">", value=100)],
        logic="and",
        rule_type="random",
        probability=0.5,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {}
    links = {}
    risk_groups = {
        "RG1": {"name": "RG1", "cost": 200},
        "RG2": {"name": "RG2", "cost": 50},
        "RG3": {"name": "RG3", "cost": 300},
    }

    # RG1 and RG3 match; RG2 does not
    # We'll mock random => [0.4, 0.6] so that one match is picked (0.4 < 0.5)
    # and the other is skipped (0.6 >= 0.5). The set iteration order is not guaranteed,
    # so we only check that exactly 1 RG is chosen, and it must be from RG1/RG3.
    with patch("ngraph.failure_policy.random") as mock_random:
        mock_random.side_effect = [0.4, 0.6]
        failed = policy.apply_failures(nodes, links, risk_groups)

    # Exactly one should fail, and it must be one of the two matched.
    assert len(failed) == 1
    assert set(failed).issubset({"RG1", "RG3"})


def test_multi_rule_union():
    """
    Two rules => union of results: one rule fails certain nodes, the other fails certain links.
    """
    r1 = FailureRule(
        entity_scope="node",
        conditions=[FailureCondition(attr="capacity", operator=">", value=100)],
        logic="and",
        rule_type="all",
    )
    r2 = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="cost", operator="==", value=9)],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[r1, r2])

    nodes = {
        "N1": {"capacity": 50},
        "N2": {"capacity": 120},  # fails rule1
    }
    links = {
        "L1": {"cost": 9},  # matches rule2
        "L2": {"cost": 9},  # matches rule2
        "L3": {"cost": 7},
    }
    with patch("ngraph.failure_policy.sample", return_value=["L1"]):
        failed = policy.apply_failures(nodes, links)
    # fails N2 from rule1, fails L1 from rule2 => union
    assert set(failed) == {"N2", "L1"}


def test_fail_shared_risk_groups():
    """
    If fail_shared_risk_groups=True, failing any node/link also fails
    all node/links that share a risk group with it.
    """
    rule = FailureRule(
        entity_scope="link",
        conditions=[FailureCondition(attr="capacity", operator=">", value=100)],
        logic="and",
        rule_type="choice",
        count=1,
    )
    # Only "L2" has capacity>100 => it will definitely match
    # We pick exactly 1 => "L2"
    policy = FailurePolicy(
        rules=[rule],
        fail_shared_risk_groups=True,
    )

    nodes = {
        "N1": {"capacity": 999, "risk_groups": ["RGalpha"]},  # not matched by link rule
        "N2": {"capacity": 10, "risk_groups": ["RGalpha"]},
    }
    links = {
        "L1": {"capacity": 100, "risk_groups": ["RGbeta"]},
        "L2": {"capacity": 300, "risk_groups": ["RGalpha"]},  # matched
        "L3": {"capacity": 80, "risk_groups": ["RGalpha"]},
        "L4": {"capacity": 500, "risk_groups": ["RGgamma"]},
    }

    with patch("ngraph.failure_policy.sample", return_value=["L2"]):
        failed = policy.apply_failures(nodes, links)
    # L2 fails => shares risk_groups "RGalpha" => that includes N1, N2, L3
    # so they all fail
    # L4 is not in RGalpha => remains unaffected
    assert set(failed) == {"L2", "N1", "N2", "L3"}


def test_fail_risk_group_children():
    """
    If fail_risk_group_children=True, failing a risk group also fails
    its children recursively.
    """
    # We'll fail any RG with cost>=200
    rule = FailureRule(
        entity_scope="risk_group",
        conditions=[FailureCondition(attr="cost", operator=">=", value=200)],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(
        rules=[rule],
        fail_risk_group_children=True,
    )

    rgs = {
        "TopRG": {
            "name": "TopRG",
            "cost": 250,
            "children": [
                {"name": "SubRG1", "cost": 100, "children": []},
                {"name": "SubRG2", "cost": 300, "children": []},
            ],
        },
        "OtherRG": {
            "name": "OtherRG",
            "cost": 50,
            "children": [],
        },
        "SubRG1": {
            "name": "SubRG1",
            "cost": 100,
            "children": [],
        },
        "SubRG2": {
            "name": "SubRG2",
            "cost": 300,
            "children": [],
        },
    }
    nodes = {}
    links = {}

    failed = policy.apply_failures(nodes, links, rgs)
    # "TopRG" cost=250 => fails => also fails children SubRG1, SubRG2
    # "SubRG2" cost=300 => also matches rule => but anyway it's included
    # "OtherRG" is unaffected
    assert set(failed) == {"TopRG", "SubRG1", "SubRG2"}


def test_use_cache():
    """
    Demonstrate that if use_cache=True, repeated calls do not re-match
    conditions. We'll just check that the second call returns the same
    result and that we've only used matching logic once.
    """
    rule = FailureRule(
        entity_scope="node",
        conditions=[FailureCondition(attr="capacity", operator=">", value=50)],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule], use_cache=True)

    nodes = {
        "N1": {"capacity": 100},
        "N2": {"capacity": 40},
    }
    links = {}

    first_fail = policy.apply_failures(nodes, links)
    assert set(first_fail) == {"N1"}
    # Clear the node capacity for N1 => but we do NOT clear the cache
    nodes["N1"]["capacity"] = 10

    second_fail = policy.apply_failures(nodes, links)
    # Because of caching, it returns the same "failed" set => ignoring the updated capacity
    assert set(second_fail) == {"N1"}, "Cache used => no re-check of conditions"

    # If we want the new matching, we must clear the cache
    policy._match_cache.clear()
    third_fail = policy.apply_failures(nodes, links)
    # Now N1 capacity=10 => does not match capacity>50 => no failures
    assert third_fail == []


def test_cache_disabled():
    """
    If use_cache=False, each call re-checks conditions => we see updated results.
    """
    rule = FailureRule(
        entity_scope="node",
        conditions=[FailureCondition(attr="capacity", operator=">", value=50)],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule], use_cache=False)

    nodes = {
        "N1": {"capacity": 100},
        "N2": {"capacity": 40},
    }
    links = {}

    first_fail = policy.apply_failures(nodes, links)
    assert set(first_fail) == {"N1"}

    # Now reduce capacity => we re-check => no longer fails
    nodes["N1"]["capacity"] = 10
    second_fail = policy.apply_failures(nodes, links)
    assert set(second_fail) == set()
