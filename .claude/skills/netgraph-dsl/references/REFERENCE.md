# NetGraph DSL Reference

Complete reference documentation for the NetGraph scenario DSL.

> For a quick start guide and common patterns, see the main [SKILL.md](../SKILL.md).
> For complete working examples, see [EXAMPLES.md](EXAMPLES.md).

## Syntax Overview

### Template and Expansion Syntaxes

NetGraph DSL uses three distinct template syntaxes in different contexts:

| Syntax | Example | Where | Purpose |
|--------|---------|-------|---------|
| **Brackets** `[1-3]` | `dc[1-3]/rack[a,b]` | Group names, risk groups | Generate multiple entities |
| **Variables** `$var` | `pod${p}/leaf` | Adjacency, demands | Template expansion |
| **Format** `{node_num}` | `srv-{node_num}` | `name_template` | Node naming |

**Important**: These syntaxes are NOT interchangeable:

- `[1-3]` works in group names and risk groups (definitions and memberships), not components
- `${var}` requires `expand_vars` dict; only works in adjacency `source`/`target` and demand `source`/`sink`
- `{node_num}` is the only placeholder available in `name_template` (Python format syntax)

### Endpoint Naming Conventions

| Context | Fields | Terminology |
|---------|--------|-------------|
| Links, adjacency, link_overrides | `source`, `target` | Graph edge |
| Traffic demands, workflow steps | `source`, `sink` | Max-flow |

**Why different?** Links use graph terminology (`target` = edge destination). Traffic demands and analysis use max-flow terminology (`sink` = flow destination).

### Expansion Controls in Traffic Demands

Traffic demands have three expansion-related fields:

| Field | Values | Default | Purpose |
|-------|--------|---------|---------|
| `mode` | `combine`, `pairwise` | `combine` | How source/sink nodes pair |
| `group_mode` | `flatten`, `per_group`, `group_pairwise` | `flatten` | How grouped nodes expand |
| `expansion_mode` | `cartesian`, `zip` | `cartesian` | How `expand_vars` combine |

See detailed sections below for each mechanism.

## Top-Level Keys

| Key | Required | Purpose |
|-----|----------|---------|
| `network` | Yes | Network topology (nodes, links, groups, adjacency) |
| `blueprints` | No | Reusable topology templates |
| `components` | No | Hardware component library |
| `risk_groups` | No | Failure correlation groups |
| `vars` | No | YAML anchors for value reuse |
| `traffic_matrix_set` | No | Traffic demand definitions |
| `failure_policy_set` | No | Failure simulation policies |
| `workflow` | No | Analysis execution steps |
| `seed` | No | Master seed for reproducible random operations |

## Network Metadata

```yaml
network:
  name: "My Network"       # Optional: network name
  version: "1.0"           # Optional: version string or number
  nodes: ...
  links: ...
```

## Network Topology

### Direct Node Definitions

```yaml
network:
  nodes:
    Seattle:
      disabled: false           # Optional: disable node
      risk_groups: ["RG1"]      # Optional: failure correlation
      attrs:                    # Optional: custom attributes
        coords: [47.6062, -122.3321]
        role: core
        hardware:
          component: "SpineRouter"
          count: 1
```

**Allowed node keys**: `disabled`, `attrs`, `risk_groups`

### Direct Link Definitions

```yaml
network:
  links:
    - source: Seattle
      target: Portland
      link_params:              # Required wrapper
        capacity: 100.0
        cost: 10
        disabled: false
        risk_groups: ["RG_Seattle_Portland"]
        attrs:
          distance_km: 280
          media_type: fiber
          hardware:
            source:
              component: "800G-ZR+"
              count: 1
              exclusive: false   # Optional: unsharable usage (rounds up)
            target:
              component: "800G-ZR+"
              count: 1
      link_count: 2             # Optional: parallel links
```

**Allowed link keys**: `source`, `target`, `link_params`, `link_count`

**Allowed link_params keys**: `capacity`, `cost`, `disabled`, `risk_groups`, `attrs`

