# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see **[api.md](api.md)**.

> **📋 Documentation Types:**

> - **[Main API Guide (api.md)](api.md)** - Curated examples and usage patterns
> - **This Document (api-full.md)** - Complete auto-generated reference
> - **[CLI Reference](cli.md)** - Command-line interface
> - **[DSL Reference](dsl.md)** - YAML syntax guide

**Generated from source code on:** June 13, 2025 at 17:13 UTC

**Modules auto-discovered:** 38

---

## ngraph.blueprints

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

**Attributes:**

- `blueprints` (Dict[str, Blueprint])
- `network` (Network)

### expand_network_dsl(data: 'Dict[str, Any]') -> 'Network'

Expands a combined blueprint + network DSL into a complete Network object.

Overall flow:
  1) Parse "blueprints" into Blueprint objects.
  2) Build a new Network from "network" metadata (e.g. name, version).
  3) Expand 'network["groups"]'.
     - If a group references a blueprint, incorporate that blueprint's subgroups
       while merging parent's attrs + disabled + risk_groups into subgroups.
     - Otherwise, directly create nodes (a "direct node group").
  4) Process any direct node definitions (network["nodes"]).
  5) Expand adjacency definitions in 'network["adjacency"]'.
  6) Process any direct link definitions (network["links"]).
  7) Process link overrides (in order if multiple overrides match).
  8) Process node overrides (in order if multiple overrides match).

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
    Network: The fully expanded Network object with all nodes and links.

---

## ngraph.cli

### main(argv: 'Optional[List[str]]' = None) -> 'None'

Entry point for the ``ngraph`` command.

Args:
    argv: Optional list of command-line arguments. If ``None``, ``sys.argv``
        is used.

---

## ngraph.components

### Component

A generic component that can represent chassis, line cards, optics, etc.
Components can have nested children, each with their own cost, power, etc.

Attributes:
    name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
    component_type (str): A string label (e.g., "chassis", "linecard", "optic").
    description (str): A human-readable description of this component.
    cost (float): Cost (capex) of a single instance of this component.
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
- `cost` (float) = 0.0
- `power_watts` (float) = 0.0
- `power_watts_max` (float) = 0.0
- `capacity` (float) = 0.0
- `ports` (int) = 0
- `count` (int) = 1
- `attrs` (Dict[str, Any]) = {}
- `children` (Dict[str, Component]) = {}

**Methods:**

- `as_dict(self, include_children: 'bool' = True) -> 'Dict[str, Any]'`
  - Returns a dictionary containing all properties of this component.
- `total_capacity(self) -> 'float'`
  - Computes the total (recursive) capacity of this component,
- `total_cost(self) -> 'float'`
  - Computes the total (recursive) cost of this component, including children,
- `total_power(self) -> 'float'`
  - Computes the total *typical* (recursive) power usage of this component,
- `total_power_max(self) -> 'float'`
  - Computes the total *peak* (recursive) power usage of this component,

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

- `clone(self) -> 'ComponentsLibrary'`
  - Creates a deep copy of this ComponentsLibrary.
- `from_dict(data: 'Dict[str, Any]') -> 'ComponentsLibrary'`
  - Constructs a ComponentsLibrary from a dictionary of raw component definitions.
- `from_yaml(yaml_str: 'str') -> 'ComponentsLibrary'`
  - Constructs a ComponentsLibrary from a YAML string. If the YAML contains
- `get(self, name: 'str') -> 'Optional[Component]'`
  - Retrieves a Component by its name from the library.
- `merge(self, other: 'ComponentsLibrary', override: 'bool' = True) -> 'ComponentsLibrary'`
  - Merges another ComponentsLibrary into this one. By default (override=True),

---

## ngraph.config

Configuration for NetGraph.

### TrafficManagerConfig

Configuration for traffic demand placement estimation.

**Attributes:**

- `default_rounds` (int) = 5
- `min_rounds` (int) = 5
- `max_rounds` (int) = 100
- `ratio_base` (int) = 5
- `ratio_multiplier` (int) = 5

**Methods:**

- `estimate_rounds(self, demand_capacity_ratio: float) -> int`
  - Calculate placement rounds based on demand to capacity ratio.

---

## ngraph.explorer

### ExternalLinkBreakdown

Holds stats for external links to a particular other subtree.

Attributes:
    link_count (int): Number of links to that other subtree.
    link_capacity (float): Sum of capacities for those links.

**Attributes:**

- `link_count` (int) = 0
- `link_capacity` (float) = 0.0

### NetworkExplorer

Provides hierarchical exploration of a Network, computing statistics in two modes:
'all' (ignores disabled) and 'active' (only enabled).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None) -> 'NetworkExplorer'`
  - Build a NetworkExplorer, constructing a tree plus 'all' and 'active' stats.
- `print_tree(self, node: 'Optional[TreeNode]' = None, indent: 'int' = 0, max_depth: 'Optional[int]' = None, skip_leaves: 'bool' = False, detailed: 'bool' = False, include_disabled: 'bool' = True) -> 'None'`
  - Print the hierarchy from 'node' down (default: root).

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
- `stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_cost=0.0, total_power=0.0)
- `active_stats` (TreeStats) = TreeStats(node_count=0, internal_link_count=0, internal_link_capacity=0.0, external_link_count=0, external_link_capacity=0.0, external_link_details={}, total_cost=0.0, total_power=0.0)
- `raw_nodes` (List[Node]) = []

**Methods:**

- `add_child(self, child_name: 'str') -> 'TreeNode'`
  - Ensure a child node named 'child_name' exists and return it.
- `is_leaf(self) -> 'bool'`
  - Return True if this node has no children.

### TreeStats

Aggregated statistics for a single tree node (subtree).

Attributes:
    node_count (int): Total number of nodes in this subtree.
    internal_link_count (int): Number of internal links in this subtree.
    internal_link_capacity (float): Sum of capacities for those internal links.
    external_link_count (int): Number of external links from this subtree to another.
    external_link_capacity (float): Sum of capacities for those external links.
    external_link_details (Dict[str, ExternalLinkBreakdown]): Breakdown by other subtree path.
    total_cost (float): Cumulative cost (nodes + links).
    total_power (float): Cumulative power (nodes + links).

**Attributes:**

- `node_count` (int) = 0
- `internal_link_count` (int) = 0
- `internal_link_capacity` (float) = 0.0
- `external_link_count` (int) = 0
- `external_link_capacity` (float) = 0.0
- `external_link_details` (Dict[str, ExternalLinkBreakdown]) = {}
- `total_cost` (float) = 0.0
- `total_power` (float) = 0.0

---

## ngraph.failure_manager

### FailureManager

Applies FailurePolicy to a Network, runs traffic placement, and (optionally)
repeats multiple times for Monte Carlo experiments.

Attributes:
    network (Network): The underlying network to mutate (enable/disable nodes/links).
    traffic_matrix_set (TrafficMatrixSet): Traffic matrices to place after failures.
    failure_policy_set (FailurePolicySet): Set of named failure policies.
    matrix_name (Optional[str]): Name of specific matrix to use, or None for default.
    policy_name (Optional[str]): Name of specific failure policy to use, or None for default.
    default_flow_policy_config: The default flow policy for any demands lacking one.

**Methods:**

- `apply_failures(self) -> 'None'`
  - Apply the current failure policy to self.network (in-place).
- `run_monte_carlo_failures(self, iterations: 'int', parallelism: 'int' = 1) -> 'Dict[str, Any]'`
  - Repeatedly applies (randomized) failures to the network and accumulates
- `run_single_failure_scenario(self) -> 'List[TrafficResult]'`
  - Applies failures to the network, places the demands, and returns per-demand results.

---

## ngraph.failure_policy

### FailureCondition

A single condition for matching an entity's attribute with an operator and value.

Example usage (YAML):
  conditions:
    - attr: "capacity"
      operator: "<"
      value: 100

