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
| `[1-3]` | `dc[1-3]/rack[a,b]` | Node group names | Generate multiple groups |
| `$var` / `${var}` | `pod${p}/leaf` | Links, demands | Template expansion with `expand` block |
| `{n}` | `srv-{n}` | `template` | Node naming (1-indexed) |

**These syntaxes are not interchangeable.** Each works only in its designated context.

**Why different syntaxes?** Each serves a distinct purpose:

| Syntax | Operation | Key Difference |
|--------|-----------|----------------|
| `[1-3]` | Static generation | Creates multiple definitions at parse time |
| `${var}` | Template substitution | Requires explicit `expand` block with `vars` |
| `{n}` | Sequential counter | Auto-increments based on `count` |

Bracket expansion generates structure; variable expansion parameterizes rules; node naming indexes instances.

## Entity Creation Architecture

The DSL implements two fundamentally different selection patterns optimized for different use cases. Understanding these patterns is essential for effective scenario authoring.

### Two Selection Models

The DSL uses distinct selection strategies depending on the operation:

**1. Path-Based Node Selection** (link rules, traffic demands, workflow steps)

- Uses regex patterns on hierarchical node names
- Supports capture group-based grouping
- Supports attribute-based grouping (`group_by`)
- Supports attribute filtering (`match` conditions)
- Supports `active_only` filtering

**2. Condition-Based Entity Selection** (failure rules, membership rules, risk group generation)

- Works on nodes, links, or risk_groups (`scope`)
- Uses only attribute-based filtering (`conditions`)
- No path/regex patterns (operates on all entities of specified type)

These patterns share common primitives (condition evaluation, match specification) but serve different purposes and should not be confused.

### Link Creation Flow

Link definitions create links between nodes using path-based selection with optional filtering:

```mermaid
flowchart TD
    Start[Link Definition] --> VarExpand{Has expand block?}
    VarExpand -->|Yes| VarSubst[Variable Substitution]
    VarSubst --> PathFilter
    VarExpand -->|No| PathFilter[1. Path-Based Selection]
    PathFilter --> PathDesc[Select nodes via regex pattern<br/>Groups by capture groups]
    PathDesc --> MatchFilter{Has match conditions?}
    MatchFilter -->|Yes| AttrFilter[2. Attribute Filtering]
    MatchFilter -->|No| ActiveFilter
    AttrFilter --> AttrDesc[Filter by attribute conditions<br/>using logic and/or]
    AttrDesc --> ActiveFilter[3. Active/Excluded Filtering]
    ActiveFilter --> GroupBy{Has group_by?}
    GroupBy -->|Yes| Regroup[4. Re-group by Attribute]
    GroupBy -->|No| Pattern
    Regroup --> Pattern[5. Apply Pattern]
    Pattern --> PatternDesc[mesh or one_to_one<br/>Creates links between groups]
```

**Processing Steps:**

1. **Path Selection**: Regex pattern matches nodes by hierarchical name
   - Capture groups create initial grouping
   - If no path specified, selects all nodes
2. **Attribute Filtering**: Optional `match` conditions filter nodes
   - Uses `logic: "and"` or `"or"` (default: `"or"`)
   - Supports operators: `==`, `!=`, `<`, `>`, `contains`, `in`, etc.
3. **Active Filtering**: Filters disabled nodes based on context
   - Links default: `active_only=false` (creates links to disabled nodes)
4. **Attribute Grouping**: Optional `group_by` overrides regex capture grouping
5. **Pattern Application**: Creates links between selected node groups
   - `mesh`: Every source to every target
   - `one_to_one`: Pairwise with wrap-around

**Key Characteristics:**

- `default_active_only=False` (links are created to disabled nodes)
- `match.logic` defaults to `"or"` (inclusive matching)
- Supports variable expansion via `expand` block

### Traffic Demand Creation Flow

Traffic demands follow a similar pattern but with important differences:

