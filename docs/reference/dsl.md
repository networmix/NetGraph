# Domain-Specific Language (DSL)

Quick links:

- [Workflow Reference](workflow.md) — analysis workflow configuration and execution
- [CLI Reference](cli.md) — command-line tools for running scenarios
- [API Reference](api.md) — Python API for programmatic scenario creation
- [Auto-Generated API Reference](api-full.md) — complete class and method documentation

This document describes the DSL for defining network scenarios in NetGraph. Scenarios are YAML files that describe network topology, traffic demands, and analysis workflows.

## Overview

A scenario file defines a complete network simulation including:

- **Network topology**: Nodes, links, and their relationships, as well as risk groups
- **Analysis configuration**: Traffic demands, failure policies, workflows
- **Reusable components**: Blueprints, hardware definitions

The DSL enables both simple direct definitions and complex hierarchical structures with templates and parameters.

## Top-Level Keys

```yaml
network:                 # Network topology (required)
blueprints:              # Reusable network templates
components:              # Hardware component library
risk_groups:             # Failure correlation groups
vars:                    # YAML anchors and variables for reuse
traffic_matrix_set:      # Traffic demand definitions
failure_policy_set:      # Failure simulation policies
workflow:                # Analysis execution steps
```

## `network` - Core Foundation

The only required section. Defines network topology through nodes and links.

**Basic Properties:**

```yaml
network:
  name: "NetworkName"     # Optional network identifier
  version: "1.0"          # Optional version
```

### Direct Node and Link Definitions

**Individual Nodes:**

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

Recognized keys for each node entry:

- `disabled`: boolean (optional)
- `attrs`: mapping of attributes (optional)
- `risk_groups`: list of risk-group names (optional)

**Individual Links:**

```yaml
network:
  links:
    - source: SEA
      target: SFO
      link_params:
        capacity: 200
        cost: 6846
        attrs:
          distance_km: 1369.13
          media_type: "fiber"
```

Recognized keys for each link entry:

- `source`, `target`: node names (required)
- `link_params`: mapping with only these keys allowed: `capacity`, `cost`, `disabled`, `risk_groups`, `attrs`
- `link_count`: integer number of parallel links to create (optional; default 1)

### Group-Based Definitions

**Node Groups:**

```yaml
network:
  groups:
    servers:
      node_count: 4
      name_template: "server-{node_num}"
      attrs:
        role: "compute"
    switches:
      node_count: 2
      name_template: "sw-{node_num}"
      attrs:
        role: "network"
```

**Adjacency Rules:**

```yaml
network:
  adjacency:
    - source: /servers
      target: /switches
      pattern: "mesh"           # Connect every server to every switch
      link_params:
        capacity: 10
        cost: 1
        # Only the following keys are allowed inside link_params:
        # capacity, cost, disabled, risk_groups, attrs
    - source: /switches
      target: /switches
      pattern: "one_to_one"     # Connect switches pairwise
      link_count: 2              # Create 2 parallel links per adjacency (optional)
      link_params:
        capacity: 40
        cost: 1
```

### Attribute-filtered Adjacency (selector objects)

You can filter the source or target node sets by attributes using the same condition syntax as failure policies. Replace a string `source`/`target` with an object that has `path` and optional `match`:

```yaml
network:
  adjacency:
    - source:
        path: "/servers"
        match:
          logic: "and"         # default: "or"
          conditions:
            - attr: "role"
              operator: "=="
              value: "compute"
            - attr: "rack"
              operator: "!="
              value: "rack-9"
      target:
        path: "/switches"
        match:
          conditions:
            - attr: "tier"
              operator: "=="
              value: "spine"
      pattern: "mesh"
      link_params:
        capacity: 100
        cost: 1
```

Notes:

- `path` uses the same semantics as before: regex on node name or `attr:<name>` directive grouping.
- `match.conditions` uses the failure-policy language (same operators as below): `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `any_value`, `no_value`.
- Conditions evaluate over a flat view of node attributes combining top-level fields (`name`, `disabled`, `risk_groups`) and `node.attrs`.
- `logic` in the `match` block accepts `"and"` or `"or"` (default `"or"`).
- Selectors filter node candidates before the adjacency `pattern` is applied.
- Cross-endpoint predicates (e.g., comparing a source attribute to a target attribute) are not supported.

Path semantics inside blueprints:

- Within a blueprint's `adjacency`, a leading `/` is treated as relative to the blueprint instantiation path, not a global root. For example, if a blueprint is used under group `pod1`, then `source: /leaf` resolves to `pod1/leaf`.

Example with OR logic to match multiple roles:

```yaml
network:
  adjacency:
    - source:
        path: "/metro1/dc[1-1]"
        match:
          conditions:
            - attr: "role"
              operator: "=="
              value: "dc"
      target:
        path: "/metro1/pop[1-2]"
        match:
          logic: "or"
          conditions:
            - attr: "role"
              operator: "=="
              value: "leaf"
            - attr: "role"
              operator: "=="
              value: "spine"
      pattern: "mesh"
```

**Connectivity Patterns:**

- `mesh`: Full connectivity between all source and target nodes
- `one_to_one`: Pairwise connections (requires compatible group sizes)

### Bracket Expansion

Create multiple similar groups using bracket notation:

```yaml
network:
  groups:
    dc[1-3]/rack[a,b]:     # Creates dc1/racka, dc1/rackb, dc2/racka, etc.
      node_count: 4
      name_template: "srv-{node_num}"
```

**Expansion Types:**

- Numeric ranges: `[1-4]` → 1, 2, 3, 4
- Explicit lists: `[red,blue,green]` → red, blue, green

### Variable Expansion in Adjacency

```yaml
adjacency:
  - source: "plane{p}/rack{r}"
    target: "spine{s}"
    expand_vars:
      p: [1, 2]
      r: ["a", "b"]
      s: [1, 2, 3]
    expansion_mode: "cartesian"  # All combinations
    pattern: "mesh"

  - source: "server{idx}"
    target: "switch{idx}"
    expand_vars:
      idx: [1, 2, 3, 4]
    expansion_mode: "zip"        # Paired by index
    pattern: "one_to_one"
```

## `blueprints` - Reusable Templates

Templates for network segments that can be instantiated multiple times:

```yaml
blueprints:
  leaf_spine:
    groups:
      leaf:
        node_count: 4
        name_template: "leaf-{node_num}"
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
    adjacency:
      - source: /leaf
        target: /spine
        pattern: mesh
        link_params:
          capacity: 40
          cost: 1

network:
  groups:
    pod1:
      use_blueprint: leaf_spine
    pod2:
      use_blueprint: leaf_spine
      parameters:                # Override blueprint parameters
        leaf.node_count: 6
        spine.name_template: "core-{node_num}"
```

**Blueprint Features:**

- Define groups and adjacency rules once, reuse multiple times
- Override parameters using dot notation during instantiation
- Hierarchical naming: `pod1/leaf/leaf-1`, `pod2/spine/core-1`

## Node and Link Overrides

Modify specific nodes or links after initial creation:

```yaml
network:
  node_overrides:
    - path: "^pod1/spine/.*$"           # Regex pattern matching
      disabled: true
      attrs:
        maintenance_mode: "active"
    - path: "server-[1-3]$"             # Specific node subset
      attrs:
        priority: "high"

  link_overrides:
    - source: "^pod1/leaf/.*$"
      target: "^pod1/spine/.*$"
      link_params:
        capacity: 100                   # Override capacity
    - source: ".*/spine/.*"
      target: ".*/spine/.*"
      any_direction: true               # Bidirectional matching
      link_params:
        cost: 5
        attrs:
          link_type: "backbone"

Notes:

- For `link_overrides`, only the keys `source`, `target`, `link_params`, and optional `any_direction` are allowed at the top level. All parameter changes must be nested under `link_params`.
- `any_direction` defaults to `true` if omitted.
```

## `components` - Hardware Library

Define hardware components with attributes for cost and power modeling:

```yaml
components:
  SpineRouter:
    component_type: "chassis"
    cost: 50000.0
    power_watts: 2500.0
    capacity: 64000.0           # Gbps
    ports: 64
    attrs:
      vendor: "VendorName"
      model: "Model-9000"
    children:
      LineCard400G:
        component_type: "linecard"
        cost: 8000.0
        power_watts: 400.0
        capacity: 12800.0
        ports: 32
        count: 4

  Optic400G:
    component_type: "optic"
    cost: 2500.0
    power_watts: 12.0
    capacity: 400.0
    attrs:
      reach: "10km"
      wavelength: "1310nm"
```

**Component Usage:**

```yaml
network:
  nodes:
    spine-1:
      attrs:
        hw_component: "SpineRouter"
        hw_count: 2   # Optional multiplier; defaults to 1 if not set
  links:
    - source: spine-1
      target: leaf-1
      link_params:
        attrs:
          hw_component: "Optic400G"
          hw_count: 4  # Optional multiplier for link hardware
```

## `risk_groups` - Hardware Risk Modeling

Define hierarchical failure correlation groups:

```yaml
risk_groups:
  - name: "Rack1"
    attrs:
      location: "DC1_Floor2"
    children:
      - name: "Card1.1"
        children:
          - name: "PortGroup1.1.1"
      - name: "Card1.2"
  - name: "PowerSupplyA"
    attrs:
      type: "power_infrastructure"
```

Nodes and links reference risk groups via `risk_groups` attribute:

```yaml
network:
  nodes:
    server-1:
      risk_groups: ["Rack1"]
      attrs:
        hw_component: "ServerChassis"
```

## `vars` - YAML Anchors

Defines reusable values using YAML anchors (`&name`) and aliases (`*name`) for deduplicating complex scenarios:

```yaml
vars:
  default_cap: &cap 10000
  base_attrs: &attrs {cost: 100, region: "dc1"}
  spine_config: &spine_cfg
    hw_component: "SpineRouter"
    power_budget: 2500

network:
  nodes:
    spine-1: {attrs: {<<: *attrs, <<: *spine_cfg, capacity: *cap}}
    spine-2: {attrs: {<<: *attrs, <<: *spine_cfg, capacity: *cap, region: "dc2"}}
```

**Anchor Types:**

- **Scalar**: `&cap 10000` - Reference primitive values
- **Mapping**: `&attrs {cost: 100}` - Reference objects
- **Merge**: `<<: *attrs` - Merge properties with override capability

**Processing Behavior:**

- Anchors are resolved during YAML parsing, before schema validation
- The `vars` section itself is ignored by NetGraph runtime logic
- Anchors can be defined in any section, not just `vars`
- Merge operations follow YAML 1.1 semantics (later keys override earlier ones)

## `traffic_matrix_set` - Traffic Analysis

Define traffic demand patterns for capacity analysis:

```yaml
traffic_matrix_set:
  production:
    - name: "server_to_storage"
      source_path: "^servers/.*"
      sink_path: "^storage/.*"
      demand: 1000               # Traffic volume
      mode: "combine"            # Aggregate demand
      priority: 1
      flow_policy_config: "SHORTEST_PATHS_ECMP"

    - name: "inter_dc_backup"
      source_path: "^dc1/.*"
      sink_path: "^dc2/.*"
      demand: 500
      mode: "pairwise"           # Distributed demand
      priority: 2
```

**Traffic Modes:**

- `combine`: Single aggregate flow between source and sink groups
- `pairwise`: Individual flows between all source-sink node pairs

**Flow Policies:**

- `SHORTEST_PATHS_ECMP`: Equal-cost multi-path routing
- `SHORTEST_PATHS_UCMP`: Unequal-cost multi-path routing
- `TE_ECMP_16_LSP`: Traffic engineering with 16 ECMP LSPs

## `failure_policy_set` - Failure Simulation

Define failure policies for resilience testing:

```yaml
failure_policy_set:
  single_link_failure:
    modes:                       # Weighted modes; exactly one mode fires per iteration
      - weight: 1.0
        rules:
          - entity_scope: "link"
            rule_type: "choice"
            count: 1

  random_failures:
    fail_risk_groups: true       # Optional expansion by shared-risk groups
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "node"
            rule_type: "random"
            probability: 0.001
          - entity_scope: "link"
            rule_type: "random"
            probability: 0.002

  maintenance_scenario:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "node"
            conditions:
              - attr: "maintenance_mode"
                operator: "=="
                value: "scheduled"
            rule_type: "all"
