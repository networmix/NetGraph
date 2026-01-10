import pytest

from ngraph.scenario import Scenario


def test_basic_network_example():
    """Test basic network definition with direct nodes and links."""
    yaml_content = """
network:
  name: "NetworkName"
  version: "1.0"
  nodes:
    SEA:
      attrs:
        coords: [47.6062, -122.3321]
        hw_type: "router_model_A"
    SFO:
      attrs:
        coords: [37.7749, -122.4194]
        hw_type: "router_model_B"
  links:
    - source: SEA
      target: SFO
      capacity: 200
      cost: 6846
      attrs:
        distance_km: 1369.13
        media_type: "fiber"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert scenario.network.attrs["name"] == "NetworkName"
    assert scenario.network.attrs["version"] == "1.0"
    assert len(scenario.network.nodes) == 2
    # NetGraph models links as bidirectional by default (single link = 2 directional edges)
    assert len(scenario.network.links) == 1  # 1 link between NodeA and NodeB


def test_groups_example():
    """Test network groups with adjacency patterns."""
    yaml_content = """
network:
  nodes:
    direct_group_A:
      count: 2
      template: "server-{n}"
      attrs:
        os: "linux"
    direct_group_B:
      count: 2
      template: "switch-{n}"
      attrs:
        type: "switch"
  links:
    - source: /direct_group_A
      target: /direct_group_B
      pattern: "mesh"
      capacity: 100
      cost: 10
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should have 4 nodes total: 2 servers + 2 switches
    assert len(scenario.network.nodes) == 4
    # Should have mesh connections: 2*2 = 4 links
    assert len(scenario.network.links) == 4


def test_adjacency_selector_match_filters_nodes():
    """Adjacency selectors with match should filter nodes by attributes."""
    yaml_content = """
network:
  nodes:
    servers:
      count: 4
      template: "srv-{n}"
      attrs:
        role: "compute"
        rack: "rack-1"
    servers_b:
      count: 2
      template: "srvb-{n}"
      attrs:
        role: "compute"
        rack: "rack-9"
    switches:
      count: 2
      template: "sw-{n}"
      attrs:
        tier: "spine"

  links:
    - source:
        path: "/servers"
        match:
          logic: "and"
          conditions:
            - attr: "role"
              op: "=="
              value: "compute"
            - attr: "rack"
              op: "!="
              value: "rack-9"
      target:
        path: "/switches"
        match:
          conditions:
            - attr: "tier"
              op: "=="
              value: "spine"
      pattern: "mesh"
      capacity: 10
      cost: 1
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect only /servers (4 nodes) to be considered (servers_b excluded via rack != rack-9)
    # Mesh between 4 servers and 2 switches => 4*2 = 8 links
    assert len(scenario.network.links) == 8


def test_bracket_expansion():
    """Test bracket expansion in group names."""
    yaml_content = """
blueprints:
  simple_pod:
    nodes:
      switches:
        count: 2
        template: "sw-{n}"

network:
  nodes:
    pod[1-2]:
      blueprint: simple_pod
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should create pod1 and pod2, each with 2 switches = 4 nodes total
    assert len(scenario.network.nodes) == 4


def test_blueprint_example():
    """Test blueprint definition and usage."""
    yaml_content = """
blueprints:
  my_blueprint_name:
    nodes:
      group_name_1:
        count: 2
        template: "prefix-{n}"
        attrs:
          hw_type: "router_model_X"
          role: "leaf"
        risk_groups: ["RG1", "RG2"]
      group_name_2:
        count: 2
        template: "spine-{n}"
    links:
      - source: /group_name_1
        target: /group_name_2
        pattern: "mesh"
        capacity: 100
        cost: 10

network:
  nodes:
    instance_of_bp:
      blueprint: my_blueprint_name
      attrs:
        location: "rack1"

risk_groups:
  - "RG1"
  - "RG2"
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should have 4 nodes: 2 from group_name_1 + 2 from group_name_2
    assert len(scenario.network.nodes) == 4
    # Should have mesh connections: 2*2 = 4 links
    assert len(scenario.network.links) == 4


def test_components_example():
    """Test components library definition."""
    yaml_content = """
