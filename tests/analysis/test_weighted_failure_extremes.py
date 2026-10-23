"""Independent exact interval and exponential-race choices across binary64 scales."""

import math
import random
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest

from ngraph import (
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Network,
    Node,
    Scenario,
    prepare,
)
from ngraph.analysis.failures import _draw, _prepare


def modes(weights):
    n = Network(nodes={k: Node(k) for k in ("a", "b")})
    policy = FailurePolicy(
        modes=[
            FailureMode(w, [FailureRule("node", path=f"^{name}$")])
            for name, w in zip(("a", "b"), weights, strict=True)
        ]
    )
    prepared = prepare(Scenario(n))
    return _prepare(
        prepared.scenario.network, prepared._membership, FailureRequest(policy, 1)
    )


@pytest.mark.parametrize("weight", [1.0, 1e308, math.ulp(0.0), 1e-310])
def test_equal_mode_intervals_at_extremes(weight):
    p = modes((weight, weight))
    for seed in (1, 7, 42, *range(100)):
        expected = "a" if random.Random(seed).random() < 0.5 else "b"
        pattern, trace = _draw(p, 0, seed)
        assert pattern.excluded_nodes == (expected,)
        assert trace.mode_index == ("a", "b").index(expected)


@pytest.mark.parametrize("power", [-1074, -1022, -512, 0, 512, 1022])
def test_mode_common_power_of_two_scaling_uses_exact_intervals(power):
    p = modes((math.ldexp(1.0, power), math.ldexp(2.0, power)))
    for seed in range(200):
        u = random.Random(seed).random()
        num, den = u.as_integer_ratio()
        expected = "a" if 3 * num < den else "b"
        assert _draw(p, 0, seed)[0].excluded_nodes == (expected,)


def choice(weights):
    n = Network(
        nodes={
            k: Node(k, attrs={"w": w})
            for k, w in zip(("a", "b", "c", "z"), weights, strict=True)
        }
    )
    policy = FailurePolicy(
        modes=[
            FailureMode(1, [FailureRule("node", mode="choice", count=2, weight_by="w")])
        ]
    )
    prepared = prepare(Scenario(n))
    return _prepare(
        prepared.scenario.network, prepared._membership, FailureRequest(policy, 1)
    )


@pytest.mark.parametrize("weight", [1.0, 1e308, math.ulp(0.0), 1e-310])
def test_equal_weight_by_extremes_follow_the_same_uniform_draws(weight):
    p = choice((weight, weight, weight, 0))
    for seed in range(100):
        rng = random.Random(seed)
        rng.random()  # The mode consumes the first draw.
        draws = {name: rng.random() for name in ("a", "b", "c")}
        expected = tuple(
            sorted(sorted(draws, key=lambda k: (draws[k], k), reverse=True)[:2])
        )
        assert _draw(p, 0, seed)[0].excluded_nodes == expected


@pytest.mark.parametrize("power", [-1074, -1022, -512, 0, 512, 1022])
def test_weight_by_scale_invariance_against_decimal_log_oracle(power):
    p = choice(
        (math.ldexp(1.0, power), math.ldexp(2.0, power), math.ldexp(1.0, power), 0)
    )
    for seed in range(100):
        rng = random.Random(seed)
        rng.random()
        exact_rng = random.Random(seed)
        exact_rng.random()
        exact_scores = {
            name: Fraction(math.log(exact_rng.random())) / Fraction(weight)
            for name, weight in zip(
                ("a", "b", "c"),
                (
                    math.ldexp(1.0, power),
                    math.ldexp(2.0, power),
                    math.ldexp(1.0, power),
                ),
                strict=True,
            )
        }
        exact_expected = tuple(
            sorted(
                sorted(exact_scores, key=lambda k: (exact_scores[k], k), reverse=True)[
                    :2
                ]
            )
        )
        with localcontext() as ctx:
            ctx.prec = 100
            scores = {
                name: Decimal.from_float(rng.random()).ln() / Decimal(w)
                for name, w in [("a", 1), ("b", 2), ("c", 1)]
            }
        expected = tuple(
            sorted(sorted(scores, key=lambda k: (scores[k], k), reverse=True)[:2])
        )
        assert expected == exact_expected
        assert _draw(p, 0, seed)[0].excluded_nodes == expected


def test_weight_by_nonpositive_and_missing_weights_follow_positive_candidates():
    p = choice((1, 0, None, "missing"))
    for seed in range(20):
        selected = _draw(p, 0, seed)[0].excluded_nodes
        assert "a" in selected and len(selected) == 2


def test_exact_mode_interval_keeps_the_tiny_first_interval_at_draw_zero(monkeypatch):
    import ngraph.analysis.failures as sampling

    p = modes((math.ulp(0.0), 1e308))

    class Zero:
        def __init__(self, *args):
            pass

        def random(self):
            return 0.0

    monkeypatch.setattr(sampling.random, "Random", Zero)
    assert _draw(p, 0, 1)[0].excluded_nodes == ("a",)


def test_weight_by_zero_draw_is_below_every_positive_draw(monkeypatch):
    import ngraph.analysis.failures as sampling

    p = choice((1, 1, 1, 0))

    class Draws:
        def __init__(self, *args):
            self.values = iter((0.0, 0.0, 2**-53, 0.5))

        def random(self):
            return next(self.values)

    monkeypatch.setattr(sampling.random, "Random", Draws)
    assert _draw(p, 0, 1)[0].excluded_nodes == ("b", "c")


def test_mode_interval_is_half_open_at_an_exact_uniform_boundary():
    seed = 0
    u = random.Random(seed).random()
    assert u + (1 - u) == 1
    p = modes((u, 1 - u))
    pattern, trace = _draw(p, 0, seed)
    assert pattern.excluded_nodes == ("b",) and trace.mode_index == 1


def test_weight_logs_are_prepared_once_and_draws_use_two_logs(monkeypatch):
    import ngraph.analysis.failures as sampling

    original = math.log
    calls = []

    def counted(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(sampling.math, "log", counted)
    p = choice((1e308, math.ulp(0.0), 2, 0))
    assert calls == [1e308, math.ulp(0.0), 2.0]
    assert p.modes[0].rules[0].log_weights == tuple(
        (name, original(weight))
        for name, weight in (("a", 1e308), ("b", math.ulp(0.0)), ("c", 2))
    )
    calls.clear()
    for seed in range(3):
        pattern, _ = _draw(p, 0, seed)
        assert pattern.excluded_nodes == ("a", "c")
    assert len(calls) == 18
    assert 1e308 not in calls and math.ulp(0.0) not in calls
