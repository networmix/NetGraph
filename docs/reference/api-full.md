<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: August 09, 2025 at 03:28 UTC

Modules auto-discovered: 59

---

## ngraph.cli

Command-line interface for NetGraph.

### main(argv: 'Optional[List[str]]' = None) -> 'None'

Entry point for the ``ngraph`` command.

Args:
    argv: Optional list of command-line arguments. If ``None``, ``sys.argv``
        is used.

---

## ngraph.components

Component and ComponentsLibrary classes for hardware cost modeling.

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

- `as_dict(self, include_children: 'bool' = True) -> 'Dict[str, Any]'` - Returns a dictionary containing all properties of this component.
- `total_capacity(self) -> 'float'` - Computes the total (recursive) capacity of this component,
- `total_cost(self) -> 'float'` - Computes the total (recursive) cost of this component, including children,
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

---

## ngraph.config

Configuration classes for NetGraph components.

### TrafficManagerConfig

Configuration for traffic demand placement estimation.

**Attributes:**

- `default_rounds` (int) = 5
- `min_rounds` (int) = 5
- `max_rounds` (int) = 100
- `ratio_base` (int) = 5
- `ratio_multiplier` (int) = 5

**Methods:**

- `estimate_rounds(self, demand_capacity_ratio: float) -> int` - Calculate placement rounds based on demand to capacity ratio.

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

### NetworkExplorer

Provides hierarchical exploration of a Network, computing statistics in two modes:
'all' (ignores disabled) and 'active' (only enabled).

**Methods:**

- `explore_network(network: 'Network', components_library: 'Optional[ComponentsLibrary]' = None) -> 'NetworkExplorer'` - Build a NetworkExplorer, constructing a tree plus 'all' and 'active' stats.
- `print_tree(self, node: 'Optional[TreeNode]' = None, indent: 'int' = 0, max_depth: 'Optional[int]' = None, skip_leaves: 'bool' = False, detailed: 'bool' = False, include_disabled: 'bool' = True) -> 'None'` - Print the hierarchy from 'node' down (default: root).

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

## ngraph.report

Standalone report generation for NetGraph analysis results.

Generates Jupyter notebooks and HTML reports from results.json files.
Separate from workflow execution to allow independent report generation.

### ReportGenerator

Generate analysis reports from NetGraph results files.

Creates Jupyter notebooks with analysis code and can optionally export to HTML.
Uses the analysis registry to determine which analysis modules to run for each workflow step.

**Methods:**

- `generate_html_report(self, notebook_path: 'Path' = PosixPath('analysis.ipynb'), html_path: 'Path' = PosixPath('analysis_report.html'), include_code: 'bool' = False) -> 'Path'` - Generate HTML report from notebook.
- `generate_notebook(self, output_path: 'Path' = PosixPath('analysis.ipynb')) -> 'Path'` - Generate Jupyter notebook with analysis code.
- `load_results(self) -> 'None'` - Load results from JSON file.

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
- `results` (Results) = Results(_store={}, _metadata={})
- `components_library` (ComponentsLibrary) = ComponentsLibrary(components={})
- `seed` (Optional[int])

**Methods:**

- `from_yaml(yaml_str: 'str', default_components: 'Optional[ComponentsLibrary]' = None) -> 'Scenario'` - Constructs a Scenario from a YAML string, optionally merging
- `run(self) -> 'None'` - Executes the scenario's workflow steps in order.

---

## ngraph.seed_manager

Deterministic seed derivation to avoid global random.seed() order dependencies.

### SeedManager

Manages deterministic seed derivation for isolated component reproducibility.

Global random.seed() creates order dependencies and component interference.
SeedManager derives unique seeds per component from a master seed using SHA-256,
ensuring reproducible results regardless of execution order or parallelism.

Usage:
    seed_mgr = SeedManager(42)
    failure_seed = seed_mgr.derive_seed("failure_policy", "default")
    analysis_seed = seed_mgr.derive_seed("workflow", "capacity_analysis", 0)

**Methods:**

- `create_random_state(self, *components: 'Any') -> 'random.Random'` - Create a new Random instance with derived seed.
- `derive_seed(self, *components: 'Any') -> 'Optional[int]'` - Derive a deterministic seed from master seed and component identifiers.
- `seed_global_random(self, *components: 'Any') -> 'None'` - Seed the global random module with derived seed.

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

## ngraph.graph.convert

Graph conversion utilities between StrictMultiDiGraph and NetworkX graphs.

Functions in this module consolidate or expand multi-edges and can preserve
original edge data for reversion through a special ``_uv_edges`` attribute.

### from_digraph(nx_graph: networkx.classes.digraph.DiGraph) -> ngraph.graph.strict_multidigraph.StrictMultiDiGraph

Convert a revertible NetworkX DiGraph to a StrictMultiDiGraph.

This function reconstructs the original StrictMultiDiGraph by restoring
multi-edge information from the '_uv_edges' attribute of each edge.

Args:
    nx_graph: A revertible NetworkX DiGraph with ``_uv_edges`` attributes.

Returns:
    A StrictMultiDiGraph reconstructed from the input DiGraph.

### from_graph(nx_graph: networkx.classes.graph.Graph) -> ngraph.graph.strict_multidigraph.StrictMultiDiGraph

Convert a revertible NetworkX Graph to a StrictMultiDiGraph.

Restores the original multi-edge structure from the '_uv_edges' attribute stored
in each consolidated edge.

Args:
    nx_graph: A revertible NetworkX Graph with ``_uv_edges`` attributes.

Returns:
    A StrictMultiDiGraph reconstructed from the input Graph.

### to_digraph(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, edge_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, dict], dict]] = None, revertible: bool = True) -> networkx.classes.digraph.DiGraph

Convert a StrictMultiDiGraph to a NetworkX DiGraph.

This function consolidates multi-edges between nodes into a single edge.
Optionally, a custom edge function can be provided to compute edge attributes.
If `revertible` is True, the original multi-edge data is stored in the '_uv_edges'
attribute of each consolidated edge, allowing for later reversion.

Args:
    graph: The StrictMultiDiGraph to convert.
    edge_func: Optional function to compute consolidated edge attributes.
        The callable receives ``(graph, u, v, edges)`` and returns a dict.
    revertible: If True, store the original multi-edge data for reversion.

Returns:
    A NetworkX DiGraph representing the input graph.

### to_graph(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, edge_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, dict], dict]] = None, revertible: bool = True) -> networkx.classes.graph.Graph

Convert a StrictMultiDiGraph to a NetworkX Graph.

This function works similarly to `to_digraph` but returns an undirected graph.

Args:
    graph: The StrictMultiDiGraph to convert.
    edge_func: Optional function to compute consolidated edge attributes.
    revertible: If True, store the original multi-edge data for reversion.

Returns:
    A NetworkX Graph representing the input graph.

---

## ngraph.graph.io

Graph serialization functions for node-link and edge-list formats.

### edgelist_to_graph(lines: 'Iterable[str]', columns: 'List[str]', separator: 'str' = ' ', graph: 'Optional[StrictMultiDiGraph]' = None, source: 'str' = 'src', target: 'str' = 'dst', key: 'str' = 'key') -> 'StrictMultiDiGraph'

Build or update a StrictMultiDiGraph from an edge list.

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

Raises:
    RuntimeError: If a line does not match the expected number of columns.

### graph_to_edgelist(graph: 'StrictMultiDiGraph', columns: 'Optional[List[str]]' = None, separator: 'str' = ' ', source_col: 'str' = 'src', target_col: 'str' = 'dst', key_col: 'str' = 'key') -> 'List[str]'

Convert a StrictMultiDiGraph into an edge-list text representation.

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

Convert a StrictMultiDiGraph into a node-link dict representation.

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

Reconstruct a StrictMultiDiGraph from its node-link dict representation.

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

Raises:
    KeyError: If required keys (e.g., "id" or "attr" on nodes) are missing.

---

## ngraph.graph.strict_multidigraph

Strict multi-directed graph with validation and convenience APIs.

`StrictMultiDiGraph` extends `networkx.MultiDiGraph` to enforce explicit node
management, unique edge identifiers, and predictable error handling. It exposes
helpers to access nodes/edges as dictionaries and to serialize in node-link
format via `to_dict()`.

### StrictMultiDiGraph

A custom multi-directed graph with strict rules and unique edge IDs.

This class enforces:

- No automatic creation of missing nodes when adding an edge.
- No duplicate nodes (raises ValueError on duplicates).
- No duplicate edges by key (raises ValueError on duplicates).
- Removing non-existent nodes or edges raises ValueError.
- Each edge key must be unique; by default, a Base64-UUID is generated

    if none is provided.

- ``copy()`` can perform a pickle-based deep copy that may be faster

    than the NetworkX default.

Inherits from:
    networkx.MultiDiGraph

**Methods:**

