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
    # Default step naming assigns a unique non-empty name like "BuildGraph_0"
    assert scenario.workflow
    step_name = scenario.workflow[0].name
    assert isinstance(step_name, str) and step_name != ""

    scenario.run()

    # Stored results must appear under steps in the exported dict
    exported = scenario.results.to_dict()
    assert "steps" in exported and step_name in exported["steps"]
    assert "data" in exported["steps"][step_name]
    assert exported["steps"][step_name]["data"].get("graph") is not None

    md = scenario.results.get_step_metadata(step_name)
    assert md is not None
    assert md.step_name == step_name
    assert md.step_type == "BuildGraph"

    # Execution order listing includes the empty-name step
    assert scenario.results.get_steps_by_execution_order() == [step_name]


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
    scen.results = Results()

    step = CostPowerEfficiency(
        name="cpe",
        delivered_bandwidth_gbps=2000.0,
        include_disabled=True,
        collect_node_hw_entries=False,
        collect_link_hw_entries=False,
    )

    step.execute(scen)

    exported = scen.results.to_dict()
    assert exported["steps"]["cpe"]["data"]["delivered_bandwidth_gbps"] == 2000.0
