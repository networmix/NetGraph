"""
Error case tests for scenario processing and validation.

Tests malformed YAML scenarios, invalid configurations, edge cases, and error
handling to ensure error reporting and graceful degradation.
"""

import pytest
from yaml.parser import ParserError

from ngraph.scenario import Scenario

from .helpers import ScenarioDataBuilder


@pytest.mark.slow
class TestMalformedYAML:
    """Tests for malformed YAML and parsing errors."""

    def test_invalid_yaml_syntax(self):
        """Test that invalid YAML syntax raises appropriate error."""
        # Use raw YAML for syntax error testing (can't build with builder)
        invalid_yaml = """
        network:
          nodes:
            NodeA: {
        """  # Missing closing brace

        with pytest.raises(ParserError):
            Scenario.from_yaml(invalid_yaml)

    def test_missing_required_fields(self):
        """Test scenarios with missing required fields."""
        # Empty scenario using builder
        builder = ScenarioDataBuilder()
        scenario = builder.build_scenario()

        # Empty scenario should be handled gracefully
        assert scenario.network is not None

    def test_invalid_node_definitions(self):
        """Test invalid node definitions."""
        # Use raw YAML for testing invalid fields that builder can't create
        invalid_node_yaml = """
        network:
          nodes:
            NodeA:
              invalid_field: "should_not_exist"
              disabled: "not_a_boolean"  # Should be boolean
        """

        # NetGraph rejects invalid keys during parsing
        with pytest.raises(ValueError, match="Unrecognized key"):
            _scenario = Scenario.from_yaml(invalid_node_yaml)

    def test_invalid_link_definitions(self):
        """Test invalid link definitions."""
        # Use raw YAML for invalid data that builder validation would prevent
        invalid_link_yaml = """
        network:
          nodes:
            NodeA: {}
            NodeB: {}
          links:
            - source: NodeA
              target: NodeB
              link_params:
                capacity: "not_a_number"  # Should be numeric
                cost: -5  # Negative cost might be invalid
        workflow:
          - step_type: BuildGraph
            name: build_graph
        """

        # NetGraph may handle this gracefully or raise errors during execution
        try:
            scenario = Scenario.from_yaml(invalid_link_yaml)
            scenario.run()
        except (ValueError, TypeError):
            # Expected if strict validation is enforced during execution
            pass

    def test_nonexistent_link_endpoints(self):
        """Test links referencing nonexistent nodes."""
        # Use raw YAML since builder would validate node existence
        invalid_endpoints_yaml = """
        network:
          nodes:
            NodeA: {}
          links:
            - source: NodeA
              target: NonexistentNode  # Node doesn't exist
              link_params:
                capacity: 10
                cost: 1
        workflow:
          - step_type: BuildGraph
            name: build_graph
        """

        with pytest.raises((ValueError, KeyError)):
            scenario = Scenario.from_yaml(invalid_endpoints_yaml)
            scenario.run()


