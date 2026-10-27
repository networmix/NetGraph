"""Refused values keep their ordinary representations, shortened when long."""

import datetime
from decimal import Decimal

import numpy as np
import pytest

from ngraph import Node, Scenario
from ngraph.utils.values import _shown


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


def test_text_representation_is_bounded():
    assert _shown("x" * 58) == "'" + "x" * 58 + "'"
    assert _shown("x" * 59) == "'" + "x" * 56 + "..."
