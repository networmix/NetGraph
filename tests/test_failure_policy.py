from unittest.mock import patch

from ngraph.failure_policy import (
    FailureCondition,
    FailurePolicy,
    FailureRule,
)


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
    # Should fail nodes with cisco equipment => N1, N3
    # Does not consider links at all
    assert set(failed) == {"N1", "N3"}


def test_link_scope_choice():
    """Rule with entity_scope='link' => only matches links, ignoring nodes."""
    rule = FailureRule(
        entity_scope="link",
        conditions=[
            FailureCondition(attr="installation", operator="==", value="underground")
        ],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {
        "N1": {"installation": "underground"},  # Should be ignored (wrong entity type)
        "N2": {"equipment_vendor": "cisco"},
    }
    links = {
        "L1": {
            "installation": "underground",
            "link_type": "fiber",
            "risk_groups": ["RG1"],
        },
        "L2": {"installation": "underground", "link_type": "fiber"},
        "L3": {"installation": "aerial", "link_type": "fiber"},
    }

    with patch("ngraph.failure_policy._random.sample", return_value=["L2"]):
        failed = policy.apply_failures(nodes, links)
    # Matches L1, L2 (underground installation), picks exactly 1 => "L2"
    assert set(failed) == {"L2"}


def test_risk_group_scope_random():
    """
    Rule with entity_scope='risk_group' => matches risk groups by criticality_level='high' and selects
    each match with probability=0.5. We mock random() calls so the first match is picked,
    the second match is skipped, but the iteration order is not guaranteed. Therefore, we
    only verify that exactly one of the matched RGs is selected.
    """
    rule = FailureRule(
        entity_scope="risk_group",
        conditions=[
            FailureCondition(attr="criticality_level", operator="==", value="high")
        ],
        logic="and",
        rule_type="random",
        probability=0.5,
    )
    policy = FailurePolicy(rules=[rule])

    nodes = {}
    links = {}
    risk_groups = {
        "DataCenter_Primary": {
            "name": "DataCenter_Primary",
            "criticality_level": "high",
        },
        "DataCenter_Backup": {
            "name": "DataCenter_Backup",
            "criticality_level": "medium",
        },
        "Substation_Main": {"name": "Substation_Main", "criticality_level": "high"},
    }

    # DataCenter_Primary and Substation_Main match; DataCenter_Backup does not
    # We'll mock random => [0.4, 0.6] so that one match is picked (0.4 < 0.5)
    # and the other is skipped (0.6 >= 0.5). The set iteration order is not guaranteed,
    # so we only check that exactly 1 RG is chosen, and it must be from the matched set.
    with patch("ngraph.failure_policy._random.random") as mock_random:
        mock_random.side_effect = [0.4, 0.6]
        failed = policy.apply_failures(nodes, links, risk_groups)

    # Exactly one should fail, and it must be one of the two matched.
    assert len(failed) == 1
    assert set(failed).issubset({"DataCenter_Primary", "Substation_Main"})


def test_multi_rule_union():
    """
    Two rules => union of results: one rule fails certain nodes, the other fails certain links.
    """
    r1 = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="power_source", operator="==", value="grid_only")
        ],
        logic="and",
        rule_type="all",
    )
    r2 = FailureRule(
        entity_scope="link",
        conditions=[
            FailureCondition(attr="installation", operator="==", value="aerial")
        ],
        logic="and",
        rule_type="choice",
        count=1,
    )
    policy = FailurePolicy(rules=[r1, r2])

    nodes = {
        "N1": {"power_source": "battery_backup"},
        "N2": {"power_source": "grid_only"},  # fails rule1
    }
    links = {
        "L1": {"installation": "aerial"},  # matches rule2
        "L2": {"installation": "aerial"},  # matches rule2
        "L3": {"installation": "underground"},
    }
    with patch("ngraph.failure_policy._random.sample", return_value=["L1"]):
        failed = policy.apply_failures(nodes, links)
    # fails N2 from rule1, fails L1 from rule2 => union
    assert set(failed) == {"N2", "L1"}


