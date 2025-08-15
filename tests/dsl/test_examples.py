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
      link_params:
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
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) == 2  # Bidirectional


def test_groups_example():
    """Test network groups with adjacency patterns."""
    yaml_content = """
network:
  groups:
    direct_group_A:
      node_count: 2
      name_template: "server-{node_num}"
      attrs:
        os: "linux"
    direct_group_B:
      node_count: 2
      name_template: "switch-{node_num}"
      attrs:
        type: "switch"
  adjacency:
    - source: /direct_group_A
      target: /direct_group_B
      pattern: "mesh"
      link_params:
        capacity: 100
        cost: 10
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should have 4 nodes total: 2 servers + 2 switches
    assert len(scenario.network.nodes) == 4
    # Should have mesh connections: 2*2 = 4 bidirectional links = 8 edges
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) == 8


def test_adjacency_selector_match_filters_nodes():
    """Adjacency selectors with match should filter nodes by attributes."""
    yaml_content = """
network:
  groups:
    servers:
      node_count: 4
      name_template: "srv-{node_num}"
      attrs:
        role: "compute"
        rack: "rack-1"
    servers_b:
      node_count: 2
      name_template: "srvb-{node_num}"
      attrs:
        role: "compute"
        rack: "rack-9"
    switches:
      node_count: 2
      name_template: "sw-{node_num}"
      attrs:
        tier: "spine"

  adjacency:
    - source:
        path: "/servers"
        match:
          logic: "and"
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
        capacity: 10
        cost: 1
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect only /servers (4 nodes) to be considered (servers_b excluded via rack != rack-9)
    # Mesh between 4 servers and 2 switches => 8 directed pairs but dedup as bidirectional added later.
    graph = scenario.network.to_strict_multidigraph()
    # 4*2*2 directions = 16 edges
    assert len(list(graph.edges())) == 16


def test_bracket_expansion():
    """Test bracket expansion in group names."""
    yaml_content = """
blueprints:
  simple_pod:
    groups:
      switches:
        node_count: 2
        name_template: "sw-{node_num}"

network:
  groups:
    pod[1-2]:
      use_blueprint: simple_pod
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should create pod1 and pod2, each with 2 switches = 4 nodes total
    assert len(scenario.network.nodes) == 4


def test_blueprint_example():
    """Test blueprint definition and usage."""
    yaml_content = """
blueprints:
  my_blueprint_name:
    groups:
      group_name_1:
        node_count: 2
        name_template: "prefix-{node_num}"
        attrs:
          hw_type: "router_model_X"
          role: "leaf"
        risk_groups: ["RG1", "RG2"]
      group_name_2:
        node_count: 2
        name_template: "spine-{node_num}"
    adjacency:
      - source: /group_name_1
        target: /group_name_2
        pattern: "mesh"
        link_params:
          capacity: 100
          cost: 10

network:
  groups:
    instance_of_bp:
      use_blueprint: my_blueprint_name
      attrs:
        location: "rack1"
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Should have 4 nodes: 2 from group_name_1 + 2 from group_name_2
    assert len(scenario.network.nodes) == 4
    # Should have mesh connections: 2*2 = 4 bidirectional links = 8 edges
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) == 8


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


def test_traffic_matrix_set_example():
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

traffic_matrix_set:
  default:
    - source_path: "source.*"
      sink_path: "sink.*"
      demand: 100
      mode: "combine"
      priority: 1
      attrs:
        service_type: "web"
