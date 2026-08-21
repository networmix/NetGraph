# API Reference

Quick links:

- [Design](design.md) -- architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) -- YAML syntax for scenario definition
- [Workflow Reference](workflow.md) -- analysis workflow configuration and execution
- [CLI Reference](cli.md) -- command-line tools for running scenarios
- [Auto-Generated API Reference](api-full.md) -- complete class and method documentation

A curated guide to NetGraph's Python API, organized by typical usage patterns.

## 1. Programmatic Quickstart

Minimal, copy-pastable start: build a tiny network, run max-flow, and reuse a bound context.

```python
from ngraph import Network, Node, Link, analyze, Mode

# Build a small directed network
net = Network()
net.add_node(Node(name="A"))
net.add_node(Node(name="B"))
net.add_node(Node(name="C"))
net.add_link(Link(source="A", target="B", capacity=10.0, cost=1.0))
net.add_link(Link(source="B", target="C", capacity=5.0, cost=1.0))

# One-off max-flow (unbound context)
flow = analyze(net).max_flow("^A$", "^C$", mode=Mode.COMBINE)
print(flow)  # {('^A$', '^C$'): 5.0}

# Detailed flow with cost distribution
detailed = analyze(net).max_flow_detailed("^A$", "^C$", mode=Mode.COMBINE)
(_, _), summary = next(iter(detailed.items()))
print(summary.total_flow, summary.cost_distribution)

# Bound context for repeated runs with exclusions
ctx = analyze(net, source="^A$", sink="^C$", mode=Mode.COMBINE)
baseline = ctx.max_flow()
# Exclude first link by getting its ID from the network
first_link_id = next(iter(net.links.keys()))
degraded = ctx.max_flow(excluded_links={first_link_id})
print("baseline", baseline, "degraded", degraded)
```

## 2. Fundamentals

The three types most NetGraph programs are built from.

### Scenario

The entry point for analysis workflows: it owns the network, runs the workflow steps in order, and stores their results. Load one from YAML for declarative scenarios, or construct one programmatically.

```python
from pathlib import Path
from ngraph import Scenario

# Load complete scenario from YAML text
yaml_text = Path("scenarios/square_mesh.yaml").read_text()
scenario = Scenario.from_yaml(yaml_text)

# Execute the scenario
scenario.run()

# Export results
exported = scenario.results.to_dict()
print(exported["workflow"].keys())
```

**Key Methods:**

- `from_yaml(yaml_str, default_components=None)` - Parse scenario from YAML string (use `Path.read_text()` for file loading)
- `run(step_hook=None)` - Execute workflow steps in sequence. The optional `step_hook` is a callable that receives each `WorkflowStep` and returns a context manager entered around that step's execution (used by the CLI for per-step profiling)

Network, workflow, and Results can also be used independently of Scenario for direct programmatic access.

### Network

The topology itself: nodes, links, and risk groups. Construct one directly for programmatic use, or read the YAML-built topology from `scenario.network`.

```python
from ngraph import Network, Node, Link, analyze

# Create a tiny network
network = Network()
network.add_node(Node(name="n1", risk_groups={"rack1"}))
network.add_node(Node(name="n2", risk_groups={"rack2"}))
network.add_link(Link(source="n1", target="n2", capacity=100.0, risk_groups={"fiber_bundle_A"}))

# Calculate maximum flow using analyze()
flow_result = analyze(network).max_flow("^n1$", "^n2$")
print(flow_result)  # {("^n1$", "^n2$"): 100.0}
```

**Key Methods:**

- `add_node(node)`, `add_link(link)` - Build topology programmatically
- `nodes`, `links` - Access topology as dictionaries

**Key Concepts:**

- **disabled flags:** Node.disabled and Link.disabled mark components as inactive in the scenario topology (use `excluded_nodes`/`excluded_links` parameters for temporary analysis-time exclusion)
- **Risk Groups:** Nodes and links can be tagged with risk group names (e.g., "rack1", "fiber_bundle") to model shared failure domains.
- **Node selection:** Use regex patterns anchored at start (e.g., `"^datacenter.*"`) or selector objects with `path`, `group_by`, and `match` fields to select and group nodes (see DSL Reference)

### Results

Holds each workflow step's output, with metadata, under that step's name; every step writes here. Managed by Scenario - access it via `scenario.results` to read results or to write from a custom step.

