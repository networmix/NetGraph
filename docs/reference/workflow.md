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
    failure_policy: weighted_modes
    iterations: 1000
    baseline: true
```

## Execution Model

- Steps run sequentially via `WorkflowStep.execute()`, which records timing and metadata and stores outputs under `{metadata, data}` for the step.
- Monte Carlo steps (`MaxFlow`, `TrafficMatrixPlacement`) execute iterations using the Failure Manager. Each iteration analyzes a `NetworkView` that masks failed nodes/links without mutating the base network. Workers are controlled by `parallelism: auto|int`.
- Seeding: a scenario-level `seed` derives per-step seeds unless a step sets an explicit `seed`. Metadata includes `scenario_seed`, `step_seed`, `seed_source`, and `active_seed`.

## Core Workflow Steps

### BuildGraph

Export the network graph to node-link JSON for external analysis. Optional for other steps.

```yaml
- step_type: BuildGraph
  name: build_graph
```

### NetworkStats

Compute node, link, and degree metrics. Supports temporary exclusions.

```yaml
- step_type: NetworkStats
  name: baseline_stats
```

### MaxFlow

Monte Carlo maximum flow analysis between node groups.

```yaml
- step_type: MaxFlow
  name: capacity_analysis
  source_path: "^servers/.*"
  sink_path: "^storage/.*"
  mode: "combine"              # combine | pairwise
  failure_policy: random_failures
  iterations: 1000
  parallelism: auto             # or an integer
  baseline: true
  shortest_path: false
  flow_placement: PROPORTIONAL  # or EQUAL_BALANCED
  store_failure_patterns: false
  include_flow_details: false   # cost_distribution per flow
  include_min_cut: false        # per-flow min-cut edge list
```

### TrafficMatrixPlacement

Monte Carlo placement of a named traffic matrix with optional alpha scaling.

```yaml
- step_type: TrafficMatrixPlacement
  name: tm_placement
  matrix_name: default
  iterations: 100
  parallelism: auto
  baseline: false
  include_flow_details: true      # cost_distribution per flow
  include_used_edges: false       # include per-demand used edge lists
  store_failure_patterns: false
  # Alpha scaling – explicit or from another step
  alpha: 1.0
  # alpha_from_step: msd_default
  # alpha_from_field: data.alpha_star
```

Outputs:

- metadata: iterations, parallelism, baseline, analysis_function, policy_name,
  execution_time, unique_patterns
- data.context: matrix_name, placement_rounds, include_flow_details,
  include_used_edges, base_demands, alpha, alpha_source

### MaximumSupportedDemand

Search for the maximum uniform traffic multiplier `alpha_star` that is fully placeable.

```yaml
- step_type: MaximumSupportedDemand
  name: msd_default
  matrix_name: default
  acceptance_rule: hard
  alpha_start: 1.0
  growth_factor: 2.0
  resolution: 0.01
  max_bracket_iters: 32
  max_bisect_iters: 32
  seeds_per_alpha: 1
  placement_rounds: auto
```

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

Select nodes by regex on `node.name` (anchored at start via Python `re.match`) or by attribute directive `attr:<name>` which groups nodes by `node.attrs[<name>]`.

### Basic Pattern Matching

```yaml
# Exact match
source_path: "spine-1"

# Prefix match
source_path: "datacenter/servers/"

# Pattern match
source_path: "^pod[1-3]/leaf/.*$"
```

### Capturing Groups for Node Grouping

**No Capturing Groups**: All matching nodes form one group labeled by the pattern.

```yaml
source_path: "edge/.*"
# Creates one group: "edge/.*" containing all matching nodes
```

**Single Capturing Group**: Each unique captured value creates a separate group.

```yaml
source_path: "(dc[1-3])/servers/.*"
# Creates groups: "dc1", "dc2", "dc3"
# Each group contains servers from that datacenter
```

**Multiple Capturing Groups**: Group labels join captured values with `|`.

```yaml
source_path: "(dc[1-3])/(spine|leaf)/switch-(\d+)"
# Creates groups: "dc1|spine|1", "dc1|leaf|2", "dc2|spine|1", etc.
```

### Attribute-based Grouping

```yaml
# Group by node attribute value (e.g., node.attrs["dc"]) — groups labeled by attribute value
source_path: "attr:dc"
```

### Flow Analysis Modes

**`combine` Mode**: Aggregates all source matches into one virtual source, all sink matches into one virtual sink. Produces single flow value.

**`pairwise` Mode**: Computes flow between each source group and sink group pair. Produces flow matrix keyed by `(source_group, sink_group)`.

## MaxFlow Parameters

### Required Parameters

- `source_path`: Regex pattern for source node selection
- `sink_path`: Regex pattern for sink node selection

### Analysis Configuration

```yaml
mode: combine                    # combine | pairwise (default: combine)
iterations: 1000                 # Monte Carlo trials (default: 1)
failure_policy: policy_name      # Name in failure_policy_set (default: null)
baseline: true                   # Include baseline iteration first (default: false)
parallelism: auto                # Worker processes (default: auto)
shortest_path: false             # Restrict to shortest paths (default: false)
flow_placement: PROPORTIONAL     # PROPORTIONAL | EQUAL_BALANCED
store_failure_patterns: false    # Store failure patterns in results
include_flow_details: false      # Emit cost_distribution per flow
include_min_cut: false           # Emit min-cut edge list per flow
```

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

- `MaxFlow` and `TrafficMatrixPlacement` write per-iteration entries under `data.flow_results`:

```json
{
  "flow_results": [
    {
      "failure_id": "baseline",
      "failure_state": null,
      "flows": [
        {
          "source": "A", "destination": "B", "priority": 0,
          "demand": 10.0, "placed": 10.0, "dropped": 0.0,
          "cost_distribution": { "2": 6.0, "4": 4.0 },
          "data": { "edges": ["(u,v,k)"] }
        }
      ],
      "summary": {
        "total_demand": 10.0, "total_placed": 10.0,
        "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 1
      },
      "data": { }
    },
    { "failure_id": "d0eea3f4d06413a2", "failure_state": null, "flows": [],
      "summary": { "total_demand": 0.0, "total_placed": 0.0, "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 0 },
      "data": {} }
  ],
  "context": { ... }
}
```

Notes:

- Baseline: when `baseline: true`, the first entry has `failure_id: "baseline"`.
- `failure_state` may be `null` or an object with `excluded_nodes` and `excluded_links` lists.
- Per-iteration `data` can include instrumentation (e.g., `iteration_metrics`).
- Per-flow `data` can include instrumentation (e.g., `policy_metrics`).
- `cost_distribution` uses string keys for JSON stability; values are numeric.
- Effective `parallelism` and other execution fields are recorded in step metadata.
