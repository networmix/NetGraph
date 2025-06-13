import random

from ngraph.network import Network, Node
from ngraph.scenario import Scenario
from ngraph.transform.enable_nodes import EnableNodesTransform


def make_scenario(nodes):
    net = Network()
    for name, disabled in nodes:
        net.add_node(Node(name=name, disabled=disabled))
    return Scenario(
        network=net, failure_policy=None, traffic_matrix_set={}, workflow=[]
    )


def test_default_order_enables_lexical_nodes():
    scenario = make_scenario([("b", True), ("a", True), ("c", True)])
    transform = EnableNodesTransform(path="^.", count=2)
    assert transform.label == "Enable 2 nodes @ '^.'"
    transform.apply(scenario)
    net = scenario.network
    assert not net.nodes["a"].disabled
    assert not net.nodes["b"].disabled
    assert net.nodes["c"].disabled


def test_reverse_order_enables_highest_name():
    scenario = make_scenario([("a", True), ("b", True), ("c", True)])
    transform = EnableNodesTransform(path="^.", count=1, order="reverse")
    transform.apply(scenario)
    net = scenario.network
    assert not net.nodes["c"].disabled
    assert net.nodes["a"].disabled
    assert net.nodes["b"].disabled


def test_random_order_enables_shuffled_node(monkeypatch):
    scenario = make_scenario([("a", True), ("b", True), ("c", True)])

    # patch shuffle to reverse order
    def fake_shuffle(lst):
        lst.reverse()

    monkeypatch.setattr(random, "shuffle", fake_shuffle)
    transform = EnableNodesTransform(path="^.", count=1, order="random")
    transform.apply(scenario)
    net = scenario.network
    # after fake shuffle, 'c' is first
    assert not net.nodes["c"].disabled
    assert net.nodes["a"].disabled
    assert net.nodes["b"].disabled


def test_no_matching_nodes_does_nothing():
    scenario = make_scenario([("x", False), ("y", True)])
    transform = EnableNodesTransform(path="^z", count=1)
    # should not raise
    transform.apply(scenario)
    net = scenario.network
    # original states remain
    assert not net.nodes["x"].disabled
    assert net.nodes["y"].disabled