- `add_edge(self, u_for_edge: 'NodeID', v_for_edge: 'NodeID', key: 'Optional[EdgeID]' = None, **attr: 'Any') -> 'EdgeID'` - Add a directed edge from u_for_edge to v_for_edge.
- `add_edges_from(self, ebunch_to_add, **attr)` - Add all the edges in ebunch_to_add.
- `add_node(self, node_for_adding: 'NodeID', **attr: 'Any') -> 'None'` - Add a single node, disallowing duplicates.
- `add_nodes_from(self, nodes_for_adding, **attr)` - Add multiple nodes.
- `add_weighted_edges_from(self, ebunch_to_add, weight='weight', **attr)` - Add weighted edges in `ebunch_to_add` with specified weight attr
- `adjacency(self)` - Returns an iterator over (node, adjacency dict) tuples for all nodes.
- `clear(self)` - Remove all nodes and edges from the graph.
- `clear_edges(self)` - Remove all edges from the graph without altering nodes.
- `copy(self, as_view: 'bool' = False, pickle: 'bool' = True) -> 'StrictMultiDiGraph'` - Create a copy of this graph.
- `edge_subgraph(self, edges)` - Returns the subgraph induced by the specified edges.
- `edges_between(self, u: 'NodeID', v: 'NodeID') -> 'List[EdgeID]'` - List all edge keys from node u to node v.
- `get_edge_attr(self, key: 'EdgeID') -> 'AttrDict'` - Retrieve the attribute dictionary of a specific edge.
- `get_edge_data(self, u, v, key=None, default=None)` - Returns the attribute dictionary associated with edge (u, v,
- `get_edges(self) -> 'Dict[EdgeID, EdgeTuple]'` - Retrieve a dictionary of all edges by their keys.
- `get_nodes(self) -> 'Dict[NodeID, AttrDict]'` - Retrieve all nodes and their attributes as a dictionary.
- `has_edge(self, u, v, key=None)` - Returns True if the graph has an edge between nodes u and v.
- `has_edge_by_id(self, key: 'EdgeID') -> 'bool'` - Check whether an edge with the given key exists.
- `has_node(self, n)` - Returns True if the graph contains the node n.
- `has_predecessor(self, u, v)` - Returns True if node u has predecessor v.
- `has_successor(self, u, v)` - Returns True if node u has successor v.
- `is_directed(self)` - Returns True if graph is directed, False otherwise.
- `is_multigraph(self)` - Returns True if graph is a multigraph, False otherwise.
- `nbunch_iter(self, nbunch=None)` - Returns an iterator over nodes contained in nbunch that are
- `neighbors(self, n)` - Returns an iterator over successor nodes of n.
- `new_edge_key(self, u, v)` - Returns an unused key for edges between nodes `u` and `v`.
- `number_of_edges(self, u=None, v=None)` - Returns the number of edges between two nodes.
- `number_of_nodes(self)` - Returns the number of nodes in the graph.
- `order(self)` - Returns the number of nodes in the graph.
- `predecessors(self, n)` - Returns an iterator over predecessor nodes of n.
- `remove_edge(self, u: 'NodeID', v: 'NodeID', key: 'Optional[EdgeID]' = None) -> 'None'` - Remove an edge (or edges) between nodes u and v.
- `remove_edge_by_id(self, key: 'EdgeID') -> 'None'` - Remove a directed edge by its unique key.
- `remove_edges_from(self, ebunch)` - Remove all edges specified in ebunch.
- `remove_node(self, n: 'NodeID') -> 'None'` - Remove a single node and all incident edges.
- `remove_nodes_from(self, nodes)` - Remove multiple nodes.
- `reverse(self, copy=True)` - Returns the reverse of the graph.
- `size(self, weight=None)` - Returns the number of edges or total of all edge weights.
- `subgraph(self, nodes)` - Returns a SubGraph view of the subgraph induced on `nodes`.
- `successors(self, n)` - Returns an iterator over successor nodes of n.
- `to_dict(self) -> 'Dict[str, Any]'` - Convert the graph to a dictionary representation suitable for JSON serialization.
- `to_directed(self, as_view=False)` - Returns a directed representation of the graph.
- `to_directed_class(self)` - Returns the class to use for empty directed copies.
- `to_undirected(self, reciprocal=False, as_view=False)` - Returns an undirected representation of the digraph.
- `to_undirected_class(self)` - Returns the class to use for empty undirected copies.
- `update(self, edges=None, nodes=None)` - Update the graph using nodes/edges/graphs as input.
- `update_edge_attr(self, key: 'EdgeID', **attr: 'Any') -> 'None'` - Update attributes on an existing edge by key.

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
nodes/links during analysis (e.g., failure simulation), use NetworkView instead
of modifying the Network's disabled states.

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
- `k_shortest_paths(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'pairwise', *, max_k: 'int' = 3, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[_NGPath]]'` - Return up to K shortest paths per group pair.
- `max_flow(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], float]'` - Compute maximum flow between node groups in this network.
- `max_flow_detailed(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]'` - Compute maximum flow with both analytics summary and graph.
- `max_flow_with_graph(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]'` - Compute maximum flow and return flow-assigned graphs.
- `max_flow_with_summary(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, FlowSummary]]'` - Compute maximum flow and return per-pair analytics summary.
- `saturated_edges(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', tolerance: 'float' = 1e-10, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], List[Tuple[str, str, str]]]'` - Identify saturated edges in max flow solutions.
- `select_node_groups_by_path(self, path: 'str') -> 'Dict[str, List[Node]]'` - Select and group nodes by regex on name or by attribute directive.
- `sensitivity_analysis(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', change_amount: 'float' = 1.0, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]'` - Perform sensitivity analysis for capacity changes.
- `shortest_path_costs(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine') -> 'Dict[Tuple[str, str], float]'` - Return minimal path costs between node groups in this network.
- `shortest_paths(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', *, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[_NGPath]]'` - Return concrete shortest path(s) between selected node groups.
- `to_strict_multidigraph(self, add_reverse: 'bool' = True) -> 'StrictMultiDiGraph'` - Create a StrictMultiDiGraph representation of this Network.

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

## ngraph.model.view

Read-only view of a ``Network`` with temporary exclusions.

This module defines a view over ``Network`` objects that can exclude nodes and
links for analysis without mutating the base network. It supports what-if
analysis, including failure simulations.

### NetworkView

Read-only overlay that hides selected nodes/links from a base Network.

NetworkView provides filtered access to a Network where both scenario-disabled
elements (Node.disabled, Link.disabled) and analysis-excluded elements are
hidden from algorithms. This enables failure simulation and what-if analysis
without mutating the base Network.

Multiple NetworkView instances can safely operate on the same base Network
concurrently, each with different exclusion sets.

Example:
    ```python
    # Create view excluding specific nodes for failure analysis
    view = NetworkView.from_excluded_sets(
        base_network,
        excluded_nodes=["node1", "node2"],
        excluded_links=["link1"]
    )

    # Run analysis on filtered topology
    flows = view.max_flow("source.*", "sink.*")
    ```

Attributes:
    _base: The underlying Network object.
    _excluded_nodes: Frozen set of node names to exclude from analysis.
    _excluded_links: Frozen set of link IDs to exclude from analysis.

**Attributes:**

- `_base` ('Network')
- `_excluded_nodes` (frozenset[str]) = frozenset()
- `_excluded_links` (frozenset[str]) = frozenset()

**Methods:**

- `from_excluded_sets(base: "'Network'", excluded_nodes: 'Iterable[str]' = (), excluded_links: 'Iterable[str]' = ()) -> "'NetworkView'"` - Create a NetworkView with specified exclusions.
- `is_link_hidden(self, link_id: 'str') -> 'bool'` - Check if a link is hidden in this view.
- `is_node_hidden(self, name: 'str') -> 'bool'` - Check if a node is hidden in this view.
- `k_shortest_paths(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'pairwise', *, max_k: 'int' = 3, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[_NGPath]]'` - Return up to K shortest paths per group pair.
- `max_flow(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> 'Dict[Tuple[str, str], float]'` - Compute maximum flow between node groups in this view.
- `max_flow_detailed(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> "Dict[Tuple[str, str], Tuple[float, 'FlowSummary', 'StrictMultiDiGraph']]"` - Compute maximum flow with complete analytics and graph.
- `max_flow_with_graph(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> "Dict[Tuple[str, str], Tuple[float, 'StrictMultiDiGraph']]"` - Compute maximum flow and return flow-assigned graph.
- `max_flow_with_summary(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> "Dict[Tuple[str, str], Tuple[float, 'FlowSummary']]"` - Compute maximum flow with detailed analytics summary.
- `saturated_edges(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', tolerance: 'float' = 1e-10, shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> 'Dict[Tuple[str, str], List[Tuple[str, str, str]]]'` - Identify saturated edges in max flow solutions.
- `select_node_groups_by_path(self, path: 'str') -> "Dict[str, List['Node']]"` - Select and group visible nodes by regex or attribute directive.
- `sensitivity_analysis(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', change_amount: 'float' = 1.0, shortest_path: 'bool' = False, flow_placement: "Optional['FlowPlacement']" = None) -> 'Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]'` - Perform sensitivity analysis on capacity changes.
- `shortest_path_costs(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine') -> 'Dict[Tuple[str, str], float]'` - Return minimal path costs between node groups in this view.
- `shortest_paths(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', *, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[_NGPath]]'` - Return concrete shortest path(s) between selected node groups.
- `to_strict_multidigraph(self, add_reverse: 'bool' = True) -> "'StrictMultiDiGraph'"` - Create a StrictMultiDiGraph representation of this view.

---

## ngraph.algorithms.base

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

## ngraph.algorithms.capacity

Capacity calculation algorithms for network analysis.

This module computes feasible flow given a predecessor DAG from a shortest-path
routine and supports two placement strategies: proportional and equal-balanced
in reversed orientation. Functions follow a Dinic-like blocking-flow approach
for proportional placement.

### calc_graph_capacity(flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', pred: 'Dict[NodeID, Dict[NodeID, List[EdgeID]]]', flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, capacity_attr: 'str' = 'capacity', flow_attr: 'str' = 'flow') -> 'Tuple[float, Dict[NodeID, Dict[NodeID, float]]]'

Calculate feasible flow and flow fractions between two nodes.

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
    tuple[float, dict[NodeID, dict[NodeID, float]]]:

- Total feasible flow from ``src_node`` to ``dst_node``.
- Normalized flow fractions in forward orientation (``[u][v]`` >= 0).

Raises:
    ValueError: If src_node or dst_node is not in the graph, or the flow_placement
                is unsupported.

---

## ngraph.algorithms.edge_select

Edge selection algorithms for routing.

Provides selection routines used by SPF to choose candidate edges between
neighbors according to cost and capacity constraints.

### edge_select_fabric(edge_select: ngraph.algorithms.base.EdgeSelect, select_value: Optional[Any] = None, edge_select_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Optional[Set[Hashable]], Optional[Set[Hashable]]], Tuple[Union[int, float], List[Hashable]]]] = None, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None, cost_attr: str = 'cost', capacity_attr: str = 'capacity', flow_attr: str = 'flow') -> Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Optional[Set[Hashable]], Optional[Set[Hashable]]], Tuple[Union[int, float], List[Hashable]]]

Create an edge-selection callable for SPF.

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
    Callable: Function with signature
        ``(graph, src, dst, edges_dict, excluded_edges, excluded_nodes) ->
        (selected_cost, [edge_ids])``.

---

## ngraph.algorithms.flow_init

Flow graph initialization utilities.

Ensures nodes and edges carry aggregate (``flow_attr``) and per-flow
(``flows_attr``) attributes, optionally resetting existing values.

### init_flow_graph(flow_graph: 'StrictMultiDiGraph', flow_attr: 'str' = 'flow', flows_attr: 'str' = 'flows', reset_flow_graph: 'bool' = True) -> 'StrictMultiDiGraph'

Ensure that nodes and edges expose flow-related attributes.

For each node and edge:

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
    StrictMultiDiGraph: The same graph instance after attribute checks.

---

## ngraph.algorithms.max_flow

Maximum-flow computation via iterative shortest-path augmentation.

Implements a practical Edmonds–Karp-like procedure using SPF with capacity
constraints and configurable flow-splitting across equal-cost parallel edges.
Provides helpers for saturated-edge detection and simple sensitivity analysis.

### calc_max_flow(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, return_summary: bool = False, return_graph: bool = False, flow_placement: ngraph.algorithms.base.FlowPlacement = <FlowPlacement.PROPORTIONAL: 1>, shortest_path: bool = False, reset_flow_graph: bool = False, capacity_attr: str = 'capacity', flow_attr: str = 'flow', flows_attr: str = 'flows', copy_graph: bool = True, tolerance: float = 1e-10) -> Union[float, tuple]

Compute max flow between two nodes in a directed multi-graph.

Uses iterative shortest-path augmentation with capacity-aware SPF and
configurable flow placement.

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
    tolerance (float):
        Tolerance for floating-point comparisons when determining saturated edges
        and residual capacity. Defaults to 1e-10.

Returns:
    Union[float, tuple]:

- If neither flag: ``float`` total flow.
- If return_summary only: ``tuple[float, FlowSummary]``.
- If both flags: ``tuple[float, FlowSummary, StrictMultiDiGraph]``.

Notes:

- When using return_summary or return_graph, the return value is a tuple.

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

### run_sensitivity(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, capacity_attr: str = 'capacity', flow_attr: str = 'flow', change_amount: float = 1.0, **kwargs) -> dict[tuple, float]

Simple sensitivity analysis for per-edge capacity changes.

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
    dict[tuple, float]: Flow delta per modified edge.

### saturated_edges(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, *, capacity_attr: str = 'capacity', flow_attr: str = 'flow', tolerance: float = 1e-10, **kwargs) -> list[tuple]

Identify saturated edges in the max-flow solution.

Args:
    graph: The graph to analyze
    src_node: Source node
    dst_node: Destination node
    capacity_attr: Name of capacity attribute
    flow_attr: Name of flow attribute
    tolerance: Tolerance for considering an edge saturated
    **kwargs: Additional arguments passed to calc_max_flow

Returns:
    list[tuple]: Edges ``(u, v, k)`` with residual capacity <= ``tolerance``.

---

## ngraph.algorithms.paths

Path manipulation utilities.

Provides helpers to enumerate realized paths from a predecessor map produced by
SPF/KSP, with optional expansion of parallel edges into distinct paths.

### resolve_to_paths(src_node: 'NodeID', dst_node: 'NodeID', pred: 'Dict[NodeID, Dict[NodeID, List[EdgeID]]]', split_parallel_edges: 'bool' = False) -> 'Iterator[PathTuple]'

Enumerate all paths from a predecessor map.

Args:
    src_node: Source node ID.
    dst_node: Destination node ID.
    pred: Predecessor map from SPF or KSP.
    split_parallel_edges: If True, expand parallel edges into distinct paths.

Yields:
    PathTuple: Sequence of ``(node_id, (edge_ids,))`` pairs from source to dest.

---

## ngraph.algorithms.placement

Flow placement for routing over equal-cost predecessor DAGs.

Places feasible flow on a graph given predecessor relations and a placement
strategy, updating aggregate and per-flow attributes.

### FlowPlacementMeta

Metadata describing how flow was placed on the graph.

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

Place flow from ``src_node`` to ``dst_node`` on ``flow_graph``.

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
    FlowPlacementMeta: Amount placed, remaining amount, and touched nodes/edges.

### remove_flow_from_graph(flow_graph: 'StrictMultiDiGraph', flow_index: 'Optional[Hashable]' = None, flow_attr: 'str' = 'flow', flows_attr: 'str' = 'flows') -> 'None'

Remove one or all flows from the graph.

Args:
    flow_graph: Graph whose edge flow attributes will be modified.
    flow_index: If provided, remove only the specified flow; otherwise remove all.
    flow_attr: Aggregate flow attribute name on edges.
    flows_attr: Per-flow attribute name on edges.

---

## ngraph.algorithms.spf

Shortest-path-first (SPF) algorithms.

Implements Dijkstra-like SPF with pluggable edge-selection policies and a
Yen-like KSP generator. Specialized fast paths exist for common selection
strategies without exclusions.

### ksp(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, dst_node: Hashable, edge_select: ngraph.algorithms.base.EdgeSelect = <EdgeSelect.ALL_MIN_COST: 1>, edge_select_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Set[Hashable], Set[Hashable]], Tuple[Union[int, float], List[Hashable]]]] = None, max_k: Optional[int] = None, max_path_cost: Union[int, float] = inf, max_path_cost_factor: Optional[float] = None, multipath: bool = True, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None) -> Iterator[Tuple[Dict[Hashable, Union[int, float]], Dict[Hashable, Dict[Hashable, List[Hashable]]]]]

Yield up to k shortest paths using a Yen-like algorithm.

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
    Tuple of ``(costs, pred)`` per discovered path in ascending cost order.

### spf(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, edge_select: ngraph.algorithms.base.EdgeSelect = <EdgeSelect.ALL_MIN_COST: 1>, edge_select_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Set[Hashable], Set[Hashable]], Tuple[Union[int, float], List[Hashable]]]] = None, multipath: bool = True, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None) -> Tuple[Dict[Hashable, Union[int, float]], Dict[Hashable, Dict[Hashable, List[Hashable]]]]

Compute shortest paths from a source node.

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
    tuple[dict[NodeID, Cost], dict[NodeID, dict[NodeID, list[EdgeID]]]]:
        Costs and predecessor mapping.

Raises:
    KeyError: If src_node does not exist in graph.

---

## ngraph.algorithms.types

Types and data structures for algorithm analytics.

Defines immutable summary containers and aliases for algorithm outputs.

### FlowSummary

Summary of max-flow computation results.

Captures edge flows, residual capacities, reachable set, and min-cut.

Attributes:
    total_flow: Maximum flow value achieved.
    edge_flow: Flow amount per edge, indexed by ``(src, dst, key)``.
    residual_cap: Remaining capacity per edge after placement.
    reachable: Nodes reachable from source in residual graph.
    min_cut: Saturated edges crossing the s-t cut.
    cost_distribution: Mapping of path cost to flow volume placed at that cost.

**Attributes:**

- `total_flow` (float)
- `edge_flow` (Dict[Edge, float])
- `residual_cap` (Dict[Edge, float])
- `reachable` (Set[str])
- `min_cut` (List[Edge])
- `cost_distribution` (Dict[Cost, float])

---

## ngraph.paths.bundle

Utilities for compact representation of equal-cost path sets.

This module defines ``PathBundle``, a structure that represents one or more
equal-cost paths between two nodes using a predecessor map. It supports
concatenation, containment checks, sub-bundle extraction with cost
recalculation, and enumeration into concrete ``Path`` instances.

### PathBundle

A collection of equal-cost paths between two nodes.

This class encapsulates one or more parallel paths (all of the same cost)
between `src_node` and `dst_node`. The predecessor map `pred` associates
each node with the node(s) from which it can be reached, along with a list
of edge IDs used in that step. The constructor performs a reverse traversal
from `dst_node` to `src_node` to collect all edges, nodes, and store them
in this bundle.

The constructor assumes the predecessor relation forms a DAG between
``src_node`` and ``dst_node``. No cycle detection is performed. If cycles
are present, traversal may not terminate.

**Methods:**

- `add(self, other: 'PathBundle') -> 'PathBundle'` - Concatenate this bundle with another bundle (end-to-start).
- `contains(self, other: 'PathBundle') -> 'bool'` - Check if this bundle's edge set contains all edges of `other`.
- `from_path(path: 'Path', resolve_edges: 'bool' = False, graph: 'Optional[StrictMultiDiGraph]' = None, edge_select: 'Optional[EdgeSelect]' = None, cost_attr: 'str' = 'cost', capacity_attr: 'str' = 'capacity') -> 'PathBundle'` - Construct a PathBundle from a single `Path` object.
- `get_sub_path_bundle(self, new_dst_node: 'NodeID', graph: 'StrictMultiDiGraph', cost_attr: 'str' = 'cost') -> 'PathBundle'` - Create a sub-bundle ending at `new_dst_node` (which must appear in this bundle).
- `is_disjoint_from(self, other: 'PathBundle') -> 'bool'` - Check if this bundle shares no edges with `other`.
- `is_subset_of(self, other: 'PathBundle') -> 'bool'` - Check if this bundle's edge set is contained in `other`'s edge set.
- `resolve_to_paths(self, split_parallel_edges: 'bool' = False) -> 'Iterator[Path]'` - Generate all concrete `Path` objects contained in this PathBundle.

---

## ngraph.paths.path

Lightweight representation of a single routing path.

The ``Path`` dataclass stores a node-and-parallel-edges sequence and a numeric
cost. Cached properties expose derived sequences for nodes and edges, and
helpers provide equality, ordering by cost, and sub-path extraction with cost
recalculation.

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

- `get_sub_path(self, dst_node: 'NodeID', graph: 'StrictMultiDiGraph', cost_attr: 'str' = 'cost') -> 'Path'` - Create a sub-path ending at the specified destination node, recalculating the cost.

---

## ngraph.flows.flow

Flow and FlowIndex classes for traffic flow representation.

### Flow

Represents a fraction of demand routed along a given PathBundle.

In traffic-engineering scenarios, a `Flow` object can model:

- MPLS LSPs/tunnels with explicit paths,
- IP forwarding behavior (with ECMP or UCMP),
- Or anything that follows a specific set of paths.

**Methods:**

- `place_flow(self, flow_graph: 'StrictMultiDiGraph', to_place: 'float', flow_placement: 'FlowPlacement') -> 'Tuple[float, float]'` - Place or update this flow on the graph.
- `remove_flow(self, flow_graph: 'StrictMultiDiGraph') -> 'None'` - Remove this flow from the graph.

### FlowIndex

Unique identifier for a flow.

Attributes:
    src_node: Source node.
    dst_node: Destination node.
    flow_class: Flow class label (hashable).
    flow_id: Monotonic integer id for this flow.

---

## ngraph.flows.policy

FlowPolicy and FlowPolicyConfig classes for traffic routing algorithms.

### FlowPolicy

Create, place, rebalance, and remove flows on a network graph.

Converts a demand into one or more `Flow` objects subject to capacity
constraints and configuration: path selection, edge selection, and flow
placement method.

**Methods:**

- `deep_copy(self) -> 'FlowPolicy'` - Return a deep copy of this policy including flows.
- `place_demand(self, flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', flow_class: 'Hashable', volume: 'float', target_flow_volume: 'Optional[float]' = None, min_flow: 'Optional[float]' = None) -> 'Tuple[float, float]'` - Place demand volume on the graph by splitting or creating flows as needed.
- `rebalance_demand(self, flow_graph: 'StrictMultiDiGraph', src_node: 'NodeID', dst_node: 'NodeID', flow_class: 'Hashable', target_flow_volume: 'float') -> 'Tuple[float, float]'` - Rebalance demand across existing flows towards the target volume per flow.
- `remove_demand(self, flow_graph: 'StrictMultiDiGraph') -> 'None'` - Removes all flows from the network graph without clearing internal state.

### FlowPolicyConfig

Enumerates supported flow policy configurations.

### get_flow_policy(flow_policy_config: 'FlowPolicyConfig') -> 'FlowPolicy'

Create a policy instance from a configuration preset.

Args:
    flow_policy_config: A FlowPolicyConfig enum value specifying the desired policy.

Returns:
    FlowPolicy: Pre-configured policy instance.

Raises:
    ValueError: If an unknown FlowPolicyConfig value is provided.

---

## ngraph.solver.helpers

---

## ngraph.solver.maxflow

Problem-level max-flow API bound to the model layer.

Functions here operate on a model context that provides:

- to_strict_multidigraph(add_reverse: bool = True) -> StrictMultiDiGraph
- select_node_groups_by_path(path: str) -> dict[str, list[Node]]

They accept either a `Network` or a `NetworkView`. The input context is not
mutated. Pseudo source and sink nodes are attached on a working graph when
computing flows between groups.

### max_flow(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], float]'

Compute max flow between groups selected from the context.

Creates a working graph from the context, adds a pseudo source attached to
the selected source nodes and a pseudo sink attached to the selected sink
nodes, then runs the max-flow routine.

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: Aggregation strategy. "combine" considers all sources as one
        group and all sinks as one group. "pairwise" evaluates each
        source-label and sink-label pair separately.
    shortest_path: If True, perform a single augmentation along the first
        shortest path instead of the full max-flow.
    flow_placement: Strategy for splitting flow among equal-cost parallel
        edges.

Returns:
    Dict[Tuple[str, str], float]: Total flow per (source_label, sink_label).

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is not one of {"combine", "pairwise"}.

### max_flow_detailed(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> "Dict[Tuple[str, str], Tuple[float, FlowSummary, 'StrictMultiDiGraph']]"

Compute max flow, return summary and flow graph for each pair.

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise". See ``max_flow``.
    shortest_path: If True, perform only one augmentation step.
    flow_placement: Strategy for splitting among equal-cost parallel edges.

Returns:
    Dict[Tuple[str, str], Tuple[float, FlowSummary, StrictMultiDiGraph]]:
    For each (source_label, sink_label), the total flow, a summary, and the
    flow-assigned graph.

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is invalid.

### max_flow_with_graph(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> "Dict[Tuple[str, str], Tuple[float, 'StrictMultiDiGraph']]"

Compute max flow and return the mutated flow graph for each pair.

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise". See ``max_flow``.
    shortest_path: If True, perform only one augmentation step.
    flow_placement: Strategy for splitting among equal-cost parallel edges.

Returns:
    Dict[Tuple[str, str], Tuple[float, StrictMultiDiGraph]]: For each
    (source_label, sink_label), the total flow and the flow-assigned graph.

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is invalid.

### max_flow_with_summary(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Tuple[float, FlowSummary]]'

Compute max flow and return a summary for each group pair.

The summary includes total flow, per-edge flow, residual capacity,
reachable set from the source in the residual graph, min-cut edges, and a
cost distribution over augmentation steps.

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise". See ``max_flow``.
    shortest_path: If True, perform only one augmentation step.
    flow_placement: Strategy for splitting among equal-cost parallel edges.

Returns:
    Dict[Tuple[str, str], Tuple[float, FlowSummary]]: For each
    (source_label, sink_label), the total flow and the associated summary.

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is invalid.

### saturated_edges(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', tolerance: 'float' = 1e-10, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], List[Tuple[str, str, str]]]'

Identify saturated edges for each selected group pair.

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise". See ``max_flow``.
    tolerance: Residual capacity threshold to consider an edge saturated.
    shortest_path: If True, perform only one augmentation step.
    flow_placement: Strategy for splitting among equal-cost parallel edges.

Returns:
    Dict[Tuple[str, str], list[tuple[str, str, str]]]: For each
    (source_label, sink_label), a list of saturated edges ``(u, v, k)``.

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is invalid.

### sensitivity_analysis(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', change_amount: 'float' = 1.0, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>) -> 'Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]'

Perform a simple sensitivity analysis per saturated edge.

For each saturated edge, test a capacity change of ``change_amount`` and
report the change in total flow. Positive amounts increase capacity; negative
amounts decrease capacity (with lower bound at zero).

Args:
    context: `Network` or `NetworkView` providing selection and graph APIs.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise". See ``max_flow``.
    change_amount: Capacity delta to apply when testing each saturated edge.
    shortest_path: If True, perform only one augmentation step.
    flow_placement: Strategy for splitting among equal-cost parallel edges.

Returns:
    Dict[Tuple[str, str], Dict[Tuple[str, str, str], float]]: For each
    (source_label, sink_label), a mapping from saturated edge ``(u, v, k)``
    to the change in total flow after applying the capacity delta.

Raises:
    ValueError: If no matching sources or sinks are found, or if ``mode``
        is invalid.

---

## ngraph.solver.paths

Shortest-path solver wrappers bound to the model layer.

Expose convenience functions for computing shortest paths between node groups
selected from a ``Network`` or ``NetworkView`` context. Selection semantics
mirror the max-flow wrappers with ``mode`` in {"combine", "pairwise"}.

Functions return minimal costs or concrete ``Path`` objects built from SPF
predecessor maps. Parallel equal-cost edges can be expanded into distinct
paths.

All functions fail fast on invalid selection inputs and do not mutate the
input context.

Note:
    For path queries, overlapping source/sink membership is treated as
    unreachable.

### k_shortest_paths(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'pairwise', max_k: 'int' = 3, edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, max_path_cost: 'float' = inf, max_path_cost_factor: 'Optional[float]' = None, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[Path]]'

Return up to K shortest paths per group pair.

Args:
    context: Network or NetworkView.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "pairwise" (default) or "combine".
    max_k: Max paths per pair.
    edge_select: SPF/KSP edge selection strategy.
    max_path_cost: Absolute cost threshold.
    max_path_cost_factor: Relative threshold versus best path.
    split_parallel_edges: Expand parallel edges into distinct paths when True.

Returns:
    Mapping from (source_label, sink_label) to list of Path (<= max_k).

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

### shortest_path_costs(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>) -> 'Dict[Tuple[str, str], float]'

Return minimal path cost(s) between selected node groups.

Args:
    context: Network or NetworkView.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    edge_select: SPF edge selection strategy.

Returns:
    Mapping from (source_label, sink_label) to minimal cost; ``inf`` if no
    path.

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

### shortest_paths(context: 'Any', source_path: 'str', sink_path: 'str', *, mode: 'str' = 'combine', edge_select: 'EdgeSelect' = <EdgeSelect.ALL_MIN_COST: 1>, split_parallel_edges: 'bool' = False) -> 'Dict[Tuple[str, str], List[Path]]'

Return concrete shortest path(s) between selected node groups.

Args:
    context: Network or NetworkView.
    source_path: Selection expression for source groups.
    sink_path: Selection expression for sink groups.
    mode: "combine" or "pairwise".
    edge_select: SPF edge selection strategy.
    split_parallel_edges: Expand parallel edges into distinct paths when True.

Returns:
    Mapping from (source_label, sink_label) to list of Path. Empty if
    unreachable.

Raises:
    ValueError: If no source nodes match ``source_path``.
    ValueError: If no sink nodes match ``sink_path``.
    ValueError: If ``mode`` is not "combine" or "pairwise".

---

## ngraph.demand.manager.builder

---

## ngraph.demand.manager.expand

---

## ngraph.demand.manager.manager

Traffic demand management and placement.

`TrafficManager` expands `TrafficDemand` specs into concrete `Demand` objects,
builds a working `StrictMultiDiGraph` from a `Network`, and places flows via
per-demand `FlowPolicy` instances.

### TrafficManager

Manage expansion and placement of traffic demands on a `Network`.

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
- Combine all matched sources into a single pseudo-source node, and all

      matched sinks into a single pseudo-sink node (named using the traffic
      demand's `source_path` and `sink_path`). A single Demand is created
      from the pseudo-source to the pseudo-sink, with the full volume.

- 'full_mesh' mode:
- All matched sources form one group, all matched sinks form another group.

      A separate Demand is created for each (src_node, dst_node) pair,
      skipping self-pairs. The total volume is split evenly across the pairs.

The sum of volumes of all expanded Demands for a given TrafficDemand matches
that TrafficDemand's `demand` value (unless no valid node pairs exist, in which
case no demands are created).

Attributes:
    network (Union[Network, NetworkView]): The underlying network or view object.
    traffic_matrix_set (TrafficMatrixSet): Traffic matrices containing demands.
    matrix_name (Optional[str]): Name of specific matrix to use, or None for default.
    default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
        a TrafficDemand does not specify one.
    graph (StrictMultiDiGraph): Active graph built from the network.
    demands (List[Demand]): All expanded demands from the active matrix.
    _td_to_demands (Dict[str, List[Demand]]): Internal mapping from
        TrafficDemand.id to its expanded Demand objects.

**Attributes:**

- `network` (Union[Network, 'NetworkView'])
- `traffic_matrix_set` ('TrafficMatrixSet')
- `matrix_name` (Optional[str])
- `default_flow_policy_config` (FlowPolicyConfig) = 1
- `graph` (Optional[StrictMultiDiGraph])
- `demands` (List[Demand]) = []
- `_td_to_demands` (Dict[str, List[Demand]]) = {}

**Methods:**

- `build_graph(self, add_reverse: 'bool' = True) -> 'None'` - Build or rebuild the internal `StrictMultiDiGraph` from ``network``.
- `expand_demands(self) -> 'None'` - Expand each `TrafficDemand` into one or more `Demand` objects.
- `get_flow_details(self) -> 'Dict[Tuple[int, int], Dict[str, object]]'` - Summarize flows from each demand's policy.
- `get_traffic_results(self, detailed: 'bool' = False) -> 'List[TrafficResult]'` - Return traffic demand summaries.
- `place_all_demands(self, placement_rounds: 'Union[int, str]' = 'auto', reoptimize_after_each_round: 'bool' = False) -> 'float'` - Place all expanded demands in ascending priority order.
- `reset_all_flow_usages(self) -> 'None'` - Remove flow usage for each demand and reset placements to 0.
- `summarize_link_usage(self) -> 'Dict[str, float]'` - Return total flow usage per edge in the graph.

### TrafficResult

Traffic demand result entry.

Attributes:
    priority: Demand priority class (lower value is more critical).
    total_volume: Total traffic volume for this entry.
    placed_volume: Volume actually placed in the flow graph.
    unplaced_volume: Volume not placed (``total_volume - placed_volume``).
    src: Source node or path.
    dst: Destination node or path.

---

## ngraph.demand.manager.schedule

---

## ngraph.demand.spec

Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. It can carry either a concrete `FlowPolicy` instance or a
`FlowPolicyConfig` enum to construct one.

### TrafficDemand

Single traffic demand input.

Attributes:
    source_path: Regex string selecting source nodes.
    sink_path: Regex string selecting sink nodes.
    priority: Priority class for this demand (lower value = higher priority).
    demand: Total demand volume.
    demand_placed: Portion of this demand placed so far.
    flow_policy_config: Policy configuration used to build a `FlowPolicy` if
        ``flow_policy`` is not provided.
    flow_policy: Concrete policy instance. If set, it overrides
        ``flow_policy_config``.
    mode: Expansion mode, e.g. ``"combine"`` or ``"full_mesh"``.
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

## ngraph.failure.manager.aggregate

Aggregation helpers for failure analysis results.

Utilities in this module group and summarize outputs produced by
`FailureManager` runs. Functions are factored here to keep `manager.py`
focused on orchestration. This module intentionally avoids importing heavy
dependencies to keep import cost low in the common path.

---

## ngraph.failure.manager.enumerate

Failure pattern enumeration helpers.

Hosts utilities for generating or iterating over failure patterns for testing
and analysis workflows. These helpers are separate from the Monte Carlo engine
to keep the main manager small and focused.

---

## ngraph.failure.manager.manager

FailureManager for Monte Carlo failure analysis.

Provides the failure analysis engine for NetGraph. Supports parallel
processing, per-worker caching, and failure policy handling for workflow steps
and direct programmatic use.

Performance characteristics:
Time complexity: O(I × A / P), where I is iteration count, A is analysis cost,
and P is parallelism. Worker-local caching reduces repeated work when exclusion
sets repeat across iterations. Network serialization happens once per worker,
not per iteration.

Space complexity: O(V + E + I × R + C), where V and E are node and link counts,
R is result size per iteration, and C is cache size. The per-worker cache is
bounded and evicts in FIFO order after 1000 unique patterns.

Parallelism: For small iteration counts, serial execution avoids IPC overhead.
For larger workloads, parallel execution benefits from worker caching and CPU
utilization. Optimal parallelism is the number of CPU cores for analysis-bound
workloads.

### AnalysisFunction

Protocol for analysis functions used with FailureManager.

Analysis functions should take a NetworkView and any additional
keyword arguments, returning analysis results of any type.

### FailureManager

Failure analysis engine with Monte Carlo capabilities.

This is the component for failure analysis in NetGraph.
Provides parallel processing, worker caching, and failure
policy handling for workflow steps and direct notebook usage.

The FailureManager can execute any analysis function that takes a NetworkView
and returns results, making it generic for different types of
failure analysis (capacity, traffic, connectivity, etc.).

Attributes:
    network: The underlying network (not modified during analysis).
    failure_policy_set: Set of named failure policies.
    policy_name: Name of specific failure policy to use.

**Methods:**

- `compute_exclusions(self, policy: "'FailurePolicy | None'" = None, seed_offset: 'int | None' = None) -> 'tuple[set[str], set[str]]'` - Compute set of nodes and links to exclude for a failure iteration.
- `create_network_view(self, excluded_nodes: 'set[str] | None' = None, excluded_links: 'set[str] | None' = None) -> 'NetworkView'` - Create NetworkView with specified exclusions.
- `get_failure_policy(self) -> "'FailurePolicy | None'"` - Get failure policy for analysis.
- `run_demand_placement_monte_carlo(self, demands_config: 'list[dict[str, Any]] | Any', iterations: 'int' = 100, parallelism: 'int' = 1, placement_rounds: 'int' = 50, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **kwargs) -> 'Any'` - Analyze traffic demand placement success under failures.
- `run_max_flow_monte_carlo(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_summary: 'bool' = False, **kwargs) -> 'Any'` - Analyze maximum flow capacity envelopes between node groups under failures.
- `run_monte_carlo_analysis(self, analysis_func: 'AnalysisFunction', iterations: 'int' = 1, parallelism: 'int' = 1, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **analysis_kwargs) -> 'dict[str, Any]'` - Run Monte Carlo failure analysis with any analysis function.
- `run_sensitivity_monte_carlo(self, source_path: 'str', sink_path: 'str', mode: 'str' = 'combine', iterations: 'int' = 100, parallelism: 'int' = 1, shortest_path: 'bool' = False, flow_placement: 'FlowPlacement | str' = <FlowPlacement.PROPORTIONAL: 1>, baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, **kwargs) -> 'Any'` - Analyze component criticality for flow capacity under failures.
- `run_single_failure_scenario(self, analysis_func: 'AnalysisFunction', **kwargs) -> 'Any'` - Run a single failure scenario for convenience.

---

## ngraph.failure.manager.simulate

Simulation helpers for failure analyses.

Contains small helpers used to drive simulations in tests and examples. The
main orchestration lives in `manager.py`.

---

## ngraph.failure.policy

Failure policy primitives.

Defines `FailureCondition`, `FailureRule`, and `FailurePolicy` for expressing
how nodes, links, and risk groups fail in analyses. Conditions match on
top-level attributes with simple operators; rules select matches using
"all", probabilistic "random" (with `probability`), or fixed-size "choice"
(with `count`). Policies can optionally expand failures by shared risk groups
or by risk-group children.

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
          2) Match them based on rule conditions using 'and' or 'or' logic.
  3) Apply the selection strategy (all, random, or choice).
  4) Collect the union of all failed entities across all rules.
  5) Optionally expand failures by shared-risk groups or sub-risks.