**Link hardware per-end fields**: `component`, `count`, `exclusive`

### Node Groups

Groups create multiple nodes from a template:

```yaml
network:
  groups:
    servers:
      node_count: 4
      name_template: "srv-{node_num}"
      disabled: false
      risk_groups: ["RG_Servers"]
      attrs:
        role: compute
```

Creates: `servers/srv-1`, `servers/srv-2`, `servers/srv-3`, `servers/srv-4`

**Allowed group keys**: `node_count`, `name_template`, `attrs`, `disabled`, `risk_groups`

### Bracket Expansion

Create multiple similar groups using bracket notation:

```yaml
network:
  groups:
    dc[1-3]/rack[a,b]:
      node_count: 4
      name_template: "srv-{node_num}"
```

**Expansion types**:

- Numeric ranges: `[1-4]` -> 1, 2, 3, 4
- Explicit lists: `[a,b,c]` -> a, b, c
- Mixed: `[1,3,5-7]` -> 1, 3, 5, 6, 7

Multiple brackets create Cartesian product.

**Scope**: Bracket expansion applies to:

- **Group names** under `network.groups` and `blueprints.*.groups`
- **Risk group names** in top-level `risk_groups` definitions (including children)
- **Risk group membership arrays** on nodes, links, and groups

It does NOT apply to: component names, direct node names (`network.nodes`), or other string fields.

**Risk group expansion examples**:

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

### Path Patterns

Path patterns in selectors and overrides are **regex patterns** matched against node names using `re.match()` (anchored at start).

**Key behaviors**:

- Paths are matched from the **start** of the node name (no implicit `.*` prefix)
- Node names are hierarchical: `group/subgroup/node-1`
- Leading `/` is stripped before matching (has no functional effect)
- All paths are relative to the current scope

**Examples**:

| Pattern | Matches | Does NOT Match |
|---------|---------|----------------|
| `leaf` | `leaf/leaf-1`, `leaf/leaf-2` | `pod1/leaf/leaf-1` |
| `pod1/leaf` | `pod1/leaf/leaf-1` | `pod2/leaf/leaf-1` |
| `.*leaf` | `leaf/leaf-1`, `pod1/leaf/leaf-1` | (matches any path containing "leaf") |
| `pod[12]/leaf` | `pod1/leaf/leaf-1`, `pod2/leaf/leaf-1` | `pod3/leaf/leaf-1` |

**Path scoping**:

- **At top-level** (`network.adjacency`): Parent path is empty, so patterns match against full node names. `/leaf` and `leaf` are equivalent.
- **In blueprints**: Paths are relative to instantiation path. If `pod1` uses a blueprint with `source: /leaf`, the pattern becomes `pod1/leaf`.

### Adjacency Rules

```yaml
network:
  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params:
        capacity: 100
        cost: 1
      link_count: 1
```

**Patterns**:

- `mesh`: Full connectivity (every source to every target)
- `one_to_one`: Pairwise with modulo wrap. Sizes must have multiple factor (4-to-2 OK, 3-to-2 ERROR)

### Adjacency Selectors

Filter nodes using attribute conditions:

```yaml
network:
  adjacency:
    - source:
        path: "/datacenter"
        match:
          logic: and           # "and" or "or" (default: "or")
          conditions:
            - attr: role
              operator: "=="
              value: leaf
            - attr: tier
              operator: ">="
              value: 2
      target:
        path: "/datacenter"
        match:
          conditions:
            - attr: role
              operator: "=="
              value: spine
      pattern: mesh
      link_params:
        capacity: 100
```

**Condition operators**:

| Operator | Description |
|----------|-------------|
| `==` | Equal |
| `!=` | Not equal |
| `<`, `<=`, `>`, `>=` | Numeric comparison |
| `contains` | String/list contains value |
| `not_contains` | String/list does not contain |
| `in` | Value in list |
| `not_in` | Value not in list |
| `any_value` | Attribute exists and is not None |
| `no_value` | Attribute missing or None |

### Variable Expansion in Adjacency

Use `$var` or `${var}` syntax in adjacency `source`/`target` fields:

