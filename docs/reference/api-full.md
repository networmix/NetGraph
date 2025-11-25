<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: November 25, 2025 at 04:05 UTC

Modules auto-discovered: 44

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
- `traffic_matrix_set` (TrafficMatrixSet) = TrafficMatrixSet(matrices={})
- `results` (Results) = Results(_store={}, _metadata={}, _active_step=None, _scenario={})
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})
- `seed` (Optional[int])

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

## ngraph.model.demand.matrix

Traffic matrix containers.

Provides `TrafficMatrixSet`, a named collection of `TrafficDemand` lists
used as input to demand expansion and placement. This module contains input
containers, not analysis results.

### TrafficMatrixSet

Named collection of TrafficDemand lists.

This mutable container maps scenario names to lists of TrafficDemand objects,
allowing management of multiple traffic matrices for analysis.

Attributes:
    matrices: Dictionary mapping scenario names to TrafficDemand lists.

**Attributes:**

- `matrices` (dict[str, list[TrafficDemand]]) = {}

**Methods:**

- `add(self, name: 'str', demands: 'list[TrafficDemand]') -> 'None'` - Add a traffic matrix to the collection.
- `get_all_demands(self) -> 'list[TrafficDemand]'` - Get all traffic demands from all matrices combined.
- `get_default_matrix(self) -> 'list[TrafficDemand]'` - Get default traffic matrix.
- `get_matrix(self, name: 'str') -> 'list[TrafficDemand]'` - Get a specific traffic matrix by name.
- `to_dict(self) -> 'dict[str, Any]'` - Convert to dictionary for JSON serialization.

---

