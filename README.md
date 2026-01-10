# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Scenario-driven network modeling and analysis framework combining Python with C++ graph algorithms.

## Overview

NetGraph enables declarative modeling of network topologies, traffic matrices, and failure scenarios. It delegates computationally intensive graph algorithms to [NetGraph-Core](https://github.com/networmix/NetGraph-Core) while providing a Python API and CLI for orchestration.

## Architecture

NetGraph employs a **hybrid Python+C++ architecture**:

- **Python layer (NetGraph)**: Scenario DSL parsing, workflow orchestration, result aggregation, and high-level APIs.
- **C++ layer (NetGraph-Core)**: Graph algorithms (SPF, KSP, Max-Flow) executing in C++ with the GIL released.

## Key Features

### 1. Modeling & DSL

- **Declarative Scenarios**: Define topology, traffic, and workflows in validated YAML.
- **Blueprints**: Reusable topology templates (e.g., Clos fabrics, regions) with parameterized expansion.
- **Directed Multigraph**: Deterministic graph representation with stable edge IDs.

### 2. Failure Analysis

- **Policy Engine**: Weighted failure modes with multiple policy rules per mode.
- **Non-Destructive**: Runtime exclusions simulate failures without modifying the base topology.
- **Risk Groups**: Model shared fate (e.g., fiber cuts, power zones).

### 3. Traffic Engineering

- **Routing Modes**: Cost-based routing (shortest paths, ignores capacity) and capacity-aware routing (considers residual capacity).
- **Flow Placement**: Strategies for **ECMP** (Equal-Cost Multi-Path) and **WCMP** (Weighted Cost Multi-Path).
- **Capacity Analysis**: Compute max-flow envelopes and demand allocation with configurable placement policies.

### 4. Workflow & Integration

- **Structured Results**: Export analysis artifacts to JSON for downstream processing.
- **CLI**: Command-line interface for validation and execution.
- **Python API**: Programmatic access to modeling and analysis capabilities.

## Installation

### From PyPI

```bash
pip install ngraph
```

### From Source

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
make dev    # Install in editable mode with dev dependencies
make check  # Run full test suite
```

## Quick Start

### CLI Usage

```bash
# Validate and inspect a scenario
ngraph inspect scenarios/readme_example.yml --detail

# Run analysis workflow
ngraph run scenarios/readme_example.yml --results example.results.json
```

### Python API

```python
from ngraph import Network, Node, Link, analyze, Mode

# Build network programmatically
network = Network()
network.add_node(Node("A"))
network.add_node(Node("B"))
network.add_node(Node("C"))
network.add_link(Link("A", "B", capacity=10.0, cost=1.0))
network.add_link(Link("B", "C", capacity=10.0, cost=1.0))

# Compute max flow with the analyze() API
flow = analyze(network).max_flow("^A$", "^C$", mode=Mode.COMBINE)
print(f"Max flow: {flow}")  # {('^A$', '^C$'): 10.0}

# Efficient repeated analysis with bound context
ctx = analyze(network, source="^A$", sink="^C$", mode=Mode.COMBINE)
baseline = ctx.max_flow()
degraded = ctx.max_flow(excluded_nodes={"B"})  # Test failure scenario
```

## Example Scenario

NetGraph scenarios define topology, configuration, and analysis steps in a unified YAML file. This example demonstrates **blueprints** for modular topology definition and a **flow analysis workflow** with Monte Carlo failure simulation:

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
      - source: /spine
        target: /leaf
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

The workflow demonstrates **step chaining**: `MaximumSupportedDemand` finds the maximum feasible demand multiplier (`alpha_star=1.0`), then `TrafficMatrixPlacement` uses that value via `alpha_from_step` to run Monte Carlo placement under random link failures. Results show baseline placement at 100% and worst-case failure at 50% (when a spine-to-spine link fails).

## Repository Structure

```text
ngraph/             # Python package source
  analysis/         # Core algorithm wrappers and placement
  dsl/              # Scenario parsing and blueprint expansion
  model/            # Network, demand, and flow domain models
  results/          # Result artifacts and storage
  workflow/         # Workflow steps and orchestration
scenarios/          # Example scenario definitions
tests/              # Pytest suite
docs/               # Documentation source (MkDocs)
dev/                # Development scripts
```

## Development

```bash
make dev        # Setup environment
make check      # Run tests and linting
make lint       # Run linting only
make test       # Run tests only
make docs-serve # Preview documentation
```

## Requirements

- **Python**: 3.11+
- **NetGraph-Core**: Compatible C++ backend version

## Documentation

- **Site**: [networmix.github.io/NetGraph](https://networmix.github.io/NetGraph/)
- **Tutorial**: [Getting Started](https://networmix.github.io/NetGraph/getting-started/tutorial/)
- **Reference**: [API](https://networmix.github.io/NetGraph/reference/api/) | [CLI](https://networmix.github.io/NetGraph/reference/cli/) | [DSL](https://networmix.github.io/NetGraph/reference/dsl/)

## License

[GNU Affero General Public License v3.0 or later](LICENSE)
