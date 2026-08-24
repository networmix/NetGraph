<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: August 24, 2026 at 00:43 UTC

Modules auto-discovered: 54

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

Hierarchical exploration of a Network.

Builds a tree of the node-name hierarchy and aggregates per-subtree
statistics — node and link counts, capacity, capex/power, and hardware
bills of materials — in two modes: all nodes, and enabled nodes only.

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
    reason: Brief reason tag.

**Attributes:**

- `source` (str)
- `target` (str)
- `capacity` (float)
- `limit` (float)
- `reason` (str)

### NetworkExplorer

Hierarchical view of a Network with per-subtree statistics.

Statistics are computed in two modes: 'all' (ignores disabled) and
'active' (only enabled).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None, strict_validation: 'bool' = True) -> 'NetworkExplorer'` - Build a NetworkExplorer, constructing a tree plus 'all' and 'active' stats.
- `get_bom(self, include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return aggregated hardware BOM for the whole network.
- `get_bom_by_path(self, path: 'str', include_disabled: 'bool' = True) -> 'Dict[str, float]'` - Return the hardware BOM for a specific hierarchy path.
- `get_bom_map(self, include_disabled: 'bool' = True, include_root: 'bool' = True, root_label: 'str' = '') -> 'Dict[str, Dict[str, float]]'` - Return a mapping from hierarchy path to BOM for each subtree.
- `get_link_issues(self) -> 'List[LinkCapacityIssue]'` - Return recorded link capacity issues discovered in non-strict mode.
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
- `stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={})
- `active_stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_capex=0.0, total_power=0.0, bom={})
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

---

## ngraph.logging

Centralized logging configuration for NetGraph.

Follows the standard library pattern: importing the package attaches only a
``logging.NullHandler`` to the root ``ngraph`` logger and never installs
stream handlers or sets levels. Applications opt into console output by
calling ``setup_root_logger()`` explicitly, or implicitly via
``set_global_log_level()``. The CLI does both in ``main()``: it calls
``setup_root_logger()`` first, then sets the level from
``--verbose``/``--quiet``.

### disable_debug_logging() -> None

Disable debug logging, set to INFO level.

### enable_debug_logging() -> None

Enable debug logging for the entire package.

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

### reset_logging() -> None

Reset logging configuration (mainly for testing).

### set_global_log_level(level: int) -> None

Set the log level for all NetGraph loggers.

Installs the default console handler via setup_root_logger() if logging
has not been configured yet. Intended for applications (e.g. the CLI);
library code never calls this implicitly.

Args:
    level: Logging level (e.g., logging.DEBUG, logging.INFO).

### setup_root_logger(level: int = 20, format_string: str | None = None, handler: logging.Handler | None = None) -> None

Set up the root NetGraph logger with a single handler.

Subsequent calls are no-ops until ``reset_logging()`` is called.

Args:
    level: Logging level (default: INFO).
    format_string: Custom format string (optional).
    handler: Custom handler (optional, defaults to StreamHandler(sys.stderr)).

---

## ngraph.scenario

Scenario class for defining network analysis workflows from YAML.

### Scenario

A complete scenario for building and executing network workflows.

Holds:

- A network (nodes/links), constructed via blueprint expansion.
- A failure policy set (one or more named failure policies).
- A demand set containing one or more named demand collections.
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

- `from_yaml(yaml_str: 'str', default_components: 'Optional[ComponentsLibrary]' = None) -> 'Scenario'` - Construct a Scenario from a YAML string, merging in a default
- `run(self, step_hook: 'Optional[Callable[[WorkflowStep], ContextManager[None]]]' = None) -> 'None'` - Execute the scenario's workflow steps in order.

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
- `total_capacity(self) -> 'float'` - Computes capacity for this component and all descendants.
- `total_capex(self) -> 'float'` - Computes total capex including children, multiplied by count.
- `total_power(self) -> 'float'` - Computes *typical* power for this component and all descendants.
- `total_power_max(self) -> 'float'` - Computes *peak* power for this component and all descendants.

### ComponentsLibrary

Holds a collection of named Components. Each entry is a top-level "template"
that can be referenced for cost/power/capacity lookups, possibly with nested children.

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