```yaml
network:
  adjacency:
    - source: "plane${p}/rack"
      target: "spine${s}"
      expand_vars:
        p: [1, 2]
        s: [1, 2, 3]
      expansion_mode: cartesian
      pattern: mesh
      link_params:
        capacity: 100
```

**Expansion modes**:

- `cartesian` (default): All combinations (2 * 3 = 6 expansions)
- `zip`: Pair by index (lists must have equal length)

**Expansion limit**: Maximum 10,000 expansions per template. Exceeding this raises an error.

## Blueprints

Reusable topology templates:

```yaml
blueprints:
  clos_pod:
    groups:
      leaf:
        node_count: 4
        name_template: "leaf-{node_num}"
        attrs:
          role: leaf
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
        attrs:
          role: spine
    adjacency:
      - source: /leaf
        target: /spine
        pattern: mesh
        link_params:
          capacity: 100
          cost: 1
```

### Blueprint Usage

```yaml
network:
  groups:
    pod1:
      use_blueprint: clos_pod
      attrs:                    # Merged into all subgroup nodes
        location: datacenter_east
      parameters:               # Override blueprint defaults
        leaf.node_count: 6
        spine.name_template: "core-{node_num}"
        leaf.attrs.priority: high
```

Creates: `pod1/leaf/leaf-1`, `pod1/spine/spine-1`, etc.

**Parameter override syntax**: `<group>.<field>` or `<group>.attrs.<nested_key>`

### Blueprint Path Scoping

All paths are relative to the current scope. In blueprints, paths resolve relative to the instantiation path:

```yaml
blueprints:
  my_bp:
    adjacency:
      - source: /leaf   # Becomes pod1/leaf when instantiated as pod1
        target: spine   # Also becomes pod1/spine (leading / is optional)
        pattern: mesh
```

**Note**: Leading `/` is stripped and has no functional effect. Both `/leaf` and `leaf` produce the same result. The `/` serves as a visual convention indicating "from scope root".

## Node and Link Overrides

Modify nodes/links after initial creation:

```yaml
network:
  node_overrides:
    - path: "^pod1/spine/.*$"  # Regex pattern
      disabled: true
      risk_groups: ["Maintenance"]
      attrs:
        maintenance_mode: active

  link_overrides:
    - source: "^pod1/leaf/.*$"
      target: "^pod1/spine/.*$"
      any_direction: true       # Match both directions (default: true)
      link_params:
        capacity: 200
        attrs:
          upgraded: true
```

**Link override fields**:

- `source`, `target`: Regex patterns for matching link endpoints
- `any_direction`: If `true` (default), matches both A→B and B→A directions
- `link_params`: Parameters to override (`capacity`, `cost`, `disabled`, `risk_groups`, `attrs`)

**Processing order**:

1. Groups and direct nodes created
2. **Node overrides applied**
3. Adjacency and blueprint adjacencies expanded
4. Direct links created
5. **Link overrides applied**

## Components Library

Define hardware components for cost/power modeling:

```yaml
components:
  SpineRouter:
    component_type: chassis
    description: "64-port spine router"
    capex: 50000.0              # Cost per instance
    power_watts: 2500.0         # Typical power usage
    power_watts_max: 3000.0     # Peak power usage
    capacity: 64000.0           # Gbps
    ports: 64
    attrs:
      vendor: "Example Corp"
    children:
      LineCard400G:
        component_type: linecard
        capex: 8000.0
        power_watts: 400.0
        capacity: 12800.0
        ports: 32
        count: 4

  Optic400G:
    component_type: optic
    description: "400G pluggable optic"
    capex: 2500.0
    power_watts: 12.0
    capacity: 400.0
```

**Component fields**:

| Field | Description |
|-------|-------------|
| `component_type` | Category: `chassis`, `linecard`, `optic`, etc. |
| `description` | Human-readable description |
| `capex` | Cost per instance |
| `power_watts` | Typical power consumption (watts) |
| `power_watts_max` | Peak power consumption (watts) |
| `capacity` | Capacity in Gbps |
| `ports` | Number of ports |
| `count` | Instance count (for children) |
| `attrs` | Additional metadata |
| `children` | Nested child components |