Large-scale performance:

- If you set `use_cache=True`, matched sets for each rule are cached,

    so repeated calls to `apply_failures` can skip re-matching if the
    network hasn't changed. If your network changes between calls,
    you should clear the cache or re-initialize the policy.

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
    use_cache (bool):
        If True, match results for each rule are cached to speed up
        repeated calls. If the network changes, the cached results
        may be stale.
    seed (Optional[int]):
        Seed for reproducible random operations. If None, operations
        will be non-deterministic.

**Attributes:**

- `rules` (List[FailureRule]) = []
- `attrs` (Dict[str, Any]) = {}
- `fail_risk_groups` (bool) = False
- `fail_risk_group_children` (bool) = False
- `use_cache` (bool) = False
- `seed` (Optional[int])
- `_match_cache` (Dict[int, Set[str]]) = {}

**Methods:**

- `apply_failures(self, network_nodes: 'Dict[str, Any]', network_links: 'Dict[str, Any]', network_risk_groups: 'Dict[str, Any] | None' = None, *, seed: 'Optional[int]' = None) -> 'List[str]'` - Identify which entities fail given the defined rules, then optionally
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

---

## ngraph.workflow.analysis.base

Base classes for notebook analysis components.

Defines a simple interface for notebook-oriented analyzers that both compute
results and render them. Concrete analyzers implement `analyze()`,
`display_analysis()`, and `get_description()`.

