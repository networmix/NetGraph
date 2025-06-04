# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-based network modeling and analysis framework written in Python. Design, simulate, and evaluate complex network topologies from small test cases to massive Data Center fabrics and WAN networks.

## Quick Start

```bash
pip install ngraph
```

```python
from ngraph.scenario import Scenario

scenario_yaml = """
network:
  groups:
    servers:
      node_count: 4
      name_template: "server-{node_num}"
    switches:
      node_count: 2
      name_template: "switch-{node_num}"
  adjacency:
    - source: /servers
      target: /switches
      pattern: mesh
"""

scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
print(f"Created network with {len(network.nodes)} nodes and {len(network.links)} links")
```

## Key Features

- **Scenario-Based Modeling**: Define complete network scenarios in YAML with topology, failures, traffic, and workflows
- **Hierarchical Blueprints**: Reusable network templates with nested structures and bracket expansion
- **Flow Analysis**: Calculate max flows, shortest paths, and capacity with ECMP/UCMP support
- **Failure Simulation**: Model component failures and risk groups for availability analysis
- **Traffic Engineering**: Define traffic demands with various placement policies
- **Rich Visualization**: Explore network topology and analyze results interactively

## Documentation

📚 **[Full Documentation](https://networmix.github.io/NetGraph/)**

- **[Installation Guide](https://networmix.github.io/NetGraph/getting-started/installation/)** - Docker and pip installation
- **[Quick Tutorial](https://networmix.github.io/NetGraph/getting-started/tutorial/)** - Build your first scenario
- **[Examples](https://networmix.github.io/NetGraph/examples/clos-fabric/)** - Clos fabric analysis and more
- **[DSL Reference](https://networmix.github.io/NetGraph/reference/dsl/)** - Complete YAML syntax
- **[API Reference](https://networmix.github.io/NetGraph/reference/api/)** - Python API documentation

## Quick Example: Clos Fabric Analysis

```python
from ngraph.scenario import Scenario
from ngraph.lib.flow_policy import FlowPlacement

# Define a 3-tier Clos network with inter-fabric connectivity
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
# Result: {('b1|b2', 'b1|b2'): 256.0}
```

## Development Setup

### Docker (Recommended)

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
pip install -e .
```

## License

[MIT License](LICENSE)
