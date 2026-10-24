<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

Every public module, class and function, generated from the docstrings.
The [API guide](api.md) covers the same API with examples.

Quick links:

- [API Guide](api.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Modules auto-discovered: 54

---

## ngraph.cli

Command-line interface for NetGraph.

### main(argv: 'Optional[List[str]]' = None) -> 'None'

Entry point for the ``ngraph`` command.

Prints help and exits with status 0 when no arguments are given.

Args:
    argv: Arguments without the program name. If ``None``,
        ``sys.argv[1:]`` is used.

---

## ngraph.explorer

Hierarchical exploration of a Network.

Builds a tree of the node-name hierarchy and aggregates per-subtree
statistics in two modes (all nodes, and enabled nodes only): node and link
counts, capacity, capex/power, and hardware bills of materials (BOM).

### ExternalLinkBreakdown

Stats for external links to one other subtree.

Attributes:
    link_count (int): Number of links to that other subtree.
    link_capacity (float): Sum of capacities for those links.

**Attributes:**

- `link_count` (int) = 0
- `link_capacity` (float) = 0.0

### LinkCapacityIssue

A link capacity constraint violation in active topology.

Attributes:
    source: Source node name.
    target: Target node name.
    capacity: Configured link capacity.
    limit: Effective capacity limit from per-end hardware (min of ends).
    reason: Machine-readable tag, e.g. ``link_capacity_exceeds_end_hw``.

**Attributes:**

- `source` (str)
- `target` (str)
- `capacity` (float)
- `limit` (float)
- `reason` (str)

### NetworkExplorer

Hierarchical view of a Network with per-subtree statistics.

Statistics are computed in two modes: 'all' (disabled nodes and links
included) and 'active' (enabled only).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None, strict_validation: 'bool' = True) -> 'NetworkExplorer'` - Build the hierarchy tree and compute 'all' and 'active' statistics.
- `get_bom(self, include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return aggregated hardware BOM for the whole network.
- `get_bom_map(self, include_disabled: 'bool' = True, include_root: 'bool' = True, root_label: 'str' = '') -> 'Dict[str, Dict[str, float]]'` - Return a mapping from hierarchy path to BOM for each subtree.
- `get_link_issues(self) -> 'List[LinkCapacityIssue]'` - Return link capacity violations recorded in non-strict mode.
- `get_node_utilization(self) -> 'List[NodeUtilization]'` - Return hardware utilization per node based on active topology.
- `print_tree(self, node: 'Optional[TreeNode]' = None, indent: 'int' = 0, max_depth: 'Optional[int]' = None, skip_leaves: 'bool' = False, detailed: 'bool' = False, include_disabled: 'bool' = True, max_external_lines: 'Optional[int]' = None, line_prefix: 'str' = '') -> 'None'` - Print the hierarchy from 'node' down (default: root).

### NodeUtilization

Per-node hardware utilization snapshot based on active topology.

Attributes:
    node_name: Fully qualified node name.
    component_name: Hardware component name if present.
    hw_count: Hardware multiplicity used for capacity/power scaling.
    capacity_supported: Total capacity supported by node hardware.
    attached_capacity_active: Sum of capacities of enabled adjacent links where the
        opposite endpoint is also enabled.
    capacity_utilization: Ratio of attached to supported capacity (0.0 when N/A).
    ports_available: Total port equivalents available on the node (0.0 when N/A).
    ports_used: Sum of port equivalents used by per-end link optics attached to this
        node on active links.
    ports_utilization: Ratio of used to available ports (0.0 when N/A).
    capacity_violation: True if attached capacity exceeds supported capacity.
    ports_violation: True if used ports exceed available ports.

**Attributes:**

- `node_name` (str)
- `component_name` (Optional[str])
- `hw_count` (float)
- `capacity_supported` (float)
- `attached_capacity_active` (float)
- `capacity_utilization` (float)
- `ports_available` (float)
- `ports_used` (float)
- `ports_utilization` (float)
- `capacity_violation` (bool)
- `ports_violation` (bool)

### TreeNode

A node in the hierarchical tree.

Attributes:
    name (str): Hierarchy segment, e.g. "plane1" in "dc1/plane1/ssw".
    parent (Optional[TreeNode]): Parent tree node; None for the root.
    children (Dict[str, TreeNode]): Mapping of child name -> child TreeNode.
    subtree_nodes (Set[str]): Node names in the subtree, disabled included.
    active_subtree_nodes (Set[str]): Node names in the subtree (only enabled).
    stats (TreeStats): Aggregated stats for "all" view.
    active_stats (TreeStats): Aggregated stats for "active" (only enabled) view.
    raw_nodes (List[Node]): Network nodes whose full name ends at this tree node.

**Attributes:**

- `name` (str)
- `parent` (Optional[TreeNode])
- `children` (Dict[str, TreeNode]) = {}
- `subtree_nodes` (Set[str]) = set()
- `active_subtree_nodes` (Set[str]) = set()
- `stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={})
- `active_stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={})
- `raw_nodes` (List[Node]) = []

**Methods:**

- `add_child(self, child_name: 'str') -> 'TreeNode'` - Return the child named ``child_name``, creating it if missing.
- `is_leaf(self) -> 'bool'` - Return True if this node has no children.

### TreeStats

Aggregated statistics for a single tree node (subtree).

Attributes:
    node_count (int): Total number of nodes in this subtree.
    internal_link_count (int): Number of internal links in this subtree.
    internal_link_capacity (float): Sum of capacities for those internal links.
    external_link_count (int): Number of external links from this subtree to another.
    external_link_capacity (float): Sum of capacities for those external links.
    external_link_details (Dict[str, ExternalLinkBreakdown]): Breakdown by other subtree path.
    total_capex (float): Total capex (nodes + links).
    total_power (float): Total power (nodes + links).
    bom (Dict[str, float]): Hardware count per component name. Shared
        optics can add fractional counts.

**Attributes:**

- `node_count` (int) = 0
- `internal_link_count` (int) = 0
- `internal_link_capacity` (float) = 0.0
- `external_link_count` (int) = 0
- `external_link_capacity` (float) = 0.0
- `external_link_details` (Dict[str, ExternalLinkBreakdown]) = {}
- `total_capex` (float) = 0.0
- `total_power` (float) = 0.0
- `bom` (Dict[str, float]) = {}

---

## ngraph.export

One exact-type result exporter registry and JSON output boundary.

A plain record is written as its declared class constants and fields, in
declaration order, by one walk over an explicit set of record types.
Native results, rows, failure cases, paths, sensitivity, the analysis
envelopes and the recorded questions have explicit encoders.

### is_question(value: 'object') -> 'bool'

Whether a step may record this value as its question.

### owned_step_result(value: 'object') -> 'object'

Publish a step result without running its encoder.

NetGraph's records are immutable and finite JSON is frozen. A registered
result type is published as it is, with any native values it holds; its
own type decides whether a later step can change it.

### project(value: 'object') -> 'JSONValue'

Write a plain record, its exact field values and finite JSON data.

### question(value, prepared: 'PreparedScenario')

Write a recorded question.

### register_result_exporter(result_type: 'type[ExportT]', encoder: 'Callable[[ExportT, ExportContext], JSONValue]') -> 'None'

Register one explicit encoder for exactly this result type.

### write_json(result: 'RunResult | AnalysisResult', file: 'IO[str]') -> 'None'

Project once and encode before writing, so encoder errors write nothing.

---

## ngraph.logging

Logging configuration for NetGraph.

Follows the standard library pattern: importing the package attaches only a
``logging.NullHandler`` to the root ``ngraph`` logger and never installs
stream handlers or sets levels. Applications opt into console output by
calling ``setup_root_logger()`` explicitly, or implicitly via
``set_global_log_level()``. The CLI does both in ``main()``: it calls
``setup_root_logger()`` first, then sets the level from
``--verbose``/``--quiet``.

### get_logger(name: str) -> logging.Logger

Get a logger under NetGraph's logging hierarchy.

Use this everywhere in the package. It configures nothing: handlers and
levels are inherited from the root 'ngraph' logger, which is configured
only when an application calls setup_root_logger() (directly or via
set_global_log_level()).

Args:
    name: Logger name (typically __name__ from calling module).

Returns:
    Logger instance inheriting from the root ngraph logger.

### set_global_log_level(level: int) -> None

Set the log level for all NetGraph loggers.

Installs the default console handler via setup_root_logger() if logging
has not been configured yet. Intended for applications (e.g. the CLI);
library code never calls this implicitly.

Args:
    level: Logging level (e.g., logging.DEBUG, logging.INFO).

### setup_root_logger(level: int = 20, format_string: str | None = None, handler: logging.Handler | None = None) -> None

Set up the root NetGraph logger with a single handler.

Subsequent calls leave the existing handlers in place.

Args:
    level: Logging level (default: INFO).
    format_string: Custom format string (optional).
    handler: Custom handler (optional, defaults to StreamHandler(sys.stderr)).

---

## ngraph.results

Owned analysis envelopes, exact reports and normalized questions.

Computational results remain native values with their native lifetime and fields.

### AnalysisMetadata

Immutable AnalysisMetadata record.

**Attributes:**

- `workers` (int)
- `sampling` (SamplingMetadata | None)

### BuildGraphResult

Immutable BuildGraphResult record.

**Attributes:**

- `kind` (ClassVar[Literal['build_graph']]) = build_graph
- `add_reverse` (bool)
- `node_count` (int)
- `link_count` (int)
- `graph` (Mapping[str, JSONValue])

### CapacityAnalysis

Immutable CapacityAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['capacity']]) = capacity
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `question` (Literal['lossless_bound', 'fixed_offer_delivery', 'first_hop_experiment'])
- `offer_source` (Literal['unlimited', 'explicit', 'design', 'first_hop'])
- `cases` (tuple[CaseResult[CapacityRow | SelfPair], ...])
- `query` (CapacityQuery)

### CapacityRow

Immutable CapacityRow record.

**Attributes:**

- `id` (str)
- `endpoints` (Endpoints)
- `result` (ngc.PlacementResult)
- `pool` (PoolMetadata | None)
- `cost_distribution` (CostReport | None)
- `unavailable_outputs` (Mapping[Literal['cost_distribution'], CostUnavailableReason])

### CaseResult

Immutable CaseResult record.

**Attributes:**

- `case` (FailureCase)
- `states` (Mapping[StateName, CaseState[RowT]])

### CaseState

One state of a case: its rows and totals, or its forwarding failure.

``dead_caps`` lists the dead root groups of a group-scope demand set in the
converged and repair states; it is None elsewhere.

**Attributes:**

- `rows` (tuple[RowT, ...])
- `totals` (PlacementTotals | None)
- `failure` (ForwardingFailure | None)
- `dead_caps` (tuple[DeadCap, ...] | None)

### CostPowerResult

Immutable CostPowerResult record.

**Attributes:**

- `kind` (ClassVar[Literal['cost_power']]) = cost_power
- `include_disabled` (bool)
- `aggregation_level` (int)
- `levels` (Mapping[int, tuple[HardwareRow, ...]])

### DeadCap

A declared root group with no live member in a case, and its fixed cap.

Its traffic is dropped at its router; ``group`` is its index in the tree.

**Attributes:**

- `destination` (str)
- `router` (str)
- `forwarding_group` (str)
- `group` (int)
- `cap` (Fraction)

### DeliveredByPathCost

Immutable DeliveredByPathCost record.

**Attributes:**

- `kind` (ClassVar[Literal['delivered_by_path_cost']]) = delivered_by_path_cost
- `cost_domain` (Literal['physical_network', 'analysis_graph'])
- `bins` (tuple[PathCostBin, ...])

### DiscardedShare

Immutable DiscardedShare record.

**Attributes:**

- `label` (str)
- `units` (int)
- `reason` (Literal['self_pair', 'filtered', 'empty_selection'])

### Endpoints

Immutable Endpoints record.

**Attributes:**

- `sources` (tuple[str, ...])
- `destinations` (tuple[str, ...])

### ExactAlpha

Immutable ExactAlpha record.

**Attributes:**

- `value` (Annotated[float, {'exclusiveMinimum': 0}])
- `numerator` (int)
- `denominator` (Annotated[int, {'minimum': 1}])

### ExpansionAccounting

Immutable ExpansionAccounting record.

**Attributes:**

- `base_id` (str)
- `declared_units` (int)
- `resolved_units` (int)
- `discarded_units` (int)
- `discards` (tuple[DiscardedShare, ...])

### ExpansionLeaf

Immutable ExpansionLeaf record.

**Attributes:**

- `id` (str)
- `order` (int)
- `endpoints` (Endpoints | None)
- `discard_reason` (Literal['self_pair', 'filtered', 'empty_selection'] | None)

### ExpansionParent

One declared demand: its declaration and its expansion tree.

``config`` is the native configuration of its first resolved leaf (None
when every leaf of a named pinned declaration was discarded).

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `priority` (int)
- `policy` (DemandPolicy)
- `config` (ngc.FlowPolicyConfig | None)
- `base_id` (str)
- `declaration_ordinal` (int)
- `expand_leaf_index` (int | None)
- `physical_volume` (float)
- `mode` (Literal['combine', 'pairwise'])
- `group_mode` (Literal['flatten', 'per_group', 'group_pairwise'])
- `root` (ExpansionSplit | ExpansionLeaf)

### ExpansionSplit

Immutable ExpansionSplit record.

**Attributes:**

- `label` (str)
- `children` (tuple[ExpansionSplit | ExpansionLeaf, ...])

### ExportContext

Immutable ExportContext record.

**Attributes:**

- `prepared` (PreparedScenario)
- `units_report` (UnitsReport)

### FailureCase

Immutable FailureCase record.

**Attributes:**

- `id` (str)
- `kind` (Literal['baseline', 'failure'])
- `pattern` (FailurePattern)
- `occurrences` (int)
- `eligibility` (ngc.Eligibility)
- `trace` (FailureTrace | None)

### FailurePattern

Canonical failure mask used as a scheduling and sampling key.

**Attributes:**

- `excluded_nodes` (tuple[str, ...])
- `excluded_links` (tuple[str, ...])

### FailureSelection

Immutable FailureSelection record.

**Attributes:**

- `rule_index` (int)
- `scope` (Literal['node', 'link', 'risk_group'])
- `selected` (tuple[str, ...])

### FailureTrace

Immutable FailureTrace record.

**Attributes:**

- `draw_index` (int)
- `mode_index` (int | None)
- `mode_attrs` (Mapping[str, JSONValue])
- `selections` (tuple[FailureSelection, ...])
- `expanded_nodes` (tuple[str, ...])
- `expanded_links` (tuple[str, ...])

### ForwardingFailure

Native lossy forwarding found no fixed point for this case and state.

**Attributes:**

- `kind` (ClassVar[Literal['loss_iteration']]) = loss_iteration
- `message` (str)

### HardwareRow

Immutable HardwareRow record.

**Attributes:**

- `path` (str)
- `platform_capex` (float)
- `platform_power_watts` (float)
- `optics_capex` (float)
- `optics_power_watts` (float)
- `capex_total` (float)
- `power_total_watts` (float)

