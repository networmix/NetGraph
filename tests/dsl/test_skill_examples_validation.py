"""Comprehensive validation of all 19 examples from EXAMPLES.md in the Claude skill.

This test file validates that every example in the Claude skill documentation
parses correctly and produces the expected results.
"""

import pytest

from ngraph.scenario import Scenario


# =============================================================================
# Example 1: Simple Data Center
# =============================================================================
def test_example_1_simple_data_center():
    """Example 1: Simple Data Center - leaf-spine topology with traffic analysis.

    Expected: 6 nodes (4 leaf + 2 spine), 8 links (4x2 mesh)
    """
    yaml_content = """
network:
  nodes:
    leaf:
      count: 4
      template: "leaf{n}"
      attrs:
        role: leaf
    spine:
      count: 2
      template: "spine{n}"
      attrs:
        role: spine
  links:
    - source: /leaf
      target: /spine
      pattern: mesh
      capacity: 100
      cost: 1

demands:
  default:
    - source: "^leaf/.*"
      target: "^leaf/.*"
      volume: 50
      mode: pairwise

failures:
  single_link:
    modes:
      - weight: 1.0
        rules:
          - scope: link
            mode: choice
            count: 1

workflow:
  - type: NetworkStats
    name: stats
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 4 leaf + 2 spine = 6
    assert len(scenario.network.nodes) == 6, (
        f"Expected 6 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count: 4 leaf * 2 spine = 8 mesh links
    assert len(scenario.network.links) == 8, (
        f"Expected 8 links, got {len(scenario.network.links)}"
    )

    # Validate node names
    expected_nodes = [
        "leaf/leaf1",
        "leaf/leaf2",
        "leaf/leaf3",
        "leaf/leaf4",
        "spine/spine1",
        "spine/spine2",
    ]
    for name in expected_nodes:
        assert name in scenario.network.nodes, f"Missing node: {name}"

    # Validate demands
    demands = scenario.demand_set.get_default_set()
    assert len(demands) == 1

    # Validate failure policy
    policy = scenario.failure_policy_set.get_policy("single_link")
    assert policy is not None
    assert len(policy.modes) == 1


# =============================================================================
# Example 2: Multi-Pod with Blueprint
# =============================================================================
def test_example_2_multi_pod_blueprint():
    """Example 2: Multi-Pod with Blueprint - two pods sharing a blueprint.

    Expected: 12 nodes (2 pods x 6 nodes), 20 links (16 internal + 4 inter-pod)
    """
    yaml_content = """
blueprints:
  clos_pod:
    nodes:
      leaf:
        count: 4
        template: "leaf{n}"
        attrs:
          role: leaf
      spine:
        count: 2
        template: "spine{n}"
        attrs:
          role: spine
    links:
      - source: /leaf
        target: /spine
        pattern: mesh
        capacity: 100