components:
  SpineChassis:
    component_type: "chassis"
    description: "High-capacity spine router chassis"
    capex: 50000.0
    power_watts: 2500.0
    power_watts_max: 3000.0
    capacity: 64000.0
    ports: 64
    count: 1
    attrs:
      vendor: "Example Corp"
      model: "EX-9000"
    children:
      LineCard400G:
        component_type: "linecard"
        capex: 8000.0
        power_watts: 400.0
        capacity: 12800.0
        ports: 32
        count: 4

network:
  nodes:
    spine-1:
      attrs:
        hw_component: "SpineChassis"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.components_library.components) == 1
    assert "SpineChassis" in scenario.components_library.components
    component = scenario.components_library.get("SpineChassis")
    assert component is not None
    assert component.component_type == "chassis"
    assert component.capex == 50000.0


def test_risk_groups_example():
    """Test risk groups definition."""
    yaml_content = """
risk_groups:
  - name: "Rack1"
    disabled: false
    attrs:
      location: "DC1_Floor2"
    children:
      - name: "Card1.1"
        children:
          - name: "PortGroup1.1.1"
      - name: "Card1.2"
  - name: "PowerSupplyUnitA"

network:
  nodes:
    server1:
      risk_groups: ["Rack1"]
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.network.risk_groups) == 2
    assert "Rack1" in scenario.network.risk_groups
    assert "PowerSupplyUnitA" in scenario.network.risk_groups
    rack1 = scenario.network.risk_groups["Rack1"]
    assert len(rack1.children) == 2


def test_demand_set_example():
    """Test traffic matrix set definition."""
    yaml_content = """
network:
  nodes:
    source1:
      attrs:
        role: "client"
    source2:
      attrs:
        role: "client"
    sink1:
      attrs:
        role: "server"
    sink2:
      attrs:
        role: "server"

demands:
  default:
    - source: "source.*"
      target: "sink.*"
      volume: 100
      mode: "combine"
      priority: 1
      attrs:
        service_type: "web"
"""

    scenario = Scenario.from_yaml(yaml_content)
    default_demands = scenario.demand_set.get_default_set()
    assert len(default_demands) == 1
    demand = default_demands[0]
    assert demand.source == "source.*"
    assert demand.target == "sink.*"
    assert demand.volume == 100
    assert demand.mode == "combine"


def test_failure_policy_example():
    """Test failure policy definition."""
    yaml_content = """
network:
  nodes:
    node1:
      attrs:
        role: "spine"
    node2:
      attrs:
        role: "leaf"

failures:
  default:
    expand_groups: true
    expand_children: false
    attrs:
      custom_key: "value"
    modes:
      - weight: 1.0
        rules:
          - scope: "node"
            match:
              logic: "and"
              conditions:
                - attr: "role"
                  op: "=="
                  value: "spine"
            mode: "all"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.failure_policy_set.policies) == 1
    policies = scenario.failure_policy_set.get_all_policies()
    assert len(policies) > 0
    default_policy = scenario.failure_policy_set.get_policy("default")
    assert default_policy.expand_groups
    assert not default_policy.expand_children
    assert len(default_policy.modes) == 1
    mode = default_policy.modes[0]
    assert len(mode.rules) == 1
    rule = mode.rules[0]
    assert rule.scope == "node"
    assert len(rule.conditions) == 1


def test_workflow_example():
    """Test workflow definition."""
    yaml_content = """
network:
  nodes:
    node1: {}
    node2: {}

workflow:
  - type: BuildGraph
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.workflow) == 1
    assert scenario.workflow[0].__class__.__name__ == "BuildGraph"

    # Test running the workflow
    scenario.run()
    # Check that build_graph step was executed (default unique name assigned)
    step_name = scenario.workflow[0].name
    exp = scenario.results.to_dict()
    assert exp["steps"][step_name]["data"].get("graph") is not None


def test_node_overrides_example():
    """Test node overrides functionality."""
    yaml_content = """
blueprints:
  test_bp:
    nodes:
      switches:
        count: 3
        template: "switch-{n}"

