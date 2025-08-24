# Domain-Specific Language (DSL)

Quick links:

- [Design](design.md) — architecture, model, algorithms, workflow
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

### Direct Node and Link Definitions

**Individual Nodes:**

```yaml
network:
  nodes:
    SEA:
      disabled: true
      risk_groups: ["RiskGroup1", "RiskGroup2"]
      attrs:
        coords: [47.6062, -122.3321]
        hardware:
          component: "LeafRouter"
          count: 1
    SFO:
      attrs:
        coords: [37.7749, -122.4194]
        hardware:
          component: "SpineRouter"
          count: 1
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
         risk_groups: ["RiskGroup1", "RiskGroup2"]
         attrs:
           distance_km: 1369.13
           media_type: "fiber"
           hardware:
             source: {component: "800G-ZR+", count: 1}
             target: {component: "1600G-2xDR4", count: 1}
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
    leaf:
      node_count: 4
      name_template: "leaf-{node_num}"
      risk_groups: ["RG-Leaf"]
      attrs:
        role: "leaf"
    spine:
      node_count: 2
      name_template: "spine-{node_num}"
      risk_groups: ["RG-Spine"]
      attrs:
        role: "spine"
```

**Adjacency Rules:**

```yaml
network:
  adjacency:
    - source: /leaf
      target: /spine
      pattern: "mesh"           # Connect every leaf to every spine
      link_params:
        capacity: 3200
        cost: 1
        # Only the following keys are allowed inside link_params:
        # capacity, cost, disabled, risk_groups, attrs
    - source: /spine
      target: /spine
      pattern: "one_to_one"     # Connect spines pairwise
      link_count: 2              # Create 2 parallel links per adjacency (optional)
      link_params:
        capacity: 1600
        cost: 1
        attrs:
          hardware:
            source: {component: "800G-DR4", count: 2}
            target: {component: "800G-DR4", count: 2}
    # Tip: In selector objects, 'path' also supports 'attr:<name>' (see Node Selection)
```

### Attribute-filtered Adjacency (selector objects)

You can filter the source or target node sets by attributes using the same condition syntax as failure policies. Replace a string `source`/`target` with an object that has `path` and optional `match`:

```yaml
network:
  adjacency:
    - source:
        path: "/leaf"
        match:
          logic: "and"         # default: "or"
          conditions:
            - attr: "role"
              operator: "=="
              value: "leaf"
      target:
        path: "/spine"
        match:
          conditions:
            - attr: "role"
              operator: "=="
              value: "spine"
      pattern: "mesh"
      link_params:
        capacity: 100
        cost: 1
```

Notes:

- `path` uses the same semantics as runtime: regex on node name or `attr:<name>` directive grouping (see Node Selection).
- `match.conditions` uses the shared condition operators implemented in code: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `any_value`, `no_value`.
- Conditions evaluate over a flat view of node attributes combining top-level fields (`name`, `disabled`, `risk_groups`) and `node.attrs`.
- `logic` in the `match` block accepts "and" or "or" (default "or").
- Selectors filter node candidates before the adjacency `pattern` is applied.
- Cross-endpoint predicates (e.g., comparing a source attribute to a target attribute) are not supported.
- Node overrides run before adjacency expansion; link overrides run after adjacency expansion.

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
              value: "core"
      pattern: "mesh"
```

**Connectivity Patterns:**

- `mesh`: Full connectivity between all source and target nodes
- `one_to_one`: Pairwise connections. Compatible sizes means max(|S|,|T|) must be an integer multiple of min(|S|,|T|); mapping wraps modulo the smaller set (e.g., 4×2 and 6×3 valid; 3×2 invalid).

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
- Ordering: `node_overrides` run after node creation (groups and direct nodes) and before any adjacency expansion; `link_overrides` run after adjacency and direct links.
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
        hardware:
          component: "SpineRouter"
          count: 2   # Optional multiplier; defaults to 1 if not set
  links:
    - source: spine-1
      target: leaf-1
      link_params:
        attrs:
          hardware:
            source: {component: "Optic400G", count: 4}
            target: {component: "Optic400G", count: 4}
```

## `risk_groups` - Risk Modeling

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
        hardware:
          component: "ServerChassis"
```

## `vars` - YAML Anchors

Defines reusable values using YAML anchors (`&name`) and aliases (`*name`) for deduplicating complex scenarios:

```yaml
vars:
  default_cap: &cap 10000
  base_attrs: &attrs {cost: 100, region: "dc1"}
  spine_config: &spine_cfg
    hardware:
      component: "SpineRouter"
      count: 1
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