### InputConstraint

Immutable InputConstraint record.

**Attributes:**

- `kind` (ClassVar[Literal['input']]) = input
- `label` (str)
- `q_upper_bound` (Fraction)
- `met` (bool)

### InputQuantization

Immutable InputQuantization record.

**Attributes:**

- `label` (str)
- `kind` (Literal['capacity', 'demand', 'offer', 'design', 'min_unreserved'])
- `binary64_value` (float)
- `binary64_hex` (str)
- `units` (int)
- `error` (Fraction)
- `relative_error` (Fraction | None)

### MSDAnalysis

Immutable MSDAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['msd']]) = msd
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `alpha_feasible` (ExactAlpha | None)
- `best_probe_index` (int | None)
- `monotone_proven` (bool)
- `proof` (MSDProof)
- `upper_certificate` (UpperCertificate | None)
- `search_status` (MSDStatus)
- `stop_reason` (MSDStopReason)
- `history` (tuple[MSDProbe, ...])
- `query` (MSDQuery)
- `best_rows` (tuple[PlacementRow, ...] | None)
- `best_accounting` (tuple[ExpansionAccounting, ...] | None)
- `probe_rows` (Mapping[int, tuple[PlacementRow, ...]] | None)

### MSDProbe

Immutable MSDProbe record.

**Attributes:**

- `index` (int)
- `alpha` (ExactAlpha)
- `outcome` (Literal['feasible', 'infeasible', 'below_resolution', 'range'])
- `totals` (PlacementTotals | None)
- `range_refusal` (RangeRefusal | None)

### MarginalCostBin

Immutable MarginalCostBin record.

**Attributes:**

- `marginal_cost` (int)
- `units` (int)

### MarginalCurve

Immutable MarginalCurve record.

**Attributes:**

- `kind` (ClassVar[Literal['marginal_curve']]) = marginal_curve
- `cost_domain` (Literal['physical_network', 'analysis_graph'])
- `bins` (tuple[MarginalCostBin, ...])

### MemberWeight

One member of a programmed router and its integer weight (0 included).

**Attributes:**

- `edge` (DirectedLink)
- `weight` (int)

### NetworkStatsResult

Immutable NetworkStatsResult record.

**Attributes:**

- `kind` (ClassVar[Literal['network_stats']]) = network_stats
- `node_count` (int)
- `link_count` (int)
- `total_capacity` (float)
- `mean_capacity` (float)
- `median_capacity` (float)
- `min_capacity` (float)
- `max_capacity` (float)
- `mean_cost` (float)
- `median_cost` (float)
- `min_cost` (float)
- `max_cost` (float)
- `mean_degree` (float)
- `median_degree` (float)
- `min_degree` (float)
- `max_degree` (float)

### OutputSelection

Immutable OutputSelection record.

**Attributes:**

- `native` (ngc.OutputOptions)
- `cost_distribution` (bool)
- `details` (bool) = False

### PathAnalysis

Immutable PathAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['paths']]) = paths
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `algorithm` (Literal['spf', 'ksp'])
- `mode` (Literal['combine', 'pairwise'])
- `costs_only` (bool)
- `rows` (tuple[PathRow, ...])
- `query` (PathQuery)

### PathCostBin

Immutable PathCostBin record.

**Attributes:**

- `cost` (int)
- `physical_path_cost` (int)
- `delivered_units` (int)

### PathRow

Immutable PathRow record.

**Attributes:**

- `id` (str)
- `endpoints` (Endpoints)
- `kind` (Literal['paths', 'self'])
- `cost` (int | None)
- `paths` (tuple[ngc.Path, ...] | None)

### PlacementAnalysis

Immutable PlacementAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['placement']]) = placement
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `alpha` (ExactAlpha)
- `cases` (tuple[CaseResult[PlacementRow], ...])
- `accounting` (tuple[ExpansionAccounting, ...])
- `query` (PlacementQuery)

### PlacementRow

Immutable PlacementRow record.

**Attributes:**

- `id` (str)
- `base_id` (str)
- `endpoints` (Endpoints)
- `reference_request_units` (int)
- `result` (ngc.PlacementResult)
- `pool` (PoolMetadata | None)
- `cost_distribution` (CostReport | None)
- `unavailable_outputs` (Mapping[Literal['cost_distribution'], CostUnavailableReason])

### PlacementTotals

Immutable PlacementTotals record.

**Attributes:**

- `reference_request_units` (int)
- `delivered_units` (int)
- `unadmitted_units` (int)
- `source_drop_units` (int)
- `edge_drop_units` (int)
- `reference_shortfall_units` (int)
- `delivery_ratio` (Fraction)
- `feasible` (bool)

### PoolHead

Immutable PoolHead record.

**Attributes:**

- `pool_id` (str)
- `physical_sources` (tuple[str, ...])

### PoolMetadata

A TE ingress pool; ``offer_limit_units`` is its prepared lossy offer budget.

**Attributes:**

- `head` (PoolHead)
- `offer_limit_units` (int) = 0
- `synthetic_ingress_cost` (ClassVar[Literal[1]]) = 1

### PrecisionMiss

Immutable PrecisionMiss record.

**Attributes:**

- `location` (ReportLocation)
- `constraints` (tuple[InputConstraint | SplitConstraint | UnverifiedConstraint, ...])
- `inexact_inputs` (int)
- `zeroed_inputs` (int)
- `examples` (tuple[InputQuantization, ...])

### PreparationScope

Immutable PreparationScope record.

**Attributes:**

- `workflow_steps` (tuple[str, ...])
- `workflow_demand_sets` (tuple[str, ...])
- `library_demand_sets` (tuple[str, ...])

### ProgrammedRouter

Immutable ProgrammedRouter record.

**Attributes:**

- `router` (str)
- `members` (tuple[MemberWeight, ...])

### RangeConstraint

Immutable RangeConstraint record.

**Attributes:**

- `kind` (Literal['capacity_sum', 'cost_sum', 'amount'])
- `label` (str)
- `tested_q` (float)
- `units_value` (int)
- `exclusive_limit` (int)
- `met` (bool)

### RangeRefusal

Immutable RangeRefusal record.

**Attributes:**

- `label` (str)
- `reason` (Literal['scaled_nonfinite', 'native_units_range'])
- `message` (str)
- `binary64_hex` (str | None)

### ReportLocation

Immutable ReportLocation record.

**Attributes:**

- `step` (str | None)
- `case_id` (str | None)
- `probe_index` (int | None)

### ResolvedDemand

Immutable ResolvedDemand record.

**Attributes:**

- `id` (str)
- `base_id` (str)
- `endpoints` (Endpoints)
- `priority` (int)
- `order` (int)
- `nominal_units` (int)
- `config` (ngc.FlowPolicyConfig)
- `pool` (PoolMetadata | None)
- `yaml_label` (str | None)

### ResolvedDemandSet

Resolved demands; a set the WCMP controller programs also holds its tables.

``controller_tables`` are the internal tables with their destination
names; ``controller`` is their report (None when the controller programs
nothing).

**Attributes:**

- `name` (str)
- `demands` (tuple[ResolvedDemand, ...])
- `accounting` (tuple[ExpansionAccounting, ...])
- `expansion_template` (tuple[ExpansionParent, ...])
- `controller_tables` (tuple[tuple[str, DestinationTable], ...]) = ()
- `controller` (tuple[TableReport, ...] | None)

**Methods:**

- `controller_table(self, destination: 'str') -> 'DestinationTable'` - The internal table toward one destination router.

### RunMetadata

Immutable RunMetadata record.

**Attributes:**

- `schema_version` (ClassVar[Literal['1.0']]) = 1.0
- `netgraph_version` (str)
- `core_version` (str)
- `core_extension_sha256` (str)
- `python_version` (str)
- `seed` (int | None)

### RunResult

One run; ``units_report`` adds every step's precision misses, by step.

**Attributes:**

- `metadata` (RunMetadata)
- `units_report` (UnitsReport)
- `steps` (tuple[StepResult, ...])
- `prepared` (PreparedScenario)

### SamplingMetadata

Immutable SamplingMetadata record.

**Attributes:**

- `random_rule_algorithm` (ClassVar[Literal['per_entity_bernoulli']]) = per_entity_bernoulli
- `rng` (ClassVar[Literal['random.Random']]) = random.Random
- `python_version` (ClassVar[str]) = 3.14.5
- `seed` (int | None)
- `seed_source` (Literal['query', 'step', 'scenario', 'policy', 'unseeded'])
- `draw_seed_rule` (ClassVar[Literal['base_plus_draw_index']]) = base_plus_draw_index
- `entity_order` (ClassVar[Literal['sorted_identifier']]) = sorted_identifier
- `rule_order` (ClassVar[Literal['declaration']]) = declaration
- `iterations` (int)

### SelfPair

Immutable SelfPair record.

**Attributes:**

- `kind` (ClassVar[Literal['self']]) = self
- `id` (str)
- `node` (str)
- `capacity_units` (ClassVar[Literal[0]]) = 0

### SensitivityAnalysis

Immutable SensitivityAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['sensitivity']]) = sensitivity
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `endpoints` (Endpoints)
- `question` (Literal['lossless_bound', 'fixed_offer_delivery'])
- `offer_source` (Literal['unlimited', 'explicit', 'design'])
- `result` (ngc.SensitivityResult)
- `query` (SensitivityQuery)

### SourceWeight

A source's nominal physical demand toward the destination and its weight.

**Attributes:**

- `source` (str)
- `nominal_physical` (Fraction)
- `weight` (int)

### SplitConstraint

Immutable SplitConstraint record.

**Attributes:**

- `kind` (Literal['expansion', 'source', 'router', 'tunnel'])
- `label` (str)
- `incoming_physical` (Fraction)
- `basis` (Literal['declared', 'observed'])
- `members` (Annotated[int, {'minimum': 2}])
- `q_upper_bound` (Fraction)
- `met` (bool)

### StepContext

Immutable StepContext record.

**Attributes:**

- `prepared` (PreparedScenario)
- `prior_results` (Mapping[str, StepResult])
- `step_name` (str)
- `execution_order` (int)
- `seed` (int | None)
- `seed_source` (Literal['explicit-step', 'scenario-derived', 'none'])

### StepOutput

Immutable StepOutput record.

**Attributes:**

- `question` (StepQuestion)
- `result` (object)

### StepResult

Immutable StepResult record.

**Attributes:**

- `name` (str)
- `step_type` (str)
- `execution_order` (int)
- `scenario_seed` (int | None)
- `step_seed` (int | None)
- `seed_source` (Literal['explicit-step', 'scenario-derived', 'none'])
- `result` (object)
- `question` (StepQuestion)

### SyntheticIngress

Immutable SyntheticIngress record.

**Attributes:**

- `pool_id` (str)
- `source` (str)

### TableReport

The WCMP controller's table toward one destination, by name.

``programmed`` lists the routers the controller programs; any other router
splits equally over its members (ECMP).

**Attributes:**

- `destination` (str)
- `programmed` (tuple[ProgrammedRouter, ...])
- `source_weights` (tuple[SourceWeight, ...] | None)

### TunnelCountAnalysis

Immutable TunnelCountAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['tunnel_counts']]) = tunnel_counts
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `rows` (tuple[TunnelCountRow, ...])
- `query` (TunnelCountQuery)

### TunnelCountRow

One demand's evaluation at one tunnel count.

``count`` is the requested count per head, or the limit of an ``up_to``
row; the chosen count is ``result.plan.tunnels_per_head``. The plan's
tunnel cost is on the analysis graph: a pool row adds one cost-1 ingress
hop per tunnel, which ``physical_tunnel_cost`` leaves out.
``lossless_at_design_units`` is min(design, the plan's largest lossless
offer).

**Attributes:**

- `id` (str)
- `base_id` (str)
- `endpoints` (Endpoints)
- `count` (int)
- `up_to` (bool)
- `result` (ngc.PlacementResult)
- `pool` (PoolMetadata | None)
- `lossless_at_design_units` (int)
- `physical_tunnel_cost` (int)

### UnitsReport

Immutable UnitsReport record.

**Attributes:**

- `q` (float)
- `exponent` (int)
- `mode` (Literal['auto', 'manual'])
- `precision` (float)
- `target_met` (bool)
- `input_convention` (ClassVar[Literal['promoted_binary64_half_up']]) = promoted_binary64_half_up
- `display_convention` (ClassVar[Literal['units_authoritative_binary64_display']]) = units_authoritative_binary64_display
- `scope` (PreparationScope)
- `binding_constraints` (tuple[UnitConstraint, ...])
- `input_count` (int)
- `inexact_inputs` (int)
- `zeroed_inputs` (int)
- `inexact_examples` (tuple[InputQuantization, ...])
- `zeroed_examples` (tuple[InputQuantization, ...])
- `max_absolute_input_error` (Fraction)
- `max_relative_input_error` (Fraction)
- `augmented_capacity_sum_units` (int)
- `augmented_cost_sum` (int)
- `nominal_split_count` (int)
- `nominal_splits` (tuple[SplitConstraint, ...])
- `misses` (tuple[PrecisionMiss, ...])
- `weight_approximations` (tuple[WeightApproximation, ...]) = ()

**Methods:**

- `with_approximations(self, entries: 'tuple[WeightApproximation, ...]') -> 'UnitsReport'` - This report with the controller's weight approximations, each once.
- `with_misses(self, misses: 'tuple[PrecisionMiss, ...]') -> 'UnitsReport'` - This report with further precision misses appended.

### UnverifiedConstraint

Immutable UnverifiedConstraint record.

**Attributes:**

- `kind` (ClassVar[Literal['unverified']]) = unverified
- `label` (str)
- `reason` (ClassVar[Literal['opaque_program']]) = opaque_program

### UpperCertificate

Immutable UpperCertificate record.

**Attributes:**

- `proof` (Literal['fixed_program', 'single_controller'])
- `lower` (ExactAlpha)
- `upper` (ExactAlpha)
- `lower_probe_index` (int)
- `upper_probe_index` (int)

### WeightApproximation

Controller weights whose exact values reached 2^62 and were apportioned.

The label names a router (``controller.<set>.<t>.router.<r>``) or, for an
``all_routers`` source vector, its source with the largest error
(``controller.<set>.<t>.source.<s>``). ``max_relative_error`` is the
largest relative error of the normalized shares over the positive members
or sources.

**Attributes:**

- `kind` (ClassVar[Literal['weight_approximation']]) = weight_approximation
- `label` (str)
- `max_relative_error` (Fraction)

### approximations(demands: 'ResolvedDemandSet') -> 'tuple[WeightApproximation, ...]'

The weight approximations of a demand set's controller tables.

### exact_alpha(value: 'float') -> 'ExactAlpha'

The exact binary64 ratio of a positive physical multiplier.

---

## ngraph.scenario

Editable scenarios, read-only shared preparation and typed workflow execution.

### Scenario

Named domain inputs, fixed at construction.

The network and the components library keep editable dicts of immutable
records; ``prepare`` takes a read-only view of them, so later edits do not
reach a prepared scenario. ``dataclasses.replace`` builds an edited copy.

