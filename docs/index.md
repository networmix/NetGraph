# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-based network modeling and analysis framework written in Python. It allows you to design, simulate, and evaluate complex network topologies - ranging from small test cases to massive Data Center fabrics and WAN networks.

You can load an entire scenario from a single YAML file (including topology, failure policies, traffic demands, multi-step workflows) and run it in just a few lines of Python. The results can then be explored, visualized, and refined — making NetGraph well-suited for iterative network design, traffic engineering experiments, and what-if scenario analysis in large-scale topologies.

## Getting Started

- **[Installation Guide](getting-started/installation.md)** - Docker and Python package installation
- **[Quick Tutorial](getting-started/tutorial.md)** - Build your first network scenario

## Examples

- **[Basic Example](examples/basic.md)** - A very simple graph
- **[Clos Fabric Analysis](examples/clos_fabric_analysis.md)** - Analyze a 3-tier Clos network

## Documentation

- **[DSL Reference](reference/dsl.md)** - Complete YAML syntax guide
- **[API Reference](reference/api.md)** - Python API documentation
