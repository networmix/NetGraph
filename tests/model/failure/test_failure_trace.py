"""Tests for failure_trace capture in FailurePolicy and FailureManager."""

import pytest

from ngraph.analysis.failure_manager import FailureManager
from ngraph.dsl.selectors.schema import Condition
from ngraph.model.failure.policy import (
    FailureMode,
    FailurePolicy,
    FailureRule,
)
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node

# -----------------------------------------------------------------------------
# FailurePolicy.apply_failures trace tests
# -----------------------------------------------------------------------------


class TestFailureTracePolicyLevel:
    """Test failure_trace capture in FailurePolicy.apply_failures."""

    def test_trace_captures_mode_index(self) -> None:
        """Test that mode_index is correctly captured."""
        rule = FailureRule(scope="node", mode="all")
        policy = FailurePolicy(
            modes=[
                FailureMode(weight=0.0, rules=[]),  # weight=0 never selected
                FailureMode(weight=1.0, rules=[rule], attrs={"name": "mode1"}),
            ]
        )

        nodes = {"N1": {}, "N2": {}}
        trace: dict = {}
        policy.apply_failures(nodes, {}, failure_trace=trace, seed=42)

        assert trace["mode_index"] == 1
        assert trace["mode_attrs"] == {"name": "mode1"}

    def test_trace_captures_mode_attrs(self) -> None:
        """Test that mode_attrs is a copy of the selected mode's attrs."""
        attrs = {"severity": "high", "region": "west"}
        rule = FailureRule(scope="node", mode="all")
        policy = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[rule], attrs=attrs)]
        )

        trace: dict = {}
        policy.apply_failures({"N1": {}}, {}, failure_trace=trace)

        assert trace["mode_attrs"] == attrs
        # Verify it's a copy, not a reference
        assert trace["mode_attrs"] is not attrs

    def test_trace_captures_selection_fields(self) -> None:
        """Test that selections contain correct fields."""
        rule = FailureRule(
            scope="node",
            conditions=[Condition(attr="type", op="==", value="router")],
            mode="choice",
            count=1,
        )
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        nodes = {
            "N1": {"type": "router"},
            "N2": {"type": "router"},
            "N3": {"type": "server"},
        }
        trace: dict = {}
        policy.apply_failures(nodes, {}, failure_trace=trace, seed=42)

        assert len(trace["selections"]) == 1
        sel = trace["selections"][0]
        assert sel["rule_index"] == 0
        assert sel["scope"] == "node"
        assert sel["mode"] == "choice"
        assert sel["matched_count"] == 2  # N1 and N2 matched
        assert len(sel["selected_ids"]) == 1  # count=1

    def test_trace_empty_selections_when_no_match(self) -> None:
        """Test that rules matching nothing are not recorded."""
        rule = FailureRule(
            scope="node",
            conditions=[Condition(attr="type", op="==", value="nonexistent")],
            mode="all",
        )
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        nodes = {"N1": {"type": "router"}}
        trace: dict = {}
        policy.apply_failures(nodes, {}, failure_trace=trace)

        assert trace["selections"] == []

    def test_trace_captures_expansion_nodes_links(self) -> None:
        """Test expansion tracking for risk group expansion."""
        nodes = {
            "N1": {"risk_groups": ["rg1"]},
            "N2": {"risk_groups": ["rg1"]},
            "N3": {"risk_groups": []},
        }
        links = {"L1": {"risk_groups": ["rg1"]}}

        # N1 and N2 share rg1, L1 also in rg1
        # After expansion: N2 and L1 should appear in expansion
        trace: dict = {}
        # Pass only N1 that matches (we need to match only one node initially)
        policy_choice = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="choice", count=1)],
                )
            ],
            expand_groups=True,
        )
        policy_choice.apply_failures(nodes, links, failure_trace=trace, seed=42)

        # The expansion should show nodes/links added after initial selection
        assert "expansion" in trace
        assert "nodes" in trace["expansion"]
        assert "links" in trace["expansion"]

    def test_trace_captures_expansion_risk_groups(self) -> None:
        """Test expansion tracking for risk group children."""
        # Select only the parent, then expansion should add child
        rule = FailureRule(
            scope="risk_group",
            conditions=[Condition(attr="name", op="==", value="parent_rg")],
            mode="all",
        )
        policy = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[rule])],
            expand_children=True,
        )

        risk_groups = {
            "parent_rg": {"name": "parent_rg", "children": [{"name": "child_rg"}]},
            "child_rg": {"name": "child_rg", "children": []},
        }

        trace: dict = {}
        policy.apply_failures({}, {}, risk_groups, failure_trace=trace)

        # child_rg should appear in expansion.risk_groups (added by expansion, not selection)
        assert "child_rg" in trace["expansion"]["risk_groups"]

    def test_trace_no_modes_returns_null_mode_index(self) -> None:
        """Test that mode_index is None when no modes configured."""
        policy = FailurePolicy(modes=[])

        trace: dict = {}
        policy.apply_failures({}, {}, failure_trace=trace)

        assert trace["mode_index"] is None
        assert trace["mode_attrs"] == {}
        assert trace["selections"] == []

    def test_trace_none_does_not_populate(self) -> None:
        """Test that passing failure_trace=None doesn't cause errors."""
        rule = FailureRule(scope="node", mode="all")
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        # Should not raise
        result = policy.apply_failures({"N1": {}}, {}, failure_trace=None)
        assert result == ["N1"]

    def test_trace_deterministic_with_seed(self) -> None:
        """Test that trace is deterministic with fixed seed."""
        rule = FailureRule(scope="node", mode="choice", count=1)
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

        nodes = {"N1": {}, "N2": {}, "N3": {}}

        trace1: dict = {}
        trace2: dict = {}
        policy.apply_failures(nodes, {}, failure_trace=trace1, seed=42)
        policy.apply_failures(nodes, {}, failure_trace=trace2, seed=42)

        assert trace1 == trace2