Attributes:
    attr (str):
        The name of the attribute to inspect (e.g., "capacity", "region").
    operator (str):
        The comparison operator: "==", "!=", "<", "<=", ">", ">=",
        "contains", "not_contains", "any_value", or "no_value".
    value (Any):
        The value to compare against (e.g., 100, True, "foo", etc.).

**Attributes:**

- `attr` (str)
- `operator` (str)
- `value` (Any)

### FailurePolicy

A container for multiple FailureRules plus optional metadata in `attrs`.

The main entry point is `apply_failures`, which:
  1) For each rule, gather the relevant entities (node, link, or risk_group).
  2) Match them based on rule conditions (or skip if 'logic=any').
  3) Apply the selection strategy (all, random, or choice).
  4) Collect the union of all failed entities across all rules.
  5) Optionally expand failures by shared-risk groups or sub-risks.

Large-scale performance:
  - If you set `use_cache=True`, matched sets for each rule are cached,
    so repeated calls to `apply_failures` can skip re-matching if the
    network hasn't changed. If your network changes between calls,
    you should clear the cache or re-initialize the policy.

Attributes:
    rules (List[FailureRule]):
        A list of FailureRules to apply.
    attrs (Dict[str, Any]):
        Arbitrary metadata about this policy (e.g. "name", "description").
    fail_shared_risk_groups (bool):
        If True, after initial selection, expand failures among any
        node/link that shares a risk group with a failed entity.
    fail_risk_group_children (bool):
        If True, and if a risk_group is marked as failed, expand to
        children risk_groups recursively.
    use_cache (bool):
        If True, match results for each rule are cached to speed up
        repeated calls. If the network changes, the cached results
        may be stale.

**Attributes:**

- `rules` (List[FailureRule]) = []
- `attrs` (Dict[str, Any]) = {}
- `fail_shared_risk_groups` (bool) = False
- `fail_risk_group_children` (bool) = False
- `use_cache` (bool) = False
- `_match_cache` (Dict[int, Set[str]]) = {}

**Methods:**

- `apply_failures(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None) -> 'List[str]'`
  - Identify which entities fail given the defined rules, then optionally
- `to_dict(self) -> 'Dict[str, Any]'`
  - Convert to dictionary for JSON serialization.

### FailureRule

Defines how to match and then select entities for failure.

Attributes:
    entity_scope (EntityScope):
        The type of entities this rule applies to: "node", "link", or "risk_group".
    conditions (List[FailureCondition]):
        A list of conditions to filter matching entities.
    logic (Literal["and", "or", "any"]):
        "and": All conditions must be true for a match.
        "or": At least one condition is true for a match.
        "any": Skip condition checks and match all.
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
- `logic` (Literal['and', 'or', 'any']) = and
- `rule_type` (Literal['random', 'choice', 'all']) = all
- `probability` (float) = 1.0
- `count` (int) = 1

---

## ngraph.network

### Link

Represents a directed link between two nodes in the network.

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

- `add_link(self, link: 'Link') -> 'None'`
  - Add a link to the network (keyed by the link's auto-generated ID).
- `add_node(self, node: 'Node') -> 'None'`
  - Add a node to the network (keyed by node.name).
- `disable_all(self) -> 'None'`
  - Mark all nodes and links as disabled.
- `disable_link(self, link_id: 'str') -> 'None'`
  - Mark a link as disabled.
- `disable_node(self, node_name: 'str') -> 'None'`
  - Mark a node as disabled.
- `disable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'`
  - Disable all nodes/links that have 'name' in their risk_groups.
- `enable_all(self) -> 'None'`
  - Mark all nodes and links as enabled.
- `enable_link(self, link_id: 'str') -> 'None'`
  - Mark a link as enabled.
- `enable_node(self, node_name: 'str') -> 'None'`
  - Mark a node as enabled.
- `enable_risk_group(self, name: 'str', recursive: 'bool' = True) -> 'None'`
  - Enable all nodes/links that have 'name' in their risk_groups.
- `find_links(self, source_regex: 'Optional[str]' = None, target_regex: 'Optional[str]' = None, any_direction: 'bool' = False) -> 'List[Link]'`
  - Search for links using optional regex patterns for source or target node names.
- `get_links_between(self, source: 'str', target: 'str') -> 'List[str]'`
  - Retrieve all link IDs that connect the specified source node
- `max_flow(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], float]'`
  - Compute maximum flow between groups of source nodes and sink nodes.
- `max_flow_detailed(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]'`
  - Compute maximum flow with complete analytics and graph.
- `max_flow_with_graph(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]'`
  - Compute maximum flow and return the flow-assigned graph.
- `max_flow_with_summary(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, FlowSummary]]'`
  - Compute maximum flow with detailed analytics summary.
- `saturated_edges(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', tolerance: 'float' = 1e-10, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], List[Tuple[str, str, str]]]'`
  - Identify saturated (bottleneck) edges in max flow solutions between node groups.
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'`
  - Select and group nodes whose names match a given regular expression.
- `sensitivity_analysis(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', change_amount: 'float' = 1.0, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]'`
  - Perform sensitivity analysis on capacity changes for max flow solutions.
- `to_strict_multidigraph(self, add_reverse: 'bool' = True) -> 'StrictMultiDiGraph'`
  - Create a StrictMultiDiGraph representation of this Network.

### Node

Represents a node in the network.

Each node is uniquely identified by its name, which is used as
the key in the Network's node dictionary.

Attributes:
    name (str): Unique identifier for the node.
    disabled (bool): Whether the node is disabled (excluded from calculations).
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

### new_base64_uuid() -> 'str'

Generate a Base64-encoded, URL-safe UUID (22 characters, no padding).

Returns:
    str: A 22-character Base64 URL-safe string with trailing '=' removed.

---

## ngraph.results

### Results

A container for storing arbitrary key-value data that arises during workflow steps.
The data is organized by step name, then by key.

Example usage:
  results.put("Step1", "total_capacity", 123.45)
  cap = results.get("Step1", "total_capacity")  # returns 123.45
  all_caps = results.get_all("total_capacity")  # might return {"Step1": 123.45, "Step2": 98.76}

**Attributes:**

- `_store` (Dict) = {}

**Methods:**

- `get(self, step_name: str, key: str, default: Any = None) -> Any`
  - Retrieve the value from (step_name, key). If the key is missing, return `default`.
- `get_all(self, key: str) -> Dict[str, Any]`
  - Retrieve a dictionary of {step_name: value} for all step_names that contain the specified key.
- `put(self, step_name: str, key: str, value: Any) -> None`
  - Store a value under (step_name, key).
- `to_dict(self) -> Dict[str, Dict[str, Any]]`
  - Return a dictionary representation of all stored results.

---

## ngraph.results_artifacts

### CapacityEnvelope

Range of max-flow values measured between two node groups.

This immutable dataclass stores capacity measurements and automatically
computes statistical measures in __post_init__.

Attributes:
    source_pattern: Regex pattern for selecting source nodes.
    sink_pattern: Regex pattern for selecting sink nodes.
    mode: Flow computation mode (e.g., "combine").
    capacity_values: List of measured capacity values.
    min_capacity: Minimum capacity value (computed).
    max_capacity: Maximum capacity value (computed).
    mean_capacity: Mean capacity value (computed).
    stdev_capacity: Standard deviation of capacity values (computed).

**Attributes:**

- `source_pattern` (str)
- `sink_pattern` (str)
- `mode` (str) = combine
- `capacity_values` (list[float]) = []
- `min_capacity` (float)
- `max_capacity` (float)
- `mean_capacity` (float)
- `stdev_capacity` (float)

**Methods:**

- `to_dict(self) -> 'dict[str, Any]'`
  - Convert to dictionary for JSON serialization.

### FailurePolicySet

Named collection of FailurePolicy objects.

This mutable container maps failure policy names to FailurePolicy objects,
allowing management of multiple failure policies for analysis.

Attributes:
    policies: Dictionary mapping failure policy names to FailurePolicy objects.

**Attributes:**

- `policies` (dict[str, 'FailurePolicy']) = {}

**Methods:**

- `add(self, name: 'str', policy: "'FailurePolicy'") -> 'None'`
  - Add a failure policy to the collection.
- `get_all_policies(self) -> "list['FailurePolicy']"`
  - Get all failure policies from the collection.
- `get_default_policy(self) -> "'FailurePolicy | None'"`
  - Get the default failure policy.
- `get_policy(self, name: 'str') -> "'FailurePolicy'"`
  - Get a specific failure policy by name.
- `to_dict(self) -> 'dict[str, Any]'`
  - Convert to dictionary for JSON serialization.

### PlacementResultSet

Aggregated traffic placement results from one or many runs.

This immutable dataclass stores traffic placement results organized by case,
with overall statistics and per-demand statistics.

Attributes:
    results_by_case: Dictionary mapping case names to TrafficResult lists.
    overall_stats: Dictionary of overall statistics.
    demand_stats: Dictionary mapping demand keys to per-demand statistics.

**Attributes:**

- `results_by_case` (dict[str, list[TrafficResult]]) = {}
- `overall_stats` (dict[str, float]) = {}
- `demand_stats` (dict[tuple[str, str, int], dict[str, float]]) = {}

**Methods:**

- `to_dict(self) -> 'dict[str, Any]'`
  - Convert to dictionary for JSON serialization.

### TrafficMatrixSet

Named collection of TrafficDemand lists.

This mutable container maps scenario names to lists of TrafficDemand objects,
allowing management of multiple traffic matrices for analysis.

Attributes:
    matrices: Dictionary mapping scenario names to TrafficDemand lists.

**Attributes:**

- `matrices` (dict[str, list[TrafficDemand]]) = {}

**Methods:**

- `add(self, name: 'str', demands: 'list[TrafficDemand]') -> 'None'`
  - Add a traffic matrix to the collection.
- `get_all_demands(self) -> 'list[TrafficDemand]'`
  - Get all traffic demands from all matrices combined.
- `get_default_matrix(self) -> 'list[TrafficDemand]'`
  - Get the default traffic matrix.
- `get_matrix(self, name: 'str') -> 'list[TrafficDemand]'`
  - Get a specific traffic matrix by name.
- `to_dict(self) -> 'dict[str, Any]'`
  - Convert to dictionary for JSON serialization.

---

## ngraph.scenario

### Scenario

Represents a complete scenario for building and executing network workflows.

This scenario includes:
  - A network (nodes/links), constructed via blueprint expansion.
  - A failure policy set (one or more named failure policies).
  - A traffic matrix set containing one or more named traffic matrices.
  - A list of workflow steps to execute.
  - A results container for storing outputs.
  - A components_library for hardware/optics definitions.

Typical usage example:

    scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
    scenario.run()
    # Inspect scenario.results

**Attributes:**

- `network` (Network)
- `workflow` (List[WorkflowStep])
- `failure_policy_set` (FailurePolicySet) = FailurePolicySet(policies={})
- `traffic_matrix_set` (TrafficMatrixSet) = TrafficMatrixSet(matrices={})
- `results` (Results) = Results(_store={})
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})

