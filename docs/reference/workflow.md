# Workflow Steps

`Scenario.from_yaml(text)` parses an ordered workflow. Python callers execute `run(prepare(scenario))`; the returned `RunResult.steps` tuple holds each step's name, type, execution order, where its seed came from, normalized question and typed result. Duplicate names refuse before execution.

An unnamed YAML step receives `<type>_<declaration index>`. A step seed is explicit or derived from the scenario seed and effective step name ([Seeds](dsl.md#seeds)). Results are returned only after the complete workflow succeeds; `ngraph run --keys` exports selected steps after the whole workflow runs ([Filtering Results by Step Names](cli.md#filtering-results-by-step-names)). The domain steps are separate from the analyses: `BuildGraph` provides physical NetworkX node-link data, `NetworkStats` describes topology, and `CostPower` (with the `NetworkExplorer`) presents hardware metrics. Built-in steps are immutable records ([Records and editing](api.md#records-and-editing)); custom steps and result exporters: [Custom steps and exporters](api.md#custom-steps-and-exporters).

## Keys common to analysis steps

| Key | Steps | Default | Meaning |
|-----|-------|---------|---------|
| `failure_policy` | MaxFlow, TrafficMatrixPlacement | none | A policy name from `failures`; each distinct drawn failure set is one case ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states)) |
| `iterations` | MaxFlow, TrafficMatrixPlacement | 1 | The number of failure draws |
| `failure_trace` | MaxFlow, TrafficMatrixPlacement | `false` | Record the first draw that produced each failure pattern |
| `workers` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | `auto` | `auto` or a positive number of worker threads |
| `seed` | every step | derived | The step's seed ([Seeds](dsl.md#seeds)) |
| `outputs` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis, MaximumSupportedDemand | all off | Optional outputs ([Output selection](#output-selection)) |

Capacity and traffic-matrix placement resolve `workers: auto` to the CPU count; explicit positive worker counts override it, and results are the same for any number of workers. MaximumSupportedDemand (MSD) searches for the largest tested feasible alpha and runs serially ([Maximum supported demand](../concepts.md#maximum-supported-demand)).

## BuildGraph

```yaml
workflow:
  - type: BuildGraph
    name: topology
    add_reverse: true
```

Returns `BuildGraphResult` with node and edge counts (`edge_count` is two per link with reverse edges) and physical NetworkX node-link JSON. Reverse export edges are enabled by default. This operation exports the domain network, including disabled entities and their flags.

## NetworkStats

```yaml
workflow:
  - type: NetworkStats
    name: stats
    include_disabled: false
    excluded_nodes: []
    excluded_links: []
```

Returns physical node/link counts and capacity, cost and degree statistics. The question records these effective filters. An excluded node or link name that the network does not have is refused at preparation.

## CostPower

Each level groups the nodes by the first parts of their `/`-separated names. A level deeper than the deepest node name repeats the rows of that deepest level.

```yaml
workflow:
  - type: CostPower
    name: hardware
    include_disabled: false
    aggregation_level: 2
```

Returns hardware rows grouped by hierarchy level, with platform and link-end optics capex/power. The aggregation level is a nonnegative integer. The network explorer and `inspect` validate hardware too, and all of them read one hardware inventory: an optic counts only where its endpoint node has hardware, `include_disabled: false` keeps enabled nodes and links whose two end nodes are enabled, and invalid hardware (see the DSL `components` section) is refused in either view.

## MaxFlow

<!-- example: unprepared -->

```yaml
workflow:
  - type: MaxFlow
    name: ideal_capacity
    source: ^site1/leaf/
    target: ^site2/leaf/
    mode: combine
    preset: TE_MAXFLOW_UNLIM
    failure_policy: random_link
    iterations: 100
    workers: auto
    failure_trace: false
    outputs:
      min_cut: true
      cost_distribution: true
```

| Key | Default | Meaning |
|-----|---------|---------|
| `source`, `target` | required | Selectors of the two node sets ([Selecting nodes](dsl.md#selecting-nodes)) |
| `mode` | `combine` | `combine` asks one source-set/destination-set question; `pairwise` one per selector-group pair |
| `preset` or `model` | `TE_MAXFLOW_UNLIM` | The model to ask ([Presets](dsl.md#presets); [Routing models and admission](../concepts.md#routing-models-and-admission)); the two are exclusive |
| `offer`, `design_demand` | none | Physical inputs whose applicability follows the declared model |

The default question is unrestricted optimized lossless capacity. Choose `SHORTEST_PATHS_ECMP`, `SHORTEST_PATHS_WCMP`, `SHORTEST_PATHS_MAXFLOW` or an explicit `model` for another question. The result names the question asked (`question`) and where its offer came from (`offer_source`):

| `question` | When | What it asks |
|------------|------|--------------|
| `lossless_bound` | lossless admission and no `offer` | The most the model delivers without loss |
| `fixed_offer_delivery` | an `offer` is given, or a lossy tunnelled `centralized_te` model has a `design_demand` | What the model delivers of that offer (`offer_source` `explicit` or `design`) |
| `first_hop_experiment` | lossy shortest-path routing and no `offer` | What arrives of an offer the Core derives from the sources' first hops |

In `pairwise` mode a source group and a target group that are the same single node give a zero-valued `self` row; any other overlap of source and target groups is refused.

The result holds the cases in order, each with its rows under `states.converged`; each row holds the engine's result. Cuts, edge arrays and cost reports appear only when requested ([Output selection](#output-selection); the kinds of cost report: [Results and their units](../concepts.md#results-and-their-units)).

## TrafficMatrixPlacement

<!-- example: unprepared -->

```yaml
workflow:
  - type: TrafficMatrixPlacement
    name: traffic
    demand_set: peak
    alpha: 1
    failure_policy: random_link
    iterations: 100
    failure_states: [converged, stale]
    interaction: ordered
    workers: auto
    outputs: {cost_distribution: true}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `demand_set` | required | The demand set to place |
| `alpha`, `alpha_from_step` | alpha 1 | The demand multiplier, or the MSD step that supplies it |
| `failure_states` | `[converged]` | The failure states each case reports: `converged`, `stale`, `repair` |
| `interaction` | `ordered` | `ordered` or `simultaneous` placement |

Places the demand set, by default in priority order, then declaration order. Each row has a stable id, its endpoints, its reference request and the engine's result; each state adds totals, and the result adds each declaration's accounting of declared, resolved and discarded units. A failure changes which nodes and links can be used, never a declared volume ([Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states)).

Each case reports the requested `failure_states`, each computed separately: `converged` computes the demands again on the failed network (declared group shares stay fixed caps, and dead caps are listed), `stale` forwards each baseline program unchanged and lossy, and `repair` re-splits the baseline programs over the surviving routes. A state whose bounded forwarding calculation cycles or reaches its round limit reports a forwarding failure with no rows. Group scope refuses `converged` and `repair` under a failure policy when it programs a router inside the IGP domain. The full rules: [Failures: patterns, cases and states](../concepts.md#failures-patterns-cases-and-states).

`interaction: simultaneous` forwards every demand at once, sharing losses on common links, as a lossy question on fixed programs; its rows are not comparable with the default `ordered` rows. A simultaneous step that takes its alpha from an MSD step cannot have pool demands. The full rules: [Ordered and simultaneous placement](../concepts.md#ordered-and-simultaneous-placement).

Use either `alpha` or `alpha_from_step`, never both. Omitting both uses 1. `alpha_from_step` names an earlier MSD step and places at its largest tested feasible alpha. Preparation refuses a name that is not an earlier MSD step; the placement refuses, when it runs, an MSD result with no feasible alpha. The placement records the MSD step's name and the alpha it used (`alpha_source`, `alpha`).

## MaximumSupportedDemand

<!-- example: unprepared -->

```yaml
workflow:
  - type: MaximumSupportedDemand
    name: supported_load
    demand_set: peak
    alpha_start: 1
    growth_factor: 2
    alpha_min: 0.000001
    alpha_max: 1000000000
    alpha_tolerance: 0.01
    max_bracket_iters: 32
    max_bisect_iters: 32
  - type: TrafficMatrixPlacement
    name: tested_load
    demand_set: peak
    alpha_from_step: supported_load
```

Searches for the largest tested alpha at which the demand set is placed in full, keeping every probe ([Maximum supported demand](../concepts.md#maximum-supported-demand)). `alpha_start`, `growth_factor`, `alpha_min` and `alpha_max` bound the search, `alpha_tolerance` ends it, and `max_bracket_iters` and `max_bisect_iters` cap its two phases; the example shows the defaults. `alpha_feasible` is null if no probe was feasible. `search_status` and `stop_reason` say how and why the search ended (each value: [Maximum supported demand](../concepts.md#maximum-supported-demand)).

When a demand set offers no traffic because all declared volumes are zero or every positive volume is discarded, MSD makes one probe at `alpha_max`. If that probe succeeds, it reports `trivial`, with `proof` and `stop_reason` both `nothing_offered`, and retains discard accounting. If scaling the discarded volume exceeds the native integer-unit range or binary64, the probe is refused and MSD reports `range` with `stop_reason` `offer_range`. A positive demand that merely rounds to zero is still searched as `below_resolution`.

An MSD probe is `below_resolution` if any resolved leaf of a positive declaration requests zero units after scaling and expansion, even when the declaration's rounded total is positive. It is never an accepted feasible probe or certificate endpoint; search moves upward from it. Before stopping on tolerance with no feasible probe and a below-resolution lower bracket end, MSD tests the first alpha where every such leaf receives at least one unit, found from rounding alone; an already tested endpoint is reused. It continues if feasible. If no feasible probe is found this way, it reports `none_feasible` with stop reason `unit_resolution`; iteration limits keep `bracket_limit` or `bisect_limit`.

## TunnelCountAnalysis

```yaml
units: {resolution: 1}
network:
  nodes: {S: {}, a: {}, b: {}, T: {}}
  links:
    - {source: S, target: T, capacity: 1, cost: 1}
    - {source: S, target: T, capacity: 100, cost: 2}
    - {source: a, target: T, capacity: 2, cost: 1}
    - {source: b, target: T, capacity: 10, cost: 1}
demands:
  te:
    - {id: pooled, source: '^S$', target: '^T$', volume: 0, preset: TE_ECMP_16_LSP}
    - id: heads
      source: '^(a|b)$'
      target: '^T$'
      volume: 0
      model:
        routing: {type: centralized_te, source_allocation: equal, tunnel_count: {per_head: 1}}
        admission: lossless
workflow:
  - type: TunnelCountAnalysis
    name: counts
    demand_set: te
    counts: [2]
    up_to: 3
    design_demand: 2
    offer: 1000
    workers: auto
    outputs: {details: false}
```

| Key | Default | Meaning |
|-----|---------|---------|
| `demand_set` | required | A set of tunnelled `centralized_te` demands |
| `counts` | none | Distinct tunnel counts per head, each from 1 to 10000 |
| `up_to` | none | The limit of the "up to" row |
| `design_demand`, `offer` | required | The physical design and offer for every demand of the set |

Evaluates every demand of the set once per listed tunnel count, then once "up to" the `up_to` limit, each row a fresh native evaluation of the demand's centralized-TE model with that count, lossy at `offer` and planned for `design_demand`. Every demand of the set uses the same `design_demand` and `offer`; the rows read no declared volume. The set must hold tunnelled centralized-TE demands only (`centralized_te` with a `tunnel_count`, or the `TE_ECMP_16_LSP` and `TE_ECMP_UP_TO_256_LSP` presets); any other model is refused at preparation. Self pairs and same-label group pairs do not create demands; empty selections and entirely excluded declarations have no tunnel-count rows.

Rows follow the set's demands, then the listed counts in order, then the `up_to` row. A row's `count` is the requested count per head (for the `up_to` row, its limit); the chosen count is `plan.tunnels_per_head`. The `plan` (fluid and whole-unit tunnel size, planned bandwidth, tunnel cost, headroom penalty, the largest lossless offer and `insufficient_resolution`) is written in every row; `result` holds what the offer delivers and loses. `lossless_at_design_units` is the lossless delivery at the design, min(design, largest lossless offer). Rows are not monotone in the count, and "up to" picks the smallest count that carries the live heads' design shares, not the count that delivers most of the offer.

In the example, the pooled demand delivers 1 + 100 of its offer of 1000 with two tunnels (one per link) and its up-to row chooses one tunnel, on the wide link; the two heads deliver 2 + 10 with two tunnels each and choose one. A pool row's `plan.total_tunnel_cost` is on the analysis graph: its `pool` section's `synthetic_ingress_cost` of 1 is paid once per tunnel, which `physical_tunnel_cost` leaves out (3 and 2 here).

The step's offer is a known lossy offer for the TE ingress pools of its set, and it and the design take part in choosing the bandwidth unit `q` ([Units and the resolution q](../concepts.md#units-and-the-resolution-q); [Tunnels and TE ingress pools](../concepts.md#tunnels-and-te-ingress-pools)). Naming the set makes it part of the run's prepared traffic like any step's set: its declared volumes and models still take part in choosing `q` and are validated at preparation.

## Output selection

| `outputs` key | Steps | Adds to each row |
| --- | --- | --- |
| `edge_flows` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | the units each directed link carries |
| `residual` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | each directed link's residual capacity after the row; under simultaneous placement, the one final residual every row shares |
| `edge_reservations` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | each directed link's tunnel holds |
| `saturated_boundary_edges` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | the saturated links at the sources' reachable boundary |
| `min_cut` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis | the minimum cut closest to the sources, where defined (unrestricted optimized maximum flow); null otherwise |
| `cost_distribution` | MaxFlow, TrafficMatrixPlacement | the cost report: delivered units per path cost, or the native marginal cost curve |
| `details` | MaxFlow, TrafficMatrixPlacement, TunnelCountAnalysis, MaximumSupportedDemand | native per-source, per-tunnel, plan and call fields |

All are false by default. Every row field is described in the [Results](results.md) reference.

Each output is selected on its own: `outputs: {details: false, min_cut: true}` gives compact rows with a cut, and `outputs: {details: true}` gives the detail fields without a cost report or cut. Omitted outputs, `{}` and `details: false` give compact rows; `details` accepts only a boolean. A row's `pool` is present either way, so a TE ingress pool's attachment cost stays identifiable. `MaximumSupportedDemand` accepts only `details`, which applies to its best rows; its probe history stays compact. Python spells the detail selector `export_details` (refused in YAML), and only Python can export every probe's rows (`MSDQuery.export_probe_rows`). `details` shapes only the JSON: Python results always hold the detail fields. Every other output exists only when requested, in Python as in JSON.

The results schema enforces each row's applicable detail fields: they are absent with `details: false` and present with `details: true`. A native result's `plan` is null when no tunnel plan applies; a tunnel-count row keeps `plan` at row level rather than inside `result`. Compact rows keep their drop totals: `edge_drop_units` sums losses on physical links and TE ingress pool attachments.