```mermaid
flowchart TD
    Start[Traffic Demand Spec] --> VarExpand{Has expand block?}
    VarExpand -->|Yes| VarSubst[Variable Substitution<br/>Creates multiple demand specs]
    VarSubst --> Process
    VarExpand -->|No| Process[Process Single Demand]
    Process --> SrcSelect[1. Select Source Nodes]
    SrcSelect --> TgtSelect[2. Select Target Nodes]
    TgtSelect --> SrcDesc[Uses same path + match + group_by<br/>selection as links]
    SrcDesc --> Mode{Demand Mode?}
    Mode -->|pairwise| Pairwise[3a. Pairwise Expansion]
    Mode -->|combine| Combine[3b. Combine Expansion]
    Pairwise --> PairDesc[Create demand for each src-tgt pair<br/>Volume distributed evenly<br/>No pseudo nodes]
    Combine --> CombDesc[Create pseudo-source and pseudo-target<br/>Single aggregated demand<br/>Augmentation edges connect real nodes]
```

**Key Differences from Links:**

1. **Active-only default**: `default_active_only=True` (only active nodes participate)
2. **Two selection phases**: Source nodes first, then target nodes (both use same selector logic)
3. **Expansion modes**:
   - **Pairwise**: Creates individual demands for each (source, target) pair
   - **Combine**: Creates pseudo nodes and a single aggregated demand
4. **Group modes**: Additional layer (`flatten`, `per_group`, `group_pairwise`) for handling grouped selections

**Processing Steps:**

1. Select source nodes using unified selector (path + match + group_by)
2. Select target nodes using unified selector
3. Apply mode-specific expansion:
   - **Pairwise**: Volume evenly distributed across all pairs
   - **Combine**: Single demand with pseudo nodes for aggregation

### Risk Group Creation Flow

Risk groups use the condition-based selection model:

```mermaid
flowchart TD
    Start[Risk Groups Definition] --> Three[Three Creation Methods]
    Three --> Direct[1. Direct Definition]
    Three --> Member[2. Membership Rules]
    Three --> Generate[3. Generate Blocks]

    Direct --> DirectDesc[Simply name the risk group<br/>Entities reference it explicitly]

    Member --> MemberScope[Specify scope<br/>node, link, or risk_group]
    MemberScope --> MemberCond[Define match conditions<br/>logic defaults to and]
    MemberCond --> MemberExec[Scan ALL entities of that scope<br/>Add matching entities to risk group]

    Generate --> GenScope[Specify scope<br/>node or link only]
    GenScope --> GenGroupBy[Specify group_by attribute]
    GenGroupBy --> GenExec[Collect unique values<br/>Create risk group for each value<br/>Add entities with that value]
```

**Creation Methods:**

1. **Direct Definition**: Explicitly name risk groups, entities reference them
2. **Membership Rules**: Auto-assign entities based on attribute matching
3. **Generate Blocks**: Auto-create risk groups from unique attribute values

**Key Characteristics:**

- **No path patterns**: Operates on ALL entities of specified scope
- **Only attribute-based**: Uses `conditions` exclusively
- **Logic defaults to "and"** for membership (stricter matching)
- **Hierarchical support**: Risk groups can contain other risk groups as children

### Comparison Table

| Feature | Links | Traffic Demands | Risk Groups |
|---------|-------|-----------------|-------------|
| Selection Type | Path-based | Path-based | Condition-based |
| Regex Patterns | Yes | Yes | No |
| Capture Groups | Yes | Yes | No |
| `group_by` | Yes | Yes | Yes (generate only) |
| `match` Conditions | Yes | Yes | Yes (membership/generate) |
| `active_only` Default | False | True | N/A |
| `match.logic` Default | "or" | "or" | "and" (membership) |
| Variable Expansion | Yes | Yes | No |
| Entity Scope | Nodes only | Nodes only | Nodes, links, risk_groups |

### Shared Evaluation Primitives

All selection mechanisms share common evaluation primitives:

1. **Condition evaluation**: `evaluate_condition()` handles all operators
   - Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
   - String/collection: `contains`, `not_contains`, `in`, `not_in`
   - Existence: `exists`, `not_exists`

2. **Condition combining**: `evaluate_conditions()` applies `"and"`/`"or"` logic

3. **Attribute flattening**: Unified access to entity attributes
   - `flatten_node_attrs()`: Merges node.attrs with top-level fields
   - `flatten_link_attrs()`: Merges link.attrs with top-level fields
   - `flatten_risk_group_attrs()`: Merges risk_group.attrs with top-level fields

4. **Dot-notation support**: `resolve_attr_path()` handles nested attributes
   - Example: `hardware.vendor` resolves to `attrs["hardware"]["vendor"]`

5. **Variable expansion**: `expand_templates()` handles `$var` and `${var}` substitution
   - Supports `cartesian` and `zip` expansion modes

### Context-Aware Defaults

