"""Zero modes never win; a policy, in Python and YAML, needs one positive mode."""

import pytest

from ngraph.model.failure import (
    FailureMode,
    FailurePolicy,
    FailureRule,
    build_failure_policies,
)
from tests.failure_fixture import draw, policy_network


@pytest.mark.parametrize("weights", [(0,), (0, 0)])
def test_a_policy_whose_modes_all_weigh_zero_is_refused_where_it_is_built(weights):
    modes = [FailureMode(w, [FailureRule("node")]) for w in weights]
    with pytest.raises(
        ValueError,
        match="^failure policy modes: at least one mode must have positive weight$",
    ):
        FailurePolicy(modes=modes)
    # Control: one positive mode makes it a policy.
    assert FailurePolicy(modes=[*modes, FailureMode(1, [FailureRule("link")])])


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
