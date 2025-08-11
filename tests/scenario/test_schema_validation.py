"""Tests for JSON schema validation of NetGraph scenario files."""

import json
from pathlib import Path

import pytest
import yaml

from ngraph.scenario import Scenario

jsonschema = pytest.importorskip("jsonschema")


class TestSchemaValidation:
    """Tests for JSON schema validation functionality."""

    @pytest.fixture
    def schema(self):
        """Load the NetGraph scenario JSON schema."""
        schema_path = Path(__file__).parents[2] / "schemas" / "scenario.json"
        with open(schema_path) as f:
            return json.load(f)

    def test_schema_validates_simple_scenario(self, schema):
        """Test that the schema validates a simple representative scenario."""
        simple_scenario = """
network:
  name: Simple Test Network
  version: 1.0
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 1000.0
        cost: 10
        risk_groups: ["link_rg_1"]
    - source: B
      target: C
      link_params:
        capacity: 1000.0
        cost: 10
        risk_groups: ["link_rg_2"]

risk_groups:
  - name: link_rg_1
  - name: link_rg_2

failure_policy_set:
  default:
    attrs:
      description: "Test single link failure policy"
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "link"
            rule_type: "choice"
            count: 1

workflow:
  - step_type: BuildGraph
    name: build_graph
  - step_type: CapacityEnvelopeAnalysis
    name: capacity_test
    source_path: "A"
    sink_path: "C"
    iterations: 1
    baseline: false
    failure_policy: null
    mode: "combine"
"""
        data = yaml.safe_load(simple_scenario)

        # Should not raise any validation errors
        jsonschema.validate(data, schema)

    def test_schema_validates_test_integration(self, schema):
        """Validate scenario YAMLs under tests/integration against the schema."""
        test_integration_dir = Path(__file__).parents[1] / "integration"

        for yaml_file in test_integration_dir.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            jsonschema.validate(data, schema)

    def test_schema_rejects_invalid_top_level_key(self, schema):
        """Test that the schema rejects invalid top-level keys."""
        invalid_data = {
            "network": {"nodes": {}, "links": []},
            "invalid_key": "should_not_be_allowed",
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_data, schema)

    def test_schema_validates_risk_groups_structure(self, schema):
        """Test that the schema correctly validates risk groups structure."""
        valid_data = {
            "network": {"nodes": {}, "links": []},
            "risk_groups": [
                {
                    "name": "test_rg",
                    "attrs": {"location": "datacenter1"},
                    "children": [{"name": "child_rg"}],
                }
            ],
        }

        # Should not raise any validation errors
        jsonschema.validate(valid_data, schema)

    def test_schema_requires_risk_group_name(self, schema):
        """Test that the schema requires risk groups to have a name."""
        invalid_data = {
            "network": {"nodes": {}, "links": []},
            "risk_groups": [
                {
                    "attrs": {"location": "datacenter1"}
                    # Missing required "name" field
                }
            ],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_data, schema)

    def test_schema_validates_vars_section(self, schema):
        """Test that the schema validates the vars section for YAML anchors."""
        valid_data = {
            "vars": {
                "default_capacity": 100,
                "common_attrs": {"region": "datacenter1", "type": "switch"},
            },
            "network": {"nodes": {}, "links": []},
        }

        # Should not raise any validation errors
        jsonschema.validate(valid_data, schema)

    def test_schema_validates_link_risk_groups(self, schema):
        """Test that the schema validates risk_groups in link_params."""
        valid_data = {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [
                    {
                        "source": "A",
                        "target": "B",
                        "link_params": {
                            "capacity": 100,
                            "cost": 1,
                            "risk_groups": ["rg1", "rg2"],
                        },
                    }
                ],
            }
        }

        # Should not raise any validation errors
        jsonschema.validate(valid_data, schema)

    def test_schema_validates_failure_policy_structure(self, schema):
        """Test that the schema validates failure policy structure."""
        valid_data = {
            "network": {"nodes": {}, "links": []},
            "failure_policy_set": {
                "default": {
                    "attrs": {"name": "test_policy"},
                    "modes": [
                        {
                            "weight": 1.0,
                            "rules": [
                                {
                                    "entity_scope": "link",
                                    "rule_type": "choice",
                                    "count": 1,
                                }
                            ],
                        }
                    ],
                }
            },
        }

        # Should not raise any validation errors
        jsonschema.validate(valid_data, schema)

    def test_schema_validates_blueprints_and_groups(self, schema):
        """Test that the schema validates blueprints with groups and adjacency."""
        blueprint_scenario = """
blueprints:
  clos_2tier:
    groups:
      leaf:
        node_count: 4
        name_template: "leaf-{node_num}"
        attrs:
          role: "leaf"
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
        attrs:
          role: "spine"
    adjacency:
      - source: "/leaf"
        target: "/spine"
        pattern: "mesh"
        link_params:
          capacity: 40000.0
          cost: 1000

network:
  name: Blueprint Test Network
  groups:
    fabric:
      use_blueprint: "clos_2tier"
      parameters:
        leaf.node_count: 6

workflow:
  - step_type: BuildGraph
    name: build_graph
"""
        data = yaml.safe_load(blueprint_scenario)
        jsonschema.validate(data, schema)

    def test_schema_validates_adjacency_selector_objects(self, schema):
        """Adjacency with selector objects for source/target should validate."""
        valid = {
            "network": {
                "nodes": {},
                "links": [],
                "adjacency": [
                    {
                        "source": {
                            "path": "/A",
                            "match": {
                                "logic": "and",
                                "conditions": [
                                    {
                                        "attr": "role",
                                        "operator": "==",
                                        "value": "compute",
                                    }
                                ],
                            },
                        },
                        "target": {"path": "/B"},
                        "pattern": "mesh",
                    }
                ],
            }
        }
        jsonschema.validate(valid, schema)

    def test_schema_validates_node_link_overrides(self, schema):
        """Test that the schema validates node and link overrides."""
        override_scenario = """
network:
  name: Override Test Network
  groups:
    servers:
      node_count: 4
      name_template: "srv-{node_num}"
  node_overrides:
    - path: "srv-[12]"
      attrs:
        hw_type: "gpu_server"
        gpu_count: 8
      risk_groups: ["gpu_srg"]
  link_overrides:
    - source: "srv-1"
      target: "srv-2"
      link_params:
        capacity: 100000.0
        attrs:
          link_type: "high_bandwidth"

workflow:
  - step_type: BuildGraph
    name: build_graph
"""
        data = yaml.safe_load(override_scenario)
        jsonschema.validate(data, schema)

    def test_schema_validates_components(self, schema):
        """Test that the schema validates hardware components."""
        components_scenario = """
components:
  ToRSwitch48p:
    component_type: "switch"
    description: "48-port ToR switch"
    capex: 8000.0
    power_watts: 350.0
    ports: 48
    children:
      SFP28_25G:
        component_type: "optic"
        capex: 150.0
        count: 48

network:
  name: Components Test Network
  nodes:
    switch1:
      attrs:
        hw_component: "ToRSwitch48p"

workflow:
  - step_type: BuildGraph
    name: build_graph
"""
        data = yaml.safe_load(components_scenario)
        jsonschema.validate(data, schema)

    def test_schema_validates_complex_failure_policies(self, schema):
        """Test that the schema validates complex failure policies with conditions."""
        complex_failure_scenario = """
failure_policy_set:
  conditional_failure:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "node"
            rule_type: "choice"
            count: 2
            conditions:
              - attr: "attrs.role"
                operator: "=="
                value: "spine"
              - attr: "attrs.criticality"
                operator: ">="
                value: 5
            logic: "and"
  risk_group_failure:
    fail_risk_groups: true
    fail_risk_group_children: true
    modes:
      - weight: 1.0
        rules:
          - entity_scope: "risk_group"
            rule_type: "choice"
            count: 1

network:
  name: Complex Failure Test Network
  nodes:
    A:
      attrs:
        role: "spine"
        criticality: 8
    B:
      attrs:
        role: "leaf"
        criticality: 3

workflow:
  - step_type: BuildGraph
    name: build_graph
"""
        data = yaml.safe_load(complex_failure_scenario)
        jsonschema.validate(data, schema)

    def test_schema_validates_traffic_matrices(self, schema):
        """Test that the schema validates complex traffic matrices."""
        traffic_scenario = """
traffic_matrix_set:
  default:
    - source_path: "^spine.*"
      sink_path: "^leaf.*"
      demand: 1000.0
      mode: "combine"
      priority: 1
      attrs:
        traffic_type: "north_south"
  hpc_workload:
    - source_path: "compute.*"
      sink_path: "storage.*"
      demand: 5000.0
      mode: "pairwise"
      flow_policy_config:
        shortest_path: false
        flow_placement: "EQUAL_BALANCED"

network:
  name: Traffic Test Network
  nodes:
    spine1: {}
    leaf1: {}
    compute1: {}
    storage1: {}

workflow:
  - step_type: BuildGraph
    name: build_graph
  - step_type: CapacityEnvelopeAnalysis
    name: capacity_test
    source_path: "spine1"
    sink_path: "leaf1"
    iterations: 1
    baseline: false
    failure_policy: null
    mode: "combine"
"""
        data = yaml.safe_load(traffic_scenario)
        jsonschema.validate(data, schema)

    def test_schema_validates_variable_expansion(self, schema):
        """Test that the schema validates variable expansion in adjacency."""
        expansion_scenario = """
blueprints:
  datacenter:
    groups:
      rack:
        node_count: 4
        name_template: "rack{rack_id}-{node_num}"
      spine:
        node_count: 2
        name_template: "spine-{node_num}"
    adjacency:
      - source: "/rack"
        target: "/spine"
        pattern: "mesh"
        expand_vars:
          rack_id: [1, 2, 3]
        expansion_mode: "cartesian"
        link_params:
          capacity: 25000.0
          cost: 1

network:
  name: Variable Expansion Test
  groups:
    dc1:
      use_blueprint: "datacenter"

workflow:
  - step_type: BuildGraph
    name: build_graph
"""
        data = yaml.safe_load(expansion_scenario)
        jsonschema.validate(data, schema)

    def test_schema_consistency_with_netgraph_validation(self, schema):
        """Test that schema validation is consistent with NetGraph's validation."""
        # Test data that should be valid for both schema and NetGraph
        valid_yaml = """
network:
  name: Test Network
  nodes:
    A: {}
    B: {}
  links:
    - source: A
      target: B
      link_params:
        capacity: 100
        cost: 1
        risk_groups: ["test_rg"]

risk_groups:
  - name: test_rg

workflow:
  - step_type: BuildGraph
    name: build
"""
        data = yaml.safe_load(valid_yaml)

        # Should validate with both our schema and NetGraph
        jsonschema.validate(data, schema)
        scenario = Scenario.from_yaml(valid_yaml)
        assert scenario is not None
