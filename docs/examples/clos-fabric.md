# Clos Fabric Analysis

This example demonstrates analysis of a 3-tier Clos fabric. For production use, run the bundled scenario and generate metrics via CLI, then iterate in Python if needed.

Refer to [Tutorial](../getting-started/tutorial.md) for running bundled scenarios via CLI.

## Scenario Overview

We'll create two separate 3-tier Clos networks and analyze the maximum flow capacity between them. This scenario showcases:

- Hierarchical blueprint composition
- Complex link patterns
- Flow analysis with different placement policies

## Programmatic scenario

```python
from ngraph.scenario import Scenario
from ngraph import analyze, Mode, FlowPlacement

scenario_yaml = """
blueprints:
  brick_2tier:
    nodes:
      t1:
        count: 8
        template: "t1-{n}"
      t2:
        count: 8
        template: "t2-{n}"

    links:
      - source: /t1
        target: /t2
        pattern: mesh
        capacity: 2
        cost: 1

  3tier_clos:
    nodes:
      b1:
        blueprint: brick_2tier
      b2:
        blueprint: brick_2tier
      spine:
        count: 64
        template: "t3-{n}"

    links:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        capacity: 2
        cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        capacity: 2
        cost: 1

network:
  name: "3tier_clos_network"
  version: 1.0

  nodes:
    my_clos1:
      blueprint: 3tier_clos

    my_clos2:
      blueprint: 3tier_clos

  links:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      count: 4
      capacity: 1
      cost: 1
"""

# Create and analyze the scenario
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network

# Calculate maximum flow with ECMP (Equal Cost Multi-Path)
max_flow_ecmp = analyze(network).max_flow(
    r"my_clos1.*(b[0-9]*)/t1",
    r"my_clos2.*(b[0-9]*)/t1",
    mode=Mode.COMBINE,
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED,
)

print(f"Maximum flow with ECMP: {max_flow_ecmp}")
# Result: {('b1|b2', 'b1|b2'): 256.0}
```

## Understanding the Results

The result `{('b1|b2', 'b1|b2'): 256.0}` means:

- **Source**: All t1 nodes in both b1 and b2 segments of my_clos1
- **Target**: All t1 nodes in both b1 and b2 segments of my_clos2
- **Capacity**: Maximum flow of 256.0 units

## ECMP vs WCMP: Impact of Link Failures

NetGraph supports different flow placement policies:

- `FlowPlacement.EQUAL_BALANCED`: Equal split across equal-cost paths
- `FlowPlacement.PROPORTIONAL`: Capacity-weighted split across equal-cost paths

Combined with the path selection settings (shortest_path=True|False), we can achieve different flow placement policies emulating ECMP, WCMP, and TE behavior in IP/MPLS networks.

In this example, we use the `FlowPlacement.EQUAL_BALANCED` policy and `shortest_path=True` to emulate ECMP behavior and we will compare it with WCMP `FlowPlacement.PROPORTIONAL` (capacity-weighted split across equal-cost paths) under two conditions:

- Baseline: symmetric parallel inter-spine links -> ECMP = WCMP (256.0).
- Uneven links: make capacities within each equal-cost bundle different -> WCMP
  achieves higher throughput than ECMP, which is limited by equal splitting.

We emulate partial inter-spine degradation by making capacities uneven across the
4 parallel spine-to-spine links per pair while keeping equal costs. This isolates
the effect of the splitting policy.