def test_fail_risk_groups():
    """
    If fail_risk_groups=True, failing any node/link also fails
    all node/links that share a risk group with it.
    """
    rule = FailureRule(
        entity_scope="link",
        conditions=[
            FailureCondition(attr="installation", operator="==", value="underground")
        ],
        logic="and",
        rule_type="choice",
        count=1,
    )
    # Only "L2" has underground installation => it will definitely match
    # We pick exactly 1 => "L2"
    policy = FailurePolicy(
        rules=[rule],
        fail_risk_groups=True,
    )

    nodes = {
        "N1": {
            "equipment_vendor": "cisco",
            "risk_groups": ["PowerGrid_Texas"],
        },  # not matched by link rule
        "N2": {"equipment_vendor": "juniper", "risk_groups": ["PowerGrid_Texas"]},
    }
    links = {
        "L1": {
            "installation": "aerial",
            "link_type": "fiber",
            "risk_groups": ["Conduit_South"],
        },
        "L2": {
            "installation": "underground",
            "link_type": "fiber",
            "risk_groups": ["PowerGrid_Texas"],
        },  # matched
        "L3": {
            "installation": "opgw",
            "link_type": "fiber",
            "risk_groups": ["PowerGrid_Texas"],
        },
        "L4": {
            "installation": "aerial",
            "link_type": "fiber",
            "risk_groups": ["Conduit_North"],
        },
    }

    with patch("ngraph.failure_policy._random.sample", return_value=["L2"]):
        failed = policy.apply_failures(nodes, links)
    # L2 fails => shares risk_groups "PowerGrid_Texas" => that includes N1, N2, L3
    # so they all fail
    # L4 is not in PowerGrid_Texas => remains unaffected
    assert set(failed) == {"L2", "N1", "N2", "L3"}


def test_fail_risk_group_children():
    """
    If fail_risk_group_children=True, failing a risk group also fails
    its children recursively.
    """
    # We'll fail any RG with facility_type='datacenter'
    rule = FailureRule(
        entity_scope="risk_group",
        conditions=[
            FailureCondition(attr="facility_type", operator="==", value="datacenter")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(
        rules=[rule],
        fail_risk_group_children=True,
    )

    rgs = {
        "Campus_Dallas": {
            "name": "Campus_Dallas",
            "facility_type": "datacenter",
            "children": [
                {"name": "Building_A", "facility_type": "building", "children": []},
                {"name": "Building_B", "facility_type": "building", "children": []},
            ],
        },
        "Office_Austin": {
            "name": "Office_Austin",
            "facility_type": "office",
            "children": [],
        },
        "Building_A": {
            "name": "Building_A",
            "facility_type": "building",
            "children": [],
        },
        "Building_B": {
            "name": "Building_B",
            "facility_type": "building",
            "children": [],
        },
    }
    nodes = {}
    links = {}

    failed = policy.apply_failures(nodes, links, rgs)
    # "Campus_Dallas" is datacenter => fails => also fails children Building_A, Building_B
    # "Office_Austin" is not a datacenter => unaffected
    assert set(failed) == {"Campus_Dallas", "Building_A", "Building_B"}


def test_use_cache():
    """
    Demonstrate that if use_cache=True, repeated calls do not re-match
    conditions. We'll just check that the second call returns the same
    result and that we've only used matching logic once.
    """
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="power_source", operator="==", value="grid_only")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule], use_cache=True)

    nodes = {
        "N1": {"power_source": "grid_only"},
        "N2": {"power_source": "battery_backup"},
    }
    links = {}

    first_fail = policy.apply_failures(nodes, links)
    assert set(first_fail) == {"N1"}
    # Change the node power source => but we do NOT clear the cache
    nodes["N1"]["power_source"] = "battery_backup"

    second_fail = policy.apply_failures(nodes, links)
    # Because of caching, it returns the same "failed" set => ignoring the updated power source
    assert set(second_fail) == {"N1"}, "Cache used => no re-check of conditions"

    # If we want the new matching, we must clear the cache
    policy._match_cache.clear()
    third_fail = policy.apply_failures(nodes, links)
    # Now N1 power_source='battery_backup' => does not match grid_only => no failures
    assert third_fail == []


