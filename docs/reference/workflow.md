# Workflow Reference

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

This document describes NetGraph workflows – analysis execution pipelines that perform capacity analysis, demand placement, and statistics computation.

## Overview

Workflows are ordered steps executed on a scenario. Each step computes a result (e.g., stats, Monte Carlo analysis, export) and writes it under its step name in the results store.

```yaml
workflow:
  - step_type: NetworkStats
    name: network_statistics
  - step_type: MaximumSupportedDemand
    name: msd_baseline
    matrix_name: baseline_traffic_matrix
  - step_type: TrafficMatrixPlacement
    name: tm_placement
    matrix_name: baseline_traffic_matrix
    failure_policy: random_failures
    iterations: 1000
```

## Execution Model

- Steps run sequentially via `WorkflowStep.execute()`, which records timing and metadata and stores outputs under `{metadata, data}` for the step.
- Monte Carlo steps (`MaxFlow`, `TrafficMatrixPlacement`) execute iterations using the Failure Manager. Each iteration analyzes the network with exclusion sets applied to mask failed nodes/links without mutating the base network. Workers are controlled by `parallelism: auto|int`.
- Seeding: a scenario-level `seed` derives per-step seeds unless a step sets an explicit `seed`. Metadata includes `scenario_seed`, `step_seed`, `seed_source`, and `active_seed`.

## Core Workflow Steps

### BuildGraph

Validates network topology and exports node-link JSON for external analysis. Optional for other workflow steps.

```yaml
- step_type: BuildGraph
  name: build_graph
  add_reverse: true  # Add reverse edges for bidirectional connectivity (default: true)
```

Parameters:

- `add_reverse`: If `true`, adds reverse edges for each link to enable bidirectional connectivity. Set to `false` for directed-only graphs. Default: `true`.

### NetworkStats

Compute node, link, and degree metrics. Supports temporary exclusions without modifying the base network.

```yaml
- step_type: NetworkStats
  name: baseline_stats
  include_disabled: false           # Include disabled nodes/links in stats
  excluded_nodes: []                # Optional: Temporary node exclusions
  excluded_links: []                # Optional: Temporary link exclusions
```

Parameters:

- `include_disabled`: If `true`, include disabled nodes and links in statistics. Default: `false`.
- `excluded_nodes`: Optional list of node names to exclude temporarily (does not modify network).
- `excluded_links`: Optional list of link IDs to exclude temporarily (does not modify network).

### MaxFlow

Monte Carlo maximum flow analysis between node groups. Baseline (no failures) is always run first as a separate reference.

```yaml
- step_type: MaxFlow
  name: capacity_analysis
  source: "^servers/.*"
  sink: "^storage/.*"
  mode: "combine"              # combine | pairwise
  failure_policy: random_failures
  iterations: 1000             # Number of failure iterations
  parallelism: auto             # or an integer
  shortest_path: false
  require_capacity: true        # false for true IP/IGP semantics
  flow_placement: PROPORTIONAL  # or EQUAL_BALANCED
  store_failure_patterns: false
  include_flow_details: false   # cost_distribution per flow
  include_min_cut: false        # per-flow min-cut edge list
```

### TrafficMatrixPlacement

Monte Carlo placement of a named traffic matrix with optional alpha scaling. Baseline (no failures) is always run first as a separate reference.

```yaml
- step_type: TrafficMatrixPlacement
  name: tm_placement
  matrix_name: default
  failure_policy: random_failures  # Optional: policy name in failure_policy_set
  iterations: 100                  # Number of failure iterations
  parallelism: auto
  placement_rounds: auto           # or an integer
  include_flow_details: true       # cost_distribution per flow
  include_used_edges: false        # include per-demand used edge lists
  store_failure_patterns: false
  # Alpha scaling – explicit or from another step
  alpha: 1.0
  # alpha_from_step: msd_default
  # alpha_from_field: data.alpha_star
```

Outputs:

- metadata: iterations, parallelism, analysis_function, policy_name,
  execution_time, unique_patterns