**Methods:**

- `from_yaml(yaml_str: 'str', default_components: 'Optional[ComponentsLibrary]' = None) -> 'Scenario'`
  - Constructs a Scenario from a YAML string, optionally merging
- `run(self) -> 'None'`
  - Executes the scenario's workflow steps in order.

---

## ngraph.traffic_demand

### TrafficDemand

Represents a single traffic demand in a network.

Attributes:
    source_path (str): A regex pattern (string) for selecting source nodes.
    sink_path (str): A regex pattern (string) for selecting sink nodes.
    priority (int): A priority class for this demand (default=0).
    demand (float): The total demand volume (default=0.0).
    demand_placed (float): The portion of this demand that has been placed so far.
    flow_policy_config (Optional[FlowPolicyConfig]): The routing/placement policy config.
    flow_policy (Optional[FlowPolicy]): A fully constructed FlowPolicy instance.
        If provided, it overrides flow_policy_config.
    mode (str): Expansion mode for generating sub-demands.
    attrs (Dict[str, Any]): Additional arbitrary attributes.
    id (str): Unique ID assigned at initialization.

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

## ngraph.traffic_manager

### TrafficManager

Manages the expansion and placement of traffic demands on a Network.

This class:

  1) Builds (or rebuilds) a StrictMultiDiGraph from the given Network.
  2) Expands each TrafficDemand into one or more Demand objects based
     on a configurable 'mode' (e.g., 'combine' or 'full_mesh').
  3) Each Demand is associated with a FlowPolicy, which handles how flows
     are placed (split across paths, balancing, etc.).
  4) Provides methods to place all demands incrementally with optional
     re-optimization, reset usage, and retrieve flow/usage summaries.

In particular:
  - 'combine' mode:
    * Combine all matched sources into a single pseudo-source node, and all
      matched sinks into a single pseudo-sink node (named using the traffic
      demand's `source_path` and `sink_path`). A single Demand is created
      from the pseudo-source to the pseudo-sink, with the full volume.

  - 'full_mesh' mode:
    * All matched sources form one group, all matched sinks form another group.
      A separate Demand is created for each (src_node, dst_node) pair,
      skipping self-pairs. The total volume is split evenly across the pairs.

The sum of volumes of all expanded Demands for a given TrafficDemand matches
that TrafficDemand's `demand` value (unless no valid node pairs exist, in which
case no demands are created).

Attributes:
    network (Network): The underlying network object.
    traffic_matrix_set (TrafficMatrixSet): Traffic matrices containing demands.
    matrix_name (Optional[str]): Name of specific matrix to use, or None for default.
    default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
        a TrafficDemand does not specify one.
    graph (StrictMultiDiGraph): Active graph built from the network.
    demands (List[Demand]): All expanded demands from the active matrix.
    _td_to_demands (Dict[str, List[Demand]]): Internal mapping from
        TrafficDemand.id to its expanded Demand objects.

**Attributes:**

- `network` (Network)
- `traffic_matrix_set` (TrafficMatrixSet)
- `matrix_name` (Optional)
- `default_flow_policy_config` (FlowPolicyConfig) = 1
- `graph` (Optional)
- `demands` (List) = []
- `_td_to_demands` (Dict) = {}

**Methods:**

- `build_graph(self, add_reverse: bool = True) -> None`
  - Builds or rebuilds the internal StrictMultiDiGraph from self.network.
- `expand_demands(self) -> None`
  - Converts each TrafficDemand in the active matrix into one or more
- `get_flow_details(self) -> Dict[Tuple[int, int], Dict[str, object]]`
  - Summarizes flows from each Demand's FlowPolicy.
- `get_traffic_results(self, detailed: bool = False) -> List[ngraph.traffic_manager.TrafficResult]`
  - Returns traffic demand summaries.
- `place_all_demands(self, placement_rounds: Union[int, str] = 'auto', reoptimize_after_each_round: bool = False) -> float`
  - Places all expanded demands in ascending priority order using multiple
- `reset_all_flow_usages(self) -> None`
  - Removes flow usage from the graph for each Demand's FlowPolicy
- `summarize_link_usage(self) -> Dict[str, float]`
  - Returns the total flow usage per edge in the graph.

### TrafficResult

A container for traffic demand result data.

Attributes:
    priority (int): Demand priority class (lower=more critical).
    total_volume (float): Total traffic volume for this entry.
    placed_volume (float): The volume actually placed in the flow graph.
    unplaced_volume (float): The volume not placed (total_volume - placed_volume).
    src (str): Source node/path.
    dst (str): Destination node/path.

---

## ngraph.yaml_utils

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

## ngraph.lib.demand

### Demand

Represents a network demand between two nodes. It is realized via one or more
flows through a single FlowPolicy.

**Attributes:**

- `src_node` (NodeID)
- `dst_node` (NodeID)
- `volume` (float)
- `demand_class` (int) = 0
- `flow_policy` (Optional[FlowPolicy])
- `placed_demand` (float) = 0.0

**Methods:**