**Attributes:**

- `network` (Network)
- `workflow` (Sequence[WorkflowStep]) = ()
- `demand_sets` (Mapping[str, DemandSet]) = {}
- `failure_policies` (Mapping[str, FailurePolicy]) = {}
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})
- `seed` (int | None)
- `units` (UnitsSettings) = UnitsSettings(resolution='auto', precision=0.001)
- `routes` (Mapping[str, RouteSpec]) = {}
- `supports` (Mapping[str, SupportSpec]) = {}
- `weights` (Mapping[str, WeightSpec]) = {}
- `forwarding_groups` (Mapping[str, ForwardingGroup]) = {}
- `routing` (RoutingDomain | None)
- `wcmp_controller` (WCMPController | None)

**Methods:**

- `from_yaml(yaml_str: 'str', default_components: 'ComponentsLibrary | None' = None) -> 'Scenario'` - Parse one closed scenario declaration and retain editable domain inputs.

### prepare(scenario: 'Scenario', *, units: 'UnitsSettings | None' = None, demand_sets: 'Sequence[str]' = ()) -> 'PreparedScenario'

Choose one graph/unit over a read-only view of the scenario.

The input is not changed. The prepared scenario shares its immutable
records and keeps read-only copies of the network and component dicts,
so later edits of the caller's collections do not reach it.

### run(prepared: 'PreparedScenario', *, step_hook: 'Callable[[WorkflowStep], AbstractContextManager[None]] | None' = None) -> 'RunResult'

Execute once in declaration order; publish a run only after every step succeeds.

---

## ngraph.model.components

Component and ComponentsLibrary classes for hardware capex/power modeling.

### Component

Hardware component such as a chassis, line card, or optic.

Components can nest children, each with its own capex, power, and count.

Attributes:
    name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
    component_type (str): Free-form label (e.g., "chassis", "linecard", "optic").
    description (str): Free-form human-readable description.
    capex (float): Monetary capex of a single instance of this component.
    power_watts (float): Typical/nominal power usage (watts) for one instance.
    power_watts_max (float): Maximum/peak power usage (watts) for one instance.
    capacity (float): A generic capacity measure (e.g., platform capacity).
    ports (int): Number of ports if relevant for this component.
    count (int): How many identical copies of this component are present.
    attrs (Dict[str, Any]): Finite JSON metadata, checked and stored
        read-only at construction.
    children (Dict[str, Component]): Nested child components (e.g., line cards
        inside a chassis), keyed by child name; read-only.

**Attributes:**

- `name` (str)
- `component_type` (str) = generic
- `description` (str)
- `capex` (float) = 0.0
- `power_watts` (float) = 0.0
- `power_watts_max` (float) = 0.0
- `capacity` (float) = 0.0
- `ports` (int) = 0
- `count` (int) = 1
- `attrs` (Dict[str, Any]) = {}
- `children` (Dict[str, Component]) = {}

**Methods:**

- `as_dict(self, include_children: 'bool' = True) -> 'Dict[str, Any]'` - Returns a dictionary containing all properties of this component.
- `total_capacity(self) -> 'float'` - Computes capacity for this component and all descendants.
- `total_capex(self) -> 'float'` - Return capex of this component and all descendants, times ``count``.
- `total_power(self) -> 'float'` - Computes *typical* power for this component and all descendants.
- `total_power_max(self) -> 'float'` - Computes *peak* power for this component and all descendants.

### ComponentsLibrary

Named Component templates for capex, power, and capacity lookups.

Each entry is a top-level template and may have nested children. The
``components`` dict stays editable; ``prepare`` keeps a read-only view.

Example (YAML-like):
    components:
      BigSwitch:
        component_type: chassis
        capex: 20000
        power_watts: 1750
        capacity: 25600
        children:
          PIM16Q-16x200G:
            component_type: linecard
            capex: 1000
            power_watts: 10
            ports: 16
            count: 8
      200G-FR4:
        component_type: optic
        capex: 2000
        power_watts: 6
        power_watts_max: 6.5

**Attributes:**

- `components` (Dict[str, Component]) = {}

**Methods:**

- `clone(self) -> 'ComponentsLibrary'` - Creates an independent copy of this ComponentsLibrary.
- `from_dict(data: 'Dict[str, Any]') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from raw component definitions.
- `from_yaml(yaml_str: 'str') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from a YAML string.
- `get(self, name: 'str') -> 'Optional[Component]'` - Retrieves a Component by its name from the library.
- `merge(self, other: 'ComponentsLibrary', override: 'bool' = True) -> 'ComponentsLibrary'` - Merges another ComponentsLibrary into this one.
- `snapshot(self) -> 'ComponentsLibrary'` - Return a read-only view sharing this library's immutable components.

### resolve_link_end_components(attrs: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'tuple[tuple[Optional[Component], float, bool], tuple[Optional[Component], float, bool]]'

Resolve per-end hardware components for a link.

Input format inside ``link.attrs`` is a structured mapping under the
``hardware`` key only:
  ``{"hardware": {"source": {"component": NAME, "count": N},
                   "target": {"component": NAME, "count": N}}}``
An optional ``exclusive: true`` per end indicates unsharable usage; BOM
counting rounds the count of an exclusive end up to an integer.

Args:
    attrs: Link attributes mapping.
    library: Components library for lookups.

Returns:
    ((src_comp, src_count, src_exclusive), (dst_comp, dst_count, dst_exclusive))
    where a component is ``None`` when the end or its name is absent or
    unknown.

Raises:
    ValueError: If an end's ``count`` is not a finite positive number.

### resolve_node_hardware(attrs: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'Tuple[Optional[Component], float]'

Resolve node hardware from ``attrs['hardware']``.

Expects the mapping: ``{"hardware": {"component": NAME, "count": N}}``.
``count`` defaults to 1. If ``component`` is missing or unknown, the
component is None.

Args:
    attrs: Node attributes mapping.
    library: Component library used for lookups.

Returns:
    Tuple of (component or None, positive multiplier).

Raises:
    ValueError: If ``count`` is not a finite positive number.

### totals_with_multiplier(comp: 'Component', hw_count: 'float') -> 'Tuple[float, float, float]'

Return (capex, power_watts, capacity) totals multiplied by ``hw_count``.

Args:
    comp: Component definition (may include nested children and internal ``count``).
    hw_count: External multiplier (e.g., number of modules used for a link or node).

Returns:
    Tuple of total capex, total power (typical), and total capacity as floats.

---

## ngraph.model.demand

Immutable demand declarations and native preset values.

### ControllerGroup

A root group of one router: its share is a fixed cap, normalized once.

**Attributes:**

- `children` (tuple[GroupChild, ...])
- `share` (Fraction)

### DemandSet

DemandSet(name: 'str', demands: 'tuple[DemandSpec, ...]')

**Attributes:**

- `name` (str)
- `demands` (tuple[DemandSpec, ...])

### DemandSpec

DemandSpec(source: 'Selector', target: 'Selector', volume: 'PhysicalAmount', policy: 'DemandPolicy' = <FlowPolicyPreset.SHORTEST_PATHS_ECMP: 'SHORTEST_PATHS_ECMP'>, id: 'str | None' = None, priority: 'int' = 0, mode: "Literal['combine', 'pairwise']" = 'combine', group_mode: "Literal['flatten', 'per_group', 'group_pairwise']" = 'flatten', attrs: 'Mapping[str, JSONValue]' = <factory>, *, yaml_label: 'str | None' = None, declaration_ordinal: 'int | None' = None, expand_leaf_index: 'int | None' = None)

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `volume` (PhysicalAmount)
- `policy` (DemandPolicy) = SHORTEST_PATHS_ECMP
- `id` (str | None)
- `priority` (int) = 0
- `mode` (Literal['combine', 'pairwise']) = combine
- `group_mode` (Literal['flatten', 'per_group', 'group_pairwise']) = flatten
- `attrs` (Mapping[str, JSONValue]) = {}
- `yaml_label` (str | None)
- `declaration_ordinal` (int | None)
- `expand_leaf_index` (int | None)

### EdgeWeight

EdgeWeight(edge: 'DirectedLink', value: 'int')

**Attributes:**

- `edge` (DirectedLink)
- `value` (int)

### FlowPolicyPreset

Named questions with one immutable native configuration each.

### ForwardingGroup

The declared root groups of one router.

**Attributes:**

- `router` (str)
- `groups` (tuple[ControllerGroup, ...])

### GroupChild

A member edge, or a conditional subtree, with its share within its parent.

Exactly one of ``edge`` and ``children`` is set; preparation checks the
structure and the share's range. The share is stored as a Fraction.

**Attributes:**

- `share` (Fraction)
- `edge` (DirectedLink | None)
- `children` (tuple[GroupChild, ...] | None)

### PinnedRoutes

PinnedRoutes(routes: 'tuple[str, ...]', admission: 'ngc.Admission' = <Admission.LOSSLESS: 0>, allocation: 'ngc.RouteAllocation | None' = None, weight_basis: 'ngc.WeightBasis | None' = None, edge_weights: 'str | None' = None)

**Attributes:**

- `routes` (tuple[str, ...])
- `admission` (ngc.Admission) = Admission.LOSSLESS
- `allocation` (ngc.RouteAllocation | None)
- `weight_basis` (ngc.WeightBasis | None)
- `edge_weights` (str | None)

### RouteSpec

RouteSpec(head: 'str', nodes: 'tuple[str, ...] | None' = None, edges: 'tuple[DirectedLink, ...] | None' = None, support: 'str | None' = None, weight: 'int' = 1)

**Attributes:**

- `head` (str)
- `nodes` (tuple[str, ...] | None)
- `edges` (tuple[DirectedLink, ...] | None)
- `support` (str | None)
- `weight` (int) = 1

### RoutingDomain

One IGP domain and the BGP-edge routers around it.

**Attributes:**

- `igp_domain` (Selector)
- `bgp_edge` (Selector)

### SupportSpec

SupportSpec(edges: 'tuple[DirectedLink, ...]')

**Attributes:**

- `edges` (tuple[DirectedLink, ...])

### WCMPController

Which routers the controller programs for SHORTEST_PATHS_WCMP demands.

**Attributes:**

- `scope` (Literal['next_hop', 'group', 'all_routers']) = next_hop

### WeightSpec

WeightSpec(entries: 'tuple[EdgeWeight, ...]')

**Attributes:**

- `entries` (tuple[EdgeWeight, ...])

---

## ngraph.model.failure

Failure declarations and one YAML construction path.

### FailureMode

FailureMode(weight: 'float', rules: 'Sequence[FailureRule]' = (), attrs: 'dict[str, Any]' = <factory>)

**Attributes:**

- `weight` (float)
- `rules` (Sequence[FailureRule]) = ()
- `attrs` (dict[str, Any]) = {}

### FailurePolicy

FailurePolicy(attrs: 'dict[str, Any]' = <factory>, expand_groups: 'bool' = False, seed: 'int | None' = None, modes: 'Sequence[FailureMode]' = ())

**Attributes:**

- `attrs` (dict[str, Any]) = {}
- `expand_groups` (bool) = False
- `seed` (int | None)
- `modes` (Sequence[FailureMode]) = ()

### FailureRule

FailureRule(scope: 'EntityScope', conditions: 'Sequence[Condition]' = (), logic: "Literal['and', 'or']" = 'or', mode: "Literal['random', 'choice', 'all']" = 'all', probability: 'float' = 1.0, count: 'int' = 1, weight_by: 'str | None' = None, path: 'str | None' = None)

**Attributes:**

- `scope` (EntityScope)
- `conditions` (Sequence[Condition]) = ()
- `logic` (Literal['and', 'or']) = or
- `mode` (Literal['random', 'choice', 'all']) = all
- `probability` (float) = 1.0
- `count` (int) = 1
- `weight_by` (str | None)
- `path` (str | None)

### build_failure_policies(raw: 'dict[str, Any]', master_seed: 'int | None') -> 'dict[str, FailurePolicy]'

Construct named policies; seeded YAML keeps the established composed hash.

Policy name ``n`` uses SHA256("<master>:failure_policy:failure_policy:<n>"),
first four bytes big-endian masked to31 bits. Step seeds use their own
workflow_step component and never pass through this policy derivation.

---

## ngraph.model.network

Network topology modeling with Node, Link, RiskGroup, and Network classes.

These classes carry no analysis machinery and can be used on their own.
Nodes, links and risk groups are immutable records; a Network holds them in
editable dicts and its edit methods replace records.

### DirectedLink

One analysis direction of a stored physical link.

**Attributes:**

- `link` (str)
- `direction` (Literal['forward', 'reverse'])

### Link

One directed link between two nodes.

The model stores a single direction (``source`` -> ``target``). When the
prepared native graph is built, a reverse
edge is added automatically for each link to provide bidirectional
connectivity.

Attributes:
    source (str): Name of the source node.
    target (str): Name of the target node.
    capacity (float): Finite nonnegative link capacity (default 1.0),
        promoted to binary64 at construction.
    cost (float): Link cost (default 1.0).
    disabled (bool): Whether the link is disabled.
    risk_groups (AbstractSet[str]): Names of the risk groups this link belongs
        to, stored as a frozenset.
    attrs (Dict[str, Any]): Finite JSON metadata (e.g., distance), checked
        and stored read-only at construction.
    id (str): Unique identifier. ``Network.add_link`` assigns the
        deterministic form "{source}|{target}|<seq>", where <seq> is a
        per-(source, target) insertion sequence number, once; links never
        added to a Network keep a provisional uuid-suffixed id.

**Attributes:**

- `source` (str)
- `target` (str)
- `capacity` (float) = 1.0
- `cost` (float) = 1.0
- `disabled` (bool) = False
- `risk_groups` (AbstractSet[str]) = frozenset()
- `attrs` (Dict[str, Any]) = {}
- `id` (str)

### Network

Scenario-level topology: nodes, links, and risk groups.

Holds persistent state only (nodes and links disabled in the scenario
configuration). For temporary exclusions, pass a graph-owned Eligibility
through the native operation's options.

The dicts stay editable; their values are immutable records, so an edit
replaces a record. ``prepare`` keeps a read-only view of these dicts, so
later edits do not reach a prepared scenario.

Attributes:
    nodes (Dict[str, Node]): Mapping from node name -> Node object.
    links (Dict[str, Link]): Mapping from link ID -> Link object.
    risk_groups (Dict[str, RiskGroup]): Top-level risk groups by name.
    attrs (Dict[str, Any]): Optional metadata about the network.

**Attributes:**

- `nodes` (Dict[str, Node]) = {}
- `links` (Dict[str, Link]) = {}
- `risk_groups` (Dict[str, RiskGroup]) = {}
- `attrs` (Dict[str, Any]) = {}
- `_link_seq` (Dict[tuple, int]) = {}

**Methods:**