### AnalysisContext

Context information for analysis execution.

**Attributes:**

- `step_name` (str)
- `results` (Dict)
- `config` (Dict)

### NotebookAnalyzer

Base class for notebook analysis components.

**Methods:**

- `analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]` - Perform the analysis and return results.
- `analyze_and_display(self, results: Dict[str, Any], **kwargs) -> None` - Analyze results and display them in notebook format.
- `display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None` - Display analysis results in notebook format.
- `get_description(self) -> str` - Return a concise description of the analyzer purpose.

---

## ngraph.workflow.analysis.capacity_matrix

Capacity envelope analysis utilities.

This module contains `CapacityMatrixAnalyzer`, responsible for processing capacity
envelope results, computing statistics, and generating notebook visualizations.
Works with both CapacityEnvelopeResults objects and workflow step data.

### CapacityMatrixAnalyzer

Processes capacity envelope data into matrices and flow availability analysis.

Transforms capacity envelope results from CapacityEnvelopeAnalysis workflow steps
or CapacityEnvelopeResults objects into matrices, statistical summaries, and
flow availability distributions. Provides visualization methods for notebook output
including capacity matrices, flow CDFs, and reliability curves.

Can be used in two modes:

1. Workflow mode: analyze() with workflow step results dictionary
2. Direct mode: analyze_results() with CapacityEnvelopeResults object

