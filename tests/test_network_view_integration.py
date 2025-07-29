"""Integration tests for NetworkView with workflow analysis steps."""

import pytest

from ngraph.failure_manager import FailureManager
from ngraph.failure_policy import FailureCondition, FailurePolicy, FailureRule
from ngraph.network import Link, Network, Node, RiskGroup
from ngraph.network_view import NetworkView
from ngraph.results import Results
from ngraph.results_artifacts import FailurePolicySet, TrafficMatrixSet
from ngraph.scenario import Scenario
from ngraph.traffic_demand import TrafficDemand
from ngraph.traffic_manager import TrafficManager
from ngraph.workflow.capacity_envelope_analysis import CapacityEnvelopeAnalysis
from ngraph.workflow.capacity_probe import CapacityProbe
from ngraph.workflow.network_stats import NetworkStats


class TestNetworkViewIntegration:
    """Test NetworkView integration with various workflow steps."""

    @pytest.fixture
    def sample_network(self):
        """Create a sample network for testing."""
        net = Network()

        # Add nodes
        net.add_node(Node("A", attrs={"type": "spine"}))
        net.add_node(Node("B", attrs={"type": "spine"}))
        net.add_node(Node("C", attrs={"type": "leaf"}))
        net.add_node(Node("D", attrs={"type": "leaf"}))
        net.add_node(Node("E", disabled=True))  # Scenario-disabled node

        # Add links
        net.add_link(Link("A", "C", capacity=100.0))
        net.add_link(Link("A", "D", capacity=100.0))
        net.add_link(Link("B", "C", capacity=100.0))
        net.add_link(Link("B", "D", capacity=100.0))
        net.add_link(Link("A", "E", capacity=50.0))  # Link to disabled node

        # Add a disabled link
        disabled_link = Link("C", "D", capacity=50.0, disabled=True)
        net.add_link(disabled_link)

        # Add risk group
        rg = RiskGroup("rack1")
        net.risk_groups["rack1"] = rg
        net.nodes["C"].risk_groups.add("rack1")
        net.nodes["D"].risk_groups.add("rack1")

        return net

    @pytest.fixture
    def sample_scenario(self, sample_network):
        """Create a sample scenario with network and traffic."""
        scenario = Scenario(
            network=sample_network,
            workflow=[],  # Empty workflow for testing
            results=Results(),
        )

        # Add traffic matrix
        traffic_matrix = TrafficMatrixSet()
        traffic_matrix.add(
            "default",
            [
                TrafficDemand(
                    source_path="^[AB]$",  # Spine nodes
                    sink_path="^[CD]$",  # Leaf nodes
                    demand=50.0,
                    priority=1,
                    mode="combine",
                )
            ],
        )
        scenario.traffic_matrix_set = traffic_matrix

        # Add failure policy
        failure_policy_set = FailurePolicySet()
        failure_policy = FailurePolicy(
            rules=[
                FailureRule(
                    entity_scope="node",
                    rule_type="choice",
                    count=1,
                    conditions=[
                        FailureCondition(
                            attr="type",
                            operator="==",
                            value="spine",
                        )
                    ],
                )
            ]
        )
        failure_policy_set.add("spine_failure", failure_policy)
        failure_policy_set.add("default", failure_policy)
        scenario.failure_policy_set = failure_policy_set

        return scenario

    def test_capacity_probe_with_network_view(self, sample_scenario):
        """Test CapacityProbe using NetworkView for failure simulation."""
        # Test without failures
        probe = CapacityProbe(
            name="probe_baseline",
            source_path="^[AB]$",
            sink_path="^[CD]$",
            mode="combine",
        )
        probe.run(sample_scenario)

        # Get baseline flow - key is based on regex patterns
        baseline_key = "max_flow:[^[AB]$ -> ^[CD]$]"
        baseline_flow = sample_scenario.results.get("probe_baseline", baseline_key)
        assert baseline_flow == 400.0  # 2 spines × 2 leaves × 100 capacity each

        # Test with node exclusion
        probe_failed = CapacityProbe(
            name="probe_failed",
            source_path="^[AB]$",
            sink_path="^[CD]$",
            mode="combine",
            excluded_nodes=["A"],  # Exclude node A
        )
        probe_failed.run(sample_scenario)

        # Get flow with exclusion
        failed_flow = sample_scenario.results.get("probe_failed", baseline_key)
        assert failed_flow == 200.0  # Only B can send, 2 leaves × 100 capacity

        # Test with link exclusion
        probe_link_failed = CapacityProbe(
            name="probe_link_failed",
            source_path="^[AB]$",
            sink_path="^[CD]$",
            mode="combine",
            excluded_links=sample_scenario.network.get_links_between("A", "C"),
        )
        probe_link_failed.run(sample_scenario)

        # Flow should be reduced due to link exclusion
        link_failed_flow = sample_scenario.results.get(
            "probe_link_failed", baseline_key
        )
        assert link_failed_flow < baseline_flow

        # Verify original network is unchanged
        assert not sample_scenario.network.nodes["A"].disabled
        assert len(sample_scenario.network.nodes) == 5

    def test_capacity_envelope_with_network_view(self, sample_scenario):
        """Test CapacityEnvelopeAnalysis uses NetworkView internally."""
        # Run capacity envelope analysis with deterministic seed
        envelope = CapacityEnvelopeAnalysis(
            name="envelope_test",
            source_path="^[AB]$",
            sink_path="^[CD]$",
            mode="combine",
            failure_policy="spine_failure",
            iterations=5,
            parallelism=1,
            baseline=True,
            seed=42,
        )
        envelope.run(sample_scenario)

        # Check results
        envelopes = sample_scenario.results.get("envelope_test", "capacity_envelopes")
        assert "^[AB]$->^[CD]$" in envelopes

        envelope_data = envelopes["^[AB]$->^[CD]$"]
        assert envelope_data["total_samples"] == 5

        # First iteration should be baseline (no failures)
        # With frequency storage, check for baseline capacity
        frequencies = envelope_data["frequencies"]
        assert 400.0 in frequencies  # Baseline capacity
        assert 200.0 in frequencies  # Failure capacity

        # Should have both baseline and failure scenarios
        assert frequencies[400.0] == 1  # One baseline
        assert frequencies[200.0] == 4  # Four failure iterations

        # Verify original network is unchanged
        assert not sample_scenario.network.nodes["A"].disabled
        assert not sample_scenario.network.nodes["B"].disabled

    def test_network_stats_with_network_view(self, sample_scenario):
        """Test NetworkStats with NetworkView for filtered statistics."""
        # Get baseline stats
        stats_base = NetworkStats(name="stats_base")
        stats_base.run(sample_scenario)

        # Get stats with node excluded
        stats_excluded = NetworkStats(
            name="stats_excluded",
            excluded_nodes=["A"],
        )
        stats_excluded.run(sample_scenario)

        # Node count should be reduced (E is disabled, A is excluded)
        base_nodes = sample_scenario.results.get("stats_base", "node_count")
        excluded_nodes = sample_scenario.results.get("stats_excluded", "node_count")
        assert base_nodes == 4  # A, B, C, D (E is disabled)
        assert excluded_nodes == 3  # B, C, D (E disabled, A excluded)

        # Link count should be reduced (links from/to A are excluded)
        base_links = sample_scenario.results.get("stats_base", "link_count")
        excluded_links = sample_scenario.results.get("stats_excluded", "link_count")
        assert excluded_links < base_links

    def test_failure_manager_with_network_view(self, sample_scenario):
        """Test FailureManager using NetworkView."""
        # Create failure manager
        fm = FailureManager(
            network=sample_scenario.network,
            failure_policy_set=sample_scenario.failure_policy_set,
            policy_name="spine_failure",
        )

        # Get failed entities
        failed_nodes, failed_links = fm.compute_exclusions()
        assert len(failed_nodes) == 1  # One spine should fail
        assert failed_nodes.pop() in ["A", "B"]

        # Run single failure scenario with a simple analysis function
        def simple_analysis(network_view, **kwargs):
            return f"Analysis completed with {len(network_view.nodes)} nodes"

        result = fm.run_single_failure_scenario(simple_analysis)

        # Check result was returned
        assert "Analysis completed" in result

        # Verify original network is unchanged
        assert not sample_scenario.network.nodes["A"].disabled
        assert not sample_scenario.network.nodes["B"].disabled

    def test_traffic_manager_with_network_view(self, sample_network):
        """Test TrafficManager directly with NetworkView."""
        # Create traffic matrix
        traffic_matrix = TrafficMatrixSet()
        traffic_matrix.add(
            "default",
            [
                TrafficDemand(
                    source_path="^[AB]$",
                    sink_path="^[CD]$",
                    demand=150.0,
                    priority=1,
                    mode="combine",
                )
            ],
        )

        # Test with base network
        tm_base = TrafficManager(
            network=sample_network,
            traffic_matrix_set=traffic_matrix,
        )
        tm_base.build_graph()
        tm_base.expand_demands()
        placed_base = tm_base.place_all_demands()
        assert placed_base == 150.0  # All demand placed

        # Test with NetworkView (node A excluded)
        view = NetworkView.from_excluded_sets(
            sample_network,
            excluded_nodes=["A"],
        )

        tm_view = TrafficManager(
            network=view,
            traffic_matrix_set=traffic_matrix,
        )
        tm_view.build_graph()
        tm_view.expand_demands()
        placed_view = tm_view.place_all_demands()

        # With only one spine, still have enough capacity (2 links × 100 = 200)
        assert placed_view == 150.0  # All demand can still be placed

    def test_concurrent_network_views(self, sample_network):
        """Test multiple NetworkView instances can operate concurrently."""
        # Create multiple views with different exclusions
        view1 = NetworkView.from_excluded_sets(sample_network, excluded_nodes=["A"])
        view2 = NetworkView.from_excluded_sets(sample_network, excluded_nodes=["B"])
        view3 = NetworkView.from_excluded_sets(sample_network, excluded_links=[])

        # Test they have different visible nodes (E is disabled in scenario)
        assert len(view1.nodes) == 3  # B, C, D (A excluded, E disabled)
        assert len(view2.nodes) == 3  # A, C, D (B excluded, E disabled)
        assert len(view3.nodes) == 4  # A, B, C, D (E disabled)

        # Test max flow on each view
        flow1 = view1.max_flow("^B$", "^[CD]$", mode="combine")
        flow2 = view2.max_flow("^A$", "^[CD]$", mode="combine")
        flow3 = view3.max_flow("^[AB]$", "^[CD]$", mode="combine")

        # Check the actual keys returned
        assert len(flow1) == 1
        assert len(flow2) == 1
        assert len(flow3) == 1

        # Get the actual flow values (keys are based on regex patterns)
        flow1_value = list(flow1.values())[0]
        flow2_value = list(flow2.values())[0]
        flow3_value = list(flow3.values())[0]

        assert flow1_value == 200.0  # B to both C and D
        assert flow2_value == 200.0  # A to both C and D
        assert flow3_value == 400.0  # Both spines to both leaves

        # Verify all views are independent
        assert "A" not in view1.nodes
        assert "B" not in view2.nodes
        assert "A" in view3.nodes and "B" in view3.nodes

    def test_risk_group_handling(self, sample_network):
        """Test NetworkView correctly handles risk group failures."""
        # Create failure policy for risk group
        failure_policy_set = FailurePolicySet()
        failure_policy = FailurePolicy(
            rules=[
                FailureRule(
                    entity_scope="risk_group",
                    rule_type="all",
                )
            ]
        )
        failure_policy_set.add("risk_failure", failure_policy)

        # Create failure manager
        fm = FailureManager(
            network=sample_network,
            failure_policy_set=failure_policy_set,
            policy_name="risk_failure",
        )

        # Get failed entities
        failed_nodes, failed_links = fm.compute_exclusions()

        # Both C and D should be failed (they're in rack1)
        assert set(failed_nodes) == {"C", "D"}

        # Create view and test
        view = NetworkView.from_excluded_sets(
            sample_network,
            excluded_nodes=failed_nodes,
        )

        # Only A, B should be visible (E is disabled, C and D are failed)
        assert set(view.nodes.keys()) == {"A", "B"}

    def test_scenario_state_preservation(self, sample_scenario):
        """Test that scenario state is preserved across multiple analyses."""
        # Run multiple analyses
        for i in range(3):
            probe = CapacityProbe(
                name=f"probe_{i}",
                source_path="^[AB]$",
                sink_path="^[CD]$",
                excluded_nodes=["A"] if i % 2 == 0 else ["B"],
            )
            probe.run(sample_scenario)

        # Verify network state is unchanged
        assert not sample_scenario.network.nodes["A"].disabled
        assert not sample_scenario.network.nodes["B"].disabled
        assert sample_scenario.network.nodes["E"].disabled  # Should remain disabled

        # Verify all results are stored
        result_key = "max_flow:[^[AB]$ -> ^[CD]$]"
        for i in range(3):
            result = sample_scenario.results.get(f"probe_{i}", result_key)
            assert result == 200.0  # One spine failed each time