def test_cache_disabled():
    """
    If use_cache=False, each call re-checks conditions => we see updated results.
    """
    rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="equipment_vendor", operator="==", value="cisco")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[rule], use_cache=False)

    nodes = {
        "N1": {"equipment_vendor": "cisco"},
        "N2": {"equipment_vendor": "juniper"},
    }
    links = {}

    first_fail = policy.apply_failures(nodes, links)
    assert set(first_fail) == {"N1"}

    # Now change equipment vendor => we re-check => no longer fails
    nodes["N1"]["equipment_vendor"] = "juniper"
    second_fail = policy.apply_failures(nodes, links)
    assert set(second_fail) == set()


def test_docstring_yaml_example_policy():
    """Test the exact policy structure from the FailurePolicy docstring YAML example.

    This test validates the Texas grid outage scenario with:
    1. All nodes in Texas electrical grid
    2. Random 40% of underground fiber links in southwest region
    3. Choice of exactly 2 risk groups
    """
    # Create the policy matching the docstring example
    policy = FailurePolicy(
        attrs={
            "name": "Texas Grid Outage Scenario",
            "description": "Regional power grid failure affecting telecom infrastructure",
        },
        fail_risk_groups=True,
        rules=[
            # Rule 1: Fail all nodes in Texas electrical grid
            FailureRule(
                entity_scope="node",
                conditions=[
                    FailureCondition(attr="electric_grid", operator="==", value="texas")
                ],
                logic="and",
                rule_type="all",
            ),
            # Rule 2: Randomly fail 40% of underground fiber links in southwest region
            FailureRule(
                entity_scope="link",
                conditions=[
                    FailureCondition(attr="region", operator="==", value="southwest"),
                    FailureCondition(
                        attr="installation", operator="==", value="underground"
                    ),
                ],
                logic="and",
                rule_type="random",
                probability=0.4,
            ),
            # Rule 3: Choose exactly 2 risk groups to fail
            FailureRule(
                entity_scope="risk_group",
                rule_type="choice",
                count=2,
            ),
        ],
    )

    # Test that policy metadata is correctly set
    assert policy.attrs["name"] == "Texas Grid Outage Scenario"
    assert (
        policy.attrs["description"]
        == "Regional power grid failure affecting telecom infrastructure"
    )
    assert policy.fail_risk_groups is True
    assert len(policy.rules) == 3

    # Verify rule 1 structure
    rule1 = policy.rules[0]
    assert rule1.entity_scope == "node"
    assert len(rule1.conditions) == 1
    assert rule1.conditions[0].attr == "electric_grid"
    assert rule1.conditions[0].operator == "=="
    assert rule1.conditions[0].value == "texas"
    assert rule1.logic == "and"
    assert rule1.rule_type == "all"

    # Verify rule 2 structure
    rule2 = policy.rules[1]
    assert rule2.entity_scope == "link"
    assert len(rule2.conditions) == 2
    assert rule2.conditions[0].attr == "region"
    assert rule2.conditions[0].operator == "=="
    assert rule2.conditions[0].value == "southwest"
    assert rule2.conditions[1].attr == "installation"
    assert rule2.conditions[1].operator == "=="
    assert rule2.conditions[1].value == "underground"
    assert rule2.logic == "and"
    assert rule2.rule_type == "random"
    assert rule2.probability == 0.4

    # Verify rule 3 structure
    rule3 = policy.rules[2]
    assert rule3.entity_scope == "risk_group"
    assert len(rule3.conditions) == 0
    assert rule3.logic == "or"
    assert rule3.rule_type == "choice"
    assert rule3.count == 2