- `clone(self) -> 'ComponentsLibrary'` - Creates a deep copy of this ComponentsLibrary.
- `from_dict(data: 'Dict[str, Any]') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from raw component definitions.
- `from_yaml(yaml_str: 'str') -> 'ComponentsLibrary'` - Constructs a ComponentsLibrary from a YAML string. If the YAML contains
- `get(self, name: 'str') -> 'Optional[Component]'` - Retrieves a Component by its name from the library.
- `merge(self, other: 'ComponentsLibrary', override: 'bool' = True) -> 'ComponentsLibrary'` - Merges another ComponentsLibrary into this one.

### resolve_link_end_components(attrs: 'Dict[str, Any]', library: 'ComponentsLibrary') -> 'tuple[tuple[Optional[Component], float, bool], tuple[Optional[Component], float, bool], bool]'

Resolve per-end hardware components for a link.

Input format inside ``link.attrs`` is a structured mapping under the
``hardware`` key only:
  ``{"hardware": {"source": {"component": NAME, "count": N},
                   "target": {"component": NAME, "count": N}}}``
An optional ``exclusive: true`` per end indicates unsharable usage; for
exclusive ends, validation and BOM counting round counts up to integers.

Args:
    attrs: Link attributes mapping.
    library: Components library for lookups.

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

### coerce_flow_policy(value: 'Any') -> 'Optional[FlowPolicyPreset]'

Return a FlowPolicyPreset from various user-friendly forms.

Accepts:

- None: returns None
- FlowPolicyPreset: returned as-is
- int: mapped by value (e.g., 1 -> SHORTEST_PATHS_ECMP); bools are

    rejected (True/False are not presets 1/0)

- str: name of enum (case-insensitive); numeric strings are allowed

Raises:
    ValueError: If the value is not one of the accepted forms (including
        bool and dict/object configs, which are not supported).

---

## ngraph.model.demand.matrix

Demand set containers.

`DemandSet` holds named `TrafficDemand` lists as input to demand expansion and
placement. These are input containers, not analysis results.

### DemandSet

Named collection of TrafficDemand lists.

Attributes:
    sets: Dictionary mapping set names to TrafficDemand lists.

**Attributes:**

- `sets` (dict[str, list[TrafficDemand]]) = {}

**Methods:**

- `add(self, name: 'str', demands: 'list[TrafficDemand]') -> 'None'` - Add a demand list, replacing any set already stored under `name`.
- `get_all_demands(self) -> 'list[TrafficDemand]'` - Get all traffic demands from all sets combined.
- `get_default_set(self) -> 'list[TrafficDemand]'` - Get default demand set.
- `get_set(self, name: 'str') -> 'list[TrafficDemand]'` - Get a specific demand set by name.

---

## ngraph.model.demand.spec

Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. Routing behavior is selected via an optional `FlowPolicyPreset`,
or pinned to explicit routes with `StaticPath`.

### StaticPath

One explicit route a demand can be pinned to (an MPLS-style LSP).

Give exactly one of `nodes` or `links`:

- `nodes`: the node names the route visits, source first and target last.

  Each consecutive pair must be adjacent. When several parallel links
  connect a pair, the cheapest is used (ties broken by link id); name the
  link explicitly to choose a different one.

- `links`: the link ids the route traverses, in order. Unambiguous when

  parallel links exist. A link may be traversed in either direction.

Attributes:
    nodes: Node names along the route, or empty when `links` is given.
    links: Link ids along the route, or empty when `nodes` is given.

**Attributes:**

- `nodes` (Tuple) = ()
- `links` (Tuple) = ()

### TrafficDemand

Traffic demand specification using unified selectors.

Attributes:
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    volume: Total demand volume.
    priority: Priority class (lower = higher priority).
    mode: Node pairing mode ("combine" or "pairwise").
    group_mode: How grouped nodes produce demands
        ("flatten", "per_group", "group_pairwise").
    flow_policy: Policy preset for routing.
    static_paths: Explicit routes to pin this demand to. When set, the
        demand is placed only on these routes: one flow per route, and a
        route broken by a failure carries nothing rather than rerouting.
        Requires selectors matching exactly one source and one target.
    attrs: Arbitrary user metadata.
    id: Unique identifier. Auto-generated if empty.

**Attributes:**

- `source` (Union)
- `target` (Union)
- `volume` (float) = 0.0
- `priority` (int) = 0
- `mode` (str) = combine
- `group_mode` (str) = flatten
- `flow_policy` (Union)
- `static_paths` (Tuple) = ()
- `attrs` (Dict) = {}
- `id` (str)

**Methods:**

- `to_dict(self) -> Dict[str, Any]` - Return the canonical serialized form (results output, snapshots).

---

## ngraph.model.failure.generate

Dynamic risk group generation from entity attributes.

Creates one risk group per unique value of a chosen node or link attribute.

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

Raises:
    ValueError: If `group_by` resolves to an unhashable value, or if the
        name template renders the same group name for two distinct values.

Note:
    Modifies entity risk_groups sets in place.

### parse_generate_spec(raw: 'Dict[str, Any]') -> 'GenerateSpec'

Parse raw generate dict into a GenerateSpec.

Args:
    raw: Raw generate dict from YAML.

Returns:
    Parsed GenerateSpec.

Raises:
    ValueError: If 'scope' is missing or is neither 'node' nor 'link', if
        'group_by' or 'name' is missing, or if 'name' omits the '${value}'
        placeholder.

---

## ngraph.model.failure.membership

Risk group membership rule resolution.

Resolves policy-based membership rules that auto-assign entities (nodes,
links, risk groups) to risk groups based on attribute conditions.

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
    Modifies entities in place. Call after all risk groups are registered
    but before validation.

---

## ngraph.model.failure.parser

Parsers for FailurePolicySet and related failure modeling structures.

### build_failure_policy(fp_data: 'Dict[str, Any]', *, policy_name: 'str', derive_seed: 'Callable[[str], Optional[int]]') -> 'FailurePolicy'

Build a FailurePolicy from a raw configuration dictionary.

Args:
    fp_data: Policy definition dict with keys: modes (required), attrs,
        expand_groups. Each mode contains weight and rules.
    policy_name: Name identifier for this policy (used for seed derivation).
    derive_seed: Callable to derive deterministic seeds from component names.

Returns:
    FailurePolicy: Configured policy with parsed modes and rules.

Raises:
    ValueError: If modes is empty or malformed, if rules are invalid, or
        if no mode has positive weight.

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

---

## ngraph.model.failure.policy

Failure policy primitives.

Defines `FailureRule` and `FailurePolicy` for expressing how nodes, links,
and risk groups fail in analyses. Conditions match on top-level attributes
with simple operators; rules select matches using "all", probabilistic
"random" (with `probability`), or fixed-size "choice" (with `count`).
Policies can optionally expand failures by shared risk groups. Failed risk
groups always cascade to their children downstream (the hierarchy is
inherent), so no policy flag controls that behavior.

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

The main entry point is `apply_failures_typed`, which:
  1) Builds a single RNG for the entire call (from `seed` or `self.seed`).
  2) Selects a mode based on weights (one RNG draw).
  3) Gathers the relevant entities for each rule in that mode.
  4) Matches them against the rule conditions using 'and' or 'or' logic.
  5) Applies the selection strategy (all, random, or choice), drawing
     from the same RNG, which keeps rules statistically independent.
  6) Collects the union of all failed entities across all rules.
  7) Optionally expands failures by shared-risk groups.

Attributes:
    attrs: Arbitrary metadata about this policy.
    expand_groups: If True, expand failures among entities sharing
        risk groups with failed entities.
    seed: Default seed for reproducible random operations. Overridden
        by the ``seed`` parameter on ``apply_failures_typed`` when
        provided.
    modes: List of weighted failure modes.

**Attributes:**

- `attrs` (Dict[str, Any]) = {}
- `expand_groups` (bool) = False
- `seed` (Optional[int])
- `modes` (List[FailureMode]) = []

**Methods:**

- `apply_failures(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None, *, seed: 'Optional[int]' = None, failure_trace: 'Optional[Dict[str, Any]]' = None, prepared_matches: 'Optional[Dict[int, tuple[str, ...]]]' = None, prepared_weights: 'Optional[Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]]' = None, prepared_rg_index: 'Optional[Dict[str, Set[str]]]' = None, prepared_rg_members: 'Optional[Dict[str, Tuple[frozenset, frozenset]]]' = None) -> 'List[str]'` - Identify which entities fail for this iteration.
- `apply_failures_typed(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None, *, seed: 'Optional[int]' = None, failure_trace: 'Optional[Dict[str, Any]]' = None, prepared_matches: 'Optional[Dict[int, tuple[str, ...]]]' = None, prepared_weights: 'Optional[Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]]' = None, prepared_rg_index: 'Optional[Dict[str, Set[str]]]' = None, prepared_rg_members: 'Optional[Dict[str, Tuple[frozenset, frozenset]]]' = None) -> 'Tuple[Set[str], Set[str], Set[str]]'` - Identify which entities fail for this iteration, typed by scope.
- `build_risk_group_index(network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]') -> 'Dict[str, Set[str]]'` - Build a risk-group -> entity-ID index for risk-group expansion.
- `prepare_matches(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None) -> 'Dict[int, tuple[str, ...]]'` - Prepare stable ordered candidate pools for all rules in this policy.
- `prepare_weights(self, prepared_matches: 'Dict[int, tuple[str, ...]]', network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None) -> 'Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]'` - Precompute per-rule weight splits for weighted-choice rules.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

