# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Network modeling and analysis framework combining Python with high-performance C++ graph algorithms.

## What It Does

NetGraph lets you model network topologies, traffic demands, and failure scenarios - then analyze capacity and resilience. Define networks in Python or declarative YAML, run max-flow and failure simulations, and export reproducible JSON results. Compute-intensive algorithms run in C++ with the GIL released.

## Install

```bash
pip install ngraph
```

## Python API

```python
from ngraph import Network, Node, Link, analyze, Mode

# Build a simple network
network = Network()
network.add_node(Node("A"))
network.add_node(Node("B"))
network.add_node(Node("C"))
network.add_link(Link("A", "B", capacity=10.0, cost=1.0))
network.add_link(Link("B", "C", capacity=10.0, cost=1.0))

# Compute max flow
result = analyze(network).max_flow("^A$", "^C$", mode=Mode.COMBINE)
print(result)  # {('^A$', '^C$'): 10.0}
```

## Scenario DSL

For reproducible analysis workflows, define topology, traffic, demands, and failure policies in YAML:

```yaml
seed: 42

# Define reusable topology templates
blueprints:
  Clos_Fabric:
    nodes:
      spine: { count: 2, template: "spine{n}" }
      leaf: { count: 4, template: "leaf{n}" }
    links:
      - source: /leaf
        target: /spine
        pattern: mesh
        capacity: 100
        cost: 1

# Instantiate network from templates
network:
  nodes:
    site1: { blueprint: Clos_Fabric }
    site2: { blueprint: Clos_Fabric }
  links:
    - source: { path: site1/spine }
      target: { path: site2/spine }
      pattern: one_to_one
      capacity: 50
      cost: 10

# Define failure policy for Monte Carlo analysis
failures:
  random_link:
    modes:
      - weight: 1.0
        rules:
          - scope: link
            mode: choice
            count: 1

# Define traffic demands
demands:
  global_traffic:
    - source: ^site1/leaf/
      target: ^site2/leaf/
      volume: 100.0
      mode: combine
      flow_policy: SHORTEST_PATHS_ECMP

# Analysis workflow: find max capacity, then test under failures
workflow:
  - type: NetworkStats
    name: stats
  - type: MaxFlow
    name: site_capacity
    source: ^site1/leaf/
    target: ^site2/leaf/
    mode: combine
  - type: MaximumSupportedDemand
    name: max_demand
    demand_set: global_traffic
  - type: TrafficMatrixPlacement
    name: placement_at_max
    demand_set: global_traffic
    alpha_from_step: max_demand # Use alpha_star from MSD step
    failure_policy: random_link
    iterations: 100
```

```bash
ngraph run scenario.yml --output results/
```

This scenario builds a dual-site Clos fabric from blueprints, finds the maximum supportable demand, then runs 100 Monte Carlo iterations with random link failures - exporting results to JSON.

See [DSL Reference](https://networmix.github.io/NetGraph/reference/dsl/) and [Examples](https://networmix.github.io/NetGraph/examples/clos-fabric/) for more.

## Capabilities

- **Declarative scenarios** with schema validation, reusable blueprints, and strict multigraph representation
- **Failure analysis** via policy engine with weighted modes, risk groups, and non-destructive runtime exclusions
- **Routing modes** for IP routing (cost-based) and traffic engineering (capacity-aware)
- **Flow placement** strategies for ECMP and WCMP with max-flow and capacity envelopes
- **Reproducible results** via seeded randomness and stable edge IDs
- **C++ performance** with GIL released via [NetGraph-Core](https://github.com/networmix/NetGraph-Core)

## Documentation

- [**Tutorial**](https://networmix.github.io/NetGraph/getting-started/tutorial/) - Getting started guide
- [**Examples**](https://networmix.github.io/NetGraph/examples/clos-fabric/) - Clos fabric, failure analysis, and more
- [**DSL Reference**](https://networmix.github.io/NetGraph/reference/dsl/) - YAML scenario syntax
- [**API Reference**](https://networmix.github.io/NetGraph/reference/api/) - Python API docs

## License

[GNU Affero General Public License v3.0 or later](LICENSE)

## Requirements

- Python 3.11+
- NetGraph-Core (installed automatically)
