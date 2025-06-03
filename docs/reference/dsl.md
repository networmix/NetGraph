# Domain-Specific Language (DSL)

This document provides an overview of the DSL used in NetGraph to define and run network scenarios. The scenario is typically defined in a YAML file that describes the network topology, traffic demands, and analysis workflow. Note: scenario can also be fully defined in Python code, but it will be covered in a separate document.

## Overview

The scenario YAML file is organized around a **core foundation** that defines your network, with **optional enhancements** for reusability, hardware modeling, failure simulation, and analysis. This document follows a logical progression from the essential core to advanced features.

## Top-Level Keys

The main sections of a scenario YAML file work together to define a complete network simulation:

- `network`: **[Required]** Describes the actual network topology - nodes, links, and their connections.
- `blueprints`: **[Optional]** Defines reusable network templates that can be instantiated multiple times within the network.
- `components`: **[Optional]** A library of hardware and optics definitions with attributes like power consumption.
- `risk_groups`: **[Optional]** Defines groups of components that might fail together (e.g., all components in a rack or multiple parallel links sharing the same DWDM transmission).
- `traffic_demands`: **[Optional]** Defines traffic demands between network nodes with various placement policies.
- `failure_policy`: **[Optional]** Specifies availability parameters and rules for simulating network failures.
- `workflow`: **[Optional]** A list of steps to be executed, such as building graphs, running simulations, or performing analyses.

## `network` - Core Foundation

The `network` section is the **only required section** in a scenario file. It defines the overall network structure through nodes and their connections. Even an empty network with zero nodes is valid (though not very useful).

**Top-Level Network Properties:**

```yaml
network:
  name: "NetworkName"     # Optional: Human-readable network name
  version: "1.0"          # Optional: Version identifier (string or number)
  # ... groups, adjacency, etc.
```

**Defining Node Groups Directly in the Network:**

The most common approach is to define groups of similar nodes and their connectivity patterns:

```yaml
network:
  groups:
    direct_group_A: # A top-level group defined directly
      node_count: 2
      name_template: "server-{node_num}" # Results in nodes: direct_group_A/server-1, direct_group_A/server-2
      attrs:
        os: "linux"
    instance_of_bp:  # Another top-level group from a blueprint
      use_blueprint: my_blueprint_name # Instantiates a blueprint. Nodes within will be prefixed by 'instance_of_bp/'
      attrs: # Attributes defined here can be inherited by nodes within the blueprint if not overridden
        location: "rack1"
      risk_groups: ["RG_INSTANCE"] # Risk groups here are merged with those defined in the blueprint's groups
  adjacency:
    - source: /direct_group_A
      target: /instance_of_bp
      pattern: "mesh"
      link_params:
        capacity: 100  # Capacity of each link
        cost: 10  # Cost (metric) of each link
```

**Direct Node Definitions:**

You can define individual nodes directly without using groups:

```yaml
network:
  nodes:
    SEA:
      attrs:
        coords: [47.6062, -122.3321]
        hw_type: "router_model_A"
    SFO:
      attrs:
        coords: [37.7749, -122.4194]
        hw_type: "router_model_B"
```

**Direct Link Definitions:**

You can define individual links directly between existing nodes:

```yaml
network:
  links:
    - source: SEA
      target: DEN
      link_params:
        capacity: 200
        cost: 6846
        attrs:
          distance_km: 1369.13
          media_type: "fiber"
    # Multiple parallel links between same nodes
    - source: DEN
      target: DFW
      link_params:
        capacity: 400
        cost: 7102
    - source: DEN
      target: DFW
      link_params:
        capacity: 400
        cost: 7102
```

**Bracket Expansion in Group Names:**

Group names can use bracket `[]` notation for concise definition of multiple similar groups. For example, `plane[1-4]` would create groups `plane1`, `plane2`, `plane3`, and `plane4`. If this group instantiates a blueprint, the blueprint is instantiated for each expanded name.

```yaml
network:
  groups:
    dc[1-2]/fabric: # Creates dc1/fabric and dc2/fabric
      use_blueprint: clos_fabric
      parameters: # Parameters can be passed to the blueprint
        clos_fabric.spine_count: 8
```

