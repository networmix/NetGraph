# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Scenario-driven network modeling and analysis: a Python front end over C++ graph algorithms.

Model network topologies, traffic matrices and failure scenarios declaratively. The graph algorithms live in [NetGraph-Core](https://github.com/networmix/NetGraph-Core); NetGraph provides the Python API and CLI that drive them.

## Architecture

Two layers:

- **Python layer (NetGraph)**: scenario DSL, workflow execution, results, the Python API and CLI.
- **C++ layer (NetGraph-Core)**: shortest paths, k-shortest paths and max-flow, run with the GIL released.

## Features

### Modeling & DSL

- **Declarative Scenarios**: Define topology, traffic, and workflows in validated YAML.
- **Blueprints**: Reusable topology templates (e.g., Clos fabrics, regions) with parameterized expansion.
- **Strict Multigraph**: Deterministic graph representation with stable edge IDs.

### Failure Analysis

- **Failure policies**: Weighted modes, each a set of selection rules.
- **Exclusions**: Failures are simulated at analysis time; the base topology is never modified.
- **Risk Groups**: Model shared fate (e.g., fiber cuts, power zones).

### Traffic Engineering

- **Routing Modes**: IP routing (cost-only, fixed paths) and traffic engineering (capacity-aware) in one model.
- **Flow Placement**: Strategies for ECMP (Equal-Cost Multi-Path) and WCMP (Weighted Cost Multi-Path).
- **Capacity Analysis**: Max-flow between node groups and traffic-matrix placement with selectable placement policies.

### Workflow & Integration

- **Structured Results**: JSON export with a fixed shape.
- **CLI**: Validate, inspect, and run scenarios from the command line.
- **Python API**: The same modeling and analysis entry points from Python.

## Getting Started

- **[Installation Guide](getting-started/installation.md)** - Install from PyPI or from source
- **[Tutorial](getting-started/tutorial.md)** - Run a scenario from the CLI and from Python

## Examples

- **[Bundled Scenarios](examples/bundled-scenarios.md)** - Ready-to-run scenarios (`square_mesh`, `backbone_clos`, `nsfnet`)
- **[Basic Example](examples/basic.md)** - The analysis API on a four-node network
- **[Clos Fabric Analysis](examples/clos-fabric.md)** - Analyze a 3-tier Clos network

## Reference Documentation

- **[Design](reference/design.md)** - Architecture, model, algorithms, and workflow
- **[DSL Reference](reference/dsl.md)** - YAML syntax guide
- **[Workflow Reference](reference/workflow.md)** - Analysis workflow configuration
- **[CLI Reference](reference/cli.md)** - Command-line interface
- **[Schema Reference](reference/schemas.md)** - JSON Schema and validation
- **[API Reference](reference/api.md)** - Python API documentation
- **[Auto-Generated API Reference](reference/api-full.md)** - Every public module, generated from docstrings
