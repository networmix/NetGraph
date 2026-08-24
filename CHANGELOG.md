# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

Analyses that previously returned wrong numbers without any error. If you rely on results from an earlier version, re-run them.

- Demand placement could report more flow than the network carries. An SPF-cached demand and a FlowPolicy-based demand sharing (source, destination, priority) produced colliding flow ids whose flows merged silently; a scenario with a 10-unit min cut reported 15 units placed. Cached flow ids now occupy a disjoint range, and two policy-based demands with the same triple raise `ValueError`
- Weighted failure sampling (`weight_by`) selected by entity name rather than by weight for small weights. Selection keys are now computed in the log domain; previously `u**(1/w)` underflowed to zero for weights around 1e-5 (per-hour failure rates), inverting the intended bias
- Combine-mode demand expansion with overlapping source/target selections routed volume through a zero-cost pseudo-node bypass, reporting placement unbounded by real capacity. Shared nodes are now excluded from the target side across `flatten`, `per_group`, and `group_pairwise`. A source group left with no targets is skipped, and a fully-overlapping `flatten`/`combine` demand fails with `No demands could be expanded`
- Demand expansion could fuse two demands' pseudo endpoints, recreating that same bypass, because composed ids concatenate demand ids and group labels and both may contain `|`. Composed ids are now injective, and duplicate demand ids and colliding pseudo endpoints raise `ValueError`
- Seeded Monte Carlo runs were not reproducible across identical scenario rebuilds: link ids carried a random uuid suffix whose sort order changed per build, remapping seeded draws onto different parallel links. Link ids are now a deterministic per-(source, target) sequence (`A|B|0`), and `add_link` raises instead of silently overwriting when an id collides (possible when node names contain `|`) or when the same link is added twice
- A risk group sharing its name with a node or link excluded the wrong entity: the node was excluded and the group's members were left up. Failed entities are now classified by rule scope
- `expand_groups` expanded differently depending on whether a failure came from an entity rule or a `risk_group` rule, and never reached members of nested groups. Expansion is now transitive and identical for both rule kinds
- **BREAKING**: `MaxFlowResult.min_cut` (`max_flow_detailed` with `include_min_cut=True`) returns a true minimum cut whose capacity equals the max flow, instead of all saturated edges. Saturated-edge analysis remains available via `sensitivity()`
- Monte Carlo with `seed=None` now falls back to the failure policy's own seed; a seeded policy previously produced one identical failure pattern on every iteration
- `group_mode: per_group` now matches its documented semantics: `combine` creates one demand per source group, `pairwise` pairs nodes within each same-label group, and volume splits evenly across groups. A skipped group's share is not redistributed
- `k_shortest_paths` between multi-node groups merges results across all source/sink pairs instead of returning paths for the single best pair, and breaks ties structurally so results no longer depend on `PYTHONHASHSEED`; `shortest_paths` ordering is likewise deterministic
- Unbound `AnalysisContext` flow methods (`max_flow`, `max_flow_detailed`, `sensitivity`) honor custom augmentations passed to `analyze()`
- Bound pairwise results for overlapping or empty pairs no longer share one mutable default object across pairs
- FailureManager's prepared-match cache verifies policy identity, so a reused `id()` address cannot return another policy's matches
- `MaximumSupportedDemand` probes `alpha_min` before declaring infeasibility, instead of raising a false "No feasible alpha found" when `alpha_start` is large
- The disable cascade for `disabled: true` risk groups runs after membership rules and `generate` blocks, so entities assigned by those mechanisms are disabled
- `flatten_node_attrs`/`flatten_link_attrs` expose `risk_groups` as a sorted list, making `group_by` labels deterministic
- `BuildGraph` no longer raises `TypeError` when node or link attrs collide with reserved keys (`disabled`, `id`, `capacity`, `cost`); reserved keys win in the exported graph

Inputs that were silently accepted and then misbehaved now fail at load or construction.

- The analysis graph build rejects fractional link and augmentation costs, link capacities at or above the internal pseudo-edge capacity (1e15), and cost totals reaching 2^62. Each previously corrupted SPF, max-flow, and cost-distribution results through int64 truncation, capacity clamping, or overflow; `from_networkx` applies the same cost check
- A `FailureRule` with a mistyped `scope` (e.g. `nodes`) raises at construction instead of matching nothing, and a bare-string `risk_groups:` value raises instead of expanding into one group per character
- Inline-dict and boolean `flow_policy` values raise at scenario build time, listing valid presets, instead of being accepted and crashing later in analysis
- Duplicate effective workflow step names raise before execution instead of silently overwriting each other's results
- `membership`, `disabled`, and `generate` keys on nested risk-group `children` are rejected instead of ignored; only top-level groups are registered, so declare such groups at top level and reference them by name
- `link_rules` entries require `source` and `target`, and non-list `node_rules`/`link_rules` sections raise instead of being skipped
- Failure modes with zero weight are never applied, and a policy whose modes all have zero weight is rejected at load
- Blueprint `params` overrides raise on unknown subgroup prefixes and malformed keys instead of being ignored, and subgroup names containing dots (e.g. `rack.a.count`) resolve by longest-prefix match instead of failing with a contradictory error
- `in`/`not_in` conditions require list values, `generate` blocks reject unhashable `group_by` values and templates that render one name from two distinct values, and `max_flow_analysis`/`sensitivity_analysis` reject a bound context whose binding differs from the call arguments
- A demand endpoint missing from a supplied analysis context reports the likely config/context mismatch instead of a raw `KeyError`, and demand configs without `id` no longer crash: ids derive deterministically from source, target, and position
- `TrafficMatrixPlacement` with `alpha_from_step` naming a missing or not-yet-run step raises an error naming that step

