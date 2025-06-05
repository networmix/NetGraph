# Quick Tutorial: Two-Tier Clos Analysis

This tutorial will walk you through analyzing a simple two-tier Clos network topology using NetGraph. You'll learn how to create a scenario in YAML, define network topologies, calculate maximum flows, and explore the network structure. This example will help you understand the basics of using NetGraph for network modeling and analysis.

## Building a Two-Tier Clos Topology

Let's start by defining a simple two-tier Clos (leaf-spine) fabric:

```python
from ngraph.scenario import Scenario

scenario_yaml = """
network:
  name: "Two-Tier Clos Fabric"
  groups:
    leaf:
      node_count: 4
      name_template: "leaf-{node_num}"
    spine:
      node_count: 2  
      name_template: "spine-{node_num}"
  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params:
        capacity: 10
        cost: 1
"""

scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
print(f"Created Clos fabric with {len(network.nodes)} nodes and {len(network.links)} links")
```

This creates a classic leaf-spine topology:

- 4 leaf switches: `leaf/leaf-1`, `leaf/leaf-2`, `leaf/leaf-3`, `leaf/leaf-4`
- 2 spine switches: `spine/spine-1`, `spine/spine-2`
- 8 bidirectional links (mesh pattern) providing full connectivity

Note that the `link_params` define the link capacity and cost, which can be adjusted based on your requirements. All links are bidirectional by default.

## Creating a Three-Tier Clos Fabric

Now let's scale our approach using blueprints to create a multi-pod Clos fabric with dedicated server connections:

```python
scenario_yaml = """
blueprints:
  clos_pod:
    groups:
      servers:
        node_count: 8
        name_template: "server-{node_num}"
      leaf:
        node_count: 4
        name_template: "leaf-{node_num}"
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
    adjacency:
      # Servers connect to leaf switches
      - source: /servers
        target: /leaf
        pattern: one_to_one
        link_count: 2  # Two parallel links per server
        link_params:
          capacity: 10
          cost: 1
      # Full mesh between leaf and spine
      - source: /leaf
        target: /spine
        pattern: mesh
        link_params:
          capacity: 40
          cost: 1

network:
  name: "Three-Tier Clos Fabric"
  groups:
    pod[1-2]:  # Creates pod1 and pod2
      use_blueprint: clos_pod
    super_spine:
      node_count: 4
      name_template: "super-spine-{node_num}"
  adjacency:
    # Connect pod spines to super spines
    - source: pod{idx}/spine
      target: /super_spine
      expand_vars:
        idx: [1, 2]
      pattern: one_to_one
      link_params:
        capacity: 100
        cost: 1
"""

scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
```

This creates a three-tier Clos fabric with the following structure:

- 2 pods, each containing 8 servers, 4 leaf switches, and 2 spine switches
- 4 super-spine switches connecting the pods
- Each server connects with two parallel links to its leaf switch
- Leaf switches connect to spine switches in a full mesh
- Spines connect to super-spines in respective columns in one-to-one fashion

## Network Topology Exploration

We can use the NetworkExplorer to understand our Clos fabric structure:

```python
from ngraph.explorer import NetworkExplorer

explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)

print(f"Total nodes in fabric: {len(network.nodes)}")
print(f"Total links in fabric: {len(network.links)}")
```

Example output:

```
- root | Nodes=32, Links=56, Cost=0.0, Power=0.0
  - pod1 | Nodes=14, Links=28, Cost=0.0, Power=0.0
    - servers | Nodes=8, Links=16, Cost=0.0, Power=0.0
    - leaf | Nodes=4, Links=24, Cost=0.0, Power=0.0
    - spine | Nodes=2, Links=12, Cost=0.0, Power=0.0
  - pod2 | Nodes=14, Links=28, Cost=0.0, Power=0.0
    - servers | Nodes=8, Links=16, Cost=0.0, Power=0.0
    - leaf | Nodes=4, Links=24, Cost=0.0, Power=0.0
    - spine | Nodes=2, Links=12, Cost=0.0, Power=0.0
  - super_spine | Nodes=4, Links=8, Cost=0.0, Power=0.0
Total nodes in fabric: 32
Total links in fabric: 56
```

## Analyzing Maximum Flow Capacity

Let's analyze the maximum flow capacity between different segments of our Clos fabric:

```python
from ngraph.lib.flow_policy import FlowPlacement

# Calculate MaxFlow from pod1 servers to pod2 servers
max_flow = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers", 
)
print(f"Maximum flow pod1→pod2: {max_flow}")

# Calculate MaxFlow from pod1 leaf to pod2 leaf
max_flow_leaf = network.max_flow(
    source_path="pod1/leaf",
    sink_path="pod2/leaf", 
)
print(f"Maximum flow pod1→pod2 leaf: {max_flow_leaf}")

# Calculate MaxFlow from pod1 spine to pod2 spine
max_flow_spine = network.max_flow(
    source_path="pod1/spine",
    sink_path="pod2/spine", 
)
print(f"Maximum flow pod1→pod2 spine: {max_flow_spine}")
```

Example output:

```
Maximum flow pod1→pod2: {('pod1/servers', 'pod2/servers'): 160.0}
Maximum flow pod1→pod2 leaf: {('pod1/leaf', 'pod2/leaf'): 320.0}
Maximum flow pod1→pod2 spine: {('pod1/spine', 'pod2/spine'): 400.0}
```

## Understanding MaxFlow Results

All the nodes matched by the `source_path` and `sink_path` respectively are attached to pseudo-source and pseudo-sink nodes, which are then used to calculate the maximum flow. The results show the maximum flow between these two pseudo-nodes, which represent the total capacity of the network paths between them.

MaxFlow calculation can be influenced by the folowing parameters:

- **`shortest_path`**: If set to `True`, it will only consider the shortest paths between source and sink nodes.
- **`flow_placement`**: This parameter controls how flows are distributed across multiple shortest paths. Options include `FlowPlacement.PROPORTIONAL` (default) and `FlowPlacement.EQUAL_BALANCED`.

  - `PROPORTIONAL` distributes flows based on link capacities.
  - `EQUAL_BALANCED` evenly distributes flows across all available paths.

Note that in the MaxFlow context, `flow_placement` makes sense only when `shortest_path` is set to `True`. In this case, `PROPORTIONAL` simulates UCMP (unequal cost multi-path) routing, while `EQUAL_BALANCED` simulates ECMP (equal cost multi-path) routing.

## Next Steps

- **[Clos Fabric Analysis](clos-fabric.md)** - Explore a more complex Clos fabric example
- **[DSL Reference](../reference/dsl.md)** - Learn the complete YAML syntax
- **[API Reference](../reference/api.md)** - Explore the Python API in detail
