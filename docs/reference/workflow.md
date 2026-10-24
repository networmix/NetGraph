# Workflow Reference

`Scenario.from_yaml(text)` parses an ordered workflow. Python callers execute `run(prepare(scenario))`; the returned `RunResult.steps` tuple contains each step's name, type, execution order, seed provenance, normalized question and typed result. Duplicate names refuse before execution.

An unnamed YAML step receives `<type>_<declaration index>`. A step seed is explicit or derived from the scenario seed and effective step name. Results are returned only after the complete workflow succeeds.

## BuildGraph

```yaml
workflow:
  - type: BuildGraph
    name: topology
    add_reverse: true
```

Returns `BuildGraphResult` with node/link counts and physical NetworkX node-link JSON. Reverse export edges are enabled by default. This operation exports the domain network, including disabled entities and their flags.

## NetworkStats

```yaml
workflow:
  - type: NetworkStats
    name: stats
    include_disabled: false
    excluded_nodes: []
    excluded_links: []
```

Returns physical node/link counts and capacity, cost and degree statistics. The question records these effective filters.

## CostPower

```yaml
workflow:
  - type: CostPower
    name: hardware
    include_disabled: false
    aggregation_level: 2
```

Returns hardware rows grouped by hierarchy level, with platform and link-end optics capex/power. The aggregation level is a nonnegative integer. Hardware validation remains available through the explorer and `inspect`.

## MaxFlow

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

The default question is unrestricted optimized lossless capacity. Choose `SHORTEST_PATHS_ECMP`, `SHORTEST_PATHS_WCMP`, `SHORTEST_PATHS_MAXFLOW` or an explicit `model` for another question. `preset` and `model` are exclusive. Optional `offer` and `design_demand` are physical inputs whose applicability follows the declared model.

`combine` asks one resolved source-set/destination-set question. `pairwise` evaluates each selector-group pair independently. A singleton self pair returns a separate zero-valued row; other overlapping groups refuse.

The result contains ordered cases with `states.converged.rows`. Rows retain native results. Cuts and edge arrays require their native output flags. Cost reports are opt-in: optimized unrestricted capacity has a marginal curve; determined path costs have delivered-unit bins.

## TrafficMatrixPlacement

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

Places the complete demand matrix in priority/declaration order through native policies. The result includes stable row IDs, endpoint labels, exact reference requests and totals, and discarded-share accounting. Failures change eligibility; they do not remove the declared volume of a failed endpoint.

Each case reports the requested `failure_states`, each computed on its own ledger (default `[converged]`; `stale` and `repair` only when listed):

- `converged`: the demands computed again on the failed network. Controller tables are rebuilt for the case; declared forwarding-group shares stay fixed caps. A root group with no live member keeps its cap, dropped at its router, and is listed in the state's `dead_caps`; a case whose program would forward such a share differently is refused with the group, case and state.
- `stale`: each demand's program from the case without failures, forwarded unchanged and lossy at that baseline's admitted total; traffic that reaches a failed node or link is lost there.
- `repair`: the same programs with failed routes removed and survivors re-split (no new route search), at the declared request and admission; group shares stay caps.

`reference_request_units` stays the scaled request in every state; the native `requested` and `offered` describe each call. Cost reports and precision misses come from converged rows only. For an explicit-route demand alone, converged and repair forward the same program. A lossy forwarding that finds no fixed point reports that case and state as `failure` (no rows); in the baseline it stops the step when stale or repair needs its programs. Group scope refuses converged and repair under a failure policy when it programs a router inside the IGP domain.

`interaction: simultaneous` forwards every demand at once in one native list, sharing losses on common links, as a lossy question on fixed programs: each model that can be lossy forwards a lossy copy of itself (tunnel models are set up first and keep their reservations), and a live controller (`TE_MAXFLOW_UNLIM`, `SHORTEST_PATHS_MAXFLOW`) is computed, then its program forwarded lossy. Its lossy copy is created after the other participants, in every state, so it loses one-unit ties to them. Rows are not comparable with the default `ordered` rows. A TE ingress pool in a simultaneous step gets a lossy offer budget, its largest known request, reported as the row's `pool.offer_limit_units`. Budgets are prepared once for the scenario: every placement step on that preparation reports them, and they count in the choice of `q`. A simultaneous step that takes its alpha from an MSD step cannot have pool demands.

