# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.22.0] - 2026-08-24

### Fixed

Analyses that previously returned wrong numbers without any error. If you rely on results from an earlier version, re-run them.

- **BREAKING**: `MaxFlowResult.min_cut` (`max_flow_detailed` with `include_min_cut=True`) returns a true minimum cut instead of all saturated edges. Its capacity equals the max flow for the default configuration (`PROPORTIONAL` placement, `require_capacity=True`, `shortest_path=False`); the others are placement models, not max-flow computations. For saturated edges, use `sensitivity()`
- Demand placement could report more flow than the network carries: an SPF-cached demand and a FlowPolicy-based demand sharing (source, destination, priority) had colliding flow ids that merged silently, so a scenario with a 10-unit min cut reported 15 units placed. Two policy-based demands sharing that triple now raise `ValueError` — merge their volumes or give them distinct priorities
- Combine-mode expansion routed volume through a zero-cost pseudo-node bypass, unbounded by real capacity, when source and target selections overlapped or when two demands' composed pseudo endpoints fused (demand ids and group labels may contain `|`). Shared nodes are now excluded from the target side across `flatten`, `per_group`, and `group_pairwise`, and colliding endpoints raise; demand ids must be unique in any mode. A source group left with no targets is skipped; a fully-overlapping `flatten`/`combine` demand fails with `No demands could be expanded`
- Weighted failure sampling (`weight_by`) selected by entity name rather than by weight wherever `u**(1/w)` underflowed to zero — around 1e-5, i.e. per-hour failure rates — inverting the intended bias
- Seeded Monte Carlo was not reproducible across identical scenario rebuilds: link ids carried a random uuid suffix whose sort order shifted per build, remapping seeded draws onto different parallel links. Link ids are now a deterministic per-(source, target) sequence (`A|B|0`), and `add_link` raises rather than silently overwriting a repeated link or a colliding id. Separately, `seed=None` falls back to the failure policy's own seed instead of replaying one identical pattern every iteration
- Risk group failures hit the wrong entities: a group sharing its name with a node or link excluded that node and left its members up, and `expand_groups` never reached nested members, expanding differently for entity rules and `risk_group` rules. Expansion is now transitive and identical for both. Separately, the `disabled: true` cascade runs after membership rules and `generate` blocks, so entities assigned by those mechanisms are disabled
- `group_mode: per_group` now matches its documented semantics: `combine` creates one demand per source group, `pairwise` pairs nodes within each same-label group, and volume splits evenly across groups; a skipped group's share is not redistributed
- Ordering is deterministic across runs and interpreters: `k_shortest_paths` between multi-node groups merges results across all source/sink pairs instead of returning only the best pair's, and breaks ties structurally rather than by `PYTHONHASHSEED`; `shortest_paths` likewise; and `risk_groups` comes back sorted from `flatten_node_attrs`/`flatten_link_attrs`, so `group_by` labels are stable
- Analysis code could get wrong or cross-contaminated results: unbound `AnalysisContext` flow methods ignored custom augmentations passed to `analyze()`, bound pairwise results shared one mutable default across pairs, and FailureManager's prepared-match cache could return another policy's matches from a reused `id()`
- Errors that should not have fired are gone: `MaximumSupportedDemand` no longer raises a false "No feasible alpha found" for a large `alpha_start`, `BuildGraph` accepts attrs colliding with reserved keys (`disabled`, `id`, `capacity`, `cost`) — the reserved keys win in the exported graph — and demand configs without `id` no longer crash

Inputs that were silently accepted and then misbehaved now fail at load or construction. Scenarios relying on any of them need an edit.

- The analysis graph build rejects fractional link and augmentation costs, link capacities at or above the internal pseudo-edge capacity (1e15), and cost totals reaching 2^62 — each previously corrupted SPF, max-flow, and cost-distribution results through int64 truncation, capacity clamping, or overflow. `from_networkx` applies the same cost check
- Failure policies: a mistyped `scope` (e.g. `nodes`) that matched nothing, a bare-string `risk_groups:` value that expanded into one group per character, `link_rules` entries without `source` and `target`, non-list `node_rules`/`link_rules` sections, and a policy whose modes all have zero weight
- `membership`, `disabled`, and `generate` keys on nested risk-group `children` are rejected instead of ignored; only top-level groups are registered, so declare such groups at top level and reference them by name
- Blueprints and selectors: unknown or malformed blueprint `params` prefixes, non-list `in`/`not_in` values, unhashable `generate` `group_by` values, and `generate` name templates rendering one name from two distinct values. Dotted subgroup names (e.g. `rack.a.count`) now resolve by longest-prefix match instead of failing with a contradictory error
- Workflow and DSL: duplicate effective step names, which silently overwrote each other's results; `alpha_from_step` naming a missing or not-yet-run step; an invalid step `parallelism` or `mode`; malformed DSL values such as a non-dict child `attrs`; and a bound context that disagrees with the `max_flow_analysis`/`sensitivity_analysis` call arguments