- `add_link(self, link: 'Link') -> 'None'` - Add a link to the network, assigning its deterministic ID.
- `add_node(self, node: 'Node') -> 'None'` - Add a node to the network (keyed by node.name).
- `disable_all(self) -> 'None'` - Mark all nodes and links as disabled.
- `disable_link(self, link_id: 'str') -> 'None'` - Mark a link as disabled.
- `disable_node(self, node_name: 'str') -> 'None'` - Mark a node as disabled.
- `disable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'` - Disable every node/link that has 'name' in its risk_groups.
- `enable_all(self) -> 'None'` - Mark all nodes and links as enabled.
- `enable_link(self, link_id: 'str') -> 'None'` - Mark a link as enabled.
- `enable_node(self, node_name: 'str') -> 'None'` - Mark a node as enabled.
- `enable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'` - Enable every node/link that has 'name' in its risk_groups.
- `find_links(self, source_regex: 'Optional[str]' = None, target_regex: 'Optional[str]' = None, any_direction: 'bool' = False) -> 'List[Link]'` - Search for links by regex on source and/or target node names.
- `get_links_between(self, source: 'str', target: 'str') -> 'List[str]'` - Retrieve the IDs of all direct links from source to target.
- `replace_link(self, link_id: 'str', **changes: 'Any') -> 'Link'` - Replace a link by a copy with the given field changes; its id stays.
- `replace_node(self, name: 'str', **changes: 'Any') -> 'Node'` - Replace a node by a copy with the given field changes.
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'` - Select and group nodes by regex pattern on node name.
- `snapshot(self) -> 'Network'` - Return a read-only view sharing this network's immutable records.

### Node

Network node, keyed by its unique name in ``Network.nodes``.

Attributes:
    name (str): Unique identifier for the node.
    disabled (bool): Whether the node is disabled in the scenario configuration.
    risk_groups (AbstractSet[str]): Names of the risk groups this node belongs
        to, stored as a frozenset.
    attrs (Dict[str, Any]): Finite JSON metadata (e.g., coordinates, region),
        checked and stored read-only at construction.

**Attributes:**

- `name` (str)
- `disabled` (bool) = False
- `risk_groups` (AbstractSet[str]) = frozenset()
- `attrs` (Dict[str, Any]) = {}

---

## ngraph.model.risk

Risk-group declarations and the shared, typed membership resolver.

### GenerateSpec

Parsed generate block specification.

Attributes:
    scope: Type of entities to group ("node" or "link").
    path: Optional regex pattern to filter entities by name.
    group_by: Attribute name to group by (supports dot-notation).
    name: Template for generated group names. Use ${value}
        as placeholder for the attribute value.
    attrs: Optional static attributes for generated groups.

**Attributes:**

- `scope` (Literal['node', 'link'])
- `group_by` (str)
- `name` (str)
- `path` (Optional[str])
- `attrs` (Dict[str, Any]) = {}

### Members

Members(nodes: 'frozenset[str]', links: 'frozenset[str]')

**Attributes:**

- `nodes` (frozenset[str])
- `links` (frozenset[str])

### MembershipIndex

One immutable resolution of the current editable network.

Node and link identifiers occupy separate namespaces. Mutation callers
build a fresh index; prepared analyses retain their owned snapshot.

**Attributes:**

- `groups` (Mapping[str, RiskGroup])
- `direct` (Mapping[str, Members])
- `transitive` (Mapping[str, Members])
- `node_groups` (Mapping[str, frozenset[str]])
- `link_groups` (Mapping[str, frozenset[str]])

**Methods:**

- `build(network: 'Network') -> 'MembershipIndex'`
- `expand(self, nodes: 'set[str]', links: 'set[str]', groups: 'set[str]', *, shared: 'bool') -> 'Members'` - Expand explicit group causes, then optional shared direct membership.
- `members(self, group: 'str', recursive: 'bool' = True) -> 'Members'`

### MembershipSpec

Parsed membership rule specification.

Attributes:
    scope: Type of entities to match ("node", "link", or "risk_group").
    path: Optional regex pattern. For node and risk_group scope it is
        matched against the entity ID; for link scope it is matched
        against the "source|target" key, not the link ID.
    match: Match specification with conditions.

**Attributes:**

- `scope` (EntityScope)
- `path` (Optional[str])
- `match` (Optional[MatchSpec])

### RiskGroup

A named failure domain with optional nested, unregistered descendants.

``attrs`` holds finite JSON metadata, checked and stored read-only at
construction.

**Attributes:**

- `name` (str)
- `children` (Sequence[RiskGroup]) = ()
- `disabled` (bool) = False
- `attrs` (dict[str, Any]) = {}
- `_membership_raw` (dict[str, Any] | None)

### build_risk_groups(rg_data: 'List[Any]') -> 'tuple[List[RiskGroup], List[Dict[str, Any]]]'

Build RiskGroup objects from raw config data.

Supports:

- String shorthand: "GroupName" is equivalent to {name: "GroupName"}
- Bracket expansion: {name: "DC[1-3]_Power"} creates DC1_Power, DC2_Power, DC3_Power
- Children are also expanded recursively
- Generate blocks: {generate: {...}} for dynamic group creation

'membership', 'disabled', and 'generate' are only honored on top-level
entries: only top-level groups are registered in network.risk_groups, so
these keys would be silently inert on nested children. Child entries
carrying them are rejected with ValueError.

Args:
    rg_data: List of risk group definitions (strings or dicts).

Returns:
    Tuple of (explicit_risk_groups, generate_specs_raw):

- explicit_risk_groups: List of RiskGroup objects with names expanded.
- generate_specs_raw: List of raw generate block dicts for deferred processing.

Raises:
    ValueError: If an entry is neither a string nor a dict, lacks a name,
        carries an unrecognized key, or is a child entry with
        'membership', 'disabled' or 'generate'.

### generate_risk_groups(network: "'Network'", spec: 'GenerateSpec') -> 'List[RiskGroup]'

Generate risk groups from unique attribute values.

For each unique value of the specified attribute, creates a new risk
group and adds its name to the `risk_groups` of every matching entity,
replacing those records in the network. The caller registers the
returned groups.

Args:
    network: Network with nodes and links populated.
    spec: Generation specification.

Returns:
    List of newly created RiskGroup objects.

Raises:
    ValueError: If `group_by` resolves to an unhashable value, or if the
        name template renders the same group name for two distinct values.

### parse_generate_spec(raw: 'Dict[str, Any]') -> 'GenerateSpec'

Parse raw generate dict into a GenerateSpec.

Args:
    raw: Raw generate dict from YAML.

Returns:
    Parsed GenerateSpec.

Raises:
    ValueError: If the block carries an unrecognized key, 'scope' is
        missing or is neither 'node' nor 'link', 'group_by' or 'name' is
        missing, or 'name' omits the '${value}' placeholder.

### resolve_membership_rules(network: "'Network'") -> 'None'

Apply membership rules to populate entity risk_groups sets.

For each risk group with a `_membership_raw` specification:

- If scope is "node" or "link": adds the risk group name to each

  matched entity's risk_groups set.

- If scope is "risk_group": adds matched risk groups as children

  of this risk group (hierarchical membership).

Replaces the affected records in the network. Call after all risk groups
are registered but before validation.

Args:
    network: Network with risk_groups, nodes, and links populated.

---

## ngraph.model.selectors.conditions

Condition evaluation for node/entity filtering.

Evaluates the attribute conditions used by selectors and failure policies.
Operators: ==, !=, <, <=, >, >=, contains, not_contains, in, not_in, exists,
not_exists.

Attribute names support dot-notation for nested access (e.g. "hardware.vendor").

### evaluate_condition(attrs: 'Dict[str, Any]', cond: "'Condition'") -> 'bool'

Evaluate a single condition against an attribute dict.

Supports dot-notation for nested attribute access (e.g., "hardware.vendor").

Args:
    attrs: Mapping of entity attributes (may contain nested dicts).
    cond: Condition to evaluate.

Returns:
    True if condition passes, False otherwise.

Raises:
    ValueError: If operator is unknown or value type is invalid.

### evaluate_conditions(attrs: 'Dict[str, Any]', conditions: "Iterable['Condition']", logic: 'str' = 'or') -> 'bool'

Evaluate multiple conditions with AND/OR logic.

Args:
    attrs: Flat mapping of entity attributes.
    conditions: Iterable of Condition objects.
    logic: "and" (all must match) or "or" (any must match).

Returns:
    True if combined predicate passes.

Raises:
    ValueError: If logic is not "and" or "or".

### resolve_attr_path(attrs: 'Dict[str, Any]', path: 'str') -> 'Tuple[bool, Any]'

Resolve a dot-notation attribute path.

Supports nested attribute access like "hardware.vendor" which resolves
to attrs["hardware"]["vendor"].

Args:
    attrs: Attribute dict (may contain nested dicts).
    path: Attribute path, optionally with dots for nesting.

Returns:
    Tuple of (found, value). If found is False, value is None.

Examples:
    >>> resolve_attr_path({"role": "spine"}, "role")
    (True, 'spine')
    >>> resolve_attr_path({"hardware": {"vendor": "Acme"}}, "hardware.vendor")
    (True, 'Acme')
    >>> resolve_attr_path({"role": "spine"}, "missing")
    (False, None)

---

## ngraph.model.selectors.parse

Parsing of match specifications from plain dicts.

Builds model schema types (`Condition`, `MatchSpec`) from raw dict input.
Lives in the model layer so failure-policy and membership parsing can use
it without a runtime dependency on the DSL package.

### normalize_selector(raw: 'Union[str, Dict[str, Any], Selector]', context: 'str') -> 'Selector'

Normalize a raw selector (string or dict) to a Selector.

All downstream code works with Selector objects only.

Args:
    raw: Either a regex string, selector dict, or existing Selector.
    context: Usage context ("link", "rule", "demand", "workflow").
        Determines the default for active_only.

Returns:
    Selector with active_only set, from the selector or the context
    default.

Raises:
    ValueError: If the selector is neither a string nor a dict, a selector
        dict carries an unrecognized key, or the context is unknown.

### parse_match_spec(raw: 'Dict[str, Any]', *, default_logic: "Literal['and', 'or']" = 'or', require_conditions: 'bool' = False, context: 'str' = 'match') -> 'MatchSpec'

Parse a match specification from raw dict.

Shared by link definitions, demands, membership rules, and failure policies.

Args:
    raw: Dict with 'conditions' list and optional 'logic'. Both keys are
        optional; a missing 'conditions' yields an empty condition list.
    default_logic: Used when 'logic' is absent.
    require_conditions: If True, raise when conditions list is empty.
    context: Name of the enclosing construct, quoted in error messages.

Returns:
    Parsed MatchSpec.

Raises:
    ValueError: If the spec or a condition carries an unrecognized key,
        'logic' is not 'and'/'or', 'conditions' is not a list, a
        condition is not a dict or lacks 'attr'/'op', 'in'/'not_in' is
        given a non-list value, or conditions are required but empty.

---

## ngraph.model.selectors.schema

Selector schema dataclasses.

Shared by network rules, demands, failure policies, and workflow steps.

### Condition

A single attribute condition for filtering.

Supports dot-notation for nested attribute access (e.g., "hardware.vendor"
resolves to attrs["hardware"]["vendor"]).

Attributes:
    attr: Attribute name to match (supports dot-notation for nested attrs).
    op: Comparison operator.
    value: Right-hand operand (unused for exists/not_exists): finite JSON
        data, stored read-only with accepted scalar subclasses normalized.

**Attributes:**

- `attr` (str)
- `op` (ConditionOp)
- `value` (Any)

### MatchSpec

Attribute conditions combined with "and" or "or" logic.

Attributes:
    conditions: Conditions to evaluate, in order.
    logic: How to combine conditions ("and" = all, "or" = any).

**Attributes:**

- `conditions` (Sequence[Condition]) = ()
- `logic` (Literal['and', 'or']) = or

### Selector

Node selection by name regex, attribute conditions, and grouping.

Evaluation order:

1. Select nodes matching `path` regex (default ".*" if omitted)
2. Filter by `match` conditions
3. Filter by `active_only` flag
4. Group by `group_by` attribute (if specified)

At least one of path, group_by, or match must be specified.

Attributes:
    path: Regex pattern on node.name.
    group_by: Attribute name to group nodes by.
    match: Attribute-based filtering conditions.
    active_only: Whether to exclude disabled nodes. None uses context default.

**Attributes:**

- `path` (Optional[str])
- `group_by` (Optional[str])
- `match` (Optional[MatchSpec])
- `active_only` (Optional[bool])

---

## ngraph.model.selectors.select

Node selection and evaluation.

`select_nodes()` combines regex matching, attribute filtering, active-only
filtering, and grouping; the flatten helpers build the attribute dicts that
condition evaluation runs against.

### flatten_link_attrs(link: "'Link'", link_id: 'str') -> 'Dict[str, Any]'

Build flat attribute dict for condition evaluation on links.

Merges link's top-level fields with link.attrs. Top-level fields
take precedence on key conflicts.

Args:
    link: Link object to flatten.
    link_id: The link's ID in the network.

Returns:
    Flat dict suitable for condition evaluation.

### flatten_node_attrs(node: "'Node'") -> 'Dict[str, Any]'

Build flat attribute dict for condition evaluation.

Merges node's top-level fields (name, disabled, risk_groups) with
node.attrs. Top-level fields take precedence on key conflicts.

Args:
    node: Node object to flatten.

Returns:
    Flat dict suitable for condition evaluation.

### flatten_risk_group_attrs(rg: "'RiskGroup'") -> 'Dict[str, Any]'

Build flat attribute dict for condition evaluation on risk groups.

Merges risk group's top-level fields (name, disabled, children) with
rg.attrs. Top-level fields take precedence on key conflicts.

Args:
    rg: RiskGroup object.

Returns:
    Flat dict suitable for condition evaluation.

### link_path_key(attrs: 'Dict[str, Any]') -> 'str'

Return the "source|target" key used when path-matching links.

Links have no name of their own, so path regexes match against this
canonical endpoint-pair form of the flattened link attributes.

### match_entity_ids(entity_attrs: 'Dict[str, Dict[str, Any]]', conditions: 'Sequence[Condition]', logic: 'str' = 'or') -> 'Set[str]'

Match entity IDs by attribute conditions.

General primitive for condition-based entity selection. Works with
any entity type as long as attributes are pre-flattened.

Args:
    entity_attrs: Mapping of {entity_id: flattened_attrs_dict}
    conditions: List of conditions to evaluate
    logic: "and" (all must match) or "or" (any must match)

Returns:
    Set of matching entity IDs. Returns all IDs if conditions is empty.

### select_nodes(network: "'Network'", selector: 'Selector', default_active_only: 'bool') -> "Dict[str, List['Node']]"

Select and group the nodes a `Selector` matches.

Evaluation order:

1. Select nodes matching `path` regex (or all nodes if path is None)
2. Filter by `match` conditions
3. Filter by `active_only` flag
4. Group by `group_by` attribute (overrides regex capture grouping)

Args:
    network: Network whose nodes are searched.
    selector: Node selection specification.
    default_active_only: Used when the selector leaves `active_only`
        unset. Required rather than defaulted so callers cannot silently
        inherit the wrong policy.

