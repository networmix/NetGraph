<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: January 16, 2026 at 02:49 UTC

Modules auto-discovered: 53

---

## ngraph._version

ngraph version metadata.

---

## ngraph.cli

Command-line interface for NetGraph.

### main(argv: 'Optional[List[str]]' = None) -> 'None'

Entry point for the ``ngraph`` command.

Args:
    argv: Optional list of command-line arguments. If ``None``, ``sys.argv``
        is used.

---

## ngraph.explorer

NetworkExplorer class for analyzing network hierarchy and structure.

### ExternalLinkBreakdown

Holds stats for external links to a particular other subtree.

Attributes:
    link_count (int): Number of links to that other subtree.
    link_capacity (float): Sum of capacities for those links.

**Attributes:**

- `link_count` (int) = 0
- `link_capacity` (float) = 0.0

### LinkCapacityIssue

Represents a link capacity constraint violation in active topology.

Attributes:
    source: Source node name.
    target: Target node name.
    capacity: Configured link capacity.
    limit: Effective capacity limit from per-end hardware (min of ends).
    reason: Brief reason tag.

**Attributes:**

- `source` (str)
- `target` (str)
- `capacity` (float)
- `limit` (float)
- `reason` (str)

### NetworkExplorer

Provides hierarchical exploration of a Network, computing statistics in two modes:
'all' (ignores disabled) and 'active' (only enabled).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None, strict_validation: 'bool' = True) -> 'NetworkExplorer'` - Build a NetworkExplorer, constructing a tree plus 'all' and 'active' stats.
- `get_bom(self, include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return aggregated hardware BOM for the whole network.
- `get_bom_by_path(self, path: 'str', include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return the hardware BOM for a specific hierarchy path.
- `get_bom_map(self, include_disabled: 'bool' = True, include_root: 'bool' = True, root_label: 'str' = '') -> 'Dict[str, Dict[str, float]]'` - Return a mapping from hierarchy path to BOM for each subtree.
- `get_link_issues(self) -> 'List[LinkCapacityIssue]'` - Return recorded link capacity issues discovered in non-strict mode.
- `get_node_utilization(self, include_disabled: 'bool' = True) -> 'List[NodeUtilization]'` - Return hardware utilization per node based on active topology.
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
    disabled: True if the node itself is disabled.

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
- `disabled` (bool)

### TreeNode

Represents a node in the hierarchical tree.

Attributes:
    name (str): Name/label of this node.
    parent (Optional[TreeNode]): Pointer to the parent tree node.
    children (Dict[str, TreeNode]): Mapping of child name -> child TreeNode.
    subtree_nodes (Set[str]): Node names in the subtree (all nodes, ignoring disabled).
    active_subtree_nodes (Set[str]): Node names in the subtree (only enabled).
    stats (TreeStats): Aggregated stats for "all" view.
    active_stats (TreeStats): Aggregated stats for "active" (only enabled) view.
    raw_nodes (List[Node]): Direct Node objects at this hierarchy level.

**Attributes:**

- `name` (str)
- `parent` (Optional[TreeNode])
- `children` (Dict[str, TreeNode]) = {}
- `subtree_nodes` (Set[str]) = set()
- `active_subtree_nodes` (Set[str]) = set()
- `stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={}, active_bom={})
- `active_stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={}, active_bom={})
- `raw_nodes` (List[Node]) = []

**Methods:**

- `add_child(self, child_name: 'str') -> 'TreeNode'` - Ensure a child node named 'child_name' exists and return it.
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
    total_capex (float): Cumulative capex (nodes + links).
    total_power (float): Cumulative power (nodes + links).

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
- `active_bom` (Dict[str, float]) = {}

---

## ngraph.logging

Centralized logging configuration for NetGraph.

### disable_debug_logging() -> None

Disable debug logging, set to INFO level.

### enable_debug_logging() -> None

Enable debug logging for the entire package.

### get_logger(name: str) -> logging.Logger

Get a logger with NetGraph's standard configuration.

This is the main function that should be used throughout the package.
All loggers will inherit from the root 'ngraph' logger configuration.

Args:
    name: Logger name (typically __name__ from calling module).

Returns:
    Configured logger instance.

### reset_logging() -> None

Reset logging configuration (mainly for testing).

### set_global_log_level(level: int) -> None

Set the log level for all NetGraph loggers.

Args:
    level: Logging level (e.g., logging.DEBUG, logging.INFO).

### setup_root_logger(level: int = 20, format_string: Optional[str] = None, handler: Optional[logging.Handler] = None) -> None

Set up the root NetGraph logger with a single handler.

This should only be called once to avoid duplicate handlers.

Args:
    level: Logging level (default: INFO).
    format_string: Custom format string (optional).
    handler: Custom handler (optional, defaults to StreamHandler).

---

## ngraph.scenario

Scenario class for defining network analysis workflows from YAML.

### Scenario

Represents a complete scenario for building and executing network workflows.

This scenario includes:

- A network (nodes/links), constructed via blueprint expansion.
- A failure policy set (one or more named failure policies).
- A traffic matrix set containing one or more named traffic matrices.
- A list of workflow steps to execute.
- A results container for storing outputs.
- A components_library for hardware/optics definitions.
- A seed for reproducible random operations (optional).

Typical usage example:

    scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
    scenario.run()
    # Inspect scenario.results

**Attributes:**

- `network` (Network)
- `workflow` (List[WorkflowStep])
- `failure_policy_set` (FailurePolicySet) = FailurePolicySet(policies={})
- `demand_set` (DemandSet) = DemandSet(sets={})
- `results` (Results) = Results(_store={}, _metadata={}, _active_step=None, _scenario={})
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})
- `seed` (Optional[int])
- `_execution_counter` (int) = 0

**Methods:**

- `from_yaml(yaml_str: 'str', default_components: 'Optional[ComponentsLibrary]' = None) -> 'Scenario'` - Constructs a Scenario from a YAML string, optionally merging
- `run(self) -> 'None'` - Executes the scenario's workflow steps in order.

---

## ngraph.model.components

Component and ComponentsLibrary classes for hardware capex/power modeling.

### Component

A generic component that can represent chassis, line cards, optics, etc.
Components can have nested children, each with their own capex, power, etc.

Attributes:
    name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
    component_type (str): A string label (e.g., "chassis", "linecard", "optic").
    description (str): A human-readable description of this component.
    capex (float): Monetary capex of a single instance of this component.
    power_watts (float): Typical/nominal power usage (watts) for one instance.
    power_watts_max (float): Maximum/peak power usage (watts) for one instance.
    capacity (float): A generic capacity measure (e.g., platform capacity).
    ports (int): Number of ports if relevant for this component.
    count (int): How many identical copies of this component are present.
    attrs (Dict[str, Any]): Arbitrary key-value attributes for extra metadata.
    children (Dict[str, Component]): Nested child components (e.g., line cards
        inside a chassis), keyed by child name.

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
- `total_capacity(self) -> 'float'` - Computes the total (recursive) capacity of this component,
- `total_capex(self) -> 'float'` - Computes total capex including children, multiplied by count.
- `total_power(self) -> 'float'` - Computes the total *typical* (recursive) power usage of this component,
- `total_power_max(self) -> 'float'` - Computes the total *peak* (recursive) power usage of this component,

### ComponentsLibrary

Holds a collection of named Components. Each entry is a top-level "template"
that can be referenced for cost/power/capacity lookups, possibly with nested children.

Example (YAML-like):
    components:
      BigSwitch:
        component_type: chassis
        cost: 20000
        power_watts: 1750
        capacity: 25600
        children:
          PIM16Q-16x200G:
            component_type: linecard
            cost: 1000
            power_watts: 10
            ports: 16
            count: 8
      200G-FR4:
        component_type: optic
        cost: 2000
        power_watts: 6
        power_watts_max: 6.5

**Attributes:**

- `components` (Dict[str, Component]) = {}

**Methods:**

- `clone(self) -> 'ComponentsLibrary'` - Creates a deep copy of this ComponentsLibrary.
- `from_dict(data: 'Dict[str, Any]') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from a dictionary of raw component definitions.
- `from_yaml(yaml_str: 'str') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from a YAML string. If the YAML contains
- `get(self, name: 'str') -> 'Optional[Component]'` - Retrieves a Component by its name from the library.
- `merge(self, other: 'ComponentsLibrary', override: 'bool' = True) -> 'ComponentsLibrary'` - Merges another ComponentsLibrary into this one. By default (override=True),

### resolve_link_end_components(attrs: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'tuple[tuple[Optional[Component], float, bool], tuple[Optional[Component], float, bool], bool]'

Resolve per-end hardware components for a link.

Input format inside ``link.attrs``:

Structured mapping under ``hardware`` key only:
  ``{"hardware": {"source": {"component": NAME, "count": N},
                   "target": {"component": NAME, "count": N}}}``

Args:
    attrs: Link attributes mapping.
    library: Components library for lookups.

Exclusive usage:

- Optional ``exclusive: true`` per end indicates unsharable usage.

    For exclusive ends, validation and BOM counting should round-up counts
    to integers.

Returns:
    ((src_comp, src_count, src_exclusive), (dst_comp, dst_count, dst_exclusive), per_end_specified)
    where components may be ``None`` if name is absent/unknown. ``per_end_specified``
    is True when a structured per-end mapping is present.

### resolve_node_hardware(attrs: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'Tuple[Optional[Component], float]'

Resolve node hardware from ``attrs['hardware']``.

Expects the mapping: ``{"hardware": {"component": NAME, "count": N}}``.
``count`` defaults to 1 if missing or invalid. If ``component`` is missing
or unknown, returns ``(None, 1.0)``.

Args:
    attrs: Node attributes mapping.
    library: Component library used for lookups.

Returns:
    Tuple of (component or None, positive multiplier).

### totals_with_multiplier(comp: 'Component', hw_count: 'float') -> 'Tuple[float, float, float]'

Return (capex, power_watts, capacity) totals multiplied by ``hw_count``.

Args:
    comp: Component definition (may include nested children and internal ``count``).
    hw_count: External multiplier (e.g., number of modules used for a link or node).

Returns:
    Tuple of total capex, total power (typical), and total capacity as floats.

---

## ngraph.model.demand.builder

Builders for demand sets.

Construct `DemandSet` from raw dictionaries (e.g. parsed YAML).

### build_demand_set(raw: 'Dict[str, List[dict]]') -> 'DemandSet'

Build a `DemandSet` from a mapping of name -> list of dicts.

Args:
    raw: Mapping where each key is a demand set name and each value is a list of
        dictionaries with `TrafficDemand` constructor fields.

Returns:
    Initialized `DemandSet` with constructed `TrafficDemand` objects.

Raises:
    ValueError: If ``raw`` is not a mapping of name -> list[dict],
        or if required fields are missing.

---

## ngraph.model.demand.matrix

Demand set containers.

Provides `DemandSet`, a named collection of `TrafficDemand` lists
used as input to demand expansion and placement. This module contains input
containers, not analysis results.

### DemandSet

Named collection of TrafficDemand lists.

This mutable container maps set names to lists of TrafficDemand objects,
allowing management of multiple demand sets for analysis.

Attributes:
    sets: Dictionary mapping set names to TrafficDemand lists.

**Attributes:**

- `sets` (dict[str, list[TrafficDemand]]) = {}

**Methods:**

- `add(self, name: 'str', demands: 'list[TrafficDemand]') -> 'None'` - Add a demand list to the collection.
- `get_all_demands(self) -> 'list[TrafficDemand]'` - Get all traffic demands from all sets combined.
- `get_default_set(self) -> 'list[TrafficDemand]'` - Get default demand set.
- `get_set(self, name: 'str') -> 'list[TrafficDemand]'` - Get a specific demand set by name.
- `to_dict(self) -> 'dict[str, Any]'` - Convert to dictionary for JSON serialization.

---

## ngraph.model.demand.spec

Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyPreset` enum to construct one.

