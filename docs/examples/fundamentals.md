# Flow Analysis Fundamentals

This guide demonstrates core flow analysis concepts in NetGraph using simple examples. These fundamentals will help you understand the more complex scenarios in the [Clos Fabric Analysis](clos-fabric.md) example.

## Max Flow Analysis with Parallel Paths

Understanding how NetGraph calculates flows when multiple paths exist between nodes is crucial for network analysis.

### Example Network

Let's create a simple network with parallel edges and alternative paths:

```python
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.max_flow import calc_max_flow
from ngraph.lib.algorithms.base import FlowPlacement

# Build a graph with parallel edges and alternative paths
g = StrictMultiDiGraph()
for node in ("A", "B", "C", "D"):
    g.add_node(node)

# Create parallel edges between A→B and B→C
g.add_edge("A", "B", key=0, cost=1, capacity=1)
g.add_edge("A", "B", key=1, cost=1, capacity=2)
g.add_edge("B", "C", key=2, cost=1, capacity=1)
g.add_edge("B", "C", key=3, cost=1, capacity=2)

# Create an alternative path A→D→C
g.add_edge("A", "D", key=4, cost=2, capacity=3)
g.add_edge("D", "C", key=5, cost=2, capacity=3)
```

**Network Topology:**
```
             [1,1] & [1,2]     [1,1] & [1,2]
      A ──────────────────► B ─────────────► C
      │                                      ▲
      │    [2,3]                             │ [2,3]
      └───────────────────► D ───────────────┘
```

### Flow Analysis Variants

Now let's analyze different types of flows:

```python
# 1. True maximum flow (uses all available paths)
max_flow_all = calc_max_flow(g, "A", "C")
print(f"Maximum flow (all paths): {max_flow_all}")
# Result: 6.0 (uses both A→B→C path capacity of 3 and A→D→C path capacity of 3)

# 2. Flow along shortest paths only
max_flow_shortest = calc_max_flow(g, "A", "C", shortest_path=True)
print(f"Flow on shortest paths: {max_flow_shortest}")
# Result: 3.0 (only uses A→B→C path, ignoring higher-cost A→D→C path)

# 3. Equal-balanced flow placement on shortest paths
max_flow_balanced = calc_max_flow(
    g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Equal-balanced flow: {max_flow_balanced}")
# Result: 2.0 (splits flow equally across parallel A→B edges, limited by smaller capacity)
```

### Key Concepts

- **True Max Flow**: Uses all available paths regardless of cost
- **Shortest Path Flow**: Only uses paths with minimum cost 
- **Flow Placement**: How traffic is distributed across parallel paths
  - `PROPORTIONAL` (UCMP): Distributes based on capacity ratios
  - `EQUAL_BALANCED` (ECMP): Distributes equally across paths

## Traffic Engineering with Demands

Real networks carry multiple traffic demands simultaneously. Let's explore how NetGraph handles demand placement and routing.

### Example: Bidirectional Traffic

```python
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.flow_policy import FlowPolicyConfig, get_flow_policy
from ngraph.lib.demand import Demand

# Build a triangular network
g = StrictMultiDiGraph()
for node in ("A", "B", "C"):
    g.add_node(node)

# Create bidirectional links
g.add_edge("A", "B", key=0, cost=1, capacity=15)
g.add_edge("B", "A", key=1, cost=1, capacity=15)
g.add_edge("B", "C", key=2, cost=1, capacity=15)
g.add_edge("C", "B", key=3, cost=1, capacity=15)
g.add_edge("A", "C", key=4, cost=1, capacity=5)  # Bottleneck link
g.add_edge("C", "A", key=5, cost=1, capacity=5)  # Bottleneck link
```

**Network Topology:**
```
          [15]
      A ─────── B
       \      /
    [5] \    / [15]
         \  /
          C
```

### Placing Traffic Demands

```python
# Initialize flow tracking
flow_graph = init_flow_graph(g)

# Create flow policies for traffic engineering
flow_policy_1 = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
flow_policy_2 = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)

# Place a large demand from A to C
demand_ac = Demand("A", "C", 20, flow_policy=flow_policy_1)
demand_ac.place(flow_graph)
print(f"A→C demand (20 units): placed {demand_ac.placed_demand}")

# Place reverse demand from C to A  
demand_ca = Demand("C", "A", 20, flow_policy=flow_policy_2)
demand_ca.place(flow_graph)
print(f"C→A demand (20 units): placed {demand_ca.placed_demand}")
```

**Results:**
- Both 20-unit demands are fully satisfied
- Traffic routes around the 5-unit bottleneck via the A→B→C path
- Each demand uses separate flow accounting (no interference)

### Traffic Engineering Insights

This example demonstrates:

1. **Automatic Route Selection**: NetGraph finds optimal paths around bottlenecks
2. **Bidirectional Independence**: Forward and reverse flows can use different policies
3. **Capacity Awareness**: Demands are placed optimally based on available capacity
4. **Flow Policy Isolation**: Each demand maintains separate flow accounting

## Next Steps

Now that you understand flow analysis fundamentals:

- **[Clos Fabric Analysis](clos-fabric.md)** - Apply these concepts to complex data center networks
- **[Tutorial](../getting-started/tutorial.md)** - Build complete network scenarios
- **[DSL Reference](../reference/dsl.md)** - Learn the full YAML syntax for scenarios

## Key Takeaways

- **Multiple flow calculation modes** serve different analysis purposes
- **Flow placement policies** significantly impact results in networks with parallel paths  
- **Traffic demands** can be placed independently with different engineering policies
- **Path diversity** allows networks to route around bottlenecks automatically
- Understanding these **fundamentals** is essential for analyzing larger network topologies
