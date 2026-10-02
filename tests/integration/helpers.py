"""
Helpers for scenario-based integration tests.

- NetworkExpectations: expected node/edge counts and named elements
- ScenarioTestHelper: validation methods over a scenario and its built graph
- ScenarioDataBuilder: programmatic construction of scenario YAML
- load_scenario_from_file, create_scenario_helper: loading and setup
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ngraph.scenario import Scenario

# Validation constants
DEFAULT_LINK_COST = 1  # Default cost value for validation
MIN_CAPACITY_VALUE = 0.0  # Minimum valid capacity (inclusive)
MIN_COST_VALUE = 0.0  # Minimum valid cost (inclusive)

# Network validation thresholds
MAX_EXPECTED_COMPONENTS_WARNING = 1  # Warn if more than this many components


@dataclass
class NetworkExpectations:
    """
    Expected characteristics of a network after scenario processing.

    Attributes:
        count: Expected total number of nodes in the final network
        edge_count: Expected total number of directed edges (links * 2 for bidirectional)
        specific_nodes: Set of specific node names that must be present
        specific_links: List of (source, target) tuples that must exist as links
        blueprint_expansions: Dict mapping blueprint paths to expected node counts
    """

    count: int
    edge_count: int
    specific_nodes: Optional[Set[str]] = None
    specific_links: Optional[List[Tuple[str, str]]] = None
    blueprint_expansions: Optional[Dict[str, int]] = None

    def __post_init__(self) -> None:
        """Replace None optional fields with empty containers."""
        if self.specific_nodes is None:
            self.specific_nodes = set()
        if self.specific_links is None:
            self.specific_links = []
        if self.blueprint_expansions is None:
            self.blueprint_expansions = {}


class ScenarioTestHelper:
    """
    Validation methods for a scenario and its built graph.

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
        self.graph: Optional[Any] = None

    def set_graph(self, graph: Any) -> None:
        """
        Set the built graph for validation operations.

        Args:
            graph: NetworkX graph produced by BuildGraph workflow step
        """
        self.graph = graph

    def validate_network_structure(self, expectations: NetworkExpectations) -> None:
        """
        Validate that basic network structure matches expectations.

        Checks node count, edge count, and the presence of specific nodes and links.

        Args:
            expectations: Expected network characteristics to validate against

        Raises:
            AssertionError: If any structural expectation is not met
        """
        if self.graph is None:
            raise ValueError("Graph must be set before validation using set_graph()")

        actual_nodes = len(self.graph.nodes)
        assert actual_nodes == expectations.count, (
            f"Network node count mismatch: expected {expectations.count}, "
            f"found {actual_nodes}. "
            f"Graph nodes: {sorted(list(self.graph.nodes)[:10])}{'...' if actual_nodes > 10 else ''}"
        )

        actual_edges = len(self.graph.edges)
        assert actual_edges == expectations.edge_count, (
            f"Network edge count mismatch: expected {expectations.edge_count}, "
            f"found {actual_edges}. "
            f"Note: NetGraph typically creates bidirectional edges (physical_links * 2)"
        )

        self._validate_specific_nodes(expectations.specific_nodes)
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

        Counts the nodes whose name starts with each blueprint path.

        Args:
            expectations: Network expectations containing blueprint expansion counts

        Raises:
            AssertionError: If blueprint expansion counts don't match expectations
        """
        if not expectations.blueprint_expansions:
            return

        for blueprint_path, expected_count in expectations.blueprint_expansions.items():
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
        default_demands = self.scenario.demand_set.get_all_demands()
        actual_count = len(default_demands)

        assert actual_count == expected_count, (
            f"Traffic demand count mismatch: expected {expected_count}, found {actual_count}. "
            f"Demands: {[(d.source, d.target, d.volume) for d in default_demands[:5]]}"
            f"{'...' if actual_count > 5 else ''}"
        )

    def validate_failure_policy(
        self,
        expected_rules: int,
        expected_scopes: Optional[List[str]] = None,
    ) -> None:
        """
        Validate failure policy configuration.

        Args:
            expected_rules: Expected number of failure rules
            expected_scopes: Optional list of expected rule scopes (node/link)

        Raises:
            AssertionError: If failure policy doesn't match expectations
        """
        # Get the first policy if any exist for validation
        policies = self.scenario.failure_policy_set.get_all_policies()
        policy = policies[0] if policies else None

        if policy is None:
            # No policy exists - only valid if expecting zero rules
            assert expected_rules == 0, (
                f"Expected a failure policy with {expected_rules} rules, but no default policy found"
            )
            return

        # Count rules across all modes
        actual_rules = sum(len(mode.rules) for mode in getattr(policy, "modes", []))
        assert actual_rules == expected_rules, (
            f"Failure policy rule count mismatch: expected {expected_rules}, found {actual_rules}"
        )

        if expected_scopes:
            actual_scopes = [
                rule.scope
                for mode in getattr(policy, "modes", [])
                for rule in mode.rules
            ]
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

    def validate_topology_semantics(self) -> None:
        """
        Check edge attributes and report topology warnings.

        Asserts that every edge has non-negative capacity and cost. Self-loops
        and multiple weakly connected components are printed as warnings, not
        failures.

        Raises:
            AssertionError: If an edge has negative capacity or cost
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

        self._validate_edge_attributes()

    def _validate_network_connectivity(self) -> None:
        """Print a warning when the graph is not weakly connected."""
        import networkx as nx

        assert self.graph is not None, (
            "Graph must be set before connectivity validation"
        )

        is_connected = nx.is_weakly_connected(self.graph)
        if not is_connected:
            components = list(nx.weakly_connected_components(self.graph))
            if len(components) > MAX_EXPECTED_COMPONENTS_WARNING:
                print(
                    f"Warning: Network has {len(components)} weakly connected components. "
                    f"This might indicate network fragmentation."
                )

    def _validate_edge_attributes(self) -> None:
        """Assert non-negative capacity and cost on every edge."""
        assert self.graph is not None, (
            "Graph must be set before edge attribute validation"
        )

        invalid_edges = []

        for u, v, key, data in self.graph.edges(keys=True, data=True):
            capacity = data.get("capacity", 0)
            cost = data.get("cost", 0)

            if capacity < MIN_CAPACITY_VALUE:
                invalid_edges.append(
                    f"Edge ({u}, {v}, {key}) has invalid capacity: {capacity}"
                )

            if cost < MIN_COST_VALUE:
                invalid_edges.append(f"Edge ({u}, {v}, {key}) has invalid cost: {cost}")

        assert not invalid_edges, (
            f"Found {len(invalid_edges)} edges with invalid attributes:\n"
            + "\n".join(invalid_edges[:5])
            + ("..." if len(invalid_edges) > 5 else "")
        )