- `place(self, flow_graph: 'StrictMultiDiGraph', max_fraction: 'float' = 1.0, max_placement: 'Optional[float]' = None) -> 'Tuple[float, float]'`
  - Places demand volume onto the network via self.flow_policy.

---

## ngraph.lib.flow

### Flow

Represents a fraction of demand routed along a given PathBundle.

In traffic-engineering scenarios, a `Flow` object can model:
  - MPLS LSPs/tunnels with explicit paths,
  - IP forwarding behavior (with ECMP or UCMP),
  - Or anything that follows a specific set of paths.

**Methods:**

- `place_flow(self, flow_graph: 'StrictMultiDiGraph', to_place: 'float', flow_placement: 'FlowPlacement') -> 'Tuple[float, float]'`
  - Attempt to place (or update) this flow on the given `flow_graph`.
- `remove_flow(self, flow_graph: 'StrictMultiDiGraph') -> 'None'`
  - Remove this flow's contribution from the provided `flow_graph`.

### FlowIndex

Describes a unique identifier for a Flow in the network.

Attributes:
    src_node (NodeID): The source node of the flow.
    dst_node (NodeID): The destination node of the flow.
    flow_class (Hashable): Identifier representing the 'class' of this flow (e.g., traffic class).
                           Can be int, str, or any hashable type for flexibility.
    flow_id (int): A unique ID for this flow.

---

## ngraph.lib.flow_policy

### FlowPolicy

Manages the placement and management of flows (demands) on a network graph.

A FlowPolicy converts a demand into one or more Flow objects subject to
capacity constraints and user-specified configurations such as path
selection algorithms and flow placement methods.

**Methods:**

- `deep_copy(self) -> 'FlowPolicy'`
  - Creates and returns a deep copy of this FlowPolicy, including all flows.
- `place_demand(self, flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', flow_class: 'Hashable', volume: 'float', target_flow_volume: 'Optional[float]' = None, min_flow: 'Optional[float]' = None) -> 'Tuple[float, float]'`
  - Places the given demand volume on the network graph by splitting or creating
- `rebalance_demand(self, flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', flow_class: 'Hashable', target_flow_volume: 'float') -> 'Tuple[float, float]'`
  - Rebalances the demand across existing flows so that their volumes are closer
- `remove_demand(self, flow_graph: 'StrictMultiDiGraph') -> 'None'`
  - Removes all flows from the network graph without clearing internal state.

### FlowPolicyConfig

Enumerates supported flow policy configurations.

### get_flow_policy(flow_policy_config: 'FlowPolicyConfig') -> 'FlowPolicy'

Factory method to create and return a FlowPolicy instance based on the provided configuration.

Args:
    flow_policy_config: A FlowPolicyConfig enum value specifying the desired policy.

Returns:
    A pre-configured FlowPolicy instance corresponding to the specified configuration.

Raises:
    ValueError: If an unknown FlowPolicyConfig value is provided.

---

## ngraph.lib.graph

### StrictMultiDiGraph

A custom multi-directed graph with strict rules and unique edge IDs.

This class enforces:
  - No automatic creation of missing nodes when adding an edge.
  - No duplicate nodes (raising ValueError on duplicates).
  - No duplicate edges by key (raising ValueError on duplicates).
  - Attempting to remove non-existent nodes or edges raises ValueError.
  - Each edge key must be unique; by default, a Base64-UUID is generated
    if none is provided.
  - copy() can perform a pickle-based deep copy that may be faster
    than NetworkX's default.

Inherits from:
    networkx.MultiDiGraph

**Methods:**

- `add_edge(self, u_for_edge: 'NodeID', v_for_edge: 'NodeID', key: 'Optional[EdgeID]' = None, **attr: 'Any') -> 'EdgeID'`
  - Add a directed edge from u_for_edge to v_for_edge.
- `add_edges_from(self, ebunch_to_add, **attr)`
  - Add all the edges in ebunch_to_add.
- `add_node(self, node_for_adding: 'NodeID', **attr: 'Any') -> 'None'`
  - Add a single node, disallowing duplicates.
- `add_nodes_from(self, nodes_for_adding, **attr)`
  - Add multiple nodes.
- `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)`
  - Add weighted edges in `ebunch_to_add` with specified weight attr
- `adjacency(self)`
  - Returns an iterator over (node, adjacency dict) tuples for all nodes.
- `clear(self)`
  - Remove all nodes and edges from the graph.
- `clear_edges(self)`
  - Remove all edges from the graph without altering nodes.
- `copy(self, as_view: 'bool' = False, pickle: 'bool' = True) -> 'StrictMultiDiGraph'`
  - Create a copy of this graph.
- `edge_subgraph(self, edges)`
  - Returns the subgraph induced by the specified edges.
- `edges_between(self, u: 'NodeID', v: 'NodeID') -> 'List[EdgeID]'`
  - List all edge keys from node u to node v.
- `get_edge_attr(self, key: 'EdgeID') -> 'AttrDict'`
  - Retrieve the attribute dictionary of a specific edge.