- data.context: matrix_name, placement_rounds, include_flow_details,
  include_used_edges, base_demands, alpha, alpha_source

### MaximumSupportedDemand

Search for the maximum uniform traffic multiplier `alpha_star` that is fully placeable.

```yaml
- step_type: MaximumSupportedDemand
  name: msd_default
  matrix_name: default
  acceptance_rule: hard          # Currently only "hard" is supported
  alpha_start: 1.0               # Starting alpha value for search
  growth_factor: 2.0             # Growth factor for bracketing (must be > 1.0)
  alpha_min: 0.000001            # Minimum alpha bound (default: 1e-6)
  alpha_max: 1000000000.0        # Maximum alpha bound (default: 1e9)
  resolution: 0.01               # Convergence resolution for bisection
  max_bracket_iters: 32          # Maximum bracketing iterations
  max_bisect_iters: 32           # Maximum bisection iterations
  seeds_per_alpha: 1             # Number of seeds to test per alpha (majority vote)
  placement_rounds: auto         # Placement optimization rounds
```

Parameters:

- `matrix_name`: Name of the traffic matrix to analyze (default: "default").
- `acceptance_rule`: Acceptance rule for feasibility (currently only "hard" is supported).
- `alpha_start`: Initial alpha value to probe.
- `growth_factor`: Multiplier for bracketing phase (must be > 1.0).
- `alpha_min`: Minimum alpha bound for search.
- `alpha_max`: Maximum alpha bound for search.
- `resolution`: Convergence threshold for bisection.
- `max_bracket_iters`: Maximum iterations for bracketing phase.
- `max_bisect_iters`: Maximum iterations for bisection phase.
- `seeds_per_alpha`: Number of random seeds to test per alpha (uses majority vote).
- `placement_rounds`: Number of placement optimization rounds (`int` or `"auto"`).

Outputs:

- data.alpha_star: maximum uniform scaling factor
- data.context: search parameters
- data.base_demands: serialized base demands prior to scaling
- data.probes: bracket/bisect evaluations with feasibility and min ratios

### CostPower

Aggregate platform and optics capex/power by hierarchy level (split by `/`).

```yaml
- step_type: CostPower
  name: cost_power
  include_disabled: false
  aggregation_level: 2
```

Outputs:

- data.context: include_disabled, aggregation_level
- data.levels: mapping level->list of {path, platform_capex, platform_power_watts,
  optics_capex, optics_power_watts, capex_total, power_total_watts}

## Node Selection Mechanism

Workflow steps use a unified selector system for node selection. Selectors can be specified as string patterns or selector objects.

### String Pattern Matching

```yaml
# Exact match
source: "spine-1"

# Prefix match
source: "datacenter/servers/"

# Pattern match
source: "^pod[1-3]/leaf/.*$"
```

### Selector Objects

```yaml
# Attribute-based grouping
source:
  group_by: "dc"

# Combined path and grouping
source:
  path: "^datacenter/.*"
  group_by: "role"

# With attribute filtering
source:
  path: "^pod[1-3]/.*"
  match:
    conditions:
      - attr: "tier"
        operator: "=="
        value: "leaf"
```

### Capturing Groups for Node Grouping

**No Capturing Groups**: All matching nodes form one group labeled by the pattern.

```yaml
source: "edge/.*"
# Creates one group: "edge/.*" containing all matching nodes
```

**Single Capturing Group**: Each unique captured value creates a separate group.

```yaml
source: "(dc[1-3])/servers/.*"
# Creates groups: "dc1", "dc2", "dc3"
# Each group contains servers from that datacenter
```

**Multiple Capturing Groups**: Group labels join captured values with `|`.

```yaml
source: "(dc[1-3])/(spine|leaf)/switch-(\d+)"
# Creates groups: "dc1|spine|1", "dc1|leaf|2", "dc2|spine|1", etc.
```

### Attribute-based Grouping

```yaml
# Group by node attribute value (e.g., node.attrs["dc"])
source:
  group_by: "dc"
```

### Flow Analysis Modes

**`combine` Mode**: Aggregates all source matches into one virtual source, all sink matches into one virtual sink. Produces single flow value.