Returns:
    Dict mapping group labels to lists of nodes. Groups that filter down
    to nothing are dropped.

---

## ngraph.workflow.base

Typed workflow execution and explicit extension registration.

### WorkflowStep

Base of every workflow step.

Built-in steps are immutable once constructed (``dataclasses.replace``
makes an edited copy). A custom step's own fields stay its own; ``prepare``
records its name and seed, so later edits of those do not reach a
prepared scenario.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> 'StepNeeds | None'` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: 'StepContext') -> 'StepOutput'` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: 'dict', name: 'str') -> 'dict'` - Turn this step type's YAML keys into constructor arguments.

### register_workflow_step(name: 'str') -> 'Callable[[type[StepT]], type[StepT]]'

Register one concrete step class for a nonempty YAML type name.

### step_type(name: 'str') -> 'type[WorkflowStep] | None'

Return the registered step class for a YAML type name, if any.

### validate_unique_step_names(workflow: 'Sequence[WorkflowStep]') -> 'None'

No documentation available.

### workflow_failures(context, policy_name, iterations, failure_trace)

Supply the step's named policy and effective seed to the one sampler.

---

## ngraph.workflow.build_graph

Export the named domain network in NetworkX node-link form.

### BuildGraph

BuildGraph(name: 'str' = '', seed: 'int | None' = None, add_reverse: bool = True, *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `question_kind` (ClassVar) = build_graph
- `add_reverse` (bool) = True

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> 'StepNeeds | None'` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: 'dict', name: 'str') -> 'dict'` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.cost_power

Platform/optic cost and power at each named hierarchy level.

### CostPower

CostPower(name: 'str' = '', seed: 'int | None' = None, include_disabled: 'bool' = False, aggregation_level: 'int' = 2, *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `question_kind` (ClassVar[str]) = cost_power
- `include_disabled` (bool) = False
- `aggregation_level` (int) = 2

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> 'StepNeeds | None'` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: 'StepContext') -> 'StepOutput'` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: 'dict', name: 'str') -> 'dict'` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.max_flow_step

Native capacity questions over one shared sequence of failure cases.

### MaxFlow

Evaluate independent endpoint capacities with explicit native routing.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `source` (Selector) = Selector(path='.*', group_by=None, match=None, active_only=None)
- `target` (Selector) = Selector(path='.*', group_by=None, match=None, active_only=None)
- `mode` (Literal) = combine
- `preset` (Union)
- `model` (object)
- `offer` (Union)
- `design_demand` (Union)
- `failure_policy` (Union)
- `iterations` (int) = 1
- `workers` (Union) = auto
- `failure_trace` (bool) = False
- `outputs` (OutputOptions)
- `export_cost_distribution` (bool) = False
- `export_details` (bool) = False

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `query(self, prepared: ngraph.analysis.preparation.PreparedScenario, failures=None) -> ngraph.analysis.capacity.CapacityQuery`
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: dict, name: str) -> dict` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.maximum_supported_demand_step

Report the largest tested feasible physical multiplier and its probe history.

### MaximumSupportedDemand

MaximumSupportedDemand(name: 'str' = '', seed: 'int | None' = None, demand_set: str = '', alpha_start: float = 1.0, growth_factor: float = 2.0, alpha_min: float = 1e-06, alpha_max: float = 1000000000.0, alpha_tolerance: float = 0.01, max_bracket_iters: int = 32, max_bisect_iters: int = 32, export_details: bool = False, *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `demand_set` (str)
- `alpha_start` (float) = 1.0
- `growth_factor` (float) = 2.0
- `alpha_min` (float) = 1e-06
- `alpha_max` (float) = 1000000000.0
- `alpha_tolerance` (float) = 0.01
- `max_bracket_iters` (int) = 32
- `max_bisect_iters` (int) = 32
- `export_details` (bool) = False

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `query(self, demands)`
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: dict, name: str) -> dict` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.network_stats

Statistics of the named physical network, with temporary exclusions.

### NetworkStats

NetworkStats(name: 'str' = '', seed: 'int | None' = None, include_disabled: bool = False, excluded_nodes: tuple[str, ...] = (), excluded_links: tuple[str, ...] = (), *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `question_kind` (ClassVar) = network_stats
- `include_disabled` (bool) = False
- `excluded_nodes` (tuple) = ()
- `excluded_links` (tuple) = ()

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> 'StepNeeds | None'` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: 'dict', name: 'str') -> 'dict'` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.parse

Workflow parsing helpers.

Converts a normalized workflow section (list[dict]) into WorkflowStep
instances using the WORKFLOW_STEP_REGISTRY and attaches unique names/seeds.

### build_workflow_steps(workflow_data: 'List[Dict[str, Any]]', derive_seed: 'Callable[[str], Optional[int]]') -> 'List[WorkflowStep]'

Instantiate workflow steps from normalized dictionaries.

Args:
    workflow_data: List of step dicts; each must have "type".
    derive_seed: Callable that takes a step name and returns a seed or None.

Returns:
    WorkflowStep instances. An unnamed step is named "{type}_{index}"; a
    step without a seed gets ``derive_seed(name)`` when that is not None.

Raises:
    ValueError: If ``workflow_data`` is not a list, a step lacks ``type``
        or names an unregistered type, two steps resolve to the same
        name, or a step carries a key its step class does not define.

---

## ngraph.workflow.traffic_matrix_placement_step

Ordered native traffic placement with typed earlier-MSD scale selection.

### TrafficMatrixPlacement

TrafficMatrixPlacement(name: 'str' = '', seed: 'int | None' = None, demand_set: str = '', failure_policy: str | None = None, iterations: int = 1, workers: int | Literal['auto'] = 'auto', failure_trace: bool = False, outputs: _netgraph_core.OutputOptions = <factory>, export_cost_distribution: bool = False, export_details: bool = False, alpha: float | None = None, alpha_from_step: str | None = None, failure_states: tuple[typing.Literal['converged', 'stale', 'repair'], ...] = ('converged',), interaction: Literal['ordered', 'simultaneous'] = 'ordered', *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `demand_set` (str)
- `failure_policy` (Union)
- `iterations` (int) = 1
- `workers` (Union) = auto
- `failure_trace` (bool) = False
- `outputs` (OutputOptions)
- `export_cost_distribution` (bool) = False
- `export_details` (bool) = False
- `alpha` (Union)
- `alpha_from_step` (Union)
- `failure_states` (tuple) = ('converged',)
- `interaction` (Literal) = ordered

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: dict, name: str) -> dict` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.workflow.tunnel_count_step

Evaluate each tunnelled TE demand of a set at fixed tunnel counts, design and offer.

### TunnelCountAnalysis

One native evaluation per demand and tunnel count (or ``up_to`` limit).

Every demand uses the same ``design_demand`` and ``offer``; the set's
declared volumes are not read by the rows, though they still take part in
choosing the resolution, as every demand set a step names does.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `demand_set` (str)
- `counts` (tuple) = ()
- `up_to` (Union)
- `design_demand` (Union)
- `offer` (Union)
- `workers` (Union) = auto
- `outputs` (OutputOptions)
- `export_details` (bool) = False

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `query(self, prepared: ngraph.analysis.preparation.PreparedScenario) -> ngraph.analysis.counts.TunnelCountQuery`
- `query_for(self, demands) -> ngraph.analysis.counts.TunnelCountQuery`
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: dict, name: str) -> dict` - Turn this step type's YAML keys into constructor arguments.

---

## ngraph.dsl.blueprints.expand

Blueprint and network DSL expansion.

Turns the `blueprints:` and `network:` sections into concrete Node and Link
objects: resolves blueprint instantiation and parameter overrides, expands
bracket patterns and `expand:` variable blocks, applies node and link rules,
and materializes `mesh`/`one_to_one` link patterns.

### Blueprint

Reusable blueprint for hierarchical sub-topologies.

A blueprint may contain multiple node definitions (each can have count
and template), plus link definitions describing how those nodes connect.

Attributes:
    name: Unique identifier of this blueprint.
    nodes: A mapping of node_name -> node definition.
    links: A list of link definitions.

**Attributes:**

- `name` (str)
- `nodes` (Dict[str, Any])
- `links` (List[Dict[str, Any]])

### DSLExpansionContext

Blueprint definitions and the Network populated during DSL expansion.

Attributes:
    blueprints: Dictionary of blueprint-name -> Blueprint.
    network: The Network into which expanded nodes/links are inserted.
    pending_bp_links: (link definition, parent path) pairs for blueprint
        links, expanded after node rules run.

**Attributes:**

- `blueprints` (Dict[str, Blueprint])
- `network` (Network)
- `pending_bp_links` (List[tuple[Dict[str, Any], str]]) = []

### expand_network_dsl(data: 'Dict[str, Any]') -> 'Network'

Expand a combined blueprint + network DSL into a Network.

Overall flow:
  1) Parse "blueprints" into Blueprint objects.
  2) Build a Network from "network" metadata (e.g. name, version).
  3) Expand 'network["nodes"]' (collect blueprint links for later).

- If a node group references a blueprint, incorporate that blueprint's

       nodes while merging parent's attrs + disabled + risk_groups.
       Blueprint links are deferred and processed after node rules.

- Otherwise, directly create nodes (a "direct node group").

  4) Process node rules (in order if multiple rules match).
  5) Expand deferred blueprint links.
  6) Expand link definitions in 'network["links"]'.
  7) Process link rules (in order if multiple rules match).

Field validation rules:

- Each structure rejects unrecognized keys.
- Link properties are flat (capacity, cost, etc. at link level).
- Node definitions accept count, template, attrs, disabled, risk_groups,

    nodes (nested groups), or blueprint and params (blueprint instances).

Args:
    data: The YAML-parsed dictionary containing optional "blueprints" + "network".

Returns:
    The expanded Network object with all nodes and links.

---

## ngraph.dsl.blueprints.parser

Parsing helpers for the network DSL.

Pure parsing/validation helpers, kept separate from the expansion module so
they can be tested independently and reused.

### check_link_keys(link_def: 'Dict[str, Any]', context: 'str') -> 'None'

Reject unrecognized link keys and require 'source' and 'target'.

### join_paths(parent_path: 'str', rel_path: 'str') -> 'str'

Join two path segments according to DSL conventions.

The DSL has no absolute paths. All paths are relative to the current
context (parent_path). A leading "/" on rel_path is stripped and has no
functional effect; it only marks that the path starts from the current
scope's root.

Examples:
    join_paths("", "/leaf") -> "leaf"
    join_paths("pod1", "/leaf") -> "pod1/leaf"
    join_paths("pod1", "leaf") -> "pod1/leaf"  (same result)

Args:
    parent_path: Parent path prefix (e.g., "pod1" when expanding a blueprint).
    rel_path: Path to join. Leading "/" is stripped if present.

Returns:
    "{parent_path}/{rel_path}", or rel_path alone when parent_path is empty.

---

## ngraph.dsl.expansion.brackets

Bracket expansion for name patterns.

`expand_name_patterns()` turns bracket expressions like "fa[1-3]" into
["fa1", "fa2", "fa3"].

### expand_name_patterns(name: 'str') -> 'List[str]'

Expand bracket expressions in a group name.

Supports:

- Ranges: [1-3] -> 1, 2, 3
- Lists: [a,b,c] -> a, b, c
- Mixed: [1,3,5-7] -> 1, 3, 5, 6, 7
- Multiple brackets: Cartesian product

Args:
    name: Name pattern with optional bracket expressions.

Returns:
    List of expanded names.

Examples:
    >>> expand_name_patterns("fa[1-3]")
    ['fa1', 'fa2', 'fa3']
    >>> expand_name_patterns("dc[1,3,5-6]")
    ['dc1', 'dc3', 'dc5', 'dc6']
    >>> expand_name_patterns("fa[1-2]_plane[5-6]")
    ['fa1_plane5', 'fa1_plane6', 'fa2_plane5', 'fa2_plane6']

### expand_risk_group_refs(rg_list: 'Union[List[str], Set[str], Tuple[str, ...]]') -> 'Set[str]'

Expand bracket patterns in a list of risk group references.

Args:
    rg_list: List, set, or tuple of risk group name patterns. Other
        iterables (including bare strings and generators) are rejected.

Returns:
    Set of expanded risk group names.

Raises:
    ValueError: If the container is not a list/set/tuple (a bare string
        would silently expand per character), or if an entry is not a
        string (e.g. a variable expansion substituted a non-string value).

Examples:
    >>> sorted(expand_risk_group_refs(["RG1"]))
    ['RG1']
    >>> sorted(expand_risk_group_refs(["RG[1-3]"]))
    ['RG1', 'RG2', 'RG3']
    >>> sorted(expand_risk_group_refs(["A[1-2]", "B[a,b]"]))
    ['A1', 'A2', 'Ba', 'Bb']

---

## ngraph.dsl.expansion.schema

Dataclasses describing template expansion configuration.

### ExpansionSpec

Specification for variable-based expansion.

Attributes:
    vars: Mapping of variable names to lists of values.
    mode: How to combine variable values.

- "cartesian": All combinations (default)
- "zip": Pair values by position

**Attributes:**

- `vars` (Dict[str, List[Any]]) = {}
- `mode` (Literal['cartesian', 'zip']) = cartesian

**Methods:**

- `from_dict(data: 'Dict[str, Any]') -> "Optional['ExpansionSpec']"` - Extract expand: block from dict.
- `is_empty(self) -> 'bool'` - Check if no variables are defined.

---

## ngraph.dsl.expansion.variables

Variable expansion for templates.

Substitutes $var and ${var} placeholders in strings, recursing into nested
structures.

### expand_block(block: 'Dict[str, Any]', spec: "Optional['ExpansionSpec']") -> 'Iterator[Dict[str, Any]]'

Expand a DSL block, yielding one dict per variable combination.

If no expand spec is provided or it has no vars, yields the original block.
Otherwise, yields a deep copy with all strings substituted for each
variable combination; the 'expand' key itself is removed from each copy.

Args:
    block: DSL block (dict) that may contain template strings.
    spec: Optional expansion specification.

Yields:
    Dict with variable substitutions applied.

### substitute_vars(obj: 'Any', var_dict: 'Dict[str, Any]') -> 'Any'

Recursively substitute $var and ${var} in all strings within obj.

A string consisting of exactly one placeholder (e.g. "${t}") is replaced
by the variable's native value, preserving its type. This keeps match
condition values comparable to non-string attributes (e.g. int tiers).
Placeholders embedded in longer strings (e.g. "dc${dc}_internal") are
interpolated as text, so the result is a string.

Args:
    obj: Any value (string, dict, list, or primitive).
    var_dict: Mapping of variable names to values.

Returns:
    obj with placeholders substituted. Dicts and lists are rebuilt, not
    mutated.

Raises:
    KeyError: If a placeholder names a variable absent from var_dict.

---

## ngraph.dsl.inputs

Closed YAML declarations for native routing and named physical references.

### boolean(value, label)

No documentation available.

### ceiling(value, label)

No documentation available.

### closed(value, keys, label)

No documentation available.

### controller_declarations(data)