The bracket expansion syntax supports:
- **Numeric ranges**: `[1-4]` expands to `1`, `2`, `3`, `4`
- **Character ranges**: `[a-c]` expands to `a`, `b`, `c`  
- **Explicit lists**: `[red,blue,green]` expands to `red`, `blue`, `green`
- **Multiple expansions**: `dc[1-2]/rack[a-b]` creates `dc1/racka`, `dc1/rackb`, `dc2/racka`, `dc2/rackb`

**Advanced Adjacency Features:**

Variable expansion allows dynamic creation of adjacency rules:

```yaml
adjacency:
  # Cartesian product expansion
  - source: "plane{p}/rack{r}"
    target: "spine{s}"
    expand_vars:
      p: [1, 2]
      r: ["a", "b"] 
      s: [1, 2, 3]
    expansion_mode: "cartesian"  # Creates all combinations
    pattern: "mesh"
    
  # Zip expansion (pairs elements by index)
  - source: "server{idx}"
    target: "switch{idx}"
    expand_vars:
      idx: [1, 2, 3, 4]
    expansion_mode: "zip"  # server1->switch1, server2->switch2, etc.
    pattern: "one_to_one"
```

Complex pattern matching with regex:

```yaml
adjacency:
  # Use regex in source/target paths with bracket expansion
  - source: "/pod1/rsw"
    target: "/plane[0-9]*/fsw/fsw-1"  # Matches plane1/fsw/fsw-1, plane2/fsw/fsw-1, etc.
    pattern: mesh
```

## Node and Link Overrides

You can override specific attributes of nodes and links after they are created by network definitions or blueprints:

```yaml
network:
  # ... groups and adjacency definitions ...
  
  node_overrides:
    - path: "^my_clos1/spine/switch-(1|3|5)$"  # Specific spine switches
      disabled: true
      attrs:
        maintenance_mode: "active"
        hw_type: "newer_model"
    - path: "^dc1/leaf/.*$"  # All leaf switches in dc1
      attrs:
        role: "access_switch"

  link_overrides:
    - source: "^my_clos1/leaf/.*$"
      target: "^my_clos1/spine/.*$"
      disabled: false  # Ensure all leaf-spine links are enabled
      capacity: 400    # Override default capacity
    - source: "^backup_dc/.*$"
      target: "^primary_dc/.*$"
      cost: 1000       # Make backup paths less preferred
    # Override specific link between two exact nodes
    - source: "my_clos1/spine/t3-1$"
      target: "my_clos2/spine/t3-1$"
      link_params:
        capacity: 1     # Reduce capacity of this specific link
        cost: 1
    # Apply attributes to all spine-to-spine links in any direction
    - source: ".*/spine/.*"
      target: ".*/spine/.*"
      any_direction: true  # Match both directions of the link
      link_params:
        attrs:
          shared_risk_groups: ["SpineSRG"]
          hw_component: "400G-LR4"
```

## `blueprints` - Reusable Templates

Blueprints are templates for network segments that can be referenced from the `network` section. They allow you to define a structure once and reuse it multiple times, making your scenarios more maintainable and reducing duplication.

**Defining Node Groups within Blueprints:**

A blueprint consists of `groups` and `adjacency` definitions. Each entry under `groups` defines a collection of nodes with common properties. Adjacency rules define how these groups connect to each other within the blueprint.

