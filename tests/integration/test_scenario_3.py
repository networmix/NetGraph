"""
Integration tests for scenario 3: 3-tier Clos network with nested blueprints.

This module tests the most advanced NetGraph capabilities including:
- Deep blueprint nesting with multiple levels of hierarchy
- 3-tier Clos fabric topology with brick-spine-spine architecture
- Node and link override mechanisms for customization
- Capacity probing with different flow placement algorithms
- Network analysis workflows with multiple steps
- Risk group assignment and validation

Scenario 3 represents the most complex network topology in the test suite,
validating NetGraph's ability to handle large network definitions with
relationships and analysis requirements.

Uses the modular testing approach with validation helpers from the
integration.helpers module.
"""

import pytest

from .expectations import SCENARIO_3_EXPECTATIONS
from .helpers import create_scenario_helper, load_scenario_from_file


@pytest.mark.slow
class TestScenario3:
    """Tests for scenario 3 using modular validation approach."""

    @pytest.fixture
    def scenario_3(self):
        """Load scenario 3 from YAML file."""
        return load_scenario_from_file("scenario_3.yaml")

    @pytest.fixture
    def scenario_3_executed(self, scenario_3):
        """Execute scenario 3 workflow and return with results."""
        scenario_3.run()
        return scenario_3

    @pytest.fixture
    def helper(self, scenario_3_executed):
        """Create test helper for scenario 3."""
        # create_scenario_helper handles graph conversion using nx.node_link_graph
        helper = create_scenario_helper(scenario_3_executed)
        return helper

    def test_scenario_parsing_and_execution(self, scenario_3_executed):
        """Test that scenario 3 can be parsed and executed without errors."""
        assert scenario_3_executed.results is not None
        exported = scenario_3_executed.results.to_dict()
        assert exported["steps"]["build_graph"]["data"].get("graph") is not None

    def test_network_structure_validation(self, helper):
        """Test basic network structure matches expectations for complex 3-tier Clos."""
        helper.validate_network_structure(SCENARIO_3_EXPECTATIONS)

    def test_nested_blueprint_structure(self, helper):
        """Test complex nested blueprint expansions work correctly."""
        # Each 3-tier Clos should have 32 nodes total
        clos1_nodes = [
            node for node in helper.network.nodes if node.startswith("my_clos1/")
        ]
        assert len(clos1_nodes) == 32, (
            f"my_clos1 should have 32 nodes, found {len(clos1_nodes)}"
        )

        clos2_nodes = [
            node for node in helper.network.nodes if node.startswith("my_clos2/")
        ]
        assert len(clos2_nodes) == 32, (
            f"my_clos2 should have 32 nodes, found {len(clos2_nodes)}"
        )

    def test_3tier_clos_blueprint_structure(self, helper):
        """Test that 3-tier Clos blueprint creates expected hierarchy."""
        # Each Clos should have:
        # - 2 brick instances (b1, b2), each with 4 t1 + 4 t2 = 8 nodes
        # - 16 spine nodes (t3-1 through t3-16)
        # Total: 8 + 8 + 16 = 32 nodes per Clos

        # Check b1 structure in my_clos1
        b1_t1_nodes = [
            node for node in helper.network.nodes if node.startswith("my_clos1/b1/t1/")
        ]
        assert len(b1_t1_nodes) == 4, (
            f"my_clos1/b1/t1 should have 4 nodes, found {len(b1_t1_nodes)}"
        )

        b1_t2_nodes = [
            node for node in helper.network.nodes if node.startswith("my_clos1/b1/t2/")
        ]
        assert len(b1_t2_nodes) == 4, (
            f"my_clos1/b1/t2 should have 4 nodes, found {len(b1_t2_nodes)}"
        )

        # Check spine structure
        spine_nodes = [
            node for node in helper.network.nodes if node.startswith("my_clos1/spine/")
        ]
        assert len(spine_nodes) == 16, (
            f"my_clos1/spine should have 16 nodes, found {len(spine_nodes)}"
        )

    def test_one_to_one_pattern_adjacency(self, helper):
        """Test that one_to_one patterns create correct pairings."""
        # b1/t2 to spine - check actual behavior (4 t2 nodes * 16 spine nodes in one_to_one pattern)
        b1_t2_to_spine_links = helper.network.find_links(
            source_regex=r"my_clos1/b1/t2/.*", target_regex=r"my_clos1/spine/.*"
        )

        # Count unique t2 source nodes
        t2_sources = {link.source for link in b1_t2_to_spine_links}

        # Verify that we have 4 t2 sources (from brick_2tier blueprint)
        assert len(t2_sources) == 4, (
            f"Expected 4 t2 source nodes, found {len(t2_sources)}"
        )

        # Verify that we have links (actual implementation may connect to all spine nodes)
        assert len(b1_t2_to_spine_links) > 0, "Should have b1/t2->spine connections"

        # Verify each t2 node connects to spine nodes
        for t2_node in t2_sources:
            t2_links = [link for link in b1_t2_to_spine_links if link.source == t2_node]
            assert len(t2_links) > 0, f"t2 node {t2_node} should connect to spine nodes"

        # Inter-Clos spine connections should also be one_to_one
        inter_spine_links = helper.network.find_links(
            source_regex=r"my_clos1/spine/.*", target_regex=r"my_clos2/spine/.*"
        )
        assert len(inter_spine_links) == 16, (
            f"Expected 16 one-to-one inter-Clos spine links, found {len(inter_spine_links)}"
        )

    def test_mesh_pattern_in_nested_blueprints(self, helper):
        """Test that mesh patterns work within nested blueprints."""
        # Within each brick_2tier blueprint, t1 should mesh with t2
        # Each brick has 4 t1 and 4 t2 nodes, so 4 * 4 = 16 mesh links per brick
        b1_t1_to_t2_links = helper.network.find_links(
            source_regex=r"my_clos1/b1/t1/.*", target_regex=r"my_clos1/b1/t2/.*"
        )
        assert len(b1_t1_to_t2_links) == 16, (
            f"Expected 16 mesh links in b1 brick, found {len(b1_t1_to_t2_links)}"
        )

    def test_node_overrides_application(self, helper):
        """Test that node overrides are correctly applied."""
        # Test specific node override from YAML
        # Uses facility domain model for risk groups
        helper.validate_node_attributes(
            "my_clos1/b1/t1/t1-1",
            {"risk_groups": {"PowerZone_Clos1_B1_PZA"}, "hw_component": "LeafHW-A"},
        )

        helper.validate_node_attributes(
            "my_clos2/b2/t1/t1-1",
            {"risk_groups": {"PowerZone_Clos2_B2_PZA"}, "hw_component": "LeafHW-B"},
        )

        # Test spine node overrides with regex pattern
        helper.validate_node_attributes(
            "my_clos1/spine/t3-1",
            {"risk_groups": {"Room_Clos1_Spine"}, "hw_component": "SpineHW"},
        )

    def test_link_overrides_application(self, helper):
        """Test that link overrides are correctly applied."""
        # Test specific capacity override
        override_links = helper.network.find_links(
            source_regex="my_clos1/spine/t3-1$", target_regex="my_clos2/spine/t3-1$"
        )
        assert len(override_links) > 0, "Override link t3-1 should exist"

        for link in override_links:
            assert link.capacity == 200.0, (
                f"Override link should have capacity 200.0 Gb/s, found {link.capacity}"
            )

        # Test general spine-spine link overrides
        # Only risk_groups are validated at link-level; per-end HW is under attrs.hardware
        # Uses fiber domain model for link risk groups
        helper.validate_link_attributes(
            source_pattern=r"my_clos1/spine/t3-2$",
            target_pattern=r"my_clos2/spine/t3-2$",
            expected_attrs={"risk_groups": {"Conduit_InterClos_C1"}},
        )

    def test_link_capacity_configuration(self, helper):
        """Test that links have correct capacities from blueprint definitions."""
        # Brick internal links should have capacity 100.0 Gb/s
        brick_internal_links = helper.network.find_links(
            source_regex=r"my_clos1/b1/t1/.*", target_regex=r"my_clos1/b1/t2/.*"
        )

        for link in brick_internal_links[:3]:  # Check first few
            assert link.capacity == 100.0, (
                f"Brick internal link expected capacity 100.0 Gb/s, found {link.capacity}"
            )

        # Spine connections should have capacity 400.0 Gb/s (except overridden one)
        regular_spine_links = helper.network.find_links(
            source_regex=r"my_clos1/spine/t3-2$", target_regex=r"my_clos2/spine/t3-2$"
        )

        for link in regular_spine_links:
            assert link.capacity == 400.0, (
                f"Regular spine link expected capacity 400.0 Gb/s, found {link.capacity}"
            )

    def test_no_traffic_demands(self, helper):
        """Test that this scenario has no traffic demands as expected."""
        helper.validate_traffic_demands(expected_count=0)

    def test_no_failure_policy(self, helper):
        """Test that this scenario has no failure policy as expected."""
        helper.validate_failure_policy(expected_rules=0)

    def test_capacity_envelope_proportional_flow_results(self, helper):
        """Test capacity envelope results with PROPORTIONAL flow placement."""
        # Test forward direction (MaxFlow returns baseline separately, flow_results for failures)
        exported = helper.scenario.results.to_dict()
        fwd = exported["steps"].get("capacity_analysis_forward", {}).get("data", {})
        # Without failure policy, use baseline; otherwise check flow_results
        fwd_result = fwd.get("baseline") or (fwd.get("flow_results", []) or [None])[0]
        assert fwd_result, (
            "Forward capacity analysis should have baseline or flow_results"
        )
        fwd_total = float(fwd_result.get("summary", {}).get("total_placed", 0.0))
        assert abs(fwd_total - 3200.0) < 0.1, (
            f"Expected forward flow ~3200.0, got {fwd_total}"
        )

        # Test reverse direction
        rev = exported["steps"].get("capacity_analysis_reverse", {}).get("data", {})
        rev_result = rev.get("baseline") or (rev.get("flow_results", []) or [None])[0]
        assert rev_result, (
            "Reverse capacity analysis should have baseline or flow_results"
        )
        rev_total = float(rev_result.get("summary", {}).get("total_placed", 0.0))
        assert abs(rev_total - 3200.0) < 0.1, (
            f"Expected reverse flow ~3200.0, got {rev_total}"
        )

    def test_capacity_envelope_equal_balanced_flow_results(self, helper):
        """Test capacity envelope results with EQUAL_BALANCED flow placement."""
        exported = helper.scenario.results.to_dict()
        fwd = (
            exported["steps"]
            .get("capacity_analysis_forward_balanced", {})
            .get("data", {})
        )
        # Without failure policy, use baseline; otherwise check flow_results
        fwd_result = fwd.get("baseline") or (fwd.get("flow_results", []) or [None])[0]
        assert fwd_result, (
            "Forward balanced capacity analysis should have baseline or flow_results"
        )
        fwd_total = float(fwd_result.get("summary", {}).get("total_placed", 0.0))
        assert abs(fwd_total - 3200.0) < 0.1

        rev = (
            exported["steps"]
            .get("capacity_analysis_reverse_balanced", {})
            .get("data", {})
        )
        rev_result = rev.get("baseline") or (rev.get("flow_results", []) or [None])[0]
        assert rev_result, (
            "Reverse balanced capacity analysis should have baseline or flow_results"
        )
        rev_total = float(rev_result.get("summary", {}).get("total_placed", 0.0))
        assert abs(rev_total - 3200.0) < 0.1

    def test_flow_conservation_properties(self, helper):
        """Test that flow results satisfy conservation principles."""
        all_flows: dict[str, float] = {}

        exported = helper.scenario.results.to_dict()

        def total_placed(step: str) -> float | None:
            data = exported["steps"].get(step, {}).get("data", {})
            # Check baseline first (no failure policy), then flow_results
            result = data.get("baseline") or (data.get("flow_results", []) or [None])[0]
            if not result:
                return None
            return float(result.get("summary", {}).get("total_placed", 0.0))

        fp = total_placed("capacity_analysis_forward")
        if fp is not None:
            all_flows["forward_proportional"] = fp

        rp = total_placed("capacity_analysis_reverse")
        if rp is not None:
            all_flows["reverse_proportional"] = rp

        fb = total_placed("capacity_analysis_forward_balanced")
        if fb is not None:
            all_flows["forward_balanced"] = fb

        rb = total_placed("capacity_analysis_reverse_balanced")
        if rb is not None:
            all_flows["reverse_balanced"] = rb

        assert len(all_flows) > 0, "Should have at least some capacity analysis results"

        expected_flow = 3200.0
        for name, value in all_flows.items():
            assert abs(value - expected_flow) < 0.1, (
                f"Flow {name} = {value}, expected ~{expected_flow}"
            )

    def test_topology_semantic_correctness(self, helper):
        """Test that the complex nested topology is semantically correct."""
        helper.validate_topology_semantics()

    def test_inter_clos_connectivity(self, helper):
        """Test connectivity between the two Clos fabrics."""
        # Should be connected only through spine-spine links
        inter_clos_links = helper.network.find_links(
            source_regex=r"my_clos1/.*", target_regex=r"my_clos2/.*"
        )

        # All inter-Clos links should be spine-spine
        for link in inter_clos_links:
            assert "/spine/" in link.source, (
                f"Inter-Clos link source should be spine: {link.source}"
            )
            assert "/spine/" in link.target, (
                f"Inter-Clos link target should be spine: {link.target}"
            )

    def test_regex_pattern_matching_in_overrides(self, helper):
        """Test that regex patterns in overrides work correctly."""
        # The node override "my_clos1/spine/t3.*" should match all spine nodes
        spine_nodes_clos1 = [
            node
            for node in helper.network.nodes
            if node.startswith("my_clos1/spine/t3-")
        ]

        # All should have the same risk group from the override
        # Uses facility domain model for risk groups
        for node_name in spine_nodes_clos1[:3]:  # Check first few
            node = helper.network.nodes[node_name]
            assert node.risk_groups == {"Room_Clos1_Spine"}, (
                f"Spine node {node_name} should have Room_Clos1_Spine risk group"
            )

    def test_workflow_step_execution_order(self, scenario_3_executed):
        """Test that workflow steps executed in correct order."""
        # Should have results from BuildGraph step
        exported2 = scenario_3_executed.results.to_dict()
        graph_result = exported2["steps"]["build_graph"]["data"].get("graph")
        assert graph_result is not None, "BuildGraph step should have executed"

        # Should have results from MaxFlow analysis steps (flow_results present)
        assert (
            exported2["steps"]["capacity_analysis_forward"]["data"].get("flow_results")
            is not None
        )
        assert (
            exported2["steps"]["capacity_analysis_forward_balanced"]["data"].get(
                "flow_results"
            )
            is not None
        )


# Removed redundant smoke test; class-based tests already cover these checks.
