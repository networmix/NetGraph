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
    cost: 50000.0
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
        cost: 8000.0
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
    assert component.cost == 50000.0


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


def test_traffic_demands_example():
    """Test traffic demands definition."""
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

traffic_demands:
  - source_path: "source.*"
    sink_path: "sink.*"
    demand: 100
    mode: "combine"
    priority: 1
    attrs:
      service_type: "web"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.traffic_demands) == 1
    demand = scenario.traffic_demands[0]
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

failure_policy:
  fail_shared_risk_groups: true
  fail_risk_group_children: false
  use_cache: true
  attrs:
    custom_key: "value"
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
    assert scenario.failure_policy is not None
    assert scenario.failure_policy.fail_shared_risk_groups
    assert not scenario.failure_policy.fail_risk_group_children
    assert len(scenario.failure_policy.rules) == 1
    rule = scenario.failure_policy.rules[0]
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
  - step_type: EnableNodes
    path: "node.*"
    count: 2
    order: "name"
"""

    scenario = Scenario.from_yaml(yaml_content)
    assert len(scenario.workflow) == 2
    assert scenario.workflow[0].__class__.__name__ == "BuildGraph"
    assert scenario.workflow[1].__class__.__name__ == "_TransformStep"

    # Test running the workflow
    scenario.run()
    # Check that build_graph step was executed (BuildGraph uses empty name by default)
    build_graph_result = scenario.results.get("", "graph")
    assert build_graph_result is not None


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
