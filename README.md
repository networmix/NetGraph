# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Scenario-driven network modeling and analysis framework combining Python's flexibility with high-performance C++ algorithms.

## Overview

NetGraph enables declarative modeling of network topologies, traffic matrices, and failure scenarios. It delegates computationally intensive graph algorithms to [NetGraph-Core](https://github.com/networmix/NetGraph-Core) while providing a rich Python API and CLI for orchestration.

## Architecture

NetGraph employs a **hybrid Python+C++ architecture**:

- **Python layer (NetGraph)**: Scenario DSL parsing, workflow orchestration, result aggregation, and high-level APIs.
- **C++ layer (NetGraph-Core)**: Performance-critical graph algorithms (SPF, KSP, Max-Flow) executing in optimized C++ with the GIL released.

## Key Features

### 1. Modeling & DSL

- **Declarative Scenarios**: Define topology, traffic, and workflows in validated YAML.
- **Blueprints**: Reusable topology templates (e.g., Clos fabrics, regions) with parameterized expansion.
- **Strict Multigraph**: Deterministic graph representation with stable edge IDs.

### 2. Failure Analysis

- **Policy Engine**: Weighted failure modes with multiple policy rules per mode.
- **Non-Destructive**: Runtime exclusions simulate failures without modifying the base topology.
- **Risk Groups**: Model shared fate (e.g., fiber cuts, power zones).

### 3. Traffic Engineering

- **Routing Modes**: Unified modeling of **IP Routing** (static costs, oblivious to congestion) and **Traffic Engineering** (dynamic residuals, congestion-aware).
- **Flow Placement**: Strategies for **ECMP** (Equal-Cost Multi-Path) and **WCMP** (Weighted Cost Multi-Path).
- **Capacity Analysis**: Compute max-flow envelopes and demand allocation with configurable placement policies.

### 4. Workflow & Integration

- **Structured Results**: Export analysis artifacts to JSON for downstream processing.
- **CLI**: Comprehensive command-line interface for validation and execution.
- **Python API**: Full programmatic access to all modeling and solving capabilities.

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
ngraph inspect scenarios/backbone_clos.yml --detail

# Run analysis workflow
ngraph run scenarios/backbone_clos.yml --results clos.results.json
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

NetGraph scenarios define topology, configuration, and analysis steps in a unified YAML file. This example demonstrates **blueprints** for modular topology definition:

```yaml
seed: 42

# Define reusable topology templates
blueprints:
  Clos_Fabric:
    groups:
      spine: {node_count: 2, name_template: "spine{node_num}"}
      leaf:  {node_count: 4, name_template: "leaf{node_num}"}
    adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params: {capacity: 100, cost: 1}
    - source: /spine
      target: /leaf
      pattern: mesh
      link_params: {capacity: 100, cost: 1}

# Instantiate network from templates
network:
  groups:
    site1: {use_blueprint: Clos_Fabric}
    site2: {use_blueprint: Clos_Fabric}
  adjacency:
  - source: {path: site1/spine}
    target: {path: site2/spine}
    pattern: one_to_one
    link_params: {capacity: 50, cost: 10}

# Define traffic matrix
traffic_matrix_set:
  global_traffic:
    - source_path: ^site1/leaf/
      sink_path: ^site2/leaf/
      demand: 100.0
      mode: combine
      flow_policy_config: SHORTEST_PATHS_ECMP

# Define analysis workflow
workflow:
- step_type: NetworkStats
  name: stats
- step_type: MaxFlow
  name: site_capacity
  source_path: ^site1/leaf/
  sink_path: ^site2/leaf/
  mode: combine
  shortest_path: false
- step_type: MaximumSupportedDemand
  name: max_demand
  matrix_name: global_traffic
```

## Repository Structure

```text
ngraph/             # Python package source
  dsl/              # Scenario parsing and blueprint expansion
  model/            # Network and flow domain models
  solver/           # Algorithms and Core wrappers
  workflow/         # Analysis steps and orchestration
scenarios/          # Example scenario definitions
tests/              # Pytest suite (unit and integration)
docs/               # Documentation source (MkDocs)
dev/                # Development tools and scripts
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

- **Python**: 3.9+
- **NetGraph-Core**: Compatible C++ backend version

## Documentation

- **Site**: [networmix.github.io/NetGraph](https://networmix.github.io/NetGraph/)
- **Tutorial**: [Getting Started](https://networmix.github.io/NetGraph/getting-started/tutorial/)
- **Reference**: [API](https://networmix.github.io/NetGraph/reference/api/) | [CLI](https://networmix.github.io/NetGraph/reference/cli/) | [DSL](https://networmix.github.io/NetGraph/reference/dsl/)

## License

[GNU Affero General Public License v3.0 or later](LICENSE)