```

**Rule Types:**

- `all`: Select all matching entities
- `choice`: Select specific count of entities
- `random`: Select entities with given probability

Notes:

- Policies are mode-based. Each mode has a non-negative `weight`. One mode is chosen per iteration with probability proportional to weights, then all rules in that mode are applied and their selections are unioned.
- Each rule has `entity_scope` ("node" | "link" | "risk_group"), optional `logic` ("and" | "or"; defaults to "or"), optional `conditions`, and one of `rule_type` parameters (`count` for choice, `probability` for random). `weight_by` can be provided for weighted sampling in `choice` rules.
- Condition language is the same as used in adjacency `match` selectors (see below) and supports: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `any_value`, `no_value`. Conditions evaluate on a flat attribute mapping that includes top-level fields and `attrs`.

**Conditions:**

- Target entities based on attributes
- Support operators: `==`, `!=`, `>`, `<`, `>=`, `<=`, `contains`, `not_contains`

## `workflow` - Execution Steps

Define analysis workflow steps:

```yaml
workflow:
  - step_type: BuildGraph
  - step_type: CapacityEnvelopeAnalysis
    name: "capacity_analysis"
    source_path: "^servers/.*"
    sink_path: "^storage/.*"
    mode: "combine"
    failure_policy: "single_link_failure"
    iterations: 1000
    parallelism: 4
    baseline: true
```

**Common Steps:**

- `BuildGraph`: Build network graph for analysis
- `NetworkStats`: Compute network statistics
- `CapacityEnvelopeAnalysis`: Monte Carlo capacity analysis

See [Workflow Reference](workflow.md) for detailed configuration.

## Node Selection

NetGraph supports two ways to select and group nodes:

1. Regex on node name (anchored at the start using `re.match()`)
2. Attribute directive `attr:<name>` to group by a node attribute

**Regex Examples:**

```yaml
# Exact match
path: "spine-1"

# Prefix match
path: "dc1/spine/"

# Wildcard patterns
path: "dc1/leaf.*"

# Anchored patterns
path: "^dc1/spine/switch-[1-3]$"

# Alternation
path: "^dc1/(spine|leaf)/.*$"
```

**Regex Capturing Groups:**

Regex capturing groups create node groupings for analysis:

```yaml
# Single group: (dc\d+)
# Creates groups: "dc1", "dc2", etc.

# Multiple groups: (dc\d+)/(spine|leaf)/switch-(\d+)
# Creates groups: "dc1|spine|1", "dc1|leaf|2", etc.
```

**Group Behavior:**

- Single capturing group: Group by captured value
- Multiple capturing groups: Join with `|` separator
- No capturing groups: Group by original pattern string

### Attribute Directive

Write `attr:<name>` to group nodes by the value of `node.attrs[<name>]`.

- Strict detection: Only a full match of `attr:<name>` (where `<name>` matches `[A-Za-z_]\w*`) triggers attribute grouping. Everything else is treated as a normal regex.
- Missing attributes: Nodes without the attribute are omitted.
- Labels: Group labels are the string form of the attribute value.

Examples:

```yaml
workflow:
  - step_type: CapacityEnvelopeAnalysis
    source_path: "attr:dc_site_id"  # groups by integer dc_site_id attribute
    sink_path:   "attr:role"        # groups by role attribute
    mode: "pairwise"
```

Mixing modes works:

```yaml
workflow:
  - step_type: MaxFlow
    source_path: "attr:metro"
    sink_path:   "SFO/servers/.*"   # regex
    mode: "combine"
```
