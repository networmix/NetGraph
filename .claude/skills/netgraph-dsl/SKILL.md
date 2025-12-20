---
name: netgraph-dsl
description: >
  NetGraph scenario DSL for defining network topologies, traffic demands, failure policies,
  and analysis workflows in YAML. Use when: creating or editing .yaml/.yml network scenarios,
  defining nodes/links/groups, writing adjacency rules, configuring selectors or blueprints,
  setting up traffic matrices or failure policies, debugging DSL syntax or validation errors,
  or asking about NetGraph scenario structure.
license: MIT
metadata:
  author: "netgraph"
  version: "1.0"
  repo: "https://github.com/networmix/NetGraph"
---

# NetGraph DSL

Define network simulation scenarios in YAML format.

## Quick Reference

| Section | Purpose |
|---------|---------|
| `network` | Topology: nodes, links, groups, adjacency (required) |
| `blueprints` | Reusable topology templates |
| `components` | Hardware library for cost/power modeling |
| `risk_groups` | Failure correlation groups |
| `vars` | YAML anchors for value reuse |
| `traffic_matrix_set` | Traffic demand definitions |
| `failure_policy_set` | Failure simulation rules |
| `workflow` | Analysis execution steps |
| `seed` | Master seed for reproducibility |

## Minimal Example

```yaml
network:
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
        cost: 1
```

## Core Patterns

### Nodes and Links

```yaml
network:
  nodes:
    Seattle:
      attrs:           # Custom attributes go here
        role: core
      risk_groups: ["RG1"]
      disabled: false
    Portland:
      attrs:
        role: edge

  links:
    - source: Seattle
      target: Portland
      link_params:     # Required wrapper for link parameters
        capacity: 100
        cost: 10
        attrs:
          distance_km: 280
      link_count: 2    # Parallel links
```

### Node Groups

```yaml
network:
  groups:
    leaf:
      node_count: 4
      name_template: "leaf-{node_num}"
      attrs:
        role: leaf
```

Creates: `leaf/leaf-1`, `leaf/leaf-2`, `leaf/leaf-3`, `leaf/leaf-4`

### Template Syntaxes

| Syntax | Example | Context |
|--------|---------|---------|
| `[1-3]` | `dc[1-3]/rack` | Group names, risk groups |
| `$var`/`${var}` | `pod${p}/leaf` | Adjacency & demand selectors |
| `{node_num}` | `srv-{node_num}` | `name_template` field |

These are NOT interchangeable. See [REFERENCE.md](references/REFERENCE.md) for details.

### Bracket Expansion

```yaml
network:
  groups:
    dc[1-3]/rack[a,b]:    # Cartesian product
      node_count: 4
      name_template: "srv-{node_num}"
```

Creates: `dc1/racka`, `dc1/rackb`, `dc2/racka`, `dc2/rackb`, `dc3/racka`, `dc3/rackb`

**Scope**: Bracket expansion works in group names, risk group definitions (including children), and risk group membership arrays. Component names and other fields treat brackets as literal characters.

### Adjacency Patterns

```yaml
network:
  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh        # Every source to every target
      link_params:
        capacity: 100

    - source: /group_a     # 4 nodes
      target: /group_b     # 2 nodes
      pattern: one_to_one  # Pairwise with modulo wrap (sizes must have multiple factor)
```

### Selectors with Conditions

```yaml
adjacency:
  - source:
      path: "/datacenter"
      match:
        logic: and         # "and" or "or" (default)
        conditions:
          - attr: role
            operator: "=="
            value: leaf
    target: /spine
    pattern: mesh
```

**Operators**: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `in`, `not_in`, `any_value`, `no_value`

### Capturing Groups for Grouping

```yaml
# Single capture group creates groups by captured value
source: "^(dc[1-3])/.*"     # Groups: dc1, dc2, dc3

# Multiple capture groups join with |
source: "^(dc\\d+)/(spine|leaf)/.*"  # Groups: dc1|spine, dc1|leaf, etc.
```

### Variable Expansion

```yaml
adjacency:
  - source: "plane${p}/rack"
    target: "spine${s}"
    expand_vars:
      p: [1, 2]
      s: [1, 2, 3]
    expansion_mode: cartesian  # or "zip" (equal-length lists required)
    pattern: mesh
```

### Blueprints