The DSL uses context-aware defaults to optimize for common use cases:

| Context | Selection Type | Active Only | Match Logic | Rationale |
|---------|---------------|-------------|-------------|-----------|
| Links | Path-based | False | "or" | Create links to all nodes, including disabled |
| Demands | Path-based | True | "or" | Only route traffic through active nodes |
| Node Rules | Path-based | False | "or" | Modify all matching nodes |
| Workflow Steps | Path-based | True | "or" | Analyze only active topology |
| Membership Rules | Condition-based | N/A | "and" | Precise matching for risk assignment |
| Failure Rules | Condition-based | N/A | "or" | Inclusive matching for failure scenarios |
| Generate Blocks | Condition-based | N/A | N/A | No conditions, groups by values |

These defaults ensure intuitive behavior while remaining overridable when needed.

## Top-Level Keys

```yaml
network:                 # Network topology (required)
blueprints:              # Reusable network templates
components:              # Hardware component library
risk_groups:             # Failure correlation groups
vars:                    # YAML anchors and variables for reuse
demands:                 # Traffic demand definitions
failures:                # Failure simulation policies
workflow:                # Analysis execution steps
seed:                    # Master seed for reproducibility (integer)
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
      capacity: 200
      cost: 6846
      attrs:
        distance_km: 1369.13
        media_type: "fiber"
        hardware:
          source: {component: "800G-ZR+", count: 1}
          target: {component: "1600G-2xDR4", count: 1}
```

Recognized keys for each link entry:

- `source`, `target`: node names (required)
- `capacity`: link capacity (optional; default 1.0)
- `cost`: link cost (optional; default 1.0)
- `disabled`: boolean (optional)
- `risk_groups`: list of risk-group names (optional)
- `attrs`: mapping of attributes (optional)
- `count`: integer number of parallel links to create (optional; default 1)

### Node Groups

**Node Groups with Count/Template:**

```yaml
network:
  nodes:
    leaf:
      count: 4
      template: "leaf-{n}"
      attrs:
        role: "leaf"
    spine:
      count: 2
      template: "spine-{n}"
      attrs:
        role: "spine"
```

Creates: `leaf/leaf-1`, `leaf/leaf-2`, `leaf/leaf-3`, `leaf/leaf-4`, `spine/spine-1`, `spine/spine-2`

**Link Definitions:**

```yaml
network:
  links:
    - source: /leaf
      target: /spine
      pattern: "mesh"           # Connect every leaf to every spine
      capacity: 3200
      cost: 1
    - source: /spine
      target: /spine
      pattern: "one_to_one"     # Connect spines pairwise
      count: 2                   # Create 2 parallel links per pair (optional)
      capacity: 1600
      cost: 1
      attrs:
        hardware:
          source: {component: "800G-DR4", count: 2}
          target: {component: "800G-DR4", count: 2}
```

### Attribute-filtered Links (selector objects)

You can filter the source or target node sets by attributes using the same condition syntax as failure policies. Replace a string `source`/`target` with an object that has `path` and optional `match`:

```yaml
network:
  links:
    - source:
        path: "/leaf"
        match:
          logic: "and"         # default: "or"
          conditions:
            - attr: "role"
              op: "=="
              value: "leaf"
      target:
        path: "/spine"
        match:
          conditions:
            - attr: "role"
              op: "=="
              value: "spine"
      pattern: "mesh"
      capacity: 100
      cost: 1
```

Notes:

- `path` is a regex pattern matched against node names (anchored at start via Python `re.match`).
- `match.conditions` uses the shared condition operators: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `exists`, `not_exists`.
- Conditions evaluate over a flat view of node attributes combining top-level fields (`name`, `disabled`, `risk_groups`) and `node.attrs`.
- `logic` in the `match` block accepts "and" or "or" (default "or").
- Selectors filter node candidates before the link `pattern` is applied.
- Cross-endpoint predicates (e.g., comparing a source attribute to a target attribute) are not supported.
- Node rules run before link expansion; link rules run after link creation.

Path semantics:

- All paths are relative to the current scope. There is no concept of absolute paths.
- Leading `/` is stripped and has no functional effect - `/leaf` and `leaf` are equivalent.
- Within a blueprint, paths resolve relative to the instantiation path. For example, if a blueprint is used under group `pod1`, then `source: /leaf` resolves to `pod1/leaf`.
- At top-level `network.links`, the parent path is empty, so patterns match against full node names.

