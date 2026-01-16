# Basic Example

This example builds a tiny topology inline to show APIs. For real analysis, prefer running a provided scenario and generating metrics via the CLI.

See [Tutorial](../getting-started/tutorial.md) for CLI usage and bundled scenarios.

## Creating a Simple Network

**Network Topology:**

```text
             [1,1] & [1,2]     [1,1] & [1,2]
      A -------------------- B ---------------- C
      |                                         |
      |    [2,3]                                | [2,3]
      +-------------------- D -----------------+

[1,1] and [1,2] are parallel edges between A and B.
They have the same metric of 1 but different capacities (1 and 2).
```

Let's create this network by using NetGraph's scenario system:

```python
from ngraph.scenario import Scenario
from ngraph import analyze, Mode, FlowPlacement

# Define network topology with parallel paths
scenario_yaml = """
seed: 1234  # Optional: ensures reproducible results

network:
  name: "fundamentals_example"

  # Create individual nodes
  nodes:
    A: {}
    B: {}
    C: {}
    D: {}

  # Create links with different capacities and costs
  links:
    # Parallel edges between A->B
    - source: A
      target: B
      capacity: 1
      cost: 1
    - source: A
      target: B
      capacity: 2
      cost: 1

    # Parallel edges between B->C
    - source: B
      target: C
      capacity: 1
      cost: 1
    - source: B
      target: C
      capacity: 2
      cost: 1

    # Alternative path A->D->C
    - source: A
      target: D
      capacity: 3
      cost: 2
    - source: D
      target: C
      capacity: 3
      cost: 2
"""

# Create the network
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
```

Note that here we used a simple `nodes` and `links` structure to directly define the network topology. The optional `seed` parameter ensures reproducible results when using randomized workflow steps. In more complex scenarios, you would typically use node groups with `count` and `template` to define groups of nodes and link rules to define their connections, or even leverage the `blueprints` to create reusable components. This advanced functionality is explained in the [DSL Reference](../reference/dsl.md) and used in the [Clos Fabric Analysis](clos-fabric.md) example.

### Flow Analysis Variants

Now let's run MaxFlow using the `analyze()` API:

```python
# 1. "True" maximum flow (uses all available paths)
max_flow_all = analyze(network).max_flow("^A$", "^C$", mode=Mode.COMBINE)
print(f"Maximum flow (all paths): {max_flow_all}")
# Result: {('^A$', '^C$'): 6.0} (uses both A->B->C path capacity of 3 and A->D->C path capacity of 3)

# 2. Flow along shortest paths only
max_flow_shortest = analyze(network).max_flow(
    "^A$",
    "^C$",
    mode=Mode.COMBINE,
    shortest_path=True
)
print(f"Flow on shortest paths: {max_flow_shortest}")
# Result: {('^A$', '^C$'): 3.0} (only uses A->B->C path, ignoring higher-cost A->D->C path)

# 3. Equal-balanced flow placement on shortest paths
max_flow_shortest_balanced = analyze(network).max_flow(
    "^A$",
    "^C$",
    mode=Mode.COMBINE,
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Equal-balanced flow: {max_flow_shortest_balanced}")
# Result: {('^A$', '^C$'): 2.0} (splits flow equally across parallel edges in A->B and B->C)
```

## Results Interpretation

- **"True" MaxFlow**: Uses all available paths regardless of their cost
- **Shortest Path**: Only uses paths with the minimum cost
- **EQUAL_BALANCED Flow Placement**: Distributes flows equally across all parallel paths. The total flow can be limited by the smallest capacity path.

Note that `EQUAL_BALANCED` flow placement is only applicable when calculating MaxFlow on shortest paths.

## Cost Distribution

Cost distribution shows how flow splits across path costs for latency/span analysis:

```python
# Get flow analysis with cost distribution
result = analyze(network).max_flow_detailed(
    "^A$",
    "^C$",
    mode=Mode.COMBINE
)

# Extract flow value and summary
(src_label, target_label), summary = next(iter(result.items()))

print(f"Total flow: {summary.total_flow}")
print(f"Cost distribution: {summary.cost_distribution}")

# Example output:
# Total flow: 6.0
# Cost distribution: {2.0: 3.0, 4.0: 3.0}
#
# This means:
# - 3.0 units of flow use paths with total cost 2.0 (A->B->C path)
# - 3.0 units of flow use paths with total cost 4.0 (A->D->C path)
```

### Latency Span Analysis

If link costs approximate latency, derive span summary from cost distribution:

```python
# Example cost distribution analysis
cost_dist = summary.cost_distribution  # {2.0: 3.0, 4.0: 3.0}
total_flow = summary.total_flow        # 6.0

# Calculate weighted average latency
avg_latency = sum(cost * flow for cost, flow in cost_dist.items()) / total_flow
print(f"Average latency: {avg_latency}")  # 3.0

# Find min/max latency tiers
min_latency = min(cost_dist.keys())
max_latency = max(cost_dist.keys())
print(f"Latency range: {min_latency} - {max_latency}")  # 2.0 - 4.0
```

## Efficient Repeated Analysis

For scenarios requiring multiple analyses with different exclusions (e.g., failure testing), use a bound context:

```python
# Create bound context - graph built once
ctx = analyze(network, source="^A$", sink="^C$", mode=Mode.COMBINE)

# Baseline capacity
baseline = ctx.max_flow()
print(f"Baseline: {baseline}")

# Test various failure scenarios
for node in ["B", "D"]:
    degraded = ctx.max_flow(excluded_nodes={node})
    print(f"Without {node}: {degraded}")

# Output:
# Baseline: {('^A$', '^C$'): 6.0}
# Without B: {('^A$', '^C$'): 3.0}
# Without D: {('^A$', '^C$'): 3.0}
```

## Sensitivity Analysis

Identify which edges are critical for the flow:

```python
# Get sensitivity analysis
sensitivity = analyze(network).sensitivity(
    "^A$",
    "^C$",
    mode=Mode.COMBINE,
    shortest_path=False  # Full max-flow mode
)

for pair, edge_impacts in sensitivity.items():
    print(f"Critical edges for {pair}:")
    for edge_key, flow_reduction in sorted(edge_impacts.items(), key=lambda x: -x[1]):
        print(f"  {edge_key}: -{flow_reduction:.1f}")
```

## Shortest Paths

Get actual path objects for routing analysis:

```python
from ngraph import EdgeSelect

# Get all equal-cost shortest paths
paths = analyze(network).shortest_paths(
    "^A$",
    "^C$",
    mode=Mode.COMBINE,
    edge_select=EdgeSelect.ALL_MIN_COST
)

for pair, path_list in paths.items():
    print(f"Paths from {pair[0]} to {pair[1]}:")
    for path in path_list:
        nodes = [elem[0] for elem in path.path]
        print(f"  {' -> '.join(nodes)} (cost: {path.cost})")

# Get k-shortest paths
k_paths = analyze(network).k_shortest_paths(
    "^A$",
    "^C$",
    max_k=3,
    mode=Mode.PAIRWISE
)

for pair, path_list in k_paths.items():
    print(f"Top {len(path_list)} paths from {pair[0]} to {pair[1]}:")
    for i, path in enumerate(path_list, 1):
        print(f"  {i}. Cost: {path.cost}")
```