network:
  nodes:
    pod[1-2]:
      blueprint: clos_pod

  links:
    - source:
        path: "pod1/spine"
        match:
          conditions:
            - attr: role
              op: "=="
              value: spine
      target:
        path: "pod2/spine"
      pattern: mesh
      capacity: 400
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 2 pods * (4 leaf + 2 spine) = 12
    assert len(scenario.network.nodes) == 12, (
        f"Expected 12 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count: 2 pods * 8 internal + 4 inter-pod = 20
    assert len(scenario.network.links) == 20, (
        f"Expected 20 links, got {len(scenario.network.links)}"
    )


# =============================================================================
# Example 3: Backbone with Risk Groups
# =============================================================================
def test_example_3_backbone_risk_groups():
    """Example 3: Backbone with Risk Groups - WAN with shared-risk link groups.

    Expected: 3 nodes, 3 links, 2 risk groups
    """
    yaml_content = """
network:
  nodes:
    NewYork: {attrs: {site_type: core}}
    Chicago: {attrs: {site_type: core}}
    LosAngeles: {attrs: {site_type: core}}

  links:
    # Parallel diverse paths
    - source: NewYork
      target: Chicago
      capacity: 100
      cost: 10
      risk_groups: [RG_NY_CHI]
    - source: NewYork
      target: Chicago
      capacity: 100
      cost: 10
    # Single path
    - source: Chicago
      target: LosAngeles
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

failures:
  srlg_failure:
    modes:
      - weight: 1.0
        rules:
          - scope: risk_group
            mode: choice
            count: 1
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 3, (
        f"Expected 3 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count
    assert len(scenario.network.links) == 3, (
        f"Expected 3 links, got {len(scenario.network.links)}"
    )

    # Validate risk groups
    assert len(scenario.network.risk_groups) == 2, (
        f"Expected 2 risk groups, got {len(scenario.network.risk_groups)}"
    )
    assert "RG_NY_CHI" in scenario.network.risk_groups
    assert "RG_CHI_LA" in scenario.network.risk_groups


# =============================================================================
# Example 4: Variable Expansion at Scale
# =============================================================================
def test_example_4_variable_expansion():
    """Example 4: Variable Expansion at Scale - large fabric.

    Expected: 1540 nodes (4x8x48 compute + 4 spine), 6144 links
    """
    yaml_content = """
network:
  nodes:
    plane[1-4]/rack[1-8]:
      count: 48
      template: "server{n}"
      attrs:
        role: compute

    fabric/spine[1-4]:
      count: 1
      template: "spine"
      attrs:
        role: spine

  links:
    - source: "plane${p}/rack${r}"
      target: "fabric/spine${s}"
      expand:
        vars:
          p: [1, 2, 3, 4]
          r: [1, 2, 3, 4, 5, 6, 7, 8]
          s: [1, 2, 3, 4]
        mode: cartesian
      pattern: mesh
      capacity: 100
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 4 planes * 8 racks * 48 servers + 4 spine = 1536 + 4 = 1540
    assert len(scenario.network.nodes) == 1540, (
        f"Expected 1540 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count:
    # Each (plane, rack) combination connects to all 4 spines with mesh pattern
    # 4 planes * 8 racks = 32 combinations
    # Each combination: 48 servers mesh with 1 spine node = 48 links per spine
    # 32 combinations * 4 spines * 48 = 6144 links
    assert len(scenario.network.links) == 6144, (
        f"Expected 6144 links, got {len(scenario.network.links)}"
    )


# =============================================================================
# Example 5: Full Mesh Topology
# =============================================================================
def test_example_5_full_mesh():
    """Example 5: Full Mesh Topology - 4-node full mesh for testing.

    Expected: 4 nodes, 6 links (full mesh)
    """
    yaml_content = """
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
      capacity: 2.0
      cost: 1.0
    - source: N1
      target: N3
      capacity: 1.0
      cost: 1.0
    - source: N1
      target: N4
      capacity: 2.0
      cost: 1.0
    - source: N2
      target: N3
      capacity: 2.0
      cost: 1.0
    - source: N2
      target: N4
      capacity: 1.0
      cost: 1.0
    - source: N3
      target: N4
      capacity: 2.0
      cost: 1.0

failures:
  single_link_failure:
    modes:
      - weight: 1.0
        rules:
          - scope: link
            mode: choice
            count: 1

demands:
  baseline:
    - source: "^N([1-4])$"
      target: "^N([1-4])$"
      volume: 12.0
      mode: pairwise

workflow:
  - type: NetworkStats
    name: stats
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 4, (
        f"Expected 4 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count (full mesh of 4 nodes = 6 links)
    assert len(scenario.network.links) == 6, (
        f"Expected 6 links, got {len(scenario.network.links)}"
    )

    # Validate seed
    assert scenario.seed == 42


# =============================================================================
# Example 6: Attribute-Based Selectors
# =============================================================================
def test_example_6_attribute_selectors():
    """Example 6: Attribute-Based Selectors - using match conditions.

    Expected: 8 nodes, 8 links (only rack-1 servers connect to switches)
    """
    yaml_content = """
network:
  nodes:
    servers:
      count: 4
      template: "srv{n}"
      attrs:
        role: compute
        rack: "rack-1"
    servers_b:
      count: 2
      template: "srvb{n}"
      attrs:
        role: compute
        rack: "rack-9"
    switches:
      count: 2
      template: "sw{n}"
      attrs:
        tier: spine

  links:
    - source:
        path: "/servers"
        match:
          logic: and
          conditions:
            - attr: role
              op: "=="
              value: compute
            - attr: rack
              op: "!="
              value: "rack-9"
      target:
        path: "/switches"
        match:
          conditions:
            - attr: tier
              op: "=="
              value: spine
      pattern: mesh
      capacity: 10
      cost: 1
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 4 servers + 2 servers_b + 2 switches = 8
    assert len(scenario.network.nodes) == 8, (
        f"Expected 8 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count: only rack-1 servers (4) connect to switches (2) = 8 links
    assert len(scenario.network.links) == 8, (
        f"Expected 8 links, got {len(scenario.network.links)}"
    )


# =============================================================================
# Example 7: Blueprint with Parameter Overrides
# =============================================================================
def test_example_7_blueprint_params():
    """Example 7: Blueprint with Parameter Overrides.

    Expected: Node Main/leaf/leaf1 has attrs.some_field.nested_key = 999
    """
    yaml_content = """
blueprints:
  bp1:
    nodes:
      leaf:
        count: 1
        attrs:
          some_field:
            nested_key: 111

network:
  nodes:
    Main:
      blueprint: bp1
      params:
        leaf.attrs.some_field.nested_key: 999
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Find the leaf node
    leaf_nodes = [n for n in scenario.network.nodes if "leaf" in n]
    assert len(leaf_nodes) == 1, f"Expected 1 leaf node, got {len(leaf_nodes)}"

    leaf_node = scenario.network.nodes[leaf_nodes[0]]
    assert leaf_node.attrs["some_field"]["nested_key"] == 999, (
        f"Expected nested_key=999, got {leaf_node.attrs['some_field']['nested_key']}"
    )


# =============================================================================
# Example 8: Node and Link Rules
# =============================================================================
def test_example_8_node_link_rules():
    """Example 8: Node and Link Rules - modifying topology after creation.

    Expected: Switches 1 and 3 disabled, specific link upgraded to 200 capacity
    """
    yaml_content = """
blueprints:
  test_bp:
    nodes:
      switches:
        count: 3
        template: "switch{n}"

network:
  nodes:
    group1:
      count: 2
      template: "node{n}"
    group2:
      count: 2
      template: "node{n}"
    my_clos1:
      blueprint: test_bp

  links:
    - source: /group1
      target: /group2
      pattern: mesh
      capacity: 100
      cost: 10

  node_rules:
    - path: "^my_clos1/switches/switch(1|3)$"
      disabled: true
      attrs:
        maintenance_mode: active
        hw_type: newer_model

  link_rules:
    - source: "^group1/node1$"
      target: "^group2/node1$"
      capacity: 200
      cost: 5
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate switches 1 and 3 are disabled
    switch1 = scenario.network.nodes.get("my_clos1/switches/switch1")
    switch3 = scenario.network.nodes.get("my_clos1/switches/switch3")
    switch2 = scenario.network.nodes.get("my_clos1/switches/switch2")

    assert switch1 is not None and switch1.disabled, "switch1 should be disabled"
    assert switch3 is not None and switch3.disabled, "switch3 should be disabled"
    assert switch2 is not None and not switch2.disabled, (
        "switch2 should not be disabled"
    )

    # Validate link rule applied
    upgraded_link = None
    for link in scenario.network.links.values():
        if link.source == "group1/node1" and link.target == "group2/node1":
            upgraded_link = link
            break

    assert upgraded_link is not None, "Upgraded link not found"
    assert upgraded_link.capacity == 200, (
        f"Expected capacity 200, got {upgraded_link.capacity}"
    )
    assert upgraded_link.cost == 5, f"Expected cost 5, got {upgraded_link.cost}"


# =============================================================================
# Example 9: Complete Traffic Analysis
# =============================================================================
def test_example_9_traffic_analysis():
    """Example 9: Complete Traffic Analysis - full workflow with MSD and placement.

    Expected: 40 nodes per pod (4 spine + 16 leaf), 2 pods, workflow steps defined
    """
    yaml_content = """
seed: 42

blueprints:
  Clos_L16_S4:
    nodes:
      spine:
        count: 4
        template: spine{n}
        attrs:
          role: spine
      leaf:
        count: 16
        template: leaf{n}
        attrs:
          role: leaf
    links:
      - source: /leaf
        target: /spine
        pattern: mesh
        capacity: 3200
        cost: 1

network:
  nodes:
    metro1/pop[1-2]:
      blueprint: Clos_L16_S4
      attrs:
        metro_name: new-york
        node_type: pop

demands:
  baseline:
    - source: "^metro1/pop1/.*"
      target: "^metro1/pop2/.*"
      volume: 15000.0
      mode: pairwise
      flow_policy: TE_WCMP_UNLIM

failures:
  single_link:
    modes:
      - weight: 1.0
        rules:
          - scope: link
            mode: choice
            count: 1

workflow:
  - type: NetworkStats
    name: network_statistics
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 2 pops * (4 spine + 16 leaf) = 40
    assert len(scenario.network.nodes) == 40, (
        f"Expected 40 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate workflow steps
    assert len(scenario.workflow) == 1

    # Run workflow
    scenario.run()

    # Check stats were computed
    results = scenario.results.to_dict()
    assert "network_statistics" in results["steps"]
    assert results["steps"]["network_statistics"]["data"]["node_count"] == 40


# =============================================================================
# Example 10: Group-By Selectors
# =============================================================================
def test_example_10_group_by():
    """Example 10: Group-By Selectors - grouping nodes by attribute.

    Expected: 4 nodes, 2 links, traffic flows grouped by datacenter
    """
    yaml_content = """
network:
  nodes:
    dc1_srv1: {attrs: {dc: dc1, role: server}}
    dc1_srv2: {attrs: {dc: dc1, role: server}}
    dc2_srv1: {attrs: {dc: dc2, role: server}}
    dc2_srv2: {attrs: {dc: dc2, role: server}}
  links:
    - source: dc1_srv1
      target: dc2_srv1
      capacity: 100
    - source: dc1_srv2
      target: dc2_srv2
      capacity: 100

demands:
  inter_dc:
    - source:
        group_by: dc
      target:
        group_by: dc
      volume: 100
      mode: pairwise
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 4, (
        f"Expected 4 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count
    assert len(scenario.network.links) == 2, (
        f"Expected 2 links, got {len(scenario.network.links)}"
    )

    # Validate demands
    demands = scenario.demand_set.get_set("inter_dc")
    assert len(demands) == 1


# =============================================================================
# Example 11: Advanced Failure Policies
# =============================================================================
def test_example_11_advanced_failures():
    """Example 11: Advanced Failure Policies - weighted modes with conditions.

    Expected: 5 nodes, 4 links, 3 risk groups, failure policy with 4 modes
    """
    yaml_content = """
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
      capacity: 1000
      risk_groups: [RG_core]
    - source: core1
      target: edge1
      capacity: 400
      risk_groups: [RG_west]
    - source: core1
      target: edge3
      capacity: 200
      risk_groups: [RG_west]
    - source: core2
      target: edge2
      capacity: 400
      risk_groups: [RG_east]

risk_groups:
  - name: RG_core
    attrs: {tier: core, distance_km: 50}
  - name: RG_west
    attrs: {tier: edge, distance_km: 500}
  - name: RG_east
    attrs: {tier: edge, distance_km: 800}

failures:
  mixed_failures:
    expand_groups: true
    expand_children: false
    modes:
      # 40% chance: fail 1 edge node weighted by capacity
      - weight: 0.4
        attrs: {scenario: edge_failure}
        rules:
          - scope: node
            mode: choice
            count: 1
            match:
              conditions:
                - attr: role
                  op: "=="
                  value: edge
            weight_by: capacity_gbps

      # 35% chance: fail 1 risk group weighted by distance
      - weight: 0.35
        attrs: {scenario: srlg_failure}
        rules:
          - scope: risk_group
            mode: choice
            count: 1
            weight_by: distance_km

      # 15% chance: fail all west-region nodes
      - weight: 0.15
        attrs: {scenario: regional_outage}
        rules:
          - scope: node
            mode: all
            match:
              conditions:
                - attr: region
                  op: "=="
                  value: west

      # 10% chance: random link failures (5% each)
      - weight: 0.1
        attrs: {scenario: random_link}
        rules:
          - scope: link
            mode: random
            probability: 0.05
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 5, (
        f"Expected 5 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count
    assert len(scenario.network.links) == 4, (
        f"Expected 4 links, got {len(scenario.network.links)}"
    )

    # Validate risk groups
    assert len(scenario.network.risk_groups) == 3, (
        f"Expected 3 risk groups, got {len(scenario.network.risk_groups)}"
    )

    # Validate failure policy modes
    policy = scenario.failure_policy_set.get_policy("mixed_failures")
    assert len(policy.modes) == 4, f"Expected 4 modes, got {len(policy.modes)}"
    assert policy.expand_groups is True
    assert policy.expand_children is False


# =============================================================================
# Example 12: Hardware Components and Cost Analysis
# =============================================================================
def test_example_12_hardware_components():
    """Example 12: Hardware Components and Cost Analysis.

    Expected: 6 nodes, 16 links (4x2x2), components library populated
    """
    yaml_content = """
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

  nodes:
    spine:
      count: 2
      template: "spine{n}"
      attrs:
        hardware:
          component: SpineRouter
          count: 1
    leaf:
      count: 4
      template: "leaf{n}"
      attrs:
        hardware:
          component: LeafRouter
          count: 1

  links:
    - source: /leaf
      target: /spine
      pattern: mesh
      count: 2
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
            exclusive: true

workflow:
  - type: NetworkStats
    name: stats
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 2 spine + 4 leaf = 6
    assert len(scenario.network.nodes) == 6, (
        f"Expected 6 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count: 4 leaf * 2 spine * 2 parallel = 16
    assert len(scenario.network.links) == 16, (
        f"Expected 16 links, got {len(scenario.network.links)}"
    )

    # Validate components library
    assert len(scenario.components_library.components) == 3
    assert scenario.components_library.get("SpineRouter") is not None
    assert scenario.components_library.get("LeafRouter") is not None
    assert scenario.components_library.get("Optic400G") is not None


# =============================================================================
# Example 13: YAML Anchors for Reuse
# =============================================================================
def test_example_13_yaml_anchors():
    """Example 13: YAML Anchors for Reuse.

    Expected: Anchors resolved during YAML parsing, 6 nodes, 8 links
    """
    yaml_content = """
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
  nodes:
    spine:
      count: 2
      template: "spine{n}"
      attrs:
        <<: *spine_attrs
        region: east

    leaf:
      count: 4
      template: "leaf{n}"
      attrs:
        <<: *leaf_attrs
        region: east

  links:
    - source: /leaf
      target: /spine
      pattern: mesh
      <<: *link_cfg
      attrs:
        link_type: fabric
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 2 spine + 4 leaf = 6
    assert len(scenario.network.nodes) == 6, (
        f"Expected 6 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count: 4 leaf * 2 spine = 8
    assert len(scenario.network.links) == 8, (
        f"Expected 8 links, got {len(scenario.network.links)}"
    )

    # Validate anchor values were resolved
    spine_node = scenario.network.nodes.get("spine/spine1")
    assert spine_node.attrs["role"] == "spine"
    assert spine_node.attrs["tier"] == 2


# =============================================================================
# Example 14: One-to-One Pattern and Zip Expansion
# =============================================================================
def test_example_14_one_to_one_zip():
    """Example 14: One-to-One Pattern and Zip Expansion.

    Expected: Demonstrates one_to_one modulo wrap and zip expansion
    """
    yaml_content = """
network:
  nodes:
    # 4 servers, 2 switches - compatible for one_to_one (4 is multiple of 2)
    server[1-4]:
      count: 1
      template: "srv"
    switch[1-2]:
      count: 1
      template: "sw"

  links:
    # one_to_one: server1->switch1, server2->switch2, server3->switch1, server4->switch2
    - source: /server
      target: /switch
      pattern: one_to_one
      capacity: 100

    # zip expansion: pairs variables by index (equal-length lists required)
    - source: "server${idx}"
      target: "switch${sw}"
      expand:
        vars:
          idx: [1, 2]
          sw: [1, 2]
        mode: zip
      pattern: one_to_one
      capacity: 50
      cost: 2
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count: 4 servers + 2 switches = 6
    assert len(scenario.network.nodes) == 6, (
        f"Expected 6 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate links were created
    assert len(scenario.network.links) > 0, "Expected links to be created"


# =============================================================================
# Example 15: Traffic Demands with Variable Expansion and Group Modes
# =============================================================================
def test_example_15_demand_variables():
    """Example 15: Traffic Demands with Variable Expansion and Group Modes.

    Expected: Variable expansion in demands, group_mode, and priority
    """
    yaml_content = """
network:
  nodes:
    dc1_leaf1: {attrs: {dc: dc1, role: leaf}}
    dc1_leaf2: {attrs: {dc: dc1, role: leaf}}
    dc2_leaf1: {attrs: {dc: dc2, role: leaf}}
    dc2_leaf2: {attrs: {dc: dc2, role: leaf}}
    dc3_leaf1: {attrs: {dc: dc3, role: leaf}}
  links:
    - {source: dc1_leaf1, target: dc2_leaf1, capacity: 100}
    - {source: dc1_leaf2, target: dc2_leaf2, capacity: 100}
    - {source: dc2_leaf1, target: dc3_leaf1, capacity: 100}

demands:
  # Variable expansion in demands
  inter_dc:
    - source: "^${src}/.*"
      target: "^${dst}/.*"
      volume: 50
      expand:
        vars:
          src: [dc1, dc2]
          dst: [dc2, dc3]
        mode: zip

  # Group modes with group_by
  grouped:
    - source:
        group_by: dc
      target:
        group_by: dc
      volume: 100
      mode: pairwise
      group_mode: per_group
      priority: 1
      flow_policy: SHORTEST_PATHS_WCMP
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 5, (
        f"Expected 5 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate inter_dc demands were expanded
    inter_dc_demands = scenario.demand_set.get_set("inter_dc")
    assert len(inter_dc_demands) == 2, (
        f"Expected 2 inter_dc demands, got {len(inter_dc_demands)}"
    )

    # Validate grouped demands
    grouped_demands = scenario.demand_set.get_set("grouped")
    assert len(grouped_demands) == 1


# =============================================================================
# Example 16: Hierarchical Risk Groups
# =============================================================================
def test_example_16_hierarchical_risk_groups():
    """Example 16: Hierarchical Risk Groups - nested risk group structure.

    Expected: Hierarchical risk groups with children, recursive failure expansion.

    Note: Nodes must reference risk groups defined at the top level. Child groups
    are used for hierarchical failure expansion (expand_children: true) but nodes
    reference the leaf-level groups which must be defined at the top level.
    """
    yaml_content = """
network:
  nodes:
    rack1_srv1: {risk_groups: [Rack1_Card1]}
    rack1_srv2: {risk_groups: [Rack1_Card1]}
    rack1_srv3: {risk_groups: [Rack1_Card2]}
    rack2_srv1: {risk_groups: [Rack2]}
  links:
    - {source: rack1_srv1, target: rack2_srv1, capacity: 100}
    - {source: rack1_srv2, target: rack2_srv1, capacity: 100}
    - {source: rack1_srv3, target: rack2_srv1, capacity: 100}

risk_groups:
  # All risk groups that nodes reference must be defined at top level
  - name: Rack1_Card1
    attrs: {slot: 1, parent: Rack1}
  - name: Rack1_Card2
    attrs: {slot: 2, parent: Rack1}
  - name: Rack2
    disabled: false
    attrs: {location: "DC1-Row2"}
  # Parent risk group with children for hierarchical failure expansion
  - name: Rack1
    attrs: {location: "DC1-Row1"}
    children:
      - name: Rack1_Card1
      - name: Rack1_Card2

failures:
  hierarchical:
    expand_groups: true
    expand_children: true
    modes:
      - weight: 1.0
        rules:
          - scope: risk_group
            mode: choice
            count: 1
            match:
              conditions:
                - attr: location
                  op: contains
                  value: "DC1"
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 4, (
        f"Expected 4 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate all risk groups exist at top level
    assert "Rack1" in scenario.network.risk_groups
    assert "Rack2" in scenario.network.risk_groups
    assert "Rack1_Card1" in scenario.network.risk_groups
    assert "Rack1_Card2" in scenario.network.risk_groups

    # Validate Rack1 has children (for hierarchical expansion)
    rack1 = scenario.network.risk_groups["Rack1"]
    assert len(rack1.children) == 2, f"Expected 2 children, got {len(rack1.children)}"

    # Validate failure policy
    policy = scenario.failure_policy_set.get_policy("hierarchical")
    assert policy.expand_groups is True
    assert policy.expand_children is True


# =============================================================================
# Example 17: Risk Group Membership Rules
# =============================================================================
def test_example_17_membership_rules():
    """Example 17: Risk Group Membership Rules - dynamic assignment by attributes.

    Expected: Nodes and links automatically assigned to risk groups
    """
    yaml_content = """
network:
  nodes:
    core1: {attrs: {role: core, tier: 3, datacenter: dc1}}
    core2: {attrs: {role: core, tier: 3, datacenter: dc2}}
    edge1: {attrs: {role: edge, tier: 1, datacenter: dc1}}
    edge2: {attrs: {role: edge, tier: 1, datacenter: dc2}}
  links:
    - source: core1
      target: core2
      capacity: 1000
      attrs:
        route_type: backbone
        path_id: primary
    - source: core1
      target: edge1
      capacity: 400

risk_groups:
  # Assign all core tier-3 nodes
  - name: CoreTier3
    membership:
      scope: node
      match:
        logic: and
        conditions:
          - attr: role
            op: "=="
            value: core
          - attr: tier
            op: "=="
            value: 3

  # Assign links by route type
  - name: BackboneLinks
    membership:
      scope: link
      match:
        logic: and
        conditions:
          - attr: route_type
            op: "=="
            value: backbone

  # String shorthand for simple groups
  - "ManualGroup1"
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 4, (
        f"Expected 4 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate risk groups
    assert "CoreTier3" in scenario.network.risk_groups
    assert "BackboneLinks" in scenario.network.risk_groups
    assert "ManualGroup1" in scenario.network.risk_groups

    # Validate membership rule applied - core nodes should have CoreTier3
    core1 = scenario.network.nodes["core1"]
    core2 = scenario.network.nodes["core2"]
    assert "CoreTier3" in core1.risk_groups, (
        f"core1 should have CoreTier3, has {core1.risk_groups}"
    )
    assert "CoreTier3" in core2.risk_groups, (
        f"core2 should have CoreTier3, has {core2.risk_groups}"
    )

    # Validate link membership
    backbone_link = None
    for link in scenario.network.links.values():
        if link.source == "core1" and link.target == "core2":
            backbone_link = link
            break

    assert backbone_link is not None
    assert "BackboneLinks" in backbone_link.risk_groups, (
        f"Backbone link should have BackboneLinks, has {backbone_link.risk_groups}"
    )


# =============================================================================
# Example 18: Generated Risk Groups
# =============================================================================
def test_example_18_generated_risk_groups():
    """Example 18: Generated Risk Groups - create from unique attribute values.

    Expected: 6 risk groups created from datacenter, rack, and connection_type
    """
    yaml_content = """
network:
  nodes:
    srv1: {attrs: {datacenter: dc1, rack: r1}}
    srv2: {attrs: {datacenter: dc1, rack: r2}}
    srv3: {attrs: {datacenter: dc2, rack: r1}}
  links:
    - source: srv1
      target: srv2
      capacity: 100
      attrs:
        connection_type: intra_dc
    - source: srv2
      target: srv3
      capacity: 100
      attrs:
        connection_type: inter_dc

risk_groups:
  # Generate risk group per datacenter (from nodes)
  - generate:
      scope: node
      group_by: datacenter
      name: "DC_${value}"
      attrs:
        generated: true
        type: location

  # Generate risk group per rack (from nodes)
  - generate:
      scope: node
      group_by: rack
      name: "Rack_${value}"

  # Generate risk group per connection type (from links)
  - generate:
      scope: link
      group_by: connection_type
      name: "Links_${value}"
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 3, (
        f"Expected 3 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate generated risk groups exist
    # DC_dc1, DC_dc2 (2 groups from datacenter)
    # Rack_r1, Rack_r2 (2 groups from rack)
    # Links_intra_dc, Links_inter_dc (2 groups from connection_type)
    expected_rgs = [
        "DC_dc1",
        "DC_dc2",
        "Rack_r1",
        "Rack_r2",
        "Links_intra_dc",
        "Links_inter_dc",
    ]
    for rg_name in expected_rgs:
        assert rg_name in scenario.network.risk_groups, (
            f"Missing generated risk group: {rg_name}"
        )

    assert len(scenario.network.risk_groups) == 6, (
        f"Expected 6 risk groups, got {len(scenario.network.risk_groups)}"
    )


# =============================================================================
# Example 19: Additional Selector Operators
# =============================================================================
def test_example_19_selector_operators():
    """Example 19: Additional Selector Operators - all condition operators.

    Expected: Demonstrates >=, <, in, contains, exists, not_exists operators
    """
    yaml_content = """
network:
  nodes:
    srv1: {attrs: {tier: 1, tags: [prod, web], region: null}}
    srv2: {attrs: {tier: 2, tags: [prod, db], region: east}}
    srv3: {attrs: {tier: 3, tags: [dev], region: west}}
    srv4: {attrs: {tier: 2}}
  links:
    - {source: srv1, target: srv2, capacity: 100}
    - {source: srv2, target: srv3, capacity: 100}
    - {source: srv3, target: srv4, capacity: 100}

demands:
  filtered:
    # Tier comparison operators
    - source:
        match:
          conditions:
            - attr: tier
              op: ">="
              value: 2
      target:
        match:
          conditions:
            - attr: tier
              op: "<"
              value: 3
      volume: 50
      mode: pairwise

    # List membership operators
    - source:
        match:
          conditions:
            - attr: region
              op: in
              value: [east, west]
      target:
        match:
          conditions:
            - attr: tags
              op: contains
              value: prod
      volume: 25
      mode: combine

    # Existence operators
    - source:
        match:
          conditions:
            - attr: region
              op: exists
      target:
        match:
          conditions:
            - attr: region
              op: not_exists
      volume: 10
      mode: pairwise
"""
    scenario = Scenario.from_yaml(yaml_content)

    # Validate node count
    assert len(scenario.network.nodes) == 4, (
        f"Expected 4 nodes, got {len(scenario.network.nodes)}"
    )

    # Validate link count
    assert len(scenario.network.links) == 3, (
        f"Expected 3 links, got {len(scenario.network.links)}"
    )

    # Validate demands were parsed
    demands = scenario.demand_set.get_set("filtered")
    assert len(demands) == 3, f"Expected 3 demands, got {len(demands)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