**Usage in nodes/links**:

```yaml
network:
  nodes:
    spine-1:
      attrs:
        hardware:
          component: "SpineRouter"
          count: 2
```

## Risk Groups

Define hierarchical failure correlation:

```yaml
risk_groups:
  - name: "Rack1"
    disabled: false             # Optional: disable on load
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

**Risk group fields**: `name` (required), `disabled`, `attrs`, `children`

## Traffic Demands

```yaml
traffic_matrix_set:
  production:
    - source: "^dc1/.*"
      sink: "^dc2/.*"
      demand: 1000
      demand_placed: 0.0      # Optional: pre-placed portion
      mode: combine
      group_mode: flatten     # How to handle grouped nodes
      priority: 1
      flow_policy_config: SHORTEST_PATHS_ECMP
      attrs:
        service: web

    - source:
        path: "^datacenter/.*"
        match:
          conditions:
            - attr: role
              operator: "=="
              value: leaf
      sink:
        group_by: metro
      demand: 500
      mode: pairwise
      priority: 2
```

### Traffic Modes

| Mode | Description |
|------|-------------|
| `combine` | Single aggregate flow between source/sink groups via pseudo nodes |
| `pairwise` | Individual flows between all source-sink node pairs |

### Group Modes

When selectors use `group_by`, `group_mode` controls how grouped nodes produce demands:

| Group Mode | Description |
|------------|-------------|
| `flatten` | Flatten all groups into single source/sink sets (default) |
| `per_group` | Create separate demands for each group |
| `group_pairwise` | Create pairwise demands between groups |

### Flow Policies

| Policy | Description |
|--------|-------------|
| `SHORTEST_PATHS_ECMP` | IP/IGP routing with equal-split ECMP |
| `SHORTEST_PATHS_WCMP` | IP/IGP routing with weighted ECMP (by capacity) |
| `TE_WCMP_UNLIM` | MPLS-TE / SDN with unlimited tunnels |
| `TE_ECMP_16_LSP` | MPLS-TE with 16 ECMP LSPs per demand |
| `TE_ECMP_UP_TO_256_LSP` | MPLS-TE with up to 256 ECMP LSPs |

### Variable Expansion in Demands

```yaml
traffic_matrix_set:
  inter_dc:
    - source: "^${src_dc}/.*"
      sink: "^${dst_dc}/.*"
      demand: 100
      expand_vars:
        src_dc: [dc1, dc2]
        dst_dc: [dc2, dc3]
      expansion_mode: cartesian
```

## Failure Policies

Failure policies define how nodes, links, and risk groups fail during Monte Carlo simulations.

### Structure

```yaml
failure_policy_set:
  policy_name:
    attrs: {}                        # Optional metadata
    fail_risk_groups: false          # Expand to shared-risk entities
    fail_risk_group_children: false  # Fail child risk groups recursively
    modes:                           # Required: weighted failure modes
      - weight: 1.0                  # Mode selection weight
        attrs: {}                    # Optional mode metadata
        rules: []                    # Rules applied when mode is selected
```

### Mode Selection

Exactly one mode is selected per failure iteration based on normalized weights:

```yaml
modes:
  - weight: 0.3   # 30% probability of selection
    rules: [...]
  - weight: 0.5   # 50% probability
    rules: [...]
  - weight: 0.2   # 20% probability
    rules: [...]
```

- Modes with zero or negative weight are never selected
- If all weights are non-positive, falls back to the first mode

### Rule Structure

```yaml
rules:
  - entity_scope: link       # Required: node, link, or risk_group
    conditions: []           # Optional: filter conditions
    logic: or                # Condition logic: and | or (default: or)
    rule_type: all           # Selection: all | choice | random (default: all)
    probability: 1.0         # For random: [0.0, 1.0]
    count: 1                 # For choice: number to select
    weight_by: null          # For choice: attribute for weighted sampling
