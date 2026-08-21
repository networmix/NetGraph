"""Round-trip tests for FailurePolicy.to_dict.

The serialized form must match the scenario YAML failure-policy format
(conditions/logic nested under "match") so it can be read back by
build_failure_policy and validates against the scenario JSON schema.
"""

from __future__ import annotations

import json
from importlib import resources

import jsonschema

from ngraph.model.failure.parser import build_failure_policy
from ngraph.model.failure.policy import FailureMode, FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.selectors import Condition


def _sample_policy() -> FailurePolicy:
    rule_a = FailureRule(
        scope="node",
        conditions=[Condition(attr="role", op="==", value="spine")],
        logic="and",
        mode="choice",
        count=2,
        weight_by="capacity",
    )
    rule_b = FailureRule(
        scope="link",
        conditions=[Condition(attr="link_type", op="==", value="fiber")],
        logic="or",
        mode="random",
        probability=0.25,
        path="^dc1/",
    )
    return FailurePolicy(
        attrs={"name": "sample"},
        expand_groups=True,
        modes=[
            FailureMode(weight=0.7, rules=[rule_a], attrs={"label": "spines"}),
            FailureMode(weight=0.3, rules=[rule_b]),
        ],
    )


def test_to_dict_round_trips_through_parser() -> None:
    """build_failure_policy(policy.to_dict()) must preserve all rule fields."""
    policy = _sample_policy()
    rebuilt = build_failure_policy(
        policy.to_dict(), policy_name="sample", derive_seed=lambda _name: None
    )

    assert rebuilt.attrs == policy.attrs
    assert rebuilt.expand_groups == policy.expand_groups
    assert len(rebuilt.modes) == len(policy.modes)
    for orig_mode, new_mode in zip(policy.modes, rebuilt.modes, strict=True):
        assert new_mode.weight == orig_mode.weight
        assert new_mode.attrs == orig_mode.attrs
        for orig_rule, new_rule in zip(orig_mode.rules, new_mode.rules, strict=True):
            assert new_rule.scope == orig_rule.scope
            assert new_rule.conditions == orig_rule.conditions
            assert new_rule.logic == orig_rule.logic
            assert new_rule.mode == orig_rule.mode
            assert new_rule.probability == orig_rule.probability
            assert new_rule.count == orig_rule.count
            assert new_rule.weight_by == orig_rule.weight_by
            assert new_rule.path == orig_rule.path


def test_to_dict_matches_scenario_schema() -> None:
    """to_dict output must validate against the scenario JSON schema."""
    policy = _sample_policy()
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    jsonschema.validate({"failures": {"sample": policy.to_dict()}}, schema)


def test_to_dict_excludes_seed_and_nests_match() -> None:
    """Serialized policies omit seed and nest conditions under match."""
    policy = _sample_policy()
    policy.seed = 42
    data = policy.to_dict()

    assert "seed" not in data
    assert "expand_children" not in data
    rule_dict = data["modes"][0]["rules"][0]
    assert "conditions" not in rule_dict
    assert "logic" not in rule_dict
    assert rule_dict["match"] == {
        "logic": "and",
        "conditions": [{"attr": "role", "op": "==", "value": "spine"}],
    }


def test_policy_set_to_dict_delegates_to_policy_to_dict() -> None:
    """FailurePolicySet.to_dict must emit the same shape per policy."""
    fps = FailurePolicySet()
    policy = _sample_policy()
    fps.add("sample", policy)

    assert fps.to_dict() == {"sample": policy.to_dict()}
