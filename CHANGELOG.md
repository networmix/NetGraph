# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- Combine-mode demand expansion with overlapping source/target selections (including `per_group` and `group_pairwise`) no longer routes volume through a zero-cost pseudo-node bypass: shared nodes are excluded from the target side, so `demand_placement_analysis`, `TrafficMatrixPlacement`, and `MaximumSupportedDemand` report placement bounded by real network capacity. A source group left with no targets is skipped; a fully-overlapping `flatten`/`combine` demand fails with `No demands could be expanded`
- Fractional link and augmentation costs now raise `ValueError` naming the offending links when the analysis graph is built, instead of being silently truncated to int64 (which corrupted SPF, KSP, cost distributions, and max-flow results); `from_networkx` applies the same check to edge costs
- **BREAKING**: `MaxFlowResult.min_cut` (`max_flow_detailed` with `include_min_cut=True`) now returns a true minimum cut whose capacity equals the max flow, instead of all saturated edges; saturated-edge analysis remains available via `sensitivity()`
- Monte Carlo analysis with `seed=None` now falls back to the failure policy's own seed, restoring per-iteration variation (a seeded policy previously produced one identical failure pattern every iteration)
- Demand-placement Monte Carlo no longer crashes with `KeyError` when demand configs lack `id`; ids are derived deterministically from source/target/position
- `group_mode: per_group` now matches documented semantics: `combine` creates one demand per source group, `pairwise` pairs nodes within each same-label group, and volume is split evenly across groups so totals are conserved — except for the share of a skipped group (combine-mode overlap exclusion can empty a group's targets, and a pairwise label with no non-self pairs is skipped)
- Risk-group failure expansion is transitive and independent of which rule kind failed: exclusions now include members of nested (grandchild) risk groups, and members of a rule-failed group seed `expand_groups` the same way whether the failure came from an entity rule or a `risk_group` rule
- The disable cascade for `disabled: true` risk groups now runs after membership rules and `generate` blocks, so entities assigned to risk groups by those mechanisms are correctly disabled
- `membership`, `disabled`, and `generate` keys on nested risk-group `children` entries are now rejected (by the JSON schema at load and by the parser with `ValueError`) instead of being silently ignored; only top-level groups are registered in `network.risk_groups`, so define such groups at top level and reference them by name as children
- Link `expand:` blocks now substitute variables in every string field (nested `attrs`, `risk_groups`, selector `match` values), matching documented behavior, and match-only selectors with expand blocks are no longer silently ignored. A variable used as a whole-string value (e.g. a match condition `value: "${t}"`) keeps its native type, so selectors match numeric node/link attributes with `==`/`!=`/`in`/`not_in`; placeholders embedded in longer strings still interpolate as text, and a bare placeholder bound to a non-string variable used as a path selector raises `ValueError` instead of being silently stringified
- Blueprint instantiation paths are regex-escaped when building blueprint link selectors, so group names containing regex metacharacters no longer link sibling subtrees or silently drop links
- Blueprint `params` overrides with unknown subgroup prefixes or malformed keys raise `ValueError` instead of being silently ignored (nested blueprint params use the dict-valued `<group>.params` form), and subgroup names containing dots (e.g. `rack.a.count` for subgroup `rack.a`) now resolve by longest-`<group>.`-prefix match against literal blueprint subgroup names instead of failing with a contradictory "matches no node group" error; when one subgroup name is a dotted extension of another, the longest match wins deterministically
- `link_rules` entries now require `source` and `target` (enforced by schema and expansion), and non-list `node_rules`/`link_rules` sections raise `ValueError` instead of being silently skipped
- Failure modes with zero weight are never applied, and scenario loading rejects policies whose modes all have zero weight
- Unbound `AnalysisContext` flow methods (`max_flow`, `max_flow_detailed`, `sensitivity`) now honor custom augmentations passed to `analyze()`
- `k_shortest_paths` between multi-node groups merges results across all source/sink node pairs instead of returning KSP for only the single best pair, and returns a deterministic selection when equal-cost paths exceed `max_k` (structural tie-breaking, independent of `PYTHONHASHSEED`); `shortest_paths` output ordering is deterministic for equal-cost paths
- Bound pairwise analysis results for overlapping/empty pairs (`sensitivity`, `max_flow_detailed`, `sensitivity_with_flow`) no longer share a single mutable default object across pairs
- FailureManager's prepared-policy match cache verifies policy identity to avoid stale results after `id()` address reuse
- A `FailureRule` with a mistyped `scope` (e.g. `nodes`) now fails at construction instead of silently matching nothing; a bare-string `risk_groups:` value anywhere in the DSL now raises `ValueError` instead of silently expanding per character
- Weighted failure sampling (`weight_by`) computes selection keys in the log domain: very small weights (e.g. per-hour failure rates around 1e-5) previously underflowed to zero and silently inverted the selection bias toward lexicographically larger entity IDs
- Demand placement no longer reports phantom flow: an SPF-cached demand and a FlowPolicy-based demand sharing (source, destination, priority) produced colliding flow ids whose flows silently merged, so reported placement could exceed the network's min cut. Cached flow ids now live in a disjoint range, and two policy-based demands with the same triple are rejected with `ValueError`
- Demand-expansion pseudo endpoints can no longer merge silently: `group_pairwise` composed demand ids are injective, `expand_demands` rejects duplicate `TrafficDemand` ids, and a post-expansion check rejects any two expansions claiming the same pseudo endpoint (ids and group labels containing `|` can compose identically). Each such collision previously fused distinct demands' pseudo nodes, resurrecting the zero-cost bypass
- A risk group sharing its name with a node or link is excluded correctly under failure: `compute_exclusions` classifies failed entities by rule scope (via the new `apply_failures_typed`) instead of probing merged IDs against network collections
- Seeded Monte Carlo results are reproducible across identical scenario rebuilds: link IDs use a deterministic per-(source, target) sequence (`A|B|0`) instead of a random uuid suffix, whose rebuild-dependent sort order re-mapped seeded draws onto different parallel links; `add_link` now raises on id collisions (possible when node names contain `|`) and on re-adding a link, instead of silently overwriting
- `MaximumSupportedDemand` probes `alpha_min` before declaring infeasibility on downward bracket exhaustion (a large `alpha_start` could previously raise a false "No feasible alpha found")
- `NetworkExplorer` paths no longer truncate at hierarchy segments literally named `root`; the walk stops at the synthetic tree root by identity
- Loud errors replace silent corruption at validation boundaries: the analysis graph build rejects link capacities at or above the internal pseudo-edge capacity (1e15) and cost totals reaching 2^62 (accumulated path costs overflow the core's int64 arithmetic, verified against the C++ implementation); `max_flow_analysis`/`sensitivity_analysis` reject a bound context whose binding differs from the call arguments; `in`/`not_in` conditions require list values at parse time; `generate` blocks report unhashable `group_by` values and same-name renders from distinct values (e.g. int `1` vs str `"1"`) as `ValueError` naming the attribute; and a demand endpoint missing from a supplied analysis context reports the likely config/context mismatch instead of a raw `KeyError`
- Inline dict `flow_policy` values are rejected at scenario build time with a `ValueError` listing valid presets, instead of being accepted and crashing later in analysis; boolean `flow_policy` values (`true`/`false`) are likewise rejected instead of silently coercing to integer presets 1/0
- Duplicate effective workflow step names raise `ValueError` before execution instead of silently overwriting results; `Scenario.run()` validates step names up front
- Workflow metadata `seed_source`/`active_seed` now report the seed a step actually uses; steps constructed without their own seed record `seed_source: none`
- `TrafficMatrixPlacement` with `alpha_from_step` naming a missing or not-yet-run producer step raises a clear error pointing at the step
- `flatten_node_attrs`/`flatten_link_attrs` expose `risk_groups` as a sorted list, making `group_by` labels and comparisons deterministic
- `BuildGraph` no longer crashes with `TypeError` when node/link attrs collide with reserved keys (`disabled`, `id`, `capacity`, `cost`); reserved keys take precedence in the exported node-link graph
- `ngraph inspect --detail`: the "Top demands (by offered volume)" table is now actually sorted by demand volume
- `NetworkExplorer.get_bom_map` honors `include_root`, and a custom `root_label` no longer duplicates the root BOM under the empty-string key
- `ComponentsLibrary.from_yaml` treats an empty or null `components:` mapping as an empty library, and a warning is logged when a component definition contains an unrecognized `cost` key (the parser reads `capex`)
- `ngraph run --profile`: per-worker `.pstats` profiles are merged into step profiles again (glob fixed from `*_worker_*` to `*_thread_*`; the Workers column previously always showed `-`), and `NGRAPH_PROFILE_DIR` no longer leaks into the process environment — it is restored (or removed) after the run, preventing stale worker-thread profiling in later in-process runs
- `ngraph run --stdout` now emits pure JSON on stdout: status banners, the `--profile` performance report, and run error messages are written to stderr, so output is safe to pipe to `jq`
- `scenarios/backbone_clos.yml` failure rules now nest conditions/logic under `match:`; `make validate` also covers `*.yml` scenario files (previously silently skipped)
- Docs: accuracy pass over the reference and getting-started documentation — every Python example and YAML snippet executes against the current code, and the design reference's algorithm sections (SPF/max-flow/KSP pseudocode, complexity bounds, residual-arc semantics, constants) were verified line-by-line against the NetGraph-Core C++ sources. Corrected: an inverted `require_capacity` description; results file locations and export shapes; link-id format; membership/generate contracts; YAML anchor-merge behavior; invalid YAML in condition examples; a "circular hierarchy" example that did not actually fail; a NetworkX write-back example that could not run and mislabeled edges; unsupported max-flow complexity bounds; node/link rule `risk_groups` documented as additive when they replace; a `one_to_one` self-pair example that creates no links; a YAML selector whose escape sequence made it invalid; workflow step `parallelism` and the CLI profiling notes, which now say "worker threads" (not processes) to match thread-based execution; and the `Scenario.from_yaml` docstring, which now reflects the actual risk-group processing order (membership resolution before `generate` blocks, disabled-member cascade after both)

### Changed

- **BREAKING**: `from_networkx` `bidirectional` now defaults to `None` and is inferred from the graph type: undirected inputs produce antiparallel arc pairs per edge (preserving connectivity) instead of a single arbitrary arc; pass `bidirectional=False` to restore the old conversion
- Monte Carlo execution is thread-based throughout: nothing is pickled, so analysis functions defined in `__main__` or a notebook run at full parallelism instead of being forced serial
- `FailurePolicy.to_dict` now emits the scenario YAML failure-policy format (conditions/logic nested under `match`, `weight_by` included when set, no derived `seed` key) and round-trips through `build_failure_policy`; the exported `scenario.failures` snapshot shape changed accordingly
- Scenario results snapshot serializes demand `flow_policy` as the preset name string (e.g. `SHORTEST_PATHS_ECMP`) instead of a bare integer
- `Results.to_dict` recursively converts nested output: dict keys are stringified and tuples emitted as lists throughout, making exports JSON-safe without `default=str` fallbacks
- Invalid `mode` strings in `max_flow_analysis`, `sensitivity_analysis`, and `build_maxflow_context` raise `ValueError` instead of silently selecting pairwise; parsing is case-insensitive
- Selector evaluation (schema types, condition evaluation, node selection, attribute flattening) and `parse_match_spec` moved from `ngraph.dsl.selectors` to `ngraph.model.selectors`; the DSL module keeps YAML-facing parsing and re-exports all moved names, and the model layer no longer imports the DSL package at import time or runtime
- Validation is unified at construction and parse boundaries: failure-rule `match` blocks go through the shared `parse_match_spec`; `FailureRule` and `TrafficDemand` validate their field vocabularies in `__post_init__`, replacing scattered, partly missing checks during expansion and selection; workflow steps validate `parallelism`/`mode` through the shared helpers; and malformed DSL values (e.g. non-dict child `attrs`) raise `ValueError` consistently across blueprint and nested node groups
- FailureManager pre-builds per-run analysis inputs through a `prepare_inputs` hook carried by the built-in analysis functions, replacing kwarg-name sniffing in the engine; custom analysis functions opt in by setting the attribute, and passing `context` explicitly skips the hook
- `run_monte_carlo_analysis` metadata includes `occurrence_counts` aligned with `results`, so custom result types get correct pattern multiplicities; docs clarify that deduplication assumes deterministic analysis functions and that failure traces describe each pattern's representative iteration
- Demand placement semantics are documented and pinned: `SHORTEST_PATHS_*` presets admit flow onto the cost-only shortest paths of the base topology and drop overflow (IGP semantics), while `TE_*` presets reroute remaining volume onto residual-capacity paths
- `TrafficDemand.to_dict()` is the canonical serialized demand form used by the results snapshot and step `base_demands` outputs (now consistently including `group_mode` and `attrs`), and demand configs round-trip it faithfully: `flow_policy` preset names/ints are coerced to the enum and config defaults match `TrafficDemand`'s (a config without `mode` now means `combine`, previously `pairwise`)
- `AnalysisContext.build_node_mask`/`build_edge_mask` are public methods for custom analysis functions calling Core primitives directly, replacing both the private methods and the unused module-level wrappers
- `ngraph inspect` quiets the `ngraph` package logger (not just the CLI logger) while printing the network hierarchy, so explorer INFO logs no longer interleave with the table output
- Importing `ngraph` no longer installs a stdout stream handler or eagerly imports `ngraph.cli`: the library attaches only a `logging.NullHandler` (importing `ngraph.logging` has no other side effects), the CLI configures logging explicitly in `main()`, and console logs go to stderr
- `CostPower` no longer constructs a `NetworkExplorer` internally; it always completes and reports aggregated capex/power even on networks that strict hardware validation would reject (hardware validation remains available via NetworkStats/inspect), and an O(nodes x links) validation scan is gone
- Performance: work that used to repeat per iteration now happens once — bound flow calls precompute expected pair keys at bind time; demand expansion, node-ID resolution, the Monte Carlo dedup-key kwargs component, and blueprint `params` resolution are computed once per run; and FailureManager builds the risk-group expansion index once per manager. PAIRWISE pseudo-attachment edges are created once per group member (O(G x members) instead of O(G^2 x members)), and plain unbound contexts build the Core graph lazily on first use
- Performance: `mode: random` failure selection uses a binomial draw plus uniform sample on Python 3.12+ (O(failures) instead of O(matched)); seeded RNG streams for `mode: random` differ from previous versions on Python 3.12+ (distribution unchanged)
- Performance: NetworkExplorer hardware validation and `ngraph inspect` aggregation use single-pass O(V+E)/O(E) scans instead of per-entity link loops; CapacityEnvelope frequency aggregation uses `collections.Counter` (O(n) instead of O(n^2))
- Performance: `k_shortest_paths` between multi-node groups prunes per-pair KSP runs — pairs are processed in ascending shortest-cost order with early termination once the top-k result cannot change, instead of running KSP for every reachable node pair
- Performance: weighted-choice failure selection precomputes per-rule weight splits and selects via a heap (about 4x faster on 100k-candidate pools); `MaximumSupportedDemand` probes share one SPF DAG cache (SPF runs drop from probes x sources to sources); membership rules flatten entity attributes once instead of per rule; pairwise overlap checks reuse per-group sets; and `group_by` selection resolves attributes directly
- Internal: repeated logic across analysis, DSL, and workflow layers is consolidated behind shared helpers (selector resolution, sensitivity decoding, Monte Carlo result serialization, blueprint parent merging, membership matching), defensive `getattr`/log-swallowing patterns on typed objects are removed, and function-local imports are reserved for optional dependencies (the package layering policy is now documented in the design reference)

### Added

- `Scenario.run(step_hook=...)`: optional callable returning a context manager entered around each workflow step's execution; the CLI `--profile` path now drives execution through it instead of a hand-rolled loop
- `AnalysisContext.sensitivity_with_flow`: computes max flow and edge sensitivity per group pair in a single pass; `sensitivity_analysis` and the sensitivity Monte Carlo hot path use it (results unchanged)
- `build_demand_placement_inputs` helper, exported from `ngraph.analysis`; `demand_placement_analysis` accepts precomputed `expansion=`/`resolved_ids=`
- `FailurePolicy.build_risk_group_index` static method and the `prepared_rg_index` parameter on `apply_failures` for reuse across Monte Carlo iterations
- `Mode.from_string` in `ngraph.types` for validated, case-insensitive parsing of analysis mode strings
- `TrafficDemand.to_dict()` returning the canonical serialized demand form (flow policy as preset name)
- `link_path_key` in `ngraph.model.selectors`: the canonical "source|target" key used when path-matching links
- `netgraph-core` dependency floor raised to 0.7.0, the API family this release is developed and tested against; the previous 0.3.0 floor predated APIs the library now uses
- `FailurePolicy.apply_failures_typed` (scope-typed failure sets; `apply_failures` remains as a merged-list wrapper) and `FailurePolicy.prepare_weights` for reusing weighted-selection splits across Monte Carlo iterations

### Removed

- **BREAKING**: failure-policy `expand_children` flag (field, parser, schema, serialization); cascading a failed risk group to its children is inherent and always applied, and scenarios using the key must drop it (previously the flag crashed when enabled and had no effect when disabled)
- **BREAKING**: inline-object `flow_policy` form from the scenario schema; use a preset name string
- `placement_rounds` parameter from `demand_placement_analysis` and `FailureManager.run_demand_placement_monte_carlo` (it never affected placement; the core engine handles optimization internally)
- Dead `TrafficDemand.volume_placed` and `TrafficDemand.flow_policy_obj` fields; routing is selected solely via the `flow_policy` preset
- Unused `FailurePatternResult`, `DemandSet.to_dict`, `ngraph.types.MIN_CAP`/`MIN_FLOW` constants, and the scenario schema's unused `linkProperties` definition
- `NetworkExplorer.get_node_utilization` no-op `include_disabled` parameter and the always-False `NodeUtilization.disabled` field
- `cli` and `logging` from `ngraph.__all__` (both remain importable as explicit submodules)
- `build_demand_context` from `ngraph.analysis` (use `build_demand_placement_inputs`, which also returns the expansion and resolved node IDs)
- `select_nodes` `excluded_nodes` parameter (no production caller; analysis exclusions are applied via Core masks) and dict-input support from `flatten_risk_group_attrs` (all callers pass `RiskGroup` objects)
- Production-orphaned public API: `Scenario.seed_manager` property and `expand_templates` from `ngraph.dsl.expansion` (`expand_block` covers its use case)
- Dead code across the analysis, DSL, workflow, and CLI layers: write-only fields, unused parameters and branches, and test-only helpers that had leaked into production modules

### Deprecated

- `placement_rounds` on `MaximumSupportedDemand` and `TrafficMatrixPlacement` workflow steps: still accepted in YAML for backward compatibility but logs a warning, has no effect, and is no longer exported in result contexts

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
