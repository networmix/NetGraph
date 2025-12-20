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

## Template Syntaxes

The DSL uses three distinct template syntaxes in different contexts:

| Syntax | Example | Context | Purpose |
|--------|---------|---------|---------|
| `[1-3]` | `dc[1-3]/rack[a,b]` | Group names | Generate multiple groups |
| `$var` / `${var}` | `pod${p}/leaf` | Adjacency, demands | Template expansion with `expand_vars` |
| `{node_num}` | `srv-{node_num}` | `name_template` | Node naming (1-indexed) |

**These syntaxes are not interchangeable.** Each works only in its designated context.

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

- `path` is a regex pattern matched against node names (anchored at start via Python `re.match`).
- `match.conditions` uses the shared condition operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `any_value`, `no_value`.
- Conditions evaluate over a flat view of node attributes combining top-level fields (`name`, `disabled`, `risk_groups`) and `node.attrs`.
- `logic` in the `match` block accepts "and" or "or" (default "or").
- Selectors filter node candidates before the adjacency `pattern` is applied.
- Cross-endpoint predicates (e.g., comparing a source attribute to a target attribute) are not supported.
- Node overrides run before adjacency expansion; link overrides run after adjacency expansion.

Path semantics:

- All paths are relative to the current scope. There is no concept of absolute paths.
- Leading `/` is stripped and has no functional effect - `/leaf` and `leaf` are equivalent.
- Within a blueprint, paths resolve relative to the instantiation path. For example, if a blueprint is used under group `pod1`, then `source: /leaf` resolves to `pod1/leaf`.
- At top-level `network.adjacency`, the parent path is empty, so patterns match against full node names.

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

**Scope:** Bracket expansion applies to:

- **Group names** under `network.groups` and `blueprints.*.groups`
- **Risk group names** in top-level `risk_groups` definitions (including children)
- **Risk group membership arrays** on nodes, links, and groups

Component names, direct node names (`network.nodes`), and other string fields treat brackets as literal characters.

**Risk Group Expansion Examples:**

```yaml
# Definition expansion - creates DC1_Power, DC2_Power, DC3_Power
risk_groups:
  - name: "DC[1-3]_Power"

# Membership expansion - assigns to RG1, RG2, RG3
network:
  nodes:
    Server:
      risk_groups: ["RG[1-3]"]
```

### Variable Expansion in Adjacency

Use `$var` or `${var}` syntax for template substitution:

```yaml
adjacency:
  - source: "plane${p}/rack${r}"
    target: "spine${s}"
    expand_vars:
      p: [1, 2]
      r: ["a", "b"]
      s: [1, 2, 3]
    expansion_mode: "cartesian"  # All combinations
    pattern: "mesh"

  - source: "server${idx}"
    target: "switch${idx}"
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
    description: "64-port spine router"
    capex: 50000.0
    power_watts: 2500.0
    power_watts_max: 3000.0
    capacity: 64000.0           # Gbps
    ports: 64
    attrs:
      vendor: "VendorName"
      model: "Model-9000"
    children:
      LineCard400G:
        component_type: "linecard"
        capex: 8000.0
        power_watts: 400.0
        capacity: 12800.0
        ports: 32
        count: 4

  Optic400G:
    component_type: "optic"
    description: "400G pluggable optic"
    capex: 2500.0
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
    # Simple string pattern selectors
    - source: "^servers/.*"
      sink: "^storage/.*"
      demand: 1000
      mode: "combine"
      priority: 1
      flow_policy_config: "SHORTEST_PATHS_ECMP"

    # Dict selectors with attribute-based grouping
    - source:
        group_by: "dc"           # Group nodes by datacenter attribute
      sink:
        group_by: "dc"
      demand: 500
      mode: "pairwise"
      priority: 2

    # Dict selectors with filtering
    - source:
        path: "^dc1/.*"
        match:
          conditions:
            - attr: "role"
              operator: "=="
              value: "leaf"
      sink:
        path: "^dc2/.*"
        match:
          conditions:
            - attr: "role"
              operator: "=="
              value: "spine"
      demand: 200
      mode: "combine"
```

### Variable Expansion in Demands

Use `expand_vars` to generate multiple demands from a template:

