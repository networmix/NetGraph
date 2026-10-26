<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# Python API (generated)

Every public name of NetGraph, generated from the docstrings: the `__all__` of `ngraph`, `ngraph.workflow`, `ngraph.hardware` and `ngraph.logging`, and nothing else. The [Python API](api.md) guide shows the same API by task, with examples.

## ngraph

### ngraph.AnalysisMetadata

Immutable AnalysisMetadata record.

**Attributes:**

- `workers` (int)
- `sampling` (SamplingMetadata | None): None when the analysis draws no failures

### ngraph.AnalysisResult

```python
AnalysisResult = CapacityAnalysis
    | PlacementAnalysis
    | SensitivityAnalysis
    | PathAnalysis
    | MSDAnalysis
    | TunnelCountAnalysis
```

### ngraph.BuildGraphResult

Immutable BuildGraphResult record.

**Attributes:**

- `kind` (ClassVar[Literal['build_graph']]) = build_graph
- `add_reverse` (bool)
- `node_count` (int)
- `edge_count` (int)
- `graph` (Mapping[str, JSONValue])

### ngraph.CapacityAnalysis

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

### ngraph.CapacityQuery

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

### ngraph.CapacityRow

Immutable CapacityRow record.

**Attributes:**

- `id` (str)
- `endpoints` (Endpoints)
- `result` (ngc.PlacementResult)
- `pool` (PoolMetadata | None)
- `cost_distribution` (CostReport | None)
- `unavailable_outputs` (Mapping[Literal['cost_distribution'], CostUnavailableReason])

### ngraph.CaseResult

Immutable CaseResult record.

**Attributes:**

- `case` (FailureCase)
- `states` (Mapping[StateName, CaseState[RowT]])

### ngraph.CaseState

One state of a case: its rows and totals, or its forwarding failure.

``dead_caps`` lists the dead root groups of a group-scope demand set in the
converged and repair states; it is None elsewhere.

**Attributes:**

- `rows` (tuple[RowT, ...])
- `totals` (PlacementTotals | None)
- `failure` (ForwardingFailure | None)
- `dead_caps` (tuple[DeadCap, ...] | None)

### ngraph.Component

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
    count (int): How many identical copies of this component are present; a positive
        integer whose conversion to float is finite.
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

### ngraph.ComponentsLibrary

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

### ngraph.Condition

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

### ngraph.ControllerGroup

A root group of one router: its share is a fixed cap, normalized once.

**Attributes:**

- `children` (tuple[GroupChild, ...])
- `share` (Fraction)

### ngraph.CostPowerResult

Immutable CostPowerResult record.

**Attributes:**

- `kind` (ClassVar[Literal['cost_power']]) = cost_power
- `include_disabled` (bool)
- `aggregation_level` (int)
- `levels` (Mapping[int, tuple[HardwareRow, ...]])

### ngraph.CostReport

```python
CostReport = DeliveredByPathCost | MarginalCurve
```

### ngraph.CostUnavailableReason

```python
CostUnavailableReason = Literal[
    "mixed_cost_dag", "unsupported_model", "controller_table"
]
```

### ngraph.DeliveredByPathCost

Immutable DeliveredByPathCost record.

**Attributes:**

- `kind` (ClassVar[Literal['delivered_by_path_cost']]) = delivered_by_path_cost
- `cost_domain` (Literal['physical_network', 'analysis_graph'])
- `bins` (tuple[PathCostBin, ...])

### ngraph.DemandSet

DemandSet(name: 'str', demands: 'tuple[DemandSpec, ...]')

**Attributes:**

- `name` (str)
- `demands` (tuple[DemandSpec, ...])

### ngraph.DemandSpec

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

### ngraph.DirectedLink

One analysis direction of a stored physical link.

**Attributes:**

- `link` (str)
- `direction` (Literal['forward', 'reverse'])

### ngraph.DiscardedShare

Immutable DiscardedShare record.

**Attributes:**

- `label` (str)
- `units` (int)
- `reason` (Literal['self_pair', 'filtered', 'empty_selection'])

### ngraph.DomainResult

```python
DomainResult = BuildGraphResult | NetworkStatsResult | CostPowerResult
```

### ngraph.EdgeWeight

EdgeWeight(edge: 'DirectedLink', value: 'int')

**Attributes:**

