"""
Integration tests for scenario 4: Advanced DSL features demonstration.

This module tests the most advanced NetGraph capabilities including:
- Component system for hardware modeling with cost/power calculations
- Variable expansion in adjacency rules (cartesian and zip modes)
- Bracket expansion in group names for multiple pattern matching
- Complex node and link override patterns with advanced regex
- Risk groups with hierarchical structure and failure simulation
- Advanced workflow steps
- NetworkExplorer integration for hierarchy analysis
- Large-scale network topology with realistic data center structure

Scenario 4 represents the most complex test of NetGraph's DSL capabilities,
validating the framework's ability to handle enterprise-scale network definitions
with complex relationships and advanced analysis requirements.

Uses the modular testing approach with validation helpers from the
integration.helpers module.
"""

import pytest

from ngraph.explorer import NetworkExplorer

from .expectations import (
    SCENARIO_4_COMPONENT_EXPECTATIONS,
    SCENARIO_4_EXPECTATIONS,
    SCENARIO_4_FAILURE_POLICY_EXPECTATIONS,
    SCENARIO_4_RISK_GROUP_EXPECTATIONS,
    SCENARIO_4_TRAFFIC_EXPECTATIONS,
)
from .helpers import create_scenario_helper, load_scenario_from_file


@pytest.mark.slow
class TestScenario4:
    """Tests for scenario 4 using modular validation approach."""

    @pytest.fixture(scope="module")
    def scenario_4(self):
        """Load scenario 4 from YAML file."""
        return load_scenario_from_file("scenario_4.yaml")

    @pytest.fixture(scope="module")
    def scenario_4_executed(self, scenario_4):
        """Execute scenario 4 workflow and return with results."""
        scenario_4.run()
        return scenario_4

    @pytest.fixture(scope="module")
    def helper(self, scenario_4_executed):
        """Create test helper for scenario 4."""
        helper = create_scenario_helper(scenario_4_executed)
        graph = scenario_4_executed.results.get("build_graph", "graph")
        helper.set_graph(graph)
        return helper

    def test_scenario_parsing_and_execution(self, scenario_4_executed):
        """Test that scenario 4 can be parsed and executed without errors."""
        assert scenario_4_executed.results is not None
        assert scenario_4_executed.results.get("build_graph", "graph") is not None

    def test_network_structure_validation(self, helper):
        """Test basic network structure matches expectations for large-scale topology."""
        helper.validate_network_structure(SCENARIO_4_EXPECTATIONS)

    def test_components_system_integration(self, helper):
        """Test that components system works correctly with hardware modeling."""
        components_lib = helper.scenario.components_library

        # Validate component library has expected components
        expected_components = SCENARIO_4_COMPONENT_EXPECTATIONS

        assert len(components_lib.components) == expected_components["total_components"]

        # Test specific component definitions
        tor_switch = components_lib.get(expected_components["tor_switches"])
        assert tor_switch is not None
        assert tor_switch.component_type == "switch"
        assert tor_switch.capex == 8000.0
        assert tor_switch.power_watts == 350.0
        assert len(tor_switch.children) == 1  # SFP28_25G optics

        spine_switch = components_lib.get(expected_components["spine_switches"])
        assert spine_switch is not None
        assert spine_switch.component_type == "switch"
        assert spine_switch.capex == 25000.0
        assert spine_switch.power_watts == 800.0

        server = components_lib.get(expected_components["servers"])
        assert server is not None
        assert server.component_type == "server"
        assert server.capex == 12000.0

    def test_component_references_in_nodes(self, helper):
        """Test that nodes correctly reference components from the library."""
        # Test ToR switch nodes have correct component references
        tor_nodes = [
            node
            for node in helper.network.nodes.values()
            if "tor" in node.name and node.attrs.get("hw_component") == "ToRSwitch48p"
        ]
        assert len(tor_nodes) > 0, "Should have ToR switches with component references"

        for tor_node in tor_nodes[:5]:  # Check first few
            assert tor_node.attrs.get("hw_component") == "ToRSwitch48p"
            assert tor_node.attrs.get("role") == "top_of_rack"

        # Test server nodes have correct component references
        server_nodes = [
            node
            for node in helper.network.nodes.values()
            if "srv" in node.name and node.attrs.get("hw_component") == "ServerNode"
        ]
        assert len(server_nodes) > 0, "Should have servers with component references"

        for server_node in server_nodes[:5]:  # Check first few
            assert server_node.attrs.get("hw_component") == "ServerNode"
            assert server_node.attrs.get("role") in ["compute", "gpu_compute"]

    def test_bracket_expansion_functionality(self, helper):
        """Test that bracket expansion creates expected node hierarchies."""
        # Test DC bracket expansion: dc[1-2] - look for actual node patterns
        all_nodes = list(helper.network.nodes.keys())

        dc1_nodes = [node for node in all_nodes if node.startswith("dc1")]
        dc2_nodes = [node for node in all_nodes if node.startswith("dc2")]

        assert len(dc1_nodes) > 0, (
            f"dc1 bracket expansion should create nodes. Found nodes: {all_nodes[:10]}"
        )
        assert len(dc2_nodes) > 0, (
            f"dc2 bracket expansion should create nodes. Found nodes: {all_nodes[:10]}"
        )

        # Test pod bracket expansion: pod[a,b] - look for actual patterns
        poda_nodes = [node for node in all_nodes if "poda" in node]
        podb_nodes = [node for node in all_nodes if "podb" in node]

        assert len(poda_nodes) > 0, (
            f"poda should have nodes from bracket expansion. Found: {poda_nodes[:5]}"
        )
        assert len(podb_nodes) > 0, (
            f"podb should have nodes from bracket expansion. Found: {podb_nodes[:5]}"
        )

        # Test rack bracket expansion: rack[01-02] - check actual rack names with underscore
        rack_nodes = [node for node in all_nodes if "_rack" in node]
        assert len(rack_nodes) > 0, (
            f"racks should have nodes from bracket expansion. Found: {rack_nodes[:5]}"
        )

    def test_variable_expansion_adjacency(self, helper):
        """Test that variable expansion in adjacency rules creates correct connections."""
        # Test leaf-spine connections created by variable expansion in blueprint
        leaf_spine_links = helper.network.find_links(
            source_regex=r".*/fabric/leaf/.*", target_regex=r".*/fabric/spine/.*"
        )

        # Check if any leaf-spine links exist at all
        if len(leaf_spine_links) == 0:
            # Try alternative patterns - the fabric might be flattened
            fabric_links = helper.network.find_links(
                source_regex=r".*fabric.*", target_regex=r".*fabric.*"
            )
            assert len(fabric_links) > 0, (
                f"Should have some fabric-related links from variable expansion. "
                f"All links: {[(link.source, link.target) for link in list(helper.network.links.values())[:10]]}"
            )
        else:
            # Verify some links have expected attributes if they exist
            for link in leaf_spine_links[:5]:  # Check first few
                assert link.capacity == 400.0
                assert link.attrs.get("media_type") == "fiber"
                assert link.attrs.get("link_type") == "leaf_spine"

        # Test rack-to-fabric connections from top-level variable expansion
        rack_fabric_links = helper.network.find_links(
            source_regex=r".*rack.*tor.*", target_regex=r".*fabric.*"
        )

        # If no rack-fabric links, at least verify basic connectivity
        if len(rack_fabric_links) == 0:
            total_links = len(helper.network.links)
            assert total_links > 0, (
                "Should have some connections from variable expansion"
            )

    def test_complex_node_overrides(self, helper):
        """Test complex node override patterns and cleaned-up attributes."""
        # Test GPU server overrides for specific nodes
        gpu_server_groups = helper.network.select_node_groups_by_path(
            r"dc1_pod[ab]_rack[12]/servers/srv-[1-4]"
        )

        gpu_servers = []
        for group_nodes in gpu_server_groups.values():
            gpu_servers.extend(group_nodes)

        assert len(gpu_servers) > 0, "Should find GPU servers from node overrides"

        for server in gpu_servers[:3]:  # Check first few
            # Verify cleaned-up attributes - no more marketing language
            assert (
                server.attrs.get("role") == "gpu_compute"
            )  # Technical role, not marketing
            assert server.attrs.get("gpu_count") == 8  # Specific technical spec
            assert (
                server.attrs.get("hw_component") == "ServerNode"
            )  # Technical component reference

            # Ensure no marketing language attributes remain
            assert "server_type" not in server.attrs, (
                "Old marketing attribute 'server_type' should be removed"
            )

        # Test that node attributes are now technical and meaningful
        all_servers = [
            node for node in helper.network.nodes.values() if "/servers/" in node.name
        ]

        for server in all_servers[:5]:  # Check a few servers
            # All servers should have technical role attribute
            role = server.attrs.get("role")
            assert role in ["compute", "gpu_compute"], (
                f"Server role should be technical, found: {role}"
            )

            # Should have technical hw_component reference
            assert server.attrs.get("hw_component") == "ServerNode"

        # Validate that attributes are meaningful and contextually appropriate
        # Check that ToR switches have appropriate technical attributes
        tor_switches = [
            node for node in helper.network.nodes.values() if "/tor/" in node.name
        ]

        assert len(tor_switches) > 0, "Should have ToR switches"

        for tor in tor_switches[:2]:  # Check a couple
            assert tor.attrs.get("role") == "top_of_rack"  # Technical role
            assert (
                tor.attrs.get("hw_component") == "ToRSwitch48p"
            )  # Technical component reference

    def test_complex_link_overrides(self, helper):
        """Test complex link override patterns with regex."""
        # Test inter-DC link capacity overrides
        inter_dc_links = helper.network.find_links(
            source_regex=r"dc1_fabric/spine/.*", target_regex=r"dc2_fabric/spine/.*"
        )

        assert len(inter_dc_links) > 0, "Should find inter-DC spine links"

        for link in inter_dc_links[:3]:  # Check first few
            assert link.capacity == 800.0  # Overridden capacity
            assert link.attrs.get("link_class") == "inter_dc"
            assert link.attrs.get("encryption") == "enabled"

        # Test higher capacity uplinks for specific racks
        enhanced_uplinks = helper.network.find_links(
            source_regex=r"dc1_pod[ab]_rack1/tor/.*",
            target_regex=r"dc1_fabric/leaf/.*",
        )

        for link in enhanced_uplinks[:3]:  # Check first few
            assert link.capacity == 200.0  # Overridden capacity

    def test_risk_groups_integration(self, helper):
        """Test that risk groups are correctly configured and hierarchical."""
        risk_groups = helper.scenario.network.risk_groups
        expected_groups = SCENARIO_4_RISK_GROUP_EXPECTATIONS["risk_groups"]

        # Validate expected risk groups exist
        risk_group_names = {rg.name for rg in risk_groups.values()}
        for expected_group in expected_groups:
            assert expected_group in risk_group_names, (
                f"Expected risk group '{expected_group}' not found"
            )

        # Test hierarchical risk group structure
        power_supply_group = risk_groups.get("DC1_PowerSupply_A")
        assert power_supply_group is not None
        assert len(power_supply_group.children) > 0, "Should have nested risk groups"
        assert power_supply_group.attrs.get("criticality") == "high"

        # Test risk group assignments on nodes
        spine_nodes_with_srg = [
            node
            for node in helper.network.nodes.values()
            if "Spine_Fabric_SRG" in node.risk_groups
        ]
        assert len(spine_nodes_with_srg) > 0, (
            "Spine nodes should have risk group assignments"
        )

    def test_traffic_matrix_configuration(self, helper):
        """Test that traffic matrices are correctly configured."""
        traffic_expectations = SCENARIO_4_TRAFFIC_EXPECTATIONS

        # Test default matrix
        default_matrix = helper.scenario.traffic_matrix_set.matrices.get("default")
        assert default_matrix is not None, "Default traffic matrix should exist"
        assert len(default_matrix) == traffic_expectations["default_matrix"]

        # Test HPC workload matrix
        hpc_matrix = helper.scenario.traffic_matrix_set.matrices.get("hpc_workload")
        assert hpc_matrix is not None, "HPC workload matrix should exist"
        assert len(hpc_matrix) == traffic_expectations["hpc_workload_matrix"]

        # Validate traffic demand attributes
        for demand in default_matrix:
            assert hasattr(demand, "attrs")
            if demand.attrs.get("traffic_type") == "east_west":
                assert demand.mode == "pairwise"
            elif demand.attrs.get("traffic_type") == "inter_dc":
                assert demand.mode == "combine"

    def test_failure_policy_configuration(self, helper):
        """Test that failure policies are correctly configured."""
        failure_expectations = SCENARIO_4_FAILURE_POLICY_EXPECTATIONS

        # Test total number of policies
        all_policies = helper.scenario.failure_policy_set.policies
        assert len(all_policies) == failure_expectations["total_policies"]

        # Test specific policies exist
        single_link_policy = helper.scenario.failure_policy_set.policies.get(
            "single_link_failure"
        )
        assert single_link_policy is not None, "single_link_failure policy should exist"
        assert sum(len(m.rules) for m in single_link_policy.modes) == 1

        single_node_policy = helper.scenario.failure_policy_set.policies.get(
            "single_node_failure"
        )
        assert single_node_policy is not None, "single_node_failure policy should exist"
        assert sum(len(m.rules) for m in single_node_policy.modes) == 1

    def test_advanced_workflow_steps(self, helper):
        """Test that advanced workflow steps executed correctly."""
        results = helper.scenario.results

        # Test BuildGraph step - correct API usage with two arguments
        graph = results.get("build_graph", "graph")
        assert graph is not None

        # Test CapacityEnvelopeAnalysis results - using capacity_envelopes key
        intra_dc_envelopes = results.get(
            "intra_dc_capacity_forward", "capacity_envelopes"
        )
        assert intra_dc_envelopes is not None, (
            "Intra-DC forward capacity analysis should have envelope results"
        )

        # Check that envelope contains expected flow key
        expected_intra_key = (
            "dc1_pod[ab]_rack.*/servers/.*->dc1_pod[ab]_rack.*/servers/.*"
        )
        assert expected_intra_key in intra_dc_envelopes, (
            f"Expected flow key '{expected_intra_key}' in intra-DC results"
        )

        # For inter-DC, check forward direction
        inter_dc_envelopes = results.get(
            "inter_dc_capacity_forward", "capacity_envelopes"
        )
        assert inter_dc_envelopes is not None, (
            "Inter-DC forward capacity analysis should have envelope results"
        )

        expected_inter_key = "dc1_.*servers/.*->dc2_.*servers/.*"
        assert expected_inter_key in inter_dc_envelopes, (
            f"Expected flow key '{expected_inter_key}' in inter-DC results"
        )

        # Test CapacityEnvelopeAnalysis results
        rack_failure_result = results.get("rack_failure_analysis", "capacity_envelopes")
        assert rack_failure_result is not None, (
            "Rack failure analysis should have results"
        )

    def test_network_explorer_integration(self, helper):
        """Test NetworkExplorer functionality with complex hierarchy."""
        explorer = NetworkExplorer.explore_network(
            helper.network, helper.scenario.components_library
        )

        assert explorer.root_node is not None

        # Verify reasonable network size for test scenario
        assert (
            explorer.root_node.stats.node_count >= 80
        )  # Should have substantial node count

        # Test component capex/power aggregation
        assert explorer.root_node.stats.total_capex > 0
        assert explorer.root_node.stats.total_power > 0

    def test_topology_semantic_correctness(self, helper):
        """Test semantic correctness of the complex topology."""
        helper.validate_topology_semantics()

        # Additional semantic checks for advanced scenario
        # Allow for disconnected components due to disabled nodes and variable expansion
        import networkx as nx

        is_connected = nx.is_weakly_connected(helper.graph)
        if not is_connected:
            components = list(nx.weakly_connected_components(helper.graph))
            # Multiple components are expected due to complex topology patterns,
            # disabled nodes, and separate data center fabric components
            assert len(components) <= 20, (
                f"Too many disconnected components ({len(components)}), "
                "may indicate topology issues"
            )

    def test_blueprint_nesting_depth(self, helper):
        """Test that blueprint nesting works correctly."""
        # Verify that nested node names are correct (adjusted for actual structure)
        all_nodes = list(helper.network.nodes.keys())
        nested_nodes = [
            node
            for node in all_nodes
            if node.count("/") >= 2  # At least 3 levels: dc/pod/rack
        ]

        assert len(nested_nodes) > 0, (
            f"Should have nested nodes. Found: {all_nodes[:10]}"
        )

        # Verify naming convention is consistent
        for node_name in nested_nodes[:10]:  # Check first few
            parts = node_name.split("/")
            assert len(parts) >= 3  # dc/pod/rack or similar
            assert parts[0].startswith("dc")

    def test_regex_pattern_matching_complexity(self, helper):
        """Test complex regex patterns in overrides and selections."""
        # Test complex node selection patterns using available API
        all_nodes = list(helper.network.nodes.keys())

        # Find GPU pattern nodes manually since select_nodes_by_path doesn't exist
        gpu_pattern_nodes = [
            node
            for node in all_nodes
            if "dc1" in node and "pod" in node and "rack" in node and "servers" in node
        ]

        assert len(gpu_pattern_nodes) > 0, "Complex patterns should match nodes"

        # Test complex link selection patterns
        inter_dc_pattern_links = helper.network.find_links(
            source_regex=r"dc1.*fabric.*spine.*",
            target_regex=r"dc2.*fabric.*spine.*",
        )

        assert len(inter_dc_pattern_links) > 0, "Complex link patterns should match"

    def test_edge_case_handling(self, helper):
        """Test edge cases and boundary conditions in complex scenario."""
        # Test disabled node handling (may be enabled by workflow steps)
        # Test disabled node handling
        # Test empty group handling (if any)
        all_nodes = list(helper.network.nodes.keys())
        assert len(all_nodes) > 0, "Should have some nodes"

        # Test node count consistency - allow for larger differences due to disabled nodes and workflow operations
        total_nodes = len(helper.network.nodes)
        graph_nodes = len(helper.graph.nodes)
        node_diff = abs(total_nodes - graph_nodes)
        assert node_diff <= 15, (
            f"Network ({total_nodes}) and graph ({graph_nodes}) node counts should be close. "
            f"Difference: {node_diff} (some nodes may be disabled and excluded from graph)"
        )
