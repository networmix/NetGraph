# Clos Fabric Analysis

Maximum flow between two 3-tier Clos fabrics, comparing ECMP and WCMP placement with and without failures. The [Tutorial](../getting-started/tutorial.md) covers running the bundled scenarios from the CLI.

## Scenario

Two 3-tier Clos networks joined spine to spine. The scenario nests blueprints inside blueprints and wires the tiers with `mesh` and `one_to_one` link patterns.

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

# Build the network
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network

# Maximum flow with ECMP
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

## Reading the result

The result `{('b1|b2', 'b1|b2'): 256.0}` means:

- **Source**: All t1 nodes in both b1 and b2 segments of my_clos1
- **Target**: All t1 nodes in both b1 and b2 segments of my_clos2
- **Capacity**: Maximum flow of 256.0 units

## ECMP versus WCMP with uneven links

Two placement policies split flow across equal-cost paths: `FlowPlacement.EQUAL_BALANCED` gives every path the same share (ECMP) and `FlowPlacement.PROPORTIONAL` weights the shares by capacity (WCMP). With `shortest_path=True` both stay on the equal-cost paths; with `shortest_path=False` placement spills onto costlier paths as capacity runs out, which is traffic engineering.

The example above pairs `EQUAL_BALANCED` with `shortest_path=True`, which is ECMP. Compare it with `PROPORTIONAL` under two conditions:

- Symmetric parallel inter-spine links: ECMP and WCMP both give 256.0.
- Uneven capacities within each equal-cost bundle: WCMP carries more, because ECMP is capped by the equal split.

The code below makes the 4 parallel spine-to-spine links of each pair uneven while keeping their costs equal, so only the splitting policy differs.

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
    links = sorted(groups[key], key=lambda x: x.id)
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

Uneven links drop ECMP to 64 while WCMP keeps 248. ECMP gives every member of a bundle the same share, so the smallest link caps the bundle.

## Failure Analysis

The same ECMP-versus-WCMP question under failures, this time with `FailureManager` running a Monte Carlo over random spine failures in `my_clos1`. Each iteration fails two spines; identical failure patterns are run once and weighted by how often they were drawn.

```python
from collections import Counter
from ngraph import FailureManager, FlowPlacement
from ngraph.model.failure.policy import FailurePolicy, FailureMode, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet

# Restore symmetric inter-spine links for this section
for lk in network.links.values():
    if lk.source.startswith("my_clos1/spine") or lk.source.startswith("my_clos2/spine"):
        lk.capacity = 1.0

two_spines = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[
    FailureRule(scope="node", mode="choice", count=2, path="^my_clos1/spine/"),
])])
fm = FailureManager(
    network=network,
    failure_policy_set=FailurePolicySet(policies={"two_spines": two_spines}),
    policy_name="two_spines",
)

for placement in (FlowPlacement.EQUAL_BALANCED, FlowPlacement.PROPORTIONAL):
    mc = fm.run_max_flow_monte_carlo(
        source=r"my_clos1.*(b[0-9]*)/t1",
        target=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        iterations=100,
        parallelism=1,
        seed=1,
        shortest_path=True,
        flow_placement=placement,
    )
    capacity = Counter()
    for item in mc["results"]:
        capacity[item.summary.total_placed] += item.occurrence_count
    print(placement.name, "baseline", mc["baseline"].summary.total_placed,
          "under failure", dict(sorted(capacity.items())))
```

```text
EQUAL_BALANCED baseline 256.0 under failure {192.0: 13, 224.0: 87}
PROPORTIONAL baseline 256.0 under failure {248.0: 100}
```

Losing two spines removes 8 of 256 inter-spine links. WCMP loses exactly that capacity in every iteration. ECMP loses 32, or 64 when both failed spines serve the same t2 switch, because the surviving equal-cost next hops still receive equal shares and the smallest one caps the whole split.

## Network structure

`NetworkExplorer` prints the node hierarchy with node, link and capacity statistics per subtree:

```python
from ngraph.explorer import NetworkExplorer

explorer = NetworkExplorer.explore_network(network)
explorer.print_tree(skip_leaves=True, detailed=False)  # skip_leaves hides individual nodes
```

## Next Steps

- **[Bundled Scenarios](bundled-scenarios.md)** - Ready-to-run examples
- **[Workflow Reference](../reference/workflow.md)** - Analysis workflows and Monte Carlo simulation
- **[DSL Reference](../reference/dsl.md)** - YAML syntax reference
- **[API Reference](../reference/api.md)** - Python API