- `edge` (DirectedLink)
- `value` (int)

### ngraph.Endpoints

Immutable Endpoints record.

**Attributes:**

- `sources` (tuple[str, ...])
- `destinations` (tuple[str, ...])

### ngraph.ExactAlpha

Immutable ExactAlpha record.

**Attributes:**

- `value` (float)
- `numerator` (int)
- `denominator` (int)

### ngraph.ExpansionAccounting

Immutable ExpansionAccounting record.

**Attributes:**

- `base_id` (str)
- `declared_units` (int)
- `resolved_units` (int)
- `discarded_units` (int)
- `discards` (tuple[DiscardedShare, ...])

### ngraph.ExpansionLeaf

Immutable ExpansionLeaf record.

**Attributes:**

- `id` (str)
- `order` (int)
- `endpoints` (Endpoints | None)
- `discard_reason` (Literal['self_pair', 'filtered', 'empty_selection'] | None)

### ngraph.ExpansionParent

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

### ngraph.ExpansionSplit

Immutable ExpansionSplit record.

**Attributes:**

- `label` (str)
- `children` (tuple[ExpansionSplit | ExpansionLeaf, ...])

### ngraph.ExportContext

Immutable ExportContext record.

**Attributes:**

- `prepared` (PreparedScenario)
- `units_report` (UnitsReport)

### ngraph.FailureCase

Immutable FailureCase record.

**Attributes:**

- `id` (str)
- `kind` (Literal['baseline', 'failure'])
- `pattern` (FailurePattern)
- `occurrences` (int)
- `eligibility` (ngc.Eligibility)
- `trace` (FailureTrace | None)

### ngraph.FailureMode

FailureMode(weight: 'float', rules: 'Sequence[FailureRule]' = (), attrs: 'dict[str, Any]' = <factory>)

**Attributes:**

- `weight` (float)
- `rules` (Sequence[FailureRule]) = ()
- `attrs` (dict[str, Any]) = {}

### ngraph.FailurePattern

Canonical failure mask used as a scheduling and sampling key.

**Attributes:**

- `excluded_nodes` (tuple[str, ...])
- `excluded_links` (tuple[str, ...])

### ngraph.FailurePolicy

Failure modes drawn by weight; at least one mode has a positive weight.

"No failures" is no policy, not an empty one.

**Attributes:**

- `attrs` (dict[str, Any]) = {}
- `expand_groups` (bool) = False
- `seed` (int | None)
- `modes` (Sequence[FailureMode])

### ngraph.FailureRequest

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

### ngraph.FailureRule

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

### ngraph.FailureSelection

Immutable FailureSelection record.

**Attributes:**

- `rule_index` (int)
- `scope` (Literal['node', 'link', 'risk_group'])
- `selected` (tuple[str, ...])

### ngraph.FailureTrace

Immutable FailureTrace record.

**Attributes:**

- `draw_index` (int)
- `mode_index` (int | None): None when the policy has no modes
- `mode_attrs` (Mapping[str, JSONValue])
- `selections` (tuple[FailureSelection, ...])
- `expanded_nodes` (tuple[str, ...])
- `expanded_links` (tuple[str, ...])

### ngraph.FlowPolicyPreset

Named questions with one immutable native configuration each.

**Members:**

- `SHORTEST_PATHS_ECMP` = 'SHORTEST_PATHS_ECMP'
- `SHORTEST_PATHS_ECMP_LOSSY` = 'SHORTEST_PATHS_ECMP_LOSSY'
- `SHORTEST_PATHS_WCMP` = 'SHORTEST_PATHS_WCMP'
- `SHORTEST_PATHS_MAXFLOW` = 'SHORTEST_PATHS_MAXFLOW'
- `TE_MAXFLOW_UNLIM` = 'TE_MAXFLOW_UNLIM'
- `TE_ECMP_16_LSP` = 'TE_ECMP_16_LSP'
- `TE_ECMP_UP_TO_256_LSP` = 'TE_ECMP_UP_TO_256_LSP'

### ngraph.ForwardingGroup

The declared root groups of one router.

**Attributes:**

- `router` (str)
- `groups` (tuple[ControllerGroup, ...])

### ngraph.GroupChild

A member edge, or a conditional subtree, with its share within its parent.