@pytest.mark.slow
class TestBlueprintErrors:
    """Tests for blueprint-related errors."""

    def test_nonexistent_blueprint_reference(self):
        """Test referencing a blueprint that doesn't exist."""
        # Use raw YAML for invalid blueprint reference
        invalid_blueprint_ref = """
        network:
          name: "test_network"
          groups:
            test_group:
              use_blueprint: nonexistent_blueprint  # Doesn't exist
        """

        with pytest.raises((ValueError, KeyError)):
            scenario = Scenario.from_yaml(invalid_blueprint_ref)
            scenario.run()

    def test_circular_blueprint_references(self):
        """Test circular references between blueprints."""
        builder = ScenarioDataBuilder()
        builder.with_blueprint(
            "blueprint_a", {"groups": {"group_a": {"use_blueprint": "blueprint_b"}}}
        )
        builder.with_blueprint(
            "blueprint_b",
            {
                "groups": {"group_b": {"use_blueprint": "blueprint_a"}}  # Circular!
            },
        )

        # Add network using one of the circular blueprints
        builder.data["network"] = {
            "name": "test_network",
            "groups": {"test_group": {"use_blueprint": "blueprint_a"}},
        }
        builder.with_workflow_step("BuildGraph", "build_graph")

        with pytest.raises((ValueError, RecursionError)):
            scenario = builder.build_scenario()
            scenario.run()

    def test_invalid_blueprint_parameters(self):
        """Test invalid blueprint parameter overrides."""
        builder = ScenarioDataBuilder()
        builder.with_blueprint(
            "simple_blueprint",
            {
                "groups": {
                    "nodes": {"node_count": 2, "name_template": "node-{node_num}"}
                }
            },
        )

        # Use raw YAML for invalid parameter override that builder might not allow
        invalid_params = """
        blueprints:
          simple_blueprint:
            groups:
              nodes:
                node_count: 2
                name_template: "node-{node_num}"

        network:
          name: "test_network"
          groups:
            test_group:
              use_blueprint: simple_blueprint
              parameters:
                nonexistent_group.param: "invalid"  # Group doesn't exist
        """

        # Depending on implementation, this might be ignored or raise error
        try:
            scenario = Scenario.from_yaml(invalid_params)
            scenario.run()
        except (ValueError, KeyError):
            # Expected if strict validation is enforced
            pass

    def test_malformed_adjacency_patterns(self):
        """Test malformed adjacency pattern definitions."""
        # Use raw YAML for invalid pattern value that builder might validate
        malformed_adjacency = """
        blueprints:
          bad_blueprint:
            groups:
              group1:
                node_count: 2
                name_template: "node-{node_num}"
              group2:
                node_count: 2
                name_template: "node-{node_num}"
            adjacency:
              - source: group1
                target: group2
                pattern: "invalid_pattern"  # Should be 'mesh' or 'one_to_one'
                link_params:
                  capacity: 10

        network:
          groups:
            test_group:
              use_blueprint: bad_blueprint
        workflow:
          - step_type: BuildGraph
            name: build_graph
        """

        with pytest.raises((ValueError, KeyError)):
            scenario = Scenario.from_yaml(malformed_adjacency)
            scenario.run()


@pytest.mark.slow
class TestFailurePolicyErrors:
    """Tests for failure policy validation errors."""

    def test_invalid_failure_rule_types(self):
        """Test invalid failure rule configurations."""
        builder = ScenarioDataBuilder()
        builder.with_failure_policy(
            "invalid_rule",
            {
                "rules": [
                    {
                        "entity_scope": "invalid_scope",  # Should be 'node' or 'link'
                        "rule_type": "choice",
                        "count": 1,
                    }
                ]
            },
        )

        # NetGraph may accept this and handle it during execution
        try:
            builder.build_scenario()
            # May succeed if validation is permissive
        except (ValueError, KeyError):
            # Expected if strict validation is enforced
            pass

    def test_invalid_failure_rule_counts(self):
        """Test invalid rule count configurations."""
        builder = ScenarioDataBuilder()
        builder.with_failure_policy(
            "negative_count",
            {
                "rules": [
                    {
                        "entity_scope": "link",
                        "rule_type": "choice",
                        "count": -1,  # Negative count should be invalid
                    }
                ]
            },
        )

        # NetGraph may accept negative counts or handle them gracefully
        try:
            builder.build_scenario()
            # May succeed if validation is permissive
        except (ValueError, TypeError):
            # Expected if strict validation is enforced
            pass

    def test_malformed_failure_conditions(self):
        """Test malformed failure condition syntax."""
        # Use raw YAML for malformed condition that builder can't create
        malformed_conditions = """
        failure_policy_set:
          default:
            rules:
              - entity_scope: "node"
                rule_type: "conditional"
                conditions:
                  - "invalid syntax here"  # Malformed condition (string instead of dict)
        """

        # NetGraph should reject malformed condition format
        with pytest.raises(TypeError, match="string indices must be integers"):
            _scenario = Scenario.from_yaml(malformed_conditions)


