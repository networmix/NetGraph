from __future__ import annotations

from unittest.mock import MagicMock

from ngraph.components import Component, ComponentsLibrary
from ngraph.model.network import Link, Network, Node
from ngraph.workflow.cost_power_efficiency import CostPowerEfficiency


def _basic_components() -> ComponentsLibrary:
    lib = ComponentsLibrary(
        components={
            "NodeHW": Component(
                name="NodeHW",
                component_type="chassis",
                capex=1000.0,
                power_watts=100.0,
                power_watts_max=120.0,
                capacity=100.0,
            ),
            "LinkHW": Component(
                name="LinkHW",
                component_type="optic",
                capex=10.0,
                power_watts=1.0,
                power_watts_max=1.5,
                capacity=100.0,
            ),
        }
    )
    return lib


def _scenario_stub() -> MagicMock:
    scenario = MagicMock()
    scenario.network = Network()
    scenario.results = MagicMock()
    scenario.results.put = MagicMock()
    scenario.results.get = MagicMock(side_effect=KeyError("missing"))
    scenario.components_library = _basic_components()

    # Nodes with hardware
    scenario.network.add_node(Node("A", attrs={"hw_component": "NodeHW"}))
    scenario.network.add_node(Node("B", attrs={"hw_component": "NodeHW"}))

    # One enabled link with hardware and capacity
    link = Link("A", "B", capacity=30.0)
    link.attrs["hw_component"] = "LinkHW"
    scenario.network.add_link(link)

    return scenario


def test_collect_node_hw_entries_basic() -> None:
    scenario = _scenario_stub()

    step = CostPowerEfficiency(
        name="cpe",
        delivered_bandwidth_gbps=1000.0,
        include_disabled=True,
        collect_node_hw_entries=True,
        collect_link_hw_entries=False,
    )

    step.run(scenario)

    # Gather stored values
    calls = {c.args[1]: c.args[2] for c in scenario.results.put.call_args_list}

    assert "node_hw_entries" in calls
    entries = calls["node_hw_entries"]
    assert isinstance(entries, list) and len(entries) == 2

    by_node = {e["node"]: e for e in entries}

    # Node hardware capacity should reflect component total * count (1)
    assert by_node["A"]["hw_capacity"] == 100.0
    assert by_node["B"]["hw_capacity"] == 100.0

    # Allocated capacity is sum of incident link capacities (bidirectional model
    # is represented as single directed link in Network object)
    assert by_node["A"]["allocated_capacity"] == 30.0
    assert by_node["B"]["allocated_capacity"] == 30.0

    # Power metrics present
    assert by_node["A"]["power_watts"] == 100.0
    assert by_node["A"]["power_watts_max"] == 120.0


def test_collect_link_hw_entries_basic() -> None:
    scenario = _scenario_stub()

    step = CostPowerEfficiency(
        name="cpe",
        delivered_bandwidth_gbps=1000.0,
        include_disabled=False,
        collect_node_hw_entries=False,
        collect_link_hw_entries=True,
    )

    step.run(scenario)

    calls = {c.args[1]: c.args[2] for c in scenario.results.put.call_args_list}

    assert "link_hw_entries" in calls
    entries = calls["link_hw_entries"]
    assert isinstance(entries, list) and len(entries) == 1

    entry = entries[0]
    assert entry["source"] == "A"
    assert entry["target"] == "B"
    assert entry["capacity"] == 30.0
    assert entry["hw_component"] == "LinkHW"
    assert entry["hw_capacity"] == 100.0
    assert entry["power_watts"] == 1.0
    assert entry["power_watts_max"] == 1.5