Example with OR logic to match multiple roles:

```yaml
network:
  links:
    - source:
        path: "/metro1/dc[1-1]"
        match:
          conditions:
            - attr: "role"
              op: "=="
              value: "dc"
      target:
        path: "/metro1/pop[1-2]"
        match:
          logic: "or"
          conditions:
            - attr: "role"
              op: "=="
              value: "leaf"
            - attr: "role"
              op: "=="
              value: "core"
      pattern: "mesh"
```

**Connectivity Patterns:**

- `mesh`: Full connectivity between all source and target nodes
- `one_to_one`: Pairwise connections. Compatible sizes means max(|S|,|T|) must be an integer multiple of min(|S|,|T|); mapping wraps modulo the smaller set (e.g., 4x2 and 6x3 valid; 3x2 invalid).

### Bracket Expansion

Create multiple similar node groups using bracket notation:

```yaml
network:
  nodes:
    dc[1-3]/rack[a,b]:     # Creates dc1/racka, dc1/rackb, dc2/racka, etc.
      count: 4
      template: "srv-{n}"
```

**Expansion Types:**

- Numeric ranges: `[1-4]` -> 1, 2, 3, 4
- Explicit lists: `[red,blue,green]` -> red, blue, green

**Scope:** Bracket expansion applies to:

- **Node group names** under `network.nodes` and `blueprints.*.nodes`
- **Risk group names** in top-level `risk_groups` definitions (including children)
- **Risk group membership arrays** on nodes, links, and node groups

Component names, direct node names (`network.nodes` without count/template), and other string fields treat brackets as literal characters.

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

**Limitations and Workarounds:**

| Pattern | Behavior | Workaround |
|---------|----------|------------|
| `[01-03]` | Produces `1, 2, 3` (no leading zeros) | Use explicit list: `[01,02,03]` |
| `[A-C]` | Error (letter ranges not supported) | Use explicit list: `[A,B,C]` |
| `[1-10]` | Produces `1, 2, ..., 10` | Works correctly |

The range syntax `[start-end]` only supports integers. For letters, mixed sequences, or zero-padded numbers, use comma-separated explicit lists.

### Variable Expansion in Links

Use `$var` or `${var}` syntax with an `expand` block for template substitution:

```yaml
links:
  - source: "plane${p}/rack${r}"
    target: "spine${s}"
    expand:
      vars:
        p: [1, 2]
        r: ["a", "b"]
        s: [1, 2, 3]
      mode: "cartesian"  # All combinations
    pattern: "mesh"

  - source: "server${idx}"
    target: "switch${idx}"
    expand:
      vars:
        idx: [1, 2, 3, 4]
      mode: "zip"        # Paired by index
    pattern: "one_to_one"
```

## `blueprints` - Reusable Templates

Templates for network segments that can be instantiated multiple times:

```yaml
blueprints:
  leaf_spine:
    nodes:
      leaf:
        count: 4
        template: "leaf-{n}"
      spine:
        count: 2
        template: "spine-{n}"
    links:
      - source: /leaf
        target: /spine
        pattern: mesh
        capacity: 40
        cost: 1

network:
  nodes:
    pod1:
      blueprint: leaf_spine
    pod2:
      blueprint: leaf_spine
      params:                    # Override blueprint parameters
        leaf.count: 6
        spine.template: "core-{n}"
```

**Blueprint Features:**

- Define nodes and link rules once, reuse multiple times
- Override parameters using dot notation during instantiation
- Hierarchical naming: `pod1/leaf/leaf-1`, `pod2/spine/core-1`

## Node and Link Rules

Modify specific nodes or links after initial creation:

```yaml
network:
  node_rules:
    - path: "^pod1/spine/.*$"           # Regex pattern matching
      disabled: true
      attrs:
        maintenance_mode: "active"
    - path: "server-[1-3]$"             # Specific node subset
      attrs:
        priority: "high"

  link_rules:
    - source: "^pod1/leaf/.*$"
      target: "^pod1/spine/.*$"
      capacity: 100                     # Override capacity
    - source: ".*/spine/.*"
      target: ".*/spine/.*"
      bidirectional: true               # Bidirectional matching (default: true)
      cost: 5
      attrs:
        link_type: "backbone"
```

Notes:

