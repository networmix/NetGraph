"""Identical component copies supply and consume their own port equivalents."""

from dataclasses import asdict

import pytest

from ngraph import Component, ComponentsLibrary, Link, Network, NetworkExplorer, Node


@pytest.mark.parametrize(
    "platform_count,optic_count,hw_count", [(2, 1, 1), (1, 2, 1), (2, 2, 0.5)]
)
def test_component_copy_counts_apply_to_both_sides_of_the_port_limit(
    platform_count, optic_count, hw_count
):
    library = ComponentsLibrary(
        {
            "p": Component("p", capacity=100, ports=1, count=platform_count),
            "o": Component("o", ports=1, count=optic_count),
        }
    )
    n = Network(
        nodes={
            "a": Node("a", attrs={"hardware": {"component": "p", "count": hw_count}}),
            "b": Node("b"),
        }
    )
    for _ in range(2):
        n.add_link(
            Link(
                "a",
                "b",
                10,
                attrs={"hardware": {"source": {"component": "o", "count": hw_count}}},
            )
        )
    explorer = NetworkExplorer.explore_network(n, library, strict_validation=False)
    available = platform_count * hw_count
    used = 2 * optic_count * hw_count
    assert [asdict(row) for row in explorer.get_node_utilization()] == [
        {
            "node_name": "a",
            "component_name": "p",
            "hw_count": hw_count,
            "capacity_supported": 100 * platform_count * hw_count,
            "attached_capacity_active": 20,
            "capacity_utilization": 20 / (100 * platform_count * hw_count),
            "ports_available": available,
            "ports_used": used,
            "ports_utilization": used / available,
            "capacity_violation": False,
            "ports_violation": used > available,
        }
    ]
    if used > available:
        with pytest.raises(ValueError, match="requires .* ports for link optics"):
            NetworkExplorer.explore_network(n, library, strict_validation=True)
    else:
        assert (
            NetworkExplorer.explore_network(
                n, library, strict_validation=True
            ).get_node_utilization()
            == explorer.get_node_utilization()
        )
