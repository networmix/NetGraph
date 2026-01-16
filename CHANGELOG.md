# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