- For `link_rules`, link properties (`capacity`, `cost`, `disabled`, `risk_groups`, `attrs`) are specified at the top level (no wrapper).
- `bidirectional` defaults to `true` if omitted.
- Ordering: `node_rules` run after node creation (groups and direct nodes) and before any link expansion; `link_rules` run after links are created.

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
      attrs:
        hardware:
          source: {component: "Optic400G", count: 4}
          target: {component: "Optic400G", count: 4}
```

## `risk_groups` - Risk Modeling

Define hierarchical failure correlation groups for modeling correlated failures. Risk groups can represent any failure correlation pattern: physical infrastructure, geographic regions, vendor dependencies, or custom domains.

### Understanding Hierarchy

Risk groups form parent-child trees that model **cascading failures**:

```yaml
risk_groups:
  - name: "Region_West"
    children:
      - name: "Site_Seattle"
      - name: "Site_Portland"
```

**Cascading semantics:** When a parent fails, all descendants also fail. This models real-world correlations where a regional outage affects all sites in that region.

**Storage model:** Children are nested within parents, not in the top-level dictionary:

```python
# Top-level only
scenario.network.risk_groups.keys()  # {'Region_West'}

# Access children via parent
region = scenario.network.risk_groups["Region_West"]
for child in region.children:
    print(child.name)  # Site_Seattle, Site_Portland
```

**Entity references:** Nodes and links reference risk groups by name. To reference a group, it must be defined at top level (children alone are not sufficient):

```yaml
risk_groups:
  - name: "Site_Seattle"      # Top-level definition enables references
  - name: "Region_West"
    children:
      - name: "Site_Seattle"  # Also a child for hierarchy

network:
  nodes:
    Router_SEA:
      risk_groups: ["Site_Seattle"]
```

### Common Use Cases

Risk groups can model any failure correlation pattern. Below are some common examples:

**Physical Infrastructure** (fiber paths, power zones, cooling systems)
**Geographic/Administrative** (regions, availability zones, maintenance windows)
**Vendor/Software Dependencies** (shared components, software versions)
**Logical Grouping** (service tiers, customer segments, custom domains)

### Example 1: Physical Infrastructure (Fiber Links)

One common use case is modeling physical infrastructure. For fiber links, you might use a hierarchy like Path -> Conduit -> Fiber Pair.

```yaml
risk_groups:
  # Top-level definitions for referenceable groups
  - name: "Conduit_NYC_CHI_C[1-2]"
    attrs:
      type: fiber_conduit

  # Hierarchy defines cascading relationships
  - name: "Path_NYC_CHI"
    attrs:
      type: fiber_path
      distance_km: 1200
    children:
      - name: "Conduit_NYC_CHI_C[1-2]"

network:
  nodes:
    NYC: {}
    CHI: {}
  links:
    - source: NYC
      target: CHI
      risk_groups: ["Conduit_NYC_CHI_C1"]
      attrs:
        fiber:
          path_id: "NYC-CHI"
          conduit_id: "NYC-CHI-C1"
```

**Cascading behavior:**

- Fiber pair failure affects only that pair
- Conduit failure affects all pairs in that conduit
- Path failure affects all conduits in that path

### Example 2: Physical Infrastructure (Data Center Nodes)

For data center nodes, you might model facility infrastructure with a hierarchy like Building -> Room -> Power Zone.

```yaml
risk_groups:
  # Top-level definitions for referenceable groups
  - name: "PowerZone_DC1_R1_PZ[A,B]"
    attrs:
      type: power_zone

  # Hierarchy defines cascading relationships
  - name: "Building_DC1"
    attrs:
      type: building
      location: "Ashburn, VA"
    children:
      - name: "Room_DC1_R[1-3]"
        attrs:
          type: room
        children:
          - name: "PowerZone_DC1_R1_PZ[A,B]"

network:
  nodes:
    Router_DC1_R1_RK01:
      risk_groups: ["PowerZone_DC1_R1_PZA"]
      attrs:
        facility:
          building_id: "DC1"
          room_id: "DC1-R1"
          power_zone: "DC1-R1-PZ-A"
```

**Cascading behavior:**

- Power zone failure affects equipment in that zone
- Room failure affects all zones in that room
- Building failure affects entire site

### Example 3: Geographic/Administrative Grouping

For geographic or administrative modeling:

```yaml
risk_groups:
  - name: "Region_West"
    attrs:
      type: geographic
    children:
      - name: "AZ_US_West_1a"
      - name: "AZ_US_West_1b"
  - name: "MaintenanceWindow_Weekend"
    attrs:
      type: operational
      schedule: "Sat-Sun 02:00-06:00 UTC"
