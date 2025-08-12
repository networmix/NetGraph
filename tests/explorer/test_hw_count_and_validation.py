from __future__ import annotations

import pytest

from ngraph.components import Component, ComponentsLibrary
from ngraph.explorer import NetworkExplorer
from ngraph.model.network import Link, Network, Node


def _lib_with_box_and_optic() -> ComponentsLibrary:
    """Create a components library with 'box' and 'optic' definitions.

    - box: capex=100, power=10, capacity=1000
    - optic: capex=5, power=1, capacity=100
    """
    lib = ComponentsLibrary()
    lib.components["box"] = Component(
        name="box",
        capex=100.0,
        power_watts=10.0,
        capacity=1000.0,
    )
    lib.components["optic"] = Component(
        name="optic",
        capex=5.0,
        power_watts=1.0,
        capacity=100.0,
    )
    return lib


def test_hw_count_multiplier_applies_to_capex_and_power() -> None:
    """Verify that node/link totals are multiplied by optional hw_count."""
    net = Network()
    net.nodes["A"] = Node(name="A", attrs={"hw_component": "box", "hw_count": 2})
    net.nodes["B"] = Node(name="B")

    # Link uses 4 optics; capacity 80 <= optic.capacity * hw_count (100 * 4)
    net.links["L1"] = Link(
        source="A",
        target="B",
        capacity=80.0,
        attrs={"hw_component": "optic", "hw_count": 4},
    )

    lib = _lib_with_box_and_optic()
    explorer = NetworkExplorer.explore_network(net, components_library=lib)
    root = explorer.root_node
    assert root is not None

    # Node totals: 2 * (capex=100, power=10) => 200, 20
    # Link totals: 4 * (capex=5, power=1) => 20, 4
    assert root.stats.total_capex == pytest.approx(220.0)
    assert root.stats.total_power == pytest.approx(24.0)


def test_node_capacity_validation_strict() -> None:
    """Total attached link capacity must not exceed node HW capacity * hw_count."""
    net = Network()
    # Node A: capacity 200 (count=1)
    net.nodes["A"] = Node(name="A", attrs={"hw_component": "box"})
    net.nodes["B"] = Node(name="B")

    # Three links of 100 each from A -> B (active)
    net.links["L1"] = Link(source="A", target="B", capacity=100.0)
    net.links["L2"] = Link(source="A", target="B", capacity=100.0)
    net.links["L3"] = Link(source="A", target="B", capacity=100.0)

    lib = _lib_with_box_and_optic()
    # Constrain node hardware to 200 to trigger validation failure (sum links=300)
    lib.components["box"].capacity = 200.0
    with pytest.raises(ValueError) as exc:
        NetworkExplorer.explore_network(net, components_library=lib)
    assert "exceeds hardware capacity" in str(exc.value)


def test_link_capacity_validation_strict() -> None:
    """Link capacity must be <= link HW capacity * hw_count if set."""
    net = Network()
    net.nodes["A"] = Node(name="A")
    net.nodes["B"] = Node(name="B")
    # Link requires optic capacity 100, but capacity is 120 -> should fail
    net.links["L1"] = Link(
        source="A",
        target="B",
        capacity=120.0,
        attrs={"hw_component": "optic"},
    )

    lib = _lib_with_box_and_optic()
    with pytest.raises(ValueError) as exc:
        NetworkExplorer.explore_network(net, components_library=lib)
    assert "exceeds hardware capacity" in str(exc.value)


def test_link_capacity_with_multiplier_allows() -> None:
    """Multiplier on link HW allows higher capacity within bounds."""
    net = Network()
    net.nodes["A"] = Node(name="A")
    net.nodes["B"] = Node(name="B")
    # Optic capacity 100, hw_count=2 -> 200 allows 180
    net.links["L1"] = Link(
        source="A",
        target="B",
        capacity=180.0,
        attrs={"hw_component": "optic", "hw_count": 2},
    )

    lib = _lib_with_box_and_optic()
    # Should not raise
    NetworkExplorer.explore_network(net, components_library=lib)
