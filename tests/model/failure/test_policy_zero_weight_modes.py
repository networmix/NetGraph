"""Zero modes never win; YAML requires at least one positive mode."""

import pytest

from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.model.failure import (
    FailureMode,
    FailurePolicy,
    FailureRule,
    build_failure_policies,
)
from tests.failure_fixture import draw, policy_network


def test_all_zero_weight_modes_apply_no_failures():
    policy = FailurePolicy(modes=[FailureMode(0, [FailureRule("node")])])
    case = draw(policy_network(), policy, trace=True)
    assert case.pattern.excluded_nodes == case.pattern.excluded_links == ()
    assert case.trace.mode_index is None
    assert dict(case.trace.mode_attrs) == {}
    assert case.trace.selections == ()


def test_all_zero_weight_modes_no_failures_across_seeds():
    policy = FailurePolicy(
        modes=[
            FailureMode(0, [FailureRule("node")]),
            FailureMode(0, [FailureRule("link")]),
        ]
    )
    cases = failure_cases(policy_network(), FailureRequest(policy, 20, 0))
    assert len(cases) == 1 and cases[0].occurrences == 20
    assert cases[0].pattern.excluded_nodes == cases[0].pattern.excluded_links == ()


def test_zero_weight_mode_never_selected_among_positive():
    policy = FailurePolicy(
        modes=[
            FailureMode(0, [FailureRule("node")]),
            FailureMode(1, [FailureRule("link")]),
        ]
    )
    prepared = policy_network()
    for seed in range(50):
        case = draw(prepared, policy, seed, trace=True)
        assert case.trace.mode_index == 1
        assert case.pattern.excluded_nodes == ()
        assert case.pattern.excluded_links == ("N1|N2|0", "N1|N3|0")


def test_parser_rejects_all_zero_weight_policy():
    with pytest.raises(ValueError, match="at least one mode must have positive weight"):
        build_failure_policies(
            {"all_zero": {"modes": [{"weight": 0, "rules": []}]}}, None
        )
    assert (
        build_failure_policies({"positive": {"modes": [{"weight": 1}]}}, None)[
            "positive"
        ]
        .modes[0]
        .weight
        == 1
    )


def test_parser_accepts_mixed_zero_and_positive_weights():
    policy = build_failure_policies(
        {
            "mixed": {
                "modes": [
                    {"weight": 0, "rules": [{"scope": "node"}]},
                    {"weight": 2.5, "rules": [{"scope": "link"}]},
                ]
            }
        },
        None,
    )["mixed"]
    assert [mode.weight for mode in policy.modes] == [0, 2.5]
    assert draw(policy_network(), policy, trace=True).trace.mode_index == 1
