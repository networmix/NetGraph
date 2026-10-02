"""
Integration tests for scenario 4: Advanced DSL features demonstration.

Covers:
- Component system for hardware modeling with cost/power calculations
- Variable expansion in adjacency rules (cartesian and zip modes)
- Bracket expansion in group names for multiple pattern matching
- Complex node and link override patterns with advanced regex
- Risk groups with hierarchical structure and failure simulation
- Advanced workflow steps
- NetworkExplorer integration for hierarchy analysis
- Large-scale network topology with realistic data center structure

Validation helpers come from integration.helpers.
"""

import re

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
    """Tests for scenario 4."""

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
        # create_scenario_helper handles graph conversion using nx.node_link_graph
        helper = create_scenario_helper(scenario_4_executed)
        return helper

    def test_scenario_parsing_and_execution(self, scenario_4_executed):
        """Test that scenario 4 can be parsed and executed without errors."""
        assert scenario_4_executed.results is not None
        exported = scenario_4_executed.results.to_dict()
        assert exported["steps"]["build_graph"]["data"].get("graph") is not None

    def test_network_structure_validation(self, helper):
        """Test basic network structure matches expectations for large-scale topology."""
        helper.validate_network_structure(SCENARIO_4_EXPECTATIONS)

    def test_components_system_integration(self, helper):
        """Test component count and the type/capex/power of each component."""
        components_lib = helper.scenario.components_library

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
        """Test that ToR and server nodes reference their hardware components."""
        # ToR switch nodes reference ToRSwitch48p
        tor_nodes = [
            node
            for node in helper.network.nodes.values()
            if "tor" in node.name
            and ((node.attrs.get("hardware") or {}).get("component") == "ToRSwitch48p")
        ]
        assert len(tor_nodes) > 0, "Should have ToR switches with component references"

        for tor_node in tor_nodes[:5]:  # Check first few
            assert (tor_node.attrs.get("hardware") or {}).get(
                "component"
            ) == "ToRSwitch48p"
            assert tor_node.attrs.get("role") == "top_of_rack"

        # Server nodes reference ServerNode
        server_nodes = [
            node
            for node in helper.network.nodes.values()
            if "srv" in node.name
            and ((node.attrs.get("hardware") or {}).get("component") == "ServerNode")
        ]
        assert len(server_nodes) > 0, "Should have servers with component references"

        for server_node in server_nodes[:5]:  # Check first few
            assert (server_node.attrs.get("hardware") or {}).get(
                "component"
            ) == "ServerNode"
            assert server_node.attrs.get("role") in ["compute", "gpu_compute"]

    def test_bracket_expansion_functionality(self, helper):
        """Test that bracket expansion creates expected node hierarchies."""
        # DC bracket expansion: dc[1-2]
        all_nodes = list(helper.network.nodes.keys())

        dc1_nodes = [node for node in all_nodes if node.startswith("dc1")]
        dc2_nodes = [node for node in all_nodes if node.startswith("dc2")]

        assert len(dc1_nodes) > 0, (
            f"dc1 bracket expansion should create nodes. Found nodes: {all_nodes[:10]}"
        )
        assert len(dc2_nodes) > 0, (
            f"dc2 bracket expansion should create nodes. Found nodes: {all_nodes[:10]}"
        )

        # Pod bracket expansion: pod[a,b]
        poda_nodes = [node for node in all_nodes if "poda" in node]
        podb_nodes = [node for node in all_nodes if "podb" in node]

        assert len(poda_nodes) > 0, (
            f"poda should have nodes from bracket expansion. Found: {poda_nodes[:5]}"
        )
        assert len(podb_nodes) > 0, (
            f"podb should have nodes from bracket expansion. Found: {podb_nodes[:5]}"
        )

        # Rack bracket expansion: rack[01-02] (names contain "_rack")
        rack_nodes = [node for node in all_nodes if "_rack" in node]
        assert len(rack_nodes) > 0, (
            f"racks should have nodes from bracket expansion. Found: {rack_nodes[:5]}"
        )

    def test_variable_expansion_links(self, helper):
        """Test fabric and rack-to-fabric links created by variable expansion."""
        links = helper.network.links.values()

        # Blueprint expand block: 2 leaves x 2 spines in each of the 2 fabrics.
        leaf_spine = [
            link for link in links if link.attrs.get("link_type") == "leaf_spine"
        ]
        assert len(leaf_spine) == 8
        for link in leaf_spine:
            assert re.fullmatch(r"dc[12]_fabric/leaf/leaf-[12]", link.source)
            assert re.fullmatch(r"dc[12]_fabric/spine/spine-[12]", link.target)
            assert link.source.split("/")[0] == link.target.split("/")[0]
            assert link.capacity == 400.0
            assert link.attrs.get("media_type") == "fiber"

        # Top-level expand block: 8 racks, each ToR wired to both leaves of its DC.
        rack_fabric = [
            link
            for link in links
            if link.attrs.get("connection_type") == "rack_to_fabric"
        ]
        assert len(rack_fabric) == 16
        for link in rack_fabric:
            assert re.fullmatch(r"dc[12]_pod[ab]_rack[12]/tor/tor-1", link.source)
            assert link.target.startswith(link.source[:3] + "_fabric/leaf/")

    def test_complex_node_rules(self, helper):
        """Test GPU server node_rules and role/hardware attrs on servers and ToRs."""
        # Test GPU server overrides for specific nodes
        gpu_server_groups = helper.network.select_node_groups_by_path(
            r"dc1_pod[ab]_rack[12]/servers/srv-[1-4]"
        )

        gpu_servers = []
        for group_nodes in gpu_server_groups.values():
            gpu_servers.extend(group_nodes)

        assert len(gpu_servers) > 0, "Should find GPU servers from node overrides"

        for server in gpu_servers[:3]:  # Check first few
            assert server.attrs.get("role") == "gpu_compute"
            assert server.attrs.get("gpu_count") == 8
            assert (server.attrs.get("hardware") or {}).get("component") == "ServerNode"

        all_servers = [
            node for node in helper.network.nodes.values() if "/servers/" in node.name
        ]

        for server in all_servers[:5]:  # Check a few servers
            role = server.attrs.get("role")
            assert role in ["compute", "gpu_compute"], (
                f"Server role should be technical, found: {role}"
            )

            assert (server.attrs.get("hardware") or {}).get("component") == "ServerNode"

        tor_switches = [
            node for node in helper.network.nodes.values() if "/tor/" in node.name
        ]

        assert len(tor_switches) > 0, "Should have ToR switches"

        for tor in tor_switches[:2]:  # Check a couple
            assert tor.attrs.get("role") == "top_of_rack"
            assert (tor.attrs.get("hardware") or {}).get("component") == "ToRSwitch48p"

    def test_complex_link_rules(self, helper):
        """Test complex link override patterns with regex."""
        # Test inter-DC link capacity overrides
        inter_dc_links = helper.network.find_links(
            source_regex=r"dc1_fabric/spine/.*", target_regex=r"dc2_fabric/spine/.*"
        )

        assert len(inter_dc_links) > 0, "Should find inter-DC spine links"

        for link in inter_dc_links[:3]:  # Check first few
            assert link.capacity == 800.0
            assert link.attrs.get("link_class") == "inter_dc"
            assert link.attrs.get("encryption") == "enabled"

        # Test higher capacity uplinks for specific racks
        enhanced_uplinks = helper.network.find_links(
            source_regex=r"dc1_pod[ab]_rack1/tor/.*",
            target_regex=r"dc1_fabric/leaf/.*",
        )

        for link in enhanced_uplinks[:3]:  # Check first few
            assert link.capacity == 200.0

    def test_risk_groups_integration(self, helper):
        """Test risk group names, Building_DC1 children, and spine membership."""
        risk_groups = helper.scenario.network.risk_groups
        expected_groups = SCENARIO_4_RISK_GROUP_EXPECTATIONS["risk_groups"]

        risk_group_names = {rg.name for rg in risk_groups.values()}
        for expected_group in expected_groups:
            assert expected_group in risk_group_names, (
                f"Expected risk group '{expected_group}' not found"
            )

        # Test hierarchical risk group structure using facility domain model
        building_group = risk_groups.get("Building_DC1")
        assert building_group is not None
        assert len(building_group.children) > 0, "Should have nested risk groups"
        assert building_group.attrs.get("type") == "building"

        # Verify nested children (expanded from bracket pattern)
        child_names = {child.name for child in building_group.children}
        assert "PowerZone_DC1_R1_PZA" in child_names
        assert "PowerZone_DC1_R1_PZB" in child_names

        # Test risk group assignments on nodes - using Room_DC1_Spine from facility domain
        spine_nodes_with_srg = [
            node
            for node in helper.network.nodes.values()
            if "Room_DC1_Spine" in node.risk_groups
        ]
        assert len(spine_nodes_with_srg) > 0, (
            "Spine nodes should have risk group assignments"
        )

    def test_traffic_matrix_configuration(self, helper):
        """Test demand set sizes and the mode used for each traffic_type."""
        traffic_expectations = SCENARIO_4_TRAFFIC_EXPECTATIONS

        # Test default matrix
        default_matrix = helper.scenario.demand_set.sets.get("default")
        assert default_matrix is not None, "Default traffic matrix should exist"
        assert len(default_matrix) == traffic_expectations["default_matrix"]

        # Test HPC workload matrix
        hpc_matrix = helper.scenario.demand_set.sets.get("hpc_workload")
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
        """Test the policy count and the single-rule link and node failure policies."""
        failure_expectations = SCENARIO_4_FAILURE_POLICY_EXPECTATIONS

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
        """Test the capacities the MaxFlow steps report.

        Every rack has 8 servers on 25-unit links, which bind before any uplink:
        pod-to-pod inside dc1 is 16 servers x 25 = 400 in either direction, and
        dc1 to dc2 is limited by dc2's 3 enabled racks (dc2_podb_rack2 is
        disabled) to 24 x 25 = 600. A single failure removes at most one
        server's 25 units.
        """
        steps = helper.scenario.results.to_dict()["steps"]

        def baseline_total(step: str) -> float:
            return steps[step]["data"]["baseline"]["summary"]["total_placed"]

        def failure_totals(step: str) -> list[float]:
            return [
                r["summary"]["total_placed"]
                for r in steps[step]["data"]["flow_results"]
            ]

        assert baseline_total("intra_dc_capacity_forward") == pytest.approx(400.0)
        assert baseline_total("intra_dc_capacity_reverse") == pytest.approx(400.0)
        assert baseline_total("inter_dc_capacity_forward") == pytest.approx(600.0)
        assert baseline_total("inter_dc_capacity_reverse") == pytest.approx(600.0)

        assert baseline_total("rack_failure_analysis") == pytest.approx(400.0)
        rack = failure_totals("rack_failure_analysis")
        assert rack and all(375.0 - 1e-9 <= t <= 400.0 + 1e-9 for t in rack)

        assert baseline_total("spine_failure_analysis") == pytest.approx(600.0)
        spine = failure_totals("spine_failure_analysis")
        assert spine and all(575.0 - 1e-9 <= t <= 600.0 + 1e-9 for t in spine)

    def test_network_explorer_integration(self, helper):
        """Test NetworkExplorer totals: at least 80 nodes, positive capex and power."""
        explorer = NetworkExplorer.explore_network(
            helper.network, helper.scenario.components_library
        )

        assert explorer.root_node is not None

        assert (
            explorer.root_node.stats.node_count >= 80
        )  # Should have substantial node count

        # Test component capex/power aggregation
        assert explorer.root_node.stats.total_capex > 0
        assert explorer.root_node.stats.total_power > 0

    def test_topology_semantic_correctness(self, helper):
        """Test edge attributes and that the graph has at most 20 weak components."""
        helper.validate_topology_semantics()

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
        """Test that nested nodes have at least three path levels starting with dc."""
        all_nodes = list(helper.network.nodes.keys())
        nested_nodes = [
            node
            for node in all_nodes
            if node.count("/") >= 2  # At least 3 levels: dc/pod/rack
        ]

        assert len(nested_nodes) > 0, (
            f"Should have nested nodes. Found: {all_nodes[:10]}"
        )

        for node_name in nested_nodes[:10]:  # Check first few
            parts = node_name.split("/")
            assert len(parts) >= 3  # dc/pod/rack or similar
            assert parts[0].startswith("dc")

    def test_regex_pattern_matching_complexity(self, helper):
        """Test complex regex patterns in overrides and selections."""
        all_nodes = list(helper.network.nodes.keys())

        # Substring filter for dc1 rack server nodes
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
        """Test that the exported graph keeps disabled nodes, flagged as disabled.

        BuildGraph exports every node; the 9 nodes of dc2_podb_rack2 (ToR plus
        8 servers) carry ``disabled: True``.
        """
        network_nodes = helper.network.nodes
        assert set(helper.graph.nodes) == set(network_nodes)

        disabled = {name for name, node in network_nodes.items() if node.disabled}
        assert len(disabled) == 9
        assert all(name.startswith("dc2_podb_rack2/") for name in disabled)
        for name in network_nodes:
            assert helper.graph.nodes[name]["disabled"] is (name in disabled)