The routing domain, the WCMP controller and the forwarding groups, if declared.

### demand_sets(raw)

No documentation available.

### directed(value, label)

No documentation available.

### enum(kind, value, label)

No documentation available.

### flow_outputs(arguments, name)

A flow step's YAML ``outputs`` as native options, cost and detail flags.

### mapping(value, label)

No documentation available.

### named_declarations(data)

Own the three separate namespaces without resolving physical identities yet.

### names(value, label, *, nonempty=False)

No documentation available.

### outputs(raw, label)

No documentation available.

### policy(value, label)

Parse one discriminated model, retaining physical T1 minimum until q is fixed.

### tunnel_count(value, label)

No documentation available.

---

## ngraph.dsl.loader

YAML loader + schema validation for Scenario DSL.

`load_scenario_yaml` parses a YAML string, validates it against the packaged
JSON schema, and returns the dictionary for expansion and parsing.

### load_scenario_yaml(yaml_str: 'str') -> 'Dict[str, Any]'

Load and validate a Scenario YAML string.

Returns the parsed dictionary with schema shape enforced. Section builders
normalize YAML-specific quirks such as boolean-like keys.

Raises:
    ValueError: If the top level is not a mapping, or a network, link, or
        risk group entry has the wrong shape (checked before the schema
        for clearer messages).
    jsonschema.ValidationError: If the data does not match the packaged
        schema, including unrecognized top-level keys.

---

## ngraph.profiling.profiler

Profiling for NetGraph workflow execution.

Times each workflow step (CPU and wall clock) with ``cProfile`` and can record
peak memory with ``tracemalloc``. Steps that take more than 10% of total wall
time are reported as bottlenecks.

### PerformanceProfiler

CPU profiler for NetGraph workflow execution.

Profiles each workflow step with cProfile and flags steps that take more
than 10% of total wall time as bottlenecks.

**Methods:**

- `analyze_performance(self) -> 'None'` - Flag steps above 10% of total wall time and fill ``analysis_summary``.
- `end_scenario(self) -> 'None'` - Record total wall time and sum CPU time and calls across steps.
- `profile_step(self, step_name: 'str', step_type: 'str') -> 'Generator[None, None, None]'` - Profile the enclosed block as one workflow step.
- `start_scenario(self) -> 'None'` - Record the scenario start time.

### PerformanceReporter

Render profiling results as a plain-text report.

Covers per-step timing, bottleneck identification, and tuning suggestions.

**Methods:**

- `generate_report(self) -> 'str'` - Render the full report.

### ProfileResults

Profiling results for a scenario execution.

Attributes:
    step_profiles: List of individual step performance profiles.
    total_wall_time: Total wall-clock time for entire scenario.
    total_cpu_time: Total CPU time across all steps.
    total_function_calls: Total function calls across all steps.
    bottlenecks: List of performance bottlenecks (>10% execution time).
    analysis_summary: Aggregate metrics computed by ``analyze_performance``.

**Attributes:**

- `step_profiles` (List[StepProfile]) = []
- `total_wall_time` (float) = 0.0
- `total_cpu_time` (float) = 0.0
- `total_function_calls` (int) = 0
- `bottlenecks` (List[Dict[str, Any]]) = []
- `analysis_summary` (Dict[str, Any]) = {}

### StepProfile

Performance profile data for a single workflow step.

Attributes:
    step_name: Name of the workflow step.
    step_type: Class name of the workflow step.
    wall_time: Total wall-clock time in seconds.
    cpu_time: CPU time in seconds (sum of cProfile internal times).
    function_calls: Number of function calls during execution.
    memory_peak: Peak traced memory in bytes; None unless memory
        tracking ran for this step.
    cprofile_stats: cProfile statistics for this step.

**Attributes:**

- `step_name` (str)
- `step_type` (str)
- `wall_time` (float)
- `cpu_time` (float)
- `function_calls` (int)
- `memory_peak` (Optional[float])
- `cprofile_stats` (Optional[pstats.Stats])

---

## ngraph.utils.output_paths

Utilities for building CLI artifact output paths.

Every artifact path the NetGraph CLI writes is composed here, from an optional
output directory, a prefix (usually derived from the scenario file or results
file), and a per-artifact suffix.

### build_artifact_path(output_dir: 'Path', prefix: 'str', suffix: 'str') -> 'Path'

Compose an artifact path as output_dir / (prefix + suffix).

Args:
    output_dir: Base directory for outputs.
    prefix: Filename prefix; usually derived from scenario or results stem.
    suffix: Per-artifact suffix including the dot (e.g. ".results.json").

Returns:
    The composed path.

### ensure_parent_dir(path: 'Path') -> 'None'

Create the parent directory of ``path`` if it is missing.

### resolve_override_path(override: 'Optional[Path]', output_dir: 'Optional[Path]') -> 'Optional[Path]'

Resolve an override path with respect to an optional output directory.

- Absolute override paths are returned as-is.
- Relative override paths are interpreted as relative to ``output_dir``

  when provided; otherwise relative to the current working directory.

Args:
    override: Path provided by the user to override the default.
    output_dir: Optional base directory for relative overrides.

Returns:
    The resolved path or None if no override was provided.

### results_path_for_run(scenario_path: 'Path', output_dir: 'Optional[Path]', results_override: 'Optional[Path]') -> 'Path'

Determine the results JSON path for the ``run`` command.

Behavior:

- If ``results_override`` is provided, return it (resolved relative to

  ``output_dir`` when that is specified, otherwise as-is).

- Else if ``output_dir`` is provided, return ``output_dir/<prefix>.results.json``.
- Else, return ``<scenario_stem>.results.json`` in the current working directory.

Args:
    scenario_path: The scenario YAML file path.
    output_dir: Optional base output directory.
    results_override: Optional explicit results file path.

Returns:
    The path where results should be written.

### scenario_prefix_from_path(scenario_path: 'Path') -> 'str'

Return the artifact filename prefix for a scenario file.

Args:
    scenario_path: The scenario YAML file path.

Returns:
    The filename without its final extension (``Path.stem``).

---

## ngraph.utils.seed_manager

Deterministic seed derivation to avoid global random.seed() order dependencies.

### SeedManager

Derives per-component seeds from one master seed.

A global random.seed() makes each component's random draws depend on what
ran before it. SeedManager hashes the master seed with component
identifiers (SHA-256), so a component's seed does not depend on execution
order or parallelism.

Usage:
    seed_mgr = SeedManager(42)
    failure_seed = seed_mgr.derive_seed("failure_policy", "default")

**Methods:**

- `derive_seed(self, *components: 'Any') -> 'Optional[int]'` - Derive a deterministic seed from master seed and component identifiers.

---

## ngraph.utils.values

Validation of domain input values and their immutable JSON form.

### exact_fraction(value: 'object', label: 'str') -> 'Fraction'

An exact ratio from an integer, a ``p/q`` or decimal string, or a Fraction.

Floats and booleans are refused: a binary64 value is not the exact ratio
the declaration means.

### frozen_attrs(value: 'object', label: 'str' = 'attrs') -> 'dict[str, JSONValue]'

Validate an attribute mapping once and return its read-only JSON form.

### frozen_dict(items: 'Mapping[Any, Any]' = {}) -> 'dict'

Return a read-only dict holding the given references.

### frozen_json(value: 'object', label: 'str' = 'attrs', *, strict_objects: 'bool' = False) -> 'JSONValue'

Validate finite JSON data and return it in read-only form.

Accepted scalar subclasses become their plain built-in values and mapping
keys become plain strings. Mappings (only dicts with ``strict_objects``)
become read-only dicts and lists become read-only lists. A read-only
container is checked like any other, since record collections share its
type, and is shared when its contents are already in that form.

### integer(value: 'object', label: 'str', *, minimum: 'int' = 0, maximum: 'int | None' = None) -> 'int'

Validate exact integer domain inputs without accepting booleans.

### json_copy(value: 'object', label: 'str' = 'attrs', *, strict_objects: 'bool' = False) -> 'JSONValue'

Validate finite JSON data and return an editable plain copy.

### own_scalars(record: 'object', label: 'str', names: 'tuple[str, ...]') -> 'None'

Normalize the named scalar fields of a record during its construction.

### owned_dict(items: 'Mapping[Any, Any]', label: 'str') -> 'dict'

Return a read-only dict of the given references under plain built-in keys.

### physical(value: 'object', label: 'str', *, positive: 'bool' = False) -> 'float'

Promote a finite nonnegative physical input to binary64.

### scalar(value: 'Any', label: 'str') -> 'Any'

Store a scalar field as its exact built-in value; refuse other scalar types.

None, bool, int, float, str and Enum members are kept; a subclass of str,
int or float becomes its stored built-in value; anything else (a NumPy
scalar, for example) is refused with the field's label.

### shared_copy(self, memo=None)

Copies of an immutable record share it, with the native values it holds.

---

## ngraph.utils.yaml_utils

Helpers for YAML parsing quirks and configuration key checks.

### check_no_extra_keys(data: Mapping[Any, Any], allowed: AbstractSet[str], context: str) -> None

Raise if ``data`` has keys outside ``allowed``; they would be ignored.

Args:
    data: Mapping parsed from configuration.
    allowed: Recognized keys.
    context: Short description of ``data`` used in the error message.

Raises:
    ValueError: If ``data`` contains any key not in ``allowed``.

### normalize_yaml_dict_keys(data: Dict[Any, ~V]) -> Dict[str, ~V]

Convert YAML-parsed dictionary keys to strings.

YAML 1.1 parses true/false/yes/no/on/off keys as Python booleans. Those
become "True"/"False"; every other key is coerced with str().

Args:
    data: Dictionary that may contain boolean or other non-string keys from YAML parsing

Returns:
    New dictionary with str() keys.

Examples:
    >>> normalize_yaml_dict_keys({True: "value1", False: "value2", "normal": "value3"})
    {"True": "value1", "False": "value2", "normal": "value3"}

    >>> # In YAML: true:, yes:, on: all become Python True
    >>> # In YAML: false:, no:, off: all become Python False

---

## ngraph.analysis.capacity

Named capacity questions evaluated directly by the native evaluators.

### CapacityQuery

CapacityQuery(source: 'Selector', target: 'Selector', config: 'ngc.FlowPolicyConfig' = <factory>, mode: "Literal['combine', 'pairwise']" = 'combine', offer: 'float | None' = None, design_demand: 'float | None' = None, failures: 'FailureRequest | None' = None, workers: 'Workers' = 'auto', outputs: 'ngc.OutputOptions' = <factory>, export_cost_distribution: 'bool' = False, export_details: 'bool' = False, declaration: 'object' = None)

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `config` (ngc.FlowPolicyConfig) = FlowPolicyConfig(routing=CentralizedTE(source_allocation=SourceAllocation.OPTIMIZED), admission=Admission.LOSSLESS)
- `mode` (Literal['combine', 'pairwise']) = combine
- `offer` (float | None)
- `design_demand` (float | None)
- `failures` (FailureRequest | None)
- `workers` (Workers) = auto
- `outputs` (ngc.OutputOptions)
- `export_cost_distribution` (bool) = False
- `export_details` (bool) = False
- `declaration` (object)

### capacity(prepared: 'PreparedScenario', query: 'CapacityQuery') -> 'CapacityAnalysis'

No documentation available.

### evaluate(topology, query: 'CapacityQuery', native_pairs, options, workers: 'int')

Evaluate each pair once with the native evaluator the question names.

### evaluation_options(topology, config, offer, design, mask, outputs)

No documentation available.

### maximum_config() -> 'ngc.FlowPolicyConfig'

No documentation available.

### question_kind(config, offer, design)

Name the actual native evaluator question and its offer source.

### question_pairs(prepared: 'PreparedScenario', query: 'CapacityQuery', label: 'str')

The question's endpoint pairs; the evaluated ones, indexed; their native
ids; and the pool of each pooled one, by index.

A singleton self pair is not evaluated. A pooled pair starts at its pool head.

### validate_capacity_inputs(source, target, config, offer, design, outputs) -> 'None'

No documentation available.

---

## ngraph.analysis.controller

The WCMP controller: one destination-wide weight table per demand set and destination.

A routing domain (an IGP domain and the BGP-edge routers around it) gives
each destination one DAG of routes. The controller programs the source
routers of the ``SHORTEST_PATHS_WCMP`` demands toward that destination:
``next_hop`` weights their next hops by progressive filling, ``group`` uses
their declared forwarding groups, whose root shares are fixed caps. Every
other router keeps equal-cost splitting (ECMP). Each demand forwards on the
one table through its own native program; nothing here forwards traffic.

### ControllerSetup

The controller declaration resolved on one prepared graph.

**Attributes:**

- `scope` (str)
- `domain` (frozenset[int])
- `edge` (frozenset[int])
- `trees` (Mapping[int, tuple[str, ForwardingGroup, tuple[DirectedLink, ...]]])

**Methods:**

- `case_tables(self, topology, demands, mask, *, repair=False, context='')` - Each destination's table of a demand set in one failure case.
- `check_failure_states(self, topology, demands, states, label)` - Refuse group converged and repair at a programmed router inside the domain.
- `check_leaf(self, topology: 'PreparedTopology', endpoints: 'Endpoints', label)` - Refuse a programmed demand the declared domain cannot place.
- `leaf_config(self, topology: 'PreparedTopology', table: 'DestinationTable', endpoints, black_holes: 'ngc.Eligibility | None' = None) -> 'ngc.FlowPolicyConfig'` - One demand's native program on the shared table, with its own endpoints.
- `tables(self, topology, set_name, consumers)` - One table and its report per destination of a demand set.

### DestinationTable

The controller's table toward one destination, on one prepared graph.

``weights`` is the one weight vector, by EdgeId: programmed rows carry
their integer weights, other DAG routers weight 1 on every member.
``encoding`` is how the table reaches native forwarding (EQUAL when every
programmed row that receives traffic is equal and positive).
``approximations`` hold each router whose exact weights reached 2^62, with
the largest relative error of its apportioned shares; for ``all_routers``,
the one source vector's entry names the source with the largest error.
``source_weights`` holds each ``all_routers`` source's nominal physical
demand and its integer weight. ``leaves`` are the (sources, exact amount)
the table was built from, so a failure case can build its own.

A failure case's group table keeps a dead root group's members at their
nominal shares: ``dropped`` are those members, where its forwarding drops
the traffic (``holes`` excludes them), and ``dead_caps`` the dead groups.

**Attributes:**

- `destination` (int)
- `dag` (ngc.PredecessorDAG)
- `weights` (tuple[int, ...])
- `encoding` (ngc.RouteAllocation)
- `programmed` (tuple[int, ...])
- `approximations` (tuple[WeightApproximation, ...])
- `source_weights` (tuple[tuple[int, Fraction, int], ...] | None)
- `leaves` (tuple[tuple[tuple[int, ...], Fraction], ...]) = ()
- `dropped` (tuple[int, ...]) = ()
- `dead_caps` (tuple[DeadCap, ...]) = ()
- `holes` (ngc.Eligibility | None)

