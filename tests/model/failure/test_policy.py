"""Failure declarations execute through typed graph-owned cases."""

import random

import pytest

from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Network
from ngraph.model.selectors import Condition, evaluate_conditions
from ngraph.scenario import Scenario, prepare
from tests.failure_fixture import draw, policy_network


def _policy(rule):
    return FailurePolicy(modes=[FailureMode(1, [rule])])


@pytest.mark.parametrize("probability", [-0.1, 1.5])
def test_failure_rule_invalid_probability(probability):
    with pytest.raises(ValueError, match="failure rule probability"):
        FailureRule("node", probability=probability)
    assert FailureRule("node", probability=0.5).probability == 0.5


def test_failure_policy_evaluate_conditions_or_logic():
    conditions = [
        Condition("vendor", "==", "cisco"),
        Condition("location", "==", "dallas"),
    ]
    assert evaluate_conditions(
        {"vendor": "cisco", "location": "houston"}, conditions, "or"
    )
    assert evaluate_conditions(
        {"vendor": "juniper", "location": "dallas"}, conditions, "or"
    )
    assert evaluate_conditions(
        {"vendor": "cisco", "location": "dallas"}, conditions, "or"
    )
    assert not evaluate_conditions(
        {"vendor": "juniper", "location": "houston"}, conditions, "or"
    )


def test_failure_policy_evaluate_conditions_invalid_logic():
    conditions = [Condition("vendor", "==", "cisco")]
    with pytest.raises(ValueError, match="Unsupported logic: invalid"):
        evaluate_conditions({"vendor": "cisco"}, conditions, "invalid")
    assert evaluate_conditions({"vendor": "cisco"}, conditions, "and")


def test_node_scope_all():
    policy = _policy(FailureRule("node", [Condition("vendor", "==", "cisco")]))
    pattern = draw(policy_network(), policy).pattern
    assert pattern.excluded_nodes == ("N1", "N3")
    assert pattern.excluded_links == ()


def test_node_scope_random():
    prepared = policy_network()
    policy = _policy(
        FailureRule(
            "node", [Condition("vendor", "==", "cisco")], mode="random", probability=0.5
        )
    )
    observations = set()
    for seed in range(50):
        rng = random.Random(seed)
        rng.random()  # mode selection precedes the independent entity draws
        expected = tuple(name for name in ("N1", "N3") if rng.random() < 0.5)
        case = draw(prepared, policy, seed)
        assert case.pattern.excluded_nodes == expected
        assert draw(prepared, policy, seed).pattern == case.pattern
        assert case.pattern.excluded_links == ()
        observations.add(expected)
    assert len(observations) == 4


def test_node_scope_choice():
    prepared = policy_network()
    policy = _policy(
        FailureRule(
            "node", [Condition("vendor", "==", "cisco")], mode="choice", count=1
        )
    )
    rng = random.Random(42)
    rng.random()
    expected = tuple(rng.sample(("N1", "N3"), 1))
    assert draw(prepared, policy).pattern.excluded_nodes == expected
    assert draw(prepared, policy).pattern.excluded_links == ()


def test_link_scope_all():
    policy = _policy(FailureRule("link", [Condition("kind", "==", "fiber")]))
    pattern = draw(policy_network(), policy).pattern
    assert pattern.excluded_nodes == ()
    assert pattern.excluded_links == ("N1|N2|0",)


def test_link_scope_random():
    prepared = policy_network()
    policy = _policy(FailureRule("link", mode="random", probability=0.5))
    for seed in range(50):
        rng = random.Random(seed)
        rng.random()
        expected = tuple(name for name in ("N1|N2|0", "N1|N3|0") if rng.random() < 0.5)
        pattern = draw(prepared, policy, seed).pattern
        assert pattern.excluded_links == expected
        assert pattern.excluded_nodes == ()


