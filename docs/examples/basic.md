# Basic Example

A tiny topology defined inline, used here to walk through the analysis APIs. For real analysis, run a bundled scenario through the CLI and generate metrics from that.

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

Build it with the scenario system:

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

This spells out every node and link individually. The optional `seed` makes randomized workflow steps reproducible. Larger topologies instead use node groups (`count` plus `template`) with link rules connecting them, or `blueprints` for reusable components - see the [DSL Reference](../reference/dsl.md) and the [Clos Fabric Analysis](clos-fabric.md) example.

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

`EQUAL_BALANCED` flow placement is typically used with `shortest_path=True` to simulate traditional ECMP behavior, where flows are split equally across equal-cost paths.

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

## Demand Placement

Max-flow asks how much the network could carry. Demand placement asks how much of a given volume it does carry under a routing model. The same 6 units from A to C give a different answer under each preset:

```python
from ngraph.analysis.functions import demand_placement_analysis

for preset in ("SHORTEST_PATHS_ECMP", "SHORTEST_PATHS_ECMP_LOSSY",
               "SHORTEST_PATHS_WCMP", "TE_WCMP_UNLIM"):
    result = demand_placement_analysis(
        network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=[{"source": "^A$", "target": "^C$", "volume": 6,
                         "mode": "pairwise", "flow_policy": preset}],
        include_flow_details=True,
    )
    entry = result.flows[0]
    print(f"{preset}: placed={entry.placed:g} dropped={entry.dropped:g} "
          f"by_cost={entry.cost_distribution} {entry.data}")

# SHORTEST_PATHS_ECMP: placed=2 dropped=4 by_cost={2.0: 2.0} {}
# SHORTEST_PATHS_ECMP_LOSSY: placed=2.5 dropped=3.5 by_cost={2.0: 2.5} {'dropped_edges': {'A|B|0:fwd': 2.0, 'A|B|1:fwd': 1.0, 'B|C|0:fwd': 0.5}}
# SHORTEST_PATHS_WCMP: placed=3 dropped=3 by_cost={2.0: 3.0} {}
# TE_WCMP_UNLIM: placed=6 dropped=0 by_cost={2.0: 3.0, 4.0: 3.0} {}
```

- `SHORTEST_PATHS_ECMP` hashes 3 units onto each parallel link of the cost-2 path. The capacity-1 link admits only 1 without loss, so the whole demand is admitted at that scale: 2 units.
- `SHORTEST_PATHS_ECMP_LOSSY` sends the same 3 and 3, and each link carries what fits. 2.5 units arrive; `dropped_edges` says where the other 3.5 were lost.
- `SHORTEST_PATHS_WCMP` splits by capacity, so the cost-2 path carries its full 3 units. The demand does not leave the shortest path, so 3 units are unmet.
- `TE_WCMP_UNLIM` reroutes the remainder onto the cost-4 path and places everything.

In a scenario file the same choice is the demand's `flow_policy`; see the [Tutorial](../getting-started/tutorial.md) for placement inside a workflow.