```

### Membership Rules

Dynamically assign entities to risk groups based on attributes:

```yaml
risk_groups:
  - name: Conduit_NYC_CHI_C1
    membership:
      scope: link
      match:
        logic: and           # "and" or "or" (default: "and")
        conditions:
          - attr: fiber.conduit_id
            op: "=="
            value: "NYC-CHI-C1"

  - name: PowerZone_DC1_R1_PZA
    membership:
      scope: node
      match:
        logic: and
        conditions:
          - attr: facility.power_zone
            op: "=="
            value: "DC1-R1-PZ-A"
```

**Note:** Membership rules default to `logic: "and"` (stricter than link/demand selectors which default to `"or"`). This ensures precise entity matching for failure correlation.

### Generated Risk Groups

Automatically create risk groups from entity attributes:

```yaml
risk_groups:
  # Generate risk groups from fiber path attributes on links
  - generate:
      scope: link
      group_by: fiber.path_id
      name: Path_${value}
      attrs:
        type: fiber_path

  # Generate risk groups from facility attributes on nodes
  - generate:
      scope: node
      group_by: facility.building_id
      name: Building_${value}
      attrs:
        type: building
```

### Validation

Risk group references are validated at scenario load time:

**Undefined Reference Detection:** All risk group names referenced by nodes and links must exist in the `risk_groups` section. This catches typos and missing definitions early:

```yaml
# This will fail validation
network:
  nodes:
    Router1:
      risk_groups: ["PowerZone_A"]  # References undefined risk group

risk_groups:
  - name: "PowerZone_B"  # Only PowerZone_B is defined
```

**Circular Hierarchy Detection:** Parent-child relationships cannot form cycles:

```yaml
# This will fail validation
risk_groups:
  - name: "GroupA"
    children:
      - name: "GroupB"
        children:
          - name: "GroupA"  # Error: circular reference
```

Validation errors list affected entities and undefined groups to aid debugging.

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

## `demands` - Traffic Analysis

Define traffic demand patterns for capacity analysis:

```yaml
demands:
  production:
    # Simple string pattern selectors
    - source: "^servers/.*"
      target: "^storage/.*"
      volume: 1000
      mode: "combine"
      priority: 1
      flow_policy: "SHORTEST_PATHS_ECMP"

    # Dict selectors with attribute-based grouping
    - source:
        group_by: "dc"           # Group nodes by datacenter attribute
      target:
        group_by: "dc"
      volume: 500
      mode: "pairwise"
      priority: 2

    # Dict selectors with filtering
    - source:
        path: "^dc1/.*"
        match:
          conditions:
            - attr: "role"
              op: "=="
              value: "leaf"
      target:
        path: "^dc2/.*"
        match:
          conditions:
            - attr: "role"
              op: "=="
              value: "spine"
      volume: 200
      mode: "combine"
```

### Variable Expansion in Demands

Use an `expand` block to generate multiple demands from a template:

```yaml
demands:
  inter_dc:
    - source: "^${src_dc}/.*"
      target: "^${dst_dc}/.*"
      volume: 100
      mode: "combine"
      expand:
        vars:
          src_dc: ["dc1", "dc2"]
          dst_dc: ["dc2", "dc3"]
        mode: "cartesian"  # All combinations (default)

    - source: "^${dc}/leaf/.*"
      target: "^${dc}/spine/.*"
      volume: 50
      mode: "pairwise"
      expand:
        vars:
          dc: ["dc1", "dc2", "dc3"]
        mode: "zip"        # Paired by index
