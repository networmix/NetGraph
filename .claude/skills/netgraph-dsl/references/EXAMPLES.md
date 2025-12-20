# NetGraph DSL Examples

Complete working examples for common use cases.

> For quick patterns and pitfalls, see the main [SKILL.md](../SKILL.md).
> For detailed field reference, see [REFERENCE.md](REFERENCE.md).

## Example 1: Simple Data Center

A basic leaf-spine topology with traffic analysis.

```yaml
network:
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

traffic_matrix_set:
  default:
    - source: "^leaf/.*"
      sink: "^leaf/.*"
      demand: 50
      mode: pairwise

failure_policy_set:
  single_link:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: link
            rule_type: choice
            count: 1

workflow:
  - step_type: TrafficMatrixPlacement
    name: placement
    matrix_name: default
    failure_policy: single_link
    iterations: 100
```

**Result**: 6 nodes (4 leaf + 2 spine), 8 links (4x2 mesh)

## Example 2: Multi-Pod with Blueprint

Two pods sharing a blueprint, connected via spine layer.

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

network:
  groups:
    pod[1-2]:
      use_blueprint: clos_pod

  adjacency:
    - source:
        path: "pod1/spine"
        match:
          conditions:
            - attr: role
              operator: "=="
              value: spine
      target:
        path: "pod2/spine"
      pattern: mesh
      link_params:
        capacity: 400
```

**Result**: 12 nodes (2 pods x 6 nodes), 20 links (16 internal + 4 inter-pod)

## Example 3: Backbone with Risk Groups

Wide-area network with shared-risk link groups.

```yaml
network:
  nodes:
    NewYork: {attrs: {site_type: core}}
    Chicago: {attrs: {site_type: core}}
    LosAngeles: {attrs: {site_type: core}}

  links:
    # Parallel diverse paths
    - source: NewYork
      target: Chicago
      link_params:
        capacity: 100
        cost: 10
        risk_groups: [RG_NY_CHI]
    - source: NewYork
      target: Chicago
      link_params:
        capacity: 100
        cost: 10
    # Single path
    - source: Chicago
      target: LosAngeles
      link_params:
        capacity: 100
        cost: 15
        risk_groups: [RG_CHI_LA]

risk_groups:
  - name: RG_NY_CHI
    attrs:
      corridor: NYC-Chicago
      distance_km: 1200
  - name: RG_CHI_LA
    attrs:
      corridor: Chicago-LA
      distance_km: 2800

failure_policy_set:
  srlg_failure:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: risk_group
            rule_type: choice
            count: 1
```

**Result**: 3 nodes, 3 links, 2 risk groups

## Example 4: Variable Expansion at Scale

Large fabric using variable expansion.

```yaml
network:
  groups:
    plane[1-4]/rack[1-8]:
      node_count: 48
      name_template: "server-{node_num}"
      attrs:
        role: compute

    fabric/spine[1-4]:
      node_count: 1
      name_template: "spine"
      attrs:
        role: spine

  adjacency:
    - source: "plane${p}/rack${r}"
      target: "fabric/spine${s}"
      expand_vars:
        p: [1, 2, 3, 4]
        r: [1, 2, 3, 4, 5, 6, 7, 8]
        s: [1, 2, 3, 4]
      expansion_mode: cartesian
      pattern: mesh
      link_params:
        capacity: 100
```

**Result**: 1540 nodes (4x8x48 compute + 4 spine), 6144 links

## Example 5: Full Mesh Topology

Simple 4-node full mesh for testing.

```yaml
seed: 42

network:
  nodes:
    N1: {}
    N2: {}
    N3: {}
    N4: {}

  links:
    - source: N1
      target: N2
      link_params: {capacity: 2.0, cost: 1.0}
    - source: N1
      target: N3
      link_params: {capacity: 1.0, cost: 1.0}
    - source: N1
      target: N4
      link_params: {capacity: 2.0, cost: 1.0}
    - source: N2
      target: N3
      link_params: {capacity: 2.0, cost: 1.0}
    - source: N2
      target: N4
      link_params: {capacity: 1.0, cost: 1.0}
    - source: N3
      target: N4
      link_params: {capacity: 2.0, cost: 1.0}