"""

    scenario = Scenario.from_yaml(yaml_content)
    default_demands = scenario.traffic_matrix_set.get_default_matrix()
    assert len(default_demands) == 1
    demand = default_demands[0]
    assert demand.source_path == "source.*"
    assert demand.sink_path == "sink.*"
    assert demand.demand == 100
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

failure_policy_set:
  default:
    fail_risk_groups: true
    fail_risk_group_children: false
    attrs:
      custom_key: "value"
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "node"
            conditions:
              - attr: "role"
                operator: "=="
                value: "spine"
            logic: "and"
            rule_type: "all"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.failure_policy_set.policies) == 1
    policies = scenario.failure_policy_set.get_all_policies()
    assert len(policies) > 0
    default_policy = scenario.failure_policy_set.get_policy("default")
    assert default_policy.fail_risk_groups
    assert not default_policy.fail_risk_group_children
    assert len(default_policy.modes) == 1
    mode = default_policy.modes[0]
    assert len(mode.rules) == 1
    rule = mode.rules[0]
    assert rule.entity_scope == "node"
    assert len(rule.conditions) == 1


def test_workflow_example():
    """Test workflow definition."""
    yaml_content = """
network:
  nodes:
    node1: {}
    node2: {}

workflow:
  - step_type: BuildGraph
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
    groups:
      switches:
        node_count: 3
        name_template: "switch-{node_num}"

network:
  groups:
    my_clos1:
      use_blueprint: test_bp

  node_overrides:
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
  groups:
    group1:
      node_count: 2
      name_template: "node-{node_num}"
    group2:
      node_count: 2
      name_template: "node-{node_num}"

  adjacency:
    - source: /group1
      target: /group2
      pattern: "mesh"
      link_params:
        capacity: 100
        cost: 10

  link_overrides:
    - source: "^group1/node-1$"
      target: "^group2/node-1$"
      link_params:
        capacity: 200
        cost: 5
"""

    scenario = Scenario.from_yaml(yaml_content)

    # Find the specific overridden link
    overridden_edge = None
    graph = scenario.network.to_strict_multidigraph()
    for u, v, data in graph.edges(data=True):
        if u == "group1/node-1" and v == "group2/node-1":
            overridden_edge = data
            break

    assert overridden_edge is not None
    assert overridden_edge["capacity"] == 200
    assert overridden_edge["cost"] == 5


def test_variable_expansion():
    """Test variable expansion in adjacency."""
    yaml_content = """
blueprints:
  test_expansion:
    groups:
      plane1_rack:
        node_count: 2
        name_template: "rack-{node_num}"
      plane2_rack:
        node_count: 2
        name_template: "rack-{node_num}"
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
    adjacency:
      - source: "plane{p}_rack"
        target: "spine"
        expand_vars:
          p: [1, 2]
        expansion_mode: "cartesian"
        pattern: "mesh"
        link_params:
          capacity: 100

network:
  groups:
    test_instance:
      use_blueprint: test_expansion
"""

    scenario = Scenario.from_yaml(yaml_content)

    # Should have nodes from both plane1_rack and plane2_rack connected to spine
    # 2 plane1_rack + 2 plane2_rack + 2 spine = 6 nodes
    assert len(scenario.network.nodes) == 6

    # Each plane rack group (2 nodes) connects to spine group (2 nodes) in mesh
    # 2 plane groups * 2 nodes each * 2 spine nodes * 2 directions = 16 edges
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) == 16


def test_unknown_blueprint_raises():
    """Using an unknown blueprint should raise ValueError with a clear message."""
    yaml_content = """
network:
  groups:
    use_missing:
      use_blueprint: non_existent
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "unknown blueprint" in str(exc.value)


def test_one_to_one_mismatch_raises():
    """one_to_one requires sizes with a multiple factor; mismatch should error."""
    yaml_content = """
network:
  groups:
    A:
      node_count: 3
    B:
      node_count: 2
  adjacency:
    - source: /A
      target: /B
      pattern: one_to_one
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "requires sizes with a multiple factor" in str(exc.value)


def test_unknown_adjacency_pattern_raises():
    """Unknown adjacency pattern should raise ValueError."""
    yaml_content = """
network:
  nodes:
    N1: {}
    N2: {}
  adjacency:
    - source: /N1
      target: /N2
      pattern: non_existent_pattern
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "Unknown adjacency pattern" in str(exc.value)


