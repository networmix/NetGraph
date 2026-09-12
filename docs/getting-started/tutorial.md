# Tutorial

The fastest way to run a scenario from the CLI, plus a minimal programmatic example. See the Examples section for fuller scenarios and for flow placement and failure policies.

## CLI: run and inspect

```bash
# Inspect (validate and preview structure, steps, demands)
ngraph inspect scenarios/square_mesh.yaml --detail

# Run and store results (JSON) in the current directory or under --output
ngraph run scenarios/square_mesh.yaml --output out

# Filter exported results by workflow step names
ngraph run scenarios/square_mesh.yaml --keys msd_baseline --stdout
```

See also: `scenarios/backbone_clos.yml` and `scenarios/nsfnet.yaml`.

## Programmatic: a small workflow

A three-node network, one demand, and the two steps most analyses start with: find the largest multiplier of the traffic matrix that still fits (`MaximumSupportedDemand`), then place the matrix under random single-link failures (`TrafficMatrixPlacement`).

```python
from ngraph.scenario import Scenario

scenario_yaml = """
seed: 42

network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: B, capacity: 10, cost: 1}
    - {source: B, target: C, capacity: 10, cost: 1}
    - {source: A, target: C, capacity: 5, cost: 3}

failures:
  single_link:
    modes:
      - weight: 1.0
        rules: [{scope: link, mode: choice, count: 1}]

demands:
  default:
    - {source: ^A$, target: ^C$, volume: 8, mode: pairwise, flow_policy: TE_WCMP_UNLIM}

workflow:
  - {type: MaximumSupportedDemand, name: msd, demand_set: default}
  - {type: TrafficMatrixPlacement, name: placement, demand_set: default,
     failure_policy: single_link, iterations: 20}
"""

scenario = Scenario.from_yaml(scenario_yaml)
scenario.run()
steps = scenario.results.to_dict()["steps"]

print("alpha_star:", steps["msd"]["data"]["alpha_star"])
placement = steps["placement"]["data"]
print("baseline placed:", placement["baseline"]["summary"]["total_placed"])
for pattern in placement["flow_results"]:
    failed = pattern["failure_state"]["excluded_links"]
    summary = pattern["summary"]
    print(f"  {failed} x{pattern['occurrence_count']}: "
          f"placed {summary['total_placed']:.0f} of {summary['total_demand']:.0f}")
```

```text
alpha_star: 1.875
baseline placed: 8.0
  ['B|C|0'] x8: placed 5 of 8
  ['A|C|0'] x7: placed 8 of 8
  ['A|B|0'] x5: placed 5 of 8
```

`alpha_star` is 1.875 because A can reach C with 15 units in total (10 through B plus 5 direct) and the demand is 8. The 20 failure iterations collapse into three distinct patterns; `occurrence_count` says how many iterations drew each one. Losing either link of the B path leaves only the 5-unit direct link.

## Results structure

Results have a fixed shape with `workflow`, `steps`, and `scenario` sections. Each step writes `metadata` and `data` under its name: `MaximumSupportedDemand` writes `data.alpha_star`, and `MaxFlow` and `TrafficMatrixPlacement` write a no-failure `data.baseline` plus `data.flow_results`, one entry per distinct failure pattern with its `occurrence_count`, per-flow `flows`, and a `summary`. See the [Workflow Reference](../reference/workflow.md) for every field.

## Next steps

- [Bundled Scenarios](../examples/bundled-scenarios.md) - Ready-to-run example scenarios
- [DSL Reference](../reference/dsl.md) - YAML scenario syntax
- [Workflow Reference](../reference/workflow.md) - Analysis step configuration
- [CLI Reference](../reference/cli.md) - Command-line interface details