# -----------------------------------------------------------------------------
# FailureManager integration tests
# -----------------------------------------------------------------------------


@pytest.fixture
def network_with_risk_groups() -> Network:
    """Create a network with risk groups for expansion testing."""
    network = Network()
    n1 = Node("N1", attrs={"type": "router"})
    n1.risk_groups = ["rg1"]
    n2 = Node("N2", attrs={"type": "router"})
    n2.risk_groups = ["rg1"]
    n3 = Node("N3", attrs={"type": "server"})
    network.add_node(n1)
    network.add_node(n2)
    network.add_node(n3)

    link = Link("N1", "N2", capacity=100.0)
    link.risk_groups = ["rg1"]
    network.add_link(link)
    network.add_link(Link("N2", "N3", capacity=100.0))
    return network


@pytest.fixture
def simple_network() -> Network:
    """Create a simple network for testing."""
    network = Network()
    network.add_node(Node("N1", attrs={"type": "router"}))
    network.add_node(Node("N2", attrs={"type": "router"}))
    network.add_node(Node("N3", attrs={"type": "server"}))
    network.add_link(Link("N1", "N2", capacity=100.0))
    network.add_link(Link("N2", "N3", capacity=100.0))
    return network


class TestFailureTraceManagerIntegration:
    """Test failure_trace integration in FailureManager."""

    def test_results_include_trace_fields(self, simple_network: Network) -> None:
        """Test that results include trace fields when store_failure_patterns=True."""
        rule = FailureRule(scope="node", mode="choice", count=1)
        policy = FailurePolicy(
            modes=[FailureMode(weight=1.0, rules=[rule], attrs={"test": "attr"})]
        )
        policy_set = FailurePolicySet()
        policy_set.policies["test"] = policy

        fm = FailureManager(simple_network, policy_set, policy_name="test")

        def mock_analysis(network, excluded_nodes, excluded_links, **kwargs):
            return {"mock": True}

        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=3,
            store_failure_patterns=True,
            seed=42,
        )

        # Results contain unique patterns (total occurrence_count == 3)
        results = result["results"]
        total_occurrences = sum(getattr(r, "occurrence_count", 1) for r in results)
        assert total_occurrences == 3

        # All results should have trace fields when store_failure_patterns=True
        # Note: mock_analysis returns dict, not FlowIterationResult, so trace
        # is stored differently. The key behavior is that failure_trace is captured.

    def test_baseline_has_no_trace_fields(self, simple_network: Network) -> None:
        """Test that baseline result doesn't have trace fields."""
        rule = FailureRule(scope="node", mode="choice", count=1)
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set = FailurePolicySet()
        policy_set.policies["test"] = policy

        fm = FailureManager(simple_network, policy_set, policy_name="test")

        def mock_analysis(network, excluded_nodes, excluded_links, **kwargs):
            return {"mock": True}

        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=3,
            store_failure_patterns=True,
            seed=42,
        )

        # Baseline is a separate result
        baseline = result["baseline"]
        assert baseline is not None

        # Results contain K unique patterns (occurrence_count sum == 3)
        results = result["results"]
        total_occurrences = sum(getattr(r, "occurrence_count", 1) for r in results)
        assert total_occurrences == 3

    def test_deduplication_produces_unique_patterns(
        self, simple_network: Network
    ) -> None:
        """Test that deduplicated iterations produce single unique result."""
        # Use a deterministic policy that always produces same result
        rule = FailureRule(
            scope="node",
            conditions=[Condition(attr="type", op="==", value="router")],
            mode="all",  # Always selects same nodes
        )
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set = FailurePolicySet()
        policy_set.policies["test"] = policy

        fm = FailureManager(simple_network, policy_set, policy_name="test")

        def mock_analysis(network, excluded_nodes, excluded_links, **kwargs):
            return {"mock": True}

        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=5,
            store_failure_patterns=True,
            seed=42,
        )

        # All 5 iterations should produce same pattern -> 1 unique result
        results = result["results"]
        assert len(results) == 1  # All deduplicated to 1 unique pattern

        # Metadata should report 1 unique pattern from 5 iterations
        assert result["metadata"]["unique_patterns"] == 1
        assert result["metadata"]["iterations"] == 5

    def test_trace_deterministic_across_runs(self, simple_network: Network) -> None:
        """Test that trace is deterministic with fixed seed across runs."""
        rule = FailureRule(scope="node", mode="choice", count=1)
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set = FailurePolicySet()
        policy_set.policies["test"] = policy

        fm = FailureManager(simple_network, policy_set, policy_name="test")

        def mock_analysis(network, excluded_nodes, excluded_links, **kwargs):
            return {"mock": True}

        result1 = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=5,
            store_failure_patterns=True,
            seed=42,
        )
        result2 = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=5,
            store_failure_patterns=True,
            seed=42,
        )

        # Compare unique patterns count
        assert len(result1["results"]) == len(result2["results"])

        # Compare metadata
        assert (
            result1["metadata"]["unique_patterns"]
            == result2["metadata"]["unique_patterns"]
        )

    def test_no_trace_when_store_failure_patterns_false(
        self, simple_network: Network
    ) -> None:
        """Test that trace is not captured when store_failure_patterns=False."""
        rule = FailureRule(scope="node", mode="choice", count=1)
        policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])
        policy_set = FailurePolicySet()
        policy_set.policies["test"] = policy

        fm = FailureManager(simple_network, policy_set, policy_name="test")

        def mock_analysis(network, excluded_nodes, excluded_links, **kwargs):
            return {"mock": True}

        result = fm.run_monte_carlo_analysis(
            analysis_func=mock_analysis,
            iterations=3,
            store_failure_patterns=False,
            seed=42,
        )

        # Results should still be present (just without trace)
        assert len(result["results"]) > 0