class ScenarioDataBuilder:
    """
    Fluent builder for scenario YAML data used in tests.

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
            "failures": {},
            "demands": {},
            "workflow": [],
        }

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
                    "capacity": capacity,
                    "cost": DEFAULT_LINK_COST,
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
        self, source: str, target: str, volume: float, demand_set: str = "default"
    ) -> "ScenarioDataBuilder":
        """
        Add a traffic demand to the named demand set.

        Args:
            source: Source node/pattern for traffic demand
            target: Target node/pattern for traffic demand
            volume: Traffic demand volume
            demand_set: Name of the demand set (default: "default")

        Returns:
            Self for method chaining
        """
        if demand_set not in self.data["demands"]:
            self.data["demands"][demand_set] = []

        self.data["demands"][demand_set].append(
            {"source": source, "target": target, "volume": volume}
        )
        return self

    def with_failure_policy(
        self, name: str, policy_data: Dict[str, Any]
    ) -> "ScenarioDataBuilder":
        """
        Add a failure policy to the scenario.

        Args:
            name: Policy name under the scenario's ``failures`` section
            policy_data: Policy configuration dictionary

        Returns:
            Self for method chaining
        """
        self.data["failures"][name] = policy_data
        return self

    def with_workflow_step(
        self, type: str, name: str, **kwargs
    ) -> "ScenarioDataBuilder":
        """
        Add a workflow step to the scenario execution plan.

        Args:
            type: Type of workflow step (e.g., "BuildGraph", "MaxFlow")
            name: Unique name for this step instance
            **kwargs: Additional step-specific parameters

        Returns:
            Self for method chaining
        """
        step_data = {"type": type, "name": name}
        step_data.update(kwargs)
        self.data["workflow"].append(step_data)
        return self

    def build_yaml(self) -> str:
        """
        Build YAML string from scenario data.

        Prepends a BuildGraph step when the workflow is non-empty and lacks one.

        Returns:
            YAML string representation of the scenario
        """
        import yaml

        workflow_steps = self.data.get("workflow", [])
        if workflow_steps and not any(
            step.get("type") == "BuildGraph" for step in workflow_steps
        ):
            workflow_steps.insert(0, {"type": "BuildGraph", "name": "build_graph"})
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
    import networkx as nx

    helper = ScenarioTestHelper(scenario)
    exported = scenario.results.to_dict()

    graph_dict = (
        exported.get("steps", {}).get("build_graph", {}).get("data", {}).get("graph")
    )
    if isinstance(graph_dict, dict):
        # Convert node-link dict format to NetworkX graph using built-in function
        graph = nx.node_link_graph(graph_dict, edges="edges")
    else:
        graph = graph_dict
    helper.set_graph(graph)
    return helper
