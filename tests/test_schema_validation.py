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
        schema_path = Path(__file__).parent.parent / "schemas" / "scenario.json"
        with open(schema_path) as f:
            return json.load(f)

    def test_schema_validates_simple_scenario(self, schema):
        """Test that the schema validates the simple.yaml scenario."""
        simple_yaml = Path(__file__).parent.parent / "scenarios" / "simple.yaml"
        with open(simple_yaml) as f:
            data = yaml.safe_load(f)

        # Should not raise any validation errors
        jsonschema.validate(data, schema)

    def test_schema_validates_test_scenarios(self, schema):
        """Test that the schema validates test scenario files."""
        test_scenarios_dir = Path(__file__).parent / "scenarios"

        for yaml_file in test_scenarios_dir.glob("*.yaml"):
            with open(yaml_file) as f:
                data = yaml.safe_load(f)

            # Should not raise any validation errors
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
                    "rules": [
                        {"entity_scope": "link", "rule_type": "choice", "count": 1}
                    ],
                }
            },
        }

        # Should not raise any validation errors
        jsonschema.validate(valid_data, schema)

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