network:
  nodes:
    my_clos1:
      blueprint: test_bp

  node_rules:
    - path: "^my_clos1/switches/switch-(1|3)$"
      disabled: true
      attrs:
        maintenance_mode: "active"
        hw_type: "newer_model"
"""

    scenario = Scenario.from_yaml(yaml_content)

    # Check that switches 1 and 3 are disabled
    disabled_nodes = [
        name for name, node in scenario.network.nodes.items() if node.disabled
    ]
    assert len(disabled_nodes) == 2
    assert "my_clos1/switches/switch-1" in disabled_nodes
    assert "my_clos1/switches/switch-3" in disabled_nodes


def test_link_overrides_example():
    """Test link overrides functionality."""
    yaml_content = """
network:
  nodes:
    group1:
      count: 2
      template: "node-{n}"
    group2:
      count: 2
      template: "node-{n}"

  links:
    - source: /group1
      target: /group2
      pattern: "mesh"
      capacity: 100
      cost: 10

  link_rules:
    - source: "^group1/node-1$"
      target: "^group2/node-1$"
      capacity: 200
      cost: 5
"""

    scenario = Scenario.from_yaml(yaml_content)

    # Find the specific overridden link
    overridden_link = None
    for _link_id, link in scenario.network.links.items():
        if link.source == "group1/node-1" and link.target == "group2/node-1":
            overridden_link = link
            break

    assert overridden_link is not None
    assert overridden_link.capacity == 200
    assert overridden_link.cost == 5


def test_variable_expansion():
    """Test variable expansion in adjacency using $var syntax."""
    yaml_content = """
blueprints:
  test_expansion:
    nodes:
      plane1_rack:
        count: 2
        template: "rack-{n}"
      plane2_rack:
        count: 2
        template: "rack-{n}"
      spine:
        count: 2
        template: "spine-{n}"
    links:
      - source: "plane${p}_rack"
        target: "spine"
        expand:
          vars:
            p: [1, 2]
          mode: "cartesian"
        pattern: "mesh"
        capacity: 100

network:
  nodes:
    test_instance:
      blueprint: test_expansion
"""

    scenario = Scenario.from_yaml(yaml_content)

    # Should have nodes from both plane1_rack and plane2_rack connected to spine
    # 2 plane1_rack + 2 plane2_rack + 2 spine = 6 nodes
    assert len(scenario.network.nodes) == 6

    # Each plane rack group (2 nodes) connects to spine group (2 nodes) in mesh
    # 2 plane groups * 2 nodes each * 2 spine nodes = 4 * 2 = 8 links
    assert len(scenario.network.links) == 8


def test_unknown_blueprint_raises():
    """Using an unknown blueprint should raise ValueError with a clear message."""
    yaml_content = """
network:
  nodes:
    use_missing:
      blueprint: non_existent
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "unknown blueprint" in str(exc.value)


def test_one_to_one_mismatch_raises():
    """one_to_one requires sizes with a multiple factor; mismatch should error."""
    yaml_content = """
network:
  nodes:
    A:
      count: 3
    B:
      count: 2
  links:
    - source: /A
      target: /B
      pattern: one_to_one
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "requires sizes with a multiple factor" in str(exc.value)


def test_unknown_adjacency_pattern_raises():
    """Unknown link pattern should raise ValidationError."""
    import jsonschema

    yaml_content = """
network:
  nodes:
    N1: {}
    N2: {}
  links:
    - source: /N1
      target: /N2
      pattern: non_existent_pattern
"""

    with pytest.raises(jsonschema.ValidationError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "is not one of ['mesh', 'one_to_one']" in str(exc.value)


def test_direct_link_same_node_skipped():
    """A direct link with identical source and target is silently skipped (no self-loops)."""
    yaml_content = """
network:
  nodes:
    X: {}
  links:
    - source: X
      target: X
"""

    # Self-loop links are silently skipped by the mesh pattern
    scenario = Scenario.from_yaml(yaml_content)
    assert "X" in scenario.network.nodes
    assert len(scenario.network.links) == 0  # No link created


def test_nested_parameter_override_in_attrs():
    """Nested parameter override via params should modify node attrs."""
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
    # Expect a single node under Main/leaf
    nodes = [name for name in scenario.network.nodes if name.startswith("Main/leaf/")]
    assert len(nodes) == 1
    node = scenario.network.nodes[nodes[0]]
    assert node.attrs["some_field"]["nested_key"] == 999


def test_zip_variable_mismatch_raises():
    """Zip expansion requires all lists same length; mismatch should raise."""
    yaml_content = """