```yaml
blueprints:
  my_blueprint_name:
    groups:
      group_name_1: # This is a logical name for a collection of nodes
        node_count: N                 # Number of nodes in this group
        name_template: "prefix-{node_num}" # How nodes are named within this group.
                                      # {node_num} is replaced by 1, 2, ..., N.
                                      # Full node name becomes: <blueprint_instance_name>/<group_name_1>/prefix-1
        attrs:                        # Optional: Default attributes for all nodes in this group
          hw_type: "router_model_X"
          role: "leaf"
        disabled: false               # Optional: If true, nodes are created but marked as disabled
        risk_groups: ["RG1", "RG2"]   # Optional: List of risk groups these nodes belong to
      # ... other groups ...
    adjacency:
      # Defines connections BETWEEN groups WITHIN this blueprint.
      # These connections are created when the blueprint is instantiated.
      - source: /group_name_1  # Path to a source group within this blueprint.
                              # Paths are typically relative to the blueprint's own scope.
                              # e.g., /group_name_1 refers to 'group_name_1' defined above.
        target: /group_name_2  # Path to a target group within this blueprint.
        pattern: "mesh"       # Connectivity pattern:
                              # - "mesh": Connect every node in source to every node in target.
                              # - "one_to_one": Pair nodes from source to target. Sizes must be
                              #   compatible (e.g., same size, or one is a multiple of the other).
                              # Other patterns might be available.
        link_count: 1         # Optional: Number of parallel links to create for each pair
                              # defined by the pattern. Defaults to 1.
        link_params:          # Optional: Attributes for the links created by this adjacency rule.
          capacity: 100       # e.g., capacity of each link.
          cost: 10            # e.g., cost of each link.
          disabled: false     # Optional: If true, links are created but marked as disabled.
          risk_groups: ["RG_LINK_TYPE_A"] # Optional: Risk groups for these links.
          attrs:              # Optional: Custom attributes for these links.
            media_type: "fiber"
      - source: /group_name_1
        target: /group_name_1 # Connecting a group to itself (e.g., full mesh within t1 nodes)
        pattern: mesh
        link_params:
          capacity: 50
      # Adjacency with variable expansion for more complex scenarios
      - source: "/group_prefix_{var1}/nodes"
        target: "/another_group_prefix_{var2}/nodes"
        pattern: "one_to_one"
        expand_vars: # Defines variables to be substituted into source and target paths
          var1: [1, 2]
          var2: ["a", "b"]
        expansion_mode: "cartesian" # "cartesian" (all combinations) or "zip"
        link_params:
          capacity: 200

      # Advanced pattern matching with regex placeholders
      - source: "eb0{idx}"
        target: "eb0{idx}"
        expand_vars:
          idx: [1, 2, 3, 4, 5, 6, 7, 8]
        expansion_mode: "zip"  # Pairs source[i] with target[i]
        pattern: "mesh"
        link_params: 
          capacity: 3200
```

**Blueprint Parameter Overrides:**

When instantiating blueprints in the `network` section, you can override specific parameters using dot notation:

```yaml
network:
  groups:
    my_clos_instance:
      use_blueprint: 3tier_clos
      parameters:
        # Override spine node count in the blueprint
        spine.node_count: 8
        # Override naming template
        spine.name_template: "backbone-{node_num}"
        # Override nested blueprint parameters
        brick.t1.node_count: 6
```

When a blueprint is instantiated (e.g., `my_clos1: use_blueprint: 3tier_clos`), the `group_name_1` above would result in nodes like `my_clos1/group_name_1/prefix-1`, `my_clos1/group_name_1/prefix-2`, etc. The `adjacency` rules would then create links between these instantiated nodes, for example, connecting nodes from `my_clos1/group_name_1` to `my_clos1/group_name_2`.

**Path Hierarchy:**

Node names form a hierarchy based on their group structure. For example, a node defined in `group_A` within a blueprint `bp_X`, which is instantiated as `instance_Y`, might have a full name like `instance_Y/group_A/node_name-1`. This hierarchical path is crucial for matching.

## `components` - Hardware Library

Defines a library of hardware components (e.g., routers, optics) and their attributes, like power consumption. Components are referenced by nodes and links through their `attrs` field, providing a centralized way to model hardware characteristics.

```yaml
components:
  SpineChassis:
    component_type: "chassis"
    description: "High-capacity spine router chassis"
    cost: 50000.0
    power_watts: 2500.0
    power_watts_max: 3000.0
    capacity: 64000.0  # Gbps
    ports: 64
    count: 1
    attrs:
      vendor: "Example Corp"
      model: "EX-9000"
    children:
      LineCard400G:
        component_type: "linecard"
        cost: 8000.0
        power_watts: 400.0
        capacity: 12800.0  # 32x400G ports
        ports: 32
        count: 4
        
  Optic400GLR4:
    component_type: "optic"
    description: "400G LR4 pluggable optic"
    cost: 2500.0
    power_watts: 12.0
    capacity: 400.0
    count: 1
    attrs:
      reach: "10km"
      wavelength: "1310nm"
```

