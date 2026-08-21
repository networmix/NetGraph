# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Scenario-driven network modeling and analysis framework combining Python with C++ graph algorithms.

## Overview

Model network topologies, traffic matrices, and failure scenarios declaratively. Graph algorithms are delegated to [NetGraph-Core](https://github.com/networmix/NetGraph-Core); NetGraph itself provides the Python API and CLI that orchestrate them.

## Architecture

NetGraph uses a hybrid Python+C++ architecture, split across two layers:

- **Python layer (NetGraph)**: Scenario DSL parsing, workflow orchestration, result aggregation, and high-level APIs.
- **C++ layer (NetGraph-Core)**: The compute-intensive graph algorithms (SPF, KSP, Max-Flow), executed in C++ with the GIL released.

## Key Features

### Modeling & DSL

- **Declarative Scenarios**: Define topology, traffic, and workflows in validated YAML.
- **Blueprints**: Reusable topology templates (e.g., Clos fabrics, regions) with parameterized expansion.
- **Strict Multigraph**: Deterministic graph representation with stable edge IDs.

### Failure Analysis

- **Policy Engine**: Weighted failure modes with multiple policy rules per mode.
- **Non-Destructive**: Runtime exclusions simulate failures without modifying the base topology.
- **Risk Groups**: Model shared fate (e.g., fiber cuts, power zones).

### Traffic Engineering

- **Routing Modes**: Unified modeling of IP routing (static costs, oblivious to congestion) and traffic engineering (dynamic residuals, congestion-aware).
- **Flow Placement**: Strategies for ECMP (Equal-Cost Multi-Path) and WCMP (Weighted Cost Multi-Path).
- **Capacity Analysis**: Compute max-flow envelopes and demand allocation with configurable placement policies.

### Workflow & Integration

- **Structured Results**: Export analysis artifacts to JSON for downstream processing.
- **CLI**: Validate, inspect, and run scenarios from the command line.
- **Python API**: Programmatic access to the same modeling and solving entry points.

## Getting Started

- **[Installation Guide](getting-started/installation.md)** - Python package installation
- **[Tutorial](getting-started/tutorial.md)** - Run scenarios (CLI) and code examples

## Examples

- **[Bundled Scenarios](examples/bundled-scenarios.md)** - Ready-to-run scenarios (`square_mesh`, `backbone_clos`, `nsfnet`)
- **[Basic Example](examples/basic.md)** - Simple graph example
- **[Clos Fabric Analysis](examples/clos-fabric.md)** - Analyze a 3-tier Clos network

## Reference Documentation

- **[Design](reference/design.md)** - Architecture, model, algorithms, and workflow
- **[DSL Reference](reference/dsl.md)** - YAML syntax guide
- **[Workflow Reference](reference/workflow.md)** - Analysis workflow configuration
- **[CLI Reference](reference/cli.md)** - Command-line interface
- **[Schema Reference](reference/schemas.md)** - JSON Schema and validation
- **[API Reference](reference/api.md)** - Python API documentation
- **[Auto-Generated API Reference](reference/api-full.md)** - Complete API docs