```

### Rule Types

| Type | Description | Parameters |
|------|-------------|------------|
| `all` | Select all matching entities | None |
| `choice` | Random sample from matches | `count`, optional `weight_by` |
| `random` | Each match selected with probability | `probability` in [0, 1] |

### Condition Logic

When multiple conditions are specified:

| Logic | Behavior |
|-------|----------|
| `or` (default) | Entity matches if **any** condition is true |
| `and` | Entity matches if **all** conditions are true |

If no conditions are specified, all entities of the given scope match.

### Weighted Sampling (choice mode)

When `weight_by` is set for `rule_type: choice`:

```yaml
- entity_scope: link
  rule_type: choice
  count: 2
  weight_by: capacity   # Sample proportional to capacity attribute
```

- Uses Efraimidis-Spirakis algorithm for weighted sampling without replacement
- Entities with non-positive or missing weights are sampled uniformly after positive-weight items
- Falls back to uniform sampling if all weights are non-positive

### Risk Group Expansion

```yaml
fail_risk_groups: true
```

When enabled, after initial failures are selected, expands to fail all entities that share a risk group with any failed entity (BFS traversal).

```yaml
fail_risk_group_children: true
```

When enabled and a risk_group is marked as failed, recursively fails all child risk groups.

### Complete Example

```yaml
failure_policy_set:
  weighted_modes:
    attrs:
      description: "Balanced failure simulation"
    fail_risk_groups: true
    fail_risk_group_children: false
    modes:
      # 30% chance: fail 1 risk group weighted by distance
      - weight: 0.3
        rules:
          - entity_scope: risk_group
            rule_type: choice
            count: 1
            weight_by: distance_km

      # 50% chance: fail 1 non-core node weighted by capacity
      - weight: 0.5
        rules:
          - entity_scope: node
            rule_type: choice
            count: 1
            conditions:
              - attr: role
                operator: "!="
                value: core
            logic: and
            weight_by: attached_capacity_gbps

      # 20% chance: random link failures with 1% probability each
      - weight: 0.2
        rules:
          - entity_scope: link
            rule_type: random
            probability: 0.01
```

### Entity Scopes

| Scope | Description |
|-------|-------------|
| `node` | Match against node attributes |
| `link` | Match against link attributes |
| `risk_group` | Match against risk group names/attributes |

## Workflow Steps

```yaml
workflow:
  - step_type: NetworkStats
    name: baseline_stats

  - step_type: MaximumSupportedDemand
    name: msd_baseline
    matrix_name: production
    acceptance_rule: hard
    alpha_start: 1.0
    growth_factor: 2.0
    resolution: 0.05

  - step_type: TrafficMatrixPlacement
    name: tm_placement
    matrix_name: production
    failure_policy: weighted_modes
    iterations: 1000
    parallelism: 8
    alpha_from_step: msd_baseline
    alpha_from_field: data.alpha_star

  - step_type: MaxFlow
    name: capacity_matrix
    source: "^(dc[1-3])$"
    sink: "^(dc[1-3])$"
    mode: pairwise
    failure_policy: single_link
    iterations: 500
    baseline: true

  - step_type: CostPower
    name: cost_analysis
    include_disabled: true
    aggregation_level: 2
```

### Step Types

| Type | Description |
|------|-------------|
| `BuildGraph` | Export graph to JSON (node-link format) |
| `NetworkStats` | Compute basic statistics (node/link counts, degrees) |
| `MaxFlow` | Monte Carlo capacity analysis between node groups |
| `TrafficMatrixPlacement` | Monte Carlo demand placement for a named matrix |
| `MaximumSupportedDemand` | Search for maximum supportable demand scaling (`alpha_star`) |
| `CostPower` | Cost and power estimation from components |

### BuildGraph Parameters

```yaml
- step_type: BuildGraph
  name: build_graph
  add_reverse: true   # Add reverse edges for bidirectional connectivity
```

### NetworkStats Parameters

```yaml
- step_type: NetworkStats
  name: stats
  include_disabled: false   # Include disabled nodes/links in stats
