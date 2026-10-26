# Tutorial

A scenario describes a network, its traffic, failure policies and an ordered workflow. Preparation turns it into one read-only graph with one bandwidth unit `q`, and a run returns typed results ([Scenario, preparation and run](../concepts.md#scenario-preparation-and-run)).

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

Each physical link carries traffic in both directions, each with its full capacity ([Links, directions and what is enabled](../concepts.md#links-directions-and-what-is-enabled)). Costs are positive integers ([link keys](../reference/dsl.md#network-topology)). Volumes and capacities are physical amounts; native bandwidth results are whole units of `q` ([Units and the resolution q](../concepts.md#units-and-the-resolution-q)).

What the other keys mean:

- `units` sets the bandwidth unit `q` (`auto`: preparation chooses it) and the precision target ([Precision and the choice of q](../concepts.md#precision-and-the-choice-of-q)).
- `failures` declares a failure policy: here, one random link fails per draw ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states); [`failures`](../reference/dsl.md#failures-failure-policies)).
- A `preset` names a model: `SHORTEST_PATHS_ECMP` splits whole units equally among equal-cost next hops at each router; `TE_MAXFLOW_UNLIM` asks for the largest flow ([Routing models and admission](../concepts.md#routing-models-and-admission)).
- `BuildGraph` and `NetworkStats` export the graph and its statistics ([Workflow Steps](../reference/workflow.md)).
- `outputs` asks for optional results: here the minimum cut and the cost report ([Output selection](../reference/workflow.md#output-selection)).
- `MaximumSupportedDemand` searches for the largest multiplier alpha of the demand volumes that the network carries in full, until the gap between a feasible and an infeasible alpha is at most `alpha_tolerance` ([Maximum supported demand](../concepts.md#maximum-supported-demand); [MaximumSupportedDemand](../reference/workflow.md#maximumsupporteddemand)).
- `alpha_from_step` places the demands at the multiplier an earlier MSD step found ([Demands: how traffic enters](../concepts.md#demands-how-traffic-enters); [TrafficMatrixPlacement](../reference/workflow.md#trafficmatrixplacement)).
- `failure_policy`, `iterations`, `workers` and `failure_trace` run that placement over 20 failure draws, on every CPU, recording the first draw of each failure pattern ([Keys common to analysis steps](../reference/workflow.md#keys-common-to-analysis-steps)).

## Run and inspect

```bash
ngraph inspect example.yaml
ngraph run example.yaml --output results/
ngraph run example.yaml --stdout --no-results
ngraph run example.yaml --profile --output results/
```

`run` writes `results/example.results.json`. `--stdout` emits pure JSON, and `--profile` reports where the run spends its time; diagnostic and step-profile reports go to stderr. The output file is replaced after complete encoding succeeds ([Command Line](../reference/cli.md#run)).

## Read results

The document has `metadata`, `units_report` and an ordered `steps` array. Each step records its normalized `question` (what it asked) and typed `result`. The `units_report` holds `q` and the run's precision ([Results and their units](../concepts.md#results-and-their-units)); each failure case's `states.converged.totals` holds the placement's totals in the converged state ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states), [Demands: how traffic enters](../concepts.md#demands-how-traffic-enters)).

```bash
jq '.steps[] | select(.name == "supported_load") | .result.alpha_feasible' results/example.results.json
jq '.steps[] | select(.name == "under_failures") | .result.cases[].states.converged.totals' results/example.results.json
```

The intact chain has physical capacity 10, cut at A→B, and route cost 3. Either single-link failure disconnects A from C. The 20 draws therefore collapse into at most two failure patterns, plus the baseline. `occurrences` sum to 20; the baseline is not an extra trial ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states)).

MSD reports its largest tested feasible alpha and every probe it made; the placement step records that it used that alpha ([Maximum supported demand](../concepts.md#maximum-supported-demand)).

To export one step, add `--keys under_failures`: the whole workflow still runs, and the step keeps its execution order 4 ([Filtering Results by Step Names](../reference/cli.md#filtering-results-by-step-names)).

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

Results belong to the returned run; topology edits after `prepare` need a new preparation ([Scenario, preparation and run](../concepts.md#scenario-preparation-and-run)). Library users can prepare selected demand sets and call `capacity`, `place`, `paths`, `edge_sensitivity` or `maximum_supported_demand` directly with typed queries ([Python API](../reference/api.md)).

Continue with [How NetGraph computes](../concepts.md), then the examples: [Basic Example](../examples/basic.md), [Clos Fabric](../examples/clos-fabric.md) and [Bundled Scenarios](../examples/bundled-scenarios.md).
