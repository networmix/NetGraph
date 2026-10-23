from __future__ import annotations

import json
from dataclasses import replace
from io import StringIO

from ngraph.export import write_json
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.cost_power import CostPower


def test_metadata_aligns_with_results_for_empty_name() -> None:
    # Build a Scenario from YAML with a BuildGraph step without explicit name
    yaml_content = """
network:
  nodes:
    A: {}
    B: {}

workflow:
  - type: BuildGraph
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Default step naming assigns a unique non-empty name like "BuildGraph_0"
    assert scenario.workflow
    step_name = scenario.workflow[0].name
    assert isinstance(step_name, str) and step_name != ""

    result = run(prepare(scenario))
    step = result.steps[0]
    assert step.name == step_name
    assert step.step_type == "BuildGraph"
    assert step.execution_order == 0
    assert step.question is scenario.workflow[0]
    assert step.result.node_count == 2
    output = StringIO()
    write_json(result, output)
    exported = json.loads(output.getvalue())["steps"]
    assert [row["name"] for row in exported] == [step_name]
    assert exported[0]["result"]["graph"]["nodes"] == [
        {"id": "A", "disabled": False},
        {"id": "B", "disabled": False},
    ]


def test_cost_power_collects_levels_schema_smoke() -> None:
    # Minimal scenario with components and one link.
    from ngraph.model.components import Component, ComponentsLibrary
    from ngraph.model.network import Link, Network, Node

    net = Network()
    net.add_node(Node("A", attrs={"hardware": {"component": "NodeHW", "count": 1}}))
    net.add_node(Node("B", attrs={"hardware": {"component": "NodeHW", "count": 1}}))
    link = Link("A", "B", capacity=10.0)
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

    step = CostPower(name="cpe", include_disabled=True, aggregation_level=1)
    scen = Scenario(network=net, workflow=(step,), components_library=comps)
    result = run(prepare(scen))
    data = result.steps[0].result
    assert result.steps[0].question is step
    assert data.include_disabled is True and data.aggregation_level == 1
    assert tuple(data.levels) == (0, 1)
    root = data.levels[0]
    assert len(root) == 1
    assert root[0].capex_total == 202
    assert root[0].power_total_watts == 21
    output = StringIO()
    write_json(result, output)
    wire = json.loads(output.getvalue())["steps"][0]["result"]
    assert [row["level"] for row in wire["levels"]] == [0, 1]
    assert wire["levels"][0]["rows"][0]["capex_total"] == 202
