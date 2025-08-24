# Workflow Reference

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

This document describes NetGraph workflows – analysis execution pipelines that perform capacity analysis, demand placement, and statistics computation.

## Overview

Workflows are lists of analysis steps executed sequentially on network scenarios. Each step performs a specific operation like computing statistics, running Monte Carlo failure simulations, or exporting graph data.

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

**Network State Management:**

- **Scenario state**: Permanent network configuration (e.g., `disabled: true` nodes/links)
- **Analysis state**: Temporary failure exclusions during Monte Carlo simulation

**NetworkView**: Provides isolated analysis contexts without modifying the base network, enabling concurrent failure scenario analysis.

## Core Workflow Steps

### BuildGraph

Exports the network graph to JSON (node-link format) for external analysis. Not required for other steps.

```yaml
- step_type: BuildGraph
  name: build_graph
```

### NetworkStats

Computes network statistics (capacity, degree metrics).

```yaml
- step_type: NetworkStats
  name: baseline_stats
```

### MaxFlow

Monte Carlo flow capacity analysis with optional failure simulation.

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
  include_flow_details: false   # cost_distribution
  include_min_cut: false        # min-cut edges list
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
  # Alpha scaling – explicit or from another step
  alpha: 1.0
  # alpha_from_step: msd_default
  # alpha_from_field: data.alpha_star
```

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

## Node Selection Mechanism

Source and sink nodes are selected using regex patterns matched against full node names with Python's `re.match()` (anchored at start).

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
failure_policy: policy_name      # From failure_policy_set (default: null)
baseline: true                   # Include baseline (default: false)
parallelism: auto                # Worker processes (default: auto)
shortest_path: false             # Limit to shortest paths (default: false)
flow_placement: PROPORTIONAL     # PROPORTIONAL | EQUAL_BALANCED
include_flow_details: false      # Emit cost_distribution per flow
include_min_cut: false           # Emit min-cut edge list per flow
```

## Results Export Shape

Exported results have a fixed top-level structure:

```json
{
  "workflow": { "<step>": { "step_type": "...", "execution_order": 0, "step_name": "..." } },
  "steps": {
    "network_statistics": { "metadata": {}, "data": { "node_count": 42, "link_count": 84 } },
    "msd_baseline": { "metadata": {}, "data": { "alpha_star": 1.37, "context": {"matrix_name": "baseline_traffic_matrix"} } },
    "tm_placement": { "metadata": { "iterations": 1000 }, "data": { "flow_results": [ { "flows": [], "summary": {} } ], "context": {"matrix_name": "baseline_traffic_matrix"} } }
  },
  "scenario": { "seed": 42, "failure_policy_set": { }, "traffic_matrices": { } }
}
```

- `MaxFlow` and `TrafficMatrixPlacement` store `data.flow_results` as a list of per-iteration results:

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
    {
      "failure_id": "d0eea3f4d06413a2",
      "failure_state": null,
      "flows": [],
      "summary": {
        "total_demand": 0.0, "total_placed": 0.0,
        "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 0
      },
      "data": { }
    }
  ],
  "context": { ... }
}
```
