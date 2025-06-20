# Basic Example

In this toy example, we'll create a simple graph with parallel edges and alternative paths, then run max flow analysis with different flow placement policies.

### Creating a Simple Network

**Network Topology:**

```
             [1,1] & [1,2]     [1,1] & [1,2]
      A ─────────────────── B ────────────── C
      │                                      │
      │    [2,3]                             │ [2,3]
      └──────────────────── D ───────────────┘

[1,1] and [1,2] are parallel edges between A and B.
They have the same metric of 1 but different capacities (1 and 2).
```

Let's create this network by using NetGraph's scenario system:

```python
from ngraph.scenario import Scenario
from ngraph.lib.algorithms.base import FlowPlacement

# Define network topology with parallel paths
scenario_yaml = """
network:
  name: "fundamentals_example"
  seed: 1234  # Optional: ensures reproducible results

  # Create individual nodes
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}

  # Create links with different capacities and costs
  links:
    # Parallel edges between A→B
    - source: A
      target: B
      link_params:
        capacity: 1
        cost: 1
    - source: A
      target: B
      link_params:
        capacity: 2
        cost: 1

    # Parallel edges between B→C
    - source: B
      target: C
      link_params:
        capacity: 1
        cost: 1
    - source: B
      target: C
      link_params:
        capacity: 2
        cost: 1

    # Alternative path A→D→C
    - source: A
      target: D
      link_params:
        capacity: 3
        cost: 2
    - source: D
      target: C
      link_params:
        capacity: 3
        cost: 2
"""

# Create the network
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
```

Note that here we used a simple `nodes` and `links` structure to directly define the network topology. The optional `seed` parameter ensures reproducible results when using randomized workflow steps. In more complex scenarios, you would typically use `groups` and `adjacency` to define groups of nodes and their connections, or even leverage the `blueprints` to create reusable components. This advanced functionality is explained in the [DSL Reference](../reference/dsl.md) and used in the [Clos Fabric Analysis](clos-fabric.md) example.

### Flow Analysis Variants

Now let's run MaxFlow using the high-level Network API:

```python
# 1. "True" maximum flow (uses all available paths)
max_flow_all = network.max_flow(source_path="A", sink_path="C")
print(f"Maximum flow (all paths): {max_flow_all}")
# Result: 6.0 (uses both A→B→C path capacity of 3 and A→D→C path capacity of 3)

# 2. Flow along shortest paths only
max_flow_shortest = network.max_flow(
    source_path="A",
    sink_path="C",
    shortest_path=True
)
print(f"Flow on shortest paths: {max_flow_shortest}")
# Result: 3.0 (only uses A→B→C path, ignoring higher-cost A→D→C path)

# 3. Equal-balanced flow placement on shortest paths
max_flow_shortest_balanced = network.max_flow(
    source_path="A",
    sink_path="C",
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Equal-balanced flow: {max_flow_shortest_balanced}")
# Result: 2.0 (splits flow equally across parallel edges in A→B and B→C)
```

### Results Interpretation

- **"True" MaxFlow**: Uses all available paths regardless of their cost
- **Shortest Path**: Only uses paths with the minimum cost
- **EQUAL_BALANCED Flow Placement**: Distributes flows equally across all parallel paths. The total flow can be limited by the smallest capacity path.

Note that `EQUAL_BALANCED` flow placement is only applicable when calculating MaxFlow on shortest paths.

### Advanced Analysis: Sensitivity Analysis

For deeper network analysis, you can use the low-level graph algorithms to perform sensitivity analysis and identify bottleneck edges:

```python
from ngraph.lib.algorithms.max_flow import calc_max_flow, saturated_edges, run_sensitivity

# Get the underlying graph for low-level analysis
graph = network.to_strict_multidigraph()

# Identify bottleneck (saturated) edges
bottlenecks = saturated_edges(graph, "A", "C")
print(f"Bottleneck edges: {bottlenecks}")

# Perform sensitivity analysis - test increasing capacity by 1 unit
sensitivity_increase = run_sensitivity(graph, "A", "C", change_amount=1.0)
print(f"Sensitivity to capacity increases: {sensitivity_increase}")

# Test sensitivity to capacity decreases
sensitivity_decrease = run_sensitivity(graph, "A", "C", change_amount=-1.0)
print(f"Sensitivity to capacity decreases: {sensitivity_decrease}")
```

This analysis helps identify:

- **Bottleneck edges**: Links that are fully utilized and limit overall flow
- **High-impact upgrades**: Which capacity increases provide the most benefit
- **Vulnerability assessment**: How flow decreases when links are degraded

## Next Steps

- **[Tutorial](../getting-started/tutorial.md)** - Build network scenarios
- **[Clos Fabric Analysis](clos-fabric.md)** - More complex example
- **[DSL Reference](../reference/dsl.md)** - Learn the full YAML syntax for scenarios
- **[API Reference](../reference/api.md)** - Explore the Python API for advanced usage