### FailureRule

Defines how to match and then select entities for failure.

Attributes:
    scope: The type of entities this rule applies to: "node", "link",
        or "risk_group".
    conditions: A list of conditions to filter matching entities.
    logic: "and" (all must be true) or "or" (any must be true, default).
    mode: The selection strategy among the matched set:

- "random": each matched entity fails independently with

          `probability`.

- "choice": pick exactly `count` items (random sample).
- "all": select every matched entity.

    probability: Probability in [0,1], used if mode="random".
    count: Number of entities to pick if mode="choice".
    weight_by: Optional attribute for weighted sampling in choice mode.
    path: Optional regex pattern applied after condition matching. For
        node and risk_group scope it is matched against the entity ID;
        for link scope it is matched against the "source|target" key,
        not the link ID.

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

Attributes:
    policies: Dictionary mapping failure policy names to FailurePolicy objects.

**Attributes:**

- `policies` (dict[str, FailurePolicy]) = {}

**Methods:**

- `add(self, name: 'str', policy: 'FailurePolicy') -> 'None'` - Add a policy, replacing any policy already stored under `name`.
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

Cycles arise when membership rules with scope='risk_group' create mutual
parent-child relationships. Detection is a DFS over the children hierarchy.

Args:
    network: Network with risk_groups populated (after membership resolution).

Raises:
    ValueError: If a cycle is detected, with details about the cycle path.

### validate_risk_group_references(network: "'Network'") -> 'None'

Ensure every risk group named by a node or link is defined.

Names are checked against network.risk_groups; typos and missing
definitions would otherwise cause silent failures in simulations.

Args:
    network: Network with nodes, links, and risk_groups populated.

Raises:
    ValueError: If any node or link references an undefined risk group.
        The error message lists up to 10 violations with entity names
        and the undefined group names.

---

## ngraph.model.flow.policy_config

Flow policy preset configurations for NetGraph.

Named routing presets and the factory that materializes them as NetGraph-Core
FlowPolicy objects built from a FlowPolicyConfig.

### FlowPolicyPreset

Enumerates common flow policy presets for traffic routing.

These presets map to specific combinations of path algorithms, flow placement
strategies, and edge selection modes provided by NetGraph-Core.

### create_flow_policy(algorithms: 'netgraph_core.Algorithms', graph: 'netgraph_core.Graph', preset: 'FlowPolicyPreset', node_mask=None, edge_mask=None, static_path_count: 'Optional[int]' = None) -> 'netgraph_core.FlowPolicy'

Create a FlowPolicy instance from a preset configuration.

Args:
    algorithms: NetGraph-Core Algorithms instance.
    graph: NetGraph-Core Graph handle.
    preset: Preset whose path algorithm, placement, edge selection, and
        flow-count bounds to apply.
    node_mask: Optional numpy bool array for node exclusions (True = include).
    edge_mask: Optional numpy bool array for edge exclusions (True = include).
    static_path_count: Number of routes the caller will pin with
        `FlowPolicy.set_static_paths`. Sets the flow count to match, since
        a pinned policy creates one flow per route and never grows.

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

Args:
    cfg: FlowPolicyPreset enum, an integer coercible to one, or any other
        value.

Returns:
    Preset name (e.g. "SHORTEST_PATHS_ECMP"); None when ``cfg`` is None.
    Values that do not map to a preset are logged at debug level and
    returned as ``str(cfg)``.

---

## ngraph.model.network

Network topology modeling with Node, Link, RiskGroup, and Network classes.

These classes carry no analysis machinery and can be used on their own.

### Link

Represents one directed link between two nodes.

The model stores a single direction (``source`` -> ``target``). When the
analysis graph is built (via ``AnalysisContext`` / netgraph-core), a reverse
edge is added automatically for each link to provide bidirectional
connectivity.

Attributes:
    source (str): Name of the source node.
    target (str): Name of the target node.
    capacity (float): Link capacity (default 1.0).
    cost (float): Link cost (default 1.0).
    disabled (bool): Whether the link is disabled.
    risk_groups (Set[str]): Set of risk group names this link belongs to.
    attrs (Dict[str, Any]): Additional metadata (e.g., distance).
    id (str): Unique identifier. ``Network.add_link`` assigns the
        deterministic form "{source}|{target}|<seq>", where <seq> is a
        per-(source, target) insertion sequence number; links never added
        to a Network keep a provisional uuid-suffixed id.

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

``Path`` stores a sequence of (node, parallel edges) elements plus a numeric
cost. Paths sort by cost, compare by structure and cost, and support sub-path
extraction, which leaves the cost for the caller to recompute.

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

### parse_match_spec(raw: 'Dict[str, Any]', *, default_logic: "Literal['and', 'or']" = 'or', require_conditions: 'bool' = False, context: 'str' = 'match') -> 'MatchSpec'

Parse a match specification from raw dict.

Shared by adjacency, demands, membership rules, and failure policies.

Args:
    raw: Dict with 'conditions' list and optional 'logic'. Both keys are
        optional; a missing 'conditions' yields an empty condition list.
    default_logic: Used when 'logic' is absent.
    require_conditions: If True, raise when conditions list is empty.
    context: Name of the enclosing construct, quoted in error messages.

Returns:
    Parsed MatchSpec.

Raises:
    ValueError: If 'logic' is not 'and'/'or', 'conditions' is not a list,
        a condition is not a dict or lacks 'attr'/'op', 'in'/'not_in' is
        given a non-list value, or conditions are required but empty.

---

## ngraph.model.selectors.schema

Schema definitions for unified node selection.

Dataclasses shared by network rules, demands, and workflow steps.

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
- `op` (ConditionOp)
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

### select_nodes(network: "'Network'", selector: 'NodeSelector', default_active_only: 'bool') -> "Dict[str, List['Node']]"

Unified entry point for node selection.

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

Base classes for workflow automation.

Defines the workflow step abstraction, registration decorator, and execution
lifecycle. Steps implement `run()` and are executed via `execute()` which
handles timing, logging, and metadata recording. Failures are logged and
re-raised.

### WorkflowStep

Base class for all workflow steps.

Every step is logged with execution timing, supports seeding for
reproducible random operations, and has its metadata stored in
scenario.results for analysis.

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
        used for logging and result storage. When empty, the class name
        is used instead.
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

Validate and resolve a parallelism setting to a concrete worker count.