Components are referenced by nodes and links through their `attrs` field:

```yaml
network:
  nodes:
    spine-1:
      attrs:
        hw_component: "SpineChassis"  # References component definition
  links:
    - source: spine-1
      target: leaf-1
      link_params:
        attrs:
          ```

## `risk_groups` - Hardware Risk Modeling

Defines hierarchical groups of components that share a common fate (e.g., all components in a rack, or on a card). This section is used in conjunction with `components` to model realistic failure scenarios.

```yaml
risk_groups:
  - name: "Rack1"
    disabled: false # Optional, defaults to false
    attrs: # Optional custom attributes
      location: "DC1_Floor2"
    children: # Optional, for nested risk groups
      - name: "Card1.1"
        children:
          - name: "PortGroup1.1.1"
      - name: "Card1.2"
  - name: "PowerSupplyUnitA"
```

Nodes and links can be associated with risk groups using their `risk_groups` attribute (a list of risk group names).

## `traffic_demands` - Traffic Analysis

Specifies the traffic demands between different parts of the network. This section enables capacity analysis and flow optimization by defining traffic patterns.

```yaml
traffic_demands:
  - name: "DemandName" # Optional
    source_path: "regex/for/source_nodes"
    sink_path: "regex/for/sink_nodes"
    demand: X # Amount of traffic
    mode: "combine" | "full_mesh" # Expansion mode for generating sub-demands
    priority: P # Optional priority level
    flow_policy_config: # Optional, defines how traffic is routed
      # Available configurations:
      # "SHORTEST_PATHS_ECMP" - hop-by-hop equal-cost balanced routing
      # "SHORTEST_PATHS_UCMP" - hop-by-hop proportional flow placement
      # "TE_UCMP_UNLIM" - unlimited MPLS LSPs with UCMP
      # "TE_ECMP_UP_TO_256_LSP" - up to 256 LSPs with ECMP
      # "TE_ECMP_16_LSP" - exactly 16 LSPs with ECMP
    attrs: # Optional custom attributes
      key: value
```

**Traffic Demand Modes:**

- **`combine`** (default): Creates a pseudo-source node connected with infinite-capacity edges to all matched source nodes, and a pseudo-sink node connected with infinite-capacity edges from all matched sink nodes. Creates one demand from the pseudo-source to the pseudo-sink with the full demand volume. This is useful for modeling aggregate traffic flows between groups of nodes.

- **`full_mesh`**: Creates individual demands for each (source_node, sink_node) pair, excluding self-pairs (where source equals sink). The total demand volume is split evenly among all valid pairs. This is useful for modeling distributed traffic patterns where every source communicates with every sink.

## `failure_policy` - Failure Simulation

Defines how network failures are simulated to test resilience and analyze failure scenarios.

```yaml
failure_policy:
  name: "PolicyName" # Optional
  fail_shared_risk_groups: true | false
  fail_risk_group_children: true | false
  use_cache: true | false
  attrs: # Optional custom attributes for the policy
    custom_key: value
  rules:
    - entity_scope: "node" | "link" | "risk_group"
      conditions: # Optional: list of conditions to select entities
        - attr: "attribute_name"
          operator: "==" | "!=" | ">" | "<" | ">=" | "<=" | "contains" | "not_contains" | "any_value" | "no_value"
          value: "some_value"
      logic: "and" | "or" | "any" # How to combine conditions
      rule_type: "all" | "choice" | "random" # How to select entities matching conditions
      count: N # For 'choice' rule_type
      probability: P # For 'random' rule_type (0.0 to 1.0)
```

## `workflow` - Execution Steps

A list of operations to perform on the network. Each step has a `step_type` and specific arguments. This section defines the analysis workflow to be executed.

