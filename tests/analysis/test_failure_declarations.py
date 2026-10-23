"""One policy seed recipe and closed, typed failure declarations."""

import pytest

from ngraph.model.failure import build_failure_policies
from ngraph.utils.seed_manager import SeedManager


def test_yaml_policy_seed_keeps_the_existing_composed_hash():
    raw = {
        "random_link": {
            "modes": [
                {
                    "weight": 1,
                    "rules": [{"scope": "link", "mode": "choice", "count": 1}],
                }
            ]
        }
    }
    policy = build_failure_policies(raw, 42)["random_link"]
    assert policy.seed == 2099469712
    assert policy.seed != 1686100401
    assert policy.seed == SeedManager(42).derive_seed(
        "failure_policy", "failure_policy", "random_link"
    )
    assert build_failure_policies(raw, None)["random_link"].seed is None
    assert build_failure_policies(raw, 43)["random_link"].seed != policy.seed
    raw["random_link"]["modes"][0]["rules"][0]["count"] = 2
    assert policy.modes[0].rules[0].count == 1


@pytest.mark.parametrize(
    "where,key", [("policy", "seed"), ("mode", "selection"), ("rule", "probabilty")]
)
def test_unknown_policy_fields_refuse_with_legal_control(where, key):
    rule = {"scope": "link"}
    mode = {"weight": 1, "rules": [rule]}
    policy = {"modes": [mode]}
    selected = {"policy": policy, "mode": mode, "rule": rule}[where]
    selected[key] = 1
    with pytest.raises(ValueError, match=key):
        build_failure_policies({"p": policy}, 42)
    del selected[key]
    assert (
        build_failure_policies({"p": policy}, 42)["p"].modes[0].rules[0].scope == "link"
    )