```

**Expansion Modes:**

- `cartesian`: All combinations of variable values (default)
- `zip`: Pair values by index (lists must have equal length)

### Selector Fields

The `source` and `target` fields accept either:

- A string regex pattern matched against node names
- A selector object with `path`, `group_by`, and/or `match` fields

### Traffic Modes

- `combine`: Single aggregate flow between source and target groups
- `pairwise`: Individual flows between all source-target node pairs

### Flow Policies

- `SHORTEST_PATHS_ECMP`: IP/IGP routing with hash-based ECMP; equal split across equal-cost paths
- `SHORTEST_PATHS_WCMP`: IP/IGP routing with weighted ECMP; proportional split by link capacity
- `TE_WCMP_UNLIM`: MPLS-TE / SDN with capacity-aware WCMP; unlimited tunnels
- `TE_ECMP_16_LSP`: MPLS-TE with exactly 16 ECMP LSPs per demand
- `TE_ECMP_UP_TO_256_LSP`: MPLS-TE with up to 256 ECMP LSPs per demand

See [Flow Policy Presets](design.md#flow-policy-presets) for detailed configuration mapping and real-world network behavior.

## `failures` - Failure Simulation

Define failure policies for resilience testing:

```yaml
failures:
  single_link_failure:
    modes:                       # Weighted modes; exactly one mode fires per iteration
      - weight: 1.0
        rules:
          - scope: "link"
            mode: "choice"
            count: 1
  weighted_modes:                # Example of weighted multi-mode policy
    modes:
      - weight: 0.30
        rules:
          - scope: "risk_group"
            mode: "choice"
            count: 1
            weight_by: distance_km
      - weight: 0.35
        rules:
          - scope: "link"
            mode: "choice"
            count: 3
            conditions:
              - attr: link_type
                op: "=="
                value: dc_to_pop
            logic: and
            weight_by: target_capacity
      - weight: 0.25
        rules:
          - scope: "node"
            mode: "choice"
            count: 1
            conditions:
              - attr: node_type
                op: "!="
                value: dc_region
            logic: and
            weight_by: attached_capacity_gbps
      - weight: 0.10
        rules:
          - scope: "link"
            mode: "choice"
            count: 4
            conditions:
              - attr: link_type
                op: "=="
                value: leaf_spine
              - attr: link_type
                op: "=="
                value: intra_group
              - attr: link_type
                op: "=="
                value: inter_group
              - attr: link_type
                op: "=="
                value: internal_mesh
            logic: or
```

**Selection Modes:**

- `all`: Select all matching entities
- `choice`: Select specific count of entities
- `random`: Select entities with given probability

Notes:

- Policies are mode-based. Each mode has a non-negative `weight`. One mode is chosen per iteration with probability proportional to weights, then all rules in that mode are applied and their selections are unioned.
- Each rule has `scope` ("node" | "link" | "risk_group"), optional `logic` ("and" | "or"; defaults to "or"), optional `conditions`, and one of the selection mode parameters (`count` for choice, `probability` for random). `weight_by` can be provided for weighted sampling in `choice` rules.
- Condition language is the same as used in link `match` selectors and supports: `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `exists`, `not_exists`. Conditions evaluate on a flat attribute mapping that includes top-level fields and `attrs`.

## `workflow` - Execution Steps

Define analysis workflow steps:

```yaml
workflow:
  - type: NetworkStats
    name: network_statistics
  - type: MaximumSupportedDemand
    name: msd_baseline
    demand_set: baseline_traffic_matrix
  - type: TrafficMatrixPlacement
    name: tm_placement
    demand_set: baseline_traffic_matrix
    failure_policy: weighted_modes
    iterations: 1000
```

**Common Steps:**

- `BuildGraph`: Export graph to JSON (node-link) for external analysis
- `NetworkStats`: Compute basic statistics
- `MaxFlow`: Monte Carlo capacity analysis between node groups
- `TrafficMatrixPlacement`: Monte Carlo demand placement for a named demand set
- `MaximumSupportedDemand`: Search for `alpha_star` for a named demand set

See [Workflow Reference](workflow.md) for detailed configuration.

## Node Selection

NetGraph provides a unified selector system for selecting and grouping nodes across links, demands, and workflow steps.

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
        op: "=="
        value: "leaf"
      - attr: "tier"
        op: ">="
        value: 2
```

**Supported operators:** `==`, `!=`, `<`, `<=`, `>`, `>=`, `contains`, `not_contains`, `in`, `not_in`, `exists`, `not_exists`

### Workflow Examples

```yaml
workflow:
  - type: MaxFlow
    source:
      group_by: "metro"      # Group by metro attribute
    target: "^metro2/.*"     # String pattern
    mode: "pairwise"
```

### Link Examples

```yaml
network:
  links:
    - source:
        group_by: "role"
      target:
        path: "^dc2/leaf/.*"
      pattern: mesh
```

### Notes

- For links, risk groups, and failure policies, use `conditions` with an `attr` field in rules (see Failure Simulation).
- Blueprint scoping: In blueprints, paths are relative to the blueprint instantiation path.
