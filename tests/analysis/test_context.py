"""Tests for AnalysisContext internal infrastructure.

Tests verify that disabled nodes/links are properly tracked and that
the context provides correct access to Core graph components.
"""

from ngraph import Link, Network, Node
from ngraph.analysis import AnalysisContext


def test_context_creation():
    """Test that AnalysisContext can be created from a network."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0))

    ctx = AnalysisContext.from_network(net)

    # Basic sanity checks
    assert ctx is not None
    assert ctx.multidigraph.num_nodes() >= 2
    assert ctx.multidigraph.num_edges() >= 2  # Forward + reverse


def test_disabled_node_tracked():
    """Test that disabled nodes are tracked in context."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=True))
    net.add_node(Node("C"))
    net.add_link(Link("A", "B", capacity=10.0))
    net.add_link(Link("B", "C", capacity=10.0))

    ctx = AnalysisContext.from_network(net)

    # Disabled node B should be tracked
    assert len(ctx.disabled_node_ids) == 1


def test_disabled_link_tracked():
    """Test that disabled links are tracked in context."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, disabled=True))

    ctx = AnalysisContext.from_network(net)

    # Disabled link should be tracked
    assert len(ctx.disabled_link_ids) == 1