```yaml
workflow:
  - step_type: BuildGraph
    # Builds the StrictMultiDiGraph from scenario.network for analysis
    # No additional parameters required

  - step_type: EnableNodes
    path: "^regex/for/nodes/to/enable"
    count: N # Number of nodes to enable
    order: "name" | "random" | "reverse" # Selection order

  - step_type: DistributeExternalConnectivity
    remote_prefix: "prefix_for_remote_nodes/"
    remote_locations:
      - LOC_A
      - LOC_B
    attachment_path: "^regex/for/attachment/nodes"
    stripe_width: W # Distribution width
    link_count: N # Number of links per remote node (default: 1)
    capacity: C # Link capacity
    cost: Z # Link cost

  - step_type: CapacityProbe
    name: "probe_name"  # Optional: Name for the probe step
    source_path: "regex/for/source_nodes"
    sink_path: "regex/for/sink_nodes"
    mode: "combine" | "pairwise" # How to group sources and sinks
    probe_reverse: true | false # Whether to probe reverse direction
    shortest_path: true | false # Use shortest path only vs full max flow
    flow_placement: "PROPORTIONAL" | "EQUAL_BALANCED" # How to distribute flow
    # Additional probe parameters available
```

**Available Workflow Steps:**

- **`BuildGraph`**: Builds the network graph from the scenario definition
- **`EnableNodes`**: Enables previously disabled nodes matching a path pattern
- **`DistributeExternalConnectivity`**: Creates external connectivity across attachment points
- **`CapacityProbe`**: Probes maximum flow capacity between node groups

## Path Matching Regex Syntax - Reference

Many parts of the DSL use **path expressions** to select nodes or links based on their names. These expressions are Python regular expressions (regex) that are matched against the full, hierarchical names of nodes or the source/target names of links.

### Core Matching Behavior

NetGraph uses Python's `re.match()` function for path matching, which has specific behavior:

- **Anchored at start**: The pattern is automatically anchored at the beginning of the node name. You don't need `^` at the start (though it's harmless to include it).
- **Prefix matching**: Unlike `re.search()`, the pattern must match from the beginning of the string.
- **Full match not required**: The pattern doesn't need to match the entire node name unless you explicitly anchor it at the end with `$`.

### Pattern Types and Examples

**1. Exact Match**
```yaml
# Matches only the node named "SFO"
path: SFO
```

**2. Prefix Match**
```yaml
# Matches all nodes starting with "SEA/spine/"
path: SEA/spine/
# Result: SEA/spine/switch-1, SEA/spine/switch-2, etc.
```

**3. Wildcard Patterns**
```yaml
# Matches nodes starting with "SEA/leaf" followed by any characters
path: SEA/leaf*
# Result: SEA/leaf1/switch-1, SEA/leaf2/switch-1, etc.
```

**4. Regex Patterns with Anchoring**
```yaml
# Matches spine nodes with specific numbering
path: ^dc1/spine/switch-[1-3]$
# Result: dc1/spine/switch-1, dc1/spine/switch-2, dc1/spine/switch-3
```

**5. Complex Regex with Alternation**
```yaml
# Matches either spine or leaf nodes in dc1
path: ^dc1/(spine|leaf)/switch-\d+$
# Result: dc1/spine/switch-1, dc1/leaf/switch-1, etc.
```

### Capturing Groups and Node Grouping

When using capturing groups `(...)` in regex patterns, NetGraph groups matching nodes based on the captured values:

**Single Capturing Group:**
```yaml
# Pattern: (SEA/leaf\d)
# Matches: SEA/leaf1/switch-1, SEA/leaf1/switch-2, SEA/leaf2/switch-1, SEA/leaf2/switch-2
# Groups created:
#   "SEA/leaf1": [SEA/leaf1/switch-1, SEA/leaf1/switch-2]
#   "SEA/leaf2": [SEA/leaf2/switch-1, SEA/leaf2/switch-2]
```

**Multiple Capturing Groups:**
```yaml
# Pattern: (dc\d+)/(spine|leaf)/switch-(\d+)
# Matches: dc1/spine/switch-1, dc1/leaf/switch-2, dc2/spine/switch-1
# Groups created (joined with '|'):
#   "dc1|spine|1": [dc1/spine/switch-1]
#   "dc1|leaf|2": [dc1/leaf/switch-2]
#   "dc2|spine|1": [dc2/spine/switch-1]
```

**No Capturing Groups:**
```yaml
# Pattern: SEA/spine/switch-\d+
# All matching nodes are grouped under the original pattern string:
#   "SEA/spine/switch-\\d+": [SEA/spine/switch-1, SEA/spine/switch-2, ...]
```

### Usage in Different DSL Sections

**Adjacency Matching:**

