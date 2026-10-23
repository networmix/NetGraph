from __future__ import annotations

from dataclasses import replace

import pytest

from ngraph.explorer import NetworkExplorer
from ngraph.model.components import Component, ComponentsLibrary
from ngraph.model.network import Link, Network, Node
from ngraph.results import HardwareRow, RunResult
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.cost_power import CostPower


def _build_simple_components() -> ComponentsLibrary:
    comps = ComponentsLibrary(
        components={
            "NodeHW": Component(
                name="NodeHW",
                component_type="chassis",
                capex=100.0,
                power_watts=10.0,
                power_watts_max=12.0,
                capacity=100.0,
            ),
            "LinkHW": Component(
                name="LinkHW",
                component_type="optic",
                capex=1.5,
                power_watts=0.5,
                power_watts_max=0.75,
                capacity=100.0,
            ),
        }
    )
    return comps


def _extract_root(results: RunResult, step: str) -> HardwareRow:
    value = next(row.result for row in results.steps if row.name == step)
    root_entries = value.levels[0]
    assert len(root_entries) == 1 and isinstance(root_entries[0], HardwareRow)
    return root_entries[0]


def test_cost_power_basic_aggregation_active() -> None:
    net = Network()
    # Two nodes under same hierarchy path 'dc1/leaf'
    net.add_node(
        Node("dc1/leaf/A", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )
    net.add_node(
        Node("dc1/leaf/B", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )

    # One link with optics on both ends
    link = Link("dc1/leaf/A", "dc1/leaf/B", capacity=10.0)
    net.add_link(
        replace(
            link,
            attrs={
                "hardware": {
                    "source": {"component": "LinkHW", "count": 1},
                    "target": {"component": "LinkHW", "count": 1},
                }
            },
        )
    )

    comps = _build_simple_components()

    step = CostPower(name="cp", include_disabled=False, aggregation_level=2)
    exported = run(prepare(Scenario(net, (step,), components_library=comps)))

    data = exported.steps[0].result
    assert data.include_disabled is False
    assert data.aggregation_level == 2

    # Root totals: platform=2*100, optics=2*1.5; power: platform=2*10, optics=2*0.5
    root = _extract_root(exported, "cp")
    assert root.platform_capex == pytest.approx(200.0)
    assert root.optics_capex == pytest.approx(3.0)
    assert root.platform_power_watts == pytest.approx(20.0)
    assert root.optics_power_watts == pytest.approx(1.0)
    assert root.capex_total == pytest.approx(203.0)
    assert root.power_total_watts == pytest.approx(21.0)

    # Level 1 should contain a single path 'dc1'
    lvl1 = {row.path: row for row in data.levels[1]}
    assert set(lvl1.keys()) == {"dc1"}
    assert lvl1["dc1"].capex_total == pytest.approx(203.0)

    # Level 2 should contain a single path 'dc1/leaf'
    lvl2 = {row.path: row for row in data.levels[2]}
    assert set(lvl2.keys()) == {"dc1/leaf"}
    assert lvl2["dc1/leaf"].platform_capex == pytest.approx(200.0)


def test_cost_power_include_disabled_filters_active_view() -> None:
    net = Network()
    net.add_node(
        Node("dc1/leaf/A", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )
    net.add_node(
        Node(
            "dc1/leaf/B",
            disabled=True,
            attrs={"hardware": {"component": "NodeHW", "count": 1}},
        )
    )

    # Link between A and B with optics. In active view, link is skipped because B disabled.
    link = Link("dc1/leaf/A", "dc1/leaf/B", capacity=10.0)
    net.add_link(
        replace(
            link,
            attrs={
                "hardware": {
                    "source": {"component": "LinkHW", "count": 1},
                    "target": {"component": "LinkHW", "count": 1},
                }
            },
        )
    )

    comps = _build_simple_components()

    step = CostPower(name="cp2", include_disabled=False, aggregation_level=1)
    exported = run(prepare(Scenario(net, (step,), components_library=comps)))

    root = _extract_root(exported, "cp2")
    # Only node A contributes platform; optics skipped (link inactive due to disabled endpoint)
    assert root.platform_capex == pytest.approx(100.0)
    assert root.platform_power_watts == pytest.approx(10.0)
    assert root.optics_capex == pytest.approx(0.0)
    assert root.optics_power_watts == pytest.approx(0.0)


def test_cost_power_optics_ignored_when_endpoint_has_no_hw() -> None:
    net = Network()
    net.add_node(
        Node("dc1/leaf/A", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )
    net.add_node(Node("dc1/leaf/C"))  # No hardware

    # Link A->C has optics on both ends; only A endpoint counts optics
    link = Link("dc1/leaf/A", "dc1/leaf/C", capacity=5.0)
    net.add_link(
        replace(
            link,
            attrs={
                "hardware": {
                    "source": {"component": "LinkHW", "count": 1},
                    "target": {"component": "LinkHW", "count": 1},
                }
            },
        )
    )

    comps = _build_simple_components()

    step = CostPower(name="cp3", include_disabled=False, aggregation_level=0)
    exported = run(prepare(Scenario(net, (step,), components_library=comps)))

    root = _extract_root(exported, "cp3")
    # Platform: node A only; Optics: only source endpoint at A
    assert root.platform_capex == pytest.approx(100.0)
    assert root.platform_power_watts == pytest.approx(10.0)
    assert root.optics_capex == pytest.approx(1.5)
    assert root.optics_power_watts == pytest.approx(0.5)


def test_cost_power_runs_despite_hardware_capacity_violation() -> None:
    """CostPower aggregates costs even when hardware validation would fail.

    The step must not depend on a strict-validation NetworkExplorer: a node
    whose attached link capacity exceeds its hardware capacity must not stop
    the cost aggregation.
    """
    net = Network()
    net.add_node(
        Node("dc1/leaf/A", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )
    net.add_node(
        Node("dc1/leaf/B", attrs={"hardware": {"component": "NodeHW", "count": 1}})
    )

    # NodeHW supports 100.0 of capacity; a 500.0 link exceeds it on both ends.
    link = Link("dc1/leaf/A", "dc1/leaf/B", capacity=500.0)
    net.add_link(
        replace(
            link,
            attrs={
                "hardware": {
                    "source": {"component": "LinkHW", "count": 1},
                    "target": {"component": "LinkHW", "count": 1},
                }
            },
        )
    )

    comps = _build_simple_components()

    # Sanity check: explorer strict validation rejects this network, so the
    # step cannot be relying on it.
    with pytest.raises(ValueError, match="exceeds hardware"):
        NetworkExplorer.explore_network(net, components_library=comps)

    step = CostPower(name="cp4", include_disabled=False, aggregation_level=2)
    exported = run(prepare(Scenario(net, (step,), components_library=comps)))

    root = _extract_root(exported, "cp4")
    assert root.platform_capex == pytest.approx(200.0)
    assert root.platform_power_watts == pytest.approx(20.0)
    assert root.optics_capex == pytest.approx(3.0)
    assert root.optics_power_watts == pytest.approx(1.0)

    # Hierarchy paths derive from node names directly.
    data = exported.steps[0].result
    lvl2 = {row.path for row in data.levels[2]}
    assert lvl2 == {"dc1/leaf"}