def test_link_scope_choice():
    policy = _policy(FailureRule("link", mode="choice", count=1))
    rng = random.Random(42)
    rng.random()
    expected = tuple(rng.sample(("N1|N2|0", "N1|N3|0"), 1))
    pattern = draw(policy_network(), policy).pattern
    assert pattern.excluded_links == expected
    assert pattern.excluded_nodes == ()


def test_complex_conditions_and_logic():
    rule = FailureRule(
        "node",
        [Condition("vendor", "==", "cisco"), Condition("location", "==", "dallas")],
        logic="and",
    )
    assert draw(policy_network(), _policy(rule)).pattern.excluded_nodes == ("N1",)


def test_complex_conditions_or_logic():
    rule = FailureRule(
        "node",
        [Condition("vendor", "==", "juniper"), Condition("location", "==", "dallas")],
        logic="or",
    )
    assert draw(policy_network(), _policy(rule)).pattern.excluded_nodes == ("N1", "N2")


def test_multiple_rules():
    rules = [
        FailureRule("node", [Condition("vendor", "==", "juniper")]),
        FailureRule("link", [Condition("kind", "==", "fiber")]),
    ]
    pattern = draw(
        policy_network(), FailurePolicy(modes=[FailureMode(1, rules)])
    ).pattern
    assert pattern.excluded_nodes == ("N2",)
    assert pattern.excluded_links == ("N1|N2|0",)


def test_condition_operators():
    prepared = policy_network()
    different = _policy(FailureRule("node", [Condition("vendor", "!=", "cisco")]))
    missing = _policy(FailureRule("node", [Condition("absent", "exists")]))
    assert draw(prepared, different).pattern.excluded_nodes == ("N2",)
    assert draw(prepared, missing).pattern.excluded_nodes == ()


def test_missing_attributes():
    policy = _policy(FailureRule("node", [Condition("missing", "==", "value")]))
    assert draw(policy_network(), policy).pattern.excluded_nodes == ()


def test_empty_policy():
    case = draw(policy_network(), FailurePolicy())
    assert case.kind == "baseline"
    assert case.pattern.excluded_nodes == case.pattern.excluded_links == ()


def test_empty_entities():
    case = draw(prepare(Scenario(Network())), _policy(FailureRule("node")))
    assert case.pattern.excluded_nodes == case.pattern.excluded_links == ()


def test_multi_rule_independence():
    prepared = policy_network()
    rules = [
        FailureRule("link", mode="random", probability=0.5),
        FailureRule("node", mode="random", probability=0.5),
    ]
    cases = failure_cases(
        prepared, FailureRequest(FailurePolicy(modes=[FailureMode(1, rules)]), 2000, 0)
    )
    joint = sum(
        case.occurrences
        for case in cases
        if "N1|N2|0" in case.pattern.excluded_links
        and "N1" in case.pattern.excluded_nodes
    )
    links = sum(
        case.occurrences for case in cases if "N1|N2|0" in case.pattern.excluded_links
    )
    nodes = sum(
        case.occurrences for case in cases if "N1" in case.pattern.excluded_nodes
    )
    assert abs(joint / 2000 - (links / 2000) * (nodes / 2000)) < 0.06
    assert 0.45 < links / 2000 < 0.55 and 0.45 < nodes / 2000 < 0.55


def test_multi_mode_entity_independence():
    prepared = policy_network()
    rule = FailureRule("node", mode="random", probability=0.3)
    policy = FailurePolicy(modes=[FailureMode(0.8, [rule]), FailureMode(0.2, [rule])])
    mode_counts, first_failed = [0, 0], [0, 0]
    # One draw per request preserves each draw's trace instead of deduplicating it.
    for seed in range(2000):
        case = draw(prepared, policy, seed, trace=True)
        mode = case.trace.mode_index
        mode_counts[mode] += 1
        first_failed[mode] += "N1" in case.pattern.excluded_nodes
    assert abs(mode_counts[0] / 2000 - 0.8) < 0.05
    for count, failed in zip(mode_counts, first_failed, strict=True):
        assert abs(failed / count - 0.3) < 0.05
