"""Regression tests for NetworkExplorer.

Covers:
- whole-network and subtree BOMs.
- get_node_utilization covers enabled nodes only.
- Node utilization and strict validation computed via the O(E) adjacency pre-pass.
- External link details name the opposite endpoint's full path.
"""

from __future__ import annotations

import pytest

from ngraph.explorer import NetworkExplorer
from ngraph.model.components import Component, ComponentsLibrary
from ngraph.model.network import Link, Network, Node


def _library() -> ComponentsLibrary:
    lib = ComponentsLibrary()
    lib.components["box"] = Component(
        name="box",
        capex=100.0,
        power_watts=10.0,
        capacity=1000.0,
        ports=8,
    )
    lib.components["optic"] = Component(
        name="optic",
        capex=5.0,
        power_watts=1.0,
        capacity=100.0,
        ports=1,
    )
    return lib


def _network_with_hw() -> Network:
    net = Network()
    net.nodes["dc1/a"] = Node(name="dc1/a", attrs={"hardware": {"component": "box"}})
    net.nodes["dc2/b"] = Node(name="dc2/b", attrs={"hardware": {"component": "box"}})
    net.links["L1"] = Link(source="dc1/a", target="dc2/b", capacity=100.0)
    return net


class TestSubtreeBom:
    """The whole-network BOM and each subtree's own BOM."""

    def test_root_and_subtree_boms(self) -> None:
        explorer = NetworkExplorer.explore_network(
            _network_with_hw(), components_library=_library()
        )
        root = explorer.root_node
        assert root is not None
        assert explorer.get_bom() == dict(root.stats.bom) == {"box": 2.0}
        assert dict(root.children["dc1"].stats.bom) == {"box": 1.0}
        assert dict(root.children["dc2"].children["b"].stats.bom) == {"box": 1.0}


class TestGetNodeUtilizationEnabledOnly:
    """Utilization snapshots cover enabled nodes only."""

    def test_disabled_nodes_have_no_snapshot(self) -> None:
        net = _network_with_hw()
        net.disable_node("dc2/b")
        explorer = NetworkExplorer.explore_network(net, components_library=_library())
        utils = explorer.get_node_utilization()
        assert [u.node_name for u in utils] == ["dc1/a"]


class TestUtilizationAdjacencyPrePass:
    """Node utilization computed via the per-node adjacency index."""

    def test_disabled_links_and_endpoints_excluded(self) -> None:
        net = Network()
        net.nodes["A"] = Node(name="A", attrs={"hardware": {"component": "box"}})
        net.nodes["B"] = Node(name="B")
        net.nodes["C"] = Node(name="C", disabled=True)
        net.links["L1"] = Link(source="A", target="B", capacity=100.0)
        net.links["L2"] = Link(source="B", target="A", capacity=50.0)
        # Disabled link: ignored.
        net.links["L3"] = Link(source="A", target="B", capacity=70.0, disabled=True)
        # Opposite endpoint disabled: ignored in active view.
        net.links["L4"] = Link(source="A", target="C", capacity=30.0)

        explorer = NetworkExplorer.explore_network(net, components_library=_library())
        utils = {u.node_name: u for u in explorer.get_node_utilization()}
        assert utils["A"].attached_capacity_active == pytest.approx(150.0)
        assert utils["A"].capacity_utilization == pytest.approx(0.15)
        assert not utils["A"].capacity_violation

    def test_self_loop_counted_once(self) -> None:
        net = Network()
        net.nodes["A"] = Node(name="A", attrs={"hardware": {"component": "box"}})
        net.links["L1"] = Link(source="A", target="A", capacity=40.0)

        explorer = NetworkExplorer.explore_network(net, components_library=_library())
        utils = {u.node_name: u for u in explorer.get_node_utilization()}
        assert utils["A"].attached_capacity_active == pytest.approx(40.0)

    def test_ports_usage_from_per_end_optics(self) -> None:
        net = Network()
        net.nodes["A"] = Node(name="A", attrs={"hardware": {"component": "box"}})
        net.nodes["B"] = Node(name="B", attrs={"hardware": {"component": "box"}})
        net.links["L1"] = Link(
            source="A",
            target="B",
            capacity=100.0,
            attrs={
                "hardware": {
                    "source": {"component": "optic", "count": 2},
                    "target": {"component": "optic", "count": 3},
                }
            },
        )

        explorer = NetworkExplorer.explore_network(net, components_library=_library())
        utils = {u.node_name: u for u in explorer.get_node_utilization()}
        assert utils["A"].ports_used == pytest.approx(2.0)
        assert utils["B"].ports_used == pytest.approx(3.0)
        assert utils["A"].ports_available == pytest.approx(8.0)
        assert utils["A"].ports_utilization == pytest.approx(0.25)

    def test_capacity_violation_still_raises_in_strict_mode(self) -> None:
        net = Network()
        net.nodes["A"] = Node(name="A", attrs={"hardware": {"component": "box"}})
        net.nodes["B"] = Node(name="B")
        net.links["L1"] = Link(source="A", target="B", capacity=1500.0)

        with pytest.raises(ValueError, match="total attached capacity"):
            NetworkExplorer.explore_network(net, components_library=_library())


class TestExternalLinkPathAttribution:
    """External link details must name the opposite endpoint's full path."""

    def test_external_details_after_path_hoist(self) -> None:
        explorer = NetworkExplorer.explore_network(
            _network_with_hw(), components_library=_library()
        )
        root = explorer.root_node
        assert root is not None
        dc1 = root.children["dc1"]
        dc2 = root.children["dc2"]

        for stats in (dc1.stats, dc1.active_stats):
            assert stats.external_link_count == 1
            assert set(stats.external_link_details) == {"dc2/b"}
            assert stats.external_link_details["dc2/b"].link_capacity == pytest.approx(
                100.0
            )
        for stats in (dc2.stats, dc2.active_stats):
            assert set(stats.external_link_details) == {"dc1/a"}