Args:
    parallelism: Either a positive integer worker count or "auto" for
        the CPU count.

Returns:
    Positive integer worker count (minimum 1).

Raises:
    ValueError: If parallelism is a string other than "auto", or an
        integer < 1.

### serialize_monte_carlo_results(raw: 'Dict[str, Any]') -> 'tuple[Any, list[dict]]'

Convert FailureManager Monte Carlo output into JSON-safe dicts.

Args:
    raw: Dict with optional "baseline" entry and "results" list, whose
        items expose to_dict() (e.g. FlowIterationResult) or are already
        plain dicts.

Returns:
    Tuple of (baseline_dict, flow_results): the baseline iteration (or
    None) and the failure iterations, converted via to_dict() when
    available.

### validate_unique_step_names(workflow: "'list[WorkflowStep]'") -> 'None'

Validate that effective step names in a workflow list are unique.

Effective names follow the same rule used for results storage:
``step.name`` or the step class name when no name is set. Duplicate
effective names would silently overwrite each other's namespace in the
results store.

Args:
    workflow: Workflow step list.

Raises:
    ValueError: If two or more steps share the same effective name.

---

## ngraph.workflow.build_graph

Graph building workflow component.

Validates the network topology and exports it as a NetworkX node-link
representation for inspection. Graph building for analysis happens in the
analysis functions, not here.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: BuildGraph

        name: "build_network_graph"  # Optional: Custom name for this step
        add_reverse: true  # Optional: Add reverse edges (default: true)
    ```

With `add_reverse: true` (the default), each Link(A→B) gets both a forward
(A→B) and a reverse (B→A) edge for bidirectional connectivity. Set it to
`false` for directed-only graphs.

Results stored in `scenario.results` under the step name as two keys:

- metadata: Step-level execution metadata (node/link counts)
- data: { graph: node-link JSON dict, context: { add_reverse: bool } }

### BuildGraph

Validates network topology and stores node-link representation.

The stored representation is JSON-serializable NetworkX node-link data.
Core graph building for analysis happens in analysis functions as needed.

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

Aggregates capex and power from the network hardware inventory, with no
normalization or reporting. Contributions are split into two categories:

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
    aggregation_level: Inclusive depth for aggregation; 0 = root only.
        Must be >= 0.

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

Baseline (no failures) always runs first as a separate reference; `iterations`
counts failure scenarios only.

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

Baseline (no failures) always runs first and is returned in a separate field.
The flow_results list holds unique failure patterns (deduplicated); each result
carries an occurrence_count of how many iterations matched that pattern.

Attributes:
    source: Source node selector (string path or selector dict).
    target: Target node selector (string path or selector dict).
    mode: Flow analysis mode ("combine" or "pairwise").
    failure_policy: Name of failure policy in scenario.failure_policy_set.
        If None, no failure policy is applied.
    iterations: Number of failure iterations to run; must be >= 0.
    parallelism: Worker thread count, or "auto" for the CPU count.
    shortest_path: Restrict flow to lowest-cost paths (IP/IGP mode).
    require_capacity: If True (default), path selection considers capacity.
        If False, path selection is cost-only (true IP/IGP semantics).
    flow_placement: Flow placement strategy.
    seed: Optional seed for reproducible results.
    store_failure_patterns: Record the failure trace on each result.
        Iterations are deduplicated, so a trace describes the first
        iteration of its pattern, not every matching iteration.
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

Binary search yields alpha_star: the largest multiplier at which every
demand in the set still places fully on the network.

Attributes:
    demand_set: Name of the demand set to analyze.
    acceptance_rule: Currently only "hard" is implemented; anything else
        raises ValueError at run time.
    alpha_start: Starting multiplier for binary search.
    growth_factor: Factor for bracket expansion; must be > 1.0.
    alpha_min: Minimum allowed alpha value.
    alpha_max: Maximum allowed alpha value.
    resolution: Convergence threshold for binary search; must be positive.
    max_bracket_iters: Maximum iterations for bracketing phase.
    max_bisect_iters: Maximum iterations for bisection phase.
    placement_rounds: Deprecated; accepted for backward compatibility but
        has no effect (placement optimization is handled by the core engine).

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
- `placement_rounds` (int | str) = auto

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Any'") -> 'None'` - Execute the workflow step logic.

---

## ngraph.workflow.network_stats

Workflow step for basic node and link statistics.

Computes and stores network statistics including node/link counts,
capacity distributions, cost distributions, and degree distributions. Excluded
entities are filtered out without modifying the base network; disabled nodes
and links are excluded too unless `include_disabled` is set.

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

