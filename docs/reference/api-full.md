<!-- markdownlint-disable MD007 MD032 MD029 MD050 MD004 MD052 MD012 -->

# NetGraph API Reference (Auto-Generated)

This is the complete auto-generated API documentation for NetGraph.
For a curated, example-driven API guide, see [api.md](api.md).

Quick links:

- [Main API Guide (api.md)](api.md)
- [This Document (api-full.md)](api-full.md)
- [CLI Reference](cli.md)
- [DSL Reference](dsl.md)

Generated from source code on: August 15, 2025 at 17:27 UTC

Modules auto-discovered: 73

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

## ngraph.report

Standalone report generation for NetGraph analysis results.

Generates Jupyter notebooks and optional HTML reports from ``results.json``.
This module is separate from workflow execution to allow independent analysis
in notebooks.

### ReportGenerator

Generate notebooks and HTML reports from a results document.

The notebook includes environment setup, results loading, overview, and
per-step analysis sections chosen via the analysis registry.

**Methods:**

- `generate_html_report(self, notebook_path: 'Path' = PosixPath('analysis.ipynb'), html_path: 'Path' = PosixPath('analysis_report.html'), include_code: 'bool' = False) -> 'Path'` - Render the notebook to HTML using nbconvert.
- `generate_notebook(self, output_path: 'Path' = PosixPath('analysis.ipynb')) -> 'Path'` - Create a Jupyter notebook with analysis scaffold.
- `load_results(self) -> 'None'` - Load and validate the JSON results file into memory.

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

Implements a practical Edmonds-Karp-like procedure using SPF with capacity
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

Notes:
    When a destination node is known, SPF supports an optimized mode that
    terminates once the destination's minimal distance is settled. In this mode:

- The destination node is not expanded (no neighbor relaxation from ``dst``).
- The algorithm continues processing any nodes with equal distance to capture

      equal-cost predecessors (needed by proportional flow placement).

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

### spf(graph: ngraph.graph.strict_multidigraph.StrictMultiDiGraph, src_node: Hashable, edge_select: ngraph.algorithms.base.EdgeSelect = <EdgeSelect.ALL_MIN_COST: 1>, edge_select_func: Optional[Callable[[ngraph.graph.strict_multidigraph.StrictMultiDiGraph, Hashable, Hashable, Dict[Hashable, Dict[str, Any]], Set[Hashable], Set[Hashable]], Tuple[Union[int, float], List[Hashable]]]] = None, multipath: bool = True, excluded_edges: Optional[Set[Hashable]] = None, excluded_nodes: Optional[Set[Hashable]] = None, dst_node: Optional[Hashable] = None) -> Tuple[Dict[Hashable, Union[int, float]], Dict[Hashable, Dict[Hashable, List[Hashable]]]]

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
    dst_node: Optional destination node. If provided, SPF avoids expanding
        from the destination and performs early termination once the next
        candidate in the heap would exceed the settled distance for
        ``dst_node``. This preserves equal-cost predecessors while avoiding
        unnecessary relaxations beyond the destination.

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
- `get_sub_path_bundle(self, new_dst_node: 'NodeID', graph: 'StrictMultiDiGraph', cost_attr: 'str' = 'cost') -> 'PathBundle'` - Create a sub-bundle ending at `new_dst_node` with correct minimal cost.
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
- `get_metrics(self) -> 'Dict[str, float]'` - Return cumulative placement metrics for this policy instance.
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

## ngraph.demand.manager.expand

Expansion helpers for traffic demand specifications.

Public functions here convert user-facing `TrafficDemand` specifications into
concrete `Demand` objects that can be placed on a `StrictMultiDiGraph`.

This module provides the pure expansion logic that was previously embedded in
`TrafficManager`.

### expand_demands(network: "Union[Network, 'NetworkView']", graph: 'StrictMultiDiGraph | None', traffic_demands: 'List[TrafficDemand]', default_flow_policy_config: 'FlowPolicyConfig') -> 'Tuple[List[Demand], Dict[str, List[Demand]]]'