failure_policy_set:
  single_link_failure:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: link
            rule_type: choice
            count: 1

traffic_matrix_set:
  baseline:
    - source: "^N([1-4])$"
      sink: "^N([1-4])$"
      demand: 12.0
      mode: pairwise

workflow:
  - step_type: MaximumSupportedDemand
    name: msd
    matrix_name: baseline
    acceptance_rule: hard
    alpha_start: 1.0
    resolution: 0.05

  - step_type: MaxFlow
    name: capacity_matrix
    source: "^(N[1-4])$"
    sink: "^(N[1-4])$"
    mode: pairwise
    failure_policy: single_link_failure
    iterations: 1000
    seed: 42
```

## Example 6: Attribute-Based Selectors

Using match conditions to filter nodes.

```yaml
network:
  groups:
    servers:
      node_count: 4
      name_template: "srv-{node_num}"
      attrs:
        role: compute
        rack: "rack-1"
    servers_b:
      node_count: 2
      name_template: "srvb-{node_num}"
      attrs:
        role: compute
        rack: "rack-9"
    switches:
      node_count: 2
      name_template: "sw-{node_num}"
      attrs:
        tier: spine

  adjacency:
    - source:
        path: "/servers"
        match:
          logic: and
          conditions:
            - attr: role
              operator: "=="
              value: compute
            - attr: rack
              operator: "!="
              value: "rack-9"
      target:
        path: "/switches"
        match:
          conditions:
            - attr: tier
              operator: "=="
              value: spine
      pattern: mesh
      link_params:
        capacity: 10
        cost: 1
```

**Result**: 8 nodes, 8 links (only rack-1 servers connect to switches)

## Example 7: Blueprint with Parameter Overrides

Customizing blueprint instances.

```yaml
blueprints:
  bp1:
    groups:
      leaf:
        node_count: 1
        attrs:
          some_field:
            nested_key: 111

network:
  groups:
    Main:
      use_blueprint: bp1
      parameters:
        leaf.attrs.some_field.nested_key: 999
```

**Result**: Node `Main/leaf/leaf-1` has `attrs.some_field.nested_key = 999`

## Example 8: Node and Link Overrides

Modifying topology after creation.

```yaml
blueprints:
  test_bp:
    groups:
      switches:
        node_count: 3
        name_template: "switch-{node_num}"

network:
  groups:
    group1:
      node_count: 2
      name_template: "node-{node_num}"
    group2:
      node_count: 2
      name_template: "node-{node_num}"
    my_clos1:
      use_blueprint: test_bp

  adjacency:
    - source: /group1
      target: /group2
      pattern: mesh
      link_params:
        capacity: 100
        cost: 10

  node_overrides:
    - path: "^my_clos1/switches/switch-(1|3)$"
      disabled: true
      attrs:
        maintenance_mode: active
        hw_type: newer_model

  link_overrides:
    - source: "^group1/node-1$"
      target: "^group2/node-1$"
      link_params:
        capacity: 200
        cost: 5
```

**Result**: Switches 1 and 3 disabled, specific link upgraded to 200 capacity

## Example 9: Complete Traffic Analysis

Full workflow with MSD and placement analysis.

```yaml
seed: 42

blueprints:
  Clos_L16_S4:
    groups:
      spine:
        node_count: 4
        name_template: spine{node_num}
        attrs:
          role: spine
      leaf:
        node_count: 16
        name_template: leaf{node_num}
        attrs:
          role: leaf
    adjacency:
      - source: /leaf
        target: /spine
        pattern: mesh
        link_params:
          capacity: 3200
          cost: 1

network:
  groups:
    metro1/pop[1-2]:
      use_blueprint: Clos_L16_S4
      attrs:
        metro_name: new-york
        node_type: pop

traffic_matrix_set:
  baseline:
    - source: "^metro1/pop1/.*"
      sink: "^metro1/pop2/.*"
      demand: 15000.0
      mode: pairwise
      flow_policy_config: TE_WCMP_UNLIM