Baseline (no failures) always runs first as a separate reference; `iterations`
counts failure scenarios only.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: TrafficMatrixPlacement

        name: "tm_analysis"
        demand_set: "default"
        failure_policy: "single_link"    # Optional: failure policy name
        iterations: 100                  # Number of failure scenarios
        parallelism: 4                   # Worker threads (or "auto")
        alpha: 1.0                       # Demand volume multiplier
        include_flow_details: true       # Include cost distribution per flow
    ```

### TrafficMatrixPlacement

Monte Carlo demand placement using a named demand set.

Baseline (no failures) always runs first and is returned in a separate field.
The flow_results list holds unique failure patterns (deduplicated); each result
carries an occurrence_count of how many iterations matched that pattern.

Attributes:
    demand_set: Name of the demand set to analyze. Required; an empty
        value raises ValueError.
    failure_policy: Failure policy name in scenario.failure_policy_set.
        If None, no failure policy is applied.
    iterations: Number of failure iterations to run; must be >= 0.
    parallelism: Worker thread count, or "auto" for the CPU count.
    placement_rounds: Deprecated; accepted for backward compatibility but
        has no effect (placement optimization is handled by the core engine).
    seed: Optional seed for reproducibility.
    store_failure_patterns: Record the failure trace on each result.
        Iterations are deduplicated, so a trace describes the first
        iteration of its pattern, not every matching iteration.
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    alpha: Numeric scale for demands in the set; must be > 0.0. Ignored
        when alpha_from_step is set.
    alpha_from_step: Optional producer step name to read alpha from; it
        must run before this step.
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

Pure parsing/validation helpers, kept separate from the expansion module so
they can be tested independently and reused.

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

Takes a list, set, or tuple of risk group names (possibly containing
bracket expressions) and returns a set of all expanded names.

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

Recursively substitute ${var} in all strings within obj.

A string consisting of exactly one placeholder (e.g. "${t}") is replaced
by the variable's native value, preserving its type. This keeps match
condition values comparable to non-string attributes (e.g. int tiers).
Placeholders embedded in longer strings (e.g. "dc${dc}_internal") are
interpolated as text, so the result is a string.

Args:
    obj: Any value (string, dict, list, or primitive).
    var_dict: Mapping of variable names to values.

Returns:
    Object with variables substituted: whole-placeholder strings replaced
    by the variable's native value, other strings interpolated as text.

Raises:
    KeyError: If a placeholder names a variable absent from var_dict.

---

## ngraph.dsl.loader

YAML loader + schema validation for Scenario DSL.

A single entrypoint parses a YAML string, normalizes keys where needed,
validates against the packaged JSON schema, and returns a canonical
dictionary suitable for downstream expansion/parsing.

### load_scenario_yaml(yaml_str: 'str') -> 'Dict[str, Any]'

Load, normalize, and validate a Scenario YAML string.

Returns a canonical dictionary representation that downstream parsers can
consume without worrying about YAML-specific quirks (e.g., boolean-like
keys) and with schema shape already enforced.

---

## ngraph.dsl.selectors.normalize

Selector parsing and normalization.

Single entry point for converting raw selector values (strings or dicts)
into NodeSelector objects.

### normalize_selector(raw: 'Union[str, Dict[str, Any], NodeSelector]', context: 'str') -> 'NodeSelector'

Normalize a raw selector (string or dict) to a NodeSelector.

All downstream code works with NodeSelector objects only.

Args:
    raw: Either a regex string, selector dict, or existing NodeSelector.
    context: Usage context ("adjacency", "demand", "override", "workflow").
        Determines the default for active_only.

Returns:
    Normalized NodeSelector instance.

Raises:
    ValueError: If selector format is invalid or context is unknown.

---

## ngraph.results.artifacts

Serializable result artifacts for analysis workflows.

`CapacityEnvelope` captures a frequency-based capacity distribution, plus
optional aggregated flow statistics, in JSON-serializable form.

### CapacityEnvelope

Capacity distribution stored as a value -> occurrence-count map.

Monte Carlo runs repeat the same capacity values many times, so counting
them keeps memory proportional to the number of distinct values. Individual
sample order is not preserved.

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
    _fmt_float_key: Formats floats as stable string keys for JSON serialization,
        in fixed-point notation with trailing zeros stripped.

### FlowEntry

One source→destination flow outcome within an iteration.

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
- `_active_step` (Union)
- `_scenario` (Dict) = {}

**Methods:**

- `enter_step(self, step_name: str) -> None` - Enter step scope. Subsequent put/get are scoped to this step.
- `exit_step(self) -> None` - Exit step scope.
- `get(self, key: str, default: Any = None) -> Any` - Get a value from the active step scope.
- `get_all_step_metadata(self) -> Dict[str, ngraph.results.store.WorkflowStepMetadata]` - Get metadata for all workflow steps.
- `get_step(self, step_name: str) -> Dict[str, Any]` - Return the raw dict for a given step name (for cross-step reads).
- `get_step_metadata(self, step_name: str) -> ngraph.results.store.WorkflowStepMetadata | None` - Get metadata for a workflow step.
- `get_steps_by_execution_order(self) -> list[str]` - Get step names ordered by their execution order.
- `put(self, key: str, value: Any) -> None` - Store a value in the active step under an allowed key.
- `put_step_metadata(self, step_name: str, step_type: str, execution_order: int, *, scenario_seed: int | None = None, step_seed: int | None = None, seed_source: str = 'none', active_seed: int | None = None) -> None` - Store metadata for a workflow step.
- `set_scenario_snapshot(self, snapshot: Dict[str, Any]) -> None` - Attach a normalized scenario snapshot for export.
- `to_dict(self) -> Dict[str, Any]` - Return exported results with shape: {workflow, steps, scenario}.

### WorkflowStepMetadata

Metadata for a workflow step execution.

Attributes:
    step_type: The workflow step class name (e.g., 'NetworkStats').
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
- `scenario_seed` (Union)
- `step_seed` (Union)
- `seed_source` (str) = none
- `active_seed` (Union)

---

## ngraph.profiling.profiler

Profiling for NetGraph workflow execution.

Provides CPU and wall-clock timing per workflow step using ``cProfile`` and
optionally peak memory via ``tracemalloc``. Aggregates results into structured
summaries and identifies time-dominant steps (bottlenecks).

### PerformanceProfiler

CPU profiler for NetGraph workflow execution.

Profiles each workflow step with cProfile and flags steps that take more
than 10% of total wall time as bottlenecks.

**Methods:**

- `analyze_performance(self) -> 'None'` - Analyze profiling results and identify bottlenecks.
- `end_scenario(self) -> 'None'` - End profiling for the entire scenario execution.
- `get_top_functions(self, step_name: 'str', limit: 'int' = 10) -> 'List[Tuple[str, float, int]]'` - Get the top CPU-consuming functions for a specific step.
- `merge_child_profiles(self, profile_dir: 'Path', step_name: 'str') -> 'None'` - Merge child worker profiles into the parent step profile.
- `profile_step(self, step_name: 'str', step_type: 'str') -> 'Generator[None, None, None]'` - Context manager for profiling individual workflow steps.
- `save_detailed_profile(self, output_path: 'Path', step_name: 'Optional[str]' = None) -> 'None'` - Save detailed profiling data to a file.
- `start_scenario(self) -> 'None'` - Start profiling for the entire scenario execution.

### PerformanceReporter

Render profiling results as a plain-text report.

Covers per-step timing, bottleneck identification, and tuning suggestions.

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

Identifying an edge by the link's unique ID rather than by a node-name
tuple keeps the reference valid across Core edge reorderings.

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
    min_cut: Edges forming a minimum cut (None if not computed).

**Attributes:**

- `total_flow` (float)
- `cost_distribution` (Dict[Cost, float])
- `min_cut` (Tuple[EdgeRef, ...] | None)

---

## ngraph.utils.ids

### new_base64_uuid() -> 'str'

Return a 22-character URL-safe Base64-encoded UUID without padding.

The 16 raw bytes of a random version 4 UUID are encoded with URL-safe
Base64; the two trailing padding characters are dropped, leaving 22 ASCII
characters.

Returns:
    A 22-character URL-safe Base64 representation of a UUID4, unpadded.

---

## ngraph.utils.output_paths

Utilities for building CLI artifact output paths.

Every artifact path the NetGraph CLI writes is composed here, from an optional
output directory, a prefix (usually derived from the scenario file or results
file), and a per-artifact suffix.

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

- `derive_seed(self, *components: 'Any') -> 'Optional[int]'` - Derive a deterministic seed from master seed and component identifiers.

---

## ngraph.utils.yaml_utils

Utilities for handling YAML parsing quirks and common operations.

### normalize_yaml_dict_keys(data: Dict[Any, ~V]) -> Dict[str, ~V]

Normalize dictionary keys from YAML parsing to ensure consistent string keys.

YAML 1.1 parses true/false/yes/no/on/off keys as Python booleans. Those
become "True"/"False"; every other key is coerced with str().

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

AnalysisContext: prepared graph state for repeated network analysis.

AnalysisContext holds the Core graph infrastructure and exposes max-flow,
shortest-path, and sensitivity analysis over it.

Usage:
    # One-off analysis
    from ngraph import analyze
    flow = analyze(network).max_flow("^A$", "^B$")

    # Repeated analysis over one prepared graph (bound context)
    ctx = analyze(network, source="^A$", sink="^B$")
    baseline = ctx.max_flow()
    degraded = ctx.max_flow(excluded_links=failed_links)

### AnalysisContext

Prepared graph state for repeated network analysis.

Wraps the Core graph infrastructure. Two usage patterns:

**Unbound** - source/sink given per call:

    ctx = AnalysisContext.from_network(network)
    cost = ctx.shortest_path_cost("A", "B")
    flow = ctx.max_flow("A", "B")

Every flow call on an unbound context builds a full temporary bound
context, which rebuilds the graph from scratch; bind the context instead
for repeated flow analysis.

**Bound** - source/sink fixed at construction, reused across calls:

    ctx = AnalysisContext.from_network(
        network,
        source="^dc/",
        sink="^edge/"
    )
    baseline = ctx.max_flow()  # Uses pre-built pseudo-nodes
    degraded = ctx.max_flow(excluded_links=failed)

Selectors, here and in every method taking one, are either a regex path
string or a dict with ``path``/``group_by``/``match``.

Thread Safety:
    Immutable after creation. Safe for concurrent analysis calls
    with different exclusion sets.

Attributes:
    network: Reference to source Network (read-only).
    is_bound: True if source/sink groups are pre-configured.

**Attributes:**

- `_network` ('Network')
- `_core` (Optional[_GraphBuildResult])
- `_source` (Optional[Union[str, Dict[str, Any]]])
- `_sink` (Optional[Union[str, Dict[str, Any]]])
- `_mode` (Optional[Mode])
- `_pseudo_context` (Optional[_PseudoNodeContext])
- `_augmentations` (Tuple[AugmentationEdge, ...]) = ()
- `_core_lock` (threading.Lock)

**Methods:**

- `build_edge_mask(self, excluded_links: 'Optional[Set[str]]' = None) -> 'np.ndarray'` - Build an edge inclusion mask for Core algorithms.
- `build_node_mask(self, excluded_nodes: 'Optional[Set[str]]' = None) -> 'np.ndarray'` - Build a node inclusion mask for Core algorithms.
- `from_network(network: "'Network'", *, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, mode: 'Mode' = <Mode.COMBINE: 1>, augmentations: 'Optional[List[AugmentationEdge]]' = None) -> "'AnalysisContext'"` - Create analysis context from network.
- `k_shortest_paths(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.PAIRWISE: 2>, max_k: 'int' = 3, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], List[Path]]'` - Compute up to K shortest paths per group pair.
- `max_flow(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], float]'` - Compute maximum flow between node groups.
- `max_flow_detailed(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None, include_min_cut: 'bool' = False) -> 'Dict[Tuple[str, str], MaxFlowResult]'` - Compute max flow with detailed results including cost distribution.
- `sensitivity(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], Dict[str, float]]'` - Analyze sensitivity of max flow to edge failures.
- `sensitivity_with_flow(self, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, *, mode: 'Mode' = <Mode.COMBINE: 1>, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], Tuple[float, Dict[str, float]]]'` - Compute max flow and edge sensitivity together per group pair.
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
    cost: Edge cost (must be an integer value; Core uses int64 costs)

