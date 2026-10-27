# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.25.0] - 2026-10-25

### Added

- Routing domains (YAML `routing: {igp_domain, bgp_edge}`) and a WCMP controller let shortest-path WCMP demands toward BGP-edge routers share forwarding weights per demand set and destination. Set `wcmp_controller.scope` to `next_hop` (default), `group` (caps from declared `forwarding_groups` shares) or `all_routers`; results report the tables under `controller`.
- Failure states for placement: each failure case of a `TrafficMatrixPlacement` (or `PlacementQuery`) reports the requested `failure_states` (Python `states`): `converged` (the default: demands computed again on the failed network), `stale` (programs forwarded unchanged, so traffic reaching a failed element is lost) and `repair` (the surviving original routes). WCMP-controller demand sets accept failure policies, but under one, group scope that programs a router inside the IGP domain accepts only `stale`.
- `interaction: simultaneous` forwards every demand's program at once with lossy admission, sharing losses on common links; the default `ordered` places demands in priority order.
- `TunnelCountAnalysis` (YAML) and `tunnel_counts(prepared, TunnelCountQuery)`: for each tunnelled `CentralizedTE` demand and each tunnel count (and optionally `up_to`), one evaluation at a fixed `design_demand` and `offer`, reporting the tunnel plan (count, planned bandwidth, cost, headroom penalty), the largest lossless offer, what the offer delivers and loses, and `insufficient_resolution` when whole units are too coarse to size the live sources' tunnels (`TunnelCountRow`).
- `ngraph.hardware` (`hardware_inventory`, `HardwareInventory`, `HardwareUse`, `link_active`, `resolve_link_end`): the hardware inventory, the enabled-link rule and one link end's hardware.
- `ngraph.workflow.StepNeeds` and `ngraph.workflow.step_name`: a step's preparation needs and run name.
- Every field of `ngraph/schemas/results.json` has a description, and `docs/reference/results.md` documents every result field.

### Changed