### TrafficDemand

Traffic demand specification using unified selectors.

Attributes:
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    volume: Total demand volume.
    volume_placed: Portion of this demand placed so far.
    priority: Priority class (lower = higher priority).
    mode: Node pairing mode ("combine" or "pairwise").
    group_mode: How grouped nodes produce demands
        ("flatten", "per_group", "group_pairwise").
    flow_policy: Policy preset for routing.
    flow_policy_obj: Concrete policy instance (overrides flow_policy).
    attrs: Arbitrary user metadata.
    id: Unique identifier. Auto-generated if empty.

**Attributes:**

- `source` (Union)
- `target` (Union)
- `volume` (float) = 0.0
- `volume_placed` (float) = 0.0
- `priority` (int) = 0
- `mode` (str) = combine
- `group_mode` (str) = flatten
- `flow_policy` (Optional)
- `flow_policy_obj` (Optional)
- `attrs` (Dict) = {}
- `id` (str)

---

## ngraph.model.failure.generate

Dynamic risk group generation from entity attributes.

Provides functionality to auto-generate risk groups based on unique
attribute values from nodes or links.

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

### generate_risk_groups(network: "'Network'", spec: 'GenerateSpec') -> 'List[RiskGroup]'

Generate risk groups from unique attribute values.

For each unique value of the specified attribute, creates a new risk
group and adds all matching entities to it.

Args:
    network: Network with nodes and links populated.
    spec: Generation specification.

Returns:
    List of newly created RiskGroup objects.

Note:
    This function modifies entity risk_groups sets in place.

### parse_generate_spec(raw: 'Dict[str, Any]') -> 'GenerateSpec'

Parse raw generate dict into a GenerateSpec.

Args:
    raw: Raw generate dict from YAML.

Returns:
    Parsed GenerateSpec.

Raises:
    ValueError: If required fields are missing or invalid.

---

## ngraph.model.failure.membership

Risk group membership rule resolution.

Provides functionality to resolve policy-based membership rules that
auto-assign entities (nodes, links, risk groups) to risk groups based
on attribute conditions.

### MembershipSpec

Parsed membership rule specification.

Attributes:
    scope: Type of entities to match ("node", "link", or "risk_group").
    path: Optional regex pattern to filter entities by name.
    match: Match specification with conditions.

**Attributes:**

- `scope` (EntityScope)
- `path` (Optional[str])
- `match` (Optional[MatchSpec])

### resolve_membership_rules(network: "'Network'") -> 'None'

Apply membership rules to populate entity risk_groups sets.

For each risk group with a `_membership_raw` specification:

- If scope is "node" or "link": adds the risk group name to each

  matched entity's risk_groups set.

- If scope is "risk_group": adds matched risk groups as children

  of this risk group (hierarchical membership).

Args:
    network: Network with risk_groups, nodes, and links populated.

Note:
    This function modifies entities in place. It should be called after
    all risk groups are registered but before validation.

---

## ngraph.model.failure.parser

Parsers for FailurePolicySet and related failure modeling structures.

### build_failure_policy(fp_data: 'Dict[str, Any]', *, policy_name: 'str', derive_seed: 'Callable[[str], Optional[int]]') -> 'FailurePolicy'

Build a FailurePolicy from a raw configuration dictionary.

Parses modes, rules, and conditions from the policy definition and
constructs a fully initialized FailurePolicy object.

Args:
    fp_data: Policy definition dict with keys: modes (required), attrs,
        expand_groups, expand_children. Each mode contains weight and rules.
    policy_name: Name identifier for this policy (used for seed derivation).
    derive_seed: Callable to derive deterministic seeds from component names.

Returns:
    FailurePolicy: Configured policy with parsed modes and rules.

Raises:
    ValueError: If modes is empty or malformed, or if rules are invalid.

### build_failure_policy_set(raw: 'Dict[str, Any]', *, derive_seed: 'Callable[[str], Optional[int]]') -> 'FailurePolicySet'

Build a FailurePolicySet from raw config data.

Args:
    raw: Mapping of policy name -> policy definition dict.
    derive_seed: Callable to derive deterministic seeds from component names.

Returns:
    Configured FailurePolicySet.

Raises:
    ValueError: If raw is not a dict or contains invalid policy definitions.

### build_risk_groups(rg_data: 'List[Any]') -> 'tuple[List[RiskGroup], List[Dict[str, Any]]]'

Build RiskGroup objects from raw config data.

Supports:

- String shorthand: "GroupName" is equivalent to {name: "GroupName"}
- Bracket expansion: {name: "DC[1-3]_Power"} creates DC1_Power, DC2_Power, DC3_Power
- Children are also expanded recursively
- Generate blocks: {generate: {...}} for dynamic group creation

Args:
    rg_data: List of risk group definitions (strings or dicts).

Returns:
    Tuple of (explicit_risk_groups, generate_specs_raw):

- explicit_risk_groups: List of RiskGroup objects with names expanded.
- generate_specs_raw: List of raw generate block dicts for deferred processing.

---

## ngraph.model.failure.policy

Failure policy primitives.

Defines `FailureRule` and `FailurePolicy` for expressing how nodes, links,
and risk groups fail in analyses. Conditions match on top-level attributes
with simple operators; rules select matches using "all", probabilistic
"random" (with `probability`), or fixed-size "choice" (with `count`).
Policies can optionally expand failures by shared risk groups or by
risk-group children.

### FailureMode

A weighted mode that encapsulates a set of rules applied together.

Exactly one mode is selected per failure iteration according to the
mode weights. Within a mode, all contained rules are applied and their
selections are unioned into the failure set.

Attributes:
    weight: Non-negative weight used for mode selection. All weights are
        normalized internally. Modes with zero weight are never selected.
    rules: A list of `FailureRule` applied together when this mode is chosen.
    attrs: Optional metadata.

**Attributes:**

- `weight` (float)
- `rules` (List[FailureRule]) = []
- `attrs` (Dict[str, Any]) = {}

### FailurePolicy

A container for failure modes plus optional metadata in `attrs`.

The main entry point is `apply_failures`, which:
  1) Select a mode based on weights.
  2) For each rule in the mode, gather relevant entities.
  3) Match based on rule conditions using 'and' or 'or' logic.
  4) Apply the selection strategy (all, random, or choice).
  5) Collect the union of all failed entities across all rules.
  6) Optionally expand failures by shared-risk groups or sub-risks.

Attributes:
    attrs: Arbitrary metadata about this policy.
    expand_groups: If True, expand failures among entities sharing
        risk groups with failed entities.
    expand_children: If True, expand failed risk groups to include
        their children recursively.
    seed: Seed for reproducible random operations.
    modes: List of weighted failure modes.

**Attributes:**

- `attrs` (Dict[str, Any]) = {}
- `expand_groups` (bool) = False
- `expand_children` (bool) = False
- `seed` (Optional[int])
- `modes` (List[FailureMode]) = []

**Methods:**

- `apply_failures(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None, *, seed: 'Optional[int]' = None, failure_trace: 'Optional[Dict[str, Any]]' = None) -> 'List[str]'` - Identify which entities fail for this iteration.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

### FailureRule

Defines how to match and then select entities for failure.

Attributes:
    scope: The type of entities this rule applies to: "node", "link",
        or "risk_group".
    conditions: A list of conditions to filter matching entities.
    logic: "and" (all must be true) or "or" (any must be true, default).
    mode: The selection strategy among the matched set:

- "random": each matched entity is chosen with probability.
- "choice": pick exactly `count` items (random sample).
- "all": select every matched entity.

    probability: Probability in [0,1], used if mode="random".
    count: Number of entities to pick if mode="choice".
    weight_by: Optional attribute for weighted sampling in choice mode.
    path: Optional regex pattern to filter entities by name.

**Attributes:**

- `scope` (EntityScope)
- `conditions` (List[Condition]) = []
- `logic` (Literal['and', 'or']) = or
- `mode` (Literal['random', 'choice', 'all']) = all
- `probability` (float) = 1.0
- `count` (int) = 1
- `weight_by` (Optional[str])
- `path` (Optional[str])

---

## ngraph.model.failure.policy_set

Failure policy containers.

Provides `FailurePolicySet`, a named collection of `FailurePolicy` objects
used as input to failure analysis workflows. This module contains input
containers, not analysis results.

### FailurePolicySet

Named collection of FailurePolicy objects.

This mutable container maps failure policy names to FailurePolicy objects,
allowing management of multiple failure policies for analysis.

Attributes:
    policies: Dictionary mapping failure policy names to FailurePolicy objects.

**Attributes:**

- `policies` (dict[str, FailurePolicy]) = {}

**Methods:**

- `add(self, name: 'str', policy: 'FailurePolicy') -> 'None'` - Add a failure policy to the collection.
- `get_all_policies(self) -> 'list[FailurePolicy]'` - Get all failure policies from the collection.
- `get_policy(self, name: 'str') -> 'FailurePolicy'` - Get a specific failure policy by name.
- `to_dict(self) -> 'dict[str, Any]'` - Convert to dictionary for JSON serialization.

---

## ngraph.model.failure.validation

Risk group reference validation.

Validates that all risk group references in nodes and links resolve to
defined risk groups. Catches typos and missing definitions early.

Also provides cycle detection for risk group hierarchies.

### validate_risk_group_hierarchy(network: "'Network'") -> 'None'

Detect circular references in risk group parent-child relationships.

Uses DFS-based cycle detection to find any risk group that is part of
a cycle in the children hierarchy. This can happen when membership rules
with scope='risk_group' create mutual parent-child relationships.

Args:
    network: Network with risk_groups populated (after membership resolution).

Raises:
    ValueError: If a cycle is detected, with details about the cycle path.

### validate_risk_group_references(network: "'Network'") -> 'None'

Ensure all risk group references resolve to defined groups.

Checks that every risk group name referenced by nodes and links
exists in network.risk_groups. This catches typos and missing
definitions that would otherwise cause silent failures in simulations.

Args:
    network: Network with nodes, links, and risk_groups populated.

Raises:
    ValueError: If any node or link references an undefined risk group.
        The error message lists up to 10 violations with entity names
        and the undefined group names.

---

## ngraph.model.flow.policy_config

Flow policy preset configurations for NetGraph.

Provides convenient factory functions to create common FlowPolicy configurations
using NetGraph-Core's FlowPolicy and FlowPolicyConfig.

### FlowPolicyPreset

Enumerates common flow policy presets for traffic routing.

These presets map to specific combinations of path algorithms, flow placement
strategies, and edge selection modes provided by NetGraph-Core.

### create_flow_policy(algorithms: 'netgraph_core.Algorithms', graph: 'netgraph_core.Graph', preset: 'FlowPolicyPreset', node_mask=None, edge_mask=None) -> 'netgraph_core.FlowPolicy'

Create a FlowPolicy instance from a preset configuration.

Args:
    algorithms: NetGraph-Core Algorithms instance.
    graph: NetGraph-Core Graph handle.
    preset: FlowPolicyPreset enum value specifying the desired policy.
    node_mask: Optional numpy bool array for node exclusions (True = include).
    edge_mask: Optional numpy bool array for edge exclusions (True = include).

Returns:
    netgraph_core.FlowPolicy: Configured policy instance.

Raises:
    ValueError: If an unknown FlowPolicyPreset value is provided.

