"""
Test helpers for scenario-based integration testing.

This module provides reusable utilities for validating NetGraph scenarios,
creating test data, and performing semantic correctness checks on network
topologies and flow results.

Key Components:
- NetworkExpectations: Structured expectations for network validation
- ScenarioTestHelper: Main validation class with modular test methods
- ScenarioDataBuilder: Builder pattern for programmatic scenario creation
- Utility functions: File loading, helper creation, and pytest fixtures

The validation approach emphasizes:
- Modular, focused validation methods
- Clear error messages with context
- Semantic correctness beyond simple counts
- Reusable patterns for common test scenarios
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.scenario import Scenario

# Validation constants for test consistency
DEFAULT_FLOW_TOLERANCE = 1e-9  # Default tolerance for flow value comparisons
MIN_CONNECTIVITY_COMPONENTS = (
    1  # Expected minimum connected components for valid networks
)
DEFAULT_LINK_COST = 1  # Default cost value for validation
MIN_CAPACITY_VALUE = 0.0  # Minimum valid capacity (inclusive)
MIN_COST_VALUE = 0.0  # Minimum valid cost (inclusive)

# Network validation thresholds
MAX_EXPECTED_COMPONENTS_WARNING = 1  # Warn if more than this many components
LARGE_NETWORK_NODE_THRESHOLD = 1000  # Threshold for "large network" optimizations


@dataclass
class NetworkExpectations:
    """
    Expected characteristics of a network after scenario processing.

    This dataclass encapsulates all the expected properties that should be
    validated after a scenario runs, including structural properties,
    specific network elements, and blueprint expansion results.

    Attributes:
        node_count: Expected total number of nodes in the final network
        edge_count: Expected total number of directed edges (links * 2 for bidirectional)
        specific_nodes: Set of specific node names that must be present
        specific_links: List of (source, target) tuples that must exist as links
        blueprint_expansions: Dict mapping blueprint paths to expected node counts
    """

    node_count: int
    edge_count: int
    specific_nodes: Optional[Set[str]] = None
    specific_links: Optional[List[Tuple[str, str]]] = None
    blueprint_expansions: Optional[Dict[str, int]] = None

    def __post_init__(self) -> None:
        """Initialize default values for optional fields to prevent None access."""
        if self.specific_nodes is None:
            self.specific_nodes = set()
        if self.specific_links is None:
            self.specific_links = []
        if self.blueprint_expansions is None:
            self.blueprint_expansions = {}


@dataclass
class ScenarioValidationConfig:
    """
    Configuration options for controlling scenario validation behavior.

    This allows tests to selectively enable/disable different types of validation
    based on the specific requirements of each test scenario.

    Attributes:
        validate_topology: Whether to perform basic topology validation
        validate_flows: Whether to validate flow calculation results
        validate_attributes: Whether to check node/link attribute correctness
        validate_semantics: Whether to perform deep semantic validation
        check_risk_groups: Whether to validate risk group assignments
        check_disabled_elements: Whether to check for disabled nodes/links
    """

    validate_topology: bool = True
    validate_flows: bool = True
    validate_attributes: bool = True
    validate_semantics: bool = True
    check_risk_groups: bool = True
    check_disabled_elements: bool = True


class ScenarioTestHelper:
    """
    Helper class for scenario testing with modular validation utilities.

    This class provides a high-level interface for validating NetGraph scenarios,
    encapsulating common validation patterns and providing clear error messages.
    It follows the builder pattern for configurable validation.

    Usage:
        helper = ScenarioTestHelper(scenario)
        helper.set_graph(built_graph)
        helper.validate_network_structure(expectations)
        helper.validate_topology_semantics()
    """

    def __init__(self, scenario: Scenario) -> None:
        """
        Initialize helper with a scenario instance.

        Args:
            scenario: NetGraph scenario instance to validate
        """
        self.scenario = scenario
        self.network = scenario.network
        self.graph: Optional[StrictMultiDiGraph] = None

    def set_graph(self, graph: StrictMultiDiGraph) -> None:
        """
        Set the built graph for validation operations.

        Args:
            graph: NetworkX graph produced by BuildGraph workflow step
        """
        self.graph = graph

    def validate_network_structure(self, expectations: NetworkExpectations) -> None:
        """
        Validate that basic network structure matches expectations.

        Performs fundamental structural validation including node count, edge count,
        and presence of specific network elements. This is typically the first
        validation performed after scenario execution.

        Args:
            expectations: Expected network characteristics to validate against

        Raises:
            AssertionError: If any structural expectation is not met
        """
        if self.graph is None:
            raise ValueError("Graph must be set before validation using set_graph()")

        # Validate node count with detailed context
        actual_nodes = len(self.graph.nodes)
        assert actual_nodes == expectations.node_count, (
            f"Network node count mismatch: expected {expectations.node_count}, "
            f"found {actual_nodes}. "
            f"Graph nodes: {sorted(list(self.graph.nodes)[:10])}{'...' if actual_nodes > 10 else ''}"
        )

        # Validate edge count with bidirectional context
        actual_edges = len(self.graph.edges)
        assert actual_edges == expectations.edge_count, (
            f"Network edge count mismatch: expected {expectations.edge_count}, "
            f"found {actual_edges}. "
            f"Note: NetGraph typically creates bidirectional edges (physical_links * 2)"
        )

        # Validate presence of specific nodes
        self._validate_specific_nodes(expectations.specific_nodes)

        # Validate presence of specific links
        self._validate_specific_links(expectations.specific_links)

    def _validate_specific_nodes(self, expected_nodes: Optional[Set[str]]) -> None:
        """Validate that specific expected nodes exist in the network."""
        if not expected_nodes:
            return

        missing_nodes = expected_nodes - set(self.network.nodes.keys())
        assert not missing_nodes, (
            f"Expected nodes missing from network: {missing_nodes}. "
            f"Available nodes: {sorted(list(self.network.nodes.keys())[:20])}"
        )

    def _validate_specific_links(
        self, expected_links: Optional[List[Tuple[str, str]]]
    ) -> None:
        """Validate that specific expected links exist in the network."""
        if not expected_links:
            return

        for source, target in expected_links:
            links = self.network.find_links(
                source_regex=f"^{source}$", target_regex=f"^{target}$"
            )
            assert len(links) > 0, (
                f"Expected link from '{source}' to '{target}' not found. "
                f"Available links from {source}: "
                f"{[link.target for link in self.network.find_links(source_regex=f'^{source}$')]}"
            )

    def validate_blueprint_expansions(self, expectations: NetworkExpectations) -> None:
        """
        Validate that blueprint expansions created expected node counts.

        This method checks that NetGraph's blueprint expansion mechanism
        produced the correct number of nodes for each blueprint pattern.

        Args:
            expectations: Network expectations containing blueprint expansion counts

        Raises:
            AssertionError: If blueprint expansion counts don't match expectations
        """
        if not expectations.blueprint_expansions:
            return

        for blueprint_path, expected_count in expectations.blueprint_expansions.items():
            # Find all nodes matching the blueprint path pattern
            matching_nodes = [
                node for node in self.network.nodes if node.startswith(blueprint_path)
            ]
            actual_count = len(matching_nodes)

            assert actual_count == expected_count, (
                f"Blueprint expansion '{blueprint_path}' count mismatch: "
                f"expected {expected_count}, found {actual_count}. "
                f"Matching nodes: {sorted(matching_nodes)[:10]}{'...' if actual_count > 10 else ''}"
            )

    def validate_traffic_demands(self, expected_count: int) -> None:
        """
        Validate traffic demand configuration.

        Args:
            expected_count: Expected number of traffic demands

        Raises:
            AssertionError: If traffic demand count doesn't match expectations
        """
        default_demands = self.scenario.traffic_matrix_set.get_default_matrix()
        actual_count = len(default_demands)

        assert actual_count == expected_count, (
            f"Traffic demand count mismatch: expected {expected_count}, found {actual_count}. "
            f"Demands: {[(d.source_path, d.sink_path, d.demand) for d in default_demands[:5]]}"
            f"{'...' if actual_count > 5 else ''}"
        )

    def validate_failure_policy(
        self,
        expected_name: Optional[str],
        expected_rules: int,
        expected_scopes: Optional[List[str]] = None,
    ) -> None:
        """
        Validate failure policy configuration.

        Args:
            expected_name: Expected failure policy name (None if no policy expected)
            expected_rules: Expected number of failure rules
            expected_scopes: Optional list of expected rule scopes (node/link)

        Raises:
            AssertionError: If failure policy doesn't match expectations
        """
        policy = self.scenario.failure_policy_set.get_default_policy()

        if expected_name is None:
            assert policy is None, (
                f"Expected no default failure policy, but found: {policy.attrs.get('name') if policy else None}"
            )
            return

        assert policy is not None, "Expected a default failure policy but none found"

        # Validate rule count
        actual_rules = len(policy.rules)
        assert actual_rules == expected_rules, (
            f"Failure policy rule count mismatch: expected {expected_rules}, found {actual_rules}"
        )

        # Validate policy name
        actual_name = policy.attrs.get("name")
        assert actual_name == expected_name, (
            f"Failure policy name mismatch: expected '{expected_name}', found '{actual_name}'"
        )

        # Validate rule scopes if specified
        if expected_scopes:
            actual_scopes = [rule.entity_scope for rule in policy.rules]
            assert set(actual_scopes) == set(expected_scopes), (
                f"Failure policy scopes mismatch: expected {expected_scopes}, found {actual_scopes}"
            )

    def validate_node_attributes(
        self, node_name: str, expected_attrs: Dict[str, Any]
    ) -> None:
        """
        Validate specific node attributes.

        Args:
            node_name: Name of the node to validate
            expected_attrs: Dictionary of expected attribute name -> value pairs

        Raises:
            AssertionError: If node attributes don't match expectations
        """
        assert node_name in self.network.nodes, (
            f"Node '{node_name}' not found in network"
        )
        node = self.network.nodes[node_name]

        for attr_name, expected_value in expected_attrs.items():
            if attr_name == "risk_groups":
                # Risk groups are handled specially as they're sets
                actual_value = node.risk_groups
                assert actual_value == expected_value, (
                    f"Node '{node_name}' risk_groups mismatch: "
                    f"expected {expected_value}, found {actual_value}"
                )
            else:
                # Regular attributes stored in attrs dictionary
                actual_value = node.attrs.get(attr_name)
                assert actual_value == expected_value, (
                    f"Node '{node_name}' attribute '{attr_name}' mismatch: "
                    f"expected {expected_value}, found {actual_value}"
                )

    def validate_link_attributes(
        self, source_pattern: str, target_pattern: str, expected_attrs: Dict[str, Any]
    ) -> None:
        """
        Validate attributes on links matching the given patterns.

        Args:
            source_pattern: Regex pattern for source nodes
            target_pattern: Regex pattern for target nodes
            expected_attrs: Dictionary of expected attribute name -> value pairs

        Raises:
            AssertionError: If link attributes don't match expectations
        """
        links = self.network.find_links(
            source_regex=source_pattern, target_regex=target_pattern
        )
        assert len(links) > 0, (
            f"No links found matching '{source_pattern}' -> '{target_pattern}'"
        )

        for link in links:
            for attr_name, expected_value in expected_attrs.items():
                if attr_name == "capacity":
                    actual_value = link.capacity
                elif attr_name == "risk_groups":
                    actual_value = link.risk_groups
                else:
                    actual_value = link.attrs.get(attr_name)

                assert actual_value == expected_value, (
                    f"Link {link.id} ({link.source} -> {link.target}) "
                    f"attribute '{attr_name}' mismatch: "
                    f"expected {expected_value}, found {actual_value}"
                )

    def validate_flow_results(
        self,
        step_name: str,
        flow_label: str,
        expected_flow: float,
        tolerance: float = DEFAULT_FLOW_TOLERANCE,
    ) -> None:
        """
        Validate flow calculation results.

        Args:
            step_name: Name of the workflow step that produced the flow
            flow_label: Label identifying the specific flow result
            expected_flow: Expected flow value
            tolerance: Numerical tolerance for flow comparison

        Raises:
            AssertionError: If flow results don't match expectations within tolerance
        """
        actual_flow = self.scenario.results.get(step_name, flow_label)
        assert actual_flow is not None, (
            f"Flow result '{flow_label}' not found for step '{step_name}'"
        )

        flow_difference = abs(actual_flow - expected_flow)
        assert flow_difference <= tolerance, (
            f"Flow value mismatch for '{flow_label}': "
            f"expected {expected_flow}, found {actual_flow} "
            f"(difference: {flow_difference}, tolerance: {tolerance})"
        )

    def validate_topology_semantics(self) -> None:
        """
        Validate semantic correctness of network topology.

        Performs deep validation of network properties including:
        - Edge attribute validity (non-negative capacity/cost)
        - Self-loop detection and reporting
        - Basic connectivity analysis
        - Structural consistency checks

        Raises:
            AssertionError: If semantic validation fails
        """
        if self.graph is None:
            raise ValueError("Graph must be set before topology validation")

        # Check for self-loops (may be valid in some topologies)
        self_loops = [(u, v) for u, v in self.graph.edges() if u == v]
        if self_loops:
            # Log warning but don't fail - self-loops might be intentional
            print(f"Warning: Found {len(self_loops)} self-loop edges: {self_loops[:5]}")

        # Analyze connectivity for multi-node networks
        if len(self.graph.nodes) > 1:
            self._validate_network_connectivity()

        # Validate edge attributes for semantic correctness
        self._validate_edge_attributes()

    def _validate_network_connectivity(self) -> None:
        """Validate network connectivity properties."""
        import networkx as nx

        # Ensure graph is available for connectivity checks
        assert self.graph is not None, (
            "Graph must be set before connectivity validation"
        )

        # Check weak connectivity for directed graphs
        is_connected = nx.is_weakly_connected(self.graph)
        if not is_connected:
            components = list(nx.weakly_connected_components(self.graph))
            if len(components) > MAX_EXPECTED_COMPONENTS_WARNING:
                print(
                    f"Warning: Network has {len(components)} weakly connected components. "
                    f"This might indicate network fragmentation."
                )

    def _validate_edge_attributes(self) -> None:
        """Validate edge attributes for semantic correctness."""
        # Ensure graph is available for edge validation
        assert self.graph is not None, (
            "Graph must be set before edge attribute validation"
        )

        invalid_edges = []

        for u, v, key, data in self.graph.edges(keys=True, data=True):
            capacity = data.get("capacity", 0)
            cost = data.get("cost", 0)

            # Check for invalid capacity values
            if capacity < MIN_CAPACITY_VALUE:
                invalid_edges.append(
                    f"Edge ({u}, {v}, {key}) has invalid capacity: {capacity}"
                )

            # Check for invalid cost values
            if cost < MIN_COST_VALUE:
                invalid_edges.append(f"Edge ({u}, {v}, {key}) has invalid cost: {cost}")

        assert not invalid_edges, (
            f"Found {len(invalid_edges)} edges with invalid attributes:\n"
            + "\n".join(invalid_edges[:5])
            + ("..." if len(invalid_edges) > 5 else "")
        )

    def validate_flow_conservation(self, flow_results: Dict[str, float]) -> None:
        """
        Validate that flow results satisfy basic conservation principles.

        Args:
            flow_results: Dictionary mapping flow labels to flow values

        Raises:
            AssertionError: If flow conservation principles are violated
        """
        # Check for negative flows (usually invalid)
        negative_flows = {
            label: flow for label, flow in flow_results.items() if flow < 0
        }
        assert not negative_flows, (
            f"Found negative flows (usually invalid): {negative_flows}"
        )

        # Check self-loop flows (should typically be zero)
        self_loop_flows = {
            label: flow
            for label, flow in flow_results.items()
            if "->" in label
            and label.split("->")[0].strip() == label.split("->")[1].strip()
        }

        for label, flow in self_loop_flows.items():
            assert flow == 0.0, f"Self-loop flow should be zero: {label} = {flow}"


class ScenarioDataBuilder:
    """
    Builder pattern implementation for creating test scenario data.

    This class provides a fluent interface for programmatically constructing
    NetGraph scenario YAML data with composable components. It simplifies
    the creation of test scenarios by providing convenient methods for
    common network elements.

    Usage:
        builder = ScenarioDataBuilder()
        scenario = (builder
            .with_simple_nodes(["A", "B", "C"])
            .with_simple_links([("A", "B", 10), ("B", "C", 20)])
            .with_workflow_step("BuildGraph", "build_graph")
            .build_scenario())
    """

    def __init__(self) -> None:
        """Initialize empty scenario data with basic structure."""
        self.data: Dict[str, Any] = {
            "network": {},
            "failure_policy_set": {},
            "traffic_matrix_set": {},
            "workflow": [],
        }

    def with_seed(self, seed: int) -> "ScenarioDataBuilder":
        """
        Add deterministic seed to scenario for reproducible results.

        Args:
            seed: Random seed value for scenario execution

        Returns:
            Self for method chaining
        """
        self.data["seed"] = seed
        return self

    def with_simple_nodes(self, node_names: List[str]) -> "ScenarioDataBuilder":
        """
        Add simple nodes to the network without any special attributes.

        Args:
            node_names: List of node names to create

        Returns:
            Self for method chaining
        """
        if "nodes" not in self.data["network"]:
            self.data["network"]["nodes"] = {}

        for name in node_names:
            self.data["network"]["nodes"][name] = {}
        return self

    def with_simple_links(
        self, links: List[Tuple[str, str, float]]
    ) -> "ScenarioDataBuilder":
        """
        Add simple bidirectional links to the network.

        Args:
            links: List of (source, target, capacity) tuples

        Returns:
            Self for method chaining
        """
        if "links" not in self.data["network"]:
            self.data["network"]["links"] = []

        for source, target, capacity in links:
            self.data["network"]["links"].append(
                {
                    "source": source,
                    "target": target,
                    "link_params": {"capacity": capacity, "cost": DEFAULT_LINK_COST},
                }
            )
        return self

    def with_blueprint(
        self, name: str, blueprint_data: Dict[str, Any]
    ) -> "ScenarioDataBuilder":
        """
        Add a network blueprint definition to the scenario.

        Args:
            name: Blueprint name for later reference
            blueprint_data: Blueprint configuration dictionary

        Returns:
            Self for method chaining
        """
        if "blueprints" not in self.data:
            self.data["blueprints"] = {}
        self.data["blueprints"][name] = blueprint_data
        return self

    def with_traffic_demand(
        self, source: str, sink: str, demand: float, matrix_name: str = "default"
    ) -> "ScenarioDataBuilder":
        """
        Add a traffic demand to the specified traffic matrix.

        Args:
            source: Source node/pattern for traffic demand
            sink: Sink node/pattern for traffic demand
            demand: Traffic demand value
            matrix_name: Name of traffic matrix (default: "default")

        Returns:
            Self for method chaining
        """
        if matrix_name not in self.data["traffic_matrix_set"]:
            self.data["traffic_matrix_set"][matrix_name] = []

        self.data["traffic_matrix_set"][matrix_name].append(
            {"source_path": source, "sink_path": sink, "demand": demand}
        )
        return self

    def with_failure_policy(
        self, name: str, policy_data: Dict[str, Any], policy_name: str = "default"
    ) -> "ScenarioDataBuilder":
        """
        Add a failure policy to the scenario.

        Args:
            name: Human-readable name for the policy
            policy_data: Policy configuration dictionary
            policy_name: Internal policy identifier (default: "default")

        Returns:
            Self for method chaining
        """
        self.data["failure_policy_set"][policy_name] = policy_data
        return self

    def with_workflow_step(
        self, step_type: str, name: str, **kwargs
    ) -> "ScenarioDataBuilder":
        """
        Add a workflow step to the scenario execution plan.

        Args:
            step_type: Type of workflow step (e.g., "BuildGraph", "CapacityProbe")
            name: Unique name for this step instance
            **kwargs: Additional step-specific parameters

        Returns:
            Self for method chaining
        """
        step_data = {"step_type": step_type, "name": name}
        step_data.update(kwargs)
        self.data["workflow"].append(step_data)
        return self

    def build_yaml(self) -> str:
        """
        Build YAML string from scenario data.

        Automatically ensures that a BuildGraph workflow step is included
        if workflow exists but lacks one.

        Returns:
            YAML string representation of the scenario
        """
        import yaml

        # Ensure BuildGraph workflow step is included if workflow exists but lacks one
        workflow_steps = self.data.get("workflow", [])
        if workflow_steps and not any(
            step.get("step_type") == "BuildGraph" for step in workflow_steps
        ):
            workflow_steps.insert(0, {"step_type": "BuildGraph", "name": "build_graph"})
            self.data["workflow"] = workflow_steps

        return yaml.dump(self.data, default_flow_style=False)

    def build_scenario(self) -> Scenario:
        """
        Build NetGraph Scenario object from accumulated data.

        Returns:
            Configured Scenario instance ready for execution
        """
        yaml_content = self.build_yaml()
        return Scenario.from_yaml(yaml_content)


# Utility functions for common operations


def load_scenario_from_file(filename: str) -> Scenario:
    """
    Load a scenario from a YAML file in the integration directory.

    Args:
        filename: Name of YAML file to load (e.g., "scenario_1.yaml")

    Returns:
        Loaded Scenario instance

    Raises:
        FileNotFoundError: If the scenario file doesn't exist
    """
    scenario_path = Path(__file__).parent / filename
    if not scenario_path.exists():
        raise FileNotFoundError(f"Scenario file not found: {scenario_path}")

    yaml_text = scenario_path.read_text()
    return Scenario.from_yaml(yaml_text)


def create_scenario_helper(scenario: Scenario) -> ScenarioTestHelper:
    """
    Create a test helper for the given scenario.

    Args:
        scenario: NetGraph scenario instance

    Returns:
        Configured ScenarioTestHelper instance
    """
    return ScenarioTestHelper(scenario)


# Pytest fixtures for common test data and patterns


@pytest.fixture
def scenario_builder() -> ScenarioDataBuilder:
    """Pytest fixture providing a fresh scenario data builder."""
    return ScenarioDataBuilder()


@pytest.fixture
def minimal_scenario() -> Scenario:
    """Pytest fixture providing a minimal valid scenario for testing."""
    return (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B", "C"])
        .with_simple_links([("A", "B", 10), ("B", "C", 20)])
        .with_workflow_step("BuildGraph", "build_graph")
        .build_scenario()
    )


@pytest.fixture
def basic_failure_scenario() -> Scenario:
    """Pytest fixture providing a scenario with failure policies configured."""
    builder = (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B", "C"])
        .with_simple_links([("A", "B", 10), ("B", "C", 20)])
        .with_failure_policy(
            "single_link_failure",
            {
                "attrs": {"name": "single_link", "description": "Single link failure"},
                "rules": [{"entity_scope": "link", "rule_type": "choice", "count": 1}],
            },
        )
        .with_workflow_step("BuildGraph", "build_graph")
    )
    return builder.build_scenario()