- `get_edge_data(self, u, v, key=None, default=None)`
  - Returns the attribute dictionary associated with edge (u, v,
- `get_edges(self) -> 'Dict[EdgeID, EdgeTuple]'`
  - Retrieve a dictionary of all edges by their keys.
- `get_nodes(self) -> 'Dict[NodeID, AttrDict]'`
  - Retrieve all nodes and their attributes as a dictionary.
- `has_edge(self, u, v, key=None)`
  - Returns True if the graph has an edge between nodes u and v.
- `has_edge_by_id(self, key: 'EdgeID') -> 'bool'`
  - Check whether an edge with the given key exists.
- `has_node(self, n)`
  - Returns True if the graph contains the node n.
- `has_predecessor(self, u, v)`
  - Returns True if node u has predecessor v.
- `has_successor(self, u, v)`
  - Returns True if node u has successor v.
- `is_directed(self)`
  - Returns True if graph is directed, False otherwise.
- `is_multigraph(self)`
  - Returns True if graph is a multigraph, False otherwise.
- `nbunch_iter(self, nbunch=None)`
  - Returns an iterator over nodes contained in nbunch that are
- `neighbors(self, n)`
  - Returns an iterator over successor nodes of n.
- `new_edge_key(self, u, v)`
  - Returns an unused key for edges between nodes `u` and `v`.
- `number_of_edges(self, u=None, v=None)`
  - Returns the number of edges between two nodes.
- `number_of_nodes(self)`
  - Returns the number of nodes in the graph.
- `order(self)`
  - Returns the number of nodes in the graph.
- `predecessors(self, n)`
  - Returns an iterator over predecessor nodes of n.
- `remove_edge(self, u: 'NodeID', v: 'NodeID', key: 'Optional[EdgeID]' = None) -> 'None'`
  - Remove an edge (or edges) between nodes u and v.
- `remove_edge_by_id(self, key: 'EdgeID') -> 'None'`
  - Remove a directed edge by its unique key.
- `remove_edges_from(self, ebunch)`
  - Remove all edges specified in ebunch.
- `remove_node(self, n: 'NodeID') -> 'None'`
  - Remove a single node and all incident edges.
- `remove_nodes_from(self, nodes)`
  - Remove multiple nodes.
- `reverse(self, copy=True)`
  - Returns the reverse of the graph.
- `size(self, weight=None)`
  - Returns the number of edges or total of all edge weights.
- `subgraph(self, nodes)`
  - Returns a SubGraph view of the subgraph induced on `nodes`.
- `successors(self, n)`
  - Returns an iterator over successor nodes of n.
- `to_directed(self, as_view=False)`
  - Returns a directed representation of the graph.
- `to_directed_class(self)`
  - Returns the class to use for empty directed copies.
- `to_undirected(self, reciprocal=False, as_view=False)`
  - Returns an undirected representation of the digraph.
- `to_undirected_class(self)`
  - Returns the class to use for empty undirected copies.
- `update(self, edges=None, nodes=None)`
  - Update the graph using nodes/edges/graphs as input.
- `update_edge_attr(self, key: 'EdgeID', **attr: 'Any') -> 'None'`
  - Update attributes on an existing edge by key.

### new_base64_uuid() -> 'str'

Generate a Base64-encoded UUID without padding.

This function produces a 22-character, URL-safe, Base64-encoded UUID.

Returns:
    str: A unique 22-character Base64-encoded UUID.

---

## ngraph.lib.io

### edgelist_to_graph(lines: 'Iterable[str]', columns: 'List[str]', separator: 'str' = ' ', graph: 'Optional[StrictMultiDiGraph]' = None, source: 'str' = 'src', target: 'str' = 'dst', key: 'str' = 'key') -> 'StrictMultiDiGraph'

Builds or updates a StrictMultiDiGraph from an edge list.

Each line in the input is split by the specified separator into tokens. These tokens
are mapped to column names provided in `columns`. The tokens corresponding to `source`
and `target` become the node IDs. If a `key` column exists, its token is used as the edge
ID; remaining tokens are added as edge attributes.

Args:
    lines: An iterable of strings, each representing one edge.
    columns: A list of column names, e.g. ["src", "dst", "cost"].
    separator: The separator used to split each line (default is a space).
    graph: An existing StrictMultiDiGraph to update; if None, a new graph is created.
    source: The column name for the source node ID.
    target: The column name for the target node ID.
    key: The column name for a custom edge ID (if present).

Returns:
    The updated (or newly created) StrictMultiDiGraph.

### graph_to_edgelist(graph: 'StrictMultiDiGraph', columns: 'Optional[List[str]]' = None, separator: 'str' = ' ', source_col: 'str' = 'src', target_col: 'str' = 'dst', key_col: 'str' = 'key') -> 'List[str]'

Converts a StrictMultiDiGraph into an edge-list text representation.

Each line in the output represents one edge with tokens joined by the given separator.
By default, the output columns are:
    [source_col, target_col, key_col] + sorted(edge_attribute_names)

If an explicit list of columns is provided, those columns (in that order) are used,
and any missing values are output as an empty string.

Args:
    graph: The StrictMultiDiGraph to export.
    columns: Optional list of column names. If None, they are auto-generated.
    separator: The string used to join tokens (default is a space).
    source_col: The column name for the source node (default "src").
    target_col: The column name for the target node (default "dst").
    key_col: The column name for the edge key (default "key").

Returns:
    A list of strings, each representing one edge in the specified column format.

### graph_to_node_link(graph: 'StrictMultiDiGraph') -> 'Dict[str, Any]'

Converts a StrictMultiDiGraph into a node-link dict representation.

This representation is suitable for JSON serialization (e.g., for D3.js or Nx formats).

The returned dict has the following structure:
    {
        "graph": { ... top-level graph attributes ... },
        "nodes": [
            {"id": node_id, "attr": { ... node attributes ... }},
            ...
        ],
        "links": [
            {
                "source": <indexed_node>,
                "target": <indexed_node>,
                "key": <edge_id>,
                "attr": { ... edge attributes ... }
            },
            ...
        ]
    }

Args:
    graph: The StrictMultiDiGraph to convert.

Returns:
    A dict containing the 'graph' attributes, list of 'nodes', and list of 'links'.

### node_link_to_graph(data: 'Dict[str, Any]') -> 'StrictMultiDiGraph'

Reconstructs a StrictMultiDiGraph from its node-link dict representation.

Expected input format:
    {
        "graph": { ... graph attributes ... },
        "nodes": [
            {"id": <node_id>, "attr": { ... node attributes ... }},
            ...
        ],
        "links": [
            {
                "source": <indexed_node>,
                "target": <indexed_node>,
                "key": <edge_id>,
                "attr": { ... edge attributes ... }
            },
            ...
        ]
    }

Args:
    data: A dict representing the node-link structure.

Returns:
    A StrictMultiDiGraph reconstructed from the provided data.

---

## ngraph.lib.path

### Path

Represents a single path in the network.

Attributes:
    path_tuple (PathTuple):
        A sequence of path elements. Each element is a tuple of the form
        (node_id, (edge_id_1, edge_id_2, ...)), where the final element typically has an empty tuple.
    cost (Cost):
        The total numeric cost (e.g., distance or metric) of the path.
    edges (Set[EdgeID]):
        A set of all edge IDs encountered in the path.
    nodes (Set[NodeID]):
        A set of all node IDs encountered in the path.
    edge_tuples (Set[Tuple[EdgeID, ...]]):
        A set of all tuples of parallel edges from each path element (including the final empty tuple).

**Attributes:**

- `path_tuple` (PathTuple)
- `cost` (Cost)
- `edges` (Set[EdgeID]) = set()
- `nodes` (Set[NodeID]) = set()
- `edge_tuples` (Set[Tuple[EdgeID, ...]]) = set()

**Methods:**

- `get_sub_path(self, dst_node: 'NodeID', graph: 'StrictMultiDiGraph', cost_attr: 'str' = 'cost') -> 'Path'`
  - Create a sub-path ending at the specified destination node, recalculating the cost.

---

## ngraph.lib.path_bundle

### PathBundle

A collection of equal-cost paths between two nodes.

This class encapsulates one or more parallel paths (all of the same cost)
between `src_node` and `dst_node`. The predecessor map `pred` associates
each node with the node(s) from which it can be reached, along with a list
of edge IDs used in that step. The constructor performs a reverse traversal
from `dst_node` to `src_node` to collect all edges, nodes, and store them
in this bundle.

Since we trust the input is already a DAG, no cycle-detection checks
are performed. All relevant edges and nodes are simply gathered.
If it's not a DAG, the behavior is... an infinite loop. Oops.

**Methods:**

- `add(self, other: 'PathBundle') -> 'PathBundle'`
  - Concatenate this bundle with another bundle (end-to-start).
- `contains(self, other: 'PathBundle') -> 'bool'`
  - Check if this bundle's edge set contains all edges of `other`.
- `from_path(path: 'Path', resolve_edges: 'bool' = False, graph: 'Optional[StrictMultiDiGraph]' = None, edge_select: 'Optional[EdgeSelect]' = None, cost_attr: 'str' = 'cost', capacity_attr: 'str' = 'capacity') -> 'PathBundle'`
  - Construct a PathBundle from a single `Path` object.
- `get_sub_path_bundle(self, new_dst_node: 'NodeID', graph: 'StrictMultiDiGraph', cost_attr: 'str' = 'cost') -> 'PathBundle'`
  - Create a sub-bundle ending at `new_dst_node` (which must appear in this bundle).
- `is_disjoint_from(self, other: 'PathBundle') -> 'bool'`
  - Check if this bundle shares no edges with `other`.
- `is_subset_of(self, other: 'PathBundle') -> 'bool'`
  - Check if this bundle's edge set is contained in `other`'s edge set.
- `resolve_to_paths(self, split_parallel_edges: 'bool' = False) -> 'Iterator[Path]'`
  - Generate all concrete `Path` objects contained in this PathBundle.

---

## ngraph.lib.util

### from_digraph(nx_graph: networkx.classes.digraph.DiGraph) -> ngraph.lib.graph.StrictMultiDiGraph

Convert a revertible NetworkX DiGraph to a StrictMultiDiGraph.

This function reconstructs the original StrictMultiDiGraph by restoring
multi-edge information from the '_uv_edges' attribute of each edge.

Args:
    nx_graph: A revertible NetworkX DiGraph with '_uv_edges' attributes.

Returns:
    A StrictMultiDiGraph reconstructed from the input DiGraph.

### from_graph(nx_graph: networkx.classes.graph.Graph) -> ngraph.lib.graph.StrictMultiDiGraph

Convert a revertible NetworkX Graph to a StrictMultiDiGraph.

Restores the original multi-edge structure from the '_uv_edges' attribute stored
in each consolidated edge.

Args:
    nx_graph: A revertible NetworkX Graph with '_uv_edges' attributes.

Returns:
    A StrictMultiDiGraph reconstructed from the input Graph.

### to_digraph(graph: ngraph.lib.graph.StrictMultiDiGraph, edge_func: Optional[Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, dict], dict]] = None, revertible: bool = True) -> networkx.classes.digraph.DiGraph

Convert a StrictMultiDiGraph to a NetworkX DiGraph.

This function consolidates multi-edges between nodes into a single edge.
Optionally, a custom edge function can be provided to compute edge attributes.
If `revertible` is True, the original multi-edge data is stored in the '_uv_edges'
attribute of each consolidated edge, allowing for later reversion.

Args:
    graph: The StrictMultiDiGraph to convert.
    edge_func: Optional function to compute consolidated edge attributes.
               Should accept (graph, u, v, edges) and return a dict.
    revertible: If True, store the original multi-edge data.

Returns:
    A NetworkX DiGraph representing the input graph.

### to_graph(graph: ngraph.lib.graph.StrictMultiDiGraph, edge_func: Optional[Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, dict], dict]] = None, revertible: bool = True) -> networkx.classes.graph.Graph

Convert a StrictMultiDiGraph to a NetworkX Graph.

This function works similarly to `to_digraph` but returns an undirected graph.

Args:
    graph: The StrictMultiDiGraph to convert.
    edge_func: Optional function to compute consolidated edge attributes.
    revertible: If True, store the original multi-edge data.

Returns:
    A NetworkX Graph representing the input graph.

---

## ngraph.lib.algorithms.base

### EdgeSelect

Edge selection criteria determining which edges are considered
for path-finding between a node and its neighbor(s).

### FlowPlacement

Ways to distribute flow across parallel equal cost paths.

### PathAlg

Types of path finding algorithms

---

## ngraph.lib.algorithms.calc_capacity

### calc_graph_capacity(flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', pred: 'Dict[NodeID, Dict[NodeID, List[EdgeID]]]', flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, capacity_attr: 'str' = 'capacity', flow_attr: 'str' = 'flow') -> 'Tuple[float, Dict[NodeID, Dict[NodeID, float]]]'

Calculate the maximum feasible flow from src_node to dst_node (forward sense)
using either the PROPORTIONAL or EQUAL_BALANCED approach.

In PROPORTIONAL mode (similar to Dinic in reversed orientation):
  1. Build the reversed residual graph from dst_node (via `_init_graph_data`).
  2. Use BFS (in `_set_levels_bfs`) to build a level graph and DFS (`_push_flow_dfs`)
     to push blocking flows, repeating until no more flow can be pushed.
  3. The net flow found is stored in reversed orientation. Convert final flows
     to forward orientation by negating and normalizing by the total.

In EQUAL_BALANCED mode:
  1. Build reversed adjacency from dst_node (also via `_init_graph_data`),
     ignoring capacity checks in that BFS.
  2. Perform a BFS pass from src_node (`_equal_balance_bfs`) to distribute a
     nominal flow of 1.0 equally among parallel edges.
  3. Determine the scaling ratio so that no edge capacity is exceeded.
     Scale the flow assignments accordingly, then normalize to the forward sense.

Args:
    flow_graph: The multigraph with capacity and flow attributes.
    src_node: The source node in the forward graph.
    dst_node: The destination node in the forward graph.
    pred: Forward adjacency mapping (node -> (adjacent node -> list of EdgeIDs)),
          typically produced by `spf(..., multipath=True)`. Must be a DAG.
    flow_placement: The flow distribution strategy (PROPORTIONAL or EQUAL_BALANCED).
    capacity_attr: Name of the capacity attribute on edges.
    flow_attr: Name of the flow attribute on edges.

Returns:
    A tuple of:
      - total_flow: The maximum feasible flow from src_node to dst_node.
      - flow_dict: A nested dictionary [u][v] -> flow value in the forward sense.
        Positive if flow is from u to v, negative otherwise.

Raises:
    ValueError: If src_node or dst_node is not in the graph, or the flow_placement
                is unsupported.

---

## ngraph.lib.algorithms.edge_select

### edge_select_fabric(edge_select: ngraph.lib.algorithms.base.EdgeSelect, select_value: Optional[Any] = None, edge_select_func: Optional[Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Optional[Set[Hashable]], Optional[Set[Hashable]]], Tuple[Union[int, float], List[Hashable]]]] = None, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None, cost_attr: str = 'cost', capacity_attr: str = 'capacity', flow_attr: str = 'flow') -> Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Optional[Set[Hashable]], Optional[Set[Hashable]]], Tuple[Union[int, float], List[Hashable]]]

Creates a function that selects edges between two nodes according
to a given EdgeSelect strategy (or a user-defined function).

Args:
    edge_select: An EdgeSelect enum specifying the selection strategy.
    select_value: An optional numeric threshold or scaling factor for capacity checks.
    edge_select_func: A user-supplied function if edge_select=USER_DEFINED.
    excluded_edges: A set of edges to ignore entirely.
    excluded_nodes: A set of nodes to skip (if the destination node is in this set).
    cost_attr: The edge attribute name representing cost.
    capacity_attr: The edge attribute name representing capacity.
    flow_attr: The edge attribute name representing current flow.

Returns:
    A function with signature:
        (graph, src_node, dst_node, edges_dict, excluded_edges, excluded_nodes) ->
        (selected_cost, [list_of_edge_ids])
    where:
        - `selected_cost` is the numeric cost used by the path-finding algorithm (e.g. Dijkstra).
        - `[list_of_edge_ids]` is the list of edges chosen.

---

## ngraph.lib.algorithms.flow_init

### init_flow_graph(flow_graph: 'StrictMultiDiGraph', flow_attr: 'str' = 'flow', flows_attr: 'str' = 'flows', reset_flow_graph: 'bool' = True) -> 'StrictMultiDiGraph'

Ensure that every node and edge in the provided `flow_graph` has
flow-related attributes. Specifically, for each node and edge:

- The attribute named `flow_attr` (default: "flow") is set to 0.
- The attribute named `flows_attr` (default: "flows") is set to an empty dict.

If `reset_flow_graph` is True, any existing flow values in these attributes
are overwritten; otherwise they are only created if missing.

Args:
    flow_graph: The StrictMultiDiGraph whose nodes and edges should be
        prepared for flow assignment.
    flow_attr: The attribute name to track a numeric flow value per node/edge.
    flows_attr: The attribute name to track multiple flow identifiers (and flows).
    reset_flow_graph: If True, reset existing flows (set to 0). If False, do not overwrite.

Returns:
    The same `flow_graph` object, after ensuring each node/edge has the
    necessary flow-related attributes.

---

## ngraph.lib.algorithms.max_flow

### calc_max_flow(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, return_summary: bool = False, return_graph: bool = False, flow_placement: ngraph.lib.algorithms.base.FlowPlacement = <FlowPlacement.PROPORTIONAL: 1>, shortest_path: bool = False, reset_flow_graph: bool = False, capacity_attr: str = 'capacity', flow_attr: str = 'flow', flows_attr: str = 'flows', copy_graph: bool = True) -> Union[float, tuple]

Compute the maximum flow between two nodes in a directed multi-graph,
using an iterative shortest-path augmentation approach.

By default, this function:
  1. Creates or re-initializes a flow-aware copy of the graph (via ``init_flow_graph``).
  2. Repeatedly finds a path from ``src_node`` to ``dst_node`` using ``spf`` with
     capacity constraints (``EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING``).
  3. Places flow along that path (via ``place_flow_on_graph``) until no augmenting path
     remains or the capacities are exhausted.

If ``shortest_path=True``, the function performs only one iteration (single augmentation)
and returns the flow placed along that single path (not the true max flow).

Args:
    graph (StrictMultiDiGraph):
        The original graph containing capacity/flow attributes on each edge.
    src_node (NodeID):
        The source node for flow.
    dst_node (NodeID):
        The destination node for flow.
    return_summary (bool):
        If True, return a FlowSummary with detailed flow analytics.
        Defaults to False.
    return_graph (bool):
        If True, return the mutated flow graph along with other results.
        Defaults to False.
    flow_placement (FlowPlacement):
        Determines how flow is split among parallel edges of equal cost.
        Defaults to ``FlowPlacement.PROPORTIONAL``.
    shortest_path (bool):
        If True, place flow only once along the first shortest path found and return
        immediately, rather than iterating for the true max flow.
    reset_flow_graph (bool):
        If True, reset any existing flow data (e.g., ``flow_attr``, ``flows_attr``).
        Defaults to False.
    capacity_attr (str):
        The name of the capacity attribute on edges. Defaults to "capacity".
    flow_attr (str):
        The name of the aggregated flow attribute on edges. Defaults to "flow".
    flows_attr (str):
        The name of the per-flow dictionary attribute on edges. Defaults to "flows".
    copy_graph (bool):
        If True, work on a copy of the original graph so it remains unmodified.
        Defaults to True.

Returns:
    Union[float, tuple]:
        - If neither return_summary nor return_graph: float (total flow)
        - If return_summary only: tuple[float, FlowSummary]
        - If both flags: tuple[float, FlowSummary, StrictMultiDiGraph]

Notes:
    - For large graphs or performance-critical scenarios, consider specialized max-flow
      algorithms (e.g., Dinic, Edmond-Karp) for better scaling.
    - When using return_summary or return_graph, callers must unpack the returned tuple.

Examples:
    >>> g = StrictMultiDiGraph()
    >>> g.add_node('A')
    >>> g.add_node('B')
    >>> g.add_node('C')
    >>> g.add_edge('A', 'B', capacity=10.0, flow=0.0, flows={}, cost=1)
    >>> g.add_edge('B', 'C', capacity=5.0, flow=0.0, flows={}, cost=1)
    >>>
    >>> # Basic usage (scalar return)
    >>> max_flow_value = calc_max_flow(g, 'A', 'C')
    >>> print(max_flow_value)
    5.0
    >>>
    >>> # With flow summary analytics
    >>> flow, summary = calc_max_flow(g, 'A', 'C', return_summary=True)
    >>> print(f"Min-cut edges: {summary.min_cut}")
    >>>
    >>> # With both summary and mutated graph
    >>> flow, summary, flow_graph = calc_max_flow(
    ...     g, 'A', 'C', return_summary=True, return_graph=True
    ... )
    >>> # flow_graph contains the flow assignments

### run_sensitivity(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, capacity_attr: str = 'capacity', flow_attr: str = 'flow', change_amount: float = 1.0, **kwargs) -> dict[tuple, float]

Perform sensitivity analysis to identify high-impact capacity changes.

Tests changing each saturated edge capacity by change_amount and measures
the resulting change in total flow. Positive values increase capacity,
negative values decrease capacity (with validation to prevent negative capacities).

Args:
    graph: The graph to analyze
    src_node: Source node
    dst_node: Destination node
    capacity_attr: Name of capacity attribute
    flow_attr: Name of flow attribute
    change_amount: Amount to change capacity for testing (positive=increase, negative=decrease)
    **kwargs: Additional arguments passed to calc_max_flow

Returns:
    Dictionary mapping edge tuples to flow change when capacity is modified

### saturated_edges(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, capacity_attr: str = 'capacity', flow_attr: str = 'flow', tolerance: float = 1e-10, **kwargs) -> list[tuple]

Identify saturated (bottleneck) edges in the max flow solution.

Args:
    graph: The graph to analyze
    src_node: Source node
    dst_node: Destination node
    capacity_attr: Name of capacity attribute
    flow_attr: Name of flow attribute
    tolerance: Tolerance for considering an edge saturated
    **kwargs: Additional arguments passed to calc_max_flow

Returns:
    List of saturated edge tuples (u, v, k) where residual capacity <= tolerance

---

## ngraph.lib.algorithms.path_utils

### resolve_to_paths(src_node: 'NodeID', dst_node: 'NodeID', pred: 'Dict[NodeID, Dict[NodeID, List[EdgeID]]]', split_parallel_edges: 'bool' = False) -> 'Iterator[PathTuple]'

Enumerate all source->destination paths from a predecessor map.

Args:
    src_node: Source node ID.
    dst_node: Destination node ID.
    pred: Predecessor map from SPF or KSP.
    split_parallel_edges: If True, expand parallel edges into distinct paths.

Yields:
    A tuple of (nodeID, (edgeIDs,)) pairs from src_node to dst_node.

---

## ngraph.lib.algorithms.place_flow

### FlowPlacementMeta

Metadata capturing how flow was placed on the graph.

Attributes:
    placed_flow: The amount of flow actually placed.
    remaining_flow: The portion of flow that could not be placed due to capacity limits.
    nodes: Set of node IDs that participated in the flow.
    edges: Set of edge IDs that carried some portion of this flow.

**Attributes:**

- `placed_flow` (float)
- `remaining_flow` (float)
- `nodes` (Set[NodeID]) = set()
- `edges` (Set[EdgeID]) = set()

### place_flow_on_graph(flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', pred: 'Dict[NodeID, Dict[NodeID, List[EdgeID]]]', flow: 'float' = inf, flow_index: 'Optional[Hashable]' = None, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, capacity_attr: 'str' = 'capacity', flow_attr: 'str' = 'flow', flows_attr: 'str' = 'flows') -> 'FlowPlacementMeta'

Place flow from `src_node` to `dst_node` on the given `flow_graph`.

Uses a precomputed `flow_dict` from `calc_graph_capacity` to figure out how
much flow can be placed. Updates the graph's edges and nodes with the placed flow.

Args:
    flow_graph: The graph on which flow will be placed.
    src_node: The source node.
    dst_node: The destination node.
    pred: A dictionary of node->(adj_node->list_of_edge_IDs) giving path adjacency.
    flow: Requested flow amount; can be infinite.
    flow_index: Identifier for this flow (used to track multiple flows).
    flow_placement: Strategy for distributing flow among parallel equal cost paths.
    capacity_attr: Attribute name on edges for capacity.
    flow_attr: Attribute name on edges/nodes for aggregated flow.
    flows_attr: Attribute name on edges/nodes for per-flow tracking.

Returns:
    FlowPlacementMeta: Contains the placed flow amount, remaining flow amount,
        and sets of touched nodes/edges.

### remove_flow_from_graph(flow_graph: 'StrictMultiDiGraph', flow_index: 'Optional[Hashable]' = None, flow_attr: 'str' = 'flow', flows_attr: 'str' = 'flows') -> 'None'

Remove one (or all) flows from the given graph.

Args:
    flow_graph: The graph from which flow(s) should be removed.
    flow_index: If provided, only remove the specified flow. If None,
        remove all flows entirely.
    flow_attr: The aggregate flow attribute name on edges.
    flows_attr: The per-flow attribute name on edges.

---

## ngraph.lib.algorithms.spf

### ksp(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, edge_select: ngraph.lib.algorithms.base.EdgeSelect = <EdgeSelect.ALL_MIN_COST: 1>, edge_select_func: Optional[Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Set[Hashable], Set[Hashable]], Tuple[Union[int, float], List[Hashable]]]] = None, max_k: Optional[int] = None, max_path_cost: Union[int, float] = inf, max_path_cost_factor: Optional[float] = None, multipath: bool = True, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None) -> Iterator[Tuple[Dict[Hashable, Union[int, float]], Dict[Hashable, Dict[Hashable, List[Hashable]]]]]

Generator of up to k shortest paths from src_node to dst_node using a Yen-like algorithm.

The initial SPF (shortest path) is computed; subsequent paths are found by systematically
excluding edges/nodes used by previously generated paths. Each iteration yields a
(costs, pred) describing one path. Stops if there are no more valid paths or if max_k
is reached.

Args:
    graph: The directed graph (StrictMultiDiGraph).
    src_node: The source node.
    dst_node: The destination node.
    edge_select: The edge selection strategy. Defaults to ALL_MIN_COST.
    edge_select_func: Optional override of the default edge selection function.
    max_k: If set, yields at most k distinct paths.
    max_path_cost: If set, do not yield any path whose total cost > max_path_cost.
    max_path_cost_factor: If set, updates max_path_cost to:
        min(max_path_cost, best_path_cost * max_path_cost_factor).
    multipath: Whether to consider multiple same-cost expansions in SPF.
    excluded_edges: Set of edge IDs to exclude globally.
    excluded_nodes: Set of node IDs to exclude globally.

Yields:
    (costs, pred) for each discovered path from src_node to dst_node, in ascending
    order of cost.

### spf(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, edge_select: ngraph.lib.algorithms.base.EdgeSelect = <EdgeSelect.ALL_MIN_COST: 1>, edge_select_func: Optional[Callable[[ngraph.lib.graph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Set[Hashable], Set[Hashable]], Tuple[Union[int, float], List[Hashable]]]] = None, multipath: bool = True, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None) -> Tuple[Dict[Hashable, Union[int, float]], Dict[Hashable, Dict[Hashable, List[Hashable]]]]

Compute shortest paths (cost-based) from a source node using a Dijkstra-like method.

By default, uses EdgeSelect.ALL_MIN_COST. If multipath=True, multiple equal-cost
paths to the same node will be recorded in the predecessor structure. If no
excluded edges/nodes are given and edge_select is one of the specialized
(ALL_MIN_COST or ALL_MIN_COST_WITH_CAP_REMAINING), it uses a fast specialized
routine.

Args:
    graph: The directed graph (StrictMultiDiGraph).
    src_node: The source node from which to compute shortest paths.
    edge_select: The edge selection strategy. Defaults to ALL_MIN_COST.
    edge_select_func: If provided, overrides the default edge selection function.
        Must return (cost, list_of_edges) for the given node->neighbor adjacency.
    multipath: Whether to record multiple same-cost paths.
    excluded_edges: A set of edge IDs to ignore in the graph.
    excluded_nodes: A set of node IDs to ignore in the graph.

Returns:
    A tuple of (costs, pred):
      - costs: Maps each reachable node to its minimal cost from src_node.
      - pred: For each reachable node, a dict of predecessor -> list of edges
        from that predecessor to the node. Multiple predecessors are possible
        if multipath=True.

Raises:
    KeyError: If src_node does not exist in graph.

---

## ngraph.lib.algorithms.types

Types and data structures for algorithm analytics.

### FlowSummary

Summary of max-flow computation results with detailed analytics.

This immutable data structure provides comprehensive information about
the flow solution, including edge flows, residual capacities, and
min-cut analysis.

Attributes:
    total_flow: The maximum flow value achieved.
    edge_flow: Flow amount on each edge, indexed by (src, dst, key).
    residual_cap: Remaining capacity on each edge after flow placement.
    reachable: Set of nodes reachable from source in residual graph.
    min_cut: List of saturated edges that form the minimum cut.

**Attributes:**

- `total_flow` (float)
- `edge_flow` (Dict[Edge, float])
- `residual_cap` (Dict[Edge, float])
- `reachable` (Set[str])
- `min_cut` (List[Edge])

---

## ngraph.workflow.base

### WorkflowStep

Base class for all workflow steps.

**Attributes:**

- `name` (str)

**Methods:**

- `run(self, scenario: 'Scenario') -> 'None'`
  - Execute the workflow step logic.

### register_workflow_step(step_type: 'str')

A decorator that registers a WorkflowStep subclass under `step_type`.

---

## ngraph.workflow.build_graph

### BuildGraph

A workflow step that builds a StrictMultiDiGraph from scenario.network.

**Attributes:**

- `name` (str)

**Methods:**

- `run(self, scenario: 'Scenario') -> 'None'`
  - Execute the workflow step logic.

---

## ngraph.workflow.capacity_envelope_analysis

### CapacityEnvelopeAnalysis

A workflow step that samples maximum capacity between node groups across random failures.

Performs Monte-Carlo analysis by repeatedly applying failures and measuring capacity
to build statistical envelopes of network resilience.

Attributes:
    source_path: Regex pattern to select source node groups.
    sink_path: Regex pattern to select sink node groups.
    mode: "combine" or "pairwise" flow analysis mode (default: "combine").
    failure_policy: Name of failure policy in scenario.failure_policy_set (optional).
    iterations: Number of Monte-Carlo trials (default: 1).
    parallelism: Number of parallel worker processes (default: 1).
    shortest_path: If True, use shortest paths only (default: False).
    flow_placement: Flow placement strategy (default: PROPORTIONAL).
    seed: Optional seed for deterministic results (for debugging).

**Attributes:**

- `name` (str)
- `source_path` (str)
- `sink_path` (str)
- `mode` (str) = combine
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int) = 1
- `shortest_path` (bool) = False
- `flow_placement` (FlowPlacement) = 1
- `seed` (int | None)