### apportion(exact: 'Sequence[int]', total: 'int') -> 'list[int]'

Highest averages over ``total`` units with one unit reserved per positive member.

Equal to giving every positive member one unit, then each further unit to
the largest ``weight / (held + 1)``, earlier member on ties; computed from
the proportional floor, then adjusted by the same quotients.

### apportioned(shares: 'Sequence[Fraction]') -> 'tuple[list[int], dict[int, Fraction]]'

Exact rational shares as reduced integers, and their errors by member.

Weights that reach 2^62 are apportioned over a total of 2^62 - 1: every
positive member first holds one unit, then each unit goes to the largest
``share / (held + 1)``, earlier member on ties. The second value holds each
positive member's relative error of its normalized share (empty when exact).

### compile_setup(topology: 'PreparedTopology', scenario) -> 'ControllerSetup'

Resolve the domain populations and check every forwarding group once.

### destination_table(topology, setup, set_name, t, leaves, mask, *, nominal: 'DestinationTable | None' = None, repair=False, context='') -> 'tuple[DestinationTable, dict[int, list[int]]]'

The one table toward t and its members by router, from the leaves' (sources, exact amount).

``next_hop`` and ``group`` program the sources of positive leaves,
downstream first; ``all_routers`` programs every router from one flow.
A failure case's group table passes its ``nominal`` table: dead root
groups keep their caps (`_group_shares`), and with ``repair`` the routes
are the nominal ones that survive the mask instead of a new search.

### encode(topology, members, programmed, rows, weights) -> 'ngc.RouteAllocation'

EQUAL when every programmed row that receives traffic is equal and positive.

Otherwise WEIGHTED, which prunes zero-capacity members and dead branches.
Zero-alone members carry weight 0 and a root group with no live member is
refused, so no router that receives traffic keeps a member WEIGHTED prunes.

### fill(columns: 'Sequence[Mapping[int, Fraction]]', alone, capacity)

Normalized progressive filling of one router's members.

Every active member grows in proportion to what it carries alone; when an
edge saturates, every active member using it stops. Members that carry
nothing alone get 0.

### flatten(tree: 'ForwardingGroup', members: 'Mapping', alive: 'Mapping') -> 'list[Fraction]'

Each member's share of the router's traffic under the fixed root caps.

``members`` maps each declared leaf ``DirectedLink`` to its index; each
root group re-flattens over its live members only, within its own cap.
The caller refuses a positive root group with no live member.

### integer_weights(shares: 'Sequence[Fraction]') -> 'tuple[list[int], Fraction | None]'

``apportioned`` with the largest relative error (None when exact).

### member_column(graph, rows, edge, t) -> 'tuple[dict[int, Fraction], Fraction]'

The load one unit entering ``edge`` puts on every edge, and what it carries alone.

``rows`` are the table's rows so far: finalized programmed rows, and every
member at other routers. A unit that meets a zero-capacity edge, or stops
at a router other than t with no member, carries nothing alone.

### surviving_dag(graph, dag, mask, t) -> 'ngc.PredecessorDAG'

The DAG's edges the mask keeps that still lead to t (native repair's pruning).

### table_report(topology: 'PreparedTopology', table: 'DestinationTable', members) -> 'TableReport'

The table by name; ``members`` are its DAG's members by router.

---

## ngraph.analysis.costs

Opt-in exact path-cost bins or native marginal-cost pieces.

### cost_distribution(topology: ngraph.analysis.topology.PreparedTopology, config: _netgraph_core.FlowPolicyConfig, result: _netgraph_core.PlacementResult, destinations, mask: _netgraph_core.Eligibility, *, pool=None, records=None, shortest_costs=None, programmed=False) -> tuple[ngraph.results.DeliveredByPathCost | ngraph.results.MarginalCurve | None, collections.abc.Mapping[typing.Literal['cost_distribution'], typing.Literal['mixed_cost_dag', 'unsupported_model', 'controller_table']]]

Project only determined costs; callers invoke this only when requested.

A demand the WCMP controller ``programmed`` forwards on a pooled table,
which does not attribute delivery to walk costs.

---

## ngraph.analysis.counts

Tunnel-count questions: one fresh native T2 evaluation per demand and count.

Every row evaluates one demand's declared centralized-TE model with the
row's tunnel count (or "up to" limit), LOSSY at the query's offer and with
its design demand; the plan, delivery and losses are the native result's.
Every demand of the set uses the same design and offer.

### TunnelCountQuery

TunnelCountQuery(demands: 'ResolvedDemandSet', counts: 'tuple[int, ...]', design_demand: 'float', offer: 'float', up_to: 'int | None' = None, eligibility: 'ngc.Eligibility | None' = None, workers: 'Workers' = 'auto', outputs: 'ngc.OutputOptions' = <factory>, export_details: 'bool' = False)

**Attributes:**

- `demands` (ResolvedDemandSet)
- `counts` (tuple[int, ...])
- `design_demand` (float)
- `offer` (float)
- `up_to` (int | None)
- `eligibility` (ngc.Eligibility | None)
- `workers` (Workers) = auto
- `outputs` (ngc.OutputOptions)
- `export_details` (bool) = False

### count_splits(prepared: 'PreparedScenario', query: 'TunnelCountQuery', label, mask)

The rows' split constraints, declared from the offer, design and live heads.

One reverse search per demand finds its live heads for all its rows; no
traffic is solved.

### tunnel_counts(prepared: 'PreparedScenario', query: 'TunnelCountQuery') -> 'TunnelCountAnalysis'

No documentation available.

---

## ngraph.analysis.demands

Canonical physical selections and total-preserving demand expansion.

### bind_plans(topology: 'PreparedTopology', named: 'NamedRoutes', name: 'str', plans: 'Sequence[_Expansion]', controller=None) -> 'ResolvedDemandSet'

Bind a demand set's leaves; ``controller`` is the prepared controller setup.

The controller's tables are built once per destination, from every
programmed leaf of the set, before any leaf's program.

### controlled(controller, policy) -> 'bool'

Whether the WCMP controller programs a demand of this declared policy.

### declared_split(named: 'NamedRoutes', config: 'ngc.FlowPolicyConfig | None', policy: 'object' = None) -> 'tuple[ngc.RouteAllocation | None, ngc.WeightBasis | None]'

The route allocation and weight basis a declared model splits by.

Shortest paths report their native allocation and, when weighted, its
basis. A named pinned declaration reports them only when one of its
routes is a support DAG (any other allocation counts as equal). Other
models split by neither.

### expand_units(root: 'ExpansionSplit | ExpansionLeaf', total: 'int') -> 'tuple[tuple[ExpansionLeaf, int], ...]'

No documentation available.

### expansion_plans(network: 'Network', specs: 'DemandSet') -> 'tuple[_Expansion, ...]'

Resolve physical endpoints once; zero and discarded leaves remain in the tree.

### leaf_amounts(root, volume: 'float') -> 'dict[str, Fraction]'

Each leaf's exact physical share of its declaration, before any rounding.

### leaves(root: 'ExpansionSplit | ExpansionLeaf') -> 'tuple[ExpansionLeaf, ...]'

No documentation available.

### materialize_config(topology: 'PreparedTopology', named: 'NamedRoutes', endpoints: 'Endpoints', policy) -> 'ngc.FlowPolicyConfig'

No documentation available.

### offer_budgets(offers, q) -> 'dict[str, int]'

Each pool leaf's largest fixed offer in units over (plans, offer, label).

### pool_budgets(scaled, q) -> 'dict[str, int]'

Each pool leaf's largest request in units over the (plan, alpha) pairs.

The run's own expansion: the parent scaled and quantized once, then split.

### pool_requirements(plans: 'Sequence[_Expansion]') -> 'dict[str, tuple[str, ...]]'

No documentation available.

### pooled(mode: 'str', declaration: 'object') -> 'bool'

Whether a question's combined sources are a pool.

### refuse_overlap(sources: 'Sequence[str]', destinations: 'Sequence[str]', label: 'str') -> 'None'

No documentation available.

### residual_weights(named: 'NamedRoutes', parents) -> 'bool'

Whether any declared demand weights its split by the residual snapshot.

### resolve_demands(prepared: 'PreparedScenario', specs: 'DemandSet') -> 'ResolvedDemandSet'

No documentation available.

### scaled_expansion(demands: 'ResolvedDemandSet', alpha: 'float', q: 'float') -> 'tuple[Mapping[str, int], tuple[ExpansionAccounting, ...]]'

Rescale physical parents; retain exact discard accounting and zero leaves.

### selected_groups(network: 'Network', selector: 'Selector', label: 'str') -> 'dict[str, tuple[str, ...]]'

No documentation available.

### selected_pairs(network: 'Network', source: 'Selector', target: 'Selector', mode: 'str', label: 'str') -> 'tuple[Endpoints, ...]'

One shared selection/overlap rule for capacity, paths and sensitivity.

---

## ngraph.analysis.failures

Canonical failure draws, graph-owned cases and independent-case scheduling.

### FailureRequest

One failure sampling question.

``policy_name`` names a scenario's policy in the recorded question (an
unnamed policy is recorded inline); ``seed_source`` records where a given
``seed`` came from.

**Attributes:**

- `policy` (FailurePolicy | None)
- `iterations` (int) = 1
- `seed` (int | None)
- `failure_trace` (bool) = False
- `policy_name` (str | None)
- `seed_source` (Literal['query', 'step', 'scenario']) = query

### failure_cases(prepared: 'PreparedScenario', request: 'FailureRequest | None') -> 'tuple[FailureCase, ...]'

The baseline, then each distinct drawn pattern with its draw count.

### resolve_workers(workers: 'Workers') -> 'int'

No documentation available.

### sampling_metadata(request: 'FailureRequest | None') -> 'SamplingMetadata | None'

No documentation available.

### schedule_cases(cases: 'tuple[_Job, ...]', solve: 'Callable[[_Job], _Result]', workers: 'int') -> 'tuple[_Result, ...]'

Publish in case order; all worker cleanup completes before an error leaves.

---

## ngraph.analysis.metadata

Producer identity captured once from the actual imported extension.

### analysis_metadata(workers: int, failures: ngraph.analysis.failures.FailureRequest | None = None) -> ngraph.results.AnalysisMetadata

No documentation available.

### run_metadata(seed: int | None = None) -> ngraph.results.RunMetadata

No documentation available.

---

## ngraph.analysis.msd

Bounded physical-alpha search on one persistent native policy roster.

### MSDQuery

MSDQuery(demands: 'ResolvedDemandSet', alpha_start: 'float' = 1.0, growth_factor: 'float' = 2.0, alpha_min: 'float' = 1e-06, alpha_max: 'float' = 1000000000.0, alpha_tolerance: 'float' = 0.01, max_bracket_iters: 'int' = 32, max_bisect_iters: 'int' = 32, export_probe_rows: 'bool' = False, export_details: 'bool' = False)

**Attributes:**

- `demands` (ResolvedDemandSet)
- `alpha_start` (float) = 1.0
- `growth_factor` (float) = 2.0
- `alpha_min` (float) = 1e-06
- `alpha_max` (float) = 1000000000.0
- `alpha_tolerance` (float) = 0.01
- `max_bracket_iters` (int) = 32
- `max_bisect_iters` (int) = 32
- `export_probe_rows` (bool) = False
- `export_details` (bool) = False

### maximum_supported_demand(prepared: 'PreparedScenario', query: 'MSDQuery') -> 'MSDAnalysis'

No documentation available.

---

## ngraph.analysis.paths

Named SPF/KSP selection and the declared cross-pair merge.

### PathQuery

PathQuery(source: 'Selector', target: 'Selector', mode: "Literal['combine', 'pairwise']" = 'combine', options: 'ngc.SpfOptions | ngc.KspOptions' = <factory>, costs_only: 'bool' = False, max_paths: 'int | None' = None, split_parallel_edges: 'bool | None' = None)

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `mode` (Literal['combine', 'pairwise']) = combine
- `options` (ngc.SpfOptions | ngc.KspOptions)
- `costs_only` (bool) = False
- `max_paths` (int | None)
- `split_parallel_edges` (bool | None)

### paths(prepared: 'PreparedScenario', query: 'PathQuery') -> 'PathAnalysis'

No documentation available.

---

## ngraph.analysis.placement

Ordered native policy actions and explicit ledger ownership.

### PlacementQuery

PlacementQuery(demands: 'ResolvedDemandSet', alpha: 'float' = 1.0, failures: 'FailureRequest | None' = None, workers: 'Workers' = 'auto', outputs: 'ngc.OutputOptions' = <factory>, export_cost_distribution: 'bool' = False, export_details: 'bool' = False, alpha_from_step: 'str | None' = None, states: 'tuple[StateName, ...]' = ('converged',), interaction: "Literal['ordered', 'simultaneous']" = 'ordered')

**Attributes:**

- `demands` (ResolvedDemandSet)
- `alpha` (float) = 1.0
- `failures` (FailureRequest | None)
- `workers` (Workers) = auto
- `outputs` (ngc.OutputOptions)
- `export_cost_distribution` (bool) = False
- `export_details` (bool) = False
- `alpha_from_step` (str | None)
- `states` (tuple[StateName, ...]) = ('converged',)
- `interaction` (Literal['ordered', 'simultaneous']) = ordered

### place(prepared: 'PreparedScenario', query: 'PlacementQuery') -> 'PlacementAnalysis'

No documentation available.

### policy_roster(topology: 'PreparedTopology', demands: 'Sequence[ResolvedDemand]', mask: 'ngc.Eligibility', entries=None) -> 'tuple[ngc.FlowLedger, tuple[ngc.FlowPolicy, ...]]'

Create one private ledger and stable policy identities for a case or series.

``entries`` give each demand its own (config, eligibility, request);
otherwise every demand uses its declared config under ``mask``.

### remove_policies(policies: 'Sequence[ngc.FlowPolicy]') -> 'None'

Release every owner explicitly; destruction is not a cleanup operation.

### replace_matrix(ledger: 'ngc.FlowLedger', policies: 'Sequence[ngc.FlowPolicy]', requests: 'Sequence[int]', outputs: 'ngc.OutputOptions | None' = None) -> 'tuple[ngc.PlacementResult, ...]'

Remove the whole previous matrix, then submit full Replace requests once.

### state_names(value, label) -> 'tuple[StateName, ...]'

Requested failure states: nonempty and unique, held in canonical order.

---

## ngraph.analysis.precision

Local split-precision constraints of native observations, under one set of rules.

A placed demand and an evaluated capacity question split traffic by the same
rules: sources share a demand equally, tunnels share a head, and DAG routers
share their incoming amount by allocation and weights. The rules read their
facts from one of two observers: a placement's native records, or the
searches a capacity evaluator would make on an empty ledger.

### dag_bounds(topology, dags, injections, destinations, allocation, weights, label, precision, *, allowed_edges=None)

Rational split propagation over native-selected DAGs, without capacity/admission.

### effective_rows(topology, edges, destinations, allocation, weights)

Native preparation's split rows over a set of DAG edges.

