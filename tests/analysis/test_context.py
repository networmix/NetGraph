"""Physical preparation owns one native graph and its nominal eligibility."""

from ngraph import Link, Network, Node, Scenario, UnitsSettings, prepare


def test_context_creation():
    """Preparation compiles every bidirectional physical link."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0))

    topology = prepare(Scenario(net, units=UnitsSettings(1))).topology

    # Basic sanity checks
    assert topology.graph.num_nodes() == 2
    assert topology.graph.num_edges() == 2


def test_disabled_node_tracked():
    """Declared disabled nodes remain in labels and are masked."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=True))
    net.add_node(Node("C"))
    net.add_link(Link("A", "B", capacity=10.0))
    net.add_link(Link("B", "C", capacity=10.0))

    topology = prepare(Scenario(net, units=UnitsSettings(1))).topology
    assert topology.node_names == ("A", "B", "C")
    assert topology.disabled.node_allowed().tolist() == [True, False, True]


def test_disabled_link_tracked():
    """A disabled physical link masks both analysis directions."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, disabled=True))

    topology = prepare(Scenario(net, units=UnitsSettings(1))).topology
    assert topology.disabled.edge_allowed().tolist() == [False, False]
    assert topology.disabled.node_allowed().tolist() == [True, True]