Example:
    >>> backend = netgraph_core.Backend.cpu()
    >>> algs = netgraph_core.Algorithms(backend)
    >>> graph = algs.build_graph(strict_multidigraph)
    >>> policy = create_flow_policy(algs, graph, FlowPolicyPreset.SHORTEST_PATHS_ECMP)

### serialize_policy_preset(cfg: 'Any') -> 'Optional[str]'

Serialize a FlowPolicyPreset to its string name for JSON storage.

Handles FlowPolicyPreset enum values, integer enum values, and string inputs.
Returns None for None input.

Args:
    cfg: FlowPolicyPreset enum, integer, or other value to serialize.

Returns:
    String name of the preset (e.g., "SHORTEST_PATHS_ECMP"), or None if input is None.

---

## ngraph.model.network

Network topology modeling with Node, Link, RiskGroup, and Network classes.

This module provides the core network model classes (Node, Link, RiskGroup, Network)
that can be used independently.

### Link

Represents one directed link between two nodes.

The model stores a single direction (``source`` -> ``target``). When building
the working graph for analysis, a reverse edge is added by default to provide
bidirectional connectivity. Disable with ``add_reverse=False`` in
``Network.to_strict_multidigraph``.

Attributes:
    source (str): Name of the source node.
    target (str): Name of the target node.
    capacity (float): Link capacity (default 1.0).
    cost (float): Link cost (default 1.0).
    disabled (bool): Whether the link is disabled.
    risk_groups (Set[str]): Set of risk group names this link belongs to.
    attrs (Dict[str, Any]): Additional metadata (e.g., distance).
    id (str): Auto-generated unique identifier: "{source}|{target}|<base64_uuid>".

**Attributes:**

- `source` (str)
- `target` (str)
- `capacity` (float) = 1.0
- `cost` (float) = 1.0
- `disabled` (bool) = False
- `risk_groups` (Set[str]) = set()
- `attrs` (Dict[str, Any]) = {}
- `id` (str)

### Network

A container for network nodes and links.

Network represents the scenario-level topology with persistent state (nodes/links
that are disabled in the scenario configuration). For temporary exclusion of
nodes/links during analysis (e.g., failure simulation), use node_mask and edge_mask
parameters when calling NetGraph-Core algorithms.

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
- `_selection_cache` (Dict[str, Dict[str, List[Node]]]) = {}

**Methods:**

- `add_link(self, link: 'Link') -> 'None'` - Add a link to the network (keyed by the link's auto-generated ID).
- `add_node(self, node: 'Node') -> 'None'` - Add a node to the network (keyed by node.name).
- `disable_all(self) -> 'None'` - Mark all nodes and links as disabled.
- `disable_link(self, link_id: 'str') -> 'None'` - Mark a link as disabled.
- `disable_node(self, node_name: 'str') -> 'None'` - Mark a node as disabled.
- `disable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'` - Disable all nodes/links that have 'name' in their risk_groups.
- `enable_all(self) -> 'None'` - Mark all nodes and links as enabled.
- `enable_link(self, link_id: 'str') -> 'None'` - Mark a link as enabled.
- `enable_node(self, node_name: 'str') -> 'None'` - Mark a node as enabled.
- `enable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'` - Enable all nodes/links that have 'name' in their risk_groups.
- `find_links(self, source_regex: 'Optional[str]' = None, target_regex: 'Optional[str]' = None, any_direction: 'bool' = False) -> 'List[Link]'` - Search for links using optional regex patterns for source or target node names.
- `get_links_between(self, source: 'str', target: 'str') -> 'List[str]'` - Retrieve all link IDs that connect the specified source node
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'` - Select and group nodes by regex pattern on node name.

### Node

Represents a node in the network.

Each node is uniquely identified by its name, which is used as
the key in the Network's node dictionary.

Attributes:
    name (str): Unique identifier for the node.
    disabled (bool): Whether the node is disabled in the scenario configuration.
    risk_groups (Set[str]): Set of risk group names this node belongs to.
    attrs (Dict[str, Any]): Additional metadata (e.g., coordinates, region).

**Attributes:**

- `name` (str)
- `disabled` (bool) = False
- `risk_groups` (Set[str]) = set()
- `attrs` (Dict[str, Any]) = {}

### RiskGroup

Represents a shared-risk or failure domain, which may have nested children.

Risk groups model correlated failures: when a risk group fails, all entities
(nodes, links) in that group fail together. Hierarchical children enable
cascading failures (parent failure implies all descendants fail).

Risk groups can be created three ways:

1. Direct definition: Explicitly named in YAML risk_groups section
2. Membership rules: Auto-assign entities based on attribute matching
3. Generate blocks: Auto-create groups from unique attribute values

Attributes:
    name (str): Unique name of this risk group.
    children (List[RiskGroup]): Subdomains in a nested structure.
    disabled (bool): Whether this group was declared disabled on load.
    attrs (Dict[str, Any]): Additional metadata for the risk group.
    _membership_raw (Optional[Dict[str, Any]]): Raw membership rule for
        deferred resolution. Internal use only.

**Attributes:**

- `name` (str)
- `children` (List[RiskGroup]) = []
- `disabled` (bool) = False
- `attrs` (Dict[str, Any]) = {}
- `_membership_raw` (Optional[Dict[str, Any]])

---

## ngraph.model.path

Lightweight representation of a single routing path.

The ``Path`` dataclass stores a node-and-parallel-edges sequence and a numeric
cost. Cached properties expose derived sequences for nodes and edges, and
helpers provide equality, ordering by cost, and sub-path extraction with cost
recalculation.

### Path

Represents a single path in the network.

Attributes:
    path: Sequence of (node_name, (edge_refs...)) tuples representing the path.
          The final element typically has an empty tuple of edge refs.
    cost: Total numeric cost (e.g., distance or metric) of the path.
    edges: Set of all EdgeRefs encountered in the path.
    nodes: Set of all node names encountered in the path.
    edge_tuples: Set of all tuples of parallel EdgeRefs from each path element.

**Attributes:**

- `path` (Tuple[Tuple[str, Tuple[EdgeRef, ...]], ...])
- `cost` (Cost)
- `edges` (Set[EdgeRef]) = set()
- `nodes` (Set[str]) = set()
- `edge_tuples` (Set[Tuple[EdgeRef, ...]]) = set()

**Methods:**

- `get_sub_path(self, dst_node: 'str') -> 'Path'` - Create a sub-path ending at the specified destination node.

---

## ngraph.workflow.base

Base classes for workflow automation.

Defines the workflow step abstraction, registration decorator, and execution
lifecycle. Steps implement `run()` and are executed via `execute()` which
handles timing, logging, and metadata recording. Failures are logged and
re-raised.

### WorkflowStep

Base class for all workflow steps.

All workflow steps are automatically logged with execution timing information.
All workflow steps support seeding for reproducible random operations.
Workflow metadata is automatically stored in scenario.results for analysis.

YAML Configuration:
    ```yaml
    workflow:
      - type: <StepTypeName>

        name: "optional_step_name"  # Optional: Custom name for this step instance
        seed: 42                    # Optional: Seed for reproducible random operations
        # ... step-specific parameters ...
    ```

Attributes:
    name: Optional custom identifier for this workflow step instance,
        used for logging and result storage purposes.
    seed: Optional seed for reproducible random operations. If None,
        random operations will be non-deterministic.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step logic.

### register_workflow_step(step_type: 'str')

Return a decorator that registers a `WorkflowStep` subclass.

Args:
    step_type: Registry key used to instantiate steps from configuration.

Returns:
    A class decorator that adds the class to `WORKFLOW_STEP_REGISTRY`.

### resolve_parallelism(parallelism: 'Union[int, str]') -> 'int'

Resolve parallelism setting to a concrete worker count.

Args:
    parallelism: Either an integer worker count or "auto" for CPU count.

Returns:
    Positive integer worker count (minimum 1).

---

## ngraph.workflow.build_graph

Graph building workflow component.

Validates and exports network topology as a node-link representation using NetworkX.
Actual graph building for analysis happens in analysis functions; this step
primarily validates the network and stores a serializable representation for
inspection.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: BuildGraph

        name: "build_network_graph"  # Optional: Custom name for this step
        add_reverse: true  # Optional: Add reverse edges (default: true)
    ```

The `add_reverse` parameter controls whether reverse edges are added for each link.
When `True` (default), each Link(A→B) gets both forward(A→B) and reverse(B→A) edges
for bidirectional connectivity. Set to `False` for directed-only graphs.

Results stored in `scenario.results` under the step name as two keys:

- metadata: Step-level execution metadata (node/link counts)
- data: { graph: node-link JSON dict, context: { add_reverse: bool } }

### BuildGraph

Validates network topology and stores node-link representation.

This step validates the network structure and stores a JSON-serializable
node-link representation using NetworkX. Core graph building happens in
analysis functions as needed.

Attributes:
    add_reverse: If True, adds reverse edges for bidirectional connectivity.
                 Defaults to True.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)
- `add_reverse` (bool) = True

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Scenario') -> 'None'` - Validate network and store node-link representation.

---

## ngraph.workflow.cost_power

CostPower workflow step: collect capex and power by hierarchy level.

This step aggregates capex and power from the network hardware inventory without
performing any normalization or reporting. It separates contributions into two
categories:

- platform_*: node hardware (e.g., chassis, linecards) resolved from node attrs
- optics_*: per-end link hardware (e.g., optics) resolved from link attrs

Aggregation is computed at hierarchy levels 0..N where level 0 is the global
root (path ""), and higher levels correspond to prefixes of node names split by
"/". For example, for node "dc1/plane1/leaf/leaf-1":

- level 1 path is "dc1"
- level 2 path is "dc1/plane1"
- etc.

Disabled handling:

- When include_disabled is False, only enabled nodes and links are considered.
- Optics are counted only when the endpoint node has platform hardware.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: CostPower

        name: "cost_power"           # Optional custom name
        include_disabled: false       # Default: only enabled nodes/links
        aggregation_level: 2          # Produce levels: 0, 1, 2
    ```

Results stored in `scenario.results` under this step namespace:
    data:
      context:
        include_disabled: bool
        aggregation_level: int
      levels:
        "0":

- path: ""

            platform_capex: float
            platform_power_watts: float
            optics_capex: float
            optics_power_watts: float
            capex_total: float
            power_total_watts: float
        "1": [ ... ]
        "2": [ ... ]

### CostPower

Collect platform and optics capex/power by aggregation level.

Attributes:
    include_disabled: If True, include disabled nodes and links.
    aggregation_level: Inclusive depth for aggregation. 0=root only.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)
- `include_disabled` (bool) = False
- `aggregation_level` (int) = 2

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Any') -> 'None'` - Aggregate capex and power by hierarchy levels 0..N.

---

## ngraph.workflow.max_flow_step

MaxFlow workflow step.

Monte Carlo analysis of maximum flow capacity between node groups using FailureManager.
Produces unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) is always run first as a separate reference. The `iterations`
parameter specifies how many failure scenarios to run.

YAML Configuration Example:

    workflow:

- type: MaxFlow

        name: "maxflow_dc_to_edge"
        source: "^datacenter/.*"
        target: "^edge/.*"
        mode: "combine"
        failure_policy: "random_failures"
        iterations: 100
        parallelism: auto
        shortest_path: false
        require_capacity: true           # false for true IP/IGP semantics
        flow_placement: "PROPORTIONAL"
        seed: 42
        store_failure_patterns: false
        include_flow_details: false      # cost_distribution
        include_min_cut: false           # min-cut edges list

### MaxFlow

Maximum flow Monte Carlo workflow step.

Baseline (no failures) is always run first as a separate reference. Results are
returned with baseline in a separate field. The flow_results list contains unique
failure patterns (deduplicated); each result has occurrence_count indicating how
many iterations matched that pattern.

