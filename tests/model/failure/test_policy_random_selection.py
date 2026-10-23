"""Per-entity Bernoulli observations and weighted draws through public cases."""

import pytest

from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Network, Node
from ngraph.scenario import Scenario, prepare
from tests.failure_fixture import draw


def _prepared(count=30):
    return prepare(
        Scenario(Network(nodes={f"N{i:03d}": Node(f"N{i:03d}") for i in range(count)}))
    )


def _random_policy(probability):
    return FailurePolicy(
        modes=[
            FailureMode(
                1, [FailureRule("node", mode="random", probability=probability)]
            )
        ]
    )


def test_random_probability_zero_selects_none():
    cases = failure_cases(_prepared(), FailureRequest(_random_policy(0), 10, 0))
    assert len(cases) == 1 and cases[0].occurrences == 10
    assert cases[0].pattern.excluded_nodes == ()


def test_random_probability_one_selects_all():
    prepared = _prepared()
    cases = failure_cases(prepared, FailureRequest(_random_policy(1), 10, 0))
    assert len(cases) == 2 and cases[1].occurrences == 10
    assert cases[1].pattern.excluded_nodes == tuple(prepared.scenario.network.nodes)
    assert cases[1].pattern.excluded_links == ()


def test_random_seeded_determinism_and_subset():
    prepared = _prepared()
    policy = _random_policy(0.4)
    patterns = set()
    for seed in range(30):
        first = draw(prepared, policy, seed).pattern
        assert draw(prepared, policy, seed).pattern == first
        assert set(first.excluded_nodes) <= set(prepared.scenario.network.nodes)
        patterns.add(first)
    assert len(patterns) > 1


def test_random_marginal_rate_matches_probability():
    cases = failure_cases(_prepared(100), FailureRequest(_random_policy(0.5), 200, 0))
    failed = sum(case.occurrences * len(case.pattern.excluded_nodes) for case in cases)
    assert abs(failed / 20000 - 0.5) < 0.05


class TestWeightedSamplingExtremeScales:
    @pytest.mark.parametrize("scale", [1e-6, 1e-3, 1.0, 1e6, 1e17])
    def test_selection_proportional_across_scales(self, scale):
        network = Network(
            nodes={
                name: Node(name, attrs={"weight": weight * scale})
                for name, weight in (("a", 2), ("b", 1), ("c", 1))
            }
        )
        prepared = prepare(Scenario(network))
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("node", mode="choice", count=1, weight_by="weight")]
                )
            ]
        )
        cases = failure_cases(prepared, FailureRequest(policy, 6000, 0))
        counts = {
            case.pattern.excluded_nodes[0]: case.occurrences for case in cases[1:]
        }
        assert set(counts) == {"a", "b", "c"}
        assert abs(counts["a"] / 6000 - 0.5) < 0.05
        assert counts["b"] > 0 and counts["c"] > 0