Other fixes.

- Link `expand:` blocks substitute variables in every string field (nested `attrs`, `risk_groups`, selector `match` values), and match-only selectors with expand blocks are no longer ignored. A whole-string placeholder keeps the variable's native type, so selectors match numeric attributes with `==`/`!=`/`in`/`not_in`; a bare placeholder bound to a non-string variable and used as a path selector now raises `ValueError` instead of being stringified
- Blueprint instantiation paths are regex-escaped when building link selectors, so group names containing regex metacharacters no longer link sibling subtrees or drop links
- Workflow metadata `seed_source`/`active_seed` report the seed a step actually uses; a step without its own seed records `seed_source: none`
- `NetworkExplorer` paths no longer truncate at hierarchy segments named `root`, and `get_bom_map` honors `include_root` without duplicating the root BOM under an empty key
- `ComponentsLibrary.from_yaml` treats an empty or null `components:` mapping as an empty library and warns when a definition uses the unrecognized `cost` key (the parser reads `capex`)
- `ngraph run --stdout` emits pure JSON on stdout, with banners, the profile report, and errors on stderr, so output is safe to pipe to `jq`
- `ngraph run --profile` merges per-worker profiles into step profiles again, and no longer leaks `NGRAPH_PROFILE_DIR` into the process environment
- `ngraph inspect --detail` sorts the "Top demands (by offered volume)" table by volume
- Documentation is corrected throughout: every example in the reference and getting-started docs executes against the shipped code, and the design reference's algorithm descriptions match the C++ engine

### Changed

- **BREAKING**: `from_networkx` `bidirectional` defaults to `None` and is inferred from the graph type: undirected inputs produce antiparallel arc pairs per edge, preserving connectivity, instead of a single arbitrary arc. Pass `bidirectional=False` for the previous conversion
- Selector evaluation (schema types, condition evaluation, node selection, attribute flattening) and `parse_match_spec` moved from `ngraph.dsl.selectors` to `ngraph.model.selectors`. The DSL package keeps YAML-facing parsing and re-exports the moved names, so existing imports continue to work
- `FailurePolicy.to_dict` emits the scenario YAML format (conditions and logic nested under `match`, `weight_by` when set, no derived `seed`) and round-trips through `build_failure_policy`; the exported `scenario.failures` snapshot changes shape accordingly
- `Results.to_dict` converts nested output recursively — dict keys stringified, tuples emitted as lists — so exports are JSON-safe without `default=str`
- `TrafficDemand.to_dict()` is the canonical serialized demand form used by the results snapshot and by step `base_demands` output, which now include `group_mode` and `attrs`. Demand configs round-trip it: preset names and ints coerce to the enum, and a config without `mode` now means `combine` rather than `pairwise`
- Scenario snapshots serialize demand `flow_policy` as the preset name (e.g. `SHORTEST_PATHS_ECMP`) instead of an integer
- Invalid `mode` strings raise instead of silently selecting pairwise; parsing is case-insensitive
- FailureManager pre-builds per-run analysis inputs through a `prepare_inputs` hook on the analysis function, replacing kwarg-name sniffing in the engine. Custom functions opt in by setting the attribute; passing `context` explicitly skips the hook
- `run_monte_carlo_analysis` metadata includes `occurrence_counts` aligned with `results`, so custom result types carry correct pattern multiplicities. Deduplication assumes a deterministic analysis function, and a failure trace describes its pattern's representative iteration
- Flow placement semantics are pinned and documented: `SHORTEST_PATHS_*` presets admit flow onto the cost-only shortest paths of the base topology and drop the overflow (IGP semantics); `TE_*` presets reroute onto residual-capacity paths
- Monte Carlo execution is thread-based throughout: nothing is pickled, so analysis functions defined in `__main__` or a notebook run at full parallelism instead of being forced serial
- `CostPower` no longer builds a `NetworkExplorer` internally; it reports aggregated capex and power even on networks that strict hardware validation would reject, and an O(nodes x links) scan is gone. Hardware validation remains available via `ngraph inspect`
- Importing `ngraph` installs no stdout handler and does not import `ngraph.cli`; the library attaches only a `NullHandler`, the CLI configures logging in `main()`, and console logs go to stderr
- `ngraph inspect` quiets the whole `ngraph` package logger while printing the hierarchy, so explorer logs no longer interleave with the table
- Validation moved to construction and parse boundaries: `FailureRule` and `TrafficDemand` validate their field vocabularies in `__post_init__`, failure-rule `match` blocks go through the shared `parse_match_spec`, and workflow steps validate `parallelism` and `mode` through shared helpers. Malformed DSL values (e.g. a non-dict child `attrs`) raise `ValueError` consistently across blueprint and nested node groups
- Performance: per-iteration work now happens once per run — demand expansion, node-ID resolution, the Monte Carlo dedup key, blueprint `params` resolution, the risk-group expansion index, and bound-context pair keys. Pairwise pseudo-attachment edges are built once per group member (O(G x members), previously O(G^2 x members)), and unbound contexts build the Core graph lazily
- Performance: weighted failure selection precomputes per-rule weight splits and selects via a heap, about 4x faster on 100k-candidate pools. `MaximumSupportedDemand` probes share one SPF DAG cache, cutting SPF runs from probes x sources to sources, and `k_shortest_paths` prunes per-pair runs by processing pairs in ascending cost order. Explorer, `ngraph inspect`, and capacity-envelope aggregation use single-pass scans
- Performance: `mode: random` failure selection uses a binomial draw on Python 3.12+, O(failures) instead of O(matched). Seeded RNG streams for that mode differ from previous versions on 3.12+; the distribution is unchanged