**Methods:**

- `analyze(self, results: 'Dict[str, Any]', **kwargs) -> 'Dict[str, Any]'` - Analyze capacity envelopes and create matrix visualization.
- `analyze_and_display(self, results: Dict[str, Any], **kwargs) -> None` - Analyze results and display them in notebook format.
- `analyze_and_display_all_steps(self, results: 'Dict[str, Any]') -> 'None'` - Run analyze/display on every step containing capacity_envelopes.
- `analyze_and_display_envelope_results(self, results: "'CapacityEnvelopeResults'", **kwargs) -> 'None'` - Complete analysis and display for CapacityEnvelopeResults object.
- `analyze_and_display_flow_availability(self, results: 'Dict[str, Any]', **kwargs) -> 'None'` - Analyze and display flow availability for a specific step.
- `analyze_and_display_step(self, results: 'Dict[str, Any]', **kwargs) -> 'None'` - Analyze and display results for a specific step.
- `analyze_flow_availability(self, results: 'Dict[str, Any]', **kwargs) -> 'Dict[str, Any]'` - Create CDF/availability distribution from capacity envelope frequencies.
- `analyze_results(self, results: "'CapacityEnvelopeResults'", **kwargs) -> 'Dict[str, Any]'` - Analyze a `CapacityEnvelopeResults` object directly.
- `display_analysis(self, analysis: 'Dict[str, Any]', **kwargs) -> 'None'` - Pretty-print analysis results to the notebook/stdout.
- `display_capacity_distributions(self, results: "'CapacityEnvelopeResults'", flow_key: 'Optional[str]' = None, bins: 'int' = 30) -> 'None'` - Display capacity distribution plots for `CapacityEnvelopeResults`.
- `display_percentile_comparison(self, results: "'CapacityEnvelopeResults'") -> 'None'` - Display percentile comparison plots for `CapacityEnvelopeResults`.
- `get_description(self) -> 'str'` - Return a concise description of the analyzer purpose.

