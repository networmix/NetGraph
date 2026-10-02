"""Programmatic failure-policy parsing rejects keys it would otherwise ignore."""

from __future__ import annotations

import pytest

from ngraph.model.failure.parser import build_failure_policy_set


def _build(policy: dict) -> None:
    build_failure_policy_set({"p": policy}, derive_seed=lambda _name: None)


def test_unknown_policy_key_raises() -> None:
    with pytest.raises(ValueError, match="failure policy 'p'.*expand_children"):
        _build({"modes": [{"weight": 1.0, "rules": []}], "expand_children": True})


def test_unknown_mode_key_raises() -> None:
    with pytest.raises(ValueError, match="failure mode.*probability"):
        _build({"modes": [{"weight": 1.0, "rules": [], "probability": 0.5}]})


def test_rule_level_conditions_raise() -> None:
    """Rule-level `conditions` outside `match` raise instead of failing every entity."""
    rule = {"scope": "node", "mode": "all", "conditions": [{"attr": "x"}]}
    with pytest.raises(ValueError, match="failure rule.*conditions"):
        _build({"modes": [{"weight": 1.0, "rules": [rule]}]})


def test_risk_group_builders_reject_unknown_keys() -> None:
    """Risk groups, children, membership and generate blocks reject stray keys."""
    from ngraph.model.failure.generate import parse_generate_spec
    from ngraph.model.failure.membership import _parse_membership_spec
    from ngraph.model.failure.parser import build_risk_groups

    with pytest.raises(ValueError, match="risk group 'X': bogus"):
        build_risk_groups([{"name": "X", "bogus": 1}])
    with pytest.raises(ValueError, match="risk group 'Y': bogus"):
        build_risk_groups([{"name": "X", "children": [{"name": "Y", "bogus": 1}]}])
    with pytest.raises(ValueError, match="generate entry: name"):
        build_risk_groups([{"generate": {}, "name": "X"}])
    with pytest.raises(ValueError, match="membership rule: bogus"):
        _parse_membership_spec({"scope": "node", "path": ".*", "bogus": 1})
    with pytest.raises(ValueError, match="generate block: bogus"):
        parse_generate_spec(
            {"scope": "node", "group_by": "g", "name": "G_${value}", "bogus": 1}
        )


def test_match_spec_rejects_unknown_keys() -> None:
    from ngraph.model.selectors import parse_match_spec

    with pytest.raises(ValueError, match="in match: bogus"):
        parse_match_spec({"conditions": [], "bogus": 1})
    with pytest.raises(ValueError, match="condition in match: bogus"):
        parse_match_spec({"conditions": [{"attr": "a", "op": "==", "bogus": 1}]})