Attributes:
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    mode: Flow analysis mode ("combine" or "pairwise").
    failure_policy: Name of failure policy in scenario.failure_policy_set.
    iterations: Number of failure iterations to run.
    parallelism: Number of parallel worker processes.
    shortest_path: Whether to use shortest paths only.
    require_capacity: If True (default), path selection considers capacity.
        If False, path selection is cost-only (true IP/IGP semantics).
    flow_placement: Flow placement strategy.
    seed: Optional seed for reproducible results.
    store_failure_patterns: Whether to store failure patterns in results.
    include_flow_details: Whether to collect cost distribution per flow.
    include_min_cut: Whether to include min-cut edges per flow.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `_seed_source` (str)
- `source` (Union[str, Dict[str, Any]])
- `target` (Union[str, Dict[str, Any]])
- `mode` (str) = combine
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int | str) = auto
- `shortest_path` (bool) = False
- `require_capacity` (bool) = True
- `flow_placement` (FlowPlacement | str) = 1
- `store_failure_patterns` (bool) = False
- `include_flow_details` (bool) = False
- `include_min_cut` (bool) = False

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step logic.

---

## ngraph.workflow.maximum_supported_demand_step

MaximumSupportedDemand workflow step.

Searches for the maximum uniform traffic multiplier `alpha_star` that is fully
placeable for a given demand set. Stores results under `data` as:

- `alpha_star`: float
- `context`: parameters used for the search
- `base_demands`: serialized base demand specs
- `probes`: bracket/bisect evaluations with feasibility

Performance: AnalysisContext is built once at search start and reused across
all binary search probes. Only demand volumes change per probe.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: MaximumSupportedDemand

        name: "msd_search"
        demand_set: "default"
        resolution: 0.01        # Convergence threshold
        max_bisect_iters: 50    # Maximum bisection iterations
        alpha_start: 1.0        # Starting multiplier
        growth_factor: 2.0      # Bracket expansion factor
    ```

### MaximumSupportedDemand

Finds the maximum uniform traffic multiplier that is fully placeable.

Uses binary search to find alpha_star, the maximum multiplier for all
demands in the set that can still be fully placed on the network.

Attributes:
    demand_set: Name of the demand set to analyze.
    acceptance_rule: Currently only "hard" is implemented.
    alpha_start: Starting multiplier for binary search.
    growth_factor: Factor for bracket expansion.
    alpha_min: Minimum allowed alpha value.
    alpha_max: Maximum allowed alpha value.
    resolution: Convergence threshold for binary search.
    max_bracket_iters: Maximum iterations for bracketing phase.
    max_bisect_iters: Maximum iterations for bisection phase.
    seeds_per_alpha: Number of placement attempts per alpha probe.
    placement_rounds: Placement optimization rounds.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)
- `demand_set` (str) = default
- `acceptance_rule` (str) = hard
- `alpha_start` (float) = 1.0
- `growth_factor` (float) = 2.0
- `alpha_min` (float) = 1e-06
- `alpha_max` (float) = 1000000000.0
- `resolution` (float) = 0.01
- `max_bracket_iters` (int) = 32
- `max_bisect_iters` (int) = 32
- `seeds_per_alpha` (int) = 1
- `placement_rounds` (int | str) = auto

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Any'") -> 'None'` - Execute the workflow step logic.

---

## ngraph.workflow.network_stats

Workflow step for basic node and link statistics.

Computes and stores network statistics including node/link counts,
capacity distributions, cost distributions, and degree distributions. Supports
optional exclusion simulation and disabled entity handling.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: NetworkStats

        name: "network_statistics"           # Optional: Custom name for this step
        include_disabled: false              # Include disabled nodes/links in stats
        excluded_nodes: ["node1", "node2"]   # Optional: Temporary node exclusions
        excluded_links: ["link1", "link3"]   # Optional: Temporary link exclusions
    ```

Results stored in `scenario.results`:

- Node statistics: node_count
- Link statistics: link_count, total_capacity, mean_capacity, median_capacity,

      min_capacity, max_capacity, mean_cost, median_cost, min_cost, max_cost

- Degree statistics: mean_degree, median_degree, min_degree, max_degree

### NetworkStats

Compute basic node and link statistics for the network.

Supports optional exclusion simulation without modifying the base network.

Attributes:
    include_disabled: If True, include disabled nodes and links in statistics.
        If False, only consider enabled entities.
    excluded_nodes: Optional list of node names to exclude (temporary exclusion).
    excluded_links: Optional list of link IDs to exclude (temporary exclusion).

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)
- `include_disabled` (bool) = False
- `excluded_nodes` (Iterable[str]) = ()
- `excluded_links` (Iterable[str]) = ()

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Scenario') -> 'None'` - Compute and store network statistics.

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
    A list of WorkflowStep instances with unique names and optional seeds.

---

## ngraph.workflow.traffic_matrix_placement_step

TrafficMatrixPlacement workflow step.