Use either `alpha` or `alpha_from_step`, never both. Omitting both uses 1. An earlier MSD step supplies its actual largest tested feasible factor; missing, forward, wrong-type and no-feasible dependencies refuse. The consuming step records the producer name and effective alpha.

## MaximumSupportedDemand

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

The search uses one persistent ledger, removes all owners before every probe and checks exact native-unit feasibility. It retains all probes and the best tested feasible rows. `alpha_feasible` is null if no probe was feasible. `search_status` distinguishes `feasible`, `none_feasible`, `range`, `stagnation`, `limit` and `trivial`; `stop_reason` records the precise boundary. A range refusal is not an infeasible congestion sample.

Only a proved downward-closed class receives an upper certificate. The bounded search on an unproved composition is a heuristic. The result does not claim an untested global maximum. YAML has no full-probe-row export input; Python's `MSDQuery.export_probe_rows` is an explicit opt-in.

## Cases, seeds and exports

No failure request means one baseline. With sampling, `occurrences` sum to the requested iterations, including sampled empty patterns on the baseline. Optional traces keep the first draw producing each physical pattern. A failed link excludes both directions. All supported Python versions use per-entity Bernoulli for random rules.

Policy seeds preserve the established recipe: SHA256 of UTF-8 `"<master>:failure_policy:failure_policy:<name>"`, first four bytes big-endian, masked with `0x7fffffff`. Master 42 and policy `random_link` yield 2099469712. Step derivation uses `"<master>:workflow_step:<effective-name>"` with the same truncation and mask. Metadata records seed source, runtime, RNG and draw order.

`write_json(result, file)` exports the run. CLI `--keys` executes the full workflow and then selects steps in declaration order; actual `execution_order` values are retained, so a filtered export can have gaps. A full run remains contiguous. CLI `--profile` prints the retained step report to stderr, while `--stdout` remains JSON.

Custom steps implement `run(StepContext) -> StepOutput`; earlier successful steps are available through a read-only mapping. Custom result types register an exact-type encoder with `register_result_exporter`; already JSON-valued domain data is also accepted. See [API](api.md) for the public boundary and [DSL](dsl.md) for complete input syntax.


## Output selection

`MaxFlow` and `TrafficMatrixPlacement` accept `outputs.details` (false by default) alongside their native output flags and `cost_distribution`. It adds per-source, per-tunnel, plan and call details to compact exact JSON rows. Pool metadata stays present in either mode so synthetic-ingress costs remain identifiable. `MaximumSupportedDemand` accepts `outputs: {details: true}` for its best rows; this step accepts no other output keys. Python callers can independently request retained historical probe rows with `MSDQuery.export_probe_rows`.

Details do not enable cost bins, cuts or arrays. For example `outputs: {details: false, min_cut: true}` keeps compact capacity rows with a requested cut; `outputs: {details: true}` emits native details without a cost report or cut. Python query/workflow constructors spell the single detail selector `export_details`; that spelling is refused in YAML. The former `include_flow_details` migration is only to `outputs.cost_distribution`.

Capacity and traffic-matrix placement resolve `workers: auto` to the CPU count, a fixed rule for each analysis kind selected by paired measurements on the shipped scenarios. Explicit positive worker counts override it. MSD is serial.

An MSD probe with a positive physical leaf rounded to zero requested units has outcome `below_resolution`. It is never feasible or a certificate endpoint; search moves upward from it. If no verified feasible probe is found at the unit-resolution boundary, MSD returns `none_feasible` with stop reason `unit_resolution`. An `alpha_from_step` placement refuses such a result because it has no tested feasible alpha. Placement’s own totals retain their exact integer-unit meaning.

Built-in steps are immutable records; `dataclasses.replace` makes an edited copy. A custom step’s own data is neither copied nor frozen and may change its later answers; `prepare` records its name and seed.

Before a tolerance stop with no verified feasible point and a below-resolution lower end, MSD tests the first multiplier where every positive leaf receives a unit. It finds this multiplier from rounding alone, records an ordinary probe and continues if feasible. Iteration-limit stops retain `bracket_limit` or `bisect_limit`.
