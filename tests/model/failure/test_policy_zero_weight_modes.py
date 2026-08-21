"""Tests for zero-weight failure mode semantics.

Modes with zero weight must never be selected, including the degenerate case
where no mode has positive weight (the policy then fails nothing). The parser
rejects policies whose modes all have zero weight.
"""

from __future__ import annotations

import pytest

from ngraph.model.failure.parser import build_failure_policy
from ngraph.model.failure.policy import FailureMode, FailurePolicy, FailureRule


def test_all_zero_weight_modes_apply_no_failures() -> None:
    """A policy whose only mode has weight 0 must not fail anything."""
    rule = FailureRule(scope="node", mode="all")
    policy = FailurePolicy(modes=[FailureMode(weight=0.0, rules=[rule])])

    nodes = {"N1": {}, "N2": {}}
    trace: dict = {}
    failed = policy.apply_failures(nodes, {}, failure_trace=trace, seed=1)

    assert failed == []
    assert trace["mode_index"] is None
    assert trace["mode_attrs"] == {}
    assert trace["selections"] == []


def test_all_zero_weight_modes_no_failures_across_seeds() -> None:
    """No seed may ever select a zero-weight mode."""
    rule = FailureRule(scope="node", mode="all")
    policy = FailurePolicy(
        modes=[
            FailureMode(weight=0.0, rules=[rule]),
            FailureMode(weight=0.0, rules=[rule]),
        ]
    )
    nodes = {"N1": {}, "N2": {}}

    for seed in range(20):
        assert policy.apply_failures(nodes, {}, seed=seed) == []


def test_zero_weight_mode_never_selected_among_positive() -> None:
    """A zero-weight mode must never win against a positive-weight mode."""
    node_rule = FailureRule(scope="node", mode="all")
    link_rule = FailureRule(scope="link", mode="all")
    policy = FailurePolicy(
        modes=[
            FailureMode(weight=0.0, rules=[node_rule]),
            FailureMode(weight=1.0, rules=[link_rule]),
        ]
    )
    nodes = {"N1": {}}
    links = {"L1": {}}

    for seed in range(50):
        trace: dict = {}
        failed = policy.apply_failures(nodes, links, failure_trace=trace, seed=seed)
        assert trace["mode_index"] == 1
        assert failed == ["L1"]


def test_parser_rejects_all_zero_weight_policy() -> None:
    """An all-zero-weight policy must fail loudly at parse time."""
    fp_data = {
        "modes": [
            {"weight": 0.0, "rules": [{"scope": "node", "mode": "all"}]},
            {"weight": 0, "rules": []},
        ]
    }
    with pytest.raises(ValueError, match="no mode with positive weight"):
        build_failure_policy(
            fp_data, policy_name="all_zero", derive_seed=lambda _name: None
        )


def test_parser_accepts_mixed_zero_and_positive_weights() -> None:
    """Zero-weight modes are allowed as long as one mode has positive weight."""
    fp_data = {
        "modes": [
            {"weight": 0.0, "rules": [{"scope": "node", "mode": "all"}]},
            {"weight": 2.5, "rules": [{"scope": "link", "mode": "all"}]},
        ]
    }
    policy = build_failure_policy(
        fp_data, policy_name="mixed", derive_seed=lambda _name: None
    )
    assert [mode.weight for mode in policy.modes] == [0.0, 2.5]