Runs Monte Carlo demand placement using a named demand set and produces
unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) is always run first as a separate reference. The `iterations`
parameter specifies how many failure scenarios to run.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: TrafficMatrixPlacement

        name: "tm_analysis"
        demand_set: "default"
        failure_policy: "single_link"    # Optional: failure policy name
        iterations: 100                  # Number of failure scenarios
        parallelism: 4                   # Worker processes (or "auto")
        alpha: 1.0                       # Demand volume multiplier
        include_flow_details: true       # Include cost distribution per flow
    ```

### TrafficMatrixPlacement

Monte Carlo demand placement using a named demand set.

Baseline (no failures) is always run first as a separate reference. Results are
returned with baseline in a separate field. The flow_results list contains unique
failure patterns (deduplicated); each result has occurrence_count indicating how
many iterations matched that pattern.

Attributes:
    demand_set: Name of the demand set to analyze.
    failure_policy: Optional failure policy name in scenario.failure_policy_set.
    iterations: Number of failure iterations to run.
    parallelism: Number of parallel worker processes.
    placement_rounds: Placement optimization rounds (int or "auto").
    seed: Optional seed for reproducibility.
    store_failure_patterns: Whether to store failure pattern results.
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    alpha: Numeric scale for demands in the set.
    alpha_from_step: Optional producer step name to read alpha from.
    alpha_from_field: Dotted field path in producer step (default: "data.alpha_star").

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `_seed_source` (str)
- `demand_set` (str)
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int | str) = auto
- `placement_rounds` (int | str) = auto
- `store_failure_patterns` (bool) = False
- `include_flow_details` (bool) = False
- `include_used_edges` (bool) = False
- `alpha` (float) = 1.0
- `alpha_from_step` (str | None)
- `alpha_from_field` (str) = data.alpha_star

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step logic.

---

## ngraph.dsl.blueprints.expand

Network topology blueprints and generation.

### Blueprint

Represents a reusable blueprint for hierarchical sub-topologies.

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

Carries the blueprint definitions and the final Network instance
to be populated during DSL expansion.

Attributes:
    blueprints: Dictionary of blueprint-name -> Blueprint.
    network: The Network into which expanded nodes/links are inserted.
    pending_bp_links: Deferred blueprint link expansions.

**Attributes:**

- `blueprints` (Dict[str, Blueprint])
- `network` (Network)
- `pending_bp_links` (List[tuple[Dict[str, Any], str]]) = []

### expand_network_dsl(data: 'Dict[str, Any]') -> 'Network'

Expands a combined blueprint + network DSL into a complete Network object.

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

- Only certain top-level fields are permitted in each structure.
- Link properties are flat (capacity, cost, etc. at link level).
- For node definitions: count, template, attrs, disabled, risk_groups,

    or blueprint for blueprint-based nodes.

Args:
    data: The YAML-parsed dictionary containing optional "blueprints" + "network".

Returns:
    The expanded Network object with all nodes and links.

---

## ngraph.dsl.blueprints.parser

Parsing helpers for the network DSL.

This module factors out pure parsing/validation helpers from the expansion
module so they can be tested independently and reused.

### check_link_keys(link_def: 'Dict[str, Any]', context: 'str') -> 'None'

Ensure link definitions only contain recognized keys.

### check_no_extra_keys(data_dict: 'Dict[str, Any]', allowed: 'set[str]', context: 'str') -> 'None'

Raise if ``data_dict`` contains keys outside ``allowed``.

Args:
    data_dict: The dict to check.
    allowed: Set of recognized keys.
    context: Short description used in error messages.

### join_paths(parent_path: 'str', rel_path: 'str') -> 'str'

Join two path segments according to DSL conventions.

The DSL has no concept of absolute paths. All paths are relative to the
current context (parent_path). A leading "/" on rel_path is stripped and
has no functional effect - it serves only as a visual indicator that the
path starts from the current scope's root.

Behavior:

- Leading "/" on rel_path is stripped (not treated as filesystem root)
- Result is always: "{parent_path}/{stripped_rel_path}" if parent_path is non-empty
- Examples:

    join_paths("", "/leaf") -> "leaf"
    join_paths("pod1", "/leaf") -> "pod1/leaf"
    join_paths("pod1", "leaf") -> "pod1/leaf"  (same result)

Args:
    parent_path: Parent path prefix (e.g., "pod1" when expanding a blueprint).
    rel_path: Path to join. Leading "/" is stripped if present.

Returns:
    Combined path string.

---

## ngraph.dsl.expansion.brackets

Bracket expansion for name patterns.

Provides expand_name_patterns() for expanding bracket expressions
like "fa[1-3]" into ["fa1", "fa2", "fa3"].

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
    ["fa1", "fa2", "fa3"]
    >>> expand_name_patterns("dc[1,3,5-6]")
    ["dc1", "dc3", "dc5", "dc6"]
    >>> expand_name_patterns("fa[1-2]_plane[5-6]")
    ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]

### expand_risk_group_refs(rg_list: 'Iterable[str]') -> 'Set[str]'

Expand bracket patterns in a list of risk group references.

Takes an iterable of risk group names (possibly containing bracket
expressions) and returns a set of all expanded names.

Args:
    rg_list: Iterable of risk group name patterns.

Returns:
    Set of expanded risk group names.

Examples:
    >>> expand_risk_group_refs(["RG1"])
    {"RG1"}
    >>> expand_risk_group_refs(["RG[1-3]"])
    {"RG1", "RG2", "RG3"}
    >>> expand_risk_group_refs(["A[1-2]", "B[a,b]"])
    {"A1", "A2", "Ba", "Bb"}

---

## ngraph.dsl.expansion.schema

Schema definitions for variable expansion.

Provides dataclasses for template expansion configuration.

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

Provides substitution of $var and ${var} placeholders in strings,
with recursive substitution in nested structures.

### expand_block(block: 'Dict[str, Any]', spec: "Optional['ExpansionSpec']") -> 'Iterator[Dict[str, Any]]'

Expand a DSL block, yielding one dict per variable combination.

If no expand spec is provided or it has no vars, yields the original block.
Otherwise, yields a deep copy with all strings substituted for each
variable combination.

Args:
    block: DSL block (dict) that may contain template strings.
    spec: Optional expansion specification.

Yields:
    Dict with variable substitutions applied.

### expand_templates(templates: 'Dict[str, str]', spec: "'ExpansionSpec'") -> 'Iterator[Dict[str, str]]'

Expand template strings with variable substitution.

Uses $var or ${var} syntax only.

Args:
    templates: Dict of template strings.
    spec: Expansion specification with variables and mode.

Yields:
    Dicts with same keys as templates, values substituted.

Raises:
    ValueError: If zip mode has mismatched list lengths or expansion exceeds limit.
    KeyError: If a template references an undefined variable.

### substitute_vars(obj: 'Any', var_dict: 'Dict[str, Any]') -> 'Any'

Recursively substitute ${var} in all strings within obj.

Args:
    obj: Any value (string, dict, list, or primitive).
    var_dict: Mapping of variable names to values.

Returns:
    Object with all string values having variables substituted.

---

## ngraph.dsl.loader

YAML loader + schema validation for Scenario DSL.

Provides a single entrypoint to parse a YAML string, normalize keys where
needed, validate against the packaged JSON schema, and return a canonical
dictionary suitable for downstream expansion/parsing.

### load_scenario_yaml(yaml_str: 'str') -> 'Dict[str, Any]'

Load, normalize, and validate a Scenario YAML string.

Returns a canonical dictionary representation that downstream parsers can
consume without worrying about YAML-specific quirks (e.g., boolean-like
keys) and with schema shape already enforced.

---

## ngraph.dsl.selectors.conditions

Condition evaluation for node/entity filtering.

Provides evaluation logic for attribute conditions used in selectors
and failure policies. Supports operators: ==, !=, <, <=, >, >=,
contains, not_contains, in, not_in, exists, not_exists.

Supports dot-notation for nested attribute access (e.g., "hardware.vendor").

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
    (True, "spine")
    >>> resolve_attr_path({"hardware": {"vendor": "Acme"}}, "hardware.vendor")
    (True, "Acme")
    >>> resolve_attr_path({"role": "spine"}, "missing")
    (False, None)

---

## ngraph.dsl.selectors.normalize

Selector parsing and normalization.

Provides the single entry point for converting raw selector values
(strings or dicts) into NodeSelector objects.

### normalize_selector(raw: 'Union[str, Dict[str, Any], NodeSelector]', context: 'str') -> 'NodeSelector'

Normalize a raw selector (string or dict) to a NodeSelector.

This is the single entry point for all selector parsing. All downstream
code works with NodeSelector objects only.

Args:
    raw: Either a regex string, selector dict, or existing NodeSelector.
    context: Usage context ("adjacency", "demand", "override", "workflow").
        Determines the default for active_only.

Returns:
    Normalized NodeSelector instance.

Raises:
    ValueError: If selector format is invalid or context is unknown.

### parse_match_spec(raw: 'Dict[str, Any]', *, default_logic: "Literal['and', 'or']" = 'or', require_conditions: 'bool' = False, context: 'str' = 'match') -> 'MatchSpec'

Parse a match specification from raw dict.

Unified match specification parser for use across adjacency, demands,
membership rules, and failure policies.

Args:
    raw: Dict with 'conditions' list and optional 'logic'.
    default_logic: Default when 'logic' not specified.
    require_conditions: If True, raise when conditions list is empty.
    context: Used in error messages.

Returns:
    Parsed MatchSpec.

Raises:
    ValueError: If validation fails.

---

## ngraph.dsl.selectors.schema

Schema definitions for unified node selection.

Provides dataclasses for node selection configuration used across
network rules, demands, and workflow steps.

### Condition

A single attribute condition for filtering.

Supports dot-notation for nested attribute access (e.g., "hardware.vendor"
resolves to attrs["hardware"]["vendor"]).

Attributes:
    attr: Attribute name to match (supports dot-notation for nested attrs).
    op: Comparison operator.
    value: Right-hand operand (unused for exists/not_exists).

**Attributes:**

- `attr` (str)
- `op` (Literal['==', '!=', '<', '<=', '>', '>=', 'contains', 'not_contains', 'in', 'not_in', 'exists', 'not_exists'])
- `value` (Any)

### MatchSpec

Specification for filtering nodes by attribute conditions.

Attributes:
    conditions: List of conditions to evaluate.
    logic: How to combine conditions ("and" = all, "or" = any).

**Attributes:**

- `conditions` (List[Condition]) = []
- `logic` (Literal['and', 'or']) = or

### NodeSelector

Unified node selection specification.

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

## ngraph.dsl.selectors.select

Node selection and evaluation.

Provides the unified select_nodes() function that handles regex matching,
attribute filtering, active-only filtering, and grouping.

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

### flatten_risk_group_attrs(rg: "Union['RiskGroup', Dict[str, Any]]") -> 'Dict[str, Any]'

Build flat attribute dict for condition evaluation on risk groups.

Merges risk group's top-level fields (name, disabled, children) with
rg.attrs. Top-level fields take precedence on key conflicts.

Supports both RiskGroup objects and dict representations (for flexibility
in failure policy matching).

Args:
    rg: RiskGroup object or dict representation.

Returns:
    Flat dict suitable for condition evaluation.

### match_entity_ids(entity_attrs: 'Dict[str, Dict[str, Any]]', conditions: 'List[Condition]', logic: 'str' = 'or') -> 'Set[str]'

Match entity IDs by attribute conditions.

General primitive for condition-based entity selection. Works with
any entity type as long as attributes are pre-flattened.

Args:
    entity_attrs: Mapping of {entity_id: flattened_attrs_dict}
    conditions: List of conditions to evaluate
    logic: "and" (all must match) or "or" (any must match)

Returns:
    Set of matching entity IDs. Returns all IDs if conditions is empty.

### select_nodes(network: "'Network'", selector: 'NodeSelector', default_active_only: 'bool', excluded_nodes: 'Optional[Set[str]]' = None) -> "Dict[str, List['Node']]"

Unified entry point for node selection.

Evaluation order:

1. Select nodes matching `path` regex (or all nodes if path is None)
2. Filter by `match` conditions
3. Filter by `active_only` flag and excluded_nodes
4. Group by `group_by` attribute (overrides regex capture grouping)

Args:
    network: The network graph.
    selector: Node selection specification.
    default_active_only: Context-aware default for active_only flag.
        Required parameter to prevent silent bugs.
    excluded_nodes: Additional node names to exclude.

Returns:
    Dict mapping group labels to lists of nodes.

---

## ngraph.results.artifacts

Serializable result artifacts for analysis workflows.

This module defines dataclasses that capture outputs from analyses and
simulations in a JSON-serializable form:

- `CapacityEnvelope`: frequency-based capacity distributions and optional

  aggregated flow statistics

- `FailurePatternResult`: capacity results for specific failure patterns

### CapacityEnvelope

Frequency-based capacity envelope that stores capacity values as frequencies.

This approach is memory-efficient for Monte Carlo analysis where we care
about statistical distributions rather than individual sample order.

Attributes:
    source_pattern: Regex pattern used to select source nodes.
    sink_pattern: Regex pattern used to select sink nodes.
    mode: Flow analysis mode ("combine" or "pairwise").
    frequencies: Dictionary mapping capacity values to their occurrence counts.
    min_capacity: Minimum observed capacity.
    max_capacity: Maximum observed capacity.
    mean_capacity: Mean capacity across all samples.
    stdev_capacity: Standard deviation of capacity values.
    total_samples: Total number of samples represented.
    flow_summary_stats: Optional dictionary with aggregated FlowSummary statistics.
                       Contains cost_distribution_stats and other flow analytics.

**Attributes:**

- `source_pattern` (str)
- `sink_pattern` (str)
- `mode` (str)
- `frequencies` (Dict[float, int])
- `min_capacity` (float)
- `max_capacity` (float)
- `mean_capacity` (float)
- `stdev_capacity` (float)
- `total_samples` (int)
- `flow_summary_stats` (Dict[str, Any]) = {}

**Methods:**

- `expand_to_values(self) -> 'List[float]'` - Expand frequency map back to individual values.
- `from_dict(data: 'Dict[str, Any]') -> "'CapacityEnvelope'"` - Construct a CapacityEnvelope from a dictionary.
- `from_values(source_pattern: 'str', sink_pattern: 'str', mode: 'str', values: 'List[float]', flow_summaries: 'List[Any] | None' = None) -> "'CapacityEnvelope'"` - Create envelope from capacity values and optional flow summaries.
- `get_percentile(self, percentile: 'float') -> 'float'` - Calculate percentile from frequency distribution.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

### FailurePatternResult

Result for a unique failure pattern with associated capacity matrix.

Attributes:
    excluded_nodes: List of failed node IDs.
    excluded_links: List of failed link IDs.
    capacity_matrix: Dictionary mapping flow keys to capacity values.
    count: Number of times this pattern occurred.
    is_baseline: Whether this represents the baseline (no failures) case.

**Attributes:**

- `excluded_nodes` (List[str])
- `excluded_links` (List[str])
- `capacity_matrix` (Dict[str, float])
- `count` (int)
- `is_baseline` (bool) = False
- `_pattern_key_cache` (str)

**Methods:**

- `from_dict(data: 'Dict[str, Any]') -> "'FailurePatternResult'"` - Construct FailurePatternResult from a dictionary.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

---

## ngraph.results.flow

Unified flow result containers for failure-analysis iterations.

Defines small, serializable dataclasses that capture per-iteration outcomes
for capacity and demand-placement style analyses in a unit-agnostic form.

Objects expose `to_dict()` that returns JSON-safe primitives. Float-keyed
distributions are normalized to string keys via `_fmt_float_key()`, and
arbitrary `data` payloads are sanitized. These dicts are written under
`data.flow_results` by steps.

Utilities:
    _fmt_float_key: Formats floats as stable string keys for JSON serialization.
        Uses fixed-point notation with trailing zeros stripped for human-readable,
        canonical representations of numeric keys like cost distributions.

### FlowEntry

Represents a single source→destination flow outcome within an iteration.

Fields are unit-agnostic. Callers can interpret numbers as needed for
presentation (e.g., Gbit/s).

Args:
    source: Source identifier.
    destination: Destination identifier.
    priority: Priority/class for traffic placement scenarios. Zero when not applicable.
    demand: Requested volume for this flow.
    placed: Delivered volume for this flow.
    dropped: Unmet volume (``demand - placed``).
    cost_distribution: Optional distribution of placed volume by path cost.
    data: Optional per-flow details (e.g., min-cut edges, used edges).

**Attributes:**

- `source` (str)
- `destination` (str)
- `priority` (int)
- `demand` (float)
- `placed` (float)
- `dropped` (float)
- `cost_distribution` (Dict[float, float]) = {}
- `data` (Dict[str, Any]) = {}

**Methods:**

- `to_dict(self) -> 'Dict[str, Any]'` - Return a JSON-serializable dictionary representation.

### FlowIterationResult

Container for per-iteration analysis results.

Args:
    failure_id: Stable identifier for the failure scenario (hash of excluded
        components, or "" for no exclusions).
    failure_state: Optional excluded components for the iteration.
    failure_trace: Optional trace info (mode_index, selections, expansion) when
        store_failure_patterns=True. None for baseline or when tracing disabled.
    occurrence_count: Number of Monte Carlo iterations that produced this exact
        failure pattern. Used with deduplication to avoid re-running identical
        analyses. Defaults to 1.
    flows: List of flow entries for this iteration.
    summary: Aggregated summary across ``flows``.
    data: Optional per-iteration extras.

**Attributes:**

- `failure_id` (str)
- `failure_state` (Optional[Dict[str, List[str]]])
- `failure_trace` (Optional[Dict[str, Any]])
- `occurrence_count` (int) = 1
- `flows` (List[FlowEntry]) = []
- `summary` (FlowSummary) = FlowSummary(total_demand=0.0, total_placed=0.0, overall_ratio=1.0, dropped_flows=0, num_flows=0)
- `data` (Dict[str, Any]) = {}

**Methods:**

- `to_dict(self) -> 'Dict[str, Any]'` - Return a JSON-serializable dictionary representation.

### FlowSummary

Aggregated metrics across all flows in one iteration.

Args:
    total_demand: Sum of all demands in this iteration.
    total_placed: Sum of all delivered volumes in this iteration.
    overall_ratio: ``total_placed / total_demand`` when demand > 0, else 1.0.
    dropped_flows: Number of flow entries with non-zero drop.
    num_flows: Total number of flows considered.

**Attributes:**

- `total_demand` (float)
- `total_placed` (float)
- `overall_ratio` (float)
- `dropped_flows` (int)
- `num_flows` (int)

**Methods:**

- `to_dict(self) -> 'Dict[str, Any]'` - Return a JSON-serializable dictionary representation.

---

## ngraph.results.snapshot

Scenario snapshot helpers.

Build a concise dictionary snapshot of failure policies and demand sets for
export into results without keeping heavy domain objects.

### build_scenario_snapshot(*, seed: 'int | None', failure_policy_set, demand_set) -> 'Dict[str, Any]'

Build a concise dictionary snapshot of the scenario state.

Creates a serializable representation of the scenario's failure policies
and demand sets, suitable for export into results without keeping heavy
domain objects.

Args:
    seed: Scenario-level seed for reproducibility, or None if unseeded.
    failure_policy_set: FailurePolicySet containing named failure policies.
    demand_set: DemandSet containing named demand collections.

Returns:
    Dict containing: seed, failures (policy snapshots), demands (demand snapshots).

---

## ngraph.results.store

Generic results store for workflow steps and their metadata.

`Results` organizes outputs by workflow step name and records
`WorkflowStepMetadata` for execution context. Storage is strictly
step-scoped: steps must write two keys under their namespace:

- ``metadata``: step-level metadata (dict)
- ``data``: step-specific payload (dict)

Export with :meth:`Results.to_dict`, which returns a JSON-safe structure
with shape ``{workflow, steps, scenario}``. During export, objects with a
``to_dict()`` method are converted, dictionary keys are coerced to strings,
tuples are emitted as lists, and only JSON primitives are produced.

### Results

Step-scoped results container with deterministic export shape.

Structure:

- workflow: step metadata registry
- steps: per-step results with enforced keys {"metadata", "data"}
- scenario: optional scenario snapshot set once at load time

**Attributes:**

- `_store` (Dict) = {}
- `_metadata` (Dict) = {}
- `_active_step` (Optional)
- `_scenario` (Dict) = {}

**Methods:**

- `enter_step(self, step_name: str) -> None` - Enter step scope. Subsequent put/get are scoped to this step.
- `exit_step(self) -> None` - Exit step scope.
- `get(self, key: str, default: Any = None) -> Any` - Get a value from the active step scope.
- `get_all_step_metadata(self) -> Dict[str, ngraph.results.store.WorkflowStepMetadata]` - Get metadata for all workflow steps.
- `get_step(self, step_name: str) -> Dict[str, Any]` - Return the raw dict for a given step name (for cross-step reads).
- `get_step_metadata(self, step_name: str) -> Optional[ngraph.results.store.WorkflowStepMetadata]` - Get metadata for a workflow step.
- `get_steps_by_execution_order(self) -> list[str]` - Get step names ordered by their execution order.
- `put(self, key: str, value: Any) -> None` - Store a value in the active step under an allowed key.
- `put_step_metadata(self, step_name: str, step_type: str, execution_order: int, *, scenario_seed: Optional[int] = None, step_seed: Optional[int] = None, seed_source: str = 'none', active_seed: Optional[int] = None) -> None` - Store metadata for a workflow step.
- `set_scenario_snapshot(self, snapshot: Dict[str, Any]) -> None` - Attach a normalized scenario snapshot for export.
- `to_dict(self) -> Dict[str, Any]` - Return exported results with shape: {workflow, steps, scenario}.

### WorkflowStepMetadata

Metadata for a workflow step execution.

Attributes:
    step_type: The workflow step class name (e.g., 'CapacityEnvelopeAnalysis').
    step_name: The instance name of the step.
    execution_order: Order in which this step was executed (0-based).
    scenario_seed: Scenario-level seed provided in the YAML (if any).
    step_seed: Seed assigned to this step (explicit or scenario-derived).
    seed_source: Source for the step seed. One of:

- "scenario-derived": seed was derived from scenario.seed
- "explicit-step": seed was explicitly provided for the step
- "none": no seed provided/active for this step

    active_seed: The effective base seed used by the step, if any. For steps
        that use Monte Carlo execution, per-iteration seeds are derived from
        active_seed (e.g., active_seed + iteration_index).

**Attributes:**

- `step_type` (str)
- `step_name` (str)
- `execution_order` (int)
- `scenario_seed` (Optional)
- `step_seed` (Optional)
- `seed_source` (str) = none
- `active_seed` (Optional)

---

## ngraph.profiling.profiler

Profiling for NetGraph workflow execution.

Provides CPU and wall-clock timing per workflow step using ``cProfile`` and
optionally peak memory via ``tracemalloc``. Aggregates results into structured
summaries and identifies time-dominant steps (bottlenecks).

### PerformanceProfiler

CPU profiler for NetGraph workflow execution.

Profiles workflow steps using cProfile and identifies bottlenecks.

**Methods:**

- `analyze_performance(self) -> 'None'` - Analyze profiling results and identify bottlenecks.
- `end_scenario(self) -> 'None'` - End profiling for the entire scenario execution.
- `get_top_functions(self, step_name: 'str', limit: 'int' = 10) -> 'List[Tuple[str, float, int]]'` - Get the top CPU-consuming functions for a specific step.
- `merge_child_profiles(self, profile_dir: 'Path', step_name: 'str') -> 'None'` - Merge child worker profiles into the parent step profile.
- `profile_step(self, step_name: 'str', step_type: 'str') -> 'Generator[None, None, None]'` - Context manager for profiling individual workflow steps.
- `save_detailed_profile(self, output_path: 'Path', step_name: 'Optional[str]' = None) -> 'None'` - Save detailed profiling data to a file.
- `start_scenario(self) -> 'None'` - Start profiling for the entire scenario execution.

### PerformanceReporter

Format and render performance profiling results.

Generates plain-text reports with timing analysis, bottleneck identification,
and practical performance tuning suggestions.

**Methods:**

- `generate_report(self) -> 'str'` - Generate performance report.

### ProfileResults

Profiling results for a scenario execution.

Attributes:
    step_profiles: List of individual step performance profiles.
    total_wall_time: Total wall-clock time for entire scenario.
    total_cpu_time: Total CPU time across all steps.
    total_function_calls: Total function calls across all steps.
    bottlenecks: List of performance bottlenecks (>10% execution time).
    analysis_summary: Performance metrics and statistics.

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
    step_type: Type/class name of the workflow step.
    wall_time: Total wall-clock time in seconds.
    cpu_time: CPU time spent in step execution.
    function_calls: Number of function calls during execution.
    memory_peak: Peak memory usage during step in bytes (if available).
    cprofile_stats: Detailed cProfile statistics object.
    worker_profiles_merged: Number of worker profiles merged into this step.

**Attributes:**

- `step_name` (str)
- `step_type` (str)
- `wall_time` (float)
- `cpu_time` (float)
- `function_calls` (int)
- `memory_peak` (Optional[float])
- `cprofile_stats` (Optional[pstats.Stats])
- `worker_profiles_merged` (int) = 0

---

## ngraph.types.base

Base classes and enums for network analysis algorithms.

### EdgeSelect

Edge selection criteria for shortest-path algorithms.

Determines which edges are considered when finding paths between nodes.
These map to NetGraph-Core's EdgeSelection configuration.

### FlowPlacement

Strategies to distribute flow across parallel equal-cost paths.

### Mode

Analysis mode for source/sink group handling.

Determines how multiple source and sink nodes are combined for analysis.

---

## ngraph.types.dto

Types and data structures for algorithm analytics.

Defines immutable summary containers for algorithm outputs.

### EdgeRef

Reference to a directed edge via scenario link_id and direction.

Provides stable, scenario-native edge identification across Core reorderings
using the link's unique ID rather than node name tuples.

Attributes:
    link_id: Scenario link identifier (matches Network.links keys)
    direction: 'fwd' for source→target as defined in Link; 'rev' for reverse

**Attributes:**

- `link_id` (str)
- `direction` (EdgeDir)

### MaxFlowResult

Result of max-flow computation between a source/sink pair.

Captures total flow, cost distribution, and optionally min-cut edges.

Attributes:
    total_flow: Maximum flow value achieved.
    cost_distribution: Mapping of path cost to flow volume placed at that cost.
    min_cut: Saturated edges forming the min-cut (None if not computed).

**Attributes:**

- `total_flow` (float)
- `cost_distribution` (Dict[Cost, float])
- `min_cut` (Tuple[EdgeRef, ...] | None)

---

## ngraph.utils.ids

### new_base64_uuid() -> 'str'

Return a 22-character URL-safe Base64-encoded UUID without padding.

The function generates a random version 4 UUID, encodes the 16 raw bytes
using URL-safe Base64, removes the two trailing padding characters, and
decodes to ASCII. The resulting string length is 22 characters.

Returns:
    A 22-character URL-safe Base64 representation of a UUID4 without
    padding.

---

## ngraph.utils.output_paths

Utilities for building CLI artifact output paths.

This module centralizes logic for composing file and directory paths for
artifacts produced by the NetGraph CLI. Paths are built from an optional
output directory, a prefix (usually derived from the scenario file or
results file), and a per-artifact suffix.

### build_artifact_path(output_dir: 'Optional[Path]', prefix: 'str', suffix: 'str') -> 'Path'

Compose an artifact path as output_dir / (prefix + suffix).

If ``output_dir`` is None, the path is created relative to the current
working directory.

Args:
    output_dir: Base directory for outputs; if None, use CWD.
    prefix: Filename prefix; usually derived from scenario or results stem.
    suffix: Per-artifact suffix including the dot (e.g. ".results.json").

Returns:
    The composed path.

### ensure_parent_dir(path: 'Path') -> 'None'

Ensure the parent directory exists for a file path.

### profiles_dir_for_run(scenario_path: 'Path', output_dir: 'Optional[Path]') -> 'Path'

Return the directory for child worker profiles for ``run --profile``.

Args:
    scenario_path: The scenario YAML path.
    output_dir: Optional base output directory.

Returns:
    Directory path where worker profiles should be stored.

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

Return a safe prefix derived from a scenario file path.

Args:
    scenario_path: The scenario YAML file path.

Returns:
    The scenario filename stem, trimmed of extensions.

---

## ngraph.utils.seed_manager

Deterministic seed derivation to avoid global random.seed() order dependencies.

### SeedManager

Manages deterministic seed derivation for isolated component reproducibility.

Global random.seed() creates order dependencies and component interference.
SeedManager derives unique seeds per component from a master seed using SHA-256,
ensuring reproducible results regardless of execution order or parallelism.

Usage:
    seed_mgr = SeedManager(42)
    failure_seed = seed_mgr.derive_seed("failure_policy", "default")

**Methods:**

- `create_random_state(self, *components: 'Any') -> 'random.Random'` - Create a new Random instance with derived seed.
- `derive_seed(self, *components: 'Any') -> 'Optional[int]'` - Derive a deterministic seed from master seed and component identifiers.
- `seed_global_random(self, *components: 'Any') -> 'None'` - Seed the global random module with derived seed.

---

## ngraph.utils.yaml_utils

Utilities for handling YAML parsing quirks and common operations.

### normalize_yaml_dict_keys(data: Dict[Any, ~V]) -> Dict[str, ~V]

Normalize dictionary keys from YAML parsing to ensure consistent string keys.

YAML 1.1 boolean keys (e.g., true, false, yes, no, on, off) get converted to
Python True/False boolean values. This function converts them to predictable
string representations ("True"/"False") and ensures all keys are strings.

Args:
    data: Dictionary that may contain boolean or other non-string keys from YAML parsing

Returns:
    Dictionary with all keys converted to strings, boolean keys converted to "True"/"False"

Examples:
    >>> normalize_yaml_dict_keys({True: "value1", False: "value2", "normal": "value3"})
    {"True": "value1", "False": "value2", "normal": "value3"}

    >>> # In YAML: true:, yes:, on: all become Python True
    >>> # In YAML: false:, no:, off: all become Python False

---

## ngraph.analysis.context

AnalysisContext: Prepared state for efficient network analysis.

This module provides the primary API for network analysis in NetGraph.
AnalysisContext encapsulates Core graph infrastructure and provides
methods for max-flow, shortest paths, and sensitivity analysis.

Usage:
    # One-off analysis
    from ngraph import analyze
    flow = analyze(network).max_flow("^A$", "^B$")

    # Efficient repeated analysis (bound context)
    ctx = analyze(network, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)

### AnalysisContext

Prepared state for efficient network analysis.

Encapsulates Core graph infrastructure. Supports two usage patterns:

**Unbound** - flexible, specify source/sink per-call:

    ctx = AnalysisContext.from_network(network)
    cost = ctx.shortest_path_cost("A", "B")
    flow = ctx.max_flow("A", "B")  # Builds pseudo-nodes each call

**Bound** - optimized for repeated analysis with same groups:

    ctx = AnalysisContext.from_network(
        network,
        source="^dc/",
        sink="^edge/"
    )
    baseline = ctx.max_flow()  # Uses pre-built pseudo-nodes
    degraded = ctx.max_flow(excluded_links=failed)

Thread Safety:
    Immutable after creation. Safe for concurrent analysis calls
    with different exclusion sets.

Attributes:
    network: Reference to source Network (read-only).
    is_bound: True if source/sink groups are pre-configured.

**Attributes:**

- `_network` ('Network')
- `_handle` (netgraph_core.Graph)
- `_multidigraph` (netgraph_core.StrictMultiDiGraph)
- `_node_mapper` (_NodeMapper)
- `_edge_mapper` (_EdgeMapper)
- `_algorithms` (netgraph_core.Algorithms)
- `_disabled_node_ids` (FrozenSet[int])
- `_disabled_link_ids` (FrozenSet[str])
- `_link_id_to_edge_indices` (Mapping[str, Tuple[int, ...]])
- `_source` (Optional[Union[str, Dict[str, Any]]])
- `_sink` (Optional[Union[str, Dict[str, Any]]])
- `_mode` (Optional[Mode])
- `_pseudo_context` (Optional[_PseudoNodeContext])

**Methods:**

- `from_network(network: "'Network'", *, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, mode: 'Mode' = <Mode.COMBINE: 1>, augmentations: 'Optional[List[AugmentationEdge]]' = None) -> "'AnalysisContext'"` - Create analysis context from network.
- `k_shortest_paths(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.PAIRWISE: 2>, max_k: 'int' = 3, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], List[Path]]'` - Compute up to K shortest paths per group pair.
- `max_flow(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], float]'` - Compute maximum flow between node groups.
- `max_flow_detailed(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None, include_min_cut: 'bool' = False) -> 'Dict[Tuple[str, str], MaxFlowResult]'` - Compute max flow with detailed results including cost distribution.
- `sensitivity(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], Dict[str, float]]'` - Analyze sensitivity of max flow to edge failures.
- `shortest_path_cost(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], float]'` - Compute shortest path costs between node groups.
- `shortest_paths(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, split_parallel_edges: 'bool' = False, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], List[Path]]'` - Compute concrete shortest paths between node groups.