Other fixes.

- Link `expand:` blocks substitute variables in every string field (nested `attrs`, `risk_groups`, selector `match` values), and match-only selectors with expand blocks are no longer ignored. A whole-string placeholder keeps the variable's native type, so selectors match numeric attributes — but a bare placeholder bound to a non-string variable and used as a path selector now raises `ValueError` instead of being stringified. Blueprint instantiation paths are regex-escaped, so group names containing regex metacharacters no longer link sibling subtrees or drop links
- `ngraph run --stdout` emits pure JSON on stdout, with banners and errors on stderr, so output is safe to pipe to `jq`; `--profile` merges per-worker profiles into step profiles again; and workflow metadata reports the seed a step actually uses
- `NetworkExplorer` paths no longer truncate at hierarchy segments named `root`, `get_bom_map` honors `include_root` without duplicating the root BOM under an empty key, and `ComponentsLibrary.from_yaml` warns on the unrecognized `cost` key (the parser reads `capex`)
- Documentation is corrected throughout: every example in the reference and getting-started docs executes against the shipped code, and the design reference's algorithm descriptions match the C++ engine

### Changed

- **BREAKING**: `from_networkx` `bidirectional` defaults to `None` and is inferred from the graph type: undirected inputs produce antiparallel arc pairs per edge, preserving connectivity, instead of a single arbitrary arc. Pass `bidirectional=False` for the previous conversion
- A demand config without `mode` now means `combine` rather than `pairwise`; an invalid `mode` string raises instead of silently selecting pairwise, and parsing is case-insensitive
- Exported shapes changed, so consumers of results may need updating. `FailurePolicy.to_dict` emits the scenario YAML format — rule `conditions` and `logic` nested under `match`, no derived `seed` — reshaping the `scenario.failures` snapshot. `TrafficDemand.to_dict()` is the canonical demand form used by the results snapshot and by step `base_demands`, which now include `group_mode` and `attrs`, and names `flow_policy` by preset (e.g. `SHORTEST_PATHS_ECMP`) instead of by integer; old integer values still load. `Results.to_dict` recurses into nested output, so exports are JSON-safe without `default=str`
- Flow placement semantics are pinned: `SHORTEST_PATHS_*` presets admit flow onto the cost-only shortest paths of the base topology and drop the overflow (IGP semantics); `TE_*` presets reroute onto residual-capacity paths
- Monte Carlo is thread-based throughout: nothing is pickled, so analysis functions defined in `__main__` or a notebook run at full parallelism instead of being forced serial. Custom functions receive pre-built per-run inputs through a `prepare_inputs` hook they opt into, and metadata gains `occurrence_counts` aligned with `results`, so custom result types carry correct pattern multiplicities; deduplication assumes a deterministic analysis function
- `mode: random` failure selection uses a binomial draw on Python 3.12+, O(failures) instead of O(matched). The distribution is unchanged, but seeded runs on 3.12+ no longer reproduce the failure patterns they did before
- Performance: per-iteration work (demand expansion, node-ID resolution, blueprint `params`, the risk-group index) now happens once per run, pairwise pseudo-attachment edges are built once per group member (O(G x members), previously O(G^2 x members)), weighted failure selection is about 4x faster on 100k-candidate pools, and `MaximumSupportedDemand` probes share one SPF DAG cache
- `CostPower` reports aggregated capex and power even on networks that strict hardware validation would reject; that validation remains available via `ngraph inspect`. Importing `ngraph` installs no stdout handler and does not import `ngraph.cli`; console logs go to stderr

### Added

- Demands can be pinned to explicit routes with `static_paths`, modelling MPLS-style LSPs: one flow per route, and a route broken by a failure carries nothing instead of rerouting. A route is a list of node names or link ids (a link id picks a specific one of several parallel links). Requires `mode: pairwise` with selectors matching exactly one source and one target
- Minimum `netgraph-core` raised to 0.8.0. Its max-flow completion phase makes `max_flow` return a true maximum, so reported values can increase against 0.7.x, and it provides the APIs pinned routes are built on
- For analysis code: `AnalysisContext.sensitivity_with_flow` (max flow and edge sensitivity per group pair in one pass, now backing `sensitivity_analysis`, results unchanged), `FailurePolicy.apply_failures_typed` returning scope-typed failure sets, and `build_demand_placement_inputs`, whose `expansion=`/`resolved_ids=` output `demand_placement_analysis` now accepts. Also public: `AnalysisContext.build_node_mask`/`build_edge_mask`, `Scenario.run(step_hook=...)`, `TrafficDemand.to_dict()`, `Mode.from_string`, and `link_path_key`