---

## ngraph.workflow.analysis.data_loader

Data loading utilities for notebook analysis.

Provides simple JSON loading with basic validation and structured status output.

### DataLoader

Handles loading and validation of analysis results.

**Methods:**

- `load_results(json_path: Union[str, pathlib._local.Path]) -> Dict[str, Any]` - Load results from a JSON file with error handling.

---

## ngraph.workflow.analysis.package_manager

Package management for notebook analysis components.

Provides light-weight helpers to ensure plotting/display packages are available
in interactive environments and to apply sensible defaults.

### PackageManager

Manage package installation and imports for notebooks.

**Methods:**

- `check_and_install_packages() -> Dict[str, Any]` - Check for required packages and install if missing.
- `setup_environment() -> Dict[str, Any]` - Set up the notebook environment.

---

## ngraph.workflow.analysis.registry

Analysis registry for mapping workflow steps to analysis modules.

This module provides the central registry that defines which analysis modules
should be executed for each workflow step type, eliminating fragile data-based
parsing and creating a clear, maintainable mapping system.

### AnalysisConfig

Configuration for a single analysis module execution.

Attributes:
    analyzer_class: The analyzer class to instantiate.
    method_name: The method to call on the analyzer (default: 'analyze_and_display').
    kwargs: Additional keyword arguments to pass to the method.
    section_title: Title for the notebook section (auto-generated if None).
    enabled: Whether this analysis is enabled (default: True).

