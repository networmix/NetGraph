"""
Integration tests for scenario 2: Hierarchical DSL with blueprints and multi-node expansions.

Covers:
- Network blueprints with nested hierarchies
- Blueprint parameter overrides
- Mesh pattern connectivity between blueprint groups
- Sub-topology composition and reuse
- Hierarchical DSL path resolution

Validation helpers come from integration.helpers.
"""

import pytest

from .expectations import SCENARIO_2_EXPECTATIONS
from .helpers import create_scenario_helper, load_scenario_from_file


@pytest.mark.slow
class TestScenario2:
    """Tests for scenario 2."""

    @pytest.fixture
    def scenario_2(self):
        """Load scenario 2 from YAML file."""
        return load_scenario_from_file("scenario_2.yaml")

    @pytest.fixture
    def scenario_2_executed(self, scenario_2):
        """Execute scenario 2 workflow and return with results."""
        scenario_2.run()
        return scenario_2

    @pytest.fixture
    def helper(self, scenario_2_executed):
        """Create test helper for scenario 2."""
        # create_scenario_helper handles graph conversion using nx.node_link_graph
        helper = create_scenario_helper(scenario_2_executed)
        return helper

    def test_scenario_parsing_and_execution(self, scenario_2_executed):
        """Test that scenario 2 can be parsed and executed without errors."""
        assert scenario_2_executed.results is not None
        exported = scenario_2_executed.results.to_dict()
        assert exported["steps"]["build_graph"]["data"].get("graph") is not None

    def test_network_structure_validation(self, helper):
        """Test basic network structure matches expectations after blueprint expansion."""
        helper.validate_network_structure(SCENARIO_2_EXPECTATIONS)

    def test_blueprint_expansion_validation(self, helper):
        """Test that blueprint expansions created expected node structures."""
        helper.validate_blueprint_expansions(SCENARIO_2_EXPECTATIONS)

        # Additional specific checks for this scenario's blueprints
        # Check that SEA uses city_cloud blueprint with overridden spine count
        sea_spine_nodes = [
            node
            for node in helper.network.nodes
            if node.startswith("SEA/clos_instance/spine/")
        ]
        assert len(sea_spine_nodes) == 6, (
            f"Expected 6 spine nodes in SEA/clos_instance, found {len(sea_spine_nodes)}"
        )

        # Check for overridden spine naming
        myspine_nodes = [node for node in sea_spine_nodes if "myspine-" in node]
        assert len(myspine_nodes) == 6, (
            f"Expected 6 'myspine-' nodes, found {len(myspine_nodes)}"
        )

    def test_hierarchical_node_naming(self, helper):
        """Test that expanded nodes get hierarchical group/subgroup/template names."""
        # Test specific expanded node names from the blueprint hierarchy
        expected_nodes = {
            "SEA/clos_instance/spine/myspine-6",  # Overridden spine with custom naming
            "SFO/single/single-1",  # Single node blueprint
            "SEA/edge_nodes/edge-1",  # Edge nodes from city_cloud blueprint
            "SEA/clos_instance/leaf/leaf-1",  # Leaf nodes from nested clos_2tier
        }

        for node_name in expected_nodes:
            assert node_name in helper.network.nodes, (
                f"Expected hierarchical node '{node_name}' not found"
            )

    def test_mesh_link_pattern(self, helper):
        """Test that mesh patterns create full connectivity between groups."""
        # In the clos_2tier blueprint, leaf should mesh with spine
        # With 4 leaf and 6 spine nodes, we expect 4 * 6 = 24 connections
        leaf_to_spine_links = helper.network.find_links(
            source_regex=r"SEA/clos_instance/leaf/.*",
            target_regex=r"SEA/clos_instance/spine/.*",
        )
        assert len(leaf_to_spine_links) == 24, (
            f"Expected 24 leaf-to-spine mesh links, found {len(leaf_to_spine_links)}"
        )

    def test_blueprint_parameters(self, helper):
        """Test that params override the SEA spine count (6) and name template."""
        # The city_cloud blueprint overrides spine.node_count to 6 and spine.name_template
        spine_nodes = [
            node
            for node in helper.network.nodes
            if node.startswith("SEA/clos_instance/spine/")
        ]

        # Should have 6 spine nodes (overridden from default 4)
        assert len(spine_nodes) == 6, (
            f"Parameter override for spine.node_count failed: expected 6, found {len(spine_nodes)}"
        )

        # Should use overridden name template "myspine-{n}"
        for node_name in spine_nodes:
            assert "myspine-" in node_name, (
                f"Parameter override for spine.name_template failed: {node_name} "
                "should contain 'myspine-'"
            )

    def test_standalone_nodes_and_links(self, helper):
        """Test that standalone nodes and direct links work alongside blueprints."""
        # Check standalone nodes exist
        standalone_nodes = {"DEN", "DFW", "JFK", "DCA"}
        for node_name in standalone_nodes:
            assert node_name in helper.network.nodes, (
                f"Standalone node '{node_name}' not found"
            )

        # Check some direct links between standalone nodes
        den_dfw_links = helper.network.find_links(
            source_regex="^DEN$", target_regex="^DFW$"
        )
        assert len(den_dfw_links) == 2, (
            f"Expected 2 DEN-DFW links, found {len(den_dfw_links)}"
        )

    def test_blueprint_to_standalone_connectivity(self, helper):
        """Test that blueprint groups connect to standalone nodes."""
        # SEA/edge_nodes should connect to DEN and DFW via mesh pattern
        edge_to_den_links = helper.network.find_links(
            source_regex=r"SEA/edge_nodes/.*", target_regex="^DEN$"
        )
        # 4 edge nodes * 1 DEN = 4 links
        assert len(edge_to_den_links) == 4, (
            f"Expected 4 edge-to-DEN links, found {len(edge_to_den_links)}"
        )

        edge_to_dfw_links = helper.network.find_links(
            source_regex=r"SEA/edge_nodes/.*", target_regex="^DFW$"
        )
        assert len(edge_to_dfw_links) == 4, (
            f"Expected 4 edge-to-DFW links, found {len(edge_to_dfw_links)}"
        )

    def test_single_node_blueprint(self, helper):
        """Test that single_node blueprint creates exactly one node."""
        sfo_nodes = [node for node in helper.network.nodes if node.startswith("SFO/")]
        assert len(sfo_nodes) == 1, (
            f"Single node blueprint should create 1 node, found {len(sfo_nodes)}"
        )
        assert sfo_nodes[0] == "SFO/single/single-1", (
            f"Single node should be named 'SFO/single/single-1', found '{sfo_nodes[0]}'"
        )

    def test_link_capacities_and_costs(self, helper):
        """Test capacity and cost on blueprint mesh links and on direct links."""
        # Test blueprint-generated links
        leaf_spine_links = helper.network.find_links(
            source_regex=r"SEA/clos_instance/leaf/.*",
            target_regex=r"SEA/clos_instance/spine/.*",
        )

        # All blueprint mesh links should have capacity=100, cost=1000
        for link in leaf_spine_links[:3]:  # Check first few
            assert link.capacity == 100, (
                f"Blueprint leaf-spine link expected capacity 100, found {link.capacity}"
            )
            assert link.cost == 1000, (
                f"Blueprint leaf-spine link expected cost 1000, found {link.cost}"
            )

        # Test direct link definitions
        jfk_dca_links = helper.network.find_links(
            source_regex="^JFK$", target_regex="^DCA$"
        )
        assert len(jfk_dca_links) > 0, "JFK-DCA link should exist"
        jfk_dca_link = jfk_dca_links[0]
        assert jfk_dca_link.capacity == 100, (
            f"JFK-DCA link expected capacity 100, found {jfk_dca_link.capacity}"
        )
        assert jfk_dca_link.cost == 1714, (
            f"JFK-DCA link expected cost 1714, found {jfk_dca_link.cost}"
        )

    def test_traffic_demands_configuration(self, helper):
        """Test that the default demand set holds the four 50-unit demands."""
        helper.validate_traffic_demands(expected_count=4)

        # Same traffic demands as scenario 1
        default_demands = helper.scenario.demand_set.get_set("default")
        demands_dict = {
            (demand.source, demand.target): demand.volume for demand in default_demands
        }

        expected_demands = {
            ("SEA", "JFK"): 50,
            ("SFO", "DCA"): 50,
            ("SEA", "DCA"): 50,
            ("SFO", "JFK"): 50,
        }

        for (source, sink), expected_demand in expected_demands.items():
            assert (source, sink) in demands_dict, (
                f"Expected traffic demand from {source} to {sink} not found"
            )
            actual_demand = demands_dict[(source, sink)]
            assert actual_demand == expected_demand, (
                f"Traffic demand {source}->{sink} expected {expected_demand}, "
                f"found {actual_demand}"
            )

    def test_failure_policy_configuration(self, helper):
        """Test failure policy configuration."""
        helper.validate_failure_policy(expected_rules=1, expected_scopes=["link"])

    def test_topology_semantic_correctness(self, helper):
        """Test that all edges have non-negative capacity and cost."""
        helper.validate_topology_semantics()

    def test_blueprint_nesting_structure(self, helper):
        """Test that a blueprint nested in another expands to leaf-1..leaf-4."""
        # city_cloud blueprint contains clos_instance which uses clos_2tier blueprint
        # Verify the full nesting path exists
        nested_leaf_nodes = [
            node for node in helper.network.nodes if "SEA/clos_instance/leaf/" in node
        ]
        assert len(nested_leaf_nodes) == 4, (
            f"Nested blueprint should create 4 leaf nodes, found {len(nested_leaf_nodes)}"
        )

        # Verify these are from the clos_2tier blueprint template
        for node in nested_leaf_nodes:
            assert node.endswith(("leaf-1", "leaf-2", "leaf-3", "leaf-4")), (
                f"Nested leaf node {node} doesn't match expected template"
            )

    def test_node_coordinate_attributes(self, helper):
        """Test that group coords reach every node a blueprint expands into."""
        expected_coords = {
            "SEA/": [47.6062, -122.3321],
            "SFO/": [37.7749, -122.4194],
            "DEN": [39.7392, -104.9903],
            "DFW": [32.8998, -97.0403],
            "JFK": [40.641766, -73.780968],
            "DCA": [38.907192, -77.036871],
        }
        nodes = helper.network.nodes
        for prefix, coords in expected_coords.items():
            matched = [name for name in nodes if name.startswith(prefix)]
            assert matched, f"No nodes under {prefix}"
            for name in matched:
                assert nodes[name].attrs.get("coords") == coords, (
                    f"{name} has coords {nodes[name].attrs.get('coords')}, "
                    f"expected {coords}"
                )
        assert len([n for n in nodes if n.startswith("SEA/")]) == 14
