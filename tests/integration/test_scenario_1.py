"""
Integration tests for scenario 1: Basic 6-node L3 US backbone network.

This module tests the fundamental building blocks of NetGraph integration:
- Basic network definition with explicit nodes and links
- Single link failure scenario configuration
- Traffic matrix setup and validation
- Network topology correctness verification

Scenario 1 serves as the baseline test for the integration framework,
validating that simple network topologies work correctly before testing
more complex blueprint-based scenarios.

Uses the modular testing approach with validation helpers from the
integration.helpers module.
"""

import pytest

from .expectations import SCENARIO_1_EXPECTATIONS
from .helpers import create_scenario_helper, load_scenario_from_file


@pytest.mark.slow
class TestScenario1:
    """Tests for scenario 1 using modular validation approach."""

    @pytest.fixture
    def scenario_1(self):
        """Load scenario 1 from YAML file."""
        return load_scenario_from_file("scenario_1.yaml")

    @pytest.fixture
    def scenario_1_executed(self, scenario_1):
        """Execute scenario 1 workflow and return with results."""
        scenario_1.run()
        return scenario_1

    @pytest.fixture
    def helper(self, scenario_1_executed):
        """Create test helper for scenario 1."""
        # create_scenario_helper handles graph conversion using nx.node_link_graph
        helper = create_scenario_helper(scenario_1_executed)
        return helper

    def test_scenario_parsing_and_execution(self, scenario_1_executed):
        """Test that scenario 1 can be parsed and executed without errors."""
        # Basic sanity check - scenario should have run successfully
        assert scenario_1_executed.results is not None
        exported = scenario_1_executed.results.to_dict()
        assert exported["steps"]["build_graph"]["data"].get("graph") is not None

    def test_network_structure_validation(self, helper):
        """Test basic network structure matches expectations."""
        helper.validate_network_structure(SCENARIO_1_EXPECTATIONS)

    def test_specific_nodes_exist(self, helper):
        """Test that all expected nodes from the YAML are present."""
        expected_nodes = {"SEA", "SFO", "DEN", "DFW", "JFK", "DCA"}

        for node_name in expected_nodes:
            assert node_name in helper.network.nodes, (
                f"Expected node '{node_name}' not found in network"
            )

    def test_link_topology_correctness(self, helper):
        """Test that the network topology matches the YAML specification."""
        # Verify some key links exist as specified in scenario_1.yaml
        expected_links = [
            ("SEA", "DEN"),
            ("SFO", "DEN"),
            ("SEA", "DFW"),
            ("SFO", "DFW"),
            ("DEN", "DFW"),  # Should have 2 parallel links
            ("DEN", "JFK"),
            ("DFW", "DCA"),
            ("DFW", "JFK"),
            ("JFK", "DCA"),
        ]

        for source, target in expected_links:
            links = helper.network.find_links(
                source_regex=f"^{source}$", target_regex=f"^{target}$"
            )
            assert len(links) > 0, (
                f"Expected link from '{source}' to '{target}' not found"
            )

    def test_parallel_links_between_den_dfw(self, helper):
        """Test that DEN-DFW has exactly 2 parallel links as specified."""
        links = helper.network.find_links(source_regex="^DEN$", target_regex="^DFW$")
        # Should have exactly 2 parallel links between DEN and DFW
        assert len(links) == 2, (
            f"Expected 2 parallel links between DEN and DFW, found {len(links)}"
        )

        # Both should have capacity 400 and cost 7102
        for link in links:
            assert link.capacity == 400, (
                f"Expected capacity 400 for DEN-DFW link, found {link.capacity}"
            )
            assert link.cost == 7102, (
                f"Expected cost 7102 for DEN-DFW link, found {link.cost}"
            )

    def test_link_capacities_and_costs(self, helper):
        """Test that links have expected capacities and costs from YAML."""
        # Test a few specific links to ensure YAML parsing worked correctly
        test_cases = [
            ("SEA", "DEN", 200, 6846),
            ("SFO", "DEN", 200, 7754),
            ("JFK", "DCA", 100, 1714),
        ]

        for source, target, expected_capacity, expected_cost in test_cases:
            links = helper.network.find_links(
                source_regex=f"^{source}$", target_regex=f"^{target}$"
            )
            assert len(links) > 0, f"No links found from {source} to {target}"

            # Check the first link (should be only one for these pairs)
            link = links[0]
            assert link.capacity == expected_capacity, (
                f"Link {source}->{target} expected capacity {expected_capacity}, "
                f"found {link.capacity}"
            )
            assert link.cost == expected_cost, (
                f"Link {source}->{target} expected cost {expected_cost}, "
                f"found {link.cost}"
            )

    def test_traffic_demands_configuration(self, helper):
        """Test that traffic demands are correctly configured."""
        helper.validate_traffic_demands(expected_count=4)

        # Verify specific demands from the YAML
        default_demands = helper.scenario.traffic_matrix_set.get_default_matrix()

        # Convert to a more testable format
        demands_dict = {
            (demand.source, demand.sink): demand.demand for demand in default_demands
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
        """Test that failure policy is correctly configured."""
        helper.validate_failure_policy(expected_rules=1, expected_scopes=["link"])

        # Additional validation of the specific rule
        policies = helper.scenario.failure_policy_set.get_all_policies()
        policy = policies[0]  # Get first policy for validation
        # Access first rule via modes-based API
        rule = policy.modes[0].rules[0]

        assert rule.logic == "or", f"Expected rule logic 'or', found '{rule.logic}'"
        assert rule.rule_type == "choice", (
            f"Expected rule type 'choice', found '{rule.rule_type}'"
        )
        assert rule.count == 1, f"Expected rule count 1, found {rule.count}"

        expected_description = "Evaluate traffic routing under any single link failure."
        actual_description = policy.attrs.get("description")
        assert actual_description == expected_description, (
            f"Expected description '{expected_description}', found '{actual_description}'"
        )

    def test_topology_semantic_correctness(self, helper):
        """Test that the network topology is semantically correct."""
        helper.validate_topology_semantics()

    def test_graph_connectivity(self, helper):
        """Test that the graph has expected connectivity properties."""
        # For this backbone network, all nodes should be reachable from any other node
        import networkx as nx

        # Check weak connectivity (appropriate for directed graphs)
        assert nx.is_weakly_connected(helper.graph), (
            "Network should be weakly connected"
        )

        # Check that there are no isolated nodes
        isolated_nodes = list(nx.isolates(helper.graph))
        assert len(isolated_nodes) == 0, f"Found isolated nodes: {isolated_nodes}"

    def test_node_attributes_from_yaml(self, helper):
        """Test that node attributes from YAML are correctly parsed."""
        # Test coordinate attributes for a few nodes
        test_nodes = {
            "SEA": [47.6062, -122.3321],
            "SFO": [37.7749, -122.4194],
            "DCA": [38.907192, -77.036871],
        }

        for node_name, expected_coords in test_nodes.items():
            helper.validate_node_attributes(node_name, {"coords": expected_coords})

    def test_link_attributes_from_yaml(self, helper):
        """Test that link attributes from YAML are correctly parsed."""
        # Test distance attributes for specific links
        helper.validate_link_attributes(
            source_pattern="^SEA$",
            target_pattern="^DEN$",
            expected_attrs={"distance_km": 1369.13},
        )

        helper.validate_link_attributes(
            source_pattern="^SFO$",
            target_pattern="^DEN$",
            expected_attrs={"distance_km": 1550.77},
        )


# Removed redundant smoke test; class-based tests already cover these checks.