**Methods:**

- `run(self, scenario: "'Scenario'") -> 'None'`
  - Execute the capacity envelope analysis workflow step.

---

## ngraph.workflow.capacity_probe

### CapacityProbe

A workflow step that probes capacity (max flow) between selected groups of nodes.

Attributes:
    source_path (str): A regex pattern to select source node groups.
    sink_path (str): A regex pattern to select sink node groups.
    mode (str): "combine" or "pairwise" (defaults to "combine").
        - "combine": All matched sources form one super-source; all matched sinks form one super-sink.
        - "pairwise": Compute flow for each (source_group, sink_group).
    probe_reverse (bool): If True, also compute flow in the reverse direction (sink→source).
    shortest_path (bool): If True, only use shortest paths when computing flow.
    flow_placement (FlowPlacement): Handling strategy for parallel equal cost paths (default PROPORTIONAL).

**Attributes:**

- `name` (str)
- `source_path` (str)
- `sink_path` (str)
- `mode` (str) = combine
- `probe_reverse` (bool) = False
- `shortest_path` (bool) = False
- `flow_placement` (FlowPlacement) = 1

**Methods:**

- `run(self, scenario: 'Scenario') -> 'None'`
  - Executes the capacity probe by computing max flow between node groups

---

## ngraph.transform.base

