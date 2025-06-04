# Quick Tutorial: Two-Tier Clos Analysis

This tutorial will walk you through analyzing a simple two-tier Clos network topology using NetGraph. You'll learn how to define the topology, calculate maximum flows, and understand traffic engineering concepts.

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

## Creating a Multi-Pod Clos Fabric

Now let's scale this up using blueprints to create a multi-pod Clos fabric with dedicated server connections:

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
        link_count: 2  # Dual-homed servers
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
  name: "Multi-Pod Clos Fabric"
  groups:
    pod[1-2]:  # Creates pod1 and pod2
      use_blueprint: clos_pod
    super_spine:
      node_count: 4
      name_template: "super-spine-{node_num}"
  adjacency:
    # Connect pod spines to super spines
    - source: "pod*/spine"
      target: /super_spine
      pattern: mesh
      link_params:
        capacity: 100
        cost: 1
"""

scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
```

This creates a hierarchical Clos fabric with:
- 2 pods, each containing 8 servers, 4 leaf switches, and 2 spine switches
- 4 super-spine switches connecting the pods
- Full mesh connectivity at each tier for maximum path diversity

## Analyzing Maximum Flow Capacity

Let's analyze the maximum flow capacity between different segments of our Clos fabric:

```python
from ngraph.lib.flow_policy import FlowPlacement

# Analyze flow from pod1 servers to pod2 servers
max_flow = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers", 
    mode="combine",
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Maximum flow pod1→pod2: {max_flow}")

# Compare ECMP vs UCMP flow placement
max_flow_ecmp = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers",
    mode="combine",
    flow_placement=FlowPlacement.EQUAL_BALANCED
)

max_flow_ucmp = network.max_flow(
    source_path="pod1/servers", 
    sink_path="pod2/servers",
    mode="combine",
    flow_placement=FlowPlacement.PROPORTIONAL
)

print(f"ECMP flow capacity: {max_flow_ecmp}")
print(f"UCMP flow capacity: {max_flow_ucmp}")
```

## Understanding Flow Results

The flow analysis results show:
- **ECMP (Equal Cost Multi-Path)**: Traffic is distributed equally across all available paths
- **UCMP (Unequal Cost Multi-Path)**: Traffic is distributed proportionally based on link capacities
- **Mode "combine"**: Aggregates flows from all source nodes to all sink nodes

## Network Topology Exploration

Use the NetworkExplorer to visualize and understand your Clos fabric structure:

```python
from ngraph.explorer import NetworkExplorer

explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)

# Example output:
# - root | Nodes=28, Links=88, Cost=0.0, Power=0.0
#   - pod1 | Nodes=14, Links=40, Cost=0.0, Power=0.0
#     - servers | Nodes=8, Links=16, Cost=0.0, Power=0.0
#     - leaf | Nodes=4, Links=24, Cost=0.0, Power=0.0  
#     - spine | Nodes=2, Links=16, Cost=0.0, Power=0.0
#   - pod2 | Nodes=14, Links=40, Cost=0.0, Power=0.0
#   - super_spine | Nodes=4, Links=16, Cost=0.0, Power=0.0

# Analyze specific paths between segments
print(f"Total nodes in fabric: {len(network.nodes)}")
print(f"Total links in fabric: {len(network.links)}")
```

## Failure Analysis and Resilience Testing

Simulate failures to test the resilience of your Clos fabric:

```python
scenario_yaml = """
# ... previous definitions ...

risk_groups:
  - name: "Pod1_Spine_Failure"
    components: ["pod1/spine/spine-1"]
  - name: "Super_Spine_Card_Failure" 
    components: ["super_spine/super-spine-1", "super_spine/super-spine-2"]

workflow:
  - step: build_graph
  - step: analyze_failures
    params:
      failure_scenarios: ["Pod1_Spine_Failure", "Super_Spine_Card_Failure"]
"""

scenario = Scenario.from_yaml(scenario_yaml)
scenario.run()

# Test flow capacity under failure conditions
print("\\nFailure impact analysis:")
print("========================")

# Baseline capacity
baseline_flow = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers",
    mode="combine"
)
print(f"Baseline flow capacity: {baseline_flow}")

# Simulate spine failure and recalculate
# (In a real scenario, the workflow would automatically 
# disable failed components and recalculate flows)
```

## Understanding Clos Network Characteristics

The analysis reveals key characteristics of Clos networks:

1. **Path Diversity**: Multiple paths between any source-destination pair provide redundancy
2. **Bandwidth Scaling**: Adding more spine switches increases aggregate bandwidth
3. **Failure Resilience**: Traffic can reroute around failed components
4. **Oversubscription**: Careful capacity planning at each tier affects overall performance

## Advanced Analysis Techniques

```python
# Analyze east-west vs north-south traffic patterns
east_west_flow = network.max_flow(
    source_path="pod1/servers", 
    sink_path="pod1/servers",  # Same pod
    mode="combine"
)

north_south_flow = network.max_flow(
    source_path="pod1/servers",
    sink_path="pod2/servers",  # Different pod
    mode="combine" 
)

print(f"East-West capacity (intra-pod): {east_west_flow}")
print(f"North-South capacity (inter-pod): {north_south_flow}")

# Calculate oversubscription ratios
server_access_bandwidth = 8 * 10 * 2  # 8 servers × 10G × 2 links
spine_uplink_bandwidth = 4 * 40  # 4 leaf × 40G uplinks
oversubscription = server_access_bandwidth / spine_uplink_bandwidth
print(f"Pod oversubscription ratio: {oversubscription}:1")
```

## Next Steps

Now that you've learned Clos network analysis fundamentals:

- **[Clos Fabric Example](../examples/clos-fabric.md)** - Deep dive into 3-tier Clos fabrics
- **[DSL Reference](../reference/dsl.md)** - Learn the complete YAML syntax
- **[API Reference](../reference/api.md)** - Explore the Python API in detail

## Key Takeaways

- **Clos topologies** provide excellent scalability and path diversity for data center networks
- **Flow placement policies** (ECMP vs UCMP) significantly impact capacity utilization
- **Hierarchical blueprints** make complex network definitions maintainable and reusable
- **Failure analysis** helps validate network resilience and identify potential bottlenecks
- **NetworkExplorer** provides powerful tools for understanding topology structure and capacity distribution