### analyze(network: "'Network'", *, source: 'Optional[Union[str, Dict[str, Any]]]' = None, sink: 'Optional[Union[str, Dict[str, Any]]]' = None, mode: 'Mode' = <Mode.COMBINE: 1>, augmentations: 'Optional[List[AugmentationEdge]]' = None) -> 'AnalysisContext'

Create an analysis context for the network.

Primary entry point for network analysis in NetGraph.

Args:
    network: Network topology to analyze.
    source: Optional source node selector (string path or selector dict).
            If provided with sink, creates a bound context whose pseudo
            nodes are pre-built once and reused by every flow call.
    sink: Optional sink node selector (string path or selector dict).
    mode: Group mode (COMBINE or PAIRWISE). Only used if bound.
    augmentations: Optional custom augmentation edges.

Returns:
    AnalysisContext ready for analysis calls.

Raises:
    ValueError: If only one of source/sink is provided, or if a bound
        selector matches no nodes.
    ValueError: If any link capacity is at or above LARGE_CAPACITY (1e15,
        the internal pseudo-edge capacity), since such a link would be
        silently clamped by the pseudo attachment edges in combine-mode
        flows.
    ValueError: If any link or augmentation cost is negative or
        non-integer, or if the total of all edge costs reaches 2**62.
        Core's int64 cost arithmetic would overflow and silently corrupt
        SPF and flow results.

Note:
    The capacity and cost checks run during the graph build, which happens
    here for bound contexts and for contexts with custom augmentations,
    and on first use otherwise.

Examples:
    One-off analysis (unbound context):

        flow = analyze(network).max_flow("^A$", "^B$")
        paths = analyze(network).shortest_paths("^A$", "^B$")

    Repeated analysis over one prepared graph (bound context):

        ctx = analyze(network, source="^dc/", sink="^edge/")
        baseline = ctx.max_flow()
        degraded = ctx.max_flow(excluded_links=failed_links)

    Multiple exclusion scenarios:

        ctx = analyze(network, source="^A$", sink="^B$")
        for scenario in failure_scenarios:
            result = ctx.max_flow(excluded_links=scenario)

---

## ngraph.analysis.demand

Demand expansion: converts TrafficDemand specs into concrete placement demands.

Combine mode aggregates each side behind augmentation-based pseudo nodes;
pairwise mode emits one demand per (source, target) pair. Endpoints are
resolved through the shared selector layer.

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
    static_paths: Routes this demand is pinned to, empty when it is
        routed by the policy.

**Attributes:**

