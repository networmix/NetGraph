from __future__ import annotations

from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.workflow.cost_power_efficiency import CostPowerEfficiency


def test_metadata_aligns_with_results_for_empty_name() -> None:
    # Build a Scenario from YAML with a BuildGraph step without explicit name
    yaml_content = """
network:
  nodes:
    A: {}
    B: {}

workflow:
  - step_type: BuildGraph
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Sanity: BuildGraph step has empty name by default
    assert scenario.workflow and (scenario.workflow[0].name == "")

    scenario.run()

    # Stored results and metadata must share the exact same step name namespace (empty string)
    graph = scenario.results.get("", "graph")
    assert graph is not None

    md = scenario.results.get_step_metadata("")
    assert md is not None
    assert md.step_name == ""
    assert md.step_type == "BuildGraph"

    # Execution order listing includes the empty-name step
    assert scenario.results.get_steps_by_execution_order() == [""]


def test_cost_power_efficiency_denominator_global_fallback_uses_latest() -> None:
    # Minimal scenario with components and one link; results is a real store
    from ngraph.components import Component, ComponentsLibrary
    from ngraph.model.network import Link, Network, Node

    net = Network()
    net.add_node(Node("A", attrs={"hardware": {"component": "NodeHW", "count": 1}}))
    net.add_node(Node("B", attrs={"hardware": {"component": "NodeHW", "count": 1}}))
    link = Link("A", "B", capacity=10.0)
    link.attrs["hardware"] = {
        "source": {"component": "LinkHW", "count": 1},
        "target": {"component": "LinkHW", "count": 1},
    }
    net.add_link(link)

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
                capex=1.0,
                power_watts=0.5,
                power_watts_max=0.75,
                capacity=100.0,
            ),
        }
    )

    scen = Scenario(network=net, workflow=[], components_library=comps)
    # Populate two prior steps that set a global key with different execution orders
    scen.results = Results()
    scen.results.put_step_metadata("s1", "Dummy", 0)
    scen.results.put("s1", "delivered", 1000.0)
    scen.results.put_step_metadata("s2", "Dummy", 1)
    scen.results.put("s2", "delivered", 2000.0)

    step = CostPowerEfficiency(
        name="cpe",
        delivered_bandwidth_gbps=None,
        delivered_bandwidth_key="delivered",
        include_disabled=True,
        collect_node_hw_entries=False,
        collect_link_hw_entries=False,
    )

    step.run(scen)

    # Denominator should come from the most recent step (s2 => 2000.0)
    assert float(scen.results.get("cpe", "delivered_bandwidth_gbps")) == 2000.0