failure_policy_set:
  single_link:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: link
            rule_type: choice
            count: 1

workflow:
  - step_type: NetworkStats
    name: network_statistics

  - step_type: MaximumSupportedDemand
    name: msd_baseline
    matrix_name: baseline
    acceptance_rule: hard
    alpha_start: 1.0
    growth_factor: 2.0
    resolution: 0.05

  - step_type: TrafficMatrixPlacement
    name: tm_placement
    seed: 42
    matrix_name: baseline
    failure_policy: single_link
    iterations: 1000
    parallelism: 7
    include_flow_details: true
    alpha_from_step: msd_baseline
    alpha_from_field: data.alpha_star
```

## Example 10: Group-By Selectors

Grouping nodes by attribute for demand generation.

```yaml
network:
  nodes:
    dc1_srv1: {attrs: {dc: dc1, role: server}}
    dc1_srv2: {attrs: {dc: dc1, role: server}}
    dc2_srv1: {attrs: {dc: dc2, role: server}}
    dc2_srv2: {attrs: {dc: dc2, role: server}}
  links:
    - source: dc1_srv1
      target: dc2_srv1
      link_params: {capacity: 100}
    - source: dc1_srv2
      target: dc2_srv2
      link_params: {capacity: 100}

traffic_matrix_set:
  inter_dc:
    - source:
        group_by: dc
      sink:
        group_by: dc
      demand: 100
      mode: pairwise
```

**Result**: Traffic flows grouped by datacenter attribute

## Example 11: Advanced Failure Policies

Multiple weighted failure modes with conditions and weighted sampling.

```yaml
network:
  nodes:
    core1: {attrs: {role: core, capacity_gbps: 1000}}
    core2: {attrs: {role: core, capacity_gbps: 1000}}
    edge1: {attrs: {role: edge, capacity_gbps: 400, region: west}}
    edge2: {attrs: {role: edge, capacity_gbps: 400, region: east}}
    edge3: {attrs: {role: edge, capacity_gbps: 200, region: west}}
  links:
    - source: core1
      target: core2
      link_params: {capacity: 1000, risk_groups: [RG_core]}
    - source: core1
      target: edge1
      link_params: {capacity: 400, risk_groups: [RG_west]}
    - source: core1
      target: edge3
      link_params: {capacity: 200, risk_groups: [RG_west]}
    - source: core2
      target: edge2
      link_params: {capacity: 400, risk_groups: [RG_east]}

risk_groups:
  - name: RG_core
    attrs: {tier: core, distance_km: 50}
  - name: RG_west
    attrs: {tier: edge, distance_km: 500}
  - name: RG_east
    attrs: {tier: edge, distance_km: 800}

failure_policy_set:
  mixed_failures:
    fail_risk_groups: true          # Expand to shared-risk entities
    fail_risk_group_children: false
    modes:
      # 40% chance: fail 1 edge node weighted by capacity
      - weight: 0.4
        attrs: {scenario: edge_failure}
        rules:
          - entity_scope: node
            rule_type: choice
            count: 1
            conditions:
              - attr: role
                operator: "=="
                value: edge
            logic: and
            weight_by: capacity_gbps

      # 35% chance: fail 1 risk group weighted by distance
      - weight: 0.35
        attrs: {scenario: srlg_failure}
        rules:
          - entity_scope: risk_group
            rule_type: choice
            count: 1
            weight_by: distance_km

      # 15% chance: fail all west-region nodes
      - weight: 0.15
        attrs: {scenario: regional_outage}
        rules:
          - entity_scope: node
            rule_type: all
            conditions:
              - attr: region
                operator: "=="
                value: west

      # 10% chance: random link failures (5% each)
      - weight: 0.1
        attrs: {scenario: random_link}
        rules:
          - entity_scope: link
            rule_type: random
            probability: 0.05

workflow:
  - step_type: MaxFlow
    name: failure_analysis
    source: "^(edge[1-3])$"
    sink: "^(edge[1-3])$"
    mode: pairwise
    failure_policy: mixed_failures
    iterations: 1000
    seed: 42
