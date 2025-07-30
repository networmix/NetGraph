# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-based network modeling and analysis framework written in Python. Design, simulate, and evaluate complex network topologies from small test cases to large-scale Data Center fabrics and WAN networks.

## Roadmap

- ✅ **Fundamental Components**: StrictMultiGraph, base pathfinding and flow algorithms
- ✅ **Scenario-Based Modeling**: YAML-based scenarios with Domain-Specific Language (DSL) describing topology, failures, traffic, and workflow
- ✅ **Hierarchical Blueprints**: Reusable network templates with nested structures and parameterization
- ✅ **Demand Placement**: Place traffic demands on the network with various flow placement strategies (e.g., shortest path only, ECMP/UCMP, etc.)
- ✅ **Capacity Calculation**: Calculate MaxFlow with different flow placement strategies
- ✅ **Reproducible Analysis**: Seed-based deterministic random operations for reliable testing and debugging
- ✅ **Command Line Interface**: Execute scenarios from terminal with JSON output for simple automation
- ✅ **Reporting**: Export of results to JSON, Jupyter Notebook, and HTML
- ✅ **JupyterLab Support**: Run NetGraph in a containerized environment with JupyterLab for interactive analysis
- 🚧 **Network Analysis**: Workflow steps and tools to analyze capacity, failure tolerance, and power/cost efficiency of network designs
- 🚧 **Failure Simulation**: Model component and risk groups failures for availability analysis with Monte Carlo simulation
- 🚧 **Python API**: API for programmatic access to scenario components and network analysis tools
- 🚧 **Documentation and Examples**: Guides and use cases
- 🔜 **Components Library**: Hardware/optics modeling with cost, power consumption, and capacity specifications

### Status Legend

- ✅ **Done**: Feature implemented and tested
- 🚧 **In Progress**: Feature under development
- 🔜 **Planned**: Feature planned but not yet started
- ❓ **Future Consideration**: Feature may be added later

## Quick Start

### Local Installation

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e '.[dev]'
```

### Docker with JupyterLab

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
./run.sh build
./run.sh run  # Opens JupyterLab at http://127.0.0.1:8788/
```

## Documentation

📚 **[Full Documentation](https://networmix.github.io/NetGraph/)**

- **[Installation Guide](https://networmix.github.io/NetGraph/getting-started/installation/)** - Docker and Python package installation
- **[Quick Tutorial](https://networmix.github.io/NetGraph/getting-started/tutorial/)** - Build your first network scenario
- **[Examples](https://networmix.github.io/NetGraph/examples/basic/)** - Basic and Clos fabric examples
- **[DSL Reference](https://networmix.github.io/NetGraph/reference/dsl/)** - YAML syntax guide
- **[API Reference](https://networmix.github.io/NetGraph/reference/api/)** - Python API documentation
- **[CLI Reference](https://networmix.github.io/NetGraph/reference/cli/)** - Command-line interface

## License

[MIT License](LICENSE)