### NetworkTransform

Stateless mutator applied to a :class:`ngraph.scenario.Scenario`.

Subclasses must override :meth:`apply`.

**Methods:**

- `apply(self, scenario: 'Scenario') -> 'None'`
  - Modify *scenario.network* in-place.
- `create(step_type: 'str', **kwargs: 'Any') -> 'Self'`
  - Instantiate a registered transform by *step_type*.

### register_transform(name: 'str') -> 'Any'

Class decorator that registers a concrete :class:`NetworkTransform` and
auto-wraps it as a :class:`WorkflowStep`.

The same *name* is used for both the transform factory and the workflow
``step_type`` in YAML.

Raises:
    ValueError: If *name* is already registered.

---

## ngraph.transform.distribute_external

### DistributeExternalConnectivity

Attach (or create) remote nodes and link them to attachment stripes.

Args:
    remote_locations: Iterable of node names, e.g. ``["den", "sea"]``.
    attachment_path: Regex matching nodes that accept the links.
    stripe_width: Number of attachment nodes per stripe (≥ 1).
    link_count: Number of links per remote node (default ``1``).
    capacity: Per-link capacity.
    cost: Per-link cost metric.
    remote_prefix: Prefix used when creating remote node names (default ``""``).

**Methods:**

- `apply(self, scenario: ngraph.scenario.Scenario) -> None`
  - Modify *scenario.network* in-place.
- `create(step_type: 'str', **kwargs: 'Any') -> 'Self'`
  - Instantiate a registered transform by *step_type*.

---

## ngraph.transform.enable_nodes

### EnableNodesTransform

Enable *count* disabled nodes that match *path*.

Ordering is configurable; default is lexical by node name.

**Methods:**

- `apply(self, scenario: 'Scenario') -> 'None'`
  - Modify *scenario.network* in-place.
- `create(step_type: 'str', **kwargs: 'Any') -> 'Self'`
  - Instantiate a registered transform by *step_type*.

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
