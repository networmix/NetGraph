# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see **[api.md](api.md)**.

> **📋 Documentation Types:**

> - **[Main API Guide (api.md)](api.md)** - Curated examples and usage patterns
> - **This Document (api-full.md)** - Complete auto-generated reference
> - **[CLI Reference](cli.md)** - Command-line interface
> - **[DSL Reference](dsl.md)** - YAML syntax guide

**Generated from source code on:** June 08, 2025 at 00:33 UTC

---

## ngraph.scenario

### Scenario

Represents a complete scenario for building and executing network workflows.

This scenario includes:
  - A network (nodes/links), constructed via blueprint expansion.
  - A failure policy (one or more rules).
  - A set of traffic demands.
  - A list of workflow steps to execute.
  - A results container for storing outputs.
  - A components_library for hardware/optics definitions.

Typical usage example:

    scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
    scenario.run()
    # Inspect scenario.results

**Attributes:**

- `network` (Network)
- `failure_policy` (Optional[FailurePolicy])
- `traffic_demands` (List[TrafficDemand])
- `workflow` (List[WorkflowStep])
- `results` (Results) = Results(_store={})
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})

**Methods:**

- `from_yaml(yaml_str: 'str', default_components: 'Optional[ComponentsLibrary]' = None) -> 'Scenario'`
  - Constructs a Scenario from a YAML string, optionally merging
- `run(self) -> 'None'`
  - Executes the scenario's workflow steps in order.

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
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'`
  - Select and group nodes whose names match a given regular expression.
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

## ngraph.failure_manager

### FailureManager

Applies FailurePolicy to a Network, runs traffic placement, and (optionally)
repeats multiple times for Monte Carlo experiments.

Attributes:
    network (Network): The underlying network to mutate (enable/disable nodes/links).
    traffic_demands (List[TrafficDemand]): List of demands to place after failures.
    failure_policy (Optional[FailurePolicy]): The policy describing what fails.
    default_flow_policy_config: The default flow policy for any demands lacking one.

**Methods:**

- `apply_failures(self) -> 'None'`
  - Apply the current failure_policy to self.network (in-place).
- `run_monte_carlo_failures(self, iterations: 'int', parallelism: 'int' = 1) -> 'Dict[str, Any]'`
  - Repeatedly applies (randomized) failures to the network and accumulates
- `run_single_failure_scenario(self) -> 'List[TrafficResult]'`
  - Applies failures to the network, places the demands, and returns per-demand results.

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
    traffic_demands (List[TrafficDemand]): The scenario-level demands.
    default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
        a TrafficDemand does not specify one.
    graph (StrictMultiDiGraph): Active graph built from the network.
    demands (List[Demand]): All expanded demands from traffic_demands.
    _td_to_demands (Dict[str, List[Demand]]): Internal mapping from
        TrafficDemand.id to its expanded Demand objects.

**Attributes:**

- `network` (Network)
- `traffic_demands` (List) = []
- `default_flow_policy_config` (FlowPolicyConfig) = 1
- `graph` (Optional)
- `demands` (List) = []
- `_td_to_demands` (Dict) = {}

**Methods:**

- `build_graph(self, add_reverse: bool = True) -> None`
  - Builds or rebuilds the internal StrictMultiDiGraph from self.network.
- `expand_demands(self) -> None`
  - Converts each TrafficDemand in self.traffic_demands into one or more
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

## ngraph.lib.algorithms.max_flow

### calc_max_flow(graph: ngraph.lib.graph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, flow_placement: ngraph.lib.algorithms.base.FlowPlacement = <FlowPlacement.PROPORTIONAL: 1>, shortest_path: bool = False, reset_flow_graph: bool = False, capacity_attr: str = 'capacity', flow_attr: str = 'flow', flows_attr: str = 'flows', copy_graph: bool = True) -> float

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
    float:
        The total flow placed between ``src_node`` and ``dst_node``. If ``shortest_path=True``,
        this is just the flow from a single augmentation.

Notes:
    - For large graphs or performance-critical scenarios, consider specialized max-flow
      algorithms (e.g., Dinic, Edmond-Karp) for better scaling.

Examples:
    >>> g = StrictMultiDiGraph()
    >>> g.add_node('A')
    >>> g.add_node('B')
    >>> g.add_node('C')
    >>> _ = g.add_edge('A', 'B', capacity=10.0, flow=0.0, flows={})
    >>> _ = g.add_edge('B', 'C', capacity=5.0, flow=0.0, flows={})
    >>> max_flow_value = calc_max_flow(g, 'A', 'C')
    >>> print(max_flow_value)
    5.0

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

## ngraph.transform.distribute_external

Distribute external (remote) nodes across stripes of attachment nodes.

The transform is generic:

* ``attachment_path`` - regex that selects any enabled nodes to serve as
  attachment points.
* ``remote_locations`` - short names; each is mapped deterministically to
  a stripe of attachments.
* ``stripe_width`` - number of attachment nodes per stripe.
* ``capacity`` / ``cost`` - link attributes for created edges.

Idempotent: re-running the transform will not duplicate nodes or links.

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