network:
  nodes:
    RackA:
      count: 1
    RackB:
      count: 1
    RackC:
      count: 1
  links:
    - source: /Rack${rack_id}
      target: /Rack${other_rack_id}
      expand:
        vars:
          rack_id: [A, B]
          other_rack_id: [C, A, B]
        mode: zip
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "zip expansion requires equal-length lists" in str(exc.value)


def test_direct_link_unknown_node_skipped():
    """Referencing an unknown node in a direct link creates no links (pattern finds no target)."""
    yaml_content = """
network:
  nodes:
    KnownNode: {}
  links:
    - source: KnownNode
      target: UnknownNode
"""

    # Link with unknown target node is silently skipped (no matching target)
    scenario = Scenario.from_yaml(yaml_content)
    assert "KnownNode" in scenario.network.nodes
    assert len(scenario.network.links) == 0  # No link created


def test_group_by_selector_inside_blueprint():
    """Test group_by selector in blueprint adjacency.

    When a blueprint adjacency uses a selector with group_by, nodes are
    grouped by that attribute value regardless of path prefix. This test
    ensures the expansion connects leaf->spine using attribute-based
    selectors inside the blueprint.
    """
    yaml_content = """
blueprints:
  bp_group:
    nodes:
      leaf:
        count: 2
        template: "leaf-{n}"
        attrs:
          role: "leaf"
      spine:
        count: 1
        template: "spine-{n}"
        attrs:
          role: "spine"
    links:
      - source:
          group_by: "role"
          match:
            conditions:
              - attr: "role"
                op: "=="
                value: "leaf"
        target:
          group_by: "role"
          match:
            conditions:
              - attr: "role"
                op: "=="
                value: "spine"
        pattern: "mesh"
        capacity: 10

network:
  nodes:
    pod1:
      blueprint: bp_group
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect 3 nodes total (2 leaf, 1 spine)
    assert len(scenario.network.nodes) == 3
    # Mesh between 2 leaf and 1 spine = 2 links
    assert len(scenario.network.links) == 2


def test_group_by_with_variable_expansion():
    """Test group_by selector combined with variable expansion.

    Validates that group_by selectors work correctly when the attribute
    name is generated via variable expansion using $var syntax.
    """
    yaml_content = """
blueprints:
  bp_group_vars:
    nodes:
      leaf:
        count: 2
        template: "leaf-{n}"
        attrs:
          src_role: "leaf"
      spine:
        count: 1
        template: "spine-{n}"
        attrs:
          dst_role: "spine"
    links:
      - source:
          group_by: "${src_attr}"
        target:
          group_by: "${dst_attr}"
        expand:
          vars:
            src_attr: ["src_role"]
            dst_attr: ["dst_role"]
        pattern: "mesh"
        capacity: 10

network:
  nodes:
    pod1:
      blueprint: bp_group_vars
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect 3 nodes total (2 leaf, 1 spine)
    assert len(scenario.network.nodes) == 3
    # Mesh between 2 leaf and 1 spine = 2 links
    assert len(scenario.network.links) == 2


def test_invalid_nodes_type_raises():
    """network.nodes must be a mapping; lists should raise a clear error."""
    yaml_content = """
network:
  nodes: []
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "'nodes' must be a mapping" in str(exc.value)


def test_invalid_links_type_raises():
    """network.links must be a list; mappings should raise a clear error."""
    yaml_content = """
network:
  nodes:
    A: {}
    B: {}
  links: {}
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "'links' must be a list" in str(exc.value)


def test_direct_link_missing_required_keys_raises():
    """Each direct link entry must contain 'source' and 'target'."""
    yaml_content = """
network:
  nodes:
    A: {}
    B: {}
  links:
    - capacity: 1
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "Each link definition must include 'source' and 'target'" in str(exc.value)