Exactly one of ``edge`` and ``children`` is set, and the share is
nonnegative, stored as a Fraction; preparation checks the tree against the
network (edges leaving the router, zero shares, duplicates).

**Attributes:**

- `share` (Fraction)
- `edge` (DirectedLink | None)
- `children` (tuple[GroupChild, ...] | None)

### ngraph.HardwareRow

Immutable HardwareRow record.

**Attributes:**

- `path` (str)
- `platform_capex` (float)
- `platform_power_watts` (float)
- `optics_capex` (float)
- `optics_power_watts` (float)
- `capex_total` (float)
- `power_total_watts` (float)

### ngraph.InputConstraint

Immutable InputConstraint record.

**Attributes:**

- `kind` (ClassVar[Literal['input']]) = input
- `label` (str)
- `q_upper_bound` (Fraction)
- `met` (bool)

### ngraph.InputQuantization

Immutable InputQuantization record.

**Attributes:**

- `label` (str)
- `kind` (Literal['capacity', 'demand', 'offer', 'design', 'min_unreserved'])
- `binary64_value` (float)
- `binary64_hex` (str)
- `units` (int)
- `error` (Fraction)
- `relative_error` (Fraction | None): None when the input is zero

### ngraph.JSONValue

```python
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
```

### ngraph.Link

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
    cost (int): Link cost, an integer from 1 to below 2^62 (default 1); an
        exactly integral float such as 2.0 is stored as 2.
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
- `cost` (int) = 1
- `disabled` (bool) = False
- `risk_groups` (AbstractSet[str]) = frozenset()
- `attrs` (Dict[str, Any]) = {}
- `id` (str)

### ngraph.MSDAnalysis

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

### ngraph.MSDProbe

Immutable MSDProbe record.

**Attributes:**

- `index` (int)
- `alpha` (ExactAlpha)
- `outcome` (Literal['feasible', 'infeasible', 'below_resolution', 'range'])
- `totals` (PlacementTotals | None): None when the probe was out of range
- `range_refusal` (RangeRefusal | None): None when the probe was in range

### ngraph.MSDProof

```python
MSDProof = Literal[
    "fixed_program", "single_controller", "nothing_offered", "unproved"
]
```

### ngraph.MSDQuery

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

### ngraph.MSDStatus

```python
MSDStatus = Literal[
    "feasible", "none_feasible", "range", "stagnation", "limit", "trivial"
]
```

### ngraph.MSDStopReason

```python
MSDStopReason = Literal[
    "tolerance",
    "alpha_bound",
    "bracket_limit",
    "bisect_limit",
    "offer_range",
    "representable_limit",
    "nothing_offered",
    "unit_resolution",
]
```

### ngraph.MarginalCostBin

Immutable MarginalCostBin record.

**Attributes:**

- `marginal_cost` (int)
- `units` (int)

### ngraph.MarginalCurve

Immutable MarginalCurve record.

**Attributes:**

- `kind` (ClassVar[Literal['marginal_curve']]) = marginal_curve
- `cost_domain` (Literal['physical_network', 'analysis_graph'])
- `bins` (tuple[MarginalCostBin, ...])

### ngraph.MatchSpec

Attribute conditions combined with "and" or "or" logic.

Attributes:
    conditions: Conditions to evaluate, in order.
    logic: How to combine conditions ("and" = all, "or" = any).

**Attributes:**

- `conditions` (Sequence[Condition]) = ()
- `logic` (Literal['and', 'or']) = or

### ngraph.Network

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

### ngraph.NetworkExplorer

Hierarchical view of a Network with per-subtree statistics.