### Removed

- **BREAKING**: failure-policy `expand_children`. Cascading a failed risk group to its children is inherent and always applied; scenarios using the key must drop it. It previously crashed when enabled and did nothing when disabled
- **BREAKING**: the inline-object `flow_policy` form in the scenario schema; use a preset name string. Inline-dict and boolean values now raise at scenario build time, listing the valid presets, instead of crashing later in analysis
- Replaced API: `placement_rounds` on `demand_placement_analysis` and `FailureManager.run_demand_placement_monte_carlo`, which never affected placement; `build_demand_context`, superseded by `build_demand_placement_inputs`; and the module-level `build_node_mask`/`build_edge_mask`, superseded by the `AnalysisContext` methods of the same name
- Also removed: `Scenario.seed_manager`, `expand_templates` (use `expand_block`), `DemandSet.to_dict`, `FailurePatternResult`, the `MIN_CAP`/`MIN_FLOW` constants, `select_nodes`'s `excluded_nodes` (analysis exclusions now go through Core masks), dict input to `flatten_risk_group_attrs`, `NetworkExplorer.get_node_utilization`'s `include_disabled` and the always-False `NodeUtilization.disabled`, the dead `TrafficDemand.volume_placed` and `flow_policy_obj` fields, and `cli`/`logging` from `ngraph.__all__` (still importable as submodules)

### Deprecated

- `placement_rounds` on the `MaximumSupportedDemand` and `TrafficMatrixPlacement` workflow steps. Still accepted in YAML, but it has no effect, warns when set to a non-default value, and is no longer exported in result contexts

## [0.21.0] - 2026-03-26

### Fixed

- Risk group scoped failures now produce correct exclusions; `compute_exclusions` passes flattened attribute dicts to policy matching instead of raw `RiskGroup` objects

### Changed

- Relicensed from BSD-3-Clause to MIT

### Added

- Cached failure-rule candidate pools in `FailureManager`, avoiding repeated condition matching across Monte Carlo iterations
- Cached risk group membership index for O(1) node/link exclusion lookup on risk group failure

## [0.20.0] - 2026-02-26

### Changed

- Relicensed from GPL-3.0-or-later to BSD-3-Clause

## [0.19.0] - 2026-02-18

### Changed

- Relicensed from AGPL-3.0-or-later to GPL-3.0-or-later

## [0.18.0] - 2026-02-17

### Added

- Python 3.14 support, including free-threaded (no-GIL) builds in CI

## [0.17.4] - 2026-02-08

### Fixed

- Single shared RNG per `apply_failures` call, fixing correlated-seed bug across rules
- Bracket-exhaustion edge case in MSD binary search when all probed alphas are feasible

### Removed

- `seeds_per_alpha` MSD parameter (placement is deterministic)
- `SeedManager.create_random_state()` and `seed_global_random()` (unused)

## [0.17.3] - 2026-02-02

### Fixed

- Link path filter now uses deterministic `{source}|{target}` instead of full link ID

## [0.17.2] - 2026-02-02

### Changed

- Version management simplified

## [0.17.1] - 2026-01-16

### Fixed

- DSL skill documentation aligned with implementation; removed unused `demand_placed` schema field

## [0.17.0] - 2026-01-10

### Changed

- **BREAKING**: DSL syntax refinement with renamed fields and restructured expansion blocks; see updated [DSL reference](docs/reference/dsl.md)

## [0.16.0] - 2025-12-21

### Changed

- **Module reorganization**: `ngraph.exec` split into `ngraph.analysis` (runtime analysis) and `ngraph.model` (data structures); public API unchanged via re-exports
- **Expanded public API**: `TrafficDemand`, `FlowPolicyPreset`, `Scenario`, `NetworkExplorer`, and placement functions now exported from top-level modules
- **Placement analysis**: Extracted SPF caching and demand placement logic into `ngraph.analysis.placement` module with `place_demands()` and `PlacementResult`

### Added

- `ngraph.model.demand` subpackage: `TrafficDemand` and builder functions
- `ngraph.model.flow` subpackage: `FlowPolicyPreset` and policy configuration
- `ngraph.types` exports: `Mode`, `FlowPlacement`, `EdgeSelect`, `EdgeRef`, `MaxFlowResult`