- `src_name` (str)
- `dst_name` (str)
- `volume` (float)
- `priority` (int)
- `policy_preset` (FlowPolicyPreset)
- `static_paths` (Tuple[StaticPath, ...]) = ()

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
    ValueError: If no demands could be expanded, if two demands share an
        id (pseudo node names embed the id, so duplicates would merge
        distinct demands' attachment edges into one endpoint), or if a
        demand with `static_paths` does not resolve to exactly one
        source/target pair.

---

## ngraph.analysis.failure_manager

FailureManager for Monte Carlo failure analysis.

Runs an analysis function over many failure scenarios, handling failure policy
application, graph caching, and parallel execution. Used by workflow steps and
directly from user code.

Performance characteristics:
Time complexity: O(S + I * A / P), where S is one-time graph setup cost,
I is iteration count, A is per-iteration analysis cost, and P is parallelism.
Graph caching amortizes graph construction across all iterations: each
iteration applies its exclusions as an O(|excluded|) mask update instead of
rebuilding the graph or re-scanning all O(V+E) nodes and edges.

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

Run an analysis function across Monte Carlo failure scenarios.

Applies a failure policy, deduplicates identical failure patterns, and
runs iterations in parallel. Used by workflow steps and directly from user code.

Executes any analysis function that takes a Network plus exclusion sets and
returns results, so the same engine covers capacity, traffic, connectivity,
and custom analyses.

Attributes:
    network: The underlying network (not modified during analysis).
    failure_policy_set: Set of named failure policies.
    policy_name: Name of specific failure policy to use.

**Methods:**

- `compute_exclusions(self, policy: "'FailurePolicy | None'" = None, seed_offset: 'int | None' = None, failure_trace: 'Optional[Dict[str, Any]]' = None) -> 'tuple[set[str], set[str]]'` - Compute set of nodes and links to exclude for a failure iteration.
- `get_failure_policy(self) -> "'FailurePolicy | None'"` - Get failure policy for analysis.
- `run_demand_placement_monte_carlo(self, demands_config: 'list[dict[str, Any]] | Any', iterations: 'int' = 100, parallelism: 'int' = 1, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_details: 'bool' = False, include_used_edges: 'bool' = False) -> 'Any'` - Analyze traffic demand placement success under failures.
- `run_max_flow_monte_carlo(self, source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, require_capacity: 'bool' = True, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_summary: 'bool' = False, include_min_cut: 'bool' = False) -> 'Any'` - Compute max-flow capacity envelopes between node groups under failures.
- `run_monte_carlo_analysis(self, analysis_func: 'AnalysisFunction', iterations: 'int' = 1, parallelism: 'int' = 1, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **analysis_kwargs) -> 'dict[str, Any]'` - Run Monte Carlo failure analysis with any analysis function.
- `run_sensitivity_monte_carlo(self, source: 'str | dict[str, Any]', target: 'str | dict[str, Any]', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, seed: 'int | None' = None, store_failure_patterns: 'bool' = False) -> 'dict[str, Any]'` - Analyze component criticality for flow capacity under failures.
- `run_single_failure_scenario(self, analysis_func: 'AnalysisFunction', **kwargs) -> 'Any'` - Run one failure iteration, for quick analysis or debugging.

---

## ngraph.analysis.functions

Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager. Each analysis function
takes a Network, exclusion sets, and analysis-specific parameters, returning
results of type FlowIterationResult.

Parameters should ideally be hashable so FailureManager can deduplicate
identical failure patterns before dispatch; non-hashable objects are keyed
by memory address.

Graph caching builds the graph once and applies each exclusion set as an
O(|excluded|) mask instead of rebuilding.

SPF caching computes shortest paths once per unique source node rather than
once per demand. For networks with many demands sharing the same sources, this
can reduce SPF computations by an order of magnitude.

### build_demand_placement_inputs(network: "'Network'", demands_config: 'list[dict[str, Any]]') -> 'tuple[AnalysisContext, DemandExpansion, list[tuple[int, int]]]'

Build context, expansion, and resolved node IDs for demand placement.

Reconstructs and expands demands once so repeated calls to
demand_placement_analysis (e.g., Monte Carlo iterations) can skip the
per-iteration expansion and node-ID resolution work. Building the
expansion and context together guarantees that pseudo node names
(derived from demand ids) match the context's graph.

Args:
    network: Network instance.
    demands_config: List of demand configurations (same format as
        demand_placement_analysis).

Returns:
    Tuple of (context, expansion, resolved_ids) where resolved_ids holds
    (src_id, dst_id) pairs aligned with expansion.demands.

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

### demand_placement_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', demands_config: 'list[dict[str, Any]]', include_flow_details: 'bool' = False, include_used_edges: 'bool' = False, context: 'Optional[AnalysisContext]' = None, expansion: 'Optional[DemandExpansion]' = None, resolved_ids: 'Optional[Sequence[tuple[int, int]]]' = None) -> 'FlowIterationResult'

Analyze traffic demand placement success rates using Core directly.

Steps:

1. Build Core infrastructure (graph, algorithms, flow_graph), or reuse the

   pre-built ``context``

2. Expand demands into concrete (src, dst, volume) tuples (or use a

   pre-computed expansion)

3. Place each demand using SPF caching for cacheable policies.

   SHORTEST_PATHS_* presets admit flow onto the cost-only shortest paths
   of the base topology and drop overflow (IGP semantics); TE_* presets
   reroute remaining volume onto residual-capacity paths.

4. Fall back to FlowPolicy for presets outside CACHEABLE_PRESETS
5. Aggregate results into FlowIterationResult

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
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    context: Pre-built AnalysisContext, reused across calls. Must be built
        from this same demands_config - pseudo node names embed demand
        ids, so a context built from a different config raises ValueError
        during endpoint resolution. See build_demand_placement_inputs.
    expansion: Pre-computed DemandExpansion matching demands_config. When
        provided, per-call demand reconstruction and expansion are skipped.
        Must be built together with ``context`` (pseudo node names embed
        demand ids) - see build_demand_placement_inputs.
    resolved_ids: Pre-resolved (src_id, dst_id) pairs aligned with
        expansion.demands. Only valid together with ``context``.

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
    shortest_path: If True, use single-tier shortest-path flow (IP/IGP
        mode) instead of full iterative max-flow.
    require_capacity: If True (default), path selection considers available
        capacity. If False, path selection is cost-only (true IP/IGP semantics).
    flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP).
    include_flow_details: Whether to collect cost distribution and similar details.
    include_min_cut: Whether to include min-cut edge list in entry data.
    context: Pre-built AnalysisContext reused across calls. Must be
        unbound or bound to these same source/target/mode arguments.

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
    flow_placement: PROPORTIONAL (WCMP) or EQUAL_BALANCED (ECMP).
    context: Pre-built AnalysisContext reused across calls. Must be
        unbound or bound to these same source/target/mode arguments.

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

Result of one `place_demands` call.

Attributes:
    summary: Aggregated demand and placed totals.
    entries: Per-demand results, or None unless the call passed
        ``collect_entries=True``.

**Attributes:**

- `summary` (PlacementSummary)
- `entries` (list[PlacementEntry] | None)