```

### MaxFlow Parameters

```yaml
- step_type: MaxFlow
  name: capacity_analysis
  source: "^servers/.*"
  sink: "^storage/.*"
  mode: combine              # combine | pairwise
  failure_policy: policy_name
  iterations: 1000
  parallelism: auto          # or integer
  baseline: true             # Include baseline (no failures) iteration
  shortest_path: false       # Restrict to shortest paths only
  require_capacity: true     # Path selection considers capacity
  flow_placement: PROPORTIONAL  # PROPORTIONAL | EQUAL_BALANCED
  store_failure_patterns: false
  include_flow_details: false   # Cost distribution per flow
  include_min_cut: false        # Min-cut edge list per flow
```

### TrafficMatrixPlacement Parameters

```yaml
- step_type: TrafficMatrixPlacement
  name: tm_placement
  matrix_name: default
  failure_policy: policy_name
  iterations: 100
  parallelism: auto
  placement_rounds: auto     # or integer
  baseline: false
  include_flow_details: true
  include_used_edges: false
  store_failure_patterns: false
  # Alpha scaling options
  alpha: 1.0                 # Explicit scaling factor
  # Or reference another step's output:
  alpha_from_step: msd_step_name
  alpha_from_field: data.alpha_star
```

### MaximumSupportedDemand Parameters

```yaml
- step_type: MaximumSupportedDemand
  name: msd
  matrix_name: default
  acceptance_rule: hard      # Currently only "hard" supported
  alpha_start: 1.0           # Starting alpha for search
  growth_factor: 2.0         # Growth factor for bracketing (> 1.0)
  alpha_min: 0.000001        # Minimum alpha bound
  alpha_max: 1000000000.0    # Maximum alpha bound
  resolution: 0.01           # Convergence resolution
  max_bracket_iters: 32
  max_bisect_iters: 32
  seeds_per_alpha: 1         # Seeds per alpha (majority vote)
  placement_rounds: auto
```

### CostPower Parameters

```yaml
- step_type: CostPower
  name: cost_power
  include_disabled: false    # Include disabled nodes/links
  aggregation_level: 2       # Hierarchy level for aggregation (split by /)
```

## Selector Reference

Selectors work across adjacency, demands, and workflows.

### String Pattern (Regex)

```yaml
source: "^dc1/spine/.*$"
```

Patterns use Python `re.match()`, anchored at start.

### Selector Object

```yaml
source:
  path: "^dc1/.*"           # Regex on node.name
  group_by: metro           # Group by attribute value
  match:                    # Filter by conditions
    logic: and
    conditions:
      - attr: role
        operator: "=="
        value: spine
  active_only: true         # Exclude disabled nodes
```

At least one of `path`, `group_by`, or `match` must be specified.

### Context-Aware Defaults for active_only

The `active_only` field has context-dependent defaults:

| Context | Default | Rationale |
|---------|---------|-----------|
| `adjacency` | `false` | Links to disabled nodes are created |
| `override` | `false` | Overrides can target disabled nodes |
| `demand` | `true` | Traffic only between active nodes |
| `workflow` | `true` | Analysis uses active nodes only |

### Capture Groups for Labeling

```yaml
# Single capture group
source: "^(dc[1-3])/.*"     # Groups: dc1, dc2, dc3

# Multiple capture groups join with |
source: "^(dc\\d+)/(spine|leaf)/.*"  # Groups: dc1|spine, dc1|leaf
```

## YAML Anchors

Use `vars` section for reusable values:

```yaml
vars:
  default_cap: &cap 10000
  base_attrs: &attrs {cost: 100, region: "dc1"}
  spine_config: &spine_cfg
    hardware:
      component: "SpineRouter"
      count: 1

network:
  nodes:
    spine-1: {attrs: {<<: *attrs, <<: *spine_cfg, capacity: *cap}}
    spine-2: {attrs: {<<: *attrs, <<: *spine_cfg, capacity: *cap, region: "dc2"}}
```

Anchors are resolved during YAML parsing, before schema validation.