### Added

- Demands can be pinned to explicit routes with `static_paths`, modelling MPLS-style LSPs: one flow per route, and a route broken by a failure carries nothing instead of rerouting. A route is a list of node names or link ids (link ids pick a specific one of several parallel links). Requires `mode: pairwise` with selectors matching exactly one source and one target
- `AnalysisContext.sensitivity_with_flow`: max flow and edge sensitivity per group pair in a single pass, used by `sensitivity_analysis` and the sensitivity Monte Carlo path (results unchanged)
- `AnalysisContext.build_node_mask`/`build_edge_mask` as public methods, for analysis functions calling Core primitives directly
- `Scenario.run(step_hook=...)`: a callable returning a context manager entered around each step, used by the CLI `--profile` path
- `FailurePolicy.apply_failures_typed`, returning scope-typed failure sets (`apply_failures` remains as a merged-list wrapper), plus `prepare_weights`, `build_risk_group_index`, and the `prepared_rg_index` parameter on `apply_failures` for reuse across Monte Carlo iterations
- `build_demand_placement_inputs`, exported from `ngraph.analysis`; `demand_placement_analysis` accepts precomputed `expansion=` and `resolved_ids=`
- `TrafficDemand.to_dict()`, `Mode.from_string` in `ngraph.types`, and `link_path_key` in `ngraph.model.selectors` (the canonical "source|target" key used when path-matching links)
- Minimum `netgraph-core` raised to 0.8.0, which introduces the `FlowPolicy.set_static_paths` and `PredDAG.from_edges` APIs that pinned routes are built on, and whose max-flow completion phase makes `max_flow` return a true maximum (values can increase against 0.7.x)

### Removed

- **BREAKING**: failure-policy `expand_children`. Cascading a failed risk group to its children is inherent and always applied; scenarios using the key must drop it. It previously crashed when enabled and did nothing when disabled
- **BREAKING**: the inline-object `flow_policy` form in the scenario schema; use a preset name string
- `placement_rounds` from `demand_placement_analysis` and `FailureManager.run_demand_placement_monte_carlo`; it never affected placement, which the core engine handles internally
- `build_demand_context` from `ngraph.analysis`; use `build_demand_placement_inputs`, which also returns the expansion and resolved node IDs
- `Scenario.seed_manager`, `expand_templates` (use `expand_block`), `DemandSet.to_dict`, `FailurePatternResult`, and the `MIN_CAP`/`MIN_FLOW` constants
- `select_nodes`'s `excluded_nodes` parameter (analysis exclusions are applied through Core masks) and dict input to `flatten_risk_group_attrs`
- `NetworkExplorer.get_node_utilization`'s no-op `include_disabled` parameter and the always-False `NodeUtilization.disabled` field
- Dead `TrafficDemand.volume_placed` and `TrafficDemand.flow_policy_obj` fields; routing comes solely from the `flow_policy` preset
- The module-level `build_node_mask`/`build_edge_mask` functions from `ngraph.analysis`; use the `AnalysisContext` methods of the same name
- `cli` and `logging` from `ngraph.__all__`; both remain importable as explicit submodules

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