def test_docstring_policy_individual_rules():
    """Test individual rule types from the docstring example to ensure they work."""

    # Test rule 1: All nodes in Texas electrical grid
    texas_grid_rule = FailureRule(
        entity_scope="node",
        conditions=[
            FailureCondition(attr="electric_grid", operator="==", value="texas")
        ],
        logic="and",
        rule_type="all",
    )
    policy = FailurePolicy(rules=[texas_grid_rule])

    nodes = {
        "N1": {"electric_grid": "texas"},  # Should fail
        "N2": {"electric_grid": "california"},  # Should not fail
        "N3": {"electric_grid": "texas"},  # Should fail
        "N4": {"electric_grid": "pjm"},  # Should not fail
    }
    failed = policy.apply_failures(nodes, {})
    assert "N1" in failed
    assert "N2" not in failed
    assert "N3" in failed
    assert "N4" not in failed

    # Test rule 2: Random underground fiber links in southwest region
    underground_link_rule = FailureRule(
        entity_scope="link",
        conditions=[
            FailureCondition(attr="region", operator="==", value="southwest"),
            FailureCondition(attr="installation", operator="==", value="underground"),
        ],
        logic="and",
        rule_type="random",
        probability=0.4,
    )
    policy = FailurePolicy(rules=[underground_link_rule])

    links = {
        "L1": {
            "region": "southwest",
            "installation": "underground",
        },  # Matches conditions
        "L2": {"region": "northeast", "installation": "underground"},  # Wrong region
        "L3": {"region": "southwest", "installation": "opgw"},  # Wrong type
        "L4": {
            "region": "southwest",
            "installation": "underground",
        },  # Matches conditions
        "L5": {"region": "southwest", "installation": "aerial"},  # Wrong type
    }

    # Test with deterministic random values
    with patch("ngraph.failure_policy._random.random") as mock_random:
        # Only L1 and L4 match the conditions, so we need 2 random calls
        mock_random.side_effect = [
            0.3,  # L1 fails (0.3 < 0.4)
            0.5,  # L4 doesn't fail (0.5 > 0.4)
        ]
        failed = policy.apply_failures({}, links)

        # Check which entities matched and were evaluated
        # Since the order might not be deterministic, let's be flexible
        matched_and_failed = {link for link in ["L1", "L4"] if link in failed}
        matched_and_not_failed = {link for link in ["L1", "L4"] if link not in failed}

        # We should have exactly one failed (based on our mock) and one not failed
        assert len(matched_and_failed) == 1, (
            f"Expected 1 failed, got {matched_and_failed}"
        )
        assert len(matched_and_not_failed) == 1, (
            f"Expected 1 not failed, got {matched_and_not_failed}"
        )

        # L2, L3, L5 should never be in failed (don't match conditions)
        assert "L2" not in failed  # Wrong region
        assert "L3" not in failed  # Wrong installation type
        assert "L5" not in failed  # Wrong installation type

    # Test rule 3: Choice of exactly 2 risk groups
    risk_group_rule = FailureRule(
        entity_scope="risk_group",
        rule_type="choice",
        count=2,
    )
    policy = FailurePolicy(rules=[risk_group_rule])

    risk_groups = {
        "RG1": {"name": "RG1"},
        "RG2": {"name": "RG2"},
        "RG3": {"name": "RG3"},
        "RG4": {"name": "RG4"},
    }

    with patch("ngraph.failure_policy._random.sample") as mock_sample:
        mock_sample.return_value = ["RG1", "RG3"]
        failed = policy.apply_failures({}, {}, risk_groups)
        assert "RG1" in failed
        assert "RG2" not in failed
        assert "RG3" in failed
        assert "RG4" not in failed

        # Verify sample was called with correct parameters
        mock_sample.assert_called_once()
        call_args, call_kwargs = mock_sample.call_args
        assert set(call_args[0]) == {"RG1", "RG2", "RG3", "RG4"}
        assert call_kwargs.get("k", call_args[1] if len(call_args) > 1 else None) == 2