```

**Result**: 5 nodes, 4 links, 3 risk groups, failure policy with 4 weighted modes

## Example 12: Hardware Components and Cost Analysis

Using the components library for cost/power modeling.

```yaml
components:
  SpineRouter:
    component_type: chassis
    description: "64-port spine switch"
    capex: 55000.0
    power_watts: 2000.0
    power_watts_max: 3000.0
    capacity: 102400.0
    ports: 64

  LeafRouter:
    component_type: chassis
    description: "48-port leaf switch"
    capex: 25000.0
    power_watts: 800.0
    power_watts_max: 1200.0
    capacity: 38400.0
    ports: 48

  Optic400G:
    component_type: optic
    description: "400G DR4 pluggable"
    capex: 3000.0
    power_watts: 16.0
    capacity: 400.0

network:
  name: "datacenter-fabric"
  version: "2.0"

  groups:
    spine:
      node_count: 2
      name_template: "spine-{node_num}"
      attrs:
        hardware:
          component: SpineRouter
          count: 1
    leaf:
      node_count: 4
      name_template: "leaf-{node_num}"
      attrs:
        hardware:
          component: LeafRouter
          count: 1

  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_count: 2                    # 2 parallel links per pair
      link_params:
        capacity: 800
        cost: 1
        attrs:
          hardware:
            source:
              component: Optic400G
              count: 2
            target:
              component: Optic400G
              count: 2
              exclusive: true          # Dedicated optics (rounds up count)

workflow:
  - step_type: NetworkStats
    name: stats

  - step_type: CostPower
    name: cost_analysis
    include_disabled: false
    aggregation_level: 1               # Aggregate by top-level group
```

**Result**: 6 nodes, 16 links (4x2x2), component-based cost/power analysis

## Example 13: YAML Anchors for Reuse

Using `vars` section for DRY configuration.

```yaml
vars:
  default_link: &link_cfg
    capacity: 100
    cost: 1
  spine_attrs: &spine_attrs
    role: spine
    tier: 2
  leaf_attrs: &leaf_attrs
    role: leaf
    tier: 1

network:
  groups:
    spine:
      node_count: 2
      name_template: "spine-{node_num}"
      attrs:
        <<: *spine_attrs             # Merge anchor
        region: east

    leaf:
      node_count: 4
      name_template: "leaf-{node_num}"
      attrs:
        <<: *leaf_attrs
        region: east

  adjacency:
    - source: /leaf
      target: /spine
      pattern: mesh
      link_params:
        <<: *link_cfg                # Reuse link config
        attrs:
          link_type: fabric
```

**Result**: Anchors resolved during YAML parsing; cleaner, less repetitive config

## Example 14: One-to-One Adjacency and Zip Expansion

Demonstrating pairwise connectivity patterns.

```yaml
network:
  groups:
    # 4 servers, 2 switches - compatible for one_to_one (4 is multiple of 2)
    server[1-4]:
      node_count: 1
      name_template: "srv"
    switch[1-2]:
      node_count: 1
      name_template: "sw"

  adjacency:
    # one_to_one: server1->switch1, server2->switch2, server3->switch1, server4->switch2
    - source: /server
      target: /switch
      pattern: one_to_one
      link_params:
        capacity: 100

    # zip expansion: pairs variables by index (equal-length lists required)
    - source: "server${idx}"
      target: "switch${sw}"
      expand_vars:
        idx: [1, 2]
        sw: [1, 2]
      expansion_mode: zip            # server1->switch1, server2->switch2
      pattern: one_to_one
      link_params:
        capacity: 50
        cost: 2
```

**Result**: Demonstrates one_to_one modulo wrap and zip expansion mode

## Example 15: Traffic Demands with Variable Expansion and Group Modes

Advanced demand configuration.

```yaml
network:
  nodes:
    dc1_leaf1: {attrs: {dc: dc1, role: leaf}}
    dc1_leaf2: {attrs: {dc: dc1, role: leaf}}
    dc2_leaf1: {attrs: {dc: dc2, role: leaf}}
    dc2_leaf2: {attrs: {dc: dc2, role: leaf}}
    dc3_leaf1: {attrs: {dc: dc3, role: leaf}}
  links:
    - {source: dc1_leaf1, target: dc2_leaf1, link_params: {capacity: 100}}
    - {source: dc1_leaf2, target: dc2_leaf2, link_params: {capacity: 100}}
    - {source: dc2_leaf1, target: dc3_leaf1, link_params: {capacity: 100}}

