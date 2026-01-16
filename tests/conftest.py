"""Global pytest configuration and shared fixtures."""

from __future__ import annotations

import pytest

from ngraph import Link, Network, Node

# -----------------------------------------------------------------------------
# Shared Network Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def diamond_network() -> Network:
    """Symmetric diamond network: A -> B,C -> D with equal capacity paths.

    Topology:
        A -> B (cap 60, cost 1) -> D
        A -> C (cap 60, cost 1) -> D

    Both paths have cost 2, total capacity 120.
    Used for demand placement and basic flow tests.
    """
    network = Network()
    for node in ["A", "B", "C", "D"]:
        network.add_node(Node(node))

    network.add_link(Link("A", "B", capacity=60.0, cost=1.0))
    network.add_link(Link("A", "C", capacity=60.0, cost=1.0))
    network.add_link(Link("B", "D", capacity=60.0, cost=1.0))
    network.add_link(Link("C", "D", capacity=60.0, cost=1.0))

    return network


def make_asymmetric_diamond(
    *,
    disable_node_b: bool = False,
    disable_link_a_b: bool = False,
) -> Network:
    """Factory for asymmetric diamond network with optional disabled elements.

    Topology:
        A -> B (cap 5, cost 1) -> D (cap 5, cost 1)  [tier 1: cost 2, cap 5]
        A -> C (cap 3, cost 2) -> D (cap 3, cost 2)  [tier 2: cost 4, cap 3]

    With both paths enabled: max flow = 8 (5 via B + 3 via C)
    With B disabled: max flow = 3 (only via C)
    With A->B link disabled: max flow = 3 (only via C)

    Args:
        disable_node_b: If True, disable node B.
        disable_link_a_b: If True, disable the A->B link.

    Returns:
        Network with configured topology.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=disable_node_b))
    net.add_node(Node("C"))
    net.add_node(Node("D"))

    net.add_link(Link("A", "B", capacity=5.0, cost=1.0, disabled=disable_link_a_b))
    net.add_link(Link("B", "D", capacity=5.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=3.0, cost=2.0))
    net.add_link(Link("C", "D", capacity=3.0, cost=2.0))

    return net


@pytest.fixture
def asymmetric_diamond() -> Network:
    """Asymmetric diamond network with different cost tiers.

    Shortcut fixture for make_asymmetric_diamond() with defaults.
    """
    return make_asymmetric_diamond()


@pytest.fixture
def multi_tier_network() -> Network:
    """Multi-tier cost network with large capacity.

    Topology:
        A -> B (cap 30, cost 1) -> D (cap 30, cost 1)  [tier 1: cost 2]
        A -> C (cap 30, cost 2) -> D (cap 30, cost 2)  [tier 2: cost 4]

    Both tiers have equal capacity (30), but different costs.
    Used for demand placement cost distribution tests.
    """
    network = Network()
    for node in ["A", "B", "C", "D"]:
        network.add_node(Node(node))

    # Tier 1: cost 2, capacity 30
    network.add_link(Link("A", "B", capacity=30.0, cost=1.0))
    network.add_link(Link("B", "D", capacity=30.0, cost=1.0))

    # Tier 2: cost 4, capacity 30
    network.add_link(Link("A", "C", capacity=30.0, cost=2.0))
    network.add_link(Link("C", "D", capacity=30.0, cost=2.0))

    return network
