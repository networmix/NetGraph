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
from ngraph import Network, Node, Link, analyze, Mode

# Three nodes in a line
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

For reproducible analysis workflows, define topology, demands, and failure policies in YAML:

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
jq '.steps.max_demand.data.alpha_star' results/scenario.results.json
```

The scenario builds two Clos sites from one blueprint, finds the largest demand multiplier the network carries, then places that demand under 100 random single-link failures and writes the results to JSON.

See [DSL Reference](https://networmix.github.io/NetGraph/reference/dsl/) and [Examples](https://networmix.github.io/NetGraph/examples/clos-fabric/) for more.

## Capabilities

- **Declarative scenarios**: schema-validated YAML, reusable blueprints, a strict multigraph model
- **Failure analysis**: weighted failure modes, risk groups, and analysis-time exclusions that leave the base topology untouched
- **Routing models**: cost-only IP routing and capacity-aware traffic engineering
- **Flow placement**: ECMP and WCMP splits, max-flow and demand placement
- **Reproducible results**: seeded randomness and stable link ids
- **C++ algorithms** with the GIL released, via [NetGraph-Core](https://github.com/networmix/NetGraph-Core)

## Documentation

- [**Tutorial**](https://networmix.github.io/NetGraph/getting-started/tutorial/) - Running a scenario from the CLI and from Python
- [**Examples**](https://networmix.github.io/NetGraph/examples/clos-fabric/) - Clos fabric capacity and failure analysis
- [**DSL Reference**](https://networmix.github.io/NetGraph/reference/dsl/) - YAML scenario syntax
- [**API Reference**](https://networmix.github.io/NetGraph/reference/api/) - Python API

## License

[MIT License](LICENSE)

## Requirements

- Python 3.11+
- NetGraph-Core (installed automatically)