```yaml
blueprints:
  clos_pod:
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
          capacity: 100

network:
  groups:
    pod[1-2]:
      use_blueprint: clos_pod
      parameters:
        leaf.node_count: 6  # Override defaults
```

### Traffic Demands

```yaml
traffic_matrix_set:
  production:
    - source: "^dc1/.*"
      sink: "^dc2/.*"
      demand: 1000
      mode: pairwise       # or "combine"
      flow_policy_config: SHORTEST_PATHS_ECMP
```

**Flow policies**: `SHORTEST_PATHS_ECMP`, `SHORTEST_PATHS_WCMP`, `TE_WCMP_UNLIM`, `TE_ECMP_16_LSP`, `TE_ECMP_UP_TO_256_LSP`

### Failure Policies

```yaml
failure_policy_set:
  single_link:
    fail_risk_groups: false         # Expand to shared-risk entities
    modes:                          # Weighted modes (one selected per iteration)
      - weight: 1.0
        rules:
          - entity_scope: link      # node, link, or risk_group
            rule_type: choice       # all, choice, or random
            count: 1
            # Optional: weight_by: capacity  # Weighted sampling by attribute
```

**Rule types**: `all` (select all matches), `choice` (sample `count`), `random` (each with `probability`)

### Workflow

```yaml
workflow:
  - step_type: NetworkStats
    name: stats
  - step_type: MaximumSupportedDemand
    name: msd
    matrix_name: production
    alpha_start: 1.0
    resolution: 0.05
  - step_type: TrafficMatrixPlacement
    name: placement
    matrix_name: production
    failure_policy: single_link
    iterations: 1000
    alpha_from_step: msd          # Reference MSD result
    alpha_from_field: data.alpha_star
  - step_type: MaxFlow
    source: "^(dc[1-3])$"
    sink: "^(dc[1-3])$"
    mode: pairwise
    failure_policy: single_link
    iterations: 1000
    baseline: true                # Include no-failure baseline
```

**Step types**: `BuildGraph`, `NetworkStats`, `MaxFlow`, `TrafficMatrixPlacement`, `MaximumSupportedDemand`, `CostPower`

## Common Pitfalls

### 1. Custom fields must go in `attrs`

```yaml
# WRONG
nodes:
  A:
    my_field: value    # Error!

# CORRECT
nodes:
  A:
    attrs:
      my_field: value
```

### 2. Link parameters require `link_params` wrapper

```yaml
# WRONG
links:
  - source: A
    target: B
    capacity: 100      # Error!

# CORRECT
links:
  - source: A
    target: B
    link_params:
      capacity: 100
```

### 3. `one_to_one` requires compatible sizes

Sizes must have a multiple factor (4-to-2 OK, 3-to-2 ERROR).

### 4. Path patterns are anchored at start

```yaml
path: "leaf"       # Only matches names STARTING with "leaf"
path: ".*leaf.*"   # Matches "leaf" anywhere
```

**Note**: Leading `/` is stripped and has no effect. `/leaf` and `leaf` are equivalent. All paths are relative to the current scope (blueprint instantiation path or network root).

### 5. Variable syntax uses `$` prefix

```yaml
# WRONG (conflicts with regex {m,n})
source: "{dc}/leaf"

# CORRECT
source: "${dc}/leaf"
```

### 6. `zip` requires equal-length lists

```yaml
# WRONG
expand_vars:
  a: [1, 2]
  b: [x, y, z]     # Length mismatch!
expansion_mode: zip
```

### 7. Processing order matters

1. Groups and direct nodes created
2. Node overrides applied
3. Adjacency and blueprint adjacencies expanded
4. Direct links created
5. Link overrides applied

Overrides only affect entities that exist at their processing stage.

## Validation Checklist

- [ ] Custom fields inside `attrs`
- [ ] Link parameters inside `link_params`
- [ ] Referenced blueprints exist
- [ ] Node names in direct links exist
- [ ] `one_to_one` sizes have multiple factor
- [ ] `zip` lists have equal length
- [ ] Selectors have at least one of: `path`, `group_by`, `match`

## More Information

- [Full DSL Reference](references/REFERENCE.md) - Complete field documentation, all operators, workflow steps
- [Working Examples](references/EXAMPLES.md) - 11 complete scenarios from simple to advanced