- **BREAKING**: a link end's hardware `exclusive` and Python boolean flag arguments (including `NetworkExplorer.get_bom(include_disabled)`, `NetworkExplorer.print_tree(skip_leaves, detailed, include_disabled)` and `Network.find_links(any_direction)`) must be booleans; 0.24 read any value by truthiness, so `"false"` counted as true.
- **BREAKING**: a pairwise or group-pairwise volume is divided only among pairs that can carry traffic: node-to-itself pairs and same-label group pairs get no share, and a group or group pair that has only such pairs gives its share to the others (for one with only node-to-itself pairs, 0.24 dropped that share). A declaration with no eligible pair is reported whole as discarded; an empty selection keeps its discarded share.
- **BREAKING**: requires `netgraph-core` 0.12 (`>=0.12.0,<0.13`), the rebuilt engine; 0.24 runs on `netgraph-core` 0.10 and 0.11.
- **BREAKING**: inputs are rounded to whole units of `q` (`units: {resolution, precision}`; Python `UnitsSettings`, automatic by default), so answers can differ from 0.24. Delivered traffic, losses and link flows use units (multiply by `q`); inputs, offers, designs and `NetworkStats` capacities stay physical, and `units_report` gives `q`, rounding and missed precision targets.
- **BREAKING**: an analysis runs as `run(prepare(scenario))`, which returns a `RunResult`; `prepare` chooses `q` and builds the graph once, without changing the scenario. The library questions are `capacity`, `place`, `paths`, `edge_sensitivity` and `maximum_supported_demand`, with typed queries (`CapacityQuery`, `PlacementQuery`, `PathQuery`, `SensitivityQuery`, `MSDQuery`) and `FailureRequest` for failure cases.
- **BREAKING**: result shapes: each failure case holds one entry per failure state under `states` (capacity: `converged`; placement: its failure states), each analysis records its typed query as `query`, and each step result records it as its `question`.
- **BREAKING**: domain records (nodes, links, risk groups, components, selectors, failure and demand declarations, built-in workflow steps) are immutable; edit through `Network` methods such as `replace_node` and `replace_link`, or `dataclasses.replace`. Every input field is checked where its object is built, by the same rule in Python and YAML, and a refusal names the field and the value (for example, `attrs` must be finite JSON and patterns must compile).
- **BREAKING**: a link cost is an integer from 1 to below 2^62 (`Link.cost: int = 1`); YAML `cost: 1.0` stays valid and is stored as `1`, and exported graph costs and `NetworkStats` `min_cost`/`max_cost` are integers.
- **BREAKING**: `BuildGraphResult.link_count` is renamed `edge_count` (the exported graph's edges, two per link with reverse edges); `NetworkStatsResult.link_count` still counts links.
- **BREAKING**: a failure policy needs at least one mode with a positive weight (`FailurePolicy(modes=...)` is required), and a failure rule's `count` is at least 1; for no failures, give no policy.
- **BREAKING**: a YAML link whose source or target matches no node is refused at load.
- **BREAKING**: custom workflow steps implement `run(StepContext) -> StepOutput`, read earlier results (read-only) through `context.prior_results`, state what preparation must bind with `needs()`, and register custom result types with `register_result_exporter`.
- **BREAKING**: YAML demands and MaxFlow steps name a `preset` or a `model` instead of `flow_policy` and the MaxFlow flags `shortest_path`, `require_capacity` and `flow_placement` (a MaxFlow step with neither asks maximum flow, `TE_MAXFLOW_UNLIM`); demand `static_paths` become `routes`, `supports` and `weights`.
- **BREAKING**: step keys: `parallelism` is `workers`, `store_failure_patterns` is `failure_trace`, `include_flow_details` is `outputs.cost_distribution`, `include_min_cut` is `outputs.min_cut`, `include_used_edges` is replaced by `outputs.edge_flows`, MaximumSupportedDemand (MSD) `resolution` is `alpha_tolerance`, and `alpha_from_field` is gone.
- **BREAKING**: old spellings, overlapping source and destination sets (except a single node paired with itself), and nonpositive costs are refused.
- **BREAKING**: presets are native models: `TE_WCMP_UNLIM` is renamed `TE_MAXFLOW_UNLIM` (minimum-cost maximum flow), `SHORTEST_PATHS_WCMP` splits by link capacity on shortest paths, `SHORTEST_PATHS_MAXFLOW` is new, and `TE_ECMP_16_LSP` and `TE_ECMP_UP_TO_256_LSP` over combined sources treat the selected sources as one tunnel origin, reported as the row's `pool`. Equal splits place whole units, so answers can differ from 0.24 by whole units.
- **BREAKING**: MSD returns the largest tested feasible alpha (`alpha_feasible`), its probe history and a `search_status` instead of raising "No feasible alpha found" (now `none_feasible`); a probe whose traffic rounds to zero units is `below_resolution`, never feasible.
- **BREAKING**: `write_json` (and the CLI) writes JSON as one compact line (0.24 indented it; `jq .` shows it indented). `outputs.details` adds native per-source, per-tunnel, plan and call fields; cost reports, cuts and edge arrays are separate opt-in outputs.
- Workflow step names longer than 100 characters are refused in Python and YAML.
- Each input field accepts its built-in type or the NumPy scalar of the same kind; integers also accept exactly integral floats (`2.0`); booleans are never numbers.
- `NetworkStats` refuses an excluded node or link name the network does not have.
- Every YAML load refusal is a `ValueError` naming the field's path and raw value, and a workflow-step refusal also names the step. An explicit `null` means not given wherever the Python field accepts `None`.
- `ngraph inspect` exits 1 at load on an invalid demand or workflow selector pattern.
- A random failure rule draws one random number per matched entity, the same on every supported Python, so random draws on Python 3.12 and later differ from 0.24; choice-rule seeds are unchanged. Results record the runtime, seed and draw order.
- `workers: auto` uses every CPU for traffic-matrix placement too; 0.24 used one worker there unless the demand set used an LSP preset or Python was free-threaded.
- ECMP shortest-path demands in `combine` mode, which split their volume equally over several source nodes, now report what those equal shares actually deliver; 0.24 could report more than the shares carry. Under lossless admission a selected source whose route has zero capacity keeps its share, so it can stop admission for the whole demand.
- Shortest-path capacity between node groups keeps every selected source on its own shortest routes, so a grouped answer can be larger than 0.24's, which used one shortest-path tree for the whole group.
- A step with no failure policy counts its requested draws (`iterations`, 1 by default) in the baseline's `occurrences`; 0.24 recorded no draws.
- K-shortest paths can choose or order equal-cost paths differently at the `k` limit; parallel links remain separate paths unless `parallel_edges=False`.
- Preparation refusals name the workflow step, the demand, link or node, and the YAML location they refuse; 0.24 did not name the step.
- Nodes and links may reference a risk group declared only as a nested child; that group's failures and its ancestors' failures include the members without a duplicate top-level declaration. Nested declarations that reuse a name must be identical.
- `import ngraph` loads each module on first use; NetworkX loads only for `BuildGraph`.
- Step log lines and export type errors name the class by module (`ngraph.workflow.max_flow_step.MaxFlow`).
- `NetworkExplorer` and `CostPower` read one hardware inventory (`ngraph.hardware.hardware_inventory`); their capex and power totals are unchanged.
- Hardware is validated before any capacity or port check, and each refusal names its node or link end.
- `ngraph inspect` calls a link enabled only when it and both end nodes are enabled, as `NetworkStats` does.
- `ngraph inspect --detail` lists each set's first demands by their selector labels (`^A -> ^B`).
- `ngraph --help` and command-line errors no longer load the analysis engine.

### Removed

- **BREAKING**: `analyze`, `AnalysisContext` and `FailureManager`; use `prepare` with the library questions above and `FailureRequest`.
- **BREAKING**: `Scenario.run` and `Scenario.results`; use `run(prepare(scenario))`.
- **BREAKING**: `TrafficDemand` and `build_demand_set`; use `DemandSpec` and `DemandSet`.
- **BREAKING**: `MaxFlowResult`, `FlowEntry`, `FlowIterationResult`, `FlowSummary`, `CapacityEnvelope` and the result store `Results`; analyses return typed records holding native results.
- **BREAKING**: `FlowPlacement`, `EdgeSelect`, `Mode`, `EdgeRef` and `Path`; use presets or native models, `DirectedLink` and `PathQuery`.
- **BREAKING**: `from_networkx`, `to_networkx`, `NodeMap` and `EdgeMap`; `BuildGraph` exports node-link JSON.
- **BREAKING**: the modules `ngraph.types`, `ngraph.lib` (with `ngraph.lib.nx`), `ngraph.model.flow`, `ngraph.model.path`, `ngraph.dsl.selectors` (`normalize_selector` is in `ngraph.model.selectors`), `ngraph.utils.ids`, `ngraph.analysis.context`, `ngraph.analysis.demand`, `ngraph.analysis.functions`, `ngraph.analysis.failure_manager` and `ngraph.analysis.static_paths`, and the submodules of `ngraph.results`, `ngraph.model.demand` and `ngraph.model.failure`, which are single modules now.
- `FailurePolicySet`, `build_failure_policy` and `build_failure_policy_set`; use the `Scenario.failure_policies` mapping of `FailurePolicy` values.
- `ngraph.model.components.resolve_link_end_components`; use `ngraph.hardware.hardware_inventory` or `ngraph.hardware.resolve_link_end` for one end.
- `validate_risk_group_hierarchy` and `validate_risk_group_references`; `prepare` validates risk groups.
- `NetworkExplorer.get_bom_by_path` and `get_bom_map`; use `get_bom` or a tree node's `stats.bom`.
- Worker profiles of `run --profile` (`NGRAPH_PROFILE_DIR`, the `<scenario>.profiles` directory, `PerformanceProfiler.merge_child_profiles`, `StepProfile.worker_profiles_merged`) and `PerformanceProfiler.get_top_functions`/`save_detailed_profile`; the report covers the main process.
- `ngraph.logging.reset_logging`, `ngraph.utils.output_paths.profiles_dir_for_run` and `ngraph.utils.ids.new_base64_uuid`.

### Fixed

- Ordering conditions compare integers exactly; 0.24 compared floats, so `2**53 + 1 > 2**53` was false and integers above the float range crashed.
- Hardware totals too large for a finite float are refused, naming the entity and field; 0.24 wrote them as infinity: `Infinity` in the results file (not valid JSON) and `inf` in `ngraph inspect`.
- Hardware component `count` multiplies both the ports a platform offers and the ports a link-end component uses, as it does for capacity, capex and power.
- Weighted failure modes and weighted choices follow their weights when the total weight overflows or a weight is subnormal; 0.24 picked the last mode or fell back to name order.
- `ngraph inspect` previews selectors as analyses select: attribute conditions and `group_by` apply, and selectors sharing a path are listed apart; 0.24 matched and merged them as node-name patterns.
- The `--profile` report's CPU time is each step's process CPU time, all threads and native code included (0.24 showed the profiled wall time), and its advice for CPU-intensive steps no longer suggests parallelization.
- A `hardware` value that is not a mapping, on a node, a link or a link end, is refused; 0.24 crashed or ignored it. `CostPower` also refuses an invalid hardware `count` on a disabled link or a link to a disabled node, and a count too large for a float is a `ValueError` (was `OverflowError`).
- The explorer counts both optic ends of a self-loop as used ports, so a node without the ports is refused.
- The bundled NSFNET scenario now follows Merit's 1992 T3 map and May 1992 node list, so its results differ throughout from 0.24.1; see [the scenario](scenarios/nsfnet.yaml) for sites, circuits and units. Sites are `core/<city>` and `end/<place>`, the new `single_connection_failure` step fails one core connection per draw, and `availability_1992` is renamed `assumed_random_failures` because its failure rates are assumptions.

## [0.24.1] - 2026-10-24

### Fixed

- `netgraph-core` is required below 0.12 (`>=0.10.0,<0.12`): netgraph-core 0.12 changes the engine API that NetGraph 0.24 calls, so an unbounded upgrade would break it. NetGraph 0.25 runs on netgraph-core 0.12

## [0.24.0] - 2026-10-02

### Fixed

- Bill-of-materials counts for `exclusive: true` link ends round up as documented (a fractional count was truncated, so an exclusive half optic counted as none)
- `ngraph inspect --detail` shows enum step parameters by name (`PROPORTIONAL`, not `1`)
- `ngraph inspect` reports errors on stderr, as `run` does

### Removed

- **BREAKING**: `placement_rounds` (`MaximumSupportedDemand`, `TrafficMatrixPlacement`) and `acceptance_rule` (`MaximumSupportedDemand`)
- **BREAKING**: integer, numeric-string and blank `flow_policy` values; use the preset name
- **BREAKING**: `ngraph.dsl.selectors` re-exports; import selector types and evaluation from `ngraph.model.selectors`
- **BREAKING**: `edge_select` on `shortest_path_cost` and `k_shortest_paths`, where it had no effect
- **BREAKING**: `include_flow_summary` on `FailureManager.run_max_flow_monte_carlo`; use `include_flow_details`
- **BREAKING**: `CapacityEnvelope` flow-summary aggregation (`from_values(flow_summaries=...)`, `flow_summary_stats`), which nothing produced
- `serialize_policy_preset`, `DemandSet.get_default_set` and `FailureManager.run_single_failure_scenario`
- `enable_debug_logging`/`disable_debug_logging`; use `set_global_log_level`
- `expand_demands(default_policy_preset=...)`; unset presets use `DEFAULT_PRESET`
- Re-exports `ngraph.analysis.LARGE_CAPACITY` and `ngraph.dsl.blueprints.parser.expand_name_patterns`; `check_no_extra_keys` moved to `ngraph.utils.yaml_utils`
- The always-true third element of `resolve_link_end_components`, and `ngraph inspect --output`
- Result fields without information: workflow `active_seed` (equal to `step_seed`), MSD context `acceptance_rule`, failure-trace `expansion.risk_groups`
- The implicit `type: node` attribute on YAML-defined nodes

### Changed

Inputs that were silently ignored or replaced now raise, `ValueError` unless noted.

- Unknown keys in any scenario builder, from demands and failure policies to selectors, components and workflow steps
- `mode` on a bound `AnalysisContext` call, or on `analyze()`/`from_network()` without `source` and `sink`
- `alpha` together with `alpha_from_step` on `TrafficMatrixPlacement`; `alpha` defaults to 1.0
- A `parallelism` that is not an integer or `"auto"` (floats were truncated)
- A hardware `count` that is not a finite positive number (it became 1)
- Duplicate top-level risk-group names (the last one silently won)
- An unbound `context` passed to `max_flow_analysis` or `sensitivity_analysis`
- A `run_demand_placement_monte_carlo` input that is not a list of demand configs or a `DemandSet` (`TypeError`)
- A non-`FlowPolicyPreset` `TrafficDemand.flow_policy`, and a `to_networkx` node map missing an index (`KeyError`)
- CLI: an unknown `--keys` step, `--profile-memory` without `--profile`, and non-JSON results (were stringified)

Other changes.

- **BREAKING**: selector contexts follow the DSL sections: `link` and `rule` replace `adjacency` and `override`
- Monte Carlo keeps `None` results from custom analysis functions in `results`
- `PerformanceProfiler.save_detailed_profile` requires `step_name`
- Dependencies: `pandas` dropped, `numpy` declared; dev extras drop pytest-benchmark, pytest-mock, pdoc and pandas-stubs
- Bundled `TrafficMatrixPlacement` scenarios use `parallelism: auto`
- Internal: removed impossible-state fallbacks, required-import guards, test-only helpers and unused test scaffolding

## [0.23.1] - 2026-09-13

### Changed

- Minimum `netgraph-core` raised to 0.10.0. Core's `EQUAL_BALANCED` now keeps every next hop with capacity in the split, the load-blind behaviour that 0.23.0 obtained from a separate Core mode, and that mode is gone. `SHORTEST_PATHS_ECMP` and the `TE_ECMP_*` presets place exactly as in 0.23.0. The one difference is `max_flow` with `flow_placement=EQUAL_BALANCED`, `shortest_path=False` and `require_capacity=False`: it filled the cost-only DAG in several passes and now places once, the single-pass answer that cost-only routing is documented to give. Use `require_capacity=True` for the residual-aware fill

## [0.23.0] - 2026-09-13

### Fixed

Placement results that were wrong in plausible scenarios. Re-run analyses that used these configurations.

- Combine mode with a `SHORTEST_PATHS_*` preset routed the whole demand from the pseudo source, so only the sources nearest the targets carried traffic and the equal hash across sources let one small source scale the rest down. The pseudo source is now a pool: every source that can reach a target originates an even share, routed to its nearest targets over a DAG built by Core's new reverse SPF. Under `SHORTEST_PATHS_ECMP` the pool is admitted as one demand at a single lossless scale (two equal-cost sources of capacity 100 and 10 admit 20 of 110; `SHORTEST_PATHS_ECMP_LOSSY` delivers 65). `TE_*` presets keep letting capacity decide which sources originate. A fixed per-source matrix is `group_mode: per_group` with `group_by: name`, or `pairwise`
- `SHORTEST_PATHS_ECMP` skipped next hops filled by earlier demands, overstating lossless capacity. It now models a load-blind forwarding table: a filled next hop blocks later demands hashed onto it (Core placement `EQUAL_BALANCED_FIXED`)
- `TE_WCMP_UNLIM` stopped rerouting after 100 cost tiers and dropped the remainder silently. The loop is now bounded by the edge count
- `MaximumSupportedDemand` failed with "No feasible alpha found" for LSP presets over many small demands. Core never places less than 1/4096 on a flow, so those demands were always short by a fraction of that. Feasible now means every demand is placed to within that resolution and none placed nothing; the failure message reports the best ratio seen
- `create_flow_policy` left Core's `require_capacity` at its default for the `SHORTEST_PATHS_*` presets, so a FlowPolicy built from an IGP preset selected paths with residual awareness and the WCMP one rerouted. Both engines now read one `preset_config`, and a hop-by-hop FlowPolicy places exactly what the cached engine places

### Changed

- `TrafficMatrixPlacement` resolves `parallelism: auto` to 1 unless the demand set uses an LSP preset or the interpreter is free-threaded. Iterations for the other presets are Python-bound between short engine calls, and the CPU-count default made Monte Carlo about 2x slower than serial. Explicit worker counts are unchanged
- Minimum `netgraph-core` raised to 0.9.0 (new placement modes, per-link drop reporting, reverse SPF)
- Documentation describes placement as greedy and sequential: priority order, input order within a priority, order-dependent totals under contention

### Added

- `SHORTEST_PATHS_ECMP_LOSSY` preset: hop-by-hop ECMP forwarded best-effort. Every link carries what fits and drops the rest, `placed` is the delivered volume, and with `include_flow_details` each entry reports `dropped_edges`, the lost volume per link. On a 100/10 parallel pair offered 100 units, `SHORTEST_PATHS_ECMP` admits 20 and the lossy preset delivers 60
- `ngraph.model.flow.policy_config.preset_config` and `HOP_BY_HOP_PRESETS`; `PlacementSummary.max_shortfall` and `unserved_demands`; `resolve_placement_parallelism`

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
