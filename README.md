# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-based network modeling and analysis framework written in Python. It allows you to design, simulate, and evaluate complex network topologies - ranging from small test cases to massive Data Center fabrics and WAN networks.

## Roadmap

- ✅ **Fundamental Components**: StrictMultiGraph, base pathfinding and flow algorithms
- ✅ **Scenario-Based Modeling**: YAML-based scenarios with Domain-Specific Language (DSL) describing topology, failures, traffic, and workflow
- ✅ **Hierarchical Blueprints**: Reusable network templates with nested structures and parameterization
- ✅ **JupyterLab Support**: Run NetGraph in a containerized environment with JupyterLab for interactive analysis
- ✅ **Demand Placement**: Place traffic demands on the network with various flow placement strategies (e.g., shortest path only, ECMP/UCMP, etc.)
- ✅ **Capacity Calculation**: Calculate MaxFlow with different flow placement strategies
- 🚧 **Failure Simulation**: Model component and risk groups failures for availability analysis with Monte Carlo simulation
- 🚧 **Network Analysis**: Workflow steps and tools to analyze capacity, failure tolerance, and power/cost efficiency of network designs
- 🚧 **Command Line Interface**: Execute scenarios from terminal with JSON output for simple automation
- 🚧 **Python API**: API for programmatic access to scenario components and network analysis tools
- 🚧 **Documentation and Examples**: Comprehensive guides and use cases
- ❌ **Components Library**: Hardware/optics modeling with cost, power consumption, and capacity specifications
- ❓ **Visualization**: Graphical representation of scenarios and results

### Status Legend
- ✅ **Done**: Feature implemented and tested
- 🚧 **In Progress**: Feature under development
- ❌ **Planned**: Feature planned but not yet started
- ❓ **Future Consideration**: Feature may be added later

## Quick Start

### Docker with JupyterLab (Recommended)

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
./run.sh build
./run.sh run  # Opens JupyterLab at http://127.0.0.1:8788/
```

### Local Installation

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e '.[dev]'
```

### Example: Clos Fabric Analysis

```python
from ngraph.scenario import Scenario
from ngraph.lib.flow_policy import FlowPlacement

# Define two 3-tier Clos networks with inter-fabric connectivity
clos_scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 8
        name_template: t1-{node_num}
      t2:
        node_count: 8
        name_template: t2-{node_num}
    adjacency:
      - source: /t1
        target: /t2
        pattern: mesh
        link_params:
          capacity: 2
          cost: 1

  3tier_clos:
    groups:
      b1:
        use_blueprint: brick_2tier
      b2:
        use_blueprint: brick_2tier
      spine:
        node_count: 64
        name_template: t3-{node_num}
    adjacency:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1

network:
  groups:
    my_clos1:
      use_blueprint: 3tier_clos
    my_clos2:
      use_blueprint: 3tier_clos
  adjacency:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      link_count: 4
      link_params:
        capacity: 1
        cost: 1
"""

scenario = Scenario.from_yaml(clos_scenario_yaml)
network = scenario.network

# Calculate maximum flow with ECMP
max_flow = network.max_flow(
    source_path=r"my_clos1.*(b[0-9]*)/t1",
    sink_path=r"my_clos2.*(b[0-9]*)/t1",
    mode="combine",
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Maximum flow: {max_flow}")
# Maximum flow: {('b1|b2', 'b1|b2'): 256.0}
```

## Documentation

📚 **[Full Documentation](https://networmix.github.io/NetGraph/)**

- **[Installation Guide](https://networmix.github.io/NetGraph/getting-started/installation/)** - Docker and pip installation
- **[Quick Tutorial](https://networmix.github.io/NetGraph/getting-started/tutorial/)** - Build your first scenario
- **[Examples](https://networmix.github.io/NetGraph/examples/clos-fabric/)** - Clos fabric analysis and more
- **[DSL Reference](https://networmix.github.io/NetGraph/reference/dsl/)** - Complete YAML syntax
- **[API Reference](https://networmix.github.io/NetGraph/reference/api/)** - Python API documentation

## License

[MIT License](LICENSE)