In `adjacency` blocks (both in blueprints and top-level network):
- `source` and `target` fields accept regex patterns
- Blueprint paths can be relative (no leading `/`) or absolute (with leading `/`)
- Relative paths are resolved relative to the blueprint instance's path

```yaml
adjacency:
  - source: "^my_clos1/leaf/switch-\\d+$"
    target: "^my_clos1/spine/switch-\\d+$"
    pattern: mesh
```

**Node and Link Overrides:**

Use `path` field for nodes or `source`/`target` for links:

```yaml
node_overrides:
  - path: ^my_clos1/spine/switch-(1|3|5)$  # Specific switches
    disabled: true
    attrs:
      maintenance_mode: "active"

link_overrides:
  - source: ^my_clos1/leaf/switch-1$
    target: ^my_clos1/spine/switch-1$
    disabled: true
```

**Workflow Steps:**

Workflow steps like `EnableNodes`, `CapacityProbe`, etc., use path patterns:

```yaml
workflow:
  - step_type: EnableNodes
    path: "^my_clos2/leaf/switch-\\d+$"  # All leaf switches
    count: 4
    
  - step_type: CapacityProbe
    source_path: "^(dc\\d+)/client"  # Capturing group creates per-DC groups
    sink_path: "^(dc\\d+)/server"
    mode: pairwise  # Test dc1 client -> dc1 server, dc2 client -> dc2 server
```

### Best Practices

1. **Use anchors for precision**: Always use `$` at the end if you want exact matches
2. **Escape special characters in YAML**: 
   - For digit patterns: Use `\\d+` instead of `\d+` in quoted YAML strings
   - For simple wildcards: `.*/spine/.*` works directly in YAML
   - In Python code: Use raw strings `r"pattern"` or double escaping `"\\d+"`
3. **Test patterns**: Use capturing groups strategically to create meaningful node groups
4. **Relative vs absolute paths**: In blueprints, prefer relative paths for reusability
5. **Group meaningfully**: Design capturing groups to create logical node groupings for workflow steps

### Common Pitfalls

1. **Missing end anchors**: `switch-1` matches `switch-10`, `switch-11`, etc.
   - Fix: Use `switch-1$` for exact match
   
2. **YAML escaping inconsistencies**: 
   - Simple patterns like `.*` work directly: `path: .*/spine/.*`
   - Complex patterns need escaping: `path: "spine-\\d+$"`
   - Python code always needs proper escaping: `"(SEA/leaf\\d)"`
   
3. **Greedy matching**: `.*` can match more than intended
   - Fix: Use specific patterns like `[^/]+` to match within path segments
   
4. **Empty groups**: Patterns that don't match any nodes create empty results
   - Fix: Test patterns against your actual node names

### Regex Escaping Reference

NetGraph processes regex patterns differently depending on context:

**YAML Files (Scenarios):**
```yaml
# Simple wildcards - no escaping needed
adjacency:
  - source: .*/spine/.*    # Matches any spine nodes
    target: .*/spine/.*

# Complex patterns - use quotes and double backslashes  
node_overrides:
  - path: "spine-\\d+$"    # Matches spine-1, spine-2, etc.
    attrs:
      hw_type: "high_performance"

# Traffic demands with capturing groups
traffic_demands:
  - source_path: "my_clos1/b.*/t1"    # Works in YAML
    sink_path: "my_clos2/b.*/t1"
```

**Python Code:**
```python
# Use raw strings (preferred)
pattern = r"^S(\d+)$"
```

## Command Line Interface

NetGraph provides a command-line interface for running scenarios and generating results:

**Basic Usage:**
```bash
# Run a scenario and output results to stdout as JSON
python -m ngraph run scenario.yaml

# Run a scenario and save results to a file
python -m ngraph run scenario.yaml --results output.json
python -m ngraph run scenario.yaml -r output.json
```

**Example:**
```bash
# Run one of the test scenarios
python -m ngraph run tests/scenarios/scenario_1.yaml --results results.json
```

The CLI will execute the complete workflow defined in the scenario file and output all results in JSON format, including:
- Graph statistics from `BuildGraph` steps
- Flow analysis results from `CapacityProbe` steps
- Any other workflow step outputs
