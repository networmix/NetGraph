---
name: netgraph-dsl
description: >
  NetGraph scenario DSL for defining network topologies, traffic demands, failure policies,
  and analysis workflows in YAML. Use when: creating or editing .yaml/.yml network scenarios,
  defining nodes/links/groups, writing link rules with patterns, configuring selectors or blueprints,
  setting up traffic demands or failure policies, debugging DSL syntax or validation errors,
  or asking about NetGraph scenario structure.
---

# NetGraph DSL

Define network simulation scenarios in YAML format.

> **Quick Start**: See [Minimal Example](#minimal-example) below.
> **Complete Reference**: See [references/REFERENCE.md](references/REFERENCE.md) for full documentation.

## Development Environment (Agent Guidance)

Working with NetGraph requires the local virtual environment at `./venv`.

### Prerequisites (Check First)

Before running any command:

1. **Working directory**: Must be the NetGraph repo root (where `Makefile` and `pyproject.toml` exist)
2. **Venv exists**: Check that `./venv/bin/python` exists

### Command Execution (Priority Order)

**1. Prefer `make` targets** - auto-handles venv detection, simplest approach:

```bash
make qt         # Quick tests (after code changes)
make test       # Full tests with coverage
make lint       # Linting and type checks
make check      # Pre-commit + tests + lint
make validate   # Validate YAML schemas
```

**2. Use direct venv paths** - reliable, no shell state required:

```bash
./venv/bin/ngraph inspect <scenario.yaml>   # Validate scenario YAML
./venv/bin/ngraph run <scenario.yaml>       # Execute scenario workflow
./venv/bin/python -m pytest tests/dsl/      # Run specific tests
```

**Note**: Avoid `source venv/bin/activate` - requires shell state that agents may not maintain between commands.

### If Setup Is Missing

If venv doesn't exist or commands fail with import errors:

```bash
make dev  # Creates venv, installs all dependencies and pre-commit hooks
```

### Key Commands Reference

| Task | Command |
|------|---------|
| Quick tests after changes | `make qt` |
| Check formatting/types | `make lint` |
| Validate scenario YAML | `./venv/bin/ngraph inspect <file>` |
| Execute scenario | `./venv/bin/ngraph run <file>` |
| Run specific test file | `./venv/bin/python -m pytest <path>` |

Python 3.11+ is required.

## Instructions

When working with NetGraph scenarios:

1. **Creating new scenarios**: Start with the [Minimal Example](#minimal-example), then add sections as needed
2. **Editing existing scenarios**: Identify the relevant section (network, demands, failures, etc.)
3. **Understanding selection**: Review [Selection Models](#selection-models) to understand path-based vs condition-based selection
4. **Debugging issues**: Check [Common Pitfalls](#common-pitfalls) and [Validation Checklist](#validation-checklist)
5. **Complex topologies**: Use [Blueprints](#blueprints) for reusable patterns
6. **Failure simulation**: Define [Risk Groups](#risk-groups) before creating failure policies

Refer to specific sections below for detailed syntax and examples.

## Quick Reference

| Section | Purpose |
|---------|---------|
| `network` | Topology: nodes, links (required) |
| `blueprints` | Reusable topology templates |
| `components` | Hardware library for cost/power modeling |
| `risk_groups` | Failure correlation groups |
| `vars` | YAML anchors for value reuse |
| `demands` | Traffic demand definitions |
| `failures` | Failure simulation rules |
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
      capacity: 100
      cost: 1
```

## Core Patterns

### Selection Models

The DSL implements two distinct selection patterns:

**1. Path-based Node Selection** (link rules, traffic demands, workflow steps)

- Uses regex patterns on hierarchical node names
- Supports capture group-based grouping
- Supports attribute-based grouping (`group_by`)
- Supports attribute filtering (`match` conditions)
- Supports `active_only` filtering

**2. Condition-based Entity Selection** (failure rules, membership rules, risk group generation)

- Works on nodes, links, or risk_groups (`scope`)
- Uses only attribute-based filtering (`conditions`)
- No path/regex patterns (operates on all entities of specified type)

These patterns share common primitives (condition evaluation, match specification) but serve different purposes and should not be confused.

> **For comprehensive details** on entity creation flows, processing steps, and comparison tables, see the [Entity Creation Architecture](references/REFERENCE.md#entity-creation-architecture) section in the full reference.

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
      capacity: 100    # Direct properties (no wrapper)
      cost: 10
      attrs:
        distance_km: 280
      count: 2         # Parallel links
```

### Node Groups

```yaml
network:
  nodes:
    leaf:
      count: 4
      template: "leaf{n}"
      attrs:
        role: leaf
```

Creates: `leaf/leaf1`, `leaf/leaf2`, `leaf/leaf3`, `leaf/leaf4`

### Template Syntaxes

| Syntax | Example | Context |
|--------|---------|---------|
| `[1-3]` | `dc[1-3]/rack` | Group names, risk groups |
| `$var`/`${var}` | `pod${p}/leaf` | Link & demand selectors |
| `{n}` | `srv{n}` | `template` field |

These are NOT interchangeable. See [REFERENCE.md](references/REFERENCE.md) for details.

### Bracket Expansion

```yaml
network:
  nodes:
    dc[1-3]/rack[a,b]:    # Cartesian product
      count: 4
      template: "srv{n}"
```

Creates: `dc1/racka`, `dc1/rackb`, `dc2/racka`, `dc2/rackb`, `dc3/racka`, `dc3/rackb`

**Scope**: Bracket expansion works in group names, risk group definitions (including children), and risk group membership arrays. Component names and other fields treat brackets as literal characters.

### Link Patterns

```yaml
network:
  links:
    - source: /leaf
      target: /spine
      pattern: mesh        # Every source to every target
      capacity: 100

    - source: /group_a     # 4 nodes
      target: /group_b     # 2 nodes
      pattern: one_to_one  # Pairwise with modulo wrap (sizes must have multiple factor)
```

### Selectors with Conditions

```yaml
links:
  - source:
      path: "/datacenter"
      match:
        logic: and         # "and" or "or"; defaults vary by context (see below)
        conditions:
          - attr: role
            op: "=="
            value: leaf
    target: /spine
    pattern: mesh
```

**Operators**: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `in`, `not_in`, `exists`, `not_exists`

**Logic defaults by context**:

| Context | Default `logic` | Rationale |
|---------|-----------------|-----------|
| Link `match` | `"or"` | Inclusive: match any condition |
| Demand `match` | `"or"` | Inclusive: match any condition |
| Membership rules | `"and"` | Precise: must match all conditions |
| Failure rules | `"or"` | Inclusive: match any condition |

### Capturing Groups for Grouping

```yaml
# Single capture group creates groups by captured value
source: "^(dc[1-3])/.*"     # Groups: dc1, dc2, dc3

# Multiple capture groups join with |
source: "^(dc\\d+)/(spine|leaf)/.*"  # Groups: dc1|spine, dc1|leaf, etc.
```

### Variable Expansion

```yaml
links:
  - source: "plane${p}/rack"
    target: "spine${s}"
    expand:
      vars:
        p: [1, 2]
        s: [1, 2, 3]
      mode: cartesian  # or "zip" (equal-length lists required)
    pattern: mesh
```

### Blueprints

```yaml
blueprints:
  clos_pod:
    nodes:
      leaf:
        count: 4
        template: "leaf{n}"
      spine:
        count: 2
        template: "spine{n}"
    links:
      - source: /leaf
        target: /spine
        pattern: mesh
        capacity: 100

network:
  nodes:
    pod[1-2]:
      blueprint: clos_pod
      params:
        leaf.count: 6  # Override defaults
```

### Traffic Demands

```yaml
demands:
  production:
    - source: "^dc1/.*"
      target: "^dc2/.*"
      volume: 1000
      mode: pairwise       # or "combine"
      flow_policy: SHORTEST_PATHS_ECMP
```

**Flow policies**: `SHORTEST_PATHS_ECMP`, `SHORTEST_PATHS_WCMP`, `TE_WCMP_UNLIM`, `TE_ECMP_16_LSP`, `TE_ECMP_UP_TO_256_LSP`

### Failure Policies

```yaml
failures:
  single_link:
    expand_groups: false         # Expand to shared-risk entities
    modes:                       # Weighted modes (one selected per iteration)
      - weight: 1.0
        rules:
          - scope: link          # node, link, or risk_group
            mode: choice         # all, choice, or random
            count: 1
            # Optional: weight_by: capacity  # Weighted sampling by attribute
```

**Rule modes**: `all` (select all matches), `choice` (sample `count`), `random` (each with `probability`)

### Risk Groups

Risk groups model failure correlation (shared infrastructure, geographic regions, vendor dependencies, or any custom domain). Three methods:

**Direct definition:**

```yaml
risk_groups:
  - name: "RG1"              # Full form
  - "RG2"                    # String shorthand (equivalent to {name: "RG2"})
```

**Membership rules** (assign entities by attribute matching):

```yaml
risk_groups:
  - name: HighCapacityLinks
    membership:
      scope: link            # node, link, or risk_group
      match:
        logic: and           # "and" or "or" (default: "and" for membership)
        conditions:
          - attr: capacity
            op: ">="
            value: 1000
```

**Generate blocks** (create groups from unique attribute values):

```yaml
risk_groups:
  - generate:
      scope: node            # node or link only
      group_by: region       # Any attribute to group by
      name: "Region_${value}"
```

**Validation:** Risk group references are validated at load time (undefined references and circular hierarchies detected).

See [REFERENCE.md](references/REFERENCE.md) for complete details.

### Workflow

```yaml
workflow:
  - type: NetworkStats
    name: stats
  - type: MaximumSupportedDemand
    name: msd
    demand_set: production
    alpha_start: 1.0
    resolution: 0.05
  - type: TrafficMatrixPlacement
    name: placement
    demand_set: production
    failure_policy: single_link
    iterations: 1000
    alpha_from_step: msd          # Reference MSD result
    alpha_from_field: data.alpha_star
  - type: MaxFlow
    source: "^(dc[1-3])$"
    target: "^(dc[1-3])$"
    mode: pairwise
    failure_policy: single_link
    iterations: 1000
    seed: 42                      # Optional: for reproducibility
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

### 2. Link properties are flattened (no wrapper)

```yaml
# WRONG
links:
  - source: A
    target: B
    link_params:       # Error! No wrapper
      capacity: 100

# CORRECT
links:
  - source: A
    target: B
    capacity: 100      # Direct property
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
expand:
  vars:
    a: [1, 2]
    b: [x, y, z]     # Length mismatch!
  mode: zip
```

### 7. Processing order matters

1. Groups and direct nodes created
2. Node rules applied
3. Blueprint links and network links expanded
4. Direct links created
5. Link rules applied

Rules only affect entities that exist at their processing stage.

## Validation Checklist

- [ ] Custom fields inside `attrs`
- [ ] Link properties directly on link (no wrapper)
- [ ] Referenced blueprints exist
- [ ] Node names in direct links exist
- [ ] `one_to_one` sizes have multiple factor
- [ ] `zip` lists have equal length
- [ ] Selectors have at least one of: `path`, `group_by`, `match`

## More Information

- [Full DSL Reference](references/REFERENCE.md) - Complete field documentation, all operators, workflow steps
- [Working Examples](references/EXAMPLES.md) - 19 complete scenarios from simple to advanced
