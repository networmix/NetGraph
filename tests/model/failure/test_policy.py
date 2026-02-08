import pytest

from ngraph.dsl.selectors.schema import Condition
from ngraph.model.failure.policy import (
    FailureMode,
    FailurePolicy,
    FailureRule,
)


def _single_mode_policy(rule: FailureRule, **kwargs) -> FailurePolicy:
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
    """Rule with scope='node' and mode='random' => seeded random node failure."""
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

    # Same seed must produce identical results (determinism)
    failed1 = policy.apply_failures(nodes, links, seed=42)
    failed2 = policy.apply_failures(nodes, links, seed=42)
    assert failed1 == failed2

    # Only cisco nodes can appear in results (juniper N2 never matched)
    assert all(f in {"N1", "N3"} for f in failed1)

    # Different seeds should eventually produce different results
    results_by_seed = {
        tuple(policy.apply_failures(nodes, links, seed=s)) for s in range(50)
    }
    assert len(results_by_seed) > 1  # Not all identical


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

    # Seeded selection is deterministic and picks exactly 1
    failed = policy.apply_failures(nodes, links, seed=42)
    assert len(failed) == 1
    assert failed[0] in {"N1", "N3"}  # Must be a cisco node

    # Same seed → same result
    assert policy.apply_failures(nodes, links, seed=42) == failed


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
    """Rule with scope='link' and mode='random' => seeded random link failure."""
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

    # Same seed must produce identical results (determinism)
    failed1 = policy.apply_failures(nodes, links, seed=42)
    failed2 = policy.apply_failures(nodes, links, seed=42)
    assert failed1 == failed2

    # Only fiber links can appear (radio_relay L2 never matched)
    assert all(f in {"L1", "L3"} for f in failed1)

    # Different seeds should eventually produce different results
    results_by_seed = {
        tuple(policy.apply_failures(nodes, links, seed=s)) for s in range(50)
    }
    assert len(results_by_seed) > 1


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

    # Seeded selection is deterministic and picks exactly 1
    failed = policy.apply_failures(nodes, links, seed=42)
    assert len(failed) == 1
    assert failed[0] in {"L1", "L3"}  # Must be a fiber link

    # Same seed → same result
    assert policy.apply_failures(nodes, links, seed=42) == failed


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


def test_multi_rule_independence():
    """Multi-rule policies must produce statistically independent selections.

    Verifies the fix for the correlated-seed bug: each rule in a mode
    must draw from the same RNG stream sequentially rather than each
    creating a fresh RNG from the same seed.
    """
    link_rule = FailureRule(scope="link", mode="random", probability=0.5)
    node_rule = FailureRule(scope="node", mode="random", probability=0.5)
    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[link_rule, node_rule])]
    )

    # 20 links and 20 nodes so we get enough samples per entity
    links = {f"L{i:02d}": {} for i in range(20)}
    nodes = {f"N{i:02d}": {} for i in range(20)}

    N = 2000
    # Count how often the *first* link (L00) and *first* node (N00) both fail.
    # Under independence P(both) ≈ 0.5 * 0.5 = 0.25
    # Under the old correlated bug P(both) ≈ 0.5 (draws are identical)
    joint_fail = 0
    link0_fail = 0
    node0_fail = 0

    for trial in range(N):
        failed = set(policy.apply_failures(nodes, links, seed=trial))
        l0 = "L00" in failed
        n0 = "N00" in failed
        if l0:
            link0_fail += 1
        if n0:
            node0_fail += 1
        if l0 and n0:
            joint_fail += 1

    p_link = link0_fail / N
    p_node = node0_fail / N
    p_joint = joint_fail / N
    p_expected_independent = p_link * p_node

    # Joint probability should be close to the product (independent).
    # Allow generous tolerance for finite sample size, but catch the 2x
    # correlation that the old bug produced.
    assert abs(p_joint - p_expected_independent) < 0.06, (
        f"Joint failure rate {p_joint:.4f} deviates too much from independent "
        f"expectation {p_expected_independent:.4f} (p_link={p_link:.4f}, "
        f"p_node={p_node:.4f}). Rules may be correlated."
    )


def test_multi_mode_entity_independence():
    """Entity failure probability must be independent of which mode was selected.

    Verifies the fix for the mode-entity correlation bug: the RNG draw
    that selects the mode must not be the same draw that determines
    entity[0] failure.
    """
    # Two modes with asymmetric weights
    rule_mode0 = FailureRule(scope="node", mode="random", probability=0.3)
    rule_mode1 = FailureRule(scope="node", mode="random", probability=0.3)
    policy = FailurePolicy(
        modes=[
            FailureMode(weight=0.8, rules=[rule_mode0]),
            FailureMode(weight=0.2, rules=[rule_mode1]),
        ]
    )

    nodes = {f"N{i:02d}": {} for i in range(10)}
    links = {}

    N = 5000
    mode0_count = 0
    mode0_n00_fail = 0
    mode1_count = 0
    mode1_n00_fail = 0

    for trial in range(N):
        trace: dict = {}
        failed = set(
            policy.apply_failures(nodes, links, seed=trial, failure_trace=trace)
        )
        mode_idx = trace["mode_index"]
        n00_failed = "N00" in failed

        if mode_idx == 0:
            mode0_count += 1
            if n00_failed:
                mode0_n00_fail += 1
        else:
            mode1_count += 1
            if n00_failed:
                mode1_n00_fail += 1

    # Both conditional rates should be close to 0.3 (the probability),
    # regardless of which mode was selected.
    rate_mode0 = mode0_n00_fail / mode0_count if mode0_count > 0 else 0
    rate_mode1 = mode1_n00_fail / mode1_count if mode1_count > 0 else 0

    assert abs(rate_mode0 - 0.3) < 0.05, (
        f"P(N00 fails | mode=0) = {rate_mode0:.4f}, expected ~0.3"
    )
    assert abs(rate_mode1 - 0.3) < 0.05, (
        f"P(N00 fails | mode=1) = {rate_mode1:.4f}, expected ~0.3"
    )
    # Mode selection frequency should match weights
    assert abs(mode0_count / N - 0.8) < 0.05, (
        f"P(mode=0) = {mode0_count / N:.4f}, expected ~0.8"
    )