### AugmentationEdge

Edge specification for graph augmentation.

Augmentation edges are added to the graph as-is (unidirectional).
Nodes referenced in augmentations that don't exist in the network
are automatically treated as pseudo/virtual nodes.

Attributes:
    source: Source node name (real or pseudo)
    target: Target node name (real or pseudo)
    capacity: Edge capacity
    cost: Edge cost (converted to int64 for Core)

### analyze(network: "'Network'", *, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, mode: 'Mode' = <Mode.COMBINE: 1>, augmentations: 'Optional[List[AugmentationEdge]]' = None) -> 'AnalysisContext'

Create an analysis context for the network.

This is THE primary entry point for network analysis in NetGraph.

Args:
    network: Network topology to analyze.
    source: Optional source node selector (string path or selector dict).
            If provided with sink, creates bound context with pre-built
            pseudo-nodes for efficient repeated flow analysis.
    sink: Optional sink node selector (string path or selector dict).
    mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
    augmentations: Optional custom augmentation edges.

Returns:
    AnalysisContext ready for analysis calls.

Examples:
    One-off analysis (unbound context):

        flow = analyze(network).max_flow("^A$", "^B$")
        paths = analyze(network).shortest_paths("^A$", "^B$")

    Efficient repeated analysis (bound context):

        ctx = analyze(network, source="^dc/", sink="^edge/")
        baseline = ctx.max_flow()
        degraded = ctx.max_flow(excluded_links=failed_links)

    Multiple exclusion scenarios:

        ctx = analyze(network, source="^A$", sink="^B$")
        for scenario in failure_scenarios:
            result = ctx.max_flow(excluded_links=scenario)

