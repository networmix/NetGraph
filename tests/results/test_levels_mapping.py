"""A compressed levels mapping has ordinary dict key and equality semantics."""

import signal
from fractions import Fraction

import numpy as np
import pytest

from ngraph import (
    Component,
    ComponentsLibrary,
    CostPowerResult,
    Network,
    Node,
    Scenario,
    prepare,
    run,
)
from ngraph.workflow import CostPower


class EqualInteger:
    def __hash__(self):
        return 1

    def __eq__(self, other):
        return other == 1


class EqualWithBrokenIndex(EqualInteger):
    def __index__(self):
        raise ValueError("a dict never asks for this conversion")


class UnequalSameHash:
    def __hash__(self):
        return 1

    def __eq__(self, other):
        return False


class IndexOnly:
    def __index__(self):
        return 1


KEYS = [
    1,
    1.0,
    Fraction(1),
    1 + 0j,
    True,
    np.int64(1),
    np.uint64(1),
    1.5,
    "1",
    None,
    -1,
    5,
    1 << 80,
    float("nan"),
    float("inf"),
    Fraction(3, 2),
    1 + 1j,
    EqualInteger(),
    EqualWithBrokenIndex(),
    UnequalSameHash(),
    IndexOnly(),
    [],
    {},
]


def outcome(action):
    try:
        return "value", action()
    except (KeyError, TypeError) as error:
        return type(error), error.args


@pytest.mark.parametrize("key", KEYS, ids=lambda k: type(k).__name__)
def test_every_mapping_operation_agrees_with_an_ordinary_dict(key):
    result = (
        run(
            prepare(
                Scenario(
                    Network(
                        nodes={
                            "a/b/c": Node(
                                "a/b/c",
                                attrs={"hardware": {"component": "c", "count": 1}},
                            ),
                            "x": Node(
                                "x", attrs={"hardware": {"component": "c", "count": 2}}
                            ),
                        }
                    ),
                    components_library=ComponentsLibrary(
                        {"c": Component("c", capex=7, power_watts=3)}
                    ),
                    workflow=[CostPower(aggregation_level=4)],
                )
            )
        )
        .steps[0]
        .result
    )
    assert isinstance(result, CostPowerResult)
    expected = dict(result.levels)
    assert [(r.path, r.capex_total, r.power_total_watts) for r in expected[0]] == [
        ("", 21, 9)
    ]
    assert [(r.path, r.capex_total, r.power_total_watts) for r in expected[1]] == [
        ("a", 7, 3),
        ("x", 14, 6),
    ]
    assert [r.path for r in expected[2]] == ["a/b", "x"]
    for operation in (
        lambda m: m[key],
        lambda m: m.get(key, "missing"),
        lambda m: key in m,
    ):
        assert outcome(lambda op=operation: op(result.levels)) == outcome(
            lambda op=operation: op(expected)
        )
    assert result.levels == expected and expected == result.levels
    assert result == CostPowerResult(False, 4, expected)
    changed = dict(expected)
    changed[1] = (None,)
    assert result.levels != changed and changed != result.levels


def test_equivalent_numeric_keys_and_large_requested_levels_keep_storage_bounded():
    previous = signal.signal(
        signal.SIGALRM,
        lambda *a: pytest.fail("bounded mapping lookup exceeded 3 seconds"),
    )
    signal.alarm(3)
    try:
        requested = 10**8
        levels = (
            run(
                prepare(
                    Scenario(
                        Network(nodes={"a/b": Node("a/b")}),
                        workflow=[CostPower(aggregation_level=requested)],
                    )
                )
            )
            .steps[0]
            .result.levels
        )
        assert len(levels.rows) == 3
        assert levels[requested] is levels[requested - 1]
        assert levels[1.0] is levels[Fraction(1)] is levels[1 + 0j] is levels[True]
        assert levels[EqualInteger()] is levels[1]
        assert (1 << 80) not in levels
        with pytest.raises(KeyError):
            levels[IndexOnly()]
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def test_mapping_equality_does_not_materialize_requested_levels(monkeypatch):
    levels = (
        run(prepare(Scenario(Network(), workflow=[CostPower(aggregation_level=10**8)])))
        .steps[0]
        .result.levels
    )

    def forbidden_iteration(self):
        raise AssertionError("unequal mapping lengths require no level iteration")

    monkeypatch.setattr(type(levels), "__iter__", forbidden_iteration)
    assert levels == levels
    assert levels != {} and {} != levels
    assert len(levels.rows) == 1
