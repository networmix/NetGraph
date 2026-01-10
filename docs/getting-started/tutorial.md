# Tutorial

This guide shows the fastest way to run a scenario from the CLI and a minimal programmatic example. See the Examples section for detailed scenarios and policies.

## CLI: run and inspect

```bash
# Inspect (validate and preview structure, steps, demands)
ngraph inspect scenarios/square_mesh.yaml --detail

# Run and store results (JSON) next to the scenario or under --output
ngraph run scenarios/square_mesh.yaml --output out

# Filter exported results by workflow step names
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout
```

See also: `scenarios/backbone_clos.yml` and `scenarios/nsfnet.yaml`.

## Programmatic: minimal example

```python
from ngraph.scenario import Scenario

scenario_yaml = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - {source: A, target: B, capacity: 10.0, cost: 1.0}
workflow:
  - type: NetworkStats
    name: baseline_stats
"""

scenario = Scenario.from_yaml(scenario_yaml)
scenario.run()

exported = scenario.results.to_dict()
print(list(exported["steps"].keys()))
```

## Results structure

Results are exported with a fixed structure containing `workflow`, `steps`, and `scenario` sections. Steps such as `MaxFlow`, `TrafficMatrixPlacement`, and `MaximumSupportedDemand` write their outputs under their step name. See the Workflow Reference for field details.

## Next steps

- [Bundled Scenarios](../examples/bundled-scenarios.md) - Ready-to-run example scenarios
- [DSL Reference](../reference/dsl.md) - YAML scenario syntax
- [Workflow Reference](../reference/workflow.md) - Analysis step configuration
- [CLI Reference](../reference/cli.md) - Command-line interface details