Expand traffic demands into concrete `Demand` objects.

The result is a flat list of `Demand` plus a mapping from
``TrafficDemand.id`` to the list of expanded demands for that entry.

Args:
    network: Network or NetworkView used for node group selection.
    graph: Flow graph to operate on. If ``None``, expansion that requires
        graph mutation (pseudo nodes/edges) is skipped.
    traffic_demands: List of high-level traffic demand specifications.
    default_flow_policy_config: Default policy to apply when a demand does
        not specify an explicit `flow_policy`.

Returns:
    A tuple ``(expanded, td_map)`` where:

- ``expanded`` is the flattened, sorted list of all expanded demands

      (sorted by ascending ``demand_class``).

- ``td_map`` maps ``TrafficDemand.id`` to its expanded demands.

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
      on a configurable 'mode' ("combine" or "pairwise").
  3) Each Demand is associated with a FlowPolicy, which handles how flows
     are placed (split across paths, balancing, etc.).
     4) Provides methods to place all demands incrementally with optional
      re-optimization, reset usage, and retrieve flow/usage summaries.

 Auto rounds semantics:

- placement_rounds="auto" performs up to a small number of fairness passes

     (at most 3), with early stop when diminishing returns are detected. Each
     pass asks the scheduler to place full leftovers without step splitting.

In particular:

