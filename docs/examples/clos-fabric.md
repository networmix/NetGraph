# Clos Fabric Analysis

This example demonstrates how to model and analyze a 3-tier Clos network fabric using NetGraph. We'll calculate maximum flow between different segments and explore traffic engineering policies.

## Scenario Overview

We'll create two separate 3-tier Clos networks and analyze the maximum flow capacity between them. This scenario showcases:

- Hierarchical blueprint composition
- Complex adjacency patterns  
- Flow analysis with different placement policies
- ECMP vs UCMP traffic distribution

## Complete Scenario

```python
from ngraph.scenario import Scenario
from ngraph.lib.flow_policy import FlowPlacement

scenario_yaml = """
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
  name: "3tier_clos_network"
  version: 1.0

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

# Create and analyze the scenario
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network

# Calculate maximum flow with ECMP (Equal Cost Multi-Path)
max_flow_ecmp = network.max_flow(
    source_path=r"my_clos1.*(b[0-9]*)/t1",
    sink_path=r"my_clos2.*(b[0-9]*)/t1",
    mode="combine",
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED,
)

print(f"Maximum flow with ECMP: {max_flow_ecmp}")
# Result: {('b1|b2', 'b1|b2'): 256.0}
```

## Understanding the Results

The result `{('b1|b2', 'b1|b2'): 256.0}` means:
- **Source**: All t1 nodes in both b1 and b2 segments of my_clos1
- **Sink**: All t1 nodes in both b1 and b2 segments of my_clos2  
- **Capacity**: Maximum flow of 256.0 units

## Traffic Engineering Comparison

### ECMP vs UCMP Analysis

```python
# Test with different flow placement policies

# ECMP: Equal distribution across all paths
max_flow_ecmp = network.max_flow(
    source_path=r"my_clos1.*(b[0-9]*)/t1",
    sink_path=r"my_clos2.*(b[0-9]*)/t1", 
    mode="combine",
    flow_placement=FlowPlacement.EQUAL_BALANCED
)

# UCMP: Proportional distribution based on link capacity
max_flow_ucmp = network.max_flow(
    source_path=r"my_clos1.*(b[0-9]*)/t1",
    sink_path=r"my_clos2.*(b[0-9]*)/t1",
    mode="combine", 
    flow_placement=FlowPlacement.PROPORTIONAL
)

print(f"ECMP Max Flow: {max_flow_ecmp}")
print(f"UCMP Max Flow: {max_flow_ucmp}")
```

### Impact of Link Failures

```python
# Simulate partial spine-to-spine connectivity failure
# If 3 out of 4 spine-spine links fail, reducing capacity to 253.0:

# With ECMP: Flow limited by bottleneck, results in 64.0
# With UCMP: Flow distributed proportionally, results in 253.0

# This demonstrates how UCMP can better utilize available capacity
# when links have different capacities or availability
```

## Network Structure Analysis

```python
from ngraph.explorer import NetworkExplorer

# Explore the network topology
explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)

# Analyze specific paths between border nodes
from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.path_utils import resolve_to_paths

# Get border nodes from different segments
border_nodes = [node for node in network.nodes.values() if '/b1/t1' in node.name or '/b2/t1' in node.name]
src_node = next(node.name for node in border_nodes if "my_clos1/b1/t1" in node.name)
dst_node = next(node.name for node in border_nodes if "my_clos2/b1/t1" in node.name)

# Find shortest paths using SPF
costs, pred = spf(network.to_strict_multidigraph(), src_node)
paths = list(resolve_to_paths(src_node, dst_node, pred))
print(f"Found {len(paths)} paths between segments")
```

## Next Steps

- **[DSL Reference](../reference/dsl.md)** - Learn the complete YAML syntax
- **[API Reference](../reference/api.md)** - Explore the Python API in detail