### PlacementSummary

Aggregated placement totals.

**Attributes:**

- `total_demand` (float)
- `total_placed` (float)

### place_demands(demands: "Sequence['ExpandedDemand']", volumes: 'Sequence[float]', flow_graph: 'netgraph_core.FlowGraph', ctx: "'AnalysisContext'", node_mask: 'np.ndarray', edge_mask: 'np.ndarray', *, resolved_ids: 'Sequence[tuple[int, int]] | None' = None, collect_entries: 'bool' = False, include_cost_distribution: 'bool' = False, include_used_edges: 'bool' = False, dag_cache: 'dict[tuple[int, bool], tuple[np.ndarray, Any]] | None' = None) -> 'PlacementResult'

Place demands on a flow graph with SPF caching.

Args:
    demands: Expanded demands (policy_preset, priority, names).
    volumes: Volume per demand, positionally aligned with `demands`;
        passed separately so callers can scale without rebuilding demands.
    flow_graph: Target FlowGraph; placed flow accumulates here.
    ctx: AnalysisContext holding the built graph and Core algorithms.
    node_mask: Node inclusion mask (True = include), as built by
        ctx.build_node_mask.
    edge_mask: Edge inclusion mask (True = include), as built by
        ctx.build_edge_mask.
    resolved_ids: Pre-resolved (src_id, dst_id) pairs. Computed from the
        demand names if None.
    collect_entries: If True, populate result.entries.
    include_cost_distribution: Include cost distribution in entries.
    include_used_edges: Include used edges in entries.
    dag_cache: Optional persistent SPF DAG cache keyed by
        (src_id, uses_capacity_aware_selection). Base DAGs depend only on
        the static graph and masks, so repeated calls with the same
        context and masks (e.g. MSD probes) can share one cache.

Returns:
    PlacementResult with summary and optional entries.

Raises:
    ValueError: If a demand endpoint is not present in ``ctx``'s graph
        (checked only when ``resolved_ids`` is not supplied). Pseudo node
        names embed demand ids, so this usually means the context was
        built from a different demands_config.
    ValueError: If two policy-based demands (presets outside
        CACHEABLE_PRESETS) share the same (src, dst, priority): their
        FlowIndex values would collide and silently merge in FlowGraph.
    ValueError: If ``demands``, ``volumes``, and ``resolved_ids`` are not
        all the same length.

---

## ngraph.analysis.static_paths

Resolution of explicit routes into Core path bundles.

Turns the `StaticPath` entries on a demand into the `PredDAG` bundles that
`FlowPolicy.set_static_paths` pins traffic to. A bundle is a single simple
path: one edge per hop, so a route that names adjacent nodes with parallel
links between them picks one of those links (see `StaticPath`).

### build_static_path_bundles(ctx: "'AnalysisContext'", paths: 'Sequence[StaticPath]', src_name: 'str', dst_name: 'str') -> 'List[netgraph_core.PredDAG]'

Build the Core path bundles a demand is pinned to.

Args:
    ctx: Context holding the built graph; routes resolve against it.
    paths: Routes to pin, in the order flows should be created.
    src_name: Node every route must start at.
    dst_name: Node every route must end at.

Returns:
    One `PredDAG` per route, in the given order. Results are cached per
    context, so repeated calls during a Monte Carlo run resolve once.

Raises:
    ValueError: If an endpoint is absent from the context graph, if a
        route names an unknown node or a disabled/unknown link, has a hop
        whose nodes are joined only by disabled links, has a hop with
        no link, traverses a link that does not leave the node it has
        reached, does not run from `src_name` to `dst_name`, or revisits
        a node (a pinned route must be a simple path).

---

## ngraph.lib.nx

NetworkX graph conversion utilities.

Convert between NetworkX graphs and the internal graph representation that
ngraph's algorithms run on.

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
    >>> # edge_flow_view() is indexed by internal Core edge index, so
    >>> # translate through ext_edge_ids_view() before using to_ref.
    >>> ext_edge_ids = graph.ext_edge_ids_view()
    >>> for edge_idx, flow in enumerate(flow_state.edge_flow_view()):
    ...     if flow > 0:
    ...         u, v, key = edge_map.to_ref[int(ext_edge_ids[edge_idx])]
    ...         G.edges[u, v, key]["flow"] = flow  # G.edges[u, v] for a DiGraph

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

### from_networkx(G: 'NxGraph', *, capacity_attr: 'str' = 'capacity', cost_attr: 'str' = 'cost', default_capacity: 'float' = 1.0, default_cost: 'int' = 1, bidirectional: 'Optional[bool]' = None) -> 'Tuple[netgraph_core.StrictMultiDiGraph, NodeMap, EdgeMap]'

Convert a NetworkX graph to ngraph's internal graph format.

Converts any NetworkX graph (DiGraph, MultiDiGraph, Graph, MultiGraph) to
netgraph_core.StrictMultiDiGraph. Node names are mapped to integer indices;
the returned NodeMap and EdgeMap preserve mappings for result interpretation.

Args:
    G: NetworkX graph (DiGraph, MultiDiGraph, Graph, or MultiGraph)
    capacity_attr: Edge attribute name for capacity (default: "capacity")
    cost_attr: Edge attribute name for cost (default: "cost"). Cost values
        must be integers (netgraph_core requires int64 costs); fractional
        values raise ValueError.
    default_capacity: Capacity value when attribute is missing (default: 1.0)
    default_cost: Cost value when attribute is missing (default: 1).
        Must be an integer value.
    bidirectional: If True, add a reverse edge for each edge. If None
        (default), inferred from the graph type: directed inputs get one
        arc per edge, undirected inputs get antiparallel arc pairs (the
        standard undirected-to-directed reduction for max-flow and
        reachability). Pass an explicit True or False to override.

Returns:
    Tuple of (graph, node_map, edge_map) where:

- graph: netgraph_core.StrictMultiDiGraph ready for algorithms
- node_map: NodeMap for converting node indices back to names
- edge_map: EdgeMap for converting edge IDs back to (u, v, key) refs

Raises:
    TypeError: If G is not a NetworkX graph
    ValueError: If graph has no nodes, or an edge cost is not an integer
        value

Example:
    >>> import networkx as nx
    >>> G = nx.DiGraph()
    >>> G.add_edge("src", "dst", capacity=100.0, cost=10)
    >>> graph, node_map, edge_map = from_networkx(G)
    >>> graph.num_nodes()
    2
    >>> node_map.to_index  # node indices assigned in sorted-name order
    {'dst': 0, 'src': 1}
    >>> edge_map.to_ref[0]  # edge refs preserve original (u, v, key)
    ('src', 'dst', 0)

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
