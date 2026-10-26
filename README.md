# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Network modeling and analysis framework: Python front end, C++ graph algorithms.

## What It Does

NetGraph models network topologies, traffic demands and failure scenarios, and analyzes capacity and resilience. Networks are defined in Python or in YAML; max-flow and failure simulations export reproducible JSON.

## Install

```bash
pip install ngraph
```

## Python API

```python
from ngraph import (
    CapacityQuery, Link, Network, Node, Scenario, Selector, UnitsSettings,
    capacity, prepare,
)

# Three nodes in a line, joined by links of capacity 10
network = Network()
for name in ("A", "B", "C"):
    network.add_node(Node(name))
network.add_link(Link("A", "B", capacity=10))
network.add_link(Link("B", "C", capacity=10))

# Prepare the graph once, with a bandwidth unit q of 1.
prepared = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
result = capacity(prepared, CapacityQuery(Selector("^A$"), Selector("^C$")))
row = result.cases[0].states["converged"].rows[0]
print(row.result.delivered)
```

<!-- example: output -->

```text
10
```

It prints 10: native bandwidth results are whole units of one bandwidth unit `q`, and `UnitsSettings(resolution=1)` sets `q` to 1 ([Units and the resolution q](https://networmix.github.io/NetGraph/concepts/#units-and-the-resolution-q)). A `CapacityQuery` without a model asks for the most that optimized traffic engineering carries from the sources to the targets (`TE_MAXFLOW_UNLIM`); `cases[0]` is the case without failures, `states["converged"]` its one state and `rows[0]` the A-to-C answer ([Failures: patterns, cases and states](https://networmix.github.io/NetGraph/concepts/#failures-patterns-cases-and-states)). For capacities this small, `q` = 1 misses the default precision target although nothing is rounded, and `prepared.units_report.target_met` is false ([Precision and the choice of q](https://networmix.github.io/NetGraph/concepts/#precision-and-the-choice-of-q)).

## Scenario DSL

For reproducible analysis workflows, define topology, demands, and failure policies in YAML (this is `scenarios/readme_example.yml`):

```yaml
# Two Clos sites built from one blueprint and joined spine to spine. The workflow finds
# the largest tested feasible demand multiplier (alpha), then places the demands at that
# alpha under 100 draws of one random link failure.
seed: 42

# A reusable topology template
blueprints:
  Clos_Fabric:
    nodes:
      spine: {count: 2, template: "spine{n}"}
      leaf: {count: 4, template: "leaf{n}"}
    links:
      - {source: /leaf, target: /spine, pattern: mesh, capacity: 100}

# Two instances of the template, linked spine to spine
network:
  nodes:
    site1: {blueprint: Clos_Fabric}
    site2: {blueprint: Clos_Fabric}
  links:
    - {source: site1/spine, target: site2/spine, pattern: one_to_one, capacity: 50}

# One random link fails per draw
failures:
  random_link:
    modes:
      - weight: 1
        rules:
          - {scope: link, mode: choice, count: 1}

# Traffic from the leaves of site1 to the leaves of site2
demands:
  global_traffic:
    - {source: ^site1/leaf/, target: ^site2/leaf/, volume: 100, preset: SHORTEST_PATHS_ECMP}

workflow:
  - type: MaximumSupportedDemand
    name: max_demand
    demand_set: global_traffic
  - type: TrafficMatrixPlacement
    name: placement_at_max
    demand_set: global_traffic
    alpha_from_step: max_demand  # its largest tested feasible alpha
    failure_policy: random_link
    iterations: 100
```

```bash
ngraph run scenarios/readme_example.yml --output results/
jq '.steps[] | select(.name == "max_demand") | .result.alpha_feasible.value' results/readme_example.results.json
```

A preset chooses routing and admission; `SHORTEST_PATHS_ECMP` splits whole units equally among equal-cost next hops at each router ([Routing models and admission](https://networmix.github.io/NetGraph/concepts/#routing-models-and-admission)). [How NetGraph computes](https://networmix.github.io/NetGraph/concepts/) explains the presets such as `SHORTEST_PATHS_ECMP`, maximum supported demand and the numbers in the results; `run(prepare(scenario))` returns the same results in Python.

## Capabilities

- **Declarative scenarios**: schema-validated YAML and reusable blueprints
- **Failure analysis**: weighted failure modes, risk groups, and analysis-time exclusions that leave the base topology untouched
- **Routing models**: cost-only IP routing and capacity-aware traffic engineering
- **Traffic placement**: ECMP and WCMP splits, maximum flow and demand placement
- **Reproducible results**: seeded randomness and stable link ids
- **C++ algorithms** with the GIL released, via [NetGraph-Core](https://github.com/networmix/NetGraph-Core)

## Documentation

- [**Tutorial**](https://networmix.github.io/NetGraph/getting-started/tutorial/) - Running a scenario from the CLI and from Python
- [**How NetGraph computes**](https://networmix.github.io/NetGraph/concepts/) - How a scenario becomes numbers
- [**Examples**](https://networmix.github.io/NetGraph/examples/basic/) - From a four-node network to the bundled scenarios
- [**Scenario YAML**](https://networmix.github.io/NetGraph/reference/dsl/) - Every scenario key
- [**Python API**](https://networmix.github.io/NetGraph/reference/api/) - The library by task

## License

[MIT License](LICENSE)

## Requirements

- Python 3.11+
- NetGraph-Core (installed automatically)