### build_edge_mask(ctx: 'AnalysisContext', excluded_links: 'Optional[Set[str]]' = None) -> 'np.ndarray'

Build an edge mask array for Core algorithms.

Uses O(|excluded| + |disabled|) time complexity.
Core semantics: True = include, False = exclude.

Args:
    ctx: AnalysisContext with pre-computed edge index mapping.
    excluded_links: Optional set of link IDs to exclude.

Returns:
    Boolean numpy array of shape (num_edges,) where True means included.

### build_node_mask(ctx: 'AnalysisContext', excluded_nodes: 'Optional[Set[str]]' = None) -> 'np.ndarray'

Build a node mask array for Core algorithms.

Uses O(|excluded| + |disabled|) time complexity.
Core semantics: True = include, False = exclude.

Args:
    ctx: AnalysisContext with pre-computed disabled node IDs.
    excluded_nodes: Optional set of node names to exclude.

Returns:
    Boolean numpy array of shape (num_nodes,) where True means included.

---

## ngraph.analysis.demand

Demand expansion: converts TrafficDemand specs into concrete placement demands.

Supports both pairwise and combine modes through augmentation-based pseudo nodes.
Uses unified selectors for node selection.

### DemandExpansion

Demand expansion result.

Attributes:
    demands: Concrete demands ready for placement (sorted by priority).
    augmentations: Augmentation edges for pseudo nodes (empty for pairwise).

**Attributes:**

- `demands` (List[ExpandedDemand])
- `augmentations` (List[AugmentationEdge])

### ExpandedDemand

Concrete demand ready for placement.

Uses node names (not IDs) so expansion happens before graph building.
Node IDs are resolved after the graph is built with pseudo nodes.

Attributes:
    src_name: Source node name (real or pseudo).
    dst_name: Destination node name (real or pseudo).
    volume: Traffic volume to place.
    priority: Priority class (lower is higher priority).
    policy_preset: FlowPolicy configuration preset.
    demand_id: Parent TrafficDemand ID for tracking.

**Attributes:**

- `src_name` (str)
- `dst_name` (str)
- `volume` (float)
- `priority` (int)
- `policy_preset` (FlowPolicyPreset)
- `demand_id` (str)

### expand_demands(network: 'Network', traffic_demands: 'List[TrafficDemand]', default_policy_preset: 'FlowPolicyPreset' = <FlowPolicyPreset.SHORTEST_PATHS_ECMP: 1>) -> 'DemandExpansion'

Expand TrafficDemand specifications into concrete demands with augmentations.

Pure function that:

1. Normalizes and evaluates selectors to get node groups
2. Distributes volume based on mode (combine/pairwise) and group_mode
3. Generates augmentation edges for combine mode (pseudo nodes)
4. Returns demands (node names) + augmentations

Node names are used (not IDs) so expansion happens BEFORE graph building.
IDs are resolved after graph is built with augmentations.

Note: Variable expansion (expand: block) is handled during YAML parsing in
build_demand_set(), so TrafficDemand objects here are already expanded.

Args:
    network: Network for node selection.
    traffic_demands: High-level demand specifications.
    default_policy_preset: Default policy if demand doesn't specify one.

Returns:
    DemandExpansion with demands and augmentations.

Raises:
    ValueError: If no demands could be expanded or unsupported mode.

---

## ngraph.analysis.failure_manager

FailureManager for Monte Carlo failure analysis.

Provides the failure analysis engine for NetGraph. Supports parallel
processing, graph caching, and failure policy handling for workflow steps
and direct programmatic use.

Performance characteristics:
Time complexity: O(S + I * A / P), where S is one-time graph setup cost,
I is iteration count, A is per-iteration analysis cost, and P is parallelism.
Graph caching amortizes expensive graph construction across all iterations,
and O(|excluded|) mask building replaces O(V+E) iteration.

Space complexity: O(V + E + I * R), where V and E are node and link counts,
and R is result size per iteration. The pre-built graph is shared across
all iterations.

Parallelism: The C++ Core backend releases the GIL during computation,
enabling true parallelism with Python threads. With graph caching, most
per-iteration work runs in GIL-free C++ code; speedup depends on workload
and parallelism level.

### AnalysisFunction

Protocol for analysis functions used with FailureManager.

Analysis functions take a Network, exclusion sets, and analysis-specific
parameters, returning results of any type.

### FailureManager

Failure analysis engine with Monte Carlo capabilities.

This is the component for failure analysis in NetGraph.
Provides parallel processing, worker caching, and failure
policy handling for workflow steps and direct notebook usage.

The FailureManager can execute any analysis function that takes a Network
with exclusion sets and returns results, making it generic for different
types of failure analysis (capacity, traffic, connectivity, etc.).

Attributes:
    network: The underlying network (not modified during analysis).
    failure_policy_set: Set of named failure policies.
    policy_name: Name of specific failure policy to use.

**Methods:**

- `compute_exclusions(self, policy: "'FailurePolicy | None'" = None, seed_offset: 'int | None' = None, failure_trace: 'Optional[Dict[str, Any]]' = None) -> 'tuple[set[str], set[str]]'` - Compute set of nodes and links to exclude for a failure iteration.
- `get_failure_policy(self) -> "'FailurePolicy | None'"` - Get failure policy for analysis.
- `run_demand_placement_monte_carlo(self, demands_config: 'list[dict[str, Any]] | Any', iterations: 'int' = 100, parallelism: 'int' = 1, placement_rounds: 'int | str' = 'auto', seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_details: 'bool' = False, include_used_edges: 'bool' = False) -> 'Any'` - Analyze traffic demand placement success under failures.
- `run_max_flow_monte_carlo(self, source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_summary: 'bool' = False, include_min_cut: 'bool' = False) -> 'Any'` - Analyze maximum flow capacity envelopes between node groups under failures.
- `run_monte_carlo_analysis(self, analysis_func: 'AnalysisFunction', iterations: 'int' = 1, parallelism: 'int' = 1, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **analysis_kwargs) -> 'dict[str, Any]'` - Run Monte Carlo failure analysis with any analysis function.
- `run_sensitivity_monte_carlo(self, source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, seed: 'int | None' = None, store_failure_patterns: 'bool' = False) -> 'dict[str, Any]'` - Analyze component criticality for flow capacity under failures.
- `run_single_failure_scenario(self, analysis_func: 'AnalysisFunction', **kwargs) -> 'Any'` - Run a single failure scenario for convenience.

---

## ngraph.analysis.functions

Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager. Each analysis function
takes a Network, exclusion sets, and analysis-specific parameters, returning
results of type FlowIterationResult.