**`pairwise` Mode**: Computes flow between each source group and sink group pair. Produces flow matrix keyed by `(source_group, sink_group)`.

## MaxFlow Parameters

### Required Parameters

- `source`: Node selector for source nodes (string pattern or selector object)
- `sink`: Node selector for sink nodes (string pattern or selector object)

### Analysis Configuration

```yaml
mode: combine                    # combine | pairwise (default: combine)
iterations: 1000                 # Failure iterations to run (default: 1)
failure_policy: policy_name      # Name in failure_policy_set (default: null)
parallelism: auto                # Worker processes (default: auto)
shortest_path: false             # Restrict to shortest paths (default: false)
require_capacity: true           # Path selection considers capacity (default: true)
                                 # Set false for true IP/IGP semantics (cost-only routing)
flow_placement: PROPORTIONAL     # PROPORTIONAL | EQUAL_BALANCED
store_failure_patterns: false    # Store failure patterns in results
include_flow_details: false      # Emit cost_distribution per flow
include_min_cut: false           # Emit min-cut edge list per flow
```

Note: Baseline (no failures) is always run first as a separate reference. The `iterations` parameter specifies the number of failure scenarios to run.

## Results Export Shape

Exported results have a fixed top-level structure. Keys under `workflow` and `steps` are step names.

```json
{
  "workflow": {
    "network_statistics": {
      "step_type": "NetworkStats",
      "step_name": "network_statistics",
      "execution_order": 0,
      "scenario_seed": 42,
      "step_seed": 42,
      "seed_source": "scenario-derived",
      "active_seed": 42
    }
  },
  "steps": {
    "network_statistics": {
      "metadata": { "duration_sec": 0.012 },
      "data": { "node_count": 42, "link_count": 84 }
    },
    "msd_baseline": {
      "metadata": { "duration_sec": 1.234 },
      "data": {
        "alpha_star": 1.37,
        "context": { "matrix_name": "baseline_traffic_matrix" }
      }
    },
    "tm_placement": {
      "metadata": { "iterations": 1000, "parallelism": 8 },
      "data": {
        "flow_results": [
          {
            "failure_id": "baseline",
            "failure_state": null,
            "flows": [],
            "summary": { "total_demand": 0.0, "total_placed": 0.0, "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 0 },
            "data": {}
          }
        ],
        "context": { "matrix_name": "baseline_traffic_matrix" }
      }
    }
  },
  "scenario": { "seed": 42, "failure_policy_set": { }, "traffic_matrices": { } }
}
```

- `MaxFlow` and `TrafficMatrixPlacement` write results with baseline separate from failure iterations:

```json
{
  "baseline": {
    "failure_id": "",
    "failure_state": { "excluded_nodes": [], "excluded_links": [] },
    "failure_trace": null,
    "occurrence_count": 1,
    "flows": [ ... ],
    "summary": { "total_demand": 10.0, "total_placed": 10.0, "overall_ratio": 1.0 }
  },
  "flow_results": [
    {
      "failure_id": "d0eea3f4d06413a2",
      "failure_state": { "excluded_nodes": ["nodeA"], "excluded_links": [] },
      "failure_trace": { "mode_index": 0, "selections": [...], ... },
      "occurrence_count": 5,
      "flows": [ ... ],
      "summary": { "total_demand": 10.0, "total_placed": 8.0, "overall_ratio": 0.8 }
    }
  ],
  "context": { ... }
}
```

Notes:

- Baseline is always returned separately in the `baseline` field.
- `flow_results` contains K unique failure patterns (deduplicated), not N iterations.
- `occurrence_count` indicates how many iterations produced each unique failure pattern.
- `failure_id` is a hash of exclusions (empty string for no exclusions).
- `failure_trace` contains policy selection details when `store_failure_patterns: true`.
- `failure_state` contains `excluded_nodes` and `excluded_links` lists.
- `cost_distribution` uses string keys for JSON stability; values are numeric.
- Effective `parallelism` and other execution fields are recorded in step metadata.
