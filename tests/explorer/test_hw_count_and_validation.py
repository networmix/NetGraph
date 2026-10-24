from __future__ import annotations

from dataclasses import replace

import pytest

from ngraph.explorer import NetworkExplorer
from ngraph.model.components import Component, ComponentsLibrary
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
    net.nodes["A"] = Node(
        name="A", attrs={"hardware": {"component": "box", "count": 2}}
    )
    net.nodes["B"] = Node(name="B")

    # Link uses per-end optics; capacity 80 <= min(src,dst) capacity
    net.links["L1"] = Link(
        source="A",
        target="B",
        capacity=80.0,
        attrs={
            "hardware": {
                "source": {"component": "optic", "count": 4},
                "target": {"component": "optic", "count": 4},
            }
        },
    )

    lib = _lib_with_box_and_optic()
    explorer = NetworkExplorer.explore_network(net, components_library=lib)
    root = explorer.root_node
    assert root is not None

    # Node totals: 2 * (capex=100, power=10) => 200, 20
    # Optics contribute only at endpoints with node hardware.
    # Only source has hardware, so link totals per-end: src 4*(5,1) + dst 0 => capex 20, power 4
    assert root.stats.total_capex == pytest.approx(220.0)
    assert root.stats.total_power == pytest.approx(24.0)


def test_node_capacity_validation_strict() -> None:
    """Total attached link capacity must not exceed node HW capacity * hw_count."""
    net = Network()
    # Node A: capacity 200 (count=1)
    net.nodes["A"] = Node(name="A", attrs={"hardware": {"component": "box"}})
    net.nodes["B"] = Node(name="B")

    # Three links of 100 each from A -> B (active)
    net.links["L1"] = Link(source="A", target="B", capacity=100.0)
    net.links["L2"] = Link(source="A", target="B", capacity=100.0)
    net.links["L3"] = Link(source="A", target="B", capacity=100.0)

    lib = _lib_with_box_and_optic()
    # Constrain node hardware to 200 to trigger validation failure (sum links=300)
    lib.components["box"] = replace(lib.components["box"], capacity=200.0)
    with pytest.raises(ValueError) as exc:
        NetworkExplorer.explore_network(net, components_library=lib)
    assert "Node 'A' total attached capacity" in str(exc.value)


def _optic_link(capacity: float, count: float, platforms: bool) -> Network:
    net = Network()
    for name in ("A", "B"):
        attrs = {"hardware": {"component": "box"}} if platforms else {}
        net.nodes[name] = Node(name=name, attrs=attrs)
    net.links["L1"] = Link(
        source="A",
        target="B",
        capacity=capacity,
        attrs={
            "hardware": {
                "source": {"component": "optic", "count": count},
                "target": {"component": "optic", "count": count},
            }
        },
    )
    return net


def test_link_ends_without_platforms_form_no_limit() -> None:
    """Optics count only where the endpoint has a platform, so no limit forms here."""
    lib = _lib_with_box_and_optic()
    explorer = NetworkExplorer.explore_network(
        _optic_link(120.0, 1, platforms=False), components_library=lib
    )
    assert explorer.get_link_issues() == []
    with pytest.raises(ValueError, match="capacity 120 exceeds per-end hardware"):
        NetworkExplorer.explore_network(
            _optic_link(120.0, 1, platforms=True), components_library=lib
        )


def test_link_limit_scales_with_the_optic_count() -> None:
    """Two optics of capacity 100 per end allow 180 and refuse 220 (limit 200)."""
    lib = _lib_with_box_and_optic()
    NetworkExplorer.explore_network(
        _optic_link(180.0, 2, platforms=True), components_library=lib
    )
    explorer = NetworkExplorer.explore_network(
        _optic_link(220.0, 2, platforms=True),
        components_library=lib,
        strict_validation=False,
    )
    assert [(i.capacity, i.limit) for i in explorer.get_link_issues()] == [
        (220.0, 200.0)
    ]