@pytest.mark.slow
class TestTrafficDemandErrors:
    """Tests for traffic demand validation errors."""

    def test_nonexistent_traffic_endpoints(self):
        """Test traffic demands with nonexistent endpoints."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        builder.with_traffic_demand("NodeA", "NonexistentNode", 50.0)
        builder.with_workflow_step("BuildGraph", "build_graph")

        # This might be caught during scenario building or execution
        scenario = builder.build_scenario()
        scenario.run()  # May or may not raise error depending on implementation

    def test_negative_traffic_demands(self):
        """Test negative traffic demand values."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        builder.with_traffic_demand("NodeA", "NodeB", -10.0)  # Negative demand
        builder.with_workflow_step("BuildGraph", "build_graph")

        # NetGraph may accept negative demands
        try:
            scenario = builder.build_scenario()
            scenario.run()
            # May succeed if NetGraph allows negative demands
        except (ValueError, AssertionError):
            # Expected if strict validation is enforced
            pass

    def test_invalid_demand_types(self):
        """Test non-numeric demand values."""
        # Use raw YAML for invalid type that builder would prevent
        invalid_type_yaml = """
        network:
          nodes:
            NodeA: {}
            NodeB: {}
        traffic_matrix_set:
          default:
            - source_path: NodeA
              sink_path: NodeB
              demand: "not_a_number"  # Should be numeric
        workflow:
          - step_type: BuildGraph
            name: build_graph
        """

        # NetGraph may handle type conversion or raise errors
        try:
            scenario = Scenario.from_yaml(invalid_type_yaml)
            scenario.run()
        except (ValueError, TypeError):
            # Expected if strict type validation is enforced
            pass


@pytest.mark.slow
class TestWorkflowErrors:
    """Tests for workflow step errors."""

    def test_nonexistent_workflow_step_type(self):
        """Test referencing nonexistent workflow step types."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA"])
        builder.with_workflow_step("NonexistentStepType", "invalid_step")

        with pytest.raises((ValueError, KeyError)):
            scenario = builder.build_scenario()
            scenario.run()

    def test_missing_required_step_parameters(self):
        """Test workflow steps missing required parameters."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        # CapacityProbe without required source_path/sink_path
        builder.data["workflow"] = [
            {
                "step_type": "CapacityProbe",
                "name": "incomplete_probe",
                # Missing required source_path and sink_path parameters
            }
        ]

        scenario = builder.build_scenario()
        # NetGraph may handle missing parameters gracefully or with defaults
        try:
            scenario.run()
            # May succeed if default parameters are used
        except (ValueError, TypeError, AttributeError):
            # Expected if strict parameter validation is enforced
            pass

    def test_invalid_step_parameter_types(self):
        """Test workflow steps with invalid parameter types."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        builder.data["workflow"] = [
            {
                "step_type": "CapacityProbe",
                "name": "invalid_probe",
                "source_path": "NodeA",
                "sink_path": "NodeB",
                "mode": "invalid_mode",  # Should be 'combine' or 'pairwise'
            }
        ]

        scenario = builder.build_scenario()
        with pytest.raises((ValueError, KeyError)):
            scenario.run()


@pytest.mark.slow
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_network(self):
        """Test scenario with no nodes or links."""
        builder = ScenarioDataBuilder()
        builder.data["network"] = {"name": "empty_network", "nodes": {}, "links": []}
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        # Should succeed but produce empty graph
        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_single_node_network(self):
        """Test scenario with only one node."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["LonelyNode"])
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 1
        assert len(graph.edges) == 0

    def test_isolated_nodes(self):
        """Test network with isolated nodes (no connections)."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB", "NodeC"])
        # No links - all nodes isolated
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 0

    def test_self_loop_links(self):
        """Test links from a node to itself."""
        # Use raw YAML since builder would prevent self-loops
        self_loop_yaml = """
        network:
          nodes:
            NodeA: {}
          links:
            - source: NodeA
              target: NodeA  # Self-loop
              link_params:
                capacity: 10
                cost: 1
        workflow:
          - step_type: BuildGraph
            name: build_graph
        """

        # NetGraph correctly rejects self-loops as invalid
        with pytest.raises(
            ValueError, match="Link cannot have the same source and target"
        ):
            scenario = Scenario.from_yaml(self_loop_yaml)
            scenario.run()

    def test_duplicate_links(self):
        """Test multiple links between the same pair of nodes."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        # Add duplicate links with different parameters
        builder.with_simple_links([("NodeA", "NodeB", 10.0)])
        builder.data["network"]["links"].append(
            {
                "source": "NodeA",
                "target": "NodeB",
                "link_params": {"capacity": 20.0, "cost": 2},
            }
        )
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        # Should handle parallel links correctly
        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 2
        # Should have multiple edges between the same nodes

    def test_zero_capacity_links(self):
        """Test links with zero capacity."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        builder.data["network"]["links"] = [
            {
                "source": "NodeA",
                "target": "NodeB",
                "link_params": {"capacity": 0, "cost": 1},  # Zero capacity
            }
        ]
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        # Should handle zero capacity links appropriately
        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 2

    def test_very_large_network_parameters(self):
        """Test handling of very large numeric parameters."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA", "NodeB"])
        builder.data["network"]["links"] = [
            {
                "source": "NodeA",
                "target": "NodeB",
                "link_params": {
                    "capacity": 999999999999,  # Very large capacity
                    "cost": 999999999999,  # Very large cost
                },
            }
        ]
        builder.with_workflow_step("BuildGraph", "build_graph")

        scenario = builder.build_scenario()
        scenario.run()

        # Should handle large numbers without overflow issues
        graph = scenario.results.get("build_graph", "graph")
        assert graph is not None, "BuildGraph should produce a graph"
        assert len(graph.nodes) == 2

    def test_special_characters_in_node_names(self):
        """Test node names with special characters."""
        builder = ScenarioDataBuilder()
        special_names = ["node-with-dashes", "node.with.dots", "node_with_underscores"]

        try:
            builder.with_simple_nodes(special_names)
            builder.with_workflow_step("BuildGraph", "build_graph")
            scenario = builder.build_scenario()
            scenario.run()
        except (ValueError, KeyError):
            # Some special characters might not be allowed
            pass


