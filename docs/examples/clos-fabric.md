# Clos Fabric

Two sites each have four leaves and two spines. Each leaf has a capacity-100 link to each local spine. The two capacity-50 inter-site links limit total site-to-site delivery to 100; losing either inter-site link leaves 50.

## Declare the topology and traffic

Save this as `clos.yaml`:

```yaml
seed: 42
blueprints:
  fabric:
    nodes:
      leaf: {count: 4, template: "leaf{n}"}
      spine: {count: 2, template: "spine{n}"}
    links:
      - {source: /leaf, target: /spine, pattern: mesh,
         capacity: 100, cost: 1}
network:
  nodes:
    site1: {blueprint: fabric}
    site2: {blueprint: fabric}
  links:
    - source: site1/spine
      target: site2/spine
      pattern: one_to_one
      capacity: 50
      cost: 10
      attrs: {role: inter_site}
failures:
  inter_site_link:
    modes:
      - weight: 1
        rules:
          - scope: link
            mode: choice
            count: 1
            match:
              conditions:
                - {attr: role, op: "==", value: inter_site}
demands:
  traffic:
    - {id: service, source: ^site1/leaf/, target: ^site2/leaf/,
       volume: 100, preset: SHORTEST_PATHS_ECMP}
workflow:
  - {type: BuildGraph, name: topology}
  - type: MaxFlow
    name: equal_shortest_capacity
    source: ^site1/leaf/
    target: ^site2/leaf/
    preset: SHORTEST_PATHS_ECMP
    failure_policy: inter_site_link
    iterations: 20
    workers: auto
    outputs: {cost_distribution: true}
  - {type: TrafficMatrixPlacement, name: traffic, demand_set: traffic}
```

`SHORTEST_PATHS_ECMP` splits whole units equally among equal-cost next hops at each router ([Routing models and admission](../concepts.md#routing-models-and-admission)).

Blueprint expansion creates 12 nodes and 18 physical links, hence 36 directed export edges. Selectors name the leaf sets; a source's shortest route crosses one local spine, an inter-site link and a remote spine-to-leaf link, cost 1 + 10 + 1 = 12.

`pattern: mesh` links every leaf to every spine of its site, and `one_to_one` pairs the spines across sites ([`network`](../reference/dsl.md#network-topology)). The failure rule's `match` keeps the links whose `role` is `inter_site` ([Selecting nodes](../reference/dsl.md#selecting-nodes)). `failure_policy`, `iterations` and `workers` run 20 draws on every CPU ([Keys common to analysis steps](../reference/workflow.md#keys-common-to-analysis-steps)), and `outputs` asks for the cost report ([Output selection](../reference/workflow.md#output-selection)).

## Execute and inspect typed results

```python
from pathlib import Path
import netgraph_core as ngc
from ngraph import Scenario, prepare, run

scenario = Scenario.from_yaml(Path("clos.yaml").read_text())
result = run(prepare(scenario))
built, analysis, placed = [step.result for step in result.steps]
assert built.node_count == 12 and built.edge_count == 36
q = result.topology.q
baseline, *failed = analysis.cases
row = baseline.states["converged"].rows[0]
assert row.result.delivered == ngc.to_units(100, q)
assert [(piece.cost, piece.delivered_units)
        for piece in row.cost_distribution.bins] == [(12, ngc.to_units(100, q))]
assert len(failed) == 2
assert sum(case.case.occurrences for case in failed) == 20
for case in failed:
    assert len(case.case.pattern.excluded_links) == 1
    assert case.states["converged"].rows[0].result.delivered == ngc.to_units(50, q)
assert placed.cases[0].states["converged"].totals.delivered_units == ngc.to_units(100, q)
```

`result.topology.q` is the run's bandwidth unit, and `ngc.to_units(100, q)` converts 100 physical to whole units ([Units and the resolution q](../concepts.md#units-and-the-resolution-q)); every case uses that `q` ([Precision and the choice of q](../concepts.md#precision-and-the-choice-of-q)). The cost report's `bins` give the delivered units at each path cost ([Results and their units](../concepts.md#results-and-their-units)).

## Use the CLI

```bash
ngraph inspect clos.yaml --detail
ngraph run clos.yaml --output results/
ngraph run clos.yaml --keys equal_shortest_capacity --stdout --no-results
```

The filtered export retains that step's actual execution order 1 ([Filtering Results by Step Names](../reference/cli.md#filtering-results-by-step-names)); its cases are described in [Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states).

Change `preset` to `SHORTEST_PATHS_WCMP` for capacity-weighted shortest routing, `SHORTEST_PATHS_MAXFLOW` for an optimized shortest-support question, or `TE_MAXFLOW_UNLIM` for unrestricted optimized capacity. These are distinct models ([Routing models and admission](../concepts.md#routing-models-and-admission)); the symmetric baseline here is bounded by the same inter-site cut.

See [DSL](../reference/dsl.md) for grouped selection, explicit routes and hardware declarations, and [workflow](../reference/workflow.md) for MSD dependencies and optional outputs.