Statistics are computed in two modes: 'all' (disabled nodes and links
included) and 'active' (enabled only).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None, strict_validation: 'bool' = True) -> 'NetworkExplorer'` - Build the hierarchy tree and compute 'all' and 'active' statistics.
- `get_bom(self, include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return aggregated hardware BOM for the whole network.
- `get_link_issues(self) -> 'List[LinkCapacityIssue]'` - Return link capacity violations recorded in non-strict mode.
- `get_node_utilization(self) -> 'List[NodeUtilization]'` - Return hardware utilization per node based on active topology.
- `print_tree(self, node: 'Optional[TreeNode]' = None, indent: 'int' = 0, max_depth: 'Optional[int]' = None, skip_leaves: 'bool' = False, detailed: 'bool' = False, include_disabled: 'bool' = True, max_external_lines: 'Optional[int]' = None, line_prefix: 'str' = '') -> 'None'` - Print the hierarchy from 'node' down (default: root).

### ngraph.NetworkStatsResult

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
- `min_cost` (int)
- `max_cost` (int)
- `mean_degree` (float)
- `median_degree` (float)
- `min_degree` (float)
- `max_degree` (float)

### ngraph.Node

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

### ngraph.OutputSelection

Immutable OutputSelection record.

**Attributes:**

- `native` (ngc.OutputOptions)
- `cost_distribution` (bool)
- `details` (bool) = False

### ngraph.PathAnalysis

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

### ngraph.PathCostBin

Immutable PathCostBin record.

**Attributes:**

- `cost` (int)
- `physical_path_cost` (int)
- `delivered_units` (int)

### ngraph.PathQuery

PathQuery(source: 'Selector', target: 'Selector', mode: "Literal['combine', 'pairwise']" = 'combine', options: 'ngc.SpfOptions | ngc.KspOptions' = <factory>, costs_only: 'bool' = False, max_paths: 'int | None' = None, split_parallel_edges: 'bool | None' = None)

**Attributes:**

- `source` (Selector)
- `target` (Selector)
- `mode` (Literal['combine', 'pairwise']) = combine
- `options` (ngc.SpfOptions | ngc.KspOptions)
- `costs_only` (bool) = False
- `max_paths` (int | None)
- `split_parallel_edges` (bool | None)

### ngraph.PathRow

Immutable PathRow record.

**Attributes:**

- `id` (str)
- `endpoints` (Endpoints)
- `kind` (Literal['paths', 'self'])
- `cost` (int | None)
- `paths` (tuple[ngc.Path, ...] | None)

### ngraph.PhysicalAmount

```python
PhysicalAmount = float
```

### ngraph.PinnedRoutes

PinnedRoutes(routes: 'tuple[str, ...]', admission: 'ngc.Admission' = <Admission.LOSSLESS: 0>, allocation: 'ngc.RouteAllocation | None' = None, weight_basis: 'ngc.WeightBasis | None' = None, edge_weights: 'str | None' = None)

**Attributes:**

- `routes` (tuple[str, ...])
- `admission` (ngc.Admission) = Admission.LOSSLESS
- `allocation` (ngc.RouteAllocation | None)
- `weight_basis` (ngc.WeightBasis | None)
- `edge_weights` (str | None)

### ngraph.PlacementAnalysis

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

### ngraph.PlacementQuery

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

### ngraph.PlacementRow

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

### ngraph.PlacementTotals

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

### ngraph.PoolHead

Immutable PoolHead record.

**Attributes:**

- `pool_id` (str)
- `physical_sources` (tuple[str, ...])

### ngraph.PoolMetadata

A TE ingress pool; ``offer_limit_units`` is its prepared lossy offer budget.

**Attributes:**

- `head` (PoolHead)
- `offer_limit_units` (int) = 0
- `synthetic_ingress_cost` (ClassVar[Literal[1]]) = 1

### ngraph.PrecisionMiss

Immutable PrecisionMiss record.

**Attributes:**

- `location` (ReportLocation)
- `constraints` (tuple[InputConstraint | SplitConstraint | UnverifiedConstraint, ...])
- `inexact_inputs` (int)
- `zeroed_inputs` (int)
- `examples` (tuple[InputQuantization, ...])

### ngraph.PreparationScope

Immutable PreparationScope record.

**Attributes:**

- `workflow_steps` (tuple[str, ...])
- `workflow_demand_sets` (tuple[str, ...])
- `library_demand_sets` (tuple[str, ...])

### ngraph.PreparedScenario

One graph, unit and demand binding over a read-only view of a scenario.

``units_report`` is the nominal preparation's report; each analysis
returns its own precision misses beside it.

**Attributes:**

- `scenario` (Scenario)
- `topology` (PreparedTopology)
- `demand_sets` (Mapping[str, ResolvedDemandSet])
- `units_report` (UnitsReport)

### ngraph.PreparedTopology

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

### ngraph.RangeConstraint

Immutable RangeConstraint record.

**Attributes:**

- `kind` (Literal['capacity_sum', 'cost_sum', 'amount'])
- `label` (str)
- `tested_q` (float)
- `units_value` (int)
- `exclusive_limit` (int)
- `met` (bool)

### ngraph.RangeRefusal

Immutable RangeRefusal record.

**Attributes:**

- `label` (str)
- `reason` (Literal['scaled_nonfinite', 'native_units_range'])
- `message` (str)
- `binary64_hex` (str | None): None when the refused amount is not a binary64 value

### ngraph.ReportLocation

Immutable ReportLocation record.

**Attributes:**

- `step` (str | None): None when the report is outside a workflow
- `case_id` (str | None): None when the report is outside failure cases
- `probe_index` (int | None): None when the report is outside MSD

### ngraph.ResolvedDemand

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

### ngraph.ResolvedDemandSet

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

### ngraph.RiskGroup

A named failure domain with optional nested, unregistered descendants.

``attrs`` holds finite JSON metadata, checked and stored read-only at
construction.

**Attributes:**

- `name` (str)
- `children` (Sequence[RiskGroup]) = ()
- `disabled` (bool) = False
- `attrs` (dict[str, Any]) = {}

### ngraph.RouteSpec

RouteSpec(head: 'str', nodes: 'tuple[str, ...] | None' = None, edges: 'tuple[DirectedLink, ...] | None' = None, support: 'str | None' = None, weight: 'int' = 1)

**Attributes:**

- `head` (str)
- `nodes` (tuple[str, ...] | None)
- `edges` (tuple[DirectedLink, ...] | None)
- `support` (str | None)
- `weight` (int) = 1

### ngraph.RoutingDomain

One IGP domain and the BGP-edge routers around it.

**Attributes:**

- `igp_domain` (Selector)
- `bgp_edge` (Selector)

### ngraph.RunMetadata

Immutable RunMetadata record.

**Attributes:**

- `schema_version` (ClassVar[Literal['1.0']]) = 1.0
- `netgraph_version` (str)
- `core_version` (str)
- `core_extension_sha256` (str)
- `python_version` (str)
- `seed` (int | None): None when the scenario sets no seed

### ngraph.RunResult

One run; ``units_report`` adds every step's precision misses, by step.

**Attributes:**

- `metadata` (RunMetadata)
- `units_report` (UnitsReport)
- `steps` (tuple[StepResult, ...])
- `prepared` (PreparedScenario)

### ngraph.SamplingMetadata

Immutable SamplingMetadata record.

**Attributes:**

- `random_rule_algorithm` (ClassVar[Literal['per_entity_bernoulli']]) = per_entity_bernoulli
- `rng` (ClassVar[Literal['random.Random']]) = random.Random
- `python_version` (ClassVar[str])
- `seed` (int | None): None when the draws are unseeded
- `seed_source` (Literal['query', 'step', 'scenario', 'policy', 'unseeded'])
- `draw_seed_rule` (ClassVar[Literal['base_plus_draw_index']]) = base_plus_draw_index
- `entity_order` (ClassVar[Literal['sorted_identifier']]) = sorted_identifier
- `rule_order` (ClassVar[Literal['declaration']]) = declaration
- `iterations` (int)

### ngraph.Scenario

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

### ngraph.Selector

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

### ngraph.SelfPair

Immutable SelfPair record.

**Attributes:**

- `kind` (ClassVar[Literal['self']]) = self
- `id` (str)
- `node` (str)
- `capacity_units` (ClassVar[Literal[0]]) = 0

### ngraph.SensitivityAnalysis

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

### ngraph.SensitivityQuery

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

### ngraph.SplitConstraint

Immutable SplitConstraint record.

**Attributes:**

- `kind` (Literal['expansion', 'source', 'router', 'tunnel'])
- `label` (str)
- `incoming_physical` (Fraction)
- `basis` (Literal['declared', 'observed'])
- `members` (int)
- `q_upper_bound` (Fraction)
- `met` (bool)

### ngraph.StepContext

Immutable StepContext record.

**Attributes:**

- `prepared` (PreparedScenario)
- `prior_results` (Mapping[str, StepResult])
- `step_name` (str)
- `execution_order` (int)
- `seed` (int | None)
- `seed_source` (Literal['explicit-step', 'scenario-derived', 'none'])

### ngraph.StepOutput

Immutable StepOutput record.

**Attributes:**

- `question` (StepQuestion)
- `result` (object)

### ngraph.StepQuestion

```python
StepQuestion = CapacityQuery
        | PlacementQuery
        | SensitivityQuery
        | PathQuery
        | MSDQuery
        | TunnelCountQuery
        | BuildGraph
        | NetworkStats
        | CostPower
        | Mapping[str, JSONValue]
```

### ngraph.StepResult

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

### ngraph.SupportSpec

SupportSpec(edges: 'tuple[DirectedLink, ...]')

**Attributes:**

- `edges` (tuple[DirectedLink, ...])

### ngraph.SyntheticIngress

Immutable SyntheticIngress record.

**Attributes:**

- `pool_id` (str)
- `source` (str)

### ngraph.TunnelCountAnalysis

Immutable TunnelCountAnalysis record.

**Attributes:**

- `kind` (ClassVar[Literal['tunnel_counts']]) = tunnel_counts
- `prepared` (PreparedScenario)
- `misses` (tuple[PrecisionMiss, ...])
- `metadata` (AnalysisMetadata)
- `outputs` (OutputSelection)
- `rows` (tuple[TunnelCountRow, ...])
- `query` (TunnelCountQuery)

### ngraph.TunnelCountQuery

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

### ngraph.TunnelCountRow

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

### ngraph.UnitConstraint

```python
UnitConstraint = InputConstraint | SplitConstraint | RangeConstraint | UnverifiedConstraint
```

### ngraph.UnitsReport

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

### ngraph.UnitsSettings

One physical unit and the local relative precision target.

**Attributes:**

- `resolution` (float | Literal['auto']) = auto
- `precision` (float) = 0.001

### ngraph.UnverifiedConstraint

Immutable UnverifiedConstraint record.

**Attributes:**

- `kind` (ClassVar[Literal['unverified']]) = unverified
- `label` (str)
- `reason` (ClassVar[Literal['opaque_program']]) = opaque_program

### ngraph.UpperCertificate

Immutable UpperCertificate record.

**Attributes:**

- `proof` (Literal['fixed_program', 'single_controller'])
- `lower` (ExactAlpha)
- `upper` (ExactAlpha)
- `lower_probe_index` (int)
- `upper_probe_index` (int)

### ngraph.WCMPController

Which routers the controller programs for SHORTEST_PATHS_WCMP demands.

**Attributes:**

- `scope` (Literal['next_hop', 'group', 'all_routers']) = next_hop

### ngraph.WeightSpec

WeightSpec(entries: 'tuple[EdgeWeight, ...]')

**Attributes:**

- `entries` (tuple[EdgeWeight, ...])

### ngraph.Workers

```python
Workers = int | Literal["auto"]
```

### ngraph.WorkflowStep

Also importable as `ngraph.workflow.WorkflowStep`.

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

### ngraph.__version__

The installed package version, a string.

### ngraph.capacity

`capacity(prepared: 'PreparedScenario', query: 'CapacityQuery') -> 'CapacityAnalysis'`

No documentation available.

### ngraph.edge_sensitivity

`edge_sensitivity(prepared: 'PreparedScenario', query: 'SensitivityQuery') -> 'SensitivityAnalysis'`

No documentation available.

### ngraph.failure_cases

`failure_cases(prepared: 'PreparedScenario', request: 'FailureRequest | None') -> 'tuple[FailureCase, ...]'`

The baseline, then each distinct drawn pattern with its draw count.

### ngraph.maximum_supported_demand

`maximum_supported_demand(prepared: 'PreparedScenario', query: 'MSDQuery') -> 'MSDAnalysis'`

No documentation available.

### ngraph.paths

`paths(prepared: 'PreparedScenario', query: 'PathQuery') -> 'PathAnalysis'`

No documentation available.

### ngraph.place

`place(prepared: 'PreparedScenario', query: 'PlacementQuery') -> 'PlacementAnalysis'`

No documentation available.

### ngraph.prepare

`prepare(scenario: 'Scenario', *, units: 'UnitsSettings | None' = None, demand_sets: 'Sequence[str]' = ()) -> 'PreparedScenario'`

Choose one graph/unit over a read-only view of the scenario.

The input is not changed. The prepared scenario shares its immutable
records and keeps read-only copies of the network and component dicts,
so later edits of the caller's collections do not reach it.

### ngraph.register_result_exporter

`register_result_exporter(result_type: 'type[ExportT]', encoder: 'Callable[[ExportT, ExportContext], JSONValue]') -> 'None'`

Register one explicit encoder for exactly this result type.

### ngraph.register_workflow_step

Also importable as `ngraph.workflow.register_workflow_step`.

`register_workflow_step(name: 'str') -> 'Callable[[type[StepT]], type[StepT]]'`

Register one concrete step class for a nonempty YAML type name.

### ngraph.resolve_demands

`resolve_demands(prepared: 'PreparedScenario', specs: 'DemandSet') -> 'ResolvedDemandSet'`

No documentation available.

### ngraph.run

`run(prepared: 'PreparedScenario', *, step_hook: 'Callable[[WorkflowStep], AbstractContextManager[None]] | None' = None) -> 'RunResult'`

Execute once in declaration order; publish a run only after every step succeeds.

### ngraph.tunnel_counts

`tunnel_counts(prepared: 'PreparedScenario', query: 'TunnelCountQuery') -> 'TunnelCountAnalysis'`

No documentation available.

### ngraph.write_json

`write_json(result: 'RunResult | AnalysisResult', file: 'IO[str]') -> 'None'`

Project once and encode before writing, so encoder errors write nothing.

---

## ngraph.workflow

### ngraph.workflow.StepNeeds

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
preparation observes once per candidate resolution. ``nodes`` and ``links``
are names the step reads that must exist in the network.

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
- `nodes` (tuple[str, ...]) = ()
- `links` (tuple[str, ...]) = ()

### ngraph.workflow.step_name

`step_name(step: 'WorkflowStep') -> 'str'`

Return the name a step runs under: its name, or its class name when unnamed.

### ngraph.workflow.BuildGraph

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

### ngraph.workflow.CostPower

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

### ngraph.workflow.MaxFlow

Evaluate independent endpoint capacities with explicit native routing.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `source` (Selector) = Selector(path='.*', group_by=None, match=None, active_only=None)
- `target` (Selector) = Selector(path='.*', group_by=None, match=None, active_only=None)
- `mode` (Literal) = combine
- `preset` (ngraph.model.demand.FlowPolicyPreset | None)
- `model` (object)
- `offer` (float | None)
- `design_demand` (float | None)
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `workers` (int | Literal['auto']) = auto
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

### ngraph.workflow.MaximumSupportedDemand

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

### ngraph.workflow.NetworkStats

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
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: 'dict', name: 'str') -> 'dict'` - Turn this step type's YAML keys into constructor arguments.

### ngraph.workflow.TrafficMatrixPlacement

TrafficMatrixPlacement(name: 'str' = '', seed: 'int | None' = None, demand_set: str = '', failure_policy: str | None = None, iterations: int = 1, workers: int | Literal['auto'] = 'auto', failure_trace: bool = False, outputs: _netgraph_core.OutputOptions = <factory>, export_cost_distribution: bool = False, export_details: bool = False, alpha: float | None = None, alpha_from_step: str | None = None, failure_states: tuple[typing.Literal['converged', 'stale', 'repair'], ...] = ('converged',), interaction: Literal['ordered', 'simultaneous'] = 'ordered', *, yaml_label: 'str | None' = None, derived_seed: 'int | None' = None)

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `yaml_label` (str | None)
- `derived_seed` (int | None)
- `demand_set` (str)
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `workers` (int | Literal['auto']) = auto
- `failure_trace` (bool) = False
- `outputs` (OutputOptions)
- `export_cost_distribution` (bool) = False
- `export_details` (bool) = False
- `alpha` (float | None)
- `alpha_from_step` (str | None)
- `failure_states` (tuple) = ('converged',)
- `interaction` (Literal) = ordered

**Methods:**

- `execute(self, context: 'StepContext') -> 'StepResult'` - Run once, validate/own its boundary, and publish one immutable result.
- `needs(self) -> ngraph.analysis.preparation.StepNeeds` - What preparation must bind for this step; None asks for nothing.
- `run(self, context: ngraph.results.StepContext) -> ngraph.results.StepOutput` - Return this step's typed question and result without publishing state.
- `yaml_arguments(arguments: dict, name: str) -> dict` - Turn this step type's YAML keys into constructor arguments.

### ngraph.workflow.TunnelCountAnalysis

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
- `up_to` (int | None)
- `design_demand` (float | None)
- `offer` (float | None)
- `workers` (int | Literal['auto']) = auto
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

## ngraph.hardware

### ngraph.hardware.hardware_inventory

`hardware_inventory(network: 'Network', library: 'ComponentsLibrary') -> 'HardwareInventory'`

Resolve every node's and link end's hardware, in that order.

A link end counts only where its endpoint node has a platform.

Raises:
    ValueError: If any node, link or link end has a ``hardware`` value
        that is not a mapping or a count that is not a finite positive
        number; the message starts with the entity
        (``node <name>``, ``link <key>``, ``link <key> source end``).

### ngraph.hardware.HardwareInventory

The hardware uses of a network and its references to unknown components.

Attributes:
    uses: Node platforms in node order, then each link's source end and
        target end in link order (the order of every sum over them).
    unknown: ``(owner, end, name)`` for each reference to a component the
        library lacks: a node name with end None, or a link key with its
        end.

**Attributes:**

- `uses` (tuple[HardwareUse, ...])
- `unknown` (tuple[tuple[str, Optional[str], object], ...])

### ngraph.hardware.HardwareUse

One installed platform or link-end optic.

Attributes:
    node: Node the hardware sits at; consumers group by this name.
    link: Key of the link in ``Network.links`` for an optic; None for a
        node platform.
    end: ``"source"`` or ``"target"`` for an optic; None for a platform.
    component: The library component.
    count: Declared count.
    bom_count: Count in the bill of materials: the count, rounded up for
        an exclusive link end.
    capex: Component capex (children included) times ``count``.
    power_watts: Component typical power times ``count``.
    capacity: Component capacity times ``count``.
    active: In the enabled view: the node is enabled (platform), or the
        link is active (optic, see ``link_active``).

**Attributes:**

- `node` (str)
- `link` (Optional[str])
- `end` (Optional[str])
- `component` (Component)
- `count` (float)
- `bom_count` (float)
- `capex` (float)
- `power_watts` (float)
- `capacity` (float)
- `active` (bool)

### ngraph.hardware.link_active

`link_active(network: 'Network', link: 'Link') -> 'bool'`

Return True when the link and both of its end nodes are enabled.

### ngraph.hardware.resolve_link_end

`resolve_link_end(spec: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'Tuple[Optional[Component], float, bool]'`

Resolve one link end's hardware: ``{"component": NAME, "count": N}``.

``count`` defaults to 1. An optional ``exclusive: true`` marks unsharable
use; the bill of materials rounds such an end's count up to an integer.

Returns:
    (component or None when the name is absent or unknown, count, exclusive).

Raises:
    ValueError: If ``spec`` is not a mapping or ``count`` is not a finite
        positive number.

---

## ngraph.logging

### ngraph.logging.get_logger

`get_logger(name: str) -> logging.Logger`

Get a logger under NetGraph's logging hierarchy.

Use this everywhere in the package. It configures nothing: handlers and
levels are inherited from the root 'ngraph' logger, which is configured
only when an application calls setup_root_logger() (directly or via
set_global_log_level()).

Args:
    name: Logger name (typically __name__ from calling module).

Returns:
    Logger instance inheriting from the root ngraph logger.

### ngraph.logging.setup_root_logger

`setup_root_logger(level: int = 20, format_string: str | None = None, handler: logging.Handler | None = None) -> None`

Set up the root NetGraph logger with a single handler.

Subsequent calls leave the existing handlers in place.

Args:
    level: Logging level (default: INFO).
    format_string: Custom format string (optional).
    handler: Custom handler (optional, defaults to StreamHandler(sys.stderr)).

### ngraph.logging.set_global_log_level

`set_global_log_level(level: int) -> None`

Set the log level for all NetGraph loggers.

Installs the default console handler via setup_root_logger() if logging
has not been configured yet. Intended for applications (e.g. the CLI);
library code never calls this implicitly.

Args:
    level: Logging level (e.g., logging.DEBUG, logging.INFO).

---

## Errors

`Scenario.from_yaml` refuses invalid input with `ValueError`, whose message starts with the field's path and value. A constructor refuses an invalid field with `ValueError` naming the field. Each entry's Raises section lists its other cases.
