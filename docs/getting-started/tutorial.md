# Tutorial

A scenario describes an editable network, traffic, failure policies and an ordered workflow. Preparation chooses one bandwidth quantum and makes owned numerical inputs; execution returns typed results.

## Write a scenario

Save this as `example.yaml`:

```yaml
seed: 42
units: {resolution: auto, precision: 0.001}
network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: B, capacity: 10, cost: 1}
    - {source: B, target: C, capacity: 10, cost: 2}
failures:
  random_link:
    modes:
      - weight: 1
        rules:
          - {scope: link, mode: choice, count: 1}
demands:
  traffic:
    - {id: service, source: ^A$, target: ^C$, volume: 4,
       preset: SHORTEST_PATHS_ECMP}
workflow:
  - {type: BuildGraph, name: topology}
  - {type: NetworkStats, name: stats}
  - type: MaxFlow
    name: ideal_capacity
    source: ^A$
    target: ^C$
    preset: TE_MAXFLOW_UNLIM
    outputs: {min_cut: true, cost_distribution: true}
  - type: MaximumSupportedDemand
    name: supported_load
    demand_set: traffic
    alpha_tolerance: 0.01
  - type: TrafficMatrixPlacement
    name: under_failures
    demand_set: traffic
    alpha_from_step: supported_load
    failure_policy: random_link
    iterations: 20
    workers: auto
    failure_trace: true
```

Each physical link carries traffic in both directions. Costs must be positive integers. Volumes and capacities are physical quantities; results use integer units and retain their quantum for display.

## Run and inspect

```bash
ngraph inspect example.yaml
ngraph run example.yaml --output results/
ngraph run example.yaml --stdout --no-results
ngraph run example.yaml --profile --output results/
```

`run` writes `results/example.results.json`. `--stdout` emits pure JSON; diagnostic and step-profile reports go to stderr. The output file is replaced after complete encoding succeeds.

## Read results

The document has `metadata`, `units_report` and an ordered `steps` array. Each step records its normalized `question` and typed `result`.

```bash
jq '.steps[] | select(.name == "supported_load") | .result.alpha_feasible' results/example.results.json
jq '.steps[] | select(.name == "under_failures") | .result.cases[].states.converged.totals' results/example.results.json
```

The intact chain has physical capacity 10, cut at A→B, and route cost 3. Either single-link failure disconnects A from C. The 20 draws therefore collapse into at most two failure patterns, plus the baseline. `occurrences` sum to 20; the baseline is not an extra trial.

MSD reports its largest tested feasible factor and complete probe history. Its result distinguishes search bounds, iteration limits, stagnation and numeric range refusal. An upper certificate is present only for a proved monotone class. The placement step records that it used the earlier step's feasible factor.

To export one step, add `--keys under_failures`. The complete workflow still executes; the selected step retains its actual execution order 4. Filtered exports can have gaps, while the full run is contiguous.

## Use Python

```python
from pathlib import Path
from ngraph import Scenario, prepare, run, write_json

scenario = Scenario.from_yaml(Path("example.yaml").read_text())
prepared = prepare(scenario)
result = run(prepared)
for step in result.steps:
    print(step.name, step.step_type)
with open("python-results.json", "w") as destination:
    write_json(result, destination)
```

Results belong to the returned run. `Scenario` keeps declarations; later topology edits require another preparation. Library users can prepare selected demand sets and call `capacity`, `place`, `paths`, `edge_sensitivity` or `maximum_supported_demand` directly with typed queries.

Continue with the [basic API example](../examples/basic.md), [Clos topology](../examples/clos-fabric.md), [DSL reference](../reference/dsl.md) and [workflow reference](../reference/workflow.md).