```yaml
traffic_matrix_set:
  inter_dc:
    - source: "^${src_dc}/.*"
      sink: "^${dst_dc}/.*"
      demand: 100
      mode: "combine"
      expand_vars:
        src_dc: ["dc1", "dc2"]
        dst_dc: ["dc2", "dc3"]
      expansion_mode: "cartesian"  # All combinations (default)

    - source: "^${dc}/leaf/.*"
      sink: "^${dc}/spine/.*"
      demand: 50
      mode: "pairwise"
      expand_vars:
        dc: ["dc1", "dc2", "dc3"]
      expansion_mode: "zip"        # Paired by index
```

**Expansion Modes:**

- `cartesian`: All combinations of variable values (default)
- `zip`: Pair values by index (lists must have equal length)

### Selector Fields

The `source` and `sink` fields accept either:

- A string regex pattern matched against node names
- A selector object with `path`, `group_by`, and/or `match` fields

### Traffic Modes

- `combine`: Single aggregate flow between source and sink groups
- `pairwise`: Individual flows between all source-sink node pairs

### Flow Policies

- `SHORTEST_PATHS_ECMP`: IP/IGP routing with hash-based ECMP; equal split across equal-cost paths
- `SHORTEST_PATHS_WCMP`: IP/IGP routing with weighted ECMP; proportional split by link capacity
- `TE_WCMP_UNLIM`: MPLS-TE / SDN with capacity-aware WCMP; unlimited tunnels
- `TE_ECMP_16_LSP`: MPLS-TE with exactly 16 ECMP LSPs per demand
- `TE_ECMP_UP_TO_256_LSP`: MPLS-TE with up to 256 ECMP LSPs per demand

See [Flow Policy Presets](design.md#flow-policy-presets) for detailed configuration mapping and real-world network behavior.

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

**Common Steps:**

- `BuildGraph`: Export graph to JSON (node-link) for external analysis
- `NetworkStats`: Compute basic statistics
- `MaxFlow`: Monte Carlo capacity analysis between node groups
- `TrafficMatrixPlacement`: Monte Carlo demand placement for a named matrix
- `MaximumSupportedDemand`: Search for `alpha_star` for a named matrix

See [Workflow Reference](workflow.md) for detailed configuration.

## Node Selection

NetGraph provides a unified selector system for selecting and grouping nodes across adjacency, demands, and workflow steps.

### Selector Forms

Selectors can be specified as:

1. **String pattern**: A regex matched against node names (anchored at start via `re.match()`)
2. **Selector object**: A dict with `path`, `group_by`, and/or `match` fields

At least one of `path`, `group_by`, or `match` must be specified in a selector object.

### String Pattern Examples

```yaml
# Exact match
source: "spine-1"

# Prefix match
source: "dc1/spine/"

# Wildcard patterns
source: "dc1/leaf.*"

# Anchored patterns
source: "^dc1/spine/switch-[1-3]$"

# Alternation
source: "^dc1/(spine|leaf)/.*$"
```

### Capturing Groups for Node Grouping

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

### Attribute-based Grouping

Use the `group_by` field to group nodes by an attribute value:

```yaml
# Group by metro attribute
source:
  group_by: "metro"

# Combine with path filtering
source:
  path: "^dc1/.*"
  group_by: "role"
```

Notes:

- `group_by` refers to a key in `node.attrs`. Nested keys are not supported.
- Nodes without the specified attribute are omitted.
- Group labels are the string form of the attribute value.

### Attribute-based Filtering

Use the `match` field to filter nodes by attribute conditions:

```yaml
source:
  path: "^dc1/.*"
  match:
    logic: "and"           # "and" or "or" (default: "or")
    conditions:
      - attr: "role"
        operator: "=="
        value: "leaf"
      - attr: "tier"
        operator: ">="
        value: 2
```

**Supported operators:** `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `in`, `not_in`, `any_value`, `no_value`

### Workflow Examples

```yaml
workflow:
  - step_type: MaxFlow
    source:
      group_by: "metro"      # Group by metro attribute
    sink: "^metro2/.*"       # String pattern
    mode: "pairwise"
```

### Adjacency Examples

```yaml
network:
  adjacency:
    - source:
        group_by: "role"
      target:
        path: "^dc2/leaf/.*"
      pattern: mesh
```

### Notes

- For links, risk groups, and failure policies, use `conditions` with an `attr` field in rules (see Failure Simulation).
- Blueprint scoping: In blueprints, paths are relative to the blueprint instantiation path.