```python
# Access results from scenario
results = scenario.results

# Export all results for serialization
all_data = results.to_dict()
print(list(all_data["steps"].keys()))
```

**Key Methods:**

- `enter_step(step_name)` / `exit_step()` - Scope writes to a step (managed by WorkflowStep.execute())
- `put(key, value)` - Store value under active step; key must be `"metadata"` or `"data"`
- `get(key, default=None)` - Retrieve value from active step scope
- `get_step(step_name)` - Retrieve complete step dict for cross-step reads
- `to_dict()` - Export results with shape `{workflow, steps, scenario}` (JSON-serializable)

## 3. NetworkX Integration

Convert between NetworkX graphs and the internal graph format for algorithm execution.

### Converting from NetworkX

```python
import networkx as nx
from ngraph import from_networkx, to_networkx
import netgraph_core

# Create or load a NetworkX graph
G = nx.DiGraph()
G.add_edge("A", "B", capacity=100.0, cost=10)
G.add_edge("B", "C", capacity=50.0, cost=5)
G.add_edge("A", "C", capacity=30.0, cost=25)

# Convert to internal format
graph, node_map, edge_map = from_networkx(G)

# Use with Core algorithms
backend = netgraph_core.Backend.cpu()
algorithms = netgraph_core.Algorithms(backend)
handle = algorithms.build_graph(graph)

# Run shortest path
src_idx = node_map.to_index["A"]
dst_idx = node_map.to_index["C"]
dists, _ = algorithms.spf(handle, src=src_idx, dst=dst_idx)
print(f"Shortest path cost A->C: {dists[dst_idx]}")  # 15.0 (via B)
```

**Key Functions:**

- `from_networkx(G, *, capacity_attr, cost_attr, default_capacity, default_cost, bidirectional)` - Convert NetworkX graph to internal format
- `to_networkx(graph, node_map, *, capacity_attr, cost_attr)` - Convert back to NetworkX MultiDiGraph

**Mapping Classes:**

- `NodeMap` - Bidirectional mapping between node names and integer indices
  - `to_index[name]` - Get integer index for node name
  - `to_name[idx]` - Get node name for integer index
- `EdgeMap` - Bidirectional mapping between edge IDs and original edge references
  - `to_ref[edge_id]` - Get (source, target, key) tuple for edge ID
  - `from_ref[(u, v, key)]` - Get list of edge IDs for original edge

**Options:**

- `bidirectional` - Direction handling. `None` (default) infers from the graph type: directed inputs get one arc per edge; undirected inputs get antiparallel arc pairs (the standard undirected-to-directed reduction for max-flow/reachability). Pass an explicit `True`/`False` to override.
- `capacity_attr` / `cost_attr` - Custom attribute names for capacity and cost
- `default_capacity` / `default_cost` - Default values when attributes missing. Cost values must be integers — `from_networkx` raises `ValueError` on fractional costs because the core engine requires int64 costs; pre-scale fractional costs (e.g., multiply by 10 or 100) before conversion.

### Writing Results Back

```python
# After algorithm execution, map results back to original graph
flow_state = netgraph_core.FlowState(graph)
# ... place flow ...

# edge_flow_view() is indexed by internal Core edge index; translate through
# ext_edge_ids_view() to the external edge IDs that edge_map is keyed by.
ext_edge_ids = graph.ext_edge_ids_view()
for edge_idx, flow in enumerate(flow_state.edge_flow_view()):
    if flow > 0:
        u, v, key = edge_map.to_ref[int(ext_edge_ids[edge_idx])]
        # G is a DiGraph here; for a MultiDiGraph source graph use G.edges[u, v, key]
        G.edges[u, v]["flow"] = float(flow)
```

## 4. Basic Analysis

Max-flow, shortest paths, and edge sensitivity.

### Flow Analysis with `analyze()`

**Purpose:** Calculate network flows between source and sink groups.

**When to use:** Measuring capacity between source and sink groups, under a choice of flow placement policy and with nodes or links excluded to model failures.

**Performance:** Max-flow computation executes in C++ with the GIL released for concurrent execution. The algorithm uses successive shortest paths on the residual graph, pushing a blocking flow across the full ECMP/WCMP shortest-path DAG at each augmentation step until no augmenting path remains. Worst case is `O(E * (V^2 E + (V+E) log V))`; in practice the phase count equals the small number of cost tiers actually used, and the `kMinFlow` tolerance caps phases at `F / kMinFlow` for total flow `F`. See [Design](design.md) for the derivation.

