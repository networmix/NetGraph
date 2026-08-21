"""Tests for mode='random' selection behavior in FailurePolicy.

Pin the semantics of the binomial-count + uniform-sample implementation:
exact behavior at probability 0 and 1, seeded determinism, candidate-subset
containment (including the prepared-matches tuple path), and the marginal
failure rate.
"""

from __future__ import annotations

import pytest

from ngraph.model.failure.policy import FailureMode, FailurePolicy, FailureRule


def _random_policy(probability: float) -> FailurePolicy:
    rule = FailureRule(scope="node", mode="random", probability=probability)
    return FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])


def test_random_probability_zero_selects_none() -> None:
    policy = _random_policy(0.0)
    nodes = {f"N{i}": {} for i in range(20)}
    for seed in range(10):
        assert policy.apply_failures(nodes, {}, seed=seed) == []


def test_random_probability_one_selects_all() -> None:
    policy = _random_policy(1.0)
    nodes = {f"N{i}": {} for i in range(20)}
    for seed in range(10):
        assert set(policy.apply_failures(nodes, {}, seed=seed)) == set(nodes)


def test_random_seeded_determinism_and_subset() -> None:
    policy = _random_policy(0.4)
    nodes = {f"N{i}": {} for i in range(30)}

    failed1 = policy.apply_failures(nodes, {}, seed=123)
    failed2 = policy.apply_failures(nodes, {}, seed=123)
    assert failed1 == failed2
    assert set(failed1).issubset(set(nodes))

    # Different seeds should eventually produce different selections
    results = {tuple(policy.apply_failures(nodes, {}, seed=s)) for s in range(30)}
    assert len(results) > 1


def test_random_with_prepared_matches_tuple() -> None:
    """Prepared candidate tuples are used as-is and yield identical results."""
    policy = _random_policy(0.5)
    nodes = {f"N{i}": {} for i in range(25)}
    prepared = policy.prepare_matches(nodes, {}, {})

    for seed in range(10):
        baseline = policy.apply_failures(nodes, {}, seed=seed)
        with_prepared = policy.apply_failures(
            nodes, {}, seed=seed, prepared_matches=prepared
        )
        assert with_prepared == baseline


def test_random_marginal_rate_matches_probability() -> None:
    """Mean failure fraction over many seeds must be close to the probability."""
    probability = 0.5
    policy = _random_policy(probability)
    n_entities = 100
    nodes = {f"N{i:03d}": {} for i in range(n_entities)}

    trials = 200
    total_failed = sum(
        len(policy.apply_failures(nodes, {}, seed=seed)) for seed in range(trials)
    )
    mean_fraction = total_failed / (trials * n_entities)
    # Std of the mean is ~0.0035; 0.05 tolerance is far beyond noise.
    assert abs(mean_fraction - probability) < 0.05


class TestWeightedSamplingExtremeScales:
    """Regression: E-S keys are computed in the log domain, so weighted
    selection stays proportional for tiny (e.g. per-hour failure rates) and
    huge weight scales instead of degenerating into descending-id order."""

    @pytest.mark.parametrize("scale", [1e-6, 1e-3, 1.0, 1e6, 1e17])
    def test_selection_proportional_across_scales(self, scale: float) -> None:
        import random
        from collections import Counter

        weights = {"a": 2.0 * scale, "b": 1.0 * scale, "c": 1.0 * scale}
        rng = random.Random(7)
        counts: Counter[str] = Counter()
        trials = 6000
        for _ in range(trials):
            counts.update(
                FailurePolicy._weighted_sample_without_replacement(weights, 1, rng)
            )
        # "a" carries half the total weight; allow generous sampling noise.
        assert abs(counts["a"] / trials - 0.5) < 0.05
        assert counts["b"] > 0 and counts["c"] > 0