**Attributes:**

- `analyzer_class` (Type[NotebookAnalyzer])
- `method_name` (str) = analyze_and_display
- `kwargs` (Dict[str, Any]) = {}
- `section_title` (Optional[str])
- `enabled` (bool) = True

### AnalysisRegistry

Registry mapping workflow step types to their analysis configurations.

The registry defines which analysis modules should run for each workflow step,
providing a clear and maintainable mapping that replaces fragile data parsing.

**Attributes:**

- `_mappings` (Dict[str, List[AnalysisConfig]]) = {}

**Methods:**

- `get_all_step_types(self) -> 'List[str]'` - Return all registered workflow step types.
- `get_analyses(self, step_type: 'str') -> 'List[AnalysisConfig]'` - Get all analysis configurations for a workflow step type.
- `has_analyses(self, step_type: 'str') -> 'bool'` - Return True if any analyses are registered for a workflow step type.
- `register(self, step_type: 'str', analyzer_class: 'Type[NotebookAnalyzer]', method_name: 'str' = 'analyze_and_display', section_title: 'Optional[str]' = None, **kwargs: 'Any') -> 'None'` - Register an analysis module for a workflow step type.

### get_default_registry() -> 'AnalysisRegistry'

Create and return the default analysis registry with standard mappings.

Returns:
    Configured registry with standard workflow step -> analysis mappings.

---

## ngraph.workflow.analysis.summary

Summary analysis for workflow results.

This module contains `SummaryAnalyzer`, which processes workflow step results
to generate high-level summaries, counts step types, and provides overview
statistics for network construction and analysis results.

### SummaryAnalyzer

Generates summary statistics and overviews of workflow results.

Counts and categorizes workflow steps by type (capacity, flow, other),
displays network statistics for graph construction steps, and provides
high-level summaries for analysis overview.

**Methods:**

- `analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]` - Analyze and summarize all results.
- `analyze_and_display(self, results: Dict[str, Any], **kwargs) -> None` - Analyze results and display them in notebook format.
- `analyze_build_graph(self, results: Dict[str, Any], **kwargs) -> None` - Analyze and display graph construction results.
- `analyze_network_stats(self, results: Dict[str, Any], **kwargs) -> None` - Analyze and display network statistics for a specific step.
- `display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None` - Display summary analysis.
- `get_description(self) -> str` - Return a concise description of the analyzer purpose.

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

Converts scenario network definitions into StrictMultiDiGraph structures suitable
for analysis algorithms. No additional parameters required beyond basic workflow step options.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: BuildGraph

        name: "build_network_graph"  # Optional: Custom name for this step
    ```

Results stored in `scenario.results`:

- graph: `StrictMultiDiGraph` object with bidirectional links

### BuildGraph

A workflow step that builds a StrictMultiDiGraph from scenario.network.

This step converts the scenario's network definition into a graph structure
suitable for analysis algorithms. No additional parameters are required.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Scenario') -> 'None'` - Build the network graph and store it in results.

---

## ngraph.workflow.capacity_envelope_analysis

Capacity envelope analysis workflow component.

Monte Carlo analysis of network capacity under random failures using FailureManager.
Generates statistical distributions (envelopes) of maximum flow capacity between
node groups across failure scenarios. Supports parallel processing, baseline analysis,
and configurable failure policies.

This component uses the `FailureManager` convenience method to perform the analysis,
ensuring consistency with the programmatic API while providing workflow integration.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: CapacityEnvelopeAnalysis

        name: "capacity_envelope_monte_carlo"  # Optional: Custom name for this step
        source_path: "^datacenter/.*"          # Regex pattern for source node groups
        sink_path: "^edge/.*"                  # Regex pattern for sink node groups
        mode: "combine"                        # "combine" or "pairwise" flow analysis
        failure_policy: "random_failures"      # Optional: Named failure policy to use
        iterations: 1000                       # Number of Monte-Carlo trials
        parallelism: 4                         # Number of parallel worker processes
        shortest_path: false                   # Use shortest paths only
        flow_placement: "PROPORTIONAL"         # Flow placement strategy
        baseline: true                         # Optional: Run first iteration without failures
        seed: 42                               # Optional: Seed for reproducible results
        store_failure_patterns: false          # Optional: Store failure patterns in results
        include_flow_summary: false            # Optional: Collect detailed flow summary statistics
    ```

Results stored in `scenario.results`:

- capacity_envelopes: Mapping of flow keys to capacity envelope data (serializable)
- failure_pattern_results: Frequency map of failure patterns (if `store_failure_patterns=True`)

### CapacityEnvelopeAnalysis

Capacity envelope analysis workflow step using FailureManager convenience method.

This workflow step uses the FailureManager.run_max_flow_monte_carlo() convenience method
to perform analysis, ensuring consistency with the programmatic API while providing
workflow integration and result storage.

Attributes:
    source_path: Regex pattern for source node groups.
    sink_path: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    failure_policy: Name of failure policy in scenario.failure_policy_set.
    iterations: Number of Monte-Carlo trials.
    parallelism: Number of parallel worker processes.
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    baseline: Whether to run first iteration without failures as baseline.
    seed: Optional seed for reproducible results.
    store_failure_patterns: Whether to store failure patterns in results.
    include_flow_summary: Whether to collect detailed flow summary statistics (cost distribution, min-cut edges).

**Attributes:**

- `name` (str)
- `seed` (int | None)
- `source_path` (str)
- `sink_path` (str)
- `mode` (str) = combine
- `failure_policy` (str | None)
- `iterations` (int) = 1
- `parallelism` (int) = 1
- `shortest_path` (bool) = False
- `flow_placement` (FlowPlacement | str) = 1
- `baseline` (bool) = False
- `store_failure_patterns` (bool) = False
- `include_flow_summary` (bool) = False

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: "'Scenario'") -> 'None'` - Execute capacity envelope analysis using `FailureManager`.

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

Supports optional exclusion simulation using NetworkView without modifying the base network.

Attributes:
    include_disabled: If True, include disabled nodes and links in statistics.
        If False, only consider enabled entities.
    excluded_nodes: Optional list of node names to exclude (temporary exclusion).
    excluded_links: Optional list of link IDs to exclude (temporary exclusion).

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `include_disabled` (bool) = False
- `excluded_nodes` (Iterable[str]) = ()
- `excluded_links` (Iterable[str]) = ()

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Scenario') -> 'None'` - Compute and store network statistics.

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
    Network: The expanded Network object with all nodes and links.

---

## ngraph.dsl.blueprints.parse

Parsing helpers for the network DSL.

This module is reserved for future parsing utilities. The main expansion
entry point is `ngraph.dsl.blueprints.expand.expand_network_dsl`.

---

## ngraph.results.artifacts

Serializable result artifacts for analysis workflows.

This module defines small dataclasses that capture outputs from analyses
and simulations in a JSON-serializable form:

- `TrafficMatrixSet`: named collections of `TrafficDemand` lists
- `PlacementResultSet`: aggregated placement results and statistics
- `FailurePolicySet`: named collections of failure policies
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

**Methods:**

- `to_dict(self) -> 'Dict[str, Any]'` - Convert to dictionary for JSON serialization.

### FailurePolicySet

Named collection of FailurePolicy objects.

This mutable container maps failure policy names to FailurePolicy objects,
allowing management of multiple failure policies for analysis.

Attributes:
    policies: Dictionary mapping failure policy names to FailurePolicy objects.

**Attributes:**

- `policies` (dict[str, 'FailurePolicy']) = {}

**Methods:**

- `add(self, name: 'str', policy: "'FailurePolicy'") -> 'None'` - Add a failure policy to the collection.
- `get_all_policies(self) -> "list['FailurePolicy']"` - Get all failure policies from the collection.
- `get_policy(self, name: 'str') -> "'FailurePolicy'"` - Get a specific failure policy by name.
- `to_dict(self) -> 'dict[str, Any]'` - Convert to dictionary for JSON serialization.

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

- `to_dict(self) -> 'dict[str, Any]'` - Convert to dictionary for JSON serialization.

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

## ngraph.results.results

Generic results store for workflow steps and their metadata.

`Results` organizes arbitrary key-value outputs by workflow step name and
records lightweight `WorkflowStepMetadata` to preserve execution context.
All stored values are kept as-is; objects that implement ``to_dict()`` are
converted when exporting with `Results.to_dict()` for JSON serialization.

### Results

A container for storing arbitrary key-value data that arises during workflow steps.

The data is organized by step name, then by key. Each step also has associated
metadata that describes the workflow step type and execution context.