traffic_matrix_set:
  # Variable expansion in demands
  inter_dc:
    - source: "^${src}/.*"
      sink: "^${dst}/.*"
      demand: 50
      expand_vars:
        src: [dc1, dc2]
        dst: [dc2, dc3]
      expansion_mode: zip            # dc1->dc2, dc2->dc3

  # Group modes with group_by
  grouped:
    - source:
        group_by: dc
      sink:
        group_by: dc
      demand: 100
      mode: pairwise
      group_mode: per_group          # Separate demand per group pair
      priority: 1
      demand_placed: 10.0            # 10 units pre-placed
      flow_policy_config: SHORTEST_PATHS_WCMP
```

**Result**: Shows variable expansion in demands, group_mode, priority, demand_placed

## Example 16: Hierarchical Risk Groups

Nested risk group structure with children.

```yaml
network:
  nodes:
    rack1_srv1: {risk_groups: [Rack1_Card1]}
    rack1_srv2: {risk_groups: [Rack1_Card1]}
    rack1_srv3: {risk_groups: [Rack1_Card2]}
    rack2_srv1: {risk_groups: [Rack2]}
  links:
    - {source: rack1_srv1, target: rack2_srv1, link_params: {capacity: 100}}
    - {source: rack1_srv2, target: rack2_srv1, link_params: {capacity: 100}}
    - {source: rack1_srv3, target: rack2_srv1, link_params: {capacity: 100}}

risk_groups:
  - name: Rack1
    attrs: {location: "DC1-Row1"}
    children:
      - name: Rack1_Card1
        attrs: {slot: 1}
      - name: Rack1_Card2
        attrs: {slot: 2}
  - name: Rack2
    disabled: false
    attrs: {location: "DC1-Row2"}

failure_policy_set:
  hierarchical:
    fail_risk_groups: true
    fail_risk_group_children: true   # Failing Rack1 also fails Card1, Card2
    modes:
      - weight: 1.0
        rules:
          - entity_scope: risk_group
            rule_type: choice
            count: 1
            conditions:
              - attr: location
                operator: contains    # String contains
                value: "DC1"
```

**Result**: Hierarchical risk groups with recursive child failure expansion

## Example 17: Additional Selector Operators

Demonstrating all condition operators.

```yaml
network:
  nodes:
    srv1: {attrs: {tier: 1, tags: [prod, web], region: null}}
    srv2: {attrs: {tier: 2, tags: [prod, db], region: east}}
    srv3: {attrs: {tier: 3, tags: [dev], region: west}}
    srv4: {attrs: {tier: 2}}
  links:
    - {source: srv1, target: srv2, link_params: {capacity: 100}}
    - {source: srv2, target: srv3, link_params: {capacity: 100}}
    - {source: srv3, target: srv4, link_params: {capacity: 100}}

traffic_matrix_set:
  filtered:
    # Tier comparison operators
    - source:
        match:
          conditions:
            - attr: tier
              operator: ">="
              value: 2
      sink:
        match:
          conditions:
            - attr: tier
              operator: "<"
              value: 3
      demand: 50
      mode: pairwise

    # List membership operators
    - source:
        match:
          conditions:
            - attr: region
              operator: in
              value: [east, west]
      sink:
        match:
          conditions:
            - attr: tags
              operator: contains     # List contains value
              value: prod
      demand: 25
      mode: combine

    # Existence operators
    - source:
        match:
          conditions:
            - attr: region
              operator: any_value    # Attribute exists and not null
      sink:
        match:
          conditions:
            - attr: region
              operator: no_value     # Attribute missing or null
      demand: 10
      mode: pairwise
```

**Result**: Demonstrates `>=`, `<`, `in`, `contains`, `any_value`, `no_value` operators
