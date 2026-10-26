# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

Scenario-driven network modeling and analysis: a Python front end over C++ graph algorithms.

Model network topologies, traffic matrices and failure scenarios declaratively. The graph algorithms live in [NetGraph-Core](https://github.com/networmix/NetGraph-Core); NetGraph provides the Python API and CLI that drive them.

## Architecture

Two layers:

- **Python layer (NetGraph)**: scenario DSL, workflow execution, results, the Python API and CLI.
- **C++ layer (NetGraph-Core)**: shortest and k-shortest paths, maximum flow, demand placement, tunnels, forwarding programs and their replay under failures, run with the GIL released.

## How it works

1. **Scenario:** a YAML file or Python objects declare the network, demands, failure policies and an ordered workflow.
2. **Prepare:** NetGraph builds one read-only graph and chooses one bandwidth unit for the whole run.
3. **Run:** each workflow step asks its question on that graph, under each failure case it draws.
4. **Results:** typed Python results, or one JSON file of exact numbers.

[How NetGraph computes](concepts.md) explains each step's rules.

## Features

### Modeling & DSL

- **Declarative Scenarios**: Define topology, traffic, and workflows in validated YAML.
- **Blueprints**: Reusable topology templates (e.g., Clos fabrics, regions) with parameterized expansion.

### Failure Analysis

- **Failure policies**: Weighted modes, each a set of selection rules.
- **Exclusions**: Failures are simulated at analysis time; the base topology is never modified.
- **Risk Groups**: Model shared fate (e.g., fiber cuts, power zones).

### Traffic Engineering

- **Routing Modes**: IP routing (cost-only, fixed paths) and traffic engineering (capacity-aware) in one model.
- **Traffic Placement:** ECMP splits equally among equal-cost next hops at each router; WCMP uses weights ([Routing models and admission](concepts.md#routing-models-and-admission)).
- **Capacity Analysis**: Max-flow between node groups and traffic-matrix placement with selectable placement policies.

### Workflow & Integration

- **CLI**: Validate, inspect, and run scenarios from the command line.
- **Python API**: The same modeling and analysis entry points from Python.

## Where to start

- **YAML and CLI:** [Tutorial](getting-started/tutorial.md) → [How NetGraph computes](concepts.md) → [Clos Fabric](examples/clos-fabric.md) → [Bundled Scenarios](examples/bundled-scenarios.md) → [Scenario YAML](reference/dsl.md), [Workflow Steps](reference/workflow.md), [Command Line](reference/cli.md), [Results](reference/results.md).
- **Python:** [Tutorial](getting-started/tutorial.md#use-python) → [How NetGraph computes](concepts.md) → [Basic Example](examples/basic.md) → [Python API](reference/api.md) → [Python API (generated)](reference/api-full.md), [Results](reference/results.md).
- **Reading JSON results:** [Tutorial](getting-started/tutorial.md#read-results) → [Results and their units](concepts.md#results-and-their-units) → [Results](reference/results.md).
- **Contributor:** [Installation](getting-started/installation.md#from-source) → [Architecture](reference/design.md) → [Schemas](reference/schemas.md#for-contributors).
