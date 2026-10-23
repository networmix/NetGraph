"""Weighted choice preserves positive picks, zero fill and mode selection."""

from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario, prepare
from tests.failure_fixture import draw


def weighted_links(weights):
    network = Network()
    network.add_node(Node("s"))
    network.add_node(Node("t"))
    for weight in weights:
        network.add_link(Link("s", "t", 10, 3, attrs={"weight": weight}))
    return prepare(Scenario(network))


def test_weighted_choice_uses_weight_by_and_excludes_zero_weight_items():
    prepared = weighted_links([10, 0, 5])
    policy = FailurePolicy(
        modes=[
            FailureMode(
                1, [FailureRule("link", mode="choice", count=2, weight_by="weight")]
            )
        ]
    )
    for seed in range(10):
        assert draw(prepared, policy, seed).pattern.excluded_links == ("s|t|0", "s|t|2")


def test_weighted_choice_fills_from_zero_when_insufficient_positive():
    prepared = weighted_links([7, 0, 0])
    policy = FailurePolicy(
        modes=[
            FailureMode(
                1, [FailureRule("link", mode="choice", count=2, weight_by="weight")]
            )
        ]
    )
    selections = set()
    for seed in range(30):
        links = draw(prepared, policy, seed).pattern.excluded_links
        assert len(links) == 2 and links[0] == "s|t|0"
        assert links[1] in ("s|t|1", "s|t|2")
        selections.add(links[1])
    assert selections == {"s|t|1", "s|t|2"}


def test_weighted_modes_selects_positive_weight_mode_only():
    prepared = weighted_links([1, 2])
    policy = FailurePolicy(
        modes=[
            FailureMode(0, [FailureRule("link")]),
            FailureMode(1, [FailureRule("node")]),
        ]
    )
    case = draw(prepared, policy, trace=True)
    assert case.trace.mode_index == 1
    assert case.pattern.excluded_nodes == ("s", "t")
    assert case.pattern.excluded_links == ()