```python
from ngraph import analyze, Mode, FlowPlacement
from ngraph.scenario import Scenario

scenario_yaml = """
blueprints:
  brick_2tier:
    nodes:
      t1: {count: 8, template: "t1-{n}"}
      t2: {count: 8, template: "t2-{n}"}
    links:
      - {source: /t1, target: /t2, pattern: mesh, capacity: 2, cost: 1}
  3tier_clos:
    nodes:
      b1: {blueprint: brick_2tier}
      b2: {blueprint: brick_2tier}
      spine: {count: 64, template: "t3-{n}"}
    links:
      - {source: b1/t2, target: spine, pattern: one_to_one, capacity: 2, cost: 1}
      - {source: b2/t2, target: spine, pattern: one_to_one, capacity: 2, cost: 1}
network:
  name: 3tier_clos_network
  nodes:
    my_clos1: {blueprint: 3tier_clos}
    my_clos2: {blueprint: 3tier_clos}
  links:
    - {source: my_clos1/spine, target: my_clos2/spine, pattern: one_to_one, count: 4, capacity: 1, cost: 1}
"""

scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network

# Baseline (symmetric)
baseline_ecmp = analyze(network).max_flow(
    r"my_clos1.*(b[0-9]*)/t1",
    r"my_clos2.*(b[0-9]*)/t1",
    mode=Mode.COMBINE, shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED,
)
baseline_wcmp = analyze(network).max_flow(
    r"my_clos1.*(b[0-9]*)/t1",
    r"my_clos2.*(b[0-9]*)/t1",
    mode=Mode.COMBINE, shortest_path=True,
    flow_placement=FlowPlacement.PROPORTIONAL,
)

# Make parallel inter-spine links uneven (keeps equal cost)
from collections import defaultdict
groups = defaultdict(list)
for lk in network.links.values():
    s, t = lk.source, lk.target
    if (s.startswith("my_clos1/spine") and t.startswith("my_clos2/spine")) or \
       (s.startswith("my_clos2/spine") and t.startswith("my_clos1/spine")):
        groups[(s, t)].append(lk)
for i, key in enumerate(sorted(groups.keys())):
    links = sorted(groups[key], key=lambda x: (x.source, x.target, id(x)))
    caps = [4.0, 0.25, 0.25, 0.25] if i % 2 == 0 else [2.0, 1.0, 0.5, 0.25]
    for lk, cap in zip(links, caps):
        lk.capacity = cap

ecmp = analyze(network).max_flow(
    r"my_clos1.*(b[0-9]*)/t1",
    r"my_clos2.*(b[0-9]*)/t1",
    mode=Mode.COMBINE, shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED,
)
wcmp = analyze(network).max_flow(
    r"my_clos1.*(b[0-9]*)/t1",
    r"my_clos2.*(b[0-9]*)/t1",
    mode=Mode.COMBINE, shortest_path=True,
    flow_placement=FlowPlacement.PROPORTIONAL,
)
print("Baseline ECMP:", baseline_ecmp)
print("Baseline WCMP:", baseline_wcmp)
print("Uneven ECMP:", ecmp)
print("Uneven WCMP:", wcmp)
```

Example output:

```text
Baseline ECMP: {('b1|b2', 'b1|b2'): 256.0}
Baseline WCMP: {('b1|b2', 'b1|b2'): 256.0}
Uneven ECMP: {('b1|b2', 'b1|b2'): 64.0}
Uneven WCMP: {('b1|b2', 'b1|b2'): 248.0}
```

As expected, WCMP achieves higher throughput than ECMP when parallel links within equal-cost bundles have uneven capacities. ECMP is limited by the link with the lowest capacity in the equal-cost group.

## Network Structure Analysis

We can also analyze the network structure using the NetworkExplorer:

```python
from ngraph.explorer import NetworkExplorer

# Explore the network topology
explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)

# The explorer shows hierarchical structure and connectivity patterns
# For detailed path analysis, use max_flow_detailed to get flow details
# including cost distribution and path information
```

## Next Steps

- **[Bundled Scenarios](bundled-scenarios.md)** - Ready-to-run examples
- **[Workflow Reference](../reference/workflow.md)** - Analysis workflows and Monte Carlo simulation
- **[DSL Reference](../reference/dsl.md)** - YAML syntax reference
- **[API Reference](../reference/api.md)** - Explore the Python API in detail