@pytest.mark.slow
class TestResourceLimits:
    """Tests for resource limitations and performance edge cases."""

    def test_blueprint_expansion_depth_limit(self):
        """Test deeply nested blueprint expansions."""
        builder = ScenarioDataBuilder()

        # Create deeply nested blueprints (might hit recursion limits)
        for i in range(10):
            if i == 0:
                builder.with_blueprint(
                    f"level_{i}",
                    {
                        "groups": {
                            "nodes": {
                                "node_count": 1,
                                "name_template": f"level_{i}_node_{{node_num}}",
                            }
                        }
                    },
                )
            else:
                builder.with_blueprint(
                    f"level_{i}",
                    {"groups": {"nested": {"use_blueprint": f"level_{i - 1}"}}},
                )

        # Use the most deeply nested blueprint
        builder.data["network"] = {
            "groups": {"deep_group": {"use_blueprint": "level_9"}}
        }
        builder.with_workflow_step("BuildGraph", "build_graph")

        try:
            scenario = builder.build_scenario()
            scenario.run()
        except (RecursionError, ValueError):
            # Expected if there are depth limits
            pass

    def test_large_mesh_expansion(self):
        """Test mesh pattern with large node counts (performance test)."""
        builder = ScenarioDataBuilder()

        # Create large mesh blueprint using template system
        large_mesh_blueprint = {
            "groups": {
                "side_a": {"node_count": 50, "name_template": "a-{node_num}"},
                "side_b": {"node_count": 50, "name_template": "b-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "/side_a",
                    "target": "/side_b",
                    "pattern": "mesh",  # Creates 50 * 50 = 2500 links
                    "link_params": {"capacity": 1, "cost": 1},
                }
            ],
        }

        builder.with_blueprint("large_mesh", large_mesh_blueprint)
        builder.data["network"] = {
            "groups": {"mesh_group": {"use_blueprint": "large_mesh"}}
        }
        builder.with_workflow_step("BuildGraph", "build_graph")

        # This is a performance test - might be slow but should complete
        scenario = builder.build_scenario()
        scenario.run()

        graph = scenario.results.get("build_graph", "graph")
        assert len(graph.nodes) == 100  # 50 + 50
        # Should have 2500 * 2 = 5000 directed edges (mesh creates bidirectional links)