```python
from ngraph import analyze, Mode, FlowPlacement

# Maximum flow between group patterns (combine all sources/sinks)
flow_result = analyze(network).max_flow(
    "^metro1/.*",
    "^metro5/.*",
    mode=Mode.COMBINE
)

# Detailed flow analysis with cost distribution
result = analyze(network).max_flow_detailed(
    "^metro1/.*",
    "^metro5/.*",
    mode=Mode.COMBINE
)
(src_label, sink_label), summary = next(iter(result.items()))
print(summary.cost_distribution)  # Dict[float, float] mapping cost to flow volume
```

**Key Functions:**

- `analyze(network, *, source=None, sink=None, mode=Mode.COMBINE)` - Create analysis context
- `ctx.max_flow(source, sink, *, mode, shortest_path, require_capacity, flow_placement, excluded_nodes, excluded_links)` - Maximum flow
- `ctx.max_flow_detailed(..., include_min_cut=False)` - Maximum flow with cost distribution and optional min-cut; the min-cut is a true minimum cut (its capacity equals the max flow), not the set of saturated edges
- `ctx.sensitivity(...)` - Identify critical edges and their impact on flow
- `ctx.sensitivity_with_flow(...)` - Compute max flow and edge sensitivity together per group pair in a single pass (used by the sensitivity Monte Carlo hot path)
- `ctx.shortest_path_cost(source, sink, *, mode, edge_select=ALL_MIN_COST, excluded_nodes, excluded_links)` - Shortest path cost
- `ctx.shortest_paths(source, sink, *, mode, edge_select, split_parallel_edges)` - Full Path objects

**Key Concepts:**

- **Mode.COMBINE:** Aggregate sources into one super-source, sinks into one super-sink; returns single total flow
- **Mode.PAIRWISE:** Compute flow for each (source_group, sink_group) pair independently
- **FlowPlacement.PROPORTIONAL (WCMP):** Split flow proportional to edge capacity
- **FlowPlacement.EQUAL_BALANCED (ECMP):** Equal split across parallel paths
- **shortest_path=True:** Restricts flow to lowest-cost paths only (IP/IGP routing semantics)
- **shortest_path=False:** Uses all paths progressively (TE/SDN semantics)
- **require_capacity=True:** Path selection considers available capacity; flow moves to next-cheapest paths as cheaper ones saturate (default)
- **require_capacity=False:** Path selection is cost-only; saturated paths are not bypassed (true IP/IGP semantics; pair with shortest_path=True for IP simulation)

### Efficient Repeated Analysis (Bound Context)

Bind source and sink groups once, then reuse the context across many calls:

```python
from ngraph import analyze, Mode

# Create bound context - graph built once with pseudo-nodes
ctx = analyze(network, source="^dc/", sink="^edge/", mode=Mode.COMBINE)

# Baseline capacity
baseline = ctx.max_flow()

# Test with different failures - only mask building per call
for failed_links in failure_scenarios:
    degraded = ctx.max_flow(excluded_links=failed_links)
    print(f"Capacity with {failed_links}: {degraded}")
```

**Benefits of Bound Context:**

- Graph infrastructure built once at context creation
- Each analysis call rebuilds only the node and edge masks — a full-length array fill (Theta(V) for nodes, Theta(E) for edges) plus O(|excluded| + |disabled|) updates — instead of rebuilding the Core graph
- Thread-safe: can run concurrent analysis calls with different exclusions

**Unbound vs. bound construction:** Unbound flow calls (`max_flow`, `max_flow_detailed`, `sensitivity`) construct a full temporary bound context per call, so repeated analysis should use a bound context. A plain unbound context builds its Core graph lazily on first use; bound contexts (and contexts with augmentations) build eagerly at creation.

### Shortest Paths

```python
from ngraph import analyze, Mode, EdgeSelect

# Get shortest path cost between groups
costs = analyze(network).shortest_path_cost(
    "^dc1/.*",
    "^dc2/.*",
    mode=Mode.PAIRWISE
)

# Get full path objects
paths = analyze(network).shortest_paths(
    "^A$",
    "^B$",
    mode=Mode.COMBINE,
    edge_select=EdgeSelect.ALL_MIN_COST
)

# K-shortest paths with constraints
k_paths = analyze(network).k_shortest_paths(
    "^A$",
    "^B$",
    max_k=5,
    mode=Mode.PAIRWISE,
    max_path_cost_factor=1.5  # Limit to 1.5x best path cost
)
```

