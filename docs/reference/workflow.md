# Workflow Reference

Quick links:

- [DSL Reference](dsl.md) — YAML syntax for scenario definition
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

This document describes NetGraph workflows - analysis execution pipelines that perform capacity analysis, failure simulation, and network statistics computation.

## Overview

Workflows are lists of analysis steps executed sequentially on network scenarios. Each step performs a specific operation like computing statistics, running Monte Carlo failure simulations, or exporting graph data.

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    source_path: "^datacenter/.*"
    sink_path: "^edge/.*"
    iterations: 1000
```

## Execution Model

**Network State Management:**

- **Scenario state**: Permanent network configuration (e.g., `disabled: true` nodes/links)
- **Analysis state**: Temporary failure exclusions during Monte Carlo simulation

**NetworkView**: Provides isolated analysis contexts without modifying the base network, enabling concurrent failure scenario analysis.

## Core Workflow Steps

### BuildGraph

Exports the network graph to a JSON file for external analysis. Not required for workflow analysis steps, which build graphs internally as needed.

```yaml
- step_type: BuildGraph
```

### NetworkStats

Computes network statistics (capacity, degree metrics, connectivity).

```yaml
- step_type: NetworkStats
  name: "baseline_stats"  # Optional name
```

### CapacityEnvelopeAnalysis

Monte Carlo capacity analysis with failure simulation. The primary analysis step for capacity planning and resilience testing.

```yaml
- step_type: CapacityEnvelopeAnalysis
  name: "capacity_analysis"
  source_path: "^servers/.*"
  sink_path: "^storage/.*"
  mode: "combine"
  failure_policy: "random_failures"
  iterations: 1000
  parallelism: 4
  baseline: true
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

## CapacityEnvelopeAnalysis Parameters

### Required Parameters

- `source_path`: Regex pattern for source node selection
- `sink_path`: Regex pattern for sink node selection

### Analysis Configuration

```yaml
mode: "combine"                    # "combine" or "pairwise" (default: "combine")
iterations: 1000                   # Monte Carlo trials (default: 1)
failure_policy: "policy_name"      # From failure_policy_set (default: null - no failures)
baseline: true                     # Include no-failure baseline (default: false)
```

### Performance Tuning

```yaml
parallelism: 8                     # Worker processes (default: 1)
seed: 42                          # Reproducible results
shortest_path: false              # Shortest paths only (default: false)
flow_placement: "PROPORTIONAL"    # "PROPORTIONAL" or "EQUAL_BALANCED"
```

### Output Control

```yaml
store_failure_patterns: false     # Retain failure pattern data
include_flow_summary: false       # Detailed flow analytics
```

## Common Workflow Patterns

### Single Deterministic Analysis

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    source_path: "^servers/.*"
    sink_path: "^storage/.*"
```

### Monte Carlo Failure Analysis

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    source_path: "^pod1/.*"
    sink_path: "^pod2/.*"
    failure_policy: "random_link_failures"
    iterations: 10000
    parallelism: 8
    baseline: true
    seed: 42
```

### Comparative Analysis

```yaml
workflow:
  # Baseline capacity
  - step_type: CapacityEnvelopeAnalysis
    name: "baseline"
    source_path: "^dc1/.*"
    sink_path: "^dc2/.*"
    iterations: 1

  # Single failure impact
  - step_type: CapacityEnvelopeAnalysis
    name: "single_failure"
    source_path: "^dc1/.*"
    sink_path: "^dc2/.*"
    failure_policy: "single_link_failure"
    iterations: 1000
    baseline: true
```

## Report Generation

Generate analysis reports using the CLI:

```bash
# Jupyter notebook (defaults to <results_name>.ipynb)
python -m ngraph report baseline_scenario.json

# HTML report (defaults to <results_name>.html when --html is used)
python -m ngraph report baseline_scenario.json --html
```

See [CLI Reference](cli.md#report) for complete options.

## Best Practices

### Performance

- Use `parallelism` for Monte Carlo analysis (typically CPU core count)
- Set `store_failure_patterns: false` for large-scale analysis
- Start with fewer iterations for initial validation

### Analysis Strategy

- Begin with single deterministic analysis before Monte Carlo
- Use `combine` mode for aggregate analysis, `pairwise` for detailed flows
- Include `baseline: true` for failure scenario comparison
- Use descriptive `name` parameters for each step

### Node Selection

- Test regex patterns against actual node names before large runs
- Use capturing groups to analyze multiple node groups simultaneously
- Anchor patterns with `^` and `$` for precise matching
- Leverage hierarchical naming conventions for effective grouping

### Integration

- Reference failure policies from `failure_policy_set` section
- Ensure failure policies exist before workflow execution
- Include `BuildGraph` only when graph export to JSON is needed for external analysis