def test_direct_link_same_node_raises():
    """A direct link with identical source and target should raise ValueError."""
    yaml_content = """
network:
  nodes:
    X: {}
  links:
    - source: X
      target: X
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "Link cannot have the same source and target" in str(exc.value)


def test_nested_parameter_override_in_attrs():
    """Nested parameter override via parameters should modify node attrs."""
    yaml_content = """
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
  groups:
    RackA:
      node_count: 1
    RackB:
      node_count: 1
    RackC:
      node_count: 1
  adjacency:
    - source: /Rack{rack_id}
      target: /Rack{other_rack_id}
      expand_vars:
        rack_id: [A, B]
        other_rack_id: [C, A, B]
      expansion_mode: zip
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "zip expansion requires all lists be the same length" in str(exc.value)


def test_direct_link_unknown_node_raises():
    """Referencing an unknown node in a direct link should raise ValueError."""
    yaml_content = """
network:
  nodes:
    KnownNode: {}
  links:
    - source: KnownNode
      target: UnknownNode
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "Link references unknown node(s)" in str(exc.value)


def test_attr_selector_inside_blueprint_paths():
    """Attribute directive paths inside blueprint adjacency should not be prefixed.

    When a blueprint adjacency uses a selector with path "attr:<name>", the
    attribute directive must be treated as global, not joined with the blueprint
    instantiation path. This test ensures the expansion connects leaf->spine
    using attribute-based selectors inside the blueprint.
    """
    yaml_content = """
blueprints:
  bp_attr:
    groups:
      leaf:
        node_count: 2
        name_template: "leaf-{node_num}"
        attrs:
          role: "leaf"
      spine:
        node_count: 1
        name_template: "spine-{node_num}"
        attrs:
          role: "spine"
    adjacency:
      - source:
          path: "attr:role"
          match:
            conditions:
              - attr: "role"
                operator: "=="
                value: "leaf"
        target:
          path: "attr:role"
          match:
            conditions:
              - attr: "role"
                operator: "=="
                value: "spine"
        pattern: "mesh"
        link_params:
          capacity: 10

network:
  groups:
    pod1:
      use_blueprint: bp_attr
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect 3 nodes total (2 leaf, 1 spine)
    assert len(scenario.network.nodes) == 3
    # Mesh between 2 leaf and 1 spine = 2 bidirectional adjacencies => 4 edges
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) == 4


def test_attr_selector_with_expand_vars_inside_blueprint_paths():
    """Attribute directive with expand_vars inside blueprint adjacency should not be prefixed.

    Use different attribute names for source and target to avoid cross-connections and
    validate that at least some edges are created when using attr: paths generated via
    expand_vars within a blueprint adjacency.
    """
    yaml_content = """
blueprints:
  bp_attr_vars:
    groups:
      leaf:
        node_count: 2
        name_template: "leaf-{node_num}"
        attrs:
          src_role: "leaf"
      spine:
        node_count: 1
        name_template: "spine-{node_num}"
        attrs:
          dst_role: "spine"
    adjacency:
      - source: "attr:{src_key}"
        target: "attr:{dst_key}"
        expand_vars:
          src_key: ["src_role"]
          dst_key: ["dst_role"]
        pattern: "mesh"
        link_params:
          capacity: 10

network:
  groups:
    pod1:
      use_blueprint: bp_attr_vars
"""

    scenario = Scenario.from_yaml(yaml_content)
    # Expect 3 nodes total (2 leaf, 1 spine)
    assert len(scenario.network.nodes) == 3
    # Without the fix, zero edges would be created due to prefixed attr: paths.
    graph = scenario.network.to_strict_multidigraph()
    assert len(list(graph.edges())) > 0


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
    - link_params: {capacity: 1}
"""

    with pytest.raises(ValueError) as exc:
        Scenario.from_yaml(yaml_content)
    assert "Each link definition must include 'source' and 'target'" in str(exc.value)
