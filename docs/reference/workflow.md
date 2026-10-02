# Workflow Reference

Quick links:

- [Design](design.md) - architecture, model, algorithms, workflow
- [DSL Reference](dsl.md) - YAML syntax for scenario definition
- [CLI Reference](cli.md) - command-line tools for running scenarios
- [API Reference](api.md) - Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) - complete class and method documentation

A workflow is the ordered list of analysis steps a scenario runs. Each step computes one result (statistics, a Monte Carlo analysis, an export) and writes it under its step name in the results store.

```yaml
workflow:
  - type: NetworkStats
    name: network_statistics
  - type: MaximumSupportedDemand
    name: msd_baseline
    demand_set: baseline_traffic_matrix
  - type: TrafficMatrixPlacement
    name: tm_placement
    demand_set: baseline_traffic_matrix
    failure_policy: random_failures
    iterations: 1000
```

## Execution Model

- Steps run sequentially via `WorkflowStep.execute()`, which records timing and metadata and stores outputs under `{metadata, data}` for the step.
- Monte Carlo steps (`MaxFlow`, `TrafficMatrixPlacement`) execute iterations using the Failure Manager. Each iteration analyzes the network with exclusion sets applied to mask failed nodes/links without mutating the base network. Workers are controlled by `parallelism: auto|int`. For `MaxFlow`, `auto` is the CPU count. For `TrafficMatrixPlacement`, `auto` is 1 unless the demand set uses an LSP preset or the interpreter is free-threaded, because iterations for the other presets are Python-bound and threads only slow them down; an explicit integer is always honoured.
- Seeding: a scenario-level `seed` derives per-step seeds unless a step sets an explicit `seed`. Metadata includes `scenario_seed`, `step_seed`, and `seed_source`. `seed_source` reflects the seed the step actually uses: a step constructed without its own seed reports `seed_source: none` even when the scenario has a seed (YAML-loaded scenarios derive per-step seeds at parse time, so those report `scenario-derived`).

## Built-in Steps

### BuildGraph

Exports the network as node-link JSON for external tools. No other step depends on it.

```yaml
- type: BuildGraph
  name: build_graph
  add_reverse: true  # Add reverse edges for bidirectional connectivity (default: true)
```

Parameters:

- `add_reverse`: Add a reverse edge for each link. Default: `true`.

### NetworkStats

Node, link, capacity and degree statistics, optionally with nodes or links excluded.

```yaml
- type: NetworkStats
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
- type: MaxFlow
  name: capacity_analysis
  source: "^servers/.*"
  target: "^storage/.*"
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

Parameters:

- `source`, `target`: Node selectors, a string pattern or a selector object (see Node Selection below). Required.
- `mode`: `combine` or `pairwise`. Default: `combine`.
- `failure_policy`: Name of a policy in the `failures` section. Default: none (no failures).
- `iterations`: Number of failure iterations; the no-failure baseline is extra. Default: `1`.
- `parallelism`: Worker threads, an integer or `auto` (the CPU count). Default: `auto`.
- `shortest_path`: Restrict flow to the lowest-cost paths. Default: `false`.
- `require_capacity`: Path selection considers residual capacity; `false` gives cost-only IP/IGP routing. Default: `true`.
- `flow_placement`: `PROPORTIONAL` or `EQUAL_BALANCED`. Default: `PROPORTIONAL`.
- `store_failure_patterns`: Record the failure trace on each result. Default: `false`.
- `include_flow_details`: Emit `cost_distribution` per flow. Default: `false`.
- `include_min_cut`: Emit the min-cut edge list per flow. Default: `false`.

Outputs:

- metadata: iterations, parallelism, analysis_function, policy_name,
  execution_time, unique_patterns, occurrence_counts
- data.baseline and data.flow_results: see Results Export Shape below
- data.context: source, target, mode, shortest_path, require_capacity,
  flow_placement, include_flow_details, include_min_cut
- each flow entry's `data` holds `edges`/`edges_kind: min_cut` with
  `include_min_cut`

### TrafficMatrixPlacement

Monte Carlo placement of a named demand set with optional alpha scaling. Baseline (no failures) is always run first as a separate reference.

```yaml
- type: TrafficMatrixPlacement
  name: tm_placement
  demand_set: default
  failure_policy: random_failures        # Optional: policy name in failures section
  iterations: 100                # Number of failure iterations
  parallelism: auto              # 1 for hop-by-hop/TE_WCMP presets, CPU count with LSP presets
  include_flow_details: true     # cost_distribution per flow
  include_used_edges: false      # include per-demand used edge lists
  store_failure_patterns: false
  # Alpha scaling – explicit (default 1.0) or from another step, not both
  alpha: 1.0
  # alpha_from_step: msd_default
  # alpha_from_field: data.alpha_star
