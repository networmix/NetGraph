# API Reference

This section provides detailed documentation for NetGraph's Python API.

> **📚 Quick Navigation:**

> - **[Complete Auto-Generated API Reference](api-full.md)** - Comprehensive class and method documentation
> - **[CLI Reference](cli.md)** - Command-line interface documentation
> - **[DSL Reference](dsl.md)** - YAML DSL syntax reference

## Core Classes

### Scenario
The main entry point for building and running network analyses.

```python
from ngraph.scenario import Scenario

# Create from YAML
scenario = Scenario.from_yaml(yaml_content)

# Create programmatically
scenario = Scenario()
scenario.network = Network()
scenario.run()
```

**Key Methods:**

- `from_yaml(yaml_content)` - Create scenario from YAML string
- `run()` - Execute the scenario workflow

### Network
Represents the network topology and provides analysis methods.

```python
from ngraph.network import Network

network = Network()
# Access nodes, links, and analysis methods
```

**Key Methods:**

- `max_flow(source_path, sink_path, **kwargs)` - Calculate maximum flow
- `add_node(name, **attrs)` - Add network node
- `add_link(source, target, **params)` - Add network link

### NetworkExplorer
Provides network visualization and exploration capabilities.

```python
from ngraph.explorer import NetworkExplorer

explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)
```

## Flow Analysis

### FlowPlacement
Enumeration of flow placement policies for traffic engineering.

```python
from ngraph.lib.algorithms.base import FlowPlacement

# Available policies:
FlowPlacement.EQUAL_BALANCED    # ECMP - equal distribution
FlowPlacement.PROPORTIONAL      # UCMP - capacity proportional
```

### Flow Calculation Methods

```python
# Maximum flow analysis
max_flow = network.max_flow(
    source_path="datacenter1/servers",
    sink_path="datacenter2/servers",
    mode="combine",                    # or "full_mesh"
    shortest_path=True,               # Use shortest paths only
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
```

## Blueprint System

### Blueprint Definition
Blueprints are defined in YAML and loaded through the scenario system:

```python
from ngraph.blueprints import Blueprint

# Blueprint is a dataclass that holds blueprint configuration
# Blueprints are typically loaded from YAML, not created programmatically
blueprint = Blueprint(
    name="my_blueprint",
    groups={
        "servers": {"node_count": 4},
        "switches": {"node_count": 2}
    },
    adjacency=[
        {"source": "/servers", "target": "/switches", "pattern": "mesh"}
    ]
)

# Note: Blueprint objects are usually created internally when parsing YAML
# For programmatic creation, use the Network class directly
```

## Traffic Demands

### TrafficDemand
Define and manage traffic demands between network segments.

```python
from ngraph.traffic_demand import TrafficDemand

demand = TrafficDemand(
    source_path="web_servers",
    sink_path="databases",
    demand=1000.0,
    mode="full_mesh"
)
```

## Failure Modeling

### FailurePolicy and FailurePolicySet
Configure failure simulation parameters using named policies.

```python
from ngraph.failure_policy import FailurePolicy, FailureRule
from ngraph.results_artifacts import FailurePolicySet

# Create individual failure rules
rule = FailureRule(
    entity_scope="link",
    rule_type="choice",
    count=2
)

# Create failure policy
policy = FailurePolicy(rules=[rule])

# Create policy set to manage multiple policies
policy_set = FailurePolicySet()
policy_set.add("light_failures", policy)
policy_set.add("default", policy)

# Use with FailureManager
from ngraph.failure_manager import FailureManager
manager = FailureManager(
    network=network,
    traffic_matrix_set=traffic_matrix_set,
    failure_policy_set=policy_set,
    policy_name="light_failures"  # Optional: specify which policy to use
)
```

### Risk Groups
Model correlated component failures.

```python
# Risk groups are typically defined in YAML
risk_groups = [
    {
        "name": "PowerSupplyA",
        "components": ["rack1/switch1", "rack1/servers"]
    }
]
```

## Components and Hardware

### Component Library
Define hardware specifications and attributes.

```python
from ngraph.components import Component

router = Component(
    name="SpineRouter",
    component_type="router",
    attrs={
        "power_consumption": 500,
        "port_count": 64,
        "switching_capacity": 12800
    }
)
```

## Workflow Automation

### Available Workflow Steps
NetGraph provides workflow steps for automated analysis sequences.

```python
# Available workflow steps:
# - BuildGraph: Builds a StrictMultiDiGraph from scenario.network
# - CapacityProbe: Probes capacity (max flow) between selected groups of nodes

# Example workflow configuration:
workflow = [
    {"step": "BuildGraph"},
    {"step": "CapacityProbe", "params": {"flow_placement": "PROPORTIONAL"}}
]
```

## Utilities and Helpers

### Graph Conversion Utilities
Utilities for converting between NetGraph and NetworkX graph formats.

```python
from ngraph.lib.util import to_digraph, from_digraph, to_graph, from_graph
from ngraph.lib.graph import StrictMultiDiGraph

# Convert to NetworkX formats
graph = StrictMultiDiGraph()
nx_digraph = to_digraph(graph)  # Convert to NetworkX DiGraph
nx_graph = to_graph(graph)      # Convert to NetworkX Graph

# Convert back to NetGraph format
restored_graph = from_digraph(nx_digraph)
restored_graph = from_graph(nx_graph)
```

### Graph Algorithms
Low-level graph analysis functions.

```python
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.spf import spf, ksp
from ngraph.lib.algorithms.max_flow import calc_max_flow, run_sensitivity, saturated_edges

# Direct graph manipulation
graph = StrictMultiDiGraph()
graph.add_node("A")
graph.add_node("B")
graph.add_edge("A", "B", capacity=10, cost=1)

# Run shortest path algorithm
costs, pred = spf(graph, "A")

# Calculate maximum flow
max_flow = calc_max_flow(graph, "A", "B")

# Sensitivity analysis - identify bottleneck edges and test capacity changes
saturated = saturated_edges(graph, "A", "B")
sensitivity = run_sensitivity(graph, "A", "B", change_amount=1.0)
```

## Error Handling

NetGraph uses standard Python exceptions for error conditions. Common error types include:

```python
try:
    scenario = Scenario.from_yaml(invalid_yaml)
except ValueError as e:
    print(f"YAML validation failed: {e}")
except KeyError as e:
    print(f"Missing required field: {e}")
except Exception as e:
    print(f"General error: {e}")
```

For complete API documentation with method signatures, parameters, and return types, see the auto-generated API docs or use Python's help system:

```python
help(Scenario)
help(Network.max_flow)
```