Parameters should ideally be hashable for efficient caching in FailureManager;
non-hashable objects are identified by memory address for cache key generation.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph once and using O(|excluded|) masks for exclusions.

SPF caching enables efficient demand placement by computing shortest paths once
per unique source node rather than once per demand. For networks with many demands
sharing the same sources, this can reduce SPF computations by an order of magnitude.

### build_demand_context(network: "'Network'", demands_config: 'list[dict[str, Any]]') -> 'AnalysisContext'

Build an AnalysisContext for repeated demand placement analysis.

Pre-computes the graph with augmentations (pseudo source/target nodes) for
efficient repeated analysis with different exclusion sets.

Args:
    network: Network instance.
    demands_config: List of demand configurations (same format as demand_placement_analysis).

Returns:
    AnalysisContext ready for use with demand_placement_analysis.

### build_maxflow_context(network: "'Network'", source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine') -> 'AnalysisContext'

Build an AnalysisContext for repeated max-flow analysis.

Pre-computes the graph with pseudo source/target nodes for all source/target
pairs, enabling O(|excluded|) mask building per iteration.

Args:
    network: Network instance.
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    mode: Flow analysis mode ("combine" or "pairwise").

Returns:
    AnalysisContext ready for use with max_flow_analysis or sensitivity_analysis.

### demand_placement_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', demands_config: 'list[dict[str, Any]]', placement_rounds: 'int | str' = 'auto', include_flow_details: 'bool' = False, include_used_edges: 'bool' = False, context: 'Optional[AnalysisContext]' = None) -> 'FlowIterationResult'

Analyze traffic demand placement success rates using Core directly.

This function:

1. Builds Core infrastructure (graph, algorithms, flow_graph) or uses cached
2. Expands demands into concrete (src, dst, volume) tuples
3. Places each demand using SPF caching for cacheable policies
4. Uses FlowPolicy for complex multi-flow policies
5. Aggregates results into FlowIterationResult

SPF Caching Optimization:
    For cacheable policies (ECMP, WCMP, TE_WCMP_UNLIM), SPF results are
    cached by source node. This reduces SPF computations from O(demands)
    to O(unique_sources), typically a 5-10x reduction for workloads with
    many demands sharing the same sources.

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    demands_config: List of demand configurations (serializable dicts).
    placement_rounds: Number of placement optimization rounds (unused - Core handles internally).
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    context: Pre-built AnalysisContext for fast repeated analysis.

Returns:
    FlowIterationResult describing this iteration.

### max_flow_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, include_flow_details: 'bool' = False, include_min_cut: 'bool' = False, context: 'Optional[AnalysisContext]' = None) -> 'FlowIterationResult'

Analyze maximum flow capacity between node groups.

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: Whether to use shortest paths only.
    require_capacity: If True (default), path selection considers available
        capacity. If False, path selection is cost-only (true IP/IGP semantics).
    flow_placement: Flow placement strategy.
    include_flow_details: Whether to collect cost distribution and similar details.
    include_min_cut: Whether to include min-cut edge list in entry data.
    context: Pre-built AnalysisContext for efficient repeated analysis.

Returns:
    FlowIterationResult describing this iteration.

### sensitivity_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, context: 'Optional[AnalysisContext]' = None) -> 'FlowIterationResult'

Analyze component sensitivity to failures.

Identifies critical edges (saturated edges) and computes the flow reduction
caused by removing each one. Returns a FlowIterationResult where each
FlowEntry represents a source/target pair with:

- demand/placed = max flow value (the capacity being analyzed)
- dropped = 0.0 (baseline analysis, no failures applied)
- data["sensitivity"] = {link_id:direction: flow_reduction} for critical edges

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: If True, use single-tier shortest-path flow (IP/IGP mode).
        Reports only edges used under ECMP routing. If False (default), use
        full iterative max-flow (SDN/TE mode) and report all saturated edges.
    flow_placement: Flow placement strategy.
    context: Pre-built AnalysisContext for efficient repeated analysis.

Returns:
    FlowIterationResult with sensitivity data in each FlowEntry.data.

---

## ngraph.analysis.placement

Core demand placement with SPF caching.

### PlacementEntry

Single demand placement result.

**Attributes:**

- `src_name` (str)
- `dst_name` (str)
- `priority` (int)
- `volume` (float)
- `placed` (float)
- `cost_distribution` (dict[float, float]) = {}
- `used_edges` (set[str]) = set()

### PlacementResult

Complete placement result.

**Attributes:**

- `summary` (PlacementSummary)
- `entries` (list[PlacementEntry] | None)

### PlacementSummary

Aggregated placement totals.

**Attributes:**

- `total_demand` (float)
- `total_placed` (float)

### place_demands(demands: "Sequence['ExpandedDemand']", volumes: 'Sequence[float]', flow_graph: 'netgraph_core.FlowGraph', ctx: "'AnalysisContext'", node_mask: 'np.ndarray', edge_mask: 'np.ndarray', *, resolved_ids: 'Sequence[tuple[int, int]] | None' = None, collect_entries: 'bool' = False, include_cost_distribution: 'bool' = False, include_used_edges: 'bool' = False) -> 'PlacementResult'

Place demands on a flow graph with SPF caching.

Args:
    demands: Expanded demands (policy_preset, priority, names).
    volumes: Demand volumes (allows scaling without modifying demands).
    flow_graph: Target FlowGraph.
    ctx: AnalysisContext with graph infrastructure.
    node_mask: Node inclusion mask.
    edge_mask: Edge inclusion mask.
    resolved_ids: Pre-resolved (src_id, dst_id) pairs. Computed if None.
    collect_entries: If True, populate result.entries.
    include_cost_distribution: Include cost distribution in entries.
    include_used_edges: Include used edges in entries.

Returns:
    PlacementResult with summary and optional entries.

---

## ngraph.lib.nx

NetworkX graph conversion utilities.

This module provides functions to convert between NetworkX graphs and the
internal graph representation used by ngraph for high-performance algorithms.

Example:
    >>> import networkx as nx
    >>> from ngraph.lib.nx import from_networkx, to_networkx
    >>>
    >>> # Create a NetworkX graph
    >>> G = nx.DiGraph()
    >>> G.add_edge("A", "B", capacity=100.0, cost=10)
    >>> G.add_edge("B", "C", capacity=50.0, cost=5)
    >>>
    >>> # Convert to ngraph format for analysis
    >>> graph, node_map, edge_map = from_networkx(G)
    >>>
    >>> # Use with ngraph algorithms...
    >>>
    >>> # Convert back to NetworkX
    >>> G_out = to_networkx(graph, node_map)

### EdgeMap

Bidirectional mapping between internal edge IDs and original edge references.

When converting a NetworkX graph, each edge is assigned an internal integer ID
(ext_edge_id). This class preserves the mapping for interpreting algorithm
results and updating the original graph.

Attributes:
    to_ref: Maps internal edge ID to original (source, target, key) tuple
    from_ref: Maps original (source, target, key) to list of internal edge IDs
        (list because bidirectional=True creates two IDs per edge)

Example:
    >>> graph, node_map, edge_map = from_networkx(G)
    >>> # After running algorithms, map flow results back to original edges
    >>> for ext_id, flow in enumerate(flow_state.edge_flow_view()):
    ...     if flow > 0:
    ...         u, v, key = edge_map.to_ref[ext_id]
    ...         G.edges[u, v, key]["flow"] = flow

**Attributes:**

- `to_ref` (Dict[int, NxEdgeTuple]) = {}
- `from_ref` (Dict[NxEdgeTuple, List[int]]) = {}

### NodeMap

Bidirectional mapping between node names and integer indices.

When converting a NetworkX graph to the internal representation, node names
(which can be any hashable type) are mapped to contiguous integer indices
starting from 0. This class preserves the mapping for result interpretation
and back-conversion.

Attributes:
    to_index: Maps original node names to integer indices
    to_name: Maps integer indices back to original node names

Example:
    >>> node_map = NodeMap.from_names(["A", "B", "C"])
    >>> node_map.to_index["A"]
    0
    >>> node_map.to_name[1]
    'B'

**Attributes:**

- `to_index` (Dict[Hashable, int]) = {}
- `to_name` (Dict[int, Hashable]) = {}

**Methods:**

- `from_names(names: 'List[Hashable]') -> "'NodeMap'"` - Create a NodeMap from a list of node names.

### from_networkx(G: 'NxGraph', *, capacity_attr: 'str' = 'capacity', cost_attr: 'str' = 'cost', default_capacity: 'float' = 1.0, default_cost: 'int' = 1, bidirectional: 'bool' = False) -> 'Tuple[netgraph_core.StrictMultiDiGraph, NodeMap, EdgeMap]'

Convert a NetworkX graph to ngraph's internal graph format.

Converts any NetworkX graph (DiGraph, MultiDiGraph, Graph, MultiGraph) to
netgraph_core.StrictMultiDiGraph. Node names are mapped to integer indices;
the returned NodeMap and EdgeMap preserve mappings for result interpretation.

Args:
    G: NetworkX graph (DiGraph, MultiDiGraph, Graph, or MultiGraph)
    capacity_attr: Edge attribute name for capacity (default: "capacity")
    cost_attr: Edge attribute name for cost (default: "cost")
    default_capacity: Capacity value when attribute is missing (default: 1.0)
    default_cost: Cost value when attribute is missing (default: 1)
    bidirectional: If True, add reverse edge for each edge. Useful for
        undirected connectivity analysis. (default: False)

Returns:
    Tuple of (graph, node_map, edge_map) where:

- graph: netgraph_core.StrictMultiDiGraph ready for algorithms
- node_map: NodeMap for converting node indices back to names
- edge_map: EdgeMap for converting edge IDs back to (u, v, key) refs

Raises:
    TypeError: If G is not a NetworkX graph
    ValueError: If graph has no nodes

Example:
    >>> import networkx as nx
    >>> G = nx.DiGraph()
    >>> G.add_edge("src", "dst", capacity=100.0, cost=10)
    >>> graph, node_map, edge_map = from_networkx(G)
    >>> graph.num_nodes()
    2
    >>> node_map.to_index["src"]
    0
    >>> edge_map.to_ref[0]  # First edge
    ('dst', 'src', 0)  # sorted node order: dst < src

### to_networkx(graph: 'netgraph_core.StrictMultiDiGraph', node_map: 'Optional[NodeMap]' = None, *, capacity_attr: 'str' = 'capacity', cost_attr: 'str' = 'cost') -> "'nx.MultiDiGraph'"

Convert ngraph's internal graph format back to NetworkX MultiDiGraph.

Reconstructs a NetworkX graph from the internal representation. If a
NodeMap is provided, original node names are restored; otherwise, nodes
are labeled with integer indices.

Args:
    graph: netgraph_core.StrictMultiDiGraph to convert
    node_map: Optional NodeMap to restore original node names.
        If None, nodes are labeled 0, 1, 2, ...
    capacity_attr: Edge attribute name for capacity (default: "capacity")
    cost_attr: Edge attribute name for cost (default: "cost")

Returns:
    nx.MultiDiGraph with edges and attributes from the internal graph

Example:
    >>> graph, node_map, edge_map = from_networkx(G)
    >>> # ... run algorithms ...
    >>> G_out = to_networkx(graph, node_map)
    >>> list(G_out.nodes())
    ['A', 'B', 'C']

---


## Error Handling

NetGraph uses standard Python exceptions:

- `ValueError` - For validation errors
- `KeyError` - For missing required fields
- `RuntimeError` - For runtime errors

For complete method signatures and detailed documentation, use Python's help system:

```python
help(ngraph.scenario.Scenario)
help(ngraph.network.Network.max_flow)
```

---

*This documentation was auto-generated from the NetGraph source code.*
