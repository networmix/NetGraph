# Basic Example

This example builds a tiny topology inline to show APIs. For real analysis, prefer running a provided scenario and generating metrics via the CLI.

See [Tutorial](../getting-started/tutorial.md) for CLI usage and bundled scenarios.

## Creating a Simple Network

**Network Topology:**

```text
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
from ngraph.types.base import FlowPlacement
from ngraph.solver.maxflow import max_flow, max_flow_with_details

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
max_flow_all = max_flow(network, source_path="A", sink_path="C")
print(f"Maximum flow (all paths): {max_flow_all}")
# Result: {('A', 'C'): 6.0} (uses both A→B→C path capacity of 3 and A→D→C path capacity of 3)

# 2. Flow along shortest paths only
max_flow_shortest = max_flow(
    network,
    source_path="A",
    sink_path="C",
    shortest_path=True
)
print(f"Flow on shortest paths: {max_flow_shortest}")
# Result: {('A', 'C'): 3.0} (only uses A→B→C path, ignoring higher-cost A→D→C path)

# 3. Equal-balanced flow placement on shortest paths
max_flow_shortest_balanced = max_flow(
    network,
    source_path="A",
    sink_path="C",
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED
)
print(f"Equal-balanced flow: {max_flow_shortest_balanced}")
# Result: {('A', 'C'): 2.0} (splits flow equally across parallel edges in A→B and B→C)
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
result = max_flow_with_details(
    network,
    source_path="A",
    sink_path="C",
    mode="combine"
)

# Extract flow value and summary
(src_label, sink_label), summary = next(iter(result.items()))

print(f"Total flow: {summary.total_flow}")
print(f"Cost distribution: {summary.cost_distribution}")

# Example output:
# Total flow: 6.0
# Cost distribution: {2.0: 3.0, 4.0: 3.0}
#
# This means:
# - 3.0 units of flow use paths with total cost 2.0 (A→B→C path)
# - 3.0 units of flow use paths with total cost 4.0 (A→D→C path)
```

### Latency Span Analysis

If link costs approximate latency, derive span summary from cost distribution:

```python
def analyze_latency_span(cost_distribution):
    """Analyze latency characteristics from cost distribution."""
    if not cost_distribution:
        return "No flow paths available"

    total_flow = sum(cost_distribution.values())
    weighted_avg_latency = sum(
        cost * flow for cost, flow in cost_distribution.items()
    ) / total_flow

    min_latency = min(cost_distribution.keys())
    max_latency = max(cost_distribution.keys())
    latency_span = max_latency - min_latency

    print(f"Latency Analysis:")
    print(f"  Average latency: {weighted_avg_latency:.2f}")
    print(f"  Latency range: {min_latency:.1f} - {max_latency:.1f}")
    print(f"  Latency span: {latency_span:.1f}")
    print(f"  Flow distribution:")
    for cost, flow in sorted(cost_distribution.items()):
        percentage = (flow / total_flow) * 100
        print(f"    {percentage:.1f}% uses paths with latency {cost:.1f}")

# Example usage
analyze_latency_span(summary.cost_distribution)
```

This helps identify traffic concentration, latency span, and potential bottlenecks.

## Advanced Analysis: Failure Simulation

You can analyze the network under different failure scenarios by excluding nodes or links:

```python
# Identify link to fail
failed_links = set()
for link_id, link in network.links.items():
    if link.source == "A" and link.target == "D":
        failed_links.add(link_id)
        break

# Compare flows: baseline vs. with failure
baseline_flow_dict = max_flow(network, source_path="A", sink_path="C")
baseline_flow = baseline_flow_dict[('A', 'C')]

degraded_flow_dict = max_flow(
    network,
    source_path="A",
    sink_path="C",
    excluded_links=failed_links
)
degraded_flow = degraded_flow_dict[('A', 'C')]

print(f"Baseline flow: {baseline_flow}")
print(f"Flow with A->D link failed: {degraded_flow}")
print(f"Impact: {baseline_flow - degraded_flow} units lost")
```

This analysis helps identify:

- **Critical links**: Links whose failure significantly impacts flow
- **Redundancy**: How well the network handles failures
- **Vulnerability assessment**: Network resilience under different failure scenarios

## Next Steps

- **[Bundled Scenarios](bundled-scenarios.md)** - Ready-to-run examples
- **[Clos Fabric Analysis](clos-fabric.md)** - More complex example
- **[Workflow Reference](../reference/workflow.md)** - Analysis workflows and Monte Carlo simulation
- **[DSL Reference](../reference/dsl.md)** - Learn the full YAML syntax for scenarios
- **[API Reference](../reference/api.md)** - Explore the Python API for advanced usage