**Key Functions:**

- `ctx.shortest_path_cost(source, sink, *, mode, edge_select=ALL_MIN_COST)` - Cost only, no path objects
- `ctx.shortest_paths(source, sink, *, mode, edge_select=ALL_MIN_COST, split_parallel_edges=False)` - Full Path objects
- `ctx.k_shortest_paths(source, sink, *, mode=PAIRWISE, max_k=3, max_path_cost, max_path_cost_factor, excluded_nodes, excluded_links)` - Multiple paths per pair

### Sensitivity Analysis

Identify critical edges and quantify their impact:

```python
from ngraph import analyze, Mode

# Get sensitivity map: which edges are critical and by how much
sensitivity = analyze(network).sensitivity(
    "^metro1/.*",
    "^metro5/.*",
    mode=Mode.COMBINE,
    shortest_path=False  # Full max-flow mode
)

for pair, edge_impacts in sensitivity.items():
    print(f"Critical edges for {pair}:")
    for edge_key, flow_reduction in edge_impacts.items():
        print(f"  {edge_key}: -{flow_reduction:.2f}")
```

## 5. Monte Carlo Analysis

Probabilistic failure analysis using FailureManager.

### FailureManager

**Purpose:** Execute Monte Carlo failure scenarios and aggregate results across multiple iterations.

```python
from ngraph import Network, Node, Link, FailureManager
from ngraph.model.failure.policy import FailurePolicy, FailureMode, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet

# Build a network with two disjoint A->C paths, so a single link failure
# degrades capacity rather than disconnecting the pair entirely.
network = Network()
for name in ["A", "B", "C", "D"]:
    network.add_node(Node(name=name))
network.add_link(Link("A", "B", capacity=100.0))
network.add_link(Link("B", "C", capacity=100.0))
network.add_link(Link("A", "D", capacity=60.0))
network.add_link(Link("D", "C", capacity=60.0))

# Define failure policy: randomly choose 1 link to fail
rule = FailureRule(scope="link", mode="choice", count=1)  # scope can be "node", "link", or "risk_group"
mode = FailureMode(weight=1.0, rules=[rule])
policy = FailurePolicy(modes=[mode])
policy_set = FailurePolicySet(policies={"single_link": policy})

# Create failure manager
fm = FailureManager(
    network=network,
    failure_policy_set=policy_set,
    policy_name="single_link"
)

# Run max-flow Monte Carlo analysis
results = fm.run_max_flow_monte_carlo(
    source="^A$",
    target="^C$",
    mode="combine",
    iterations=100,
    parallelism=1,
    seed=42  # For reproducibility
)

# Access results: one entry per unique failure pattern (iterations are
# deduplicated; occurrence_count gives how many iterations matched)
for iter_result in results["results"]:
    print(f"Flow: {iter_result.summary.total_placed:.1f} (x{iter_result.occurrence_count})")
```

**Key Methods:**

- `run_max_flow_monte_carlo(...)` - Max-flow capacity analysis under failures
- `run_demand_placement_monte_carlo(...)` - Traffic demand placement under failures
- `run_monte_carlo_analysis(analysis_func, ...)` - Generic Monte Carlo with custom function

## 6. Workflow Steps

Pre-built analysis steps for YAML-driven workflows.

### MaxFlow Step

```yaml
workflow:
  - type: MaxFlow
    name: "dc_to_edge_capacity"
    source: "^datacenter/.*"
    target: "^edge/.*"
    mode: "combine"
    failure_policy: "random_link_failures"
    iterations: 100
    parallelism: auto
    shortest_path: false
    require_capacity: true       # false for true IP/IGP semantics
    flow_placement: "PROPORTIONAL"
```

### TrafficMatrixPlacement Step

```yaml
workflow:
  - type: TrafficMatrixPlacement
    name: "tm_placement_analysis"
    demand_set: "peak_traffic"
    failure_policy: "dual_link_failures"
    iterations: 100
    parallelism: auto
```

### MaximumSupportedDemand Step

```yaml
workflow:
  - type: MaximumSupportedDemand
    name: "find_alpha_star"
    demand_set: "peak_traffic"
    alpha_start: 1.0
    growth_factor: 2.0
    resolution: 0.01
```

### NetworkStats Step