- `SHORTEST_PATHS_ECMP`: Equal-cost multi-path (ECMP) over shortest paths; equal split across paths.
- `SHORTEST_PATHS_WCMP`: Weighted ECMP (WCMP) over equal-cost shortest paths; weighted split (proportional).
- `TE_WCMP_UNLIM`: Traffic engineering weighted multipath (WCMP) with capacity-aware selection; unlimited LSPs.
- `TE_ECMP_16_LSP`: Traffic engineering with 16 ECMP LSPs; equal split across LSPs.
- `TE_ECMP_UP_TO_256_LSP`: Traffic engineering with up to 256 ECMP LSPs; equal split across LSPs.

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
  weighted_modes:                # Example of weighted multi-mode policy
    modes:
      - weight: 0.30
        rules:
          - entity_scope: "risk_group"
            rule_type: "choice"
            count: 1
            weight_by: distance_km
      - weight: 0.35
        rules:
          - entity_scope: "link"
            rule_type: "choice"
            count: 3
            conditions:
              - attr: link_type
                operator: "=="
                value: dc_to_pop
            logic: and
            weight_by: target_capacity
      - weight: 0.25
        rules:
          - entity_scope: "node"
            rule_type: "choice"
            count: 1
            conditions:
              - attr: node_type
                operator: "!="
                value: dc_region
            logic: and
            weight_by: attached_capacity_gbps
      - weight: 0.10
        rules:
          - entity_scope: "link"
            rule_type: "choice"
            count: 4
            conditions:
              - attr: link_type
                operator: "=="
                value: leaf_spine
              - attr: link_type
                operator: "=="
                value: intra_group
              - attr: link_type
                operator: "=="
                value: inter_group
              - attr: link_type
                operator: "=="
                value: internal_mesh
            logic: or
```

**Rule Types:**

- `all`: Select all matching entities
- `choice`: Select specific count of entities
- `random`: Select entities with given probability

Notes:

- Policies are mode-based. Each mode has a non-negative `weight`. One mode is chosen per iteration with probability proportional to weights, then all rules in that mode are applied and their selections are unioned.
- Each rule has `entity_scope` ("node" | "link" | "risk_group"), optional `logic` ("and" | "or"; defaults to "or"), optional `conditions`, and one of `rule_type` parameters (`count` for choice, `probability` for random). `weight_by` can be provided for weighted sampling in `choice` rules.
- Condition language is the same as used in adjacency `match` selectors (see below) and supports: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `any_value`, `no_value`. Conditions evaluate on a flat attribute mapping that includes top-level fields and `attrs`.

## `workflow` - Execution Steps

Define analysis workflow steps:

```yaml
workflow:
  - step_type: NetworkStats
    name: network_statistics
  - step_type: MaximumSupportedDemand
    name: msd_baseline
    matrix_name: baseline_traffic_matrix
  - step_type: TrafficMatrixPlacement
    name: tm_placement
    matrix_name: baseline_traffic_matrix
    failure_policy: weighted_modes
    iterations: 1000
    baseline: true
```

Note: Workflow `source_path` and `sink_path` accept either regex on node names or `attr:<name>` directive to group by node attributes (see Node Selection).

**Common Steps:**

- `BuildGraph`: Export graph to JSON (node-link) for external analysis
- `NetworkStats`: Compute basic statistics
- `MaxFlow`: Monte Carlo capacity analysis between node groups
- `TrafficMatrixPlacement`: Monte Carlo demand placement for a named matrix
- `MaximumSupportedDemand`: Search for `alpha_star` for a named matrix

See [Workflow Reference](workflow.md) for detailed configuration.

## Node Selection

NetGraph supports two ways to select and group nodes:

1. Regex on node name (anchored at the start using `re.match()`)
2. Attribute directive `attr:<name>` to group by a node attribute

Note: The attribute directive is node-only. It applies only in contexts that select nodes:

- Workflow paths: `source_path` and `sink_path`
- Adjacency selectors: the `path` field in `source`/`target` selector objects

For links, risk groups, and failure policies, use `conditions` with an `attr` field in rules (see Failure Simulation) rather than `attr:<name>`.

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

### Attribute Directive For Node Selection

Write `attr:<name>` to group nodes by the value of `node.attrs[<name>]`.
Supported contexts in the DSL:

- Workflow: `source_path` and `sink_path`
- Adjacency selectors: the `path` in `source`/`target` selector objects

Notes:

- Blueprint scoping: In blueprints, `attr:` paths are global and are not
  prefixed by the parent blueprint path.
- Attribute name: `name` must be a simple identifier (`[A-Za-z_]\w*`), and it
  refers to a key in `node.attrs`. Nested keys are not supported here.
- Non-node entities: For links and risk groups (e.g., in failure policies), use
  rule `conditions` with an `attr` field instead of `attr:<name>`.

- Strict detection: Only a full match of `attr:<name>` (where `<name>` matches `[A-Za-z_]\w*`) triggers attribute grouping. Everything else is treated as a normal regex.
- Missing attributes: Nodes without the attribute are omitted.
- Labels: Group labels are the string form of the attribute value.

Examples:

```yaml
workflow:
  - step_type: MaxFlow
    source_path: "attr:metro"  # groups by metro attribute
    sink_path:   "^metro2/.*"
    mode: "pairwise"
```

Adjacency example using `attr:`:

```yaml
network:
  adjacency:
    - source: { path: "attr:role" }
      target: { path: "^dc2/leaf/.*" }
      pattern: mesh
```