## [0.15.0] - 2025-12-21

### Added

- **Dynamic risk group creation**: `membership` rules auto-assign entities by attribute matching; `generate` blocks create groups from unique attribute values
- **Risk group validation**: Undefined references and circular hierarchies detected at load time
- **Dot-notation in conditions**: `attr` field supports nested paths (e.g., `hardware.vendor`)

### Changed

- `match.logic` defaults now context-aware: `"or"` for adjacency/demands, `"and"` for membership rules

## [0.14.0] - 2025-12-20

### Changed

- **BREAKING**: Monte Carlo results restructured: `baseline` returned separately; `results` contains deduplicated failure patterns with `occurrence_count`
- **BREAKING**: `baseline` parameter removed from Monte Carlo APIs; baseline always runs implicitly

### Added

- `FlowIterationResult.occurrence_count`: how many iterations produced this failure pattern
- `FlowIterationResult.failure_trace`: mode/rule selection details when `store_failure_patterns=True`

## [0.13.0] - 2025-12-19

### Changed

- **BREAKING**: `TrafficDemand.source_path`/`sink_path` renamed to `source`/`sink`; now accept string patterns or selector dicts with `path`, `group_by`, and `match` fields
- **BREAKING**: Removed `attr:<name>` magic string syntax; use `{"group_by": "<name>"}` dict selectors instead
- **BREAKING**: Removed `ngraph.utils.nodes` module; use `ngraph.dsl.selectors` for node selection
- **Unified selector system**: `ngraph.dsl.selectors` provides `normalize_selector()` and `select_nodes()` for consistent node selection across demands, workflows, adjacency, and overrides
- **Variable expansion in demands**: `TrafficDemand` supports `expand_vars` with `$var`/`${var}` syntax and `expansion_mode` (cartesian/zip)
- **Match conditions**: Selector `match` field supports 12 operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `in`, `not_in`, `any_value`, `no_value`
- **Context-aware defaults**: `active_only` defaults to `True` for demands/workflows, `False` for adjacency/overrides

### Added

- `ngraph.dsl.selectors` module: `NodeSelector`, `MatchSpec`, `Condition` schema classes
- `ngraph.dsl.expansion` module: `ExpansionSpec`, `expand_templates()`, `substitute_vars()`, `expand_name_patterns()`, `expand_risk_group_refs()`
- **Bracket expansion in risk groups**: `[1-3]` and `[a,b,c]` patterns now expand in risk group definitions (including children) and membership arrays on nodes, links, and groups
- `TrafficDemand.group_mode` field for node group handling (`flatten`, `per_group`, `group_pairwise`)
- `.claude/skills/netgraph-dsl/`: Claude skill with DSL syntax reference and examples

## [0.12.3] - 2025-12-11

### Changed

- **SPF caching in demand placement**: `demand_placement_analysis()` caches SPF results by (source, policy_preset) for ECMP, WCMP, and TE_WCMP_UNLIM policies; TE policies recompute when capacity constraints require alternate paths
- **MSD AnalysisContext caching**: `MaximumSupportedDemand` builds `AnalysisContext` once and reuses it across all binary search probes

### Fixed

- **TrafficDemand ID preservation**: Fixed context caching with `mode: combine` by ensuring `TrafficDemand.id` is preserved through serialization; pseudo node names now remain consistent across context build and analysis

## [0.12.2] - 2025-12-08

### Fixed

- **Cache key generation**: Use `id()` instead of `str()` for non-hashable kwargs in `_create_cache_key()` to avoid expensive `__repr__` traversals on large objects

## [0.12.1] - 2025-12-07

### Added

- **NetworkX interop**: New `ngraph.lib.nx` module with `from_networkx()` and `to_networkx()` for converting between NetworkX graphs and netgraph_core.StrictMultiDiGraph
- **Mapping classes**: `NodeMap` and `EdgeMap` for bidirectional node/edge ID lookups after conversion

## [0.12.0] - 2025-12-06

### Changed

- **BREAKING**: Minimum Python version raised to 3.11
- **Dependencies**: Updated netgraph-core to >=0.3.0

## [0.11.1] - 2025-12-06

### Added

- **AnalysisContext API**: `analyze()` now returns an `AnalysisContext` for max-flow, shortest paths, and sensitivity analysis with reusable state.

### Changed

- **Performance runner & workflows**: Reuse bound `AnalysisContext` to avoid rebuilding Core graphs across repeated analyses.
- **Docs & examples**: Updated guides and reference docs to describe the new analysis API and bound-context workflow.
- **Failure handling**: More consistent tracking of disabled nodes and links during analysis.