```yaml
workflow:
  - type: NetworkStats
    name: "baseline_stats"
    include_disabled: false
    excluded_nodes: ["n1"]
```

### CostPower Step

```yaml
workflow:
  - type: CostPower
    name: "cost_power_analysis"
    include_disabled: false
    aggregation_level: 2
```

## 7. Types Reference

### Enums

```python
from ngraph import Mode, FlowPlacement, EdgeSelect

# Mode - Source/sink group handling
Mode.COMBINE    # Aggregate all sources/sinks
Mode.PAIRWISE   # Each (src_group, sink_group) pair independently

# FlowPlacement - Flow distribution strategy
FlowPlacement.PROPORTIONAL   # WCMP: proportional to capacity
FlowPlacement.EQUAL_BALANCED # ECMP: equal split

# EdgeSelect - SPF edge selection
EdgeSelect.ALL_MIN_COST     # All equal-cost edges (ECMP)
EdgeSelect.SINGLE_MIN_COST  # Single lowest-cost edge
```

### Result Types

```python
from ngraph import MaxFlowResult, FlowEntry, FlowSummary, FlowIterationResult

# MaxFlowResult - Detailed max-flow result
result.total_flow        # Total flow placed
result.cost_distribution # Dict[cost, flow_volume]
result.min_cut           # Optional tuple of EdgeRef (edges forming a minimum cut)

# FlowEntry - Single flow entry
entry.source        # Source label
entry.destination   # Destination label
entry.demand        # Requested demand
entry.placed        # Actually placed
entry.dropped       # Unmet demand

# FlowSummary - Aggregated statistics
summary.total_demand    # Sum of all demands
summary.total_placed    # Sum of placed flows
summary.overall_ratio   # placed / demand

# FlowIterationResult - Full iteration result
iter_result.flows    # List[FlowEntry]
iter_result.summary  # FlowSummary
```

## 8. Complete Example

```python
from ngraph import Network, Node, Link, analyze, Mode

# Build network
network = Network()
for name in ["dc1", "dc2", "spine1", "spine2", "leaf1", "leaf2"]:
    network.add_node(Node(name))

# Add links with varying capacities
network.add_link(Link("dc1", "spine1", capacity=100.0, cost=1.0))
network.add_link(Link("dc1", "spine2", capacity=100.0, cost=1.0))
network.add_link(Link("dc2", "spine1", capacity=100.0, cost=1.0))
network.add_link(Link("dc2", "spine2", capacity=100.0, cost=1.0))
network.add_link(Link("spine1", "leaf1", capacity=50.0, cost=1.0))
network.add_link(Link("spine1", "leaf2", capacity=50.0, cost=1.0))
network.add_link(Link("spine2", "leaf1", capacity=50.0, cost=1.0))
network.add_link(Link("spine2", "leaf2", capacity=50.0, cost=1.0))

# One-off max flow analysis
flow = analyze(network).max_flow("^dc", "^leaf", mode=Mode.COMBINE)
print(f"DC to Leaf capacity: {list(flow.values())[0]:.1f}")

# Efficient repeated analysis with bound context
ctx = analyze(network, source="^dc", sink="^leaf", mode=Mode.COMBINE)

# Baseline
baseline = ctx.max_flow()

# Test spine failures
spine_links = [lid for lid, l in network.links.items() if "spine" in l.source]
for link_id in spine_links:
    degraded = ctx.max_flow(excluded_links={link_id})
    reduction = list(baseline.values())[0] - list(degraded.values())[0]
    print(f"If {link_id} fails: {reduction:.1f} capacity loss")

# Sensitivity analysis
sensitivity = ctx.sensitivity()
for pair, impacts in sensitivity.items():
    print(f"\nCritical edges for {pair}:")
    for edge, impact in sorted(impacts.items(), key=lambda x: -x[1])[:3]:
        print(f"  {edge}: {impact:.1f}")
```

## 9. Performance Notes

NetGraph uses a hybrid Python+C++ architecture:

- **High-level APIs** (Network, Scenario, Workflow) are pure Python
- **Core algorithms** (shortest paths, max-flow, K-shortest paths) execute in optimized C++ via NetGraph-Core
- **GIL released** during algorithm execution for parallel processing
- **Transparent integration**: You work with Python objects; Core acceleration is automatic

All public APIs accept and return Python types (Network, Node, Link, FlowSummary, etc.).
The C++ layer is an implementation detail you generally don't interact with directly.