Example usage:
  results.put("Step1", "total_capacity", 123.45)
  cap = results.get("Step1", "total_capacity")  # returns 123.45
  all_caps = results.get_all("total_capacity")  # might return {"Step1": 123.45, "Step2": 98.76}
  metadata = results.get_step_metadata("Step1")  # returns WorkflowStepMetadata

**Attributes:**

- `_store` (Dict) = {}
- `_metadata` (Dict) = {}

**Methods:**

- `get(self, step_name: str, key: str, default: Any = None) -> Any` - Retrieve the value from (step_name, key). If the key is missing, return `default`.
- `get_all(self, key: str) -> Dict[str, Any]` - Retrieve a dictionary of {step_name: value} for all step_names that contain the specified key.
- `get_all_step_metadata(self) -> Dict[str, ngraph.results.results.WorkflowStepMetadata]` - Get metadata for all workflow steps.
- `get_step_metadata(self, step_name: str) -> Optional[ngraph.results.results.WorkflowStepMetadata]` - Get metadata for a workflow step.
- `get_steps_by_execution_order(self) -> list[str]` - Get step names ordered by their execution order.
- `put(self, step_name: str, key: str, value: Any) -> None` - Store a value under (step_name, key).
- `put_step_metadata(self, step_name: str, step_type: str, execution_order: int) -> None` - Store metadata for a workflow step.
- `to_dict(self) -> Dict[str, Any]` - Return a dictionary representation of all stored results.

### WorkflowStepMetadata

Metadata for a workflow step execution.

Attributes:
    step_type: The workflow step class name (e.g., 'CapacityEnvelopeAnalysis').
    step_name: The instance name of the step.
    execution_order: Order in which this step was executed (0-based).

**Attributes:**

- `step_type` (str)
- `step_name` (str)
- `execution_order` (int)

---

## ngraph.monte_carlo.functions

Picklable Monte Carlo analysis functions for FailureManager simulations.

These functions are designed for use with FailureManager.run_monte_carlo_analysis()
and follow the pattern: analysis_func(network_view: NetworkView, **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems for Monte Carlo
failure analysis scenarios.

Note: This module is distinct from ngraph.workflow.analysis, which provides
notebook visualization components for workflow results.

### demand_placement_analysis(network_view: "'NetworkView'", demands_config: 'list[dict[str, Any]]', placement_rounds: 'int' = 50, **kwargs) -> 'dict[str, Any]'

Analyze traffic demand placement success rates.

Args:
    network_view: NetworkView with potential exclusions applied.
    demands_config: List of demand configurations (serializable dicts).
    placement_rounds: Number of placement optimization rounds.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    Dictionary with placement statistics for this run, including:

- total_placed: Total placed demand volume.
- total_demand: Total demand volume.
- overall_placement_ratio: total_placed / total_demand (0.0 if undefined).
- priority_results: Mapping from priority to statistics with keys

      total_volume, placed_volume, unplaced_volume, placement_ratio,
      and demand_count.

### max_flow_analysis(network_view: "'NetworkView'", source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, include_flow_summary: 'bool' = False, **kwargs) -> 'list[tuple]'

Analyze maximum flow capacity between node groups.

Args:
    network_view: NetworkView with potential exclusions applied.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    include_flow_summary: Whether to collect detailed flow summary data.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    List of tuples. If include_flow_summary is False: (source, sink, capacity).
    If include_flow_summary is True: (source, sink, capacity, flow_summary).

### sensitivity_analysis(network_view: "'NetworkView'", source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, **kwargs) -> 'dict[str, dict[str, float]]'

Analyze component sensitivity to failures.

Args:
    network_view: NetworkView with potential exclusions applied.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    Dictionary mapping flow keys ("src->dst") to dictionaries of component
    identifiers mapped to sensitivity scores.

---

## ngraph.monte_carlo.results

Structured result objects for FailureManager analysis functions.

These classes provide interfaces for accessing Monte Carlo analysis
results from FailureManager convenience methods. Visualization is handled by
specialized analyzer classes in the workflow.analysis module.

### CapacityEnvelopeResults

Results from capacity envelope Monte Carlo analysis.

This class provides data access for capacity envelope analysis results.
For visualization, use CapacityMatrixAnalyzer from ngraph.workflow.analysis.

Attributes:
    envelopes: Dictionary mapping flow keys to CapacityEnvelope objects.
    failure_patterns: Dictionary mapping pattern keys to FailurePatternResult objects.
    source_pattern: Source node regex pattern used in analysis.
    sink_pattern: Sink node regex pattern used in analysis.
    mode: Flow analysis mode ("combine" or "pairwise").
    iterations: Number of Monte Carlo iterations performed.
    metadata: Additional analysis metadata from FailureManager.

**Attributes:**

- `envelopes` (Dict[str, CapacityEnvelope])
- `failure_patterns` (Dict[str, FailurePatternResult])
- `source_pattern` (str)
- `sink_pattern` (str)
- `mode` (str)
- `iterations` (int)
- `metadata` (Dict[str, Any])

**Methods:**

- `cost_distribution_summary(self) -> 'pd.DataFrame'` - Get cost distribution summary across all flows.
- `export_summary(self) -> 'Dict[str, Any]'` - Export summary for serialization.
- `flow_keys(self) -> 'List[str]'` - Get list of all flow keys in results.
- `get_cost_distribution(self, flow_key: 'str') -> 'Dict[float, Dict[str, float]]'` - Get cost distribution statistics for a specific flow.
- `get_envelope(self, flow_key: 'str') -> 'CapacityEnvelope'` - Get CapacityEnvelope for a specific flow.
- `get_failure_pattern_summary(self) -> 'pd.DataFrame'` - Get summary of failure patterns if available.
- `get_min_cut_frequencies(self, flow_key: 'str') -> 'Dict[str, int]'` - Get min-cut edge frequencies for a specific flow.
- `summary_statistics(self) -> 'Dict[str, Dict[str, float]]'` - Get summary statistics for all flow pairs.
- `to_dataframe(self) -> 'pd.DataFrame'` - Convert capacity envelopes to DataFrame for analysis.

### DemandPlacementResults

Results from demand placement Monte Carlo analysis.

Attributes:
    raw_results: Raw results from FailureManager
    iterations: Number of Monte Carlo iterations
    baseline: Optional baseline result (no failures)
    failure_patterns: Dictionary mapping pattern keys to failure pattern results
    metadata: Additional analysis metadata from FailureManager

**Attributes:**

- `raw_results` (dict[str, Any])
- `iterations` (int)
- `baseline` (Optional[dict[str, Any]])
- `failure_patterns` (Optional[Dict[str, Any]])
- `metadata` (Optional[Dict[str, Any]])

**Methods:**

- `success_rate_distribution(self) -> 'pd.DataFrame'` - Get demand placement success rate distribution as DataFrame.
- `summary_statistics(self) -> 'dict[str, float]'` - Get summary statistics for success rates.

### SensitivityResults

Results from sensitivity Monte Carlo analysis.

Attributes:
    raw_results: Raw results from FailureManager
    iterations: Number of Monte Carlo iterations
    baseline: Optional baseline result (no failures)
    component_scores: Aggregated component impact scores by flow
    failure_patterns: Dictionary mapping pattern keys to failure pattern results
    source_pattern: Source node regex pattern used in analysis
    sink_pattern: Sink node regex pattern used in analysis
    mode: Flow analysis mode ("combine" or "pairwise")
    metadata: Additional analysis metadata from FailureManager

**Attributes:**

- `raw_results` (dict[str, Any])
- `iterations` (int)
- `baseline` (Optional[dict[str, Any]])
- `component_scores` (Optional[Dict[str, Dict[str, Dict[str, float]]]])
- `failure_patterns` (Optional[Dict[str, Any]])
- `source_pattern` (Optional[str])
- `sink_pattern` (Optional[str])
- `mode` (Optional[str])
- `metadata` (Optional[Dict[str, Any]])

**Methods:**

- `component_impact_distribution(self) -> 'pd.DataFrame'` - Get component impact distribution as DataFrame.
- `export_summary(self) -> 'Dict[str, Any]'` - Export summary for serialization.
- `flow_keys(self) -> 'List[str]'` - Get list of all flow keys in results.
- `get_failure_pattern_summary(self) -> 'pd.DataFrame'` - Get summary of failure patterns if available.
- `get_flow_sensitivity(self, flow_key: 'str') -> 'Dict[str, Dict[str, float]]'` - Get component sensitivity scores for a specific flow.
- `summary_statistics(self) -> 'Dict[str, Dict[str, float]]'` - Get summary statistics for component impact across all flows.
- `to_dataframe(self) -> 'pd.DataFrame'` - Convert sensitivity results to DataFrame for analysis.

---

## ngraph.profiling.profiler

Profiling for NetGraph workflow execution.

Provides CPU and wall-clock timing per workflow step using ``cProfile`` and
aggregates results into structured summaries. Supports identification of
time-dominant steps (bottlenecks) and function-level analysis for targeted
performance improvements.

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
    memory_peak: Peak memory usage during step (if available).
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

## ngraph.profiling.reporter

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
