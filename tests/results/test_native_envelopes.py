"""Domain envelopes keep exact values and native ownership."""

from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest

from ngraph import Link, Network, Node
from ngraph.results import (
    ExactAlpha,
    ExpansionAccounting,
    MSDProbe,
    PlacementTotals,
)


def test_package_import_uses_domain_models():
    network = Network()
    network.add_node(Node("a"))
    network.add_node(Node("t"))
    network.add_link(Link("a", "t", capacity=3, cost=5))
    assert tuple(network.links) == ("a|t|0",)


def test_compact_probe_and_exact_totals():
    total = PlacementTotals(
        2**65, 2**65 - 1, 1, 0, 0, 1, Fraction(2**65 - 1, 2**65), False
    )
    probe = MSDProbe(0, ExactAlpha(1.0, 1, 1), "infeasible", total, None)
    assert probe.totals.reference_request_units == 2**65
    assert probe.totals.delivery_ratio.denominator == 2**65
    assert not hasattr(probe, "rows") and not hasattr(probe, "accounting")
    with pytest.raises(FrozenInstanceError):
        probe.outcome = "feasible"
    assert (
        MSDProbe(0, ExactAlpha(1.0, 1, 1), "feasible", total, None).outcome
        == "feasible"
    )


def test_a_domain_step_records_itself_as_its_question():
    from dataclasses import replace

    from ngraph import Scenario, prepare, run
    from ngraph.workflow.build_graph import BuildGraph

    step = BuildGraph(name="graph", add_reverse=False)
    assert run(prepare(Scenario(Network(), [step]))).steps[0].question is step
    with pytest.raises(TypeError):
        replace(step, unknown=True)


def test_expansion_accounting_is_integer_data():
    value = ExpansionAccounting("set|0", 10, 9, 1, ())
    assert value.declared_units == value.resolved_units + value.discarded_units


def test_metadata_keys_are_strings_and_caller_nested_values_are_owned():
    import pytest

    from ngraph.utils.values import frozen_attrs

    with pytest.raises(ValueError, match="keys must be strings"):
        frozen_attrs({1: "bad"})
    original = {"nested": {"values": [1, 2]}}
    owned = frozen_attrs(original)
    original["nested"]["values"].append(3)
    assert owned["nested"]["values"] == [1, 2]
    with pytest.raises(TypeError):
        owned["new"] = 1