- 'combine' mode:
- Combine all matched sources into a single pseudo-source node, and all

      matched sinks into a single pseudo-sink node (named using the traffic
      demand's `source_path` and `sink_path`). A single Demand is created
      from the pseudo-source to the pseudo-sink, with the full volume.

- 'pairwise' mode:
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

Scheduling utilities for demand placement rounds.

Provides the simple priority-aware round-robin scheduler that was previously
implemented in `TrafficManager`.

### place_demands_round_robin(graph: 'StrictMultiDiGraph', demands: 'List[Demand]', placement_rounds: 'int', reoptimize_after_each_round: 'bool' = False) -> 'float'

Place demands using priority buckets and round-robin within each bucket.

Args:
    graph: Active flow graph.
    demands: Expanded demands to place.
    placement_rounds: Number of passes per priority class.
    reoptimize_after_each_round: Whether to re-run placement for each demand
        after a round to better share capacity.

Returns:
    Total volume successfully placed across all demands.

---

## ngraph.demand.matrix

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

## ngraph.failure.conditions

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
- `run_demand_placement_monte_carlo(self, demands_config: 'list[dict[str, Any]] | Any', iterations: 'int' = 100, parallelism: 'int' = 1, placement_rounds: 'int | str' = 'auto', baseline: 'bool' = False, seed: 'int | None' = None, store_failure_patterns: 'bool' = False, include_flow_details: 'bool' = False, **kwargs) -> 'Any'` - Analyze traffic demand placement success under failures.
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

## ngraph.failure.policy_set

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

## ngraph.workflow.analysis.bac

Bandwidth-Availability Curve (BAC) from ``flow_results``.

Supports both MaxFlow and TrafficMatrixPlacement steps. For each failure
iteration, aggregate delivered bandwidth (sum of ``placed`` over all DC-DC
pairs). Compute the empirical availability curve and summary quantiles.

This enhanced version optionally normalizes the x-axis by the offered demand
volume (when available via per-flow ``demand`` fields) to improve comparison
across scenarios of different scale. It preserves existing outputs and overlay
behavior for compatibility.

### BACAnalyzer

Base class for notebook analysis components.

Subclasses should provide a pure computation method (``analyze``) and a
rendering method (``display_analysis``). Use ``analyze_and_display`` as a
convenience to run both.

**Methods:**

- `analyze(self, results: 'dict[str, Any]', **kwargs) -> 'dict[str, Any]'` - Analyze delivered bandwidth to build an availability curve.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `display_analysis(self, analysis: 'dict[str, Any]', **kwargs) -> 'None'` - Render the BAC with optional overlay comparison.
- `get_description(self) -> 'str'` - Return a short description of the BAC analyzer.

---

## ngraph.workflow.analysis.base

Base classes for notebook analysis components.

Defines a minimal interface for notebook-oriented analyzers that compute
results and render them inline. Concrete analyzers implement ``analyze()``,
``display_analysis()``, and ``get_description()``.

### AnalysisContext

Carry context information for analysis execution.

Attributes:
    step_name: Name of the workflow step being analyzed.
    results: The full results document.
    config: Analyzer configuration or parameters for the step.

**Attributes:**

- `step_name` (str)
- `results` (dict[str, Any])
- `config` (dict[str, Any])

### NotebookAnalyzer

Base class for notebook analysis components.

Subclasses should provide a pure computation method (``analyze``) and a
rendering method (``display_analysis``). Use ``analyze_and_display`` as a
convenience to run both.

**Methods:**

- `analyze(self, results: 'dict[str, Any]', **kwargs) -> 'dict[str, Any]'` - Return analysis outputs for a given results document.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `display_analysis(self, analysis: 'dict[str, Any]', **kwargs) -> 'None'` - Render analysis outputs in notebook format.
- `get_description(self) -> 'str'` - Return a concise description of the analyzer purpose.

---

## ngraph.workflow.analysis.capacity_matrix

Capacity matrix analysis.

Consumes ``flow_results`` (from MaxFlow step). Builds node→node capacity matrix
using the maximum placed value observed per pair across iterations (i.e., the
capacity ceiling under the tested failure set). Provides stats and a heatmap.

This enhanced version augments printed statistics (quartiles, density wording)
and is designed to be extended with distribution plots. To preserve test
stability and headless environments, histogram/CDF plots are not emitted here;
they can be added in notebooks explicitly if desired.

### CapacityMatrixAnalyzer

Analyze max-flow capacities into matrices/statistics/plots.

**Methods:**

- `analyze(self, results: 'Dict[str, Any]', **kwargs) -> 'Dict[str, Any]'` - Return analysis outputs for a given results document.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `analyze_and_display_step(self, results: 'Dict[str, Any]', **kwargs) -> 'None'` - Analyze and render capacity matrix for a single workflow step.
- `display_analysis(self, analysis: 'Dict[str, Any]', **kwargs) -> 'None'` - Render analysis outputs in notebook format.
- `get_description(self) -> 'str'` - Return the analyzer description.

---

## ngraph.workflow.analysis.cost_power_analysis

Power/Cost analyzer for CostPower workflow step.

Computes absolute and unit-normalised metrics per aggregation level path
(typically level 2 "sites").

Inputs:

- CostPower step data under ``steps[step_name]["data"]`` with ``levels`` and

  ``context.aggregation_level``.

- Delivered traffic from a ``TrafficMatrixPlacement`` step (auto-detected or

  provided via ``traffic_step``), using baseline iteration if available.

Outputs:

- site_metrics: mapping path -> {power_total_watts, capex_total, delivered_gbps}
- normalized_metrics: mapping path -> {power_per_unit, cost_per_unit}

Display renders tables (itables.show) and simple bar charts (seaborn).

### CostPowerAnalysis

Analyze power and capex per site and normalise by delivered traffic.

The analyzer aggregates absolute metrics from the CostPower step and
attributes delivered traffic to sites based on the baseline iteration of a
TrafficMatrixPlacement step. Ratios are computed as W/{unit} and $/{unit}.

**Methods:**

- `analyze(self, results: 'Dict[str, Any]', **kwargs: 'Any') -> 'Dict[str, Any]'` - Compute absolute and normalised metrics per site.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `display_analysis(self, analysis: 'Dict[str, Any]', **kwargs: 'Any') -> 'None'` - Render absolute and normalised metrics tables and bar charts.
- `get_description(self) -> 'str'` - Return a concise description of the analyzer purpose.

---

## ngraph.workflow.analysis.data_loader

Load JSON results for notebook analysis with a status wrapper.

The loader returns a small dictionary that includes success status and basic
metadata about the results file. It keeps errors non-fatal for notebook usage.

### DataLoader

Load and validate analysis results from a JSON file.

**Methods:**

- `load_results(json_path: Union[str, pathlib._local.Path]) -> dict[str, typing.Any]`

---

## ngraph.workflow.analysis.latency

Latency (distance) and stretch from ``cost_distribution``.

For each iteration, compute:
  • mean distance per delivered Gbps (km/Gbps) aggregated across flows
  • stretch = (mean distance) / (pair-wise lower-bound distance)
Lower bound is approximated as the minimum observed path cost per (src, dst) in
the "baseline" iteration(s) of the same step (or, if absent, across all
iterations).

This enhanced version augments the display with a CDF of stretch values to show
the distribution across iterations, complementing the scatter plot view.

### LatencyAnalyzer

Base class for notebook analysis components.

Subclasses should provide a pure computation method (``analyze``) and a
rendering method (``display_analysis``). Use ``analyze_and_display`` as a
convenience to run both.

**Methods:**

- `analyze(self, results: 'dict[str, Any]', **kwargs) -> 'dict[str, Any]'` - Compute latency and stretch metrics for each failure iteration.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `display_analysis(self, analysis: 'dict[str, Any]', **kwargs) -> 'None'` - Render the latency and stretch scatter plot with summary lines.
- `get_description(self) -> 'str'` - Return a short description of the latency analyzer.

---

## ngraph.workflow.analysis.msd

Analyzer for Maximum Supported Demand (MSD) step.

### MSDAnalyzer

Base class for notebook analysis components.

Subclasses should provide a pure computation method (``analyze``) and a
rendering method (``display_analysis``). Use ``analyze_and_display`` as a
convenience to run both.

**Methods:**

- `analyze(self, results: 'dict[str, Any]', **kwargs) -> 'dict[str, Any]'` - Return analysis outputs for a given results document.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `display_analysis(self, analysis: 'dict[str, Any]', **kwargs) -> 'None'` - Render analysis outputs in notebook format.
- `get_description(self) -> 'str'` - Return a concise description of the analyzer purpose.

---

## ngraph.workflow.analysis.package_manager

Environment setup for notebook analysis components.

This module configures plotting and table-display libraries used by notebook
analysis. It does not install packages dynamically. All required dependencies
must be declared in ``pyproject.toml`` and available at runtime.

### PackageManager

Configure plotting and table-display packages for notebooks.

The class validates that required packages are importable and applies common
styling defaults for plots and data tables.

**Methods:**

- `check_packages() -> 'dict[str, Any]'` - Return availability status of required packages.
- `setup_environment() -> 'dict[str, Any]'` - Configure plotting and table libraries if present.

---

## ngraph.workflow.analysis.placement_matrix

Placement analysis utilities for ``flow_results`` (unified design).

Consumes results produced by ``TrafficMatrixPlacementAnalysis`` with the new
schema under ``step["data"]["flow_results"]``. Builds matrices of mean placed
volume by pair (overall and per priority), with basic statistics.

This enhanced version also computes delivery fraction statistics (placed/
demand) per flow instance to quantify drops and renders simple distributions
(histogram and CDF) when demand is present, while preserving existing outputs
so tests remain stable.

### PlacementMatrixAnalyzer

Analyze placed Gbps envelopes and display matrices/statistics.

**Methods:**

- `analyze(self, results: 'Dict[str, Any]', **kwargs) -> 'Dict[str, Any]'` - Analyze ``flow_results`` for a given step.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `analyze_and_display_step(self, results: 'Dict[str, Any]', **kwargs) -> 'None'` - Convenience wrapper that analyzes and renders one step.
- `display_analysis(self, analysis: 'Dict[str, Any]', **kwargs) -> 'None'` - Render per-priority placement matrices with summary statistics.
- `get_description(self) -> 'str'` - Return a short description of the analyzer purpose.

---

## ngraph.workflow.analysis.registry

Registry mapping workflow step types to notebook analyzers.

Provides a simple mapping from workflow ``step_type`` identifiers to analyzer
configurations. The default registry wires common NetGraph analysis steps to
their notebook components.

### AnalysisConfig

Configuration for a single analyzer binding.

**Attributes:**

- `analyzer_class` (Type[NotebookAnalyzer])
- `method_name` (str) = analyze_and_display
- `kwargs` (dict[str, Any]) = {}
- `section_title` (Optional[str])
- `enabled` (bool) = True

### AnalysisRegistry

Collection of analyzer bindings keyed by workflow step type.

**Attributes:**

- `_mappings` (dict[str, list[AnalysisConfig]]) = {}

**Methods:**

- `get_all_step_types(self) -> 'list[str]'`
- `get_analyses(self, step_type: 'str') -> 'list[AnalysisConfig]'`
- `register(self, step_type: 'str', analyzer_class: 'Type[NotebookAnalyzer]', method_name: 'str' = 'analyze_and_display', section_title: 'Optional[str]' = None, **kwargs: 'Any') -> 'None'`

### get_default_registry() -> 'AnalysisRegistry'

Return standard analyzer mapping for common workflow steps.

Includes bindings for ``NetworkStats``, ``MaximumSupportedDemand``,
``TrafficMatrixPlacement``, and ``MaxFlow``.

---

## ngraph.workflow.analysis.summary

High-level summary analyzer for results documents.

Provides quick counts of steps and basic categorisation by presence of
``flow_results`` in the new schema. Also contains a small helper for
``NetworkStats`` sections aimed at notebook usage.

### SummaryAnalyzer

Compute simple counts and high-level summary statistics.

**Methods:**

- `analyze(self, results: dict[str, typing.Any], **kwargs) -> dict[str, typing.Any]` - Return analysis outputs for a given results document.
- `analyze_and_display(self, results: 'dict[str, Any]', **kwargs) -> 'None'` - Analyze results and render them in notebook format.
- `analyze_network_stats(self, results: dict[str, typing.Any], **kwargs) -> None` - Display a small info line for ``NetworkStats`` steps.
- `display_analysis(self, analysis: dict[str, typing.Any], **kwargs) -> None` - Render analysis outputs in notebook format.
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

Converts scenario network definitions into StrictMultiDiGraph structures suitable
for analysis algorithms. No additional parameters required beyond basic workflow step options.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: BuildGraph

        name: "build_network_graph"  # Optional: Custom name for this step
    ```

Results stored in `scenario.results` under the step name as two keys:

- metadata: Step-level execution metadata (empty dict)
- data: { graph: node-link JSON dict, context: { add_reverse: bool } }

### BuildGraph

A workflow step that builds a StrictMultiDiGraph from scenario.network.

This step converts the scenario's network definition into a graph structure
suitable for analysis algorithms. No additional parameters are required.

**Attributes:**

- `name` (str)
- `seed` (Optional[int])
- `_seed_source` (str)

**Methods:**

- `execute(self, scenario: "'Scenario'") -> 'None'` - Execute the workflow step with logging and metadata storage.
- `run(self, scenario: 'Scenario') -> 'None'` - Build the network graph and store it in results.

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
        include_failure_patterns: false  # same as store_failure_patterns
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

Supports optional exclusion simulation using NetworkView without modifying the base network.

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
    include_flow_details: If True, include edges used per demand.
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

## ngraph.results.artifacts

Serializable result artifacts for analysis workflows.

This module defines dataclasses that capture outputs from analyses and
simulations in a JSON-serializable form:

- `PlacementResultSet`: aggregated placement results and statistics
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

## ngraph.monte_carlo.functions

Picklable Monte Carlo analysis functions for FailureManager simulations.

These functions are designed for use with FailureManager.run_monte_carlo_analysis()
and follow the pattern: analysis_func(network_view: NetworkView, **kwargs) -> Any.

All functions accept only simple, hashable parameters to ensure compatibility
with FailureManager's caching and multiprocessing systems for Monte Carlo
failure analysis scenarios.

Note: This module is distinct from ngraph.workflow.analysis, which provides
notebook visualization components for workflow results.

### demand_placement_analysis(network_view: "'NetworkView'", demands_config: 'list[dict[str, Any]]', placement_rounds: 'int | str' = 'auto', include_flow_details: 'bool' = False, **kwargs) -> 'FlowIterationResult'

Analyze traffic demand placement success rates.

Returns a structured dictionary per iteration containing per-demand offered
and placed volumes (in Gbit/s) and an iteration-level summary. This shape
is designed for downstream computation of delivered bandwidth percentiles
without having to reconstruct per-iteration joint distributions.

Args:
    network_view: NetworkView with potential exclusions applied.
    demands_config: List of demand configurations (serializable dicts).
    placement_rounds: Number of placement optimization rounds.
    include_flow_details: If True, include edges used per demand.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    FlowIterationResult describing this iteration.

### max_flow_analysis(network_view: "'NetworkView'", source_regex: 'str', sink_regex: 'str', mode: 'str' = 'combine', shortest_path: 'bool' = False, flow_placement: 'FlowPlacement' = <FlowPlacement.PROPORTIONAL: 1>, include_flow_details: 'bool' = False, include_min_cut: 'bool' = False, **kwargs) -> 'FlowIterationResult'

Analyze maximum flow capacity between node groups.

Args:
    network_view: NetworkView with potential exclusions applied.
    source_regex: Regex pattern for source node groups.
    sink_regex: Regex pattern for sink node groups.
    mode: Flow analysis mode ("combine" or "pairwise").
    shortest_path: Whether to use shortest paths only.
    flow_placement: Flow placement strategy.
    include_flow_details: Whether to collect cost distribution and similar details.
    include_min_cut: Whether to include min-cut edge list in entry data.
    **kwargs: Ignored. Accepted for interface compatibility.

Returns:
    FlowIterationResult describing this iteration.

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

CapacityEnvelopeResults(envelopes: 'Dict[str, CapacityEnvelope]', failure_patterns: 'Dict[str, FailurePatternResult]', source_pattern: 'str', sink_pattern: 'str', mode: 'str', iterations: 'int', metadata: 'Dict[str, Any]')

**Attributes:**

- `envelopes` (Dict[str, CapacityEnvelope])
- `failure_patterns` (Dict[str, FailurePatternResult])
- `source_pattern` (str)
- `sink_pattern` (str)
- `mode` (str)
- `iterations` (int)
- `metadata` (Dict[str, Any])

**Methods:**

- `export_summary(self) -> 'Dict[str, Any]'`

### DemandPlacementResults

DemandPlacementResults(raw_results: 'dict[str, Any]', iterations: 'int', baseline: 'Optional[dict[str, Any]]' = None, failure_patterns: 'Optional[Dict[str, Any]]' = None, metadata: 'Optional[Dict[str, Any]]' = None)

**Attributes:**

- `raw_results` (dict[str, Any])
- `iterations` (int)
- `baseline` (Optional[dict[str, Any]])
- `failure_patterns` (Optional[Dict[str, Any]])
- `metadata` (Optional[Dict[str, Any]])

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

## ngraph.monte_carlo.types

Typed protocols for Monte Carlo analysis IPC payloads.

Defines lightweight, serializable structures used across worker boundaries.

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