Native W prunes zero-capacity members even for positive EXPLICIT weights,
then removes branches with no effective continuation to a destination;
EQUAL keeps every member. Returns each router's members in EdgeId order,
with their weights (1 for EQUAL).

### expansion_bounds(plans, q, precision, alpha=1.0)

Describe continuous declared splits on the fixed ordered tree.

### observed_inputs(prepared: 'PreparedScenario', inputs)

Reuse exact prepared atoms; scaled or query-local atoms remain local.

### placement_inputs(prepared: 'PreparedScenario', demands, alpha)

The input observations shared by cases of one fixed-alpha question.

### placement_miss(prepared: 'PreparedScenario', demands, owners, results, records, mask, alpha, location, observations, tables=None, ordered=True) -> 'PrecisionMiss | None'

The missed local targets of one placement on the fixed prepared q.

``tables`` are a failure case's controller tables by destination.

### placement_splits(topology: 'PreparedTopology', named: 'NamedRoutes', demands, owners, results, record_sets, mask, alpha, precision, tables=None, ordered=True)

Describe actual native records; never rerun a placement to obtain a report.

A row is described by its demand's declared model, from the participant's
records. A controlled row is described from its table: the set's nominal
one, or the case's own (``tables``, by destination). Under a SIMULTANEOUS
list (not ``ordered``) every participant was prepared on one common view.

### propagate(graph, rows, injections, *, reached_only=False)

Exact rational propagation of injected amounts through split rows.

``rows`` maps a router to its members (EdgeId, positive weight); a router
splits what it holds in proportion to the weights. Returns the nodes in
processing order (with ``reached_only``, only those the injections reach),
the amount each node holds and the amount on each edge. Amounts at a node
without a row stay there (a destination, or a loss).

### query_has_splits(query) -> 'bool'

Whether this native allocation has local split constraints at all.

### query_inputs(prepared: 'PreparedScenario', query, label)

The input observations of one capacity question, shared by its cases.

### query_miss(prepared: 'PreparedScenario', query, observations, location, inputs) -> 'PrecisionMiss | None'

The missed local targets of one capacity question's evaluations.

``observations`` holds (pair, delivered units, eligibility, label, pool)
rows.

### query_splits(topology, named, query, pair, delivered, mask, label, precision, pool=None, facts=None)

Describe this native evaluation's splits, without another traffic solve.

``facts`` reuses one pair's searches across questions that differ only in
their tunnel count.

### question_inputs(offer, design_demand, declaration)

A capacity question's physical atoms, by field, known before evaluation.

### split_constraint(kind: "Literal['expansion', 'source', 'router', 'tunnel']", label: 'str', incoming: 'Fraction', members: 'int', q: 'float', precision: 'float') -> 'SplitConstraint'

Record a local split bound without solving admission or forwarding.

---

## ngraph.analysis.preparation

Assemble one prepared graph, unit and demand binding for a scenario's questions.

Preparation decides what is asked (which steps, demand sets and capacity
questions are active) and observes each candidate resolution once; the units
module calculates conversions, reports and the choice of resolution.

### PreparedScenario

One graph, unit and demand binding over a read-only view of a scenario.

``units_report`` is the nominal preparation's report; each analysis
returns its own precision misses beside it.

**Attributes:**

- `scenario` (Scenario)
- `topology` (PreparedTopology)
- `demand_sets` (Mapping[str, ResolvedDemandSet])
- `units_report` (UnitsReport)
- `_named` (NamedRoutes)
- `_membership` (MembershipIndex)
- `_inputs` (Mapping[str, tuple[_InputKind, float]])
- `_input_observations` (Mapping[str, tuple[InputQuantization, InputConstraint | None]])
- `_steps` (tuple[tuple[str, int | None, SeedSource], ...])
- `_controller` (ControllerSetup | None)

### StepNeeds

What preparation must know of one workflow step's question.

``numerical`` steps are evaluated at the prepared resolution. A step may
name a demand set to bind, a failure policy, and an earlier step whose
feasible alpha it uses (one that ``provides_alpha``). ``capacity`` builds
the step's capacity question, which preparation evaluates once per
candidate resolution; ``inputs`` are that question's physical amounts, by
field name. ``pool_endpoints`` are the source and target of a question
whose combined sources are a pool: preparation gives them a private head.
``offer_budget`` is a fixed lossy offer every pool leaf of ``demand_set``
receives; ``counts`` builds a tunnel-count question, whose split targets
preparation observes once per candidate resolution.

**Attributes:**

- `numerical` (bool) = False
- `demand_set` (str | None)
- `failure_policy` (str | None)
- `states` (tuple[str, ...]) = ()
- `interaction` (str) = ordered
- `alpha` (float | None) = 1.0
- `alpha_from_step` (str | None)
- `provides_alpha` (bool) = False
- `capacity` (Callable[[PreparedScenario], CapacityQuery] | None)
- `inputs` (Mapping[str, tuple[_InputKind, float]]) = {}
- `pool_endpoints` (tuple[Selector, Selector] | None)
- `offer_budget` (float | None)
- `counts` (Callable[[PreparedScenario], TunnelCountQuery] | None)

### prepare_scenario(scenario: 'Scenario', settings: 'UnitsSettings', requested: 'tuple[str, ...]') -> 'PreparedScenario'

Prepare a read-only scenario view; the steps' needs decide what is bound.

---

## ngraph.analysis.programs

Resolve declared physical routes, supports and weights into native programs.

### compile_named(topology, *, routes=None, supports=None, weights=None)

Validate all named references and own one native value per graph/name.

### dag_from_edges(graph: 'ngc.Graph', edges) -> 'ngc.PredecessorDAG'

One native DAG over a set of EdgeIds; validation (cycles included) is native.

### domain_dag(topology: 'PreparedTopology', domain: 'frozenset[int]', edge: 'frozenset[int]', destination: 'int', mask: 'ngc.Eligibility') -> 'ngc.PredecessorDAG'

The routes toward one BGP-edge destination through one IGP domain.

Exits are domain nodes with an eligible link to the destination; one
reverse search from all of them, inside the domain and blind to capacity,
gives each domain node its nearest exits. The DAG adds every eligible exit
link and every eligible uplink from another BGP-edge node into a domain
node that reaches an exit; nothing enters a BGP-edge node but the
destination, so no other one carries transit. No exit gives an empty DAG.

### edge_id(topology: 'PreparedTopology', ref: 'DirectedLink', label: 'str') -> 'int'

No documentation available.

### explicit_weights(topology: 'PreparedTopology', spec: 'WeightSpec', label: 'str') -> 'tuple[int, ...]'

Unlisted edges have weight zero; duplicates are errors, never summed.

### hop_index(topology: 'PreparedTopology') -> 'dict[tuple[int, int], int]'

The cheapest enabled physical edge of each node pair, by (cost, link, direction).

### pinned_config(topology: 'PreparedTopology', endpoints: 'Endpoints', declaration: 'PinnedRoutes', named: 'NamedRoutes') -> 'ngc.FlowPolicyConfig'

No documentation available.

### route_definition(topology: 'PreparedTopology', spec: 'RouteSpec', supports: 'Mapping[str, ngc.PredecessorDAG]', hops_by_pair: 'Mapping[tuple[int, int], int]', label: 'str') -> 'ngc.RouteDefinition'

No documentation available.

### support_dag(topology: 'PreparedTopology', spec: 'SupportSpec', label: 'str') -> 'ngc.PredecessorDAG'

Build the declared DAG once, validating duplicate and cyclic supports natively.

### validate_pinned(declaration, routes, weights)

No documentation available.

---

## ngraph.analysis.sensitivity

Directed-edge sensitivity of one native model at a fixed question.

### SensitivityQuery

SensitivityQuery(source: 'Selector', target: 'Selector', config: 'ngc.FlowPolicyConfig', offer: 'float | None' = None, design_demand: 'float | None' = None, eligibility: 'ngc.Eligibility | None' = None, workers: 'Workers' = 'auto', outputs: 'ngc.OutputOptions' = <factory>, export_details: 'bool' = False)

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `config` (ngc.FlowPolicyConfig)
- `offer` (float | None)
- `design_demand` (float | None)
- `eligibility` (ngc.Eligibility | None)
- `workers` (Workers) = auto
- `outputs` (ngc.OutputOptions)
- `export_details` (bool) = False

### edge_sensitivity(prepared: 'PreparedScenario', query: 'SensitivityQuery') -> 'SensitivityAnalysis'

No documentation available.

---

## ngraph.analysis.states

What each failure state forwards: one case's native demand configs per state.

``converged`` evaluates the declared demands on the failed topology (a WCMP
controller set on the case's own tables); ``stale`` forwards each demand's
baseline program unchanged, LOSSY, at its baseline admitted total, with the
case's failures as black holes; ``repair`` forwards the baseline program under
the failure mask (native repair: survivors re-split, no new search) at the
declared request, except that declared group caps get a table recompiled from
the surviving routes. Nothing here forwards traffic.

### Baseline

Each demand's baseline program and admitted total, by demand id.

**Attributes:**

- `programs` (Mapping[str, ngc.ForwardingProgram])
- `admitted` (Mapping[str, int])

**Methods:**

- `of(state: 'CaseState') -> 'Baseline'`

### forwarding_failure(exc: 'ValueError') -> 'ForwardingFailure | None'

The case outcome a native error stands for, or None for any other error.

### participants(topology, setup, demands, controlled, case: 'FailureCase', state, requests, baseline, tables)

Per demand, in demand order: (native config, policy eligibility, request).

``controlled`` holds the demand ids the WCMP controller programs;
``tables`` the case's tables by destination (None: the demands' own
configs, as in the baseline case).

### simultaneous_role(routing) -> 'str'

How a model joins a SIMULTANEOUS list (CONTRACT 11.1).

``tunnels`` (T1, T2) are set up first and forwarded; a live
``controller`` cannot be LOSSY, so its prepared program is imported;
every other model is replaced directly on the common view.

---

## ngraph.analysis.topology

Compile named physical links and finite TE ingresses into one native graph.

### NamedRoutes

Declared routes, supports and weights, and their native forms on one graph.

**Attributes:**

- `route_specs` (Mapping[str, RouteSpec]) = {}
- `support_specs` (Mapping[str, SupportSpec]) = {}
- `weight_specs` (Mapping[str, WeightSpec]) = {}
- `routes` (Mapping[str, ngc.RouteDefinition]) = {}
- `supports` (Mapping[str, ngc.PredecessorDAG]) = {}
- `weights` (Mapping[str, tuple[int, ...]]) = {}

**Methods:**

- `vector(self, name: 'str') -> 'tuple[int, ...]'` - The named explicit edge weights.

### PreparedTopology

One graph with network labels; native edge arrays remain authoritative.

``pool_heads`` maps each finite TE ingress pool to its synthetic head node;
``pool_budgets`` holds a pool's lossy offer budget in units, when it has one.

**Attributes:**

- `graph` (ngc.Graph)
- `node_names` (tuple[str, ...])
- `node_id_by_name` (Mapping[str, int])
- `edge_refs` (tuple[DirectedLink | SyntheticIngress, ...])
- `edges_by_link` (Mapping[str, tuple[int, int]])
- `disabled` (ngc.Eligibility)
- `q` (float)
- `pool_heads` (Mapping[str, int])
- `pool_budgets` (Mapping[str, int])
- `_edge_id_by_ref` (Mapping[DirectedLink | SyntheticIngress, int])

### compile_topology(network: 'Network', q: 'float', *, pools: 'Mapping[str, tuple[str, ...]] | None' = None, budgets: 'Mapping[str, int] | None' = None) -> 'PreparedTopology'

Compile a candidate graph, refusing directed capacity/cost sums out of range.

A pool's attachments carry its source's outgoing capacity, or its lossy
offer budget (units) when that is larger.

### cost_units(value, label)

Positive integral costs keep their value; no offset or rounding.

### eligibility(topology: 'PreparedTopology', excluded_nodes=(), excluded_links=(), excluded_edges=()) -> 'ngc.Eligibility'

Intersect physical failures with declared disabled nodes and links.

### outgoing_units(network: 'Network', q: 'float') -> 'Counter[str]'

Each node's outgoing directed capacity in units at q.

---

## ngraph.analysis.totals

Exact converged-state totals with the declared reference denominator.

### placement_totals(entries) -> ngraph.results.PlacementTotals

Totals of (demand id, reference request units, native result) entries.

---

## ngraph.analysis.units

Exact physical conversion, unit reports and the choice of one resolution.

### UnitRangeError

A validated physical amount exceeded the fixed native units domain.

### UnitsSettings

One physical unit and the local relative precision target.

**Attributes:**

- `resolution` (float | Literal['auto']) = auto
- `precision` (float) = 0.001

### choose_resolution(settings: 'UnitsSettings', inputs: 'Mapping[str, tuple[_InputKind, float]]', coefficients: 'Mapping[str, int]', split_bounds: 'Iterable[Fraction]', candidate: 'Callable[[float], tuple[Candidate, bool]]', extra: 'Callable[[float], int] | None' = None) -> 'tuple[Candidate, RangeConstraint | None]'

Choose q by the fixed recipe and return the chosen candidate.

``coefficients`` counts each link capacity's directed copies in the
augmented graph; ``split_bounds`` are the declared expansion bounds, which
like the input bounds do not depend on q. ``candidate(q)`` prepares one
resolution and says whether it meets the target; ``extra(q)`` adds the
capacity that pool offer budgets add above their sources' outgoing
capacity. Automatic choice takes the
coarsest range-valid q within the declared bounds that meets the target,
else the finest range-valid one. The second value is the range failure of
the next finer q, which the caller reports as binding.

### input_constraint(label: 'str', value: 'float', q: 'float', precision: 'float') -> 'InputConstraint | None'

Positive inputs retain their precision constraint even if rounded to zero.

### input_observations(inputs, q, precision)

Own one complete set of exact input samples and constraints per unit.

### input_samples(inputs: 'Mapping[str, tuple[_InputKind, float]]', q: 'float') -> 'tuple[InputQuantization, ...]'

Describe all input errors exactly, before truncating report examples.

### make_report(q, settings, scope, inputs, capacity_sum, cost_sum, splits=(), extra=(), misses=(), *, observations=None)

Build a report from complete observations; examples are only a sample.

### precision_miss(location, samples, constraints) -> 'PrecisionMiss | None'

One observation's missed local targets, or None when all are met.

### quantize(value: 'float', q: 'float', label: 'str') -> 'int'

Quantize the promoted binary64 amount using Core's half-up rule.

### scaled_units(volume: 'float', alpha: 'float', q: 'float', label: 'str') -> 'int'

Scale the original physical total once, then quantize once.

### split_units(total: 'int', members: 'int') -> 'tuple[int, ...]'

Allocate a declared total in canonical quotient/remainder order.

### validate_resolution(q: 'float') -> 'float'

No documentation available.

### with_splits(report, splits, extra)

Complete the existing input report without observing its inputs again.

---


## Errors

Invalid input mostly raises `ValueError`; a scenario that fails schema validation raises `jsonschema.ValidationError`. Each entry's Raises section lists its cases.
