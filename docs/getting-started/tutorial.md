# Quickstart

This guide shows the fastest way to run a scenario from the CLI and a minimal programmatic example. Use examples for detailed scenarios and policies.

## CLI: run and inspect

```bash
# Inspect (validate and preview structure, steps, matrices)
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
    - {source: A, target: B, link_params: {capacity: 10.0, cost: 1.0}}
workflow:
  - step_type: NetworkStats
    name: baseline_stats
"""

scenario = Scenario.from_yaml(scenario_yaml)
scenario.run()

exported = scenario.results.to_dict()
print(list(exported["steps"].keys()))
```

## Results shape (high level)

Results are exported as a fixed shape with `workflow`, `steps`, and `scenario`. Steps such as `MaxFlow`, `TrafficMatrixPlacement`, and `MaximumSupportedDemand` write under their step name. See Reference → Workflow for exact fields.

## Next steps

- Examples → Bundled Scenarios
- Reference → DSL, Workflow, CLI