## ngraph.model.demand.spec

Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyPreset` enum to construct one.

### TrafficDemand

Single traffic demand input.

Attributes:
    source_path: Regex string selecting source nodes.
    sink_path: Regex string selecting sink nodes.
    priority: Priority class for this demand (lower value = higher priority).
    demand: Total demand volume.
    demand_placed: Portion of this demand placed so far.
    flow_policy_config: Policy preset (FlowPolicyPreset enum) used to build
        a `FlowPolicy` if ``flow_policy`` is not provided.
    flow_policy: Concrete policy instance. If set, it overrides
        ``flow_policy_config``.
    mode: Expansion mode, ``"combine"`` or ``"pairwise"``.
    attrs: Arbitrary user metadata.
    id: Unique identifier assigned at initialization.

**Attributes:**

- `source_path` (str)
- `sink_path` (str)
- `priority` (int) = 0
- `demand` (float) = 0.0
- `demand_placed` (float) = 0.0
- `flow_policy_config` (Optional)
- `flow_policy` (Optional)
- `mode` (str) = combine
- `attrs` (Dict) = {}
- `id` (str)

---

## ngraph.model.failure.conditions

Shared condition primitives and evaluators.

This module provides a small, dependency-free condition evaluation utility
that can be reused by failure policies and DSL selection filters.

Operators supported:

- ==, !=, <, <=, >, >=
- contains, not_contains
- any_value, no_value

The evaluator operates on a flat attribute mapping for an entity. Callers are
responsible for constructing that mapping (e.g. merging top-level fields with
``attrs`` and ensuring appropriate precedence rules).

### FailureCondition

A single condition for matching an entity attribute.

Args:
    attr: Attribute name to inspect in the entity mapping.
    operator: Comparison operator. See module docstring for the list.
    value: Right-hand operand for the comparison (unused for any_value/no_value).

**Attributes:**

- `attr` (str)
- `operator` (str)
- `value` (Any | None)

### evaluate_condition(entity_attrs: 'dict[str, Any]', cond: 'FailureCondition') -> 'bool'

Evaluate a single condition against an entity attribute mapping.

Args:
    entity_attrs: Flat mapping of attributes for the entity.
    cond: Condition to evaluate.

Returns:
    True if the condition passes, False otherwise.

### evaluate_conditions(entity_attrs: 'dict[str, Any]', conditions: 'Iterable[FailureCondition]', logic: 'str') -> 'bool'

Evaluate multiple conditions with AND/OR logic.

Args:
    entity_attrs: Flat mapping of attributes for the entity.
    conditions: Iterable of conditions to evaluate.
    logic: "and" or "or".

Returns:
    True if the combined predicate passes, False otherwise.

---

## ngraph.model.failure.parser

Parsers for FailurePolicySet and related failure modeling structures.

### build_failure_policy(fp_data: 'Dict[str, Any]', *, policy_name: 'str', derive_seed) -> 'FailurePolicy'

No documentation available.

### build_failure_policy_set(raw: 'Dict[str, Any]', *, derive_seed) -> 'FailurePolicySet'

No documentation available.

### build_risk_groups(rg_data: 'List[Dict[str, Any]]') -> 'List[RiskGroup]'

No documentation available.

---

## ngraph.model.failure.policy

Failure policy primitives.

Defines `FailureCondition`, `FailureRule`, and `FailurePolicy` for expressing
how nodes, links, and risk groups fail in analyses. Conditions match on
top-level attributes with simple operators; rules select matches using
"all", probabilistic "random" (with `probability`), or fixed-size "choice"
(with `count`). Policies can optionally expand failures by shared risk groups
or by risk-group children.

### FailureCondition

Alias to the shared condition dataclass.

This maintains a consistent import path within the failure policy module.

**Attributes:**

- `attr` (str)
- `operator` (str)
- `value` (Any | None)

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

A container for multiple FailureRules plus optional metadata in `attrs`.

The main entry point is `apply_failures`, which:
  1) For each rule, gather the relevant entities (node, link, or risk_group).
          2) Match them based on rule conditions using 'and' or 'or' logic.
  3) Apply the selection strategy (all, random, or choice).
  4) Collect the union of all failed entities across all rules.
  5) Optionally expand failures by shared-risk groups or sub-risks.

Example YAML configuration:
    ```yaml
    failure_policy:
      attrs:
        description: "Regional power grid failure affecting telecom infrastructure"
      fail_risk_groups: true
      rules:
        # Fail all nodes in Texas electrical grid
        - entity_scope: "node"

          conditions:
            - attr: "electric_grid"

              operator: "=="
              value: "texas"
          logic: "and"
          rule_type: "all"

        # Randomly fail 40% of underground fiber links in affected region
        - entity_scope: "link"

          conditions:
            - attr: "region"

              operator: "=="
              value: "southwest"
            - attr: "installation"

              operator: "=="
              value: "underground"
          logic: "and"
          rule_type: "random"
          probability: 0.4

        # Choose exactly 2 risk groups to fail (e.g., data centers)
        # Note: logic defaults to "or" when not specified
        - entity_scope: "risk_group"

          rule_type: "choice"
          count: 2
    ```

Attributes:
    rules (List[FailureRule]):
        A list of FailureRules to apply.
    attrs (Dict[str, Any]):
        Arbitrary metadata about this policy (e.g. "name", "description").
    fail_risk_groups (bool):
        If True, after initial selection, expand failures among any
        node/link that shares a risk group with a failed entity.
    fail_risk_group_children (bool):
        If True, and if a risk_group is marked as failed, expand to
        children risk_groups recursively.
    seed (Optional[int]):
        Seed for reproducible random operations. If None, operations
        will be non-deterministic.

**Attributes:**

- `attrs` (Dict[str, Any]) = {}
- `fail_risk_groups` (bool) = False
- `fail_risk_group_children` (bool) = False
- `seed` (Optional[int])
- `modes` (List[FailureMode]) = []

**Methods:**

- `apply_failures(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None, *, seed: 'Optional[int]' = None) -> 'List[str]'` - Identify which entities fail for this iteration.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

### FailureRule

Defines how to match and then select entities for failure.

Attributes:
    entity_scope (EntityScope):
        The type of entities this rule applies to: "node", "link", or "risk_group".
    conditions (List[FailureCondition]):
        A list of conditions to filter matching entities.
    logic (Literal["and", "or"]):
        "and": All conditions must be true for a match.
        "or": At least one condition is true for a match (default).
    rule_type (Literal["random", "choice", "all"]):
        The selection strategy among the matched set:

- "random": each matched entity is chosen with probability = `probability`.
- "choice": pick exactly `count` items from the matched set (random sample).
- "all": select every matched entity in the matched set.

    probability (float):
        Probability in [0,1], used if `rule_type="random"`.
    count (int):
        Number of entities to pick if `rule_type="choice"`.

**Attributes:**

- `entity_scope` (EntityScope)
- `conditions` (List[FailureCondition]) = []
- `logic` (Literal['and', 'or']) = or
- `rule_type` (Literal['random', 'choice', 'all']) = all
- `probability` (float) = 1.0
- `count` (int) = 1
- `weight_by` (Optional[str])

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

---

## ngraph.model.network

Network topology modeling with Node, Link, RiskGroup, and Network classes.

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
- `build_core_graph(self, add_reverse: 'bool' = True, augmentations: 'Optional[List]' = None, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Tuple[Any, Any, Any, Any]'` - Build NetGraph-Core graph representation.
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
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'` - Select and group nodes by regex on name or by attribute directive.

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

Attributes:
    name (str): Unique name of this risk group.
    children (List[RiskGroup]): Subdomains in a nested structure.
    disabled (bool): Whether this group was declared disabled on load.
    attrs (Dict[str, Any]): Additional metadata for the risk group.

**Attributes:**

- `name` (str)
- `children` (List[RiskGroup]) = []
- `disabled` (bool) = False
- `attrs` (Dict[str, Any]) = {}

---

## ngraph.model.path

Lightweight representation of a single routing path.

The ``Path`` dataclass stores a node-and-parallel-edges sequence and a numeric
cost. Cached properties expose derived sequences for nodes and edges, and
helpers provide equality, ordering by cost, and sub-path extraction with cost
recalculation.

Breaking change from v1.x: Edge references now use EdgeRef (link_id + direction)
instead of integer edge keys for stable scenario-level edge identification.

### Path

Represents a single path in the network.

Breaking change from v1.x: path field now uses EdgeRef (link_id + direction)
instead of integer edge keys for stable scenario-level edge identification.

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

- `get_sub_path(self, dst_node: 'str', graph: 'StrictMultiDiGraph | None' = None, cost_attr: 'str' = 'cost') -> 'Path'` - Create a sub-path ending at the specified destination node.

---

## ngraph.solver.maxflow

Max-flow computation between node groups with NetGraph-Core integration.

This module provides max-flow analysis for Network models by transforming
multi-source/multi-sink problems into single-source/single-sink problems
using pseudo nodes.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph with pseudo nodes once and using O(|excluded|)
masks for exclusions.

### MaxFlowGraphCache

Pre-built graph with pseudo nodes for efficient repeated max-flow analysis.

Holds all components needed for running max-flow analysis with different
exclusion sets without rebuilding the graph. Includes pre-computed pseudo
node ID mappings for all source/sink pairs.

Attributes:
    graph_handle: Core Graph handle for algorithm execution.
    multidigraph: Core StrictMultiDiGraph with topology data.
    edge_mapper: Mapper for link_id <-> edge_id translation.
    node_mapper: Mapper for node_name <-> node_id translation.
    algorithms: Core Algorithms instance for running computations.
    pair_to_pseudo_ids: Mapping from (src_label, snk_label) to (pseudo_src_id, pseudo_snk_id).
    disabled_node_ids: Pre-computed set of disabled node IDs.
    disabled_link_ids: Pre-computed set of disabled link IDs.
    link_id_to_edge_indices: Mapping from link_id to edge array indices.

**Attributes:**

- `graph_handle` (netgraph_core.Graph)
- `multidigraph` (netgraph_core.StrictMultiDiGraph)
- `edge_mapper` (EdgeMapper)
- `node_mapper` (NodeMapper)
- `algorithms` (netgraph_core.Algorithms)
- `pair_to_pseudo_ids` (Dict[Tuple[str, str], Tuple[int, int]]) = {}
- `disabled_node_ids` (Set[int]) = set()
- `disabled_link_ids` (Set[str]) = set()
- `link_id_to_edge_indices` (Dict[str, List[int]]) = {}

### build_maxflow_cache(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine') -> 'MaxFlowGraphCache'

Build cached graph with pseudo nodes for efficient repeated max-flow analysis.

Constructs a single graph with all pseudo source/sink nodes for all
source/sink pairs, enabling O(|excluded|) mask building per iteration
instead of O(V+E) graph reconstruction.

Args:
    network: Network instance.
    source_path: Selection expression for source node groups.
    sink_path: Selection expression for sink node groups.
    mode: "combine" (single pair) or "pairwise" (N×M pairs).

Returns:
    MaxFlowGraphCache with pre-built graph and pseudo node mappings.

Raises:
    ValueError: If no matching sources or sinks are found.

### max_flow(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None, _cache: 'Optional[MaxFlowGraphCache]' = None) -> 'Dict[Tuple[str, str], float]'

Compute max flow between node groups in a network.

This function calculates the maximum flow from a set of source nodes
to a set of sink nodes within the provided network.

When `_cache` is provided, uses O(|excluded|) mask building instead of
O(V+E) graph reconstruction for efficient repeated analysis.

Args:
    network: Network instance containing topology and node/link data.
    source_path: Selection expression for source node groups.
    sink_path: Selection expression for sink node groups.
    mode: "combine" (all sources to all sinks) or "pairwise" (each pair separately).
    shortest_path: If True, restricts flow to shortest paths only.
    flow_placement: Strategy for distributing flow among equal-cost edges.
    excluded_nodes: Optional set of node names to exclude.
    excluded_links: Optional set of link IDs to exclude.
    _cache: Pre-built cache for efficient repeated analysis.

Returns:
    Dict mapping (source_label, sink_label) to total flow value.

Raises:
    ValueError: If no matching sources or sinks are found.

### max_flow_with_details(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None, _cache: 'Optional[MaxFlowGraphCache]' = None) -> 'Dict[Tuple[str, str], FlowSummary]'

Compute max flow with detailed results including cost distribution.

When `_cache` is provided, uses O(|excluded|) mask building instead of
O(V+E) graph reconstruction for efficient repeated analysis.

Args:
    network: Network instance.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    shortest_path: If True, restricts flow to shortest paths.
    flow_placement: Flow placement strategy.
    excluded_nodes: Optional set of node names to exclude.
    excluded_links: Optional set of link IDs to exclude.
    _cache: Pre-built cache for efficient repeated analysis.

Returns:
    Dict mapping (source_label, sink_label) to FlowSummary.

### sensitivity_analysis(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None, _cache: 'Optional[MaxFlowGraphCache]' = None) -> 'Dict[Tuple[str, str], Dict[str, float]]'

Analyze sensitivity of max flow to edge failures.

Identifies critical edges and computes the flow reduction caused by
removing each one.

When `_cache` is provided, uses O(|excluded|) mask building instead of
O(V+E) graph reconstruction for efficient repeated analysis.

The `shortest_path` parameter controls routing semantics:

- shortest_path=False (default): Full max-flow; reports all saturated edges.
- shortest_path=True: Shortest-path-only (IP/IGP); reports only edges

  used under ECMP routing.

Args:
    network: Network instance.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    shortest_path: If True, use single-tier shortest-path flow (IP/IGP).
                  If False, use full iterative max-flow (SDN/TE).
    flow_placement: Flow placement strategy.
    excluded_nodes: Optional set of node names to exclude.
    excluded_links: Optional set of link IDs to exclude.
    _cache: Pre-built cache for efficient repeated analysis.

Returns:
    Dict mapping (source_label, sink_label) to {link_id: flow_reduction}.

---

## ngraph.solver.paths

Shortest-path solver wrappers bound to the model layer.

Expose convenience functions for computing shortest paths between node groups
selected from a ``Network`` context. Selection semantics mirror the max-flow
wrappers with ``mode`` in {"combine", "pairwise"}.

Functions return minimal costs or concrete ``Path`` objects built from SPF
predecessor maps. Parallel equal-cost edges can be expanded into distinct
paths.

Graph caching is used internally for efficient mask-based exclusions. For
repeated queries with different exclusions, consider using the lower-level
adapters/core.py functions with explicit cache management.

All functions fail fast on invalid selection inputs and do not mutate the
input context.

Note:
    For path queries, overlapping source/sink membership is treated as
    unreachable.

### k_shortest_paths(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'pairwise', max_k: 'int' = 3, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], List[Path]]'

Return up to K shortest paths per group pair.

Args:
    network: Network instance.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "pairwise" (default) or "combine".
    max_k: Max paths per pair.
    edge_select: SPF/KSP edge selection strategy.
    max_path_cost: Absolute cost threshold.
    max_path_cost_factor: Relative threshold versus best path.
    split_parallel_edges: Expand parallel edges into distinct paths when True.
    excluded_nodes: Optional set of node names to exclude temporarily.
    excluded_links: Optional set of link IDs to exclude temporarily.

Returns:
    Mapping from (source_label, sink_label) to list of Path (<= max_k).

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

### shortest_path_costs(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], float]'

Return minimal path cost(s) between selected node groups.

Args:
    network: Network instance.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    edge_select: SPF edge selection strategy.
    excluded_nodes: Optional set of node names to exclude temporarily.
    excluded_links: Optional set of link IDs to exclude temporarily.

Returns:
    Mapping from (source_label, sink_label) to minimal cost; ``inf`` if no
    path.

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

### shortest_paths(network: 'Network', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, split_parallel_edges: 'bool' = False, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'Dict[Tuple[str, str], List[Path]]'

Return concrete shortest path(s) between selected node groups.

Args:
    network: Network instance.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    edge_select: SPF edge selection strategy.
    split_parallel_edges: Expand parallel edges into distinct paths when True.
    excluded_nodes: Optional set of node names to exclude temporarily.
    excluded_links: Optional set of link IDs to exclude temporarily.

Returns:
    Mapping from (source_label, sink_label) to list of Path. Empty if
    unreachable.

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

---

## ngraph.workflow.base

Base classes for workflow automation.

Defines the workflow step abstraction, registration decorator, and execution
wrapper that adds timing and logging. Steps implement `run()` and are executed
via `execute()` which records metadata and re-raises failures.

### WorkflowStep

Base class for all workflow steps.

All workflow steps are automatically logged with execution timing information.
All workflow steps support seeding for reproducible random operations.
Workflow metadata is automatically stored in scenario.results for analysis.

YAML Configuration:
    ```yaml
    workflow:
      - step_type: <StepTypeName>

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

---

## ngraph.workflow.build_graph

Graph building workflow component.

Validates and exports network topology as a node-link representation using NetworkX.
After NetGraph-Core integration, actual graph building happens in analysis
functions. This step primarily validates the network and stores a serializable
representation for inspection.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: BuildGraph

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

After NetGraph-Core integration, this step validates the network structure
and stores a JSON-serializable node-link representation using NetworkX.
Actual Core graph building happens in analysis functions as needed.

Attributes:
    add_reverse: If True, adds reverse edges for bidirectional connectivity.
                 Defaults to True for backward compatibility.

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
      - step_type: CostPower

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

YAML Configuration Example:

    workflow:

- step_type: MaxFlow

        name: "maxflow_dc_to_edge"
        source_path: "^datacenter/.*"
        sink_path: "^edge/.*"
        mode: "combine"
        failure_policy: "random_failures"
        iterations: 100
        parallelism: auto
        shortest_path: false
        flow_placement: "PROPORTIONAL"
        baseline: false
        seed: 42
        store_failure_patterns: false
        include_flow_details: false      # cost_distribution
        include_min_cut: false           # min-cut edges list

### MaxFlow

Maximum flow Monte Carlo workflow step.

Attributes:
    source_path: Regex pattern for source node groups.
    sink_path: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    failure_policy: Name of failure policy in scenario.failure_policy_set.
    iterations: Number of Monte Carlo trials.
    parallelism: Number of parallel worker processes.
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    baseline: Whether to run first iteration without failures as baseline.
    seed: Optional seed for reproducible results.
    store_failure_patterns: Whether to store failure patterns in results.
    include_flow_details: Whether to collect cost distribution per flow.
    include_min_cut: Whether to include min-cut edges per flow.

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `_seed_source` (str)
- `source_path` (str)
- `sink_path` (str)
- `mode` (str) = combine
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int | str) = auto
- `shortest_path` (bool) = False
- `flow_placement` (FlowPlacement | str) = 1
- `baseline` (bool) = False
- `store_failure_patterns` (bool) = False
- `include_flow_details` (bool) = False
- `include_min_cut` (bool) = False

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step logic.

---

## ngraph.workflow.maximum_supported_demand_step

Maximum Supported Demand (MSD) workflow step.

Searches for the maximum uniform traffic multiplier `alpha_star` that is fully
placeable for a given matrix. Stores results under `data` as:

- `alpha_star`: float
- `context`: parameters used for the search
- `base_demands`: serialized base demand specs
- `probes`: bracket/bisect evaluations with feasibility

### MaximumSupportedDemand

MaximumSupportedDemand(name: 'str' = '', seed: 'Optional[int]' = None, _seed_source: 'str' = '', matrix_name: 'str' = 'default', acceptance_rule: 'str' = 'hard', alpha_start: 'float' = 1.0, growth_factor: 'float' = 2.0, alpha_min: 'float' = 1e-06, alpha_max: 'float' = 1000000000.0, resolution: 'float' = 0.01, max_bracket_iters: 'int' = 32, max_bisect_iters: 'int' = 32, seeds_per_alpha: 'int' = 1, placement_rounds: 'int | str' = 'auto')

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)
- `matrix_name` (str) = default
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
      - step_type: NetworkStats

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

### build_workflow_steps(workflow_data: 'List[Dict[str, Any]]', derive_seed) -> 'List[WorkflowStep]'

Instantiate workflow steps from normalized dictionaries.

Args:
    workflow_data: List of step dicts; each must have "step_type".
    derive_seed: Callable(name: str) -> int | None, used to derive step seeds.

Returns:
    A list of WorkflowStep instances with unique names and optional seeds.

---

## ngraph.workflow.traffic_matrix_placement_step

TrafficMatrixPlacement workflow step.

Runs Monte Carlo demand placement using a named traffic matrix and produces
unified `flow_results` per iteration under `data.flow_results`.

### TrafficMatrixPlacement

Monte Carlo demand placement using a named traffic matrix.

Attributes:
    matrix_name: Name of the traffic matrix to analyze.
    failure_policy: Optional policy name in scenario.failure_policy_set.
    iterations: Number of Monte Carlo iterations.
    parallelism: Number of parallel worker processes.
    placement_rounds: Placement optimization rounds (int or "auto").
    baseline: Include baseline iteration without failures first.
    seed: Optional seed for reproducibility.
    store_failure_patterns: Whether to store failure pattern results.
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    alpha: Numeric scale for demands in the matrix.
    alpha_from_step: Optional producer step name to read alpha from.
    alpha_from_field: Dotted field path in producer step (default: "data.alpha_star").

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `_seed_source` (str)
- `matrix_name` (str)
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int | str) = auto
- `placement_rounds` (int | str) = auto
- `baseline` (bool) = False
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

A blueprint may contain multiple groups of nodes (each can have a node_count
and a name_template), plus adjacency rules describing how those groups connect.

Attributes:
    name (str): Unique identifier of this blueprint.
    groups (Dict[str, Any]): A mapping of group_name -> group definition.
        Allowed top-level keys in each group definition here are the same
        as in normal group definitions (e.g. node_count, name_template,
        attrs, disabled, risk_groups, or nested use_blueprint references, etc.).
    adjacency (List[Dict[str, Any]]): A list of adjacency definitions
        describing how these groups are linked, using the DSL fields
        (source, target, pattern, link_params, etc.).

**Attributes:**

- `name` (str)
- `groups` (Dict[str, Any])
- `adjacency` (List[Dict[str, Any]])

### DSLExpansionContext

Carries the blueprint definitions and the final Network instance
to be populated during DSL expansion.

Attributes:
    blueprints (Dict[str, Blueprint]): Dictionary of blueprint-name -> Blueprint.
    network (Network): The Network into which expanded nodes/links are inserted.
    pending_bp_adj (List[tuple[Dict[str, Any], str]]): Deferred blueprint adjacency
        expansions collected as (adj_def, parent_path) to be processed later.

**Attributes:**

- `blueprints` (Dict[str, Blueprint])
- `network` (Network)
- `pending_bp_adj` (List[tuple[Dict[str, Any], str]]) = []

### expand_network_dsl(data: 'Dict[str, Any]') -> 'Network'

Expands a combined blueprint + network DSL into a complete Network object.

Overall flow:
  1) Parse "blueprints" into Blueprint objects.
  2) Build a new Network from "network" metadata (e.g. name, version).
  3) Expand 'network["groups"]' (collect blueprint adjacencies for later).

- If a group references a blueprint, incorporate that blueprint's subgroups

       while merging parent's attrs + disabled + risk_groups into subgroups.
       Blueprint adjacency is deferred and processed after node overrides.

- Otherwise, directly create nodes (a "direct node group").

  4) Process any direct node definitions (network["nodes"]).
  5) Process node overrides (in order if multiple overrides match).
  6) Expand deferred blueprint adjacencies.
  7) Expand adjacency definitions in 'network["adjacency"]'.
  8) Process any direct link definitions (network["links"]).
  9) Process link overrides (in order if multiple overrides match).

Under the new rules:

- Only certain top-level fields are permitted in each structure. Any extra

    keys raise a ValueError. "attrs" is where arbitrary user fields go.

- For link_params, recognized fields are "capacity", "cost", "disabled",

    "risk_groups", "attrs". Everything else must go inside link_params["attrs"].

- For node/group definitions, recognized fields include "node_count",

    "name_template", "attrs", "disabled", "risk_groups" or "use_blueprint"
    for blueprint-based groups.

Args:
    data (Dict[str, Any]): The YAML-parsed dictionary containing
        optional "blueprints" + "network".

Returns:
    Network: The expanded Network object with all nodes and links.

---

## ngraph.dsl.blueprints.parser

Parsing helpers for the network DSL.

This module factors out pure parsing/validation helpers from the expansion
module so they can be tested independently and reused.

### check_adjacency_keys(adj_def: 'Dict[str, Any]', context: 'str') -> 'None'

Ensure adjacency definitions only contain recognized keys.

### check_link_params(link_params: 'Dict[str, Any]', context: 'str') -> 'None'

Ensure link_params contain only recognized keys.

Link attributes may include "hardware" per-end mapping when set under
link_params.attrs. This function only validates top-level link_params keys.

### check_no_extra_keys(data_dict: 'Dict[str, Any]', allowed: 'set[str]', context: 'str') -> 'None'

Raise if ``data_dict`` contains keys outside ``allowed``.

Args:
    data_dict: The dict to check.
    allowed: Set of recognized keys.
    context: Short description used in error messages.

### expand_name_patterns(name: 'str') -> 'List[str]'

Expand bracket expressions in a group name.

Examples:

- "fa[1-3]" -> ["fa1", "fa2", "fa3"]
- "dc[1,3,5-6]" -> ["dc1", "dc3", "dc5", "dc6"]
- "fa[1-2]_plane[5-6]" -> ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]

### join_paths(parent_path: 'str', rel_path: 'str') -> 'str'

Join two path segments according to the DSL conventions.

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

## ngraph.results.artifacts

Serializable result artifacts for analysis workflows.

This module defines dataclasses that capture outputs from analyses and
simulations in a JSON-serializable form:

- `CapacityEnvelope`: frequency-based capacity distributions and optional

  aggregated flow statistics

- `FailurePatternResult`: capacity results for specific failure patterns
- `PlacementEnvelope`: per-demand placement envelopes

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

### PlacementEnvelope

Per-demand placement envelope keyed like capacity envelopes.

Each envelope captures frequency distribution of placement ratio for a
specific demand definition across Monte Carlo iterations.

Attributes:
    source: Source selection regex or node label.
    sink: Sink selection regex or node label.
    mode: Demand expansion mode ("combine" or "pairwise").
    priority: Demand priority class.
    frequencies: Mapping of placement ratio to occurrence count.
    min: Minimum observed placement ratio.
    max: Maximum observed placement ratio.
    mean: Mean placement ratio.
    stdev: Standard deviation of placement ratio.
    total_samples: Number of iterations represented.

**Attributes:**

- `source` (str)
- `sink` (str)
- `mode` (str)
- `priority` (int)
- `frequencies` (Dict[float, int])
- `min` (float)
- `max` (float)
- `mean` (float)
- `stdev` (float)
- `total_samples` (int)

**Methods:**

- `from_dict(data: 'Dict[str, Any]') -> "'PlacementEnvelope'"` - Construct a PlacementEnvelope from a dictionary.
- `from_values(source: 'str', sink: 'str', mode: 'str', priority: 'int', ratios: 'List[float]', rounding_decimals: 'int' = 4) -> "'PlacementEnvelope'"`
- `to_dict(self) -> 'Dict[str, Any]'`

---

## ngraph.results.flow

Unified flow result containers for failure-analysis iterations.

Defines small, serializable dataclasses that capture per-iteration outcomes
for capacity and demand-placement style analyses in a unit-agnostic form.

Objects expose `to_dict()` that returns JSON-safe primitives. Float-keyed
distributions are normalized to string keys, and arbitrary `data` payloads are
sanitized. These dicts are written under `data.flow_results` by steps.

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
    failure_id: Stable identifier for the failure scenario (e.g., "baseline" or a hash).
    failure_state: Optional excluded components for the iteration.
    flows: List of flow entries for this iteration.
    summary: Aggregated summary across ``flows``.
    data: Optional per-iteration extras.

**Attributes:**

- `failure_id` (str)
- `failure_state` (Optional[Dict[str, List[str]]])
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

Build a concise dictionary snapshot of failure policies and traffic matrices for
export into results without keeping heavy domain objects.

### build_scenario_snapshot(*, seed: 'int | None', failure_policy_set, traffic_matrix_set) -> 'Dict[str, Any]'

No documentation available.

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

Edge selection criteria.

Determines which edges are considered for path-finding between a node and
its neighbor(s).

### FlowPlacement

Strategies to distribute flow across parallel equal-cost paths.

### PathAlg

Path-finding algorithm types.

---

## ngraph.types.dto

Types and data structures for algorithm analytics.

Defines immutable summary containers and aliases for algorithm outputs.

### EdgeRef

Reference to a directed edge via scenario link_id and direction.

Replaces the old Edge = Tuple[str, str, Hashable] to provide stable,
scenario-native edge identification across Core reorderings.

Attributes:
    link_id: Scenario link identifier (matches Network.links keys)
    direction: 'fwd' for source→target as defined in Link; 'rev' for reverse

**Attributes:**

- `link_id` (str)
- `direction` (EdgeDir)

### FlowSummary

Summary of max-flow computation results.

Captures edge flows, residual capacities, reachable set, and min-cut.

Breaking change from v1.x: Fields now use EdgeRef instead of (src, dst, key) tuples
for stable scenario-level edge identification.

Attributes:
    total_flow: Maximum flow value achieved.
    cost_distribution: Mapping of path cost to flow volume placed at that cost.
    min_cut: Saturated edges crossing the s-t cut.
    reachable_nodes: Nodes reachable from source in residual graph (optional).
    edge_flow: Flow amount per edge (optional, only populated when requested).
    residual_cap: Remaining capacity per edge after placement (optional).

**Attributes:**

- `total_flow` (float)
- `cost_distribution` (Dict[Cost, float])
- `min_cut` (Tuple[EdgeRef, ...])
- `reachable_nodes` (Tuple[str, ...] | None)
- `edge_flow` (Dict[EdgeRef, float] | None)
- `residual_cap` (Dict[EdgeRef, float] | None)

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

## ngraph.adapters.core

Adapter layer for NetGraph-Core integration.

Provides graph building, node/edge ID mapping, and result translation between
NetGraph's scenario-level types and NetGraph-Core's internal representations.

Graph caching enables efficient repeated analysis with different exclusion sets
by building the graph once and using lightweight masks for exclusions.

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

### EdgeMapper

Bidirectional mapping between external edge IDs and EdgeRef (link_id + direction).

External edge ID encoding: (linkIndex << 1) | dirBit

- linkIndex: stable sorted index of link_id in Network.links
- dirBit: 0 for forward ('fwd'), 1 for reverse ('rev')

**Methods:**

- `decode_ext_id(self, ext_id: 'int') -> 'Optional[EdgeRef]'` - Decode external edge ID to EdgeRef.
- `encode_ext_id(self, link_id: 'str', direction: 'str') -> 'int'` - Encode (link_id, direction) to external edge ID.
- `to_name(self, ext_id: 'int') -> 'Optional[str]'` - Map external edge ID to link ID (name).
- `to_ref(self, core_edge_id: 'int', multidigraph: 'netgraph_core.StrictMultiDiGraph') -> 'Optional[EdgeRef]'` - Map Core EdgeId to EdgeRef using the Core graph's ext_edge_ids.

### GraphCache

Pre-built graph components for efficient repeated analysis.

Holds all components needed for running analysis with different exclusion
sets without rebuilding the graph. Use build_graph_cache() to create.

Attributes:
    graph_handle: Core Graph handle for algorithm execution.
    multidigraph: Core StrictMultiDiGraph with topology data.
    edge_mapper: Mapper for link_id <-> edge_id translation.
    node_mapper: Mapper for node_name <-> node_id translation.
    algorithms: Core Algorithms instance for running computations.
    disabled_node_ids: Pre-computed set of disabled node IDs.
    disabled_link_ids: Pre-computed set of disabled link IDs.
    link_id_to_edge_indices: Mapping from link_id to edge array indices.

**Attributes:**

- `graph_handle` (netgraph_core.Graph)
- `multidigraph` (netgraph_core.StrictMultiDiGraph)
- `edge_mapper` (EdgeMapper)
- `node_mapper` (NodeMapper)
- `algorithms` (netgraph_core.Algorithms)
- `disabled_node_ids` (Set[int]) = set()
- `disabled_link_ids` (Set[str]) = set()
- `link_id_to_edge_indices` (Dict[str, List[int]]) = {}

### NodeMapper

Bidirectional mapping between NetGraph node names (str) and Core NodeId (int).

**Methods:**

- `to_id(self, name: 'str') -> 'int'` - Map node name to Core NodeId.
- `to_name(self, node_id: 'int') -> 'str'` - Map Core NodeId to node name.

### build_edge_mask(cache: 'GraphCache', excluded_links: 'Optional[Set[str]]' = None) -> 'np.ndarray'

Build an edge mask array for Core algorithms.

Uses O(|excluded| + |disabled|) time complexity by using the pre-computed
link_id -> edge_indices mapping, rather than iterating all edges.

Core semantics: True = include, False = exclude.

Args:
    cache: GraphCache with pre-computed edge index mapping.
    excluded_links: Optional set of link IDs to exclude.

Returns:
    Boolean numpy array of shape (num_edges,) where True means included.

### build_graph(network: "'Network'", *, add_reverse: 'bool' = True, augmentations: 'Optional[List[AugmentationEdge]]' = None, excluded_nodes: 'Optional[Set[str]]' = None, excluded_links: 'Optional[Set[str]]' = None) -> 'tuple[netgraph_core.Graph, netgraph_core.StrictMultiDiGraph, EdgeMapper, NodeMapper]'

Build Core graph with optional augmentations and exclusions.

This is the unified graph builder for all analysis functions. It supports:

- Standard network topology
- Pseudo/virtual nodes (via augmentations)
- Filtered topology (via exclusions)

For repeated analysis with different exclusions, use build_graph_cache()
with build_node_mask()/build_edge_mask() for better performance.

Args:
    network: NetGraph Network instance.
    add_reverse: If True, add reverse edges for network links.
    augmentations: Optional list of edges to add (for pseudo nodes, etc.).
    excluded_nodes: Optional set of node names to exclude.
    excluded_links: Optional set of link IDs to exclude.

Returns:
    Tuple of (graph_handle, multidigraph, edge_mapper, node_mapper).

Pseudo Nodes:
    Any node name in augmentations that doesn't exist in network.nodes
    is automatically treated as a pseudo node and assigned a node ID.

Augmentation Edges:

- Added unidirectionally as specified
- Assigned ext_edge_id of -1 (sentinel for non-network edges)
- Not included in edge_mapper translation

Node ID Assignment:
    Real nodes (sorted): IDs 0..(num_real-1)
    Pseudo nodes (sorted): IDs num_real..(num_real+num_pseudo-1)

### build_graph_cache(network: "'Network'", *, add_reverse: 'bool' = True, augmentations: 'Optional[List[AugmentationEdge]]' = None) -> 'GraphCache'

Build cached graph components for efficient repeated analysis.

Constructs the graph once and pre-computes mappings needed for fast
mask building. Use with build_node_mask() and build_edge_mask() for
O(|excluded|) exclusion handling instead of O(V+E).

Args:
    network: NetGraph Network instance.
    add_reverse: If True, add reverse edges for network links.
    augmentations: Optional list of edges to add (for pseudo nodes, etc.).

Returns:
    GraphCache with all pre-built components.

Example:
    >>> cache = build_graph_cache(network)
    >>> for excluded_nodes, excluded_links in failure_patterns:
    ...     node_mask = build_node_mask(cache, excluded_nodes)
    ...     edge_mask = build_edge_mask(cache, excluded_links)
    ...     result = cache.algorithms.max_flow(
    ...         cache.graph_handle, src, dst,
    ...         node_mask=node_mask, edge_mask=edge_mask
    ...     )

### build_node_mask(cache: 'GraphCache', excluded_nodes: 'Optional[Set[str]]' = None) -> 'np.ndarray'

Build a node mask array for Core algorithms.

Uses O(|excluded| + |disabled|) time complexity by only setting
excluded/disabled nodes to False, rather than iterating all nodes.

Core semantics: True = include, False = exclude.

Args:
    cache: GraphCache with pre-computed disabled node IDs.
    excluded_nodes: Optional set of node names to exclude.

Returns:
    Boolean numpy array of shape (num_nodes,) where True means included.

---

## ngraph.exec.analysis.flow

Flow analysis functions for network evaluation.

These functions are designed for use with FailureManager and follow the
AnalysisFunction protocol: analysis_func(network: Network, excluded_nodes: Set[str],
excluded_links: Set[str], **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems.

Graph caching enables efficient repeated analysis with different exclusion
sets by building the graph once and using O(|excluded|) masks for exclusions.

### build_demand_graph_cache(network: "'Network'", demands_config: 'list[dict[str, Any]]') -> 'GraphCache'

Build a graph cache for repeated demand placement analysis.

Pre-computes the graph with augmentations (pseudo source/sink nodes) for
efficient repeated analysis with different exclusion sets.

Args:
    network: Network instance.
    demands_config: List of demand configurations (same format as demand_placement_analysis).

Returns:
    GraphCache ready for use with demand_placement_analysis.

### build_maxflow_graph_cache(network: "'Network'", source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine') -> 'MaxFlowGraphCache'

Build a graph cache for repeated max-flow analysis.

Pre-computes the graph with pseudo source/sink nodes for all source/sink
pairs, enabling O(|excluded|) mask building per iteration.

Args:
    network: Network instance.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").

Returns:
    MaxFlowGraphCache ready for use with max_flow_analysis or sensitivity_analysis.

### demand_placement_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', demands_config: 'list[dict[str, Any]]', placement_rounds: 'int | str' = 'auto', include_flow_details: 'bool' = False, include_used_edges: 'bool' = False, _graph_cache: 'Optional[GraphCache]' = None, **kwargs) -> 'FlowIterationResult'

Analyze traffic demand placement success rates using Core directly.

This function:

1. Builds Core infrastructure (graph, algorithms, flow_graph) or uses cached
2. Expands demands into concrete (src, dst, volume) tuples
3. Places each demand using Core's FlowPolicy with exclusion masks
4. Aggregates results into FlowIterationResult

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    demands_config: List of demand configurations (serializable dicts).
    placement_rounds: Number of placement optimization rounds (unused - Core handles internally).
    include_flow_details: When True, include cost_distribution per flow.
    include_used_edges: When True, include set of used edges per demand in entry data.
    _graph_cache: Pre-built graph cache for fast repeated analysis.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    FlowIterationResult describing this iteration.

### max_flow_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, include_flow_details: 'bool' = False, include_min_cut: 'bool' = False, _graph_cache: 'Optional[MaxFlowGraphCache]' = None, **kwargs) -> 'FlowIterationResult'

Analyze maximum flow capacity between node groups.

When `_graph_cache` is provided, uses O(|excluded|) mask building instead
of O(V+E) graph reconstruction for efficient repeated analysis.

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    include_flow_details: Whether to collect cost distribution and similar details.
    include_min_cut: Whether to include min-cut edge list in entry data.
    _graph_cache: Pre-built cache for efficient repeated analysis.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    FlowIterationResult describing this iteration.

### sensitivity_analysis(network: "'Network'", excluded_nodes: 'Set[str]', excluded_links: 'Set[str]', source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, _graph_cache: 'Optional[MaxFlowGraphCache]' = None, **kwargs) -> 'dict[str, dict[str, float]]'

Analyze component sensitivity to failures.

Identifies critical edges (saturated edges) and computes the flow reduction
caused by removing each one.

When `_graph_cache` is provided, uses O(|excluded|) mask building instead
of O(V+E) graph reconstruction for efficient repeated analysis.

Args:
    network: Network instance.
    excluded_nodes: Set of node names to exclude temporarily.
    excluded_links: Set of link IDs to exclude temporarily.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: If True, use single-tier shortest-path flow (IP/IGP mode).
        Reports only edges used under ECMP routing. If False (default), use
        full iterative max-flow (SDN/TE mode) and report all saturated edges.
    flow_placement: Flow placement strategy.
    _graph_cache: Pre-built cache for efficient repeated analysis.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    Dictionary mapping flow keys ("src->dst") to dictionaries of component
    identifiers mapped to sensitivity scores.

---

## ngraph.exec.analysis.types

Typed protocols for analysis IPC payloads.

Defines lightweight, serializable structures used across worker boundaries
during parallel analysis execution.

### FlowResult

Normalized result record for a flow pair in one iteration.

Keys:
    src: Source label
    dst: Destination label
    metric: Name of metric ('capacity' or 'placement_ratio')
    value: Numeric value for the metric
    stats: Optional FlowStats with compact details
    priority: Optional demand priority (only for placement results)

### FlowStats

Compact per-flow statistics for aggregation.

Keys:
    cost_distribution: Mapping of path cost to flow volume.
    edges: List of edge identifiers (string form).
    edges_kind: Meaning of edges list: 'min_cut' for capacity analysis,
        'used' for demand placement edge usage.

---

## ngraph.exec.demand.builder

Builders for traffic matrices.

Construct `TrafficMatrixSet` from raw dictionaries (e.g. parsed YAML).
This logic was previously embedded in `Scenario.from_yaml`.

### build_traffic_matrix_set(raw: 'Dict[str, List[dict]]') -> 'TrafficMatrixSet'

Build a `TrafficMatrixSet` from a mapping of name -> list of dicts.

Args:
    raw: Mapping where each key is a matrix name and each value is a list of
        dictionaries with `TrafficDemand` constructor fields.

Returns:
    Initialized `TrafficMatrixSet` with constructed `TrafficDemand` objects.

Raises:
    ValueError: If ``raw`` is not a mapping of name -> list[dict].

---

## ngraph.exec.demand.expand

Demand expansion: converts TrafficDemand specs into concrete placement demands.

Supports both pairwise and combine modes through augmentation-based pseudo nodes.

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
    demand_id: Parent TrafficDemand ID (for tracking).

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

1. Selects node groups using Network's selection API
2. Distributes volume based on mode (combine/pairwise)
3. Generates augmentation edges for combine mode (pseudo nodes)
4. Returns demands (node names) + augmentations

Node names are used (not IDs) so expansion happens BEFORE graph building.
IDs are resolved after graph is built with augmentations.

Args:
    network: Network for node selection.
    traffic_demands: High-level demand specifications.
    default_policy_preset: Default policy if demand doesn't specify one.

Returns:
    DemandExpansion with demands and augmentations.

Raises:
    ValueError: If no demands could be expanded or unsupported mode.

---

## ngraph.exec.failure.manager

FailureManager for Monte Carlo failure analysis.

Provides the failure analysis engine for NetGraph. Supports parallel
processing, graph caching, and failure policy handling for workflow steps
and direct programmatic use.

Performance characteristics:
Time complexity: O(S + I × A / P), where S is one-time graph setup cost,
I is iteration count, A is per-iteration analysis cost, and P is parallelism.
Graph caching amortizes expensive graph construction across all iterations,
and O(|excluded|) mask building replaces O(V+E) iteration.

Space complexity: O(V + E + I × R), where V and E are node and link counts,
and R is result size per iteration. The pre-built graph is shared across
all iterations.

Parallelism: The C++ Core backend releases the GIL during computation,
enabling true parallelism with Python threads. With graph caching, most
per-iteration work happens in GIL-free C++ code, achieving near-linear
scaling with thread count.

### AnalysisFunction

Protocol for analysis functions used with FailureManager.

Analysis functions should take a Network, exclusion sets, and any additional
keyword arguments, returning analysis results of any type.

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

- `compute_exclusions(self, policy: "'FailurePolicy | None'" = None, seed_offset: 'int | None' = None) -> 'tuple[set[str], set[str]]'` - Compute set of nodes and links to exclude for a failure iteration.
- `get_failure_policy(self) -> "'FailurePolicy | None'"` - Get failure policy for analysis.
- `run_demand_placement_monte_carlo(self, demands_config: 'list[dict[str, Any]] | Any', iterations: 'int' = 100, parallelism: 'int' = 1, placement_rounds: 'int | str' = 'auto', baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_details: 'bool' = False, include_used_edges: 'bool' = False, **kwargs) -> 'Any'` - Analyze traffic demand placement success under failures.
- `run_max_flow_monte_carlo(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_summary: 'bool' = False, **kwargs) -> 'Any'` - Analyze maximum flow capacity envelopes between node groups under failures.
- `run_monte_carlo_analysis(self, analysis_func: 'AnalysisFunction', iterations: 'int' = 1, parallelism: 'int' = 1, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **analysis_kwargs) -> 'dict[str, Any]'` - Run Monte Carlo failure analysis with any analysis function.
- `run_sensitivity_monte_carlo(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **kwargs) -> 'dict[str, Any]'` - Analyze component criticality for flow capacity under failures.
- `run_single_failure_scenario(self, analysis_func: 'AnalysisFunction', **kwargs) -> 'Any'` - Run a single failure scenario for convenience.

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