```

Parameters:

- `demand_set`: Name of the demand set to place. Required.
- `failure_policy`: Name of a policy in the `failures` section. Default: none (no failures).
- `iterations`: Number of failure iterations (>= 0). Default: `1`.
- `parallelism`: Worker threads, an integer or `auto`. Default: `auto` (see Execution Model).
- `store_failure_patterns`: Record the failure trace on each result. Default: `false`.
- `include_flow_details`: Emit `cost_distribution` per flow. Default: `false`.
- `include_used_edges`: Emit the used edge list per demand. Default: `false`.
- `alpha`: Demand volume multiplier, must be > 0. Default: `1.0`. Cannot be combined with `alpha_from_step`.
- `alpha_from_step`: Name of an earlier step whose result supplies alpha.
- `alpha_from_field`: Dotted path of the alpha value in that step's results. Default: `data.alpha_star`.

Outputs:

- metadata: iterations, parallelism, analysis_function, policy_name,
  execution_time, unique_patterns, occurrence_counts
- data.baseline and data.flow_results: see Results Export Shape below
- data.context: demand_set, include_flow_details,
  include_used_edges, base_demands, alpha, alpha_source
- each flow entry's `data` holds `edges`/`edges_kind: used` with
  `include_used_edges`, and `dropped_edges` (volume lost per link) for
  `SHORTEST_PATHS_ECMP_LOSSY` demands with `include_flow_details`

### MaximumSupportedDemand

Search for the maximum uniform traffic multiplier `alpha_star` that is fully placeable. An alpha is feasible when every demand is placed to within the core engine's resolution of 1/4096 and no demand places nothing.

```yaml
- type: MaximumSupportedDemand
  name: msd_default
  demand_set: default
  alpha_start: 1.0               # Starting alpha value for search
  growth_factor: 2.0             # Growth factor for bracketing (must be > 1.0)
  alpha_min: 0.000001            # Minimum alpha bound (default: 1e-6)
  alpha_max: 1000000000.0        # Maximum alpha bound (default: 1e9)
  resolution: 0.01               # Convergence resolution for bisection
  max_bracket_iters: 32          # Maximum bracketing iterations
  max_bisect_iters: 32           # Maximum bisection iterations
```

Parameters:

- `demand_set`: Name of the demand set to analyze (default: "default").
- `alpha_start`: Initial alpha value to probe. Default: `1.0`.
- `growth_factor`: Multiplier for bracketing phase (must be > 1.0). Default: `2.0`.
- `alpha_min`: Minimum alpha bound for search. Default: `1e-6`.
- `alpha_max`: Maximum alpha bound for search. Default: `1e9`.
- `resolution`: Convergence threshold for bisection (must be positive). Default: `0.01`.
- `max_bracket_iters`: Maximum iterations for bracketing phase. Default: `32`.
- `max_bisect_iters`: Maximum iterations for bisection phase. Default: `32`.

Outputs:

- data.alpha_star: maximum uniform scaling factor
- data.context: search parameters
- data.base_demands: serialized base demands prior to scaling
- data.probes: bracket/bisect evaluations with feasibility and placement ratios

### CostPower

Aggregate platform and optics capex/power by hierarchy level (split by `/`).

```yaml
- type: CostPower
  name: cost_power
  include_disabled: false
  aggregation_level: 2
```

Parameters:

- `include_disabled`: If `true`, include disabled nodes and links. Default: `false`.
- `aggregation_level`: Deepest hierarchy level to report; levels `0..N` are produced and `0` is the root. Must be >= 0. Default: `2`.

Outputs:

- data.context: include_disabled, aggregation_level
- data.levels: mapping level (`"0"`..`"N"`) -> list of {path, platform_capex, platform_power_watts,
  optics_capex, optics_power_watts, capex_total, power_total_watts}

CostPower performs no hardware capacity/ports validation and completes even on networks that strict hardware validation would reject; use `ngraph inspect` for hardware validation.

## Node Selection

`MaxFlow` `source` and `target` accept a string pattern or a selector object; the syntax is the one described in the [DSL Reference](dsl.md#node-selection).

- A string is a regular expression matched against node names from the start (Python `re.match()`), so `"spine-1"` also matches `"spine-10"`; anchor with `^...$` for an exact match.
- Capturing groups define the groups: each distinct captured value (several captures joined with `|`) becomes one group, and a pattern without captures forms a single group labeled by the pattern.
- A selector object combines `path` (a regex), `group_by` (an attribute whose values become the groups) and `match` (attribute conditions).

```yaml
source: "(dc[1-3])/servers/.*"     # one group per captured value: dc1, dc2, dc3
target:
  path: "^pod[1-3]/.*"
  group_by: "role"
  match:
    conditions:
      - {attr: "tier", op: "==", value: "leaf"}
```

`mode: combine` aggregates all source matches into one virtual source and all target matches into one virtual target and produces one flow value; `mode: pairwise` computes a flow for each (source group, target group) pair.

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
      "step_seed": 1903777304,
      "seed_source": "scenario-derived"
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
        "context": { "demand_set": "baseline_traffic_matrix" }
      }
    },
    "tm_placement": {
      "metadata": { "iterations": 1000, "parallelism": 8 },
      "data": {
        "baseline": {
          "failure_id": "",
          "failure_state": { "excluded_nodes": [], "excluded_links": [] },
          "flows": [],
          "summary": { "total_demand": 0.0, "total_placed": 0.0, "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 0 }
        },
        "flow_results": [],
        "context": { "demand_set": "baseline_traffic_matrix" }
      }
    }
  },
  "scenario": { "seed": 42, "failures": { }, "demands": { } }
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
    "summary": { "total_demand": 10.0, "total_placed": 10.0, "overall_ratio": 1.0, "dropped_flows": 0, "num_flows": 2 },
    "data": {}
  },
  "flow_results": [
    {
      "failure_id": "d0eea3f4d06413a2",
      "failure_state": { "excluded_nodes": ["nodeA"], "excluded_links": [] },
      "failure_trace": { "mode_index": 0, "selections": [...], ... },
      "occurrence_count": 5,
      "flows": [ ... ],
      "summary": { "total_demand": 10.0, "total_placed": 8.0, "overall_ratio": 0.8, "dropped_flows": 1, "num_flows": 2 },
      "data": {}
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
- `data` on each entry is reserved for per-iteration extras; the built-in analyses leave it empty.
- Effective `parallelism` and other execution fields are recorded in step metadata.
