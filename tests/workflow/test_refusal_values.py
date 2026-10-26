"""Refused values keep their ordinary representations and bounded fallbacks."""

import datetime
from decimal import Decimal

import numpy as np
import pytest

from ngraph import Node, Scenario
from ngraph.utils.values import _shown
from ngraph.workflow import BuildGraph


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            "2026-10-26",
            "network.nodes.A.attrs.x: expected finite JSON data, got datetime.date = datetime.date(2026, 10, 26)",
        ),
        (
            "2026-10-26T10:00:00Z",
            "network.nodes.A.attrs.x: expected finite JSON data, got datetime.datetime = datetime.datetime(2026, 10, 26, 10, 0, tzinfo=datetime.ti...",
        ),
        (
            "!!set {1, 2}",
            "network.nodes.A.attrs.x: expected finite JSON data, got set = {1, 2}",
        ),
        (
            "!!binary aGVsbG8=",
            "network.nodes.A.attrs.x: expected finite JSON data, got bytes = b'hello'",
        ),
    ],
)
def test_yaml_standard_value_refusal(value, expected):
    source = "network:\n  nodes:\n    A: {attrs: {x: " + value + "}}\n"
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source)
    assert str(error.value) == expected
    assert (
        Scenario.from_yaml(source.replace(value, "5")).network.nodes["A"].attrs["x"]
        == 5
    )


@pytest.mark.parametrize(
    "value, kind, shown",
    [
        ({1, 2}, "set", "{1, 2}"),
        (frozenset({3}), "frozenset", "frozenset({3})"),
        (np.array([1.5, 2.5]), "numpy.ndarray", "array([1.5, 2.5])"),
        (datetime.date(2026, 10, 26), "datetime.date", "datetime.date(2026, 10, 26)"),
        (Decimal("1.5"), "decimal.Decimal", "Decimal('1.5')"),
        (1 + 2j, "complex", "(1+2j)"),
        (
            Node("Z"),
            "ngraph.model.network.Node",
            "Node(name='Z', disabled=False, risk_groups=frozenset(), a...",
        ),
    ],
)
def test_python_standard_value_refusal(value, kind, shown):
    with pytest.raises(ValueError) as error:
        Node("A", attrs={"x": value})
    assert (
        str(error.value)
        == f"node A.attrs.x: expected finite JSON data, got {kind} = {shown}"
    )
    assert Node("A", attrs={"x": 5}).attrs["x"] == 5


def test_a_refused_value_can_supply_its_representation():
    calls = []

    class Value:
        def __repr__(self):
            calls.append("repr")
            return "custom value"

    with pytest.raises(ValueError) as error:
        BuildGraph(add_reverse=Value())
    assert str(error.value) == "BuildGraph.add_reverse: expected bool, got custom value"
    assert calls == ["repr"]
    BuildGraph(add_reverse=False)


def test_failed_representations_keep_the_base_fallbacks():
    class Value:
        def __repr__(self):
            raise RuntimeError("cannot print")

    assert _shown(Value()) == "<unprintable Value>"
    huge = 10**5000
    assert _shown(huge) == "an integer of 5001 digits"
    assert _shown({"x": huge}) == "{'x': an integer of 5001 digits}"
    assert _shown([huge]) == "[an integer of 5001 digits]"
    assert _shown((huge,)) == "(an integer of 5001 digits)"
    assert _shown("x" * 58) == "'" + "x" * 58 + "'"
    assert _shown("x" * 59) == "'" + "x" * 56 + "..."


def test_recursive_fallback_keeps_values_when_container_repr_fails():
    values = []
    values.extend((values, 10**5000))
    assert _shown(values) == "[..., an integer of 5001 digits]"

    class Value:
        def __repr__(self):
            raise RuntimeError("cannot print")

    assert _shown({"x": Value()}) == "{'x': <unprintable Value>}"


def test_failed_container_fallback_does_not_replace_the_refusal():
    class Values(list):
        def __repr__(self):
            raise RuntimeError("cannot print")

        def __iter__(self):
            raise RuntimeError("cannot iterate")

    class Mapping(dict):
        def __repr__(self):
            raise RuntimeError("cannot print")

        def items(self):
            raise RuntimeError("cannot iterate")

    for value, shown in [(Values([1]), "Values"), (Mapping(x=1), "Mapping")]:
        with pytest.raises(ValueError) as error:
            BuildGraph(add_reverse=value)
        assert (
            str(error.value)
            == f"BuildGraph.add_reverse: expected bool, got <unprintable {shown}>"
        )
    BuildGraph(add_reverse=False)
