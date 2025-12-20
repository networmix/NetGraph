"""
Modular test data templates and components for scenario testing.

This module provides reusable, composable templates for creating NetGraph
test scenarios with consistent patterns. The templates reduce code duplication,
improve test maintainability, and enable rapid creation of test scenarios.

Key Template Categories:
- NetworkTemplates: Common network topologies (linear, star, mesh, ring, tree)
- BlueprintTemplates: Reusable blueprint patterns for hierarchies
- FailurePolicyTemplates: Standard failure scenario configurations
- TrafficDemandTemplates: Traffic demand patterns and distributions
- WorkflowTemplates: Common analysis workflow configurations
- ScenarioTemplateBuilder: High-level builder for complete scenarios
- CommonScenarios: Pre-built scenarios for typical use cases

Design Principles:
- Composability: Templates can be combined and layered
- Parameterization: All templates accept configuration parameters
- Consistency: Similar interfaces across all template types
- Reusability: Templates can be used across multiple test scenarios
- Maintainability: Centralized definitions reduce duplication

Usage Patterns:
1. Basic topology creation with NetworkTemplates
2. Hierarchies with BlueprintTemplates
3. Complete scenarios with ScenarioTemplateBuilder
4. Quick test setups with CommonScenarios
"""

from typing import Any, Dict, List, Optional

from .helpers import ScenarioDataBuilder

# Template configuration constants for consistent testing
DEFAULT_LINK_CAPACITY = 10.0  # Default capacity for template-generated links
DEFAULT_LINK_COST = 1  # Default cost for template-generated links
DEFAULT_TRAFFIC_DEMAND = 1.0  # Default traffic demand value
DEFAULT_BLUEPRINT_CAPACITY = 10.0  # Default capacity for blueprint links

# Network template size limits for safety
MAX_MESH_NODES = 20  # Prevent accidentally creating huge meshes
MAX_TREE_DEPTH = 10  # Prevent deep recursion in tree generation
MAX_BRANCHING_FACTOR = 20  # Prevent excessive tree branching


class NetworkTemplates:
    """Templates for common network topologies."""

    @staticmethod
    def linear_network(
        node_names: List[str], link_capacity: float = 10.0
    ) -> Dict[str, Any]:
        """Create a linear network topology (A-B-C-D...)."""
        network_data = {"nodes": {name: {} for name in node_names}, "links": []}

        for i in range(len(node_names) - 1):
            network_data["links"].append(
                {
                    "source": node_names[i],
                    "target": node_names[i + 1],
                    "link_params": {"capacity": link_capacity, "cost": 1},
                }
            )

        return network_data

    @staticmethod
    def star_network(
        center_node: str, leaf_nodes: List[str], link_capacity: float = 10.0
    ) -> Dict[str, Any]:
        """Create a star network topology (center node connected to all leaf nodes)."""
        all_nodes = [center_node] + leaf_nodes
        network_data = {"nodes": {name: {} for name in all_nodes}, "links": []}

        for leaf in leaf_nodes:
            network_data["links"].append(
                {
                    "source": center_node,
                    "target": leaf,
                    "link_params": {"capacity": link_capacity, "cost": 1},
                }
            )

        return network_data

    @staticmethod
    def mesh_network(
        node_names: List[str], link_capacity: float = 10.0
    ) -> Dict[str, Any]:
        """Create a full mesh network topology (all nodes connected to all others)."""
        network_data = {"nodes": {name: {} for name in node_names}, "links": []}

        for i, source in enumerate(node_names):
            for j, target in enumerate(node_names):
                if i != j:  # Skip self-loops
                    network_data["links"].append(
                        {
                            "source": source,
                            "target": target,
                            "link_params": {"capacity": link_capacity, "cost": 1},
                        }
                    )

        return network_data

    @staticmethod
    def ring_network(
        node_names: List[str], link_capacity: float = 10.0
    ) -> Dict[str, Any]:
        """Create a ring network topology (nodes connected in a circle)."""
        network_data = {"nodes": {name: {} for name in node_names}, "links": []}

        for i in range(len(node_names)):
            next_i = (i + 1) % len(node_names)
            network_data["links"].append(
                {
                    "source": node_names[i],
                    "target": node_names[next_i],
                    "link_params": {"capacity": link_capacity, "cost": 1},
                }
            )

        return network_data

    @staticmethod
    def tree_network(
        depth: int, branching_factor: int, link_capacity: float = 10.0
    ) -> Dict[str, Any]:
        """Create a tree network topology with specified depth and branching factor."""
        nodes = {}
        links = []

        # Generate nodes
        node_id = 0
        queue = [(f"node_{node_id}", 0)]  # (node_name, current_depth)
        nodes[f"node_{node_id}"] = {}
        node_id += 1

        while queue:
            parent_name, current_depth = queue.pop(0)

            if current_depth < depth:
                for _ in range(branching_factor):
                    child_name = f"node_{node_id}"
                    nodes[child_name] = {}

                    # Add link from parent to child
                    links.append(
                        {
                            "source": parent_name,
                            "target": child_name,
                            "link_params": {"capacity": link_capacity, "cost": 1},
                        }
                    )

                    queue.append((child_name, current_depth + 1))
                    node_id += 1

        return {"nodes": nodes, "links": links}


class BlueprintTemplates:
    """Templates for common blueprint patterns."""

    @staticmethod
    def simple_group_blueprint(
        group_name: str, node_count: int, name_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a simple blueprint with one group of nodes."""
        if name_template is None:
            name_template = f"{group_name}-{{node_num}}"

        return {
            "groups": {
                group_name: {"node_count": node_count, "name_template": name_template}
            }
        }

    @staticmethod
    def two_tier_blueprint(
        tier1_count: int = 4,
        tier2_count: int = 4,
        pattern: str = "mesh",
        link_capacity: float = 10.0,
    ) -> Dict[str, Any]:
        """Create a two-tier blueprint (leaf-spine pattern)."""
        return {
            "groups": {
                "tier1": {"node_count": tier1_count, "name_template": "t1-{node_num}"},
                "tier2": {"node_count": tier2_count, "name_template": "t2-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "/tier1",
                    "target": "/tier2",
                    "pattern": pattern,
                    "link_params": {"capacity": link_capacity, "cost": 1},
                }
            ],
        }

    @staticmethod
    def three_tier_clos_blueprint(
        leaf_count: int = 4,
        spine_count: int = 4,
        super_spine_count: int = 2,
        link_capacity: float = 10.0,
    ) -> Dict[str, Any]:
        """Create a three-tier Clos blueprint."""
        return {
            "groups": {
                "leaf": {"node_count": leaf_count, "name_template": "leaf-{node_num}"},
                "spine": {
                    "node_count": spine_count,
                    "name_template": "spine-{node_num}",
                },
                "super_spine": {
                    "node_count": super_spine_count,
                    "name_template": "ss-{node_num}",
                },
            },
            "adjacency": [
                {
                    "source": "/leaf",
                    "target": "/spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": link_capacity, "cost": 1},
                },
                {
                    "source": "/spine",
                    "target": "/super_spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": link_capacity, "cost": 1},
                },
            ],
        }

    @staticmethod
    def nested_blueprint(
        inner_blueprint_name: str,
        wrapper_group_name: str = "wrapper",
        additional_groups: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a blueprint that wraps another blueprint with additional components."""
        blueprint_data = {
            "groups": {wrapper_group_name: {"use_blueprint": inner_blueprint_name}}
        }

        if additional_groups:
            blueprint_data["groups"].update(additional_groups)

        return blueprint_data


class FailurePolicyTemplates:
    """Templates for common failure policy patterns."""

    @staticmethod
    def single_link_failure() -> Dict[str, Any]:
        """Template for single link failure policy."""
        return {
            "attrs": {
                "description": "Single link failure scenario",
            },
            "modes": [
                {
                    "weight": 1.0,
                    "rules": [
                        {"entity_scope": "link", "rule_type": "choice", "count": 1}
                    ],
                }
            ],
        }

    @staticmethod
    def single_node_failure() -> Dict[str, Any]:
        """Template for single node failure policy."""
        return {
            "attrs": {
                "description": "Single node failure scenario",
            },
            "modes": [
                {
                    "weight": 1.0,
                    "rules": [
                        {"entity_scope": "node", "rule_type": "choice", "count": 1}
                    ],
                }
            ],
        }

    @staticmethod
    def multiple_failure(entity_scope: str, count: int) -> Dict[str, Any]:
        """Template for multiple simultaneous failures."""
        return {
            "attrs": {
                "description": f"Multiple {entity_scope} failure scenario",
            },
            "modes": [
                {
                    "weight": 1.0,
                    "rules": [
                        {
                            "entity_scope": entity_scope,
                            "rule_type": "choice",
                            "count": count,
                        }
                    ],
                }
            ],
        }

    @staticmethod
    def all_links_failure() -> Dict[str, Any]:
        """Template for all links failure policy."""
        return {
            "attrs": {
                "description": "All links failure scenario",
            },
            "modes": [
                {"weight": 1.0, "rules": [{"entity_scope": "link", "rule_type": "all"}]}
            ],
        }

    @staticmethod
    def risk_group_failure(risk_group_name: str) -> Dict[str, Any]:
        """Template for risk group-based failure policy."""
        return {
            "attrs": {
                "description": f"Failure of risk group {risk_group_name}",
            },
            "fail_risk_groups": True,
            "modes": [
                {
                    "weight": 1.0,
                    "rules": [
                        {
                            "entity_scope": "link",
                            "rule_type": "all",
                            "conditions": [
                                {
                                    "attr": "risk_groups",
                                    "operator": "contains",
                                    "value": risk_group_name,
                                }
                            ],
                        }
                    ],
                }
            ],
        }


class TrafficDemandTemplates:
    """Templates for common traffic demand patterns."""

    @staticmethod
    def all_to_all_uniform(
        node_names: List[str], demand_value: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Create uniform all-to-all traffic demands."""
        demands = []
        for source in node_names:
            for sink in node_names:
                if source != sink:  # Skip self-demands
                    demands.append(
                        {
                            "source": source,
                            "sink": sink,
                            "demand": demand_value,
                        }
                    )
        return demands

    @staticmethod
    def star_traffic(
        center_node: str, leaf_nodes: List[str], demand_value: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Create star traffic pattern (all traffic to/from center node)."""
        demands = []

        # Traffic from leaves to center
        for leaf in leaf_nodes:
            demands.append(
                {"source": leaf, "sink": center_node, "demand": demand_value}
            )

        # Traffic from center to leaves
        for leaf in leaf_nodes:
            demands.append(
                {"source": center_node, "sink": leaf, "demand": demand_value}
            )

        return demands

    @staticmethod
    def random_demands(
        node_names: List[str],
        num_demands: int,
        min_demand: float = 1.0,
        max_demand: float = 10.0,
        seed: int = 42,
    ) -> List[Dict[str, Any]]:
        """Create random traffic demands between nodes."""
        import random

        random.seed(seed)
        demands = []

        for _ in range(num_demands):
            source = random.choice(node_names)
            sink = random.choice([n for n in node_names if n != source])
            demand_value = random.uniform(min_demand, max_demand)

            demands.append({"source": source, "sink": sink, "demand": demand_value})

        return demands

    @staticmethod
    def hotspot_traffic(
        hotspot_nodes: List[str],
        other_nodes: List[str],
        hotspot_demand: float = 10.0,
        normal_demand: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """Create traffic with hotspot patterns (high demand to/from certain nodes)."""
        demands = []

        # High demand traffic to hotspots
        for source in other_nodes:
            for hotspot in hotspot_nodes:
                demands.append(
                    {
                        "source": source,
                        "sink": hotspot,
                        "demand": hotspot_demand,
                    }
                )

        # Normal demand for other traffic
        for source in other_nodes:
            for sink in other_nodes:
                if source != sink:
                    demands.append(
                        {
                            "source": source,
                            "sink": sink,
                            "demand": normal_demand,
                        }
                    )

        return demands


class WorkflowTemplates:
    """Templates for common workflow patterns."""

    @staticmethod
    def basic_build_workflow() -> List[Dict[str, Any]]:
        """Basic workflow that just builds the graph."""
        return [{"step_type": "BuildGraph", "name": "build_graph"}]

    @staticmethod
    def capacity_analysis_workflow(
        source_pattern: str, sink_pattern: str, modes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Workflow for capacity analysis between source and sink patterns."""
        if modes is None:
            modes = ["combine", "pairwise"]

        workflow = [{"step_type": "BuildGraph", "name": "build_graph"}]

        for i, mode in enumerate(modes):
            workflow.append(
                {
                    "step_type": "MaxFlow",
                    "name": f"capacity_analysis_{i}",
                    "source": source_pattern,
                    "sink": sink_pattern,
                    "mode": mode,
                    "iterations": 1,
                    "failure_policy": None,
                    "shortest_path": True,
                }
            )

        return workflow

    @staticmethod
    def failure_analysis_workflow(
        source_pattern: str, sink_pattern: str, failure_policy_name: str = "default"
    ) -> List[Dict[str, Any]]:
        """Workflow for analyzing network under failures."""
        return [
            {"step_type": "BuildGraph", "name": "build_graph"},
            {
                "step_type": "MaxFlow",
                "name": "failure_analysis",
                "source": source_pattern,
                "sink": sink_pattern,
                "iterations": 100,
                "parallelism": 4,
            },
        ]

    @staticmethod
    def comprehensive_analysis_workflow(
        source_pattern: str, sink_pattern: str
    ) -> List[Dict[str, Any]]:
        """Comprehensive workflow with multiple analysis steps."""
        return [
            {"step_type": "BuildGraph", "name": "build_graph"},
            {
                "step_type": "MaxFlow",
                "name": "capacity_analysis_combine",
                "source": source_pattern,
                "sink": sink_pattern,
                "mode": "combine",
                "iterations": 1,
            },
            {
                "step_type": "MaxFlow",
                "name": "capacity_analysis_pairwise",
                "source": source_pattern,
                "sink": sink_pattern,
                "mode": "pairwise",
                "shortest_path": True,
                "iterations": 1,
            },
            {
                "step_type": "MaxFlow",
                "name": "envelope_analysis",
                "source": source_pattern,
                "sink": sink_pattern,
                "iterations": 50,
            },
        ]


class ScenarioTemplateBuilder:
    """High-level builder for complete scenario templates."""

    def __init__(self, name: str, version: str = "1.0"):
        """Initialize with scenario metadata."""
        self.builder = ScenarioDataBuilder()
        self.name = name
        self.version = version

    def with_linear_backbone(
        self,
        cities: List[str],
        link_capacity: float = 100.0,
        add_coordinates: bool = True,
    ) -> "ScenarioTemplateBuilder":
        """Add a linear backbone network topology."""
        network_data = NetworkTemplates.linear_network(cities, link_capacity)

        if add_coordinates:
            # Add some example coordinates for visualization
            coords_map = {
                "NYC": [40.7128, -74.0060],
                "CHI": [41.8781, -87.6298],
                "DEN": [39.7392, -104.9903],
                "SFO": [37.7749, -122.4194],
                "SEA": [47.6062, -122.3321],
                "LAX": [34.0522, -118.2437],
                "MIA": [25.7617, -80.1918],
                "ATL": [33.7490, -84.3880],
            }

            for city in cities:
                if city in coords_map:
                    network_data["nodes"][city]["attrs"] = {"coords": coords_map[city]}

        network_data["name"] = self.name
        network_data["version"] = self.version
        self.builder.data["network"] = network_data
        return self

    def with_clos_fabric(
        self,
        fabric_name: str,
        leaf_count: int = 4,
        spine_count: int = 4,
        link_capacity: float = 100.0,
    ) -> "ScenarioTemplateBuilder":
        """Add a Clos fabric using blueprints."""
        # Create the Clos blueprint
        clos_blueprint = BlueprintTemplates.two_tier_blueprint(
            tier1_count=leaf_count, tier2_count=spine_count, link_capacity=link_capacity
        )

        self.builder.with_blueprint("clos_fabric", clos_blueprint)

        # Add to network
        if "network" not in self.builder.data:
            self.builder.data["network"] = {"name": self.name, "version": self.version}
        if "groups" not in self.builder.data["network"]:
            self.builder.data["network"]["groups"] = {}

        self.builder.data["network"]["groups"][fabric_name] = {
            "use_blueprint": "clos_fabric"
        }

        return self

    def with_uniform_traffic(
        self, node_patterns: List[str], demand_value: float = 50.0
    ) -> "ScenarioTemplateBuilder":
        """Add uniform traffic demands between node patterns."""
        demands = []
        for source_pattern in node_patterns:
            for sink_pattern in node_patterns:
                if source_pattern != sink_pattern:
                    demands.append(
                        {
                            "source": source_pattern,
                            "sink": sink_pattern,
                            "demand": demand_value,
                        }
                    )

        if "traffic_matrix_set" not in self.builder.data:
            self.builder.data["traffic_matrix_set"] = {}
        self.builder.data["traffic_matrix_set"]["default"] = demands

        return self

    def with_single_link_failures(self) -> "ScenarioTemplateBuilder":
        """Add single link failure policy."""
        policy = FailurePolicyTemplates.single_link_failure()
        self.builder.with_failure_policy("single_link_failure", policy)
        return self

    def with_capacity_analysis(
        self, source_pattern: str, sink_pattern: str
    ) -> "ScenarioTemplateBuilder":
        """Add capacity analysis workflow."""
        workflow = WorkflowTemplates.capacity_analysis_workflow(
            source_pattern, sink_pattern
        )
        self.builder.data["workflow"] = workflow
        return self

    def build(self) -> str:
        """Build the complete scenario YAML."""
        return self.builder.build_yaml()


# Pre-built scenario templates for common use cases
class CommonScenarios:
    """Pre-built scenario templates for common testing patterns."""

    @staticmethod
    def simple_linear_with_failures(node_count: int = 4) -> str:
        """Simple linear network with single link failure analysis."""
        nodes = [f"Node{i}" for i in range(1, node_count + 1)]

        return (
            ScenarioTemplateBuilder("simple_linear", "1.0")
            .with_linear_backbone(nodes, link_capacity=10.0, add_coordinates=False)
            .with_uniform_traffic(nodes, demand_value=5.0)
            .with_single_link_failures()
            .with_capacity_analysis(nodes[0], nodes[-1])
            .build()
        )

    @staticmethod
    def dual_clos_interconnect() -> str:
        """Two Clos fabrics interconnected via spine links."""
        return (
            ScenarioTemplateBuilder("dual_clos", "1.0")
            .with_clos_fabric("fabric_east", leaf_count=4, spine_count=4)
            .with_clos_fabric("fabric_west", leaf_count=4, spine_count=4)
            .with_uniform_traffic(["fabric_east", "fabric_west"], demand_value=25.0)
            .with_single_link_failures()
            .with_capacity_analysis("fabric_east/.*", "fabric_west/.*")
            .build()
        )

    @staticmethod
    def us_backbone_network() -> str:
        """US backbone network with major cities."""
        cities = ["NYC", "CHI", "DEN", "SFO", "SEA", "LAX", "MIA", "ATL"]

        return (
            ScenarioTemplateBuilder("us_backbone", "1.0")
            .with_linear_backbone(cities, link_capacity=200.0, add_coordinates=True)
            .with_uniform_traffic(
                cities[:4], demand_value=75.0
            )  # Focus on major routes
            .with_single_link_failures()
            .with_capacity_analysis("NYC|CHI", "SFO|SEA")
            .build()
        )

    @staticmethod
    def minimal_test_scenario() -> str:
        """Minimal scenario for basic functionality testing."""
        from typing import Any, Dict

        from .helpers import ScenarioDataBuilder

        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B", "C"])
        builder.with_simple_links([("A", "B", 1.0), ("B", "C", 1.0)])
        builder.with_workflow_step("BuildGraph", "build_graph")
        # Set network metadata
        network_data: Dict[str, Any] = builder.data["network"]
        network_data["name"] = "minimal_test"
        network_data["version"] = "1.0"
        return builder.build_yaml()


class ErrorInjectionTemplates:
    """Templates for injecting common error conditions into scenarios."""

    @staticmethod
    def invalid_node_builder() -> ScenarioDataBuilder:
        """Create scenario builder with invalid node configuration."""
        builder = ScenarioDataBuilder()
        # Create nodes that will cause validation errors
        return builder

    @staticmethod
    def missing_nodes_builder() -> ScenarioDataBuilder:
        """Create scenario builder with links referencing missing nodes."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["NodeA"])
        # Add link to nonexistent node - will cause error during execution
        builder.data["network"]["links"] = [
            {
                "source": "NodeA",
                "target": "NonexistentNode",
                "link_params": {"capacity": 10, "cost": 1},
            }
        ]
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def circular_blueprint_builder() -> ScenarioDataBuilder:
        """Create scenario builder with circular blueprint references."""
        builder = ScenarioDataBuilder()
        builder.with_blueprint(
            "blueprint_a", {"groups": {"group_a": {"use_blueprint": "blueprint_b"}}}
        )
        builder.with_blueprint(
            "blueprint_b", {"groups": {"group_b": {"use_blueprint": "blueprint_a"}}}
        )
        builder.data["network"] = {
            "name": "circular_test",
            "groups": {"test_group": {"use_blueprint": "blueprint_a"}},
        }
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def invalid_failure_policy_builder() -> ScenarioDataBuilder:
        """Create scenario builder with invalid failure policy."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B"])
        builder.with_simple_links([("A", "B", 10.0)])
        builder.with_failure_policy(
            "invalid_policy",
            {
                "rules": [
                    {
                        "entity_scope": "invalid_scope",  # Invalid scope
                        "rule_type": "choice",
                        "count": 1,
                    }
                ]
            },
        )
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def negative_demand_builder() -> ScenarioDataBuilder:
        """Create scenario builder with negative traffic demands."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["Source", "Sink"])
        builder.with_simple_links([("Source", "Sink", 10.0)])
        builder.with_traffic_demand("Source", "Sink", -50.0)  # Negative demand
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def missing_workflow_params_builder() -> ScenarioDataBuilder:
        """Create scenario builder with incomplete workflow step parameters."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B"])
        builder.with_simple_links([("A", "B", 10.0)])
        # Add CapacityEnvelopeAnalysis without required parameters
        builder.data["workflow"] = [
            {
                "step_type": "CapacityEnvelopeAnalysis",
                "name": "incomplete_analysis",
                # Missing source and sink
            }
        ]
        return builder

    @staticmethod
    def large_network_builder(node_count: int = 1000) -> ScenarioDataBuilder:
        """Create scenario builder for stress testing with large networks."""
        builder = ScenarioDataBuilder()

        # Create many nodes
        node_names = [f"Node_{i:04d}" for i in range(node_count)]
        builder.with_simple_nodes(node_names)

        # Create star topology to avoid O(n²) mesh complexity
        if node_count > 1:
            center_node = node_names[0]
            leaf_nodes = node_names[1:]

            links = [
                (center_node, leaf, 1.0)
                for leaf in leaf_nodes[: min(100, len(leaf_nodes))]
            ]
            builder.with_simple_links(links)

        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def deep_blueprint_nesting_builder(depth: int = 15) -> ScenarioDataBuilder:
        """Create scenario builder with deeply nested blueprints."""
        builder = ScenarioDataBuilder()

        # Create nested blueprints
        for i in range(depth):
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

        # Use the deepest blueprint
        builder.data["network"] = {
            "name": "deep_nesting_test",
            "groups": {"deep_group": {"use_blueprint": f"level_{depth - 1}"}},
        }
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder


class EdgeCaseTemplates:
    """Templates for edge case scenarios and boundary conditions."""

    @staticmethod
    def empty_network_builder() -> ScenarioDataBuilder:
        """Create scenario builder with completely empty network."""
        builder = ScenarioDataBuilder()
        builder.data["network"] = {"name": "empty", "nodes": {}, "links": []}
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def single_node_builder(node_name: str = "LonelyNode") -> ScenarioDataBuilder:
        """Create scenario builder with single isolated node."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes([node_name])
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def isolated_nodes_builder(node_count: int = 5) -> ScenarioDataBuilder:
        """Create scenario builder with multiple isolated nodes."""
        builder = ScenarioDataBuilder()
        node_names = [f"Isolated_{i}" for i in range(node_count)]
        builder.with_simple_nodes(node_names)
        # No links - all nodes isolated
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def zero_capacity_links_builder() -> ScenarioDataBuilder:
        """Create scenario builder with zero-capacity links."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B", "C"])
        builder.data["network"]["links"] = [
            {"source": "A", "target": "B", "link_params": {"capacity": 0, "cost": 1}},
            {"source": "B", "target": "C", "link_params": {"capacity": 0, "cost": 1}},
        ]
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def extreme_values_builder() -> ScenarioDataBuilder:
        """Create scenario builder with extreme numeric values."""
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
        builder.with_traffic_demand("NodeA", "NodeB", 888888888888.0)  # Large demand
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def special_characters_builder() -> ScenarioDataBuilder:
        """Create scenario builder with special characters in names."""
        builder = ScenarioDataBuilder()
        special_names = ["node-with-dashes", "node.with.dots", "node_with_underscores"]
        builder.with_simple_nodes(special_names)

        # Add links between nodes with special characters
        if len(special_names) >= 2:
            builder.with_simple_links([(special_names[0], special_names[1], 10.0)])

        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def duplicate_links_builder() -> ScenarioDataBuilder:
        """Create scenario builder with multiple links between same nodes."""
        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B"])

        # Add multiple links with different parameters
        builder.data["network"]["links"] = [
            {"source": "A", "target": "B", "link_params": {"capacity": 10, "cost": 1}},
            {"source": "A", "target": "B", "link_params": {"capacity": 20, "cost": 2}},
            {"source": "A", "target": "B", "link_params": {"capacity": 15, "cost": 3}},
        ]
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder


class PerformanceTestTemplates:
    """Templates for performance and stress testing scenarios."""

    @staticmethod
    def large_star_network_builder(leaf_count: int = 100) -> ScenarioDataBuilder:
        """Create large star network for performance testing."""
        builder = ScenarioDataBuilder()

        center = "HUB"
        leaves = [f"LEAF_{i:03d}" for i in range(leaf_count)]
        all_nodes = [center] + leaves

        builder.with_simple_nodes(all_nodes)

        # Create star links
        star_links = [(center, leaf, 10.0) for leaf in leaves]
        builder.with_simple_links(star_links)

        # Add some traffic demands
        demands = [(center, leaf, 1.0) for leaf in leaves[: min(10, len(leaves))]]
        for source, sink, demand in demands:
            builder.with_traffic_demand(source, sink, demand)

        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def large_mesh_blueprint_builder(side_size: int = 20) -> ScenarioDataBuilder:
        """Create large mesh using blueprints for performance testing."""
        builder = ScenarioDataBuilder()

        # Create large mesh blueprint
        large_mesh_blueprint = {
            "groups": {
                "side_a": {"node_count": side_size, "name_template": "a-{node_num}"},
                "side_b": {"node_count": side_size, "name_template": "b-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "/side_a",
                    "target": "/side_b",
                    "pattern": "mesh",
                    "link_params": {"capacity": 1, "cost": 1},
                }
            ],
        }

        builder.with_blueprint("large_mesh", large_mesh_blueprint)
        builder.data["network"] = {
            "name": "large_mesh_test",
            "groups": {"mesh_group": {"use_blueprint": "large_mesh"}},
        }
        builder.with_workflow_step("BuildGraph", "build_graph")
        return builder

    @staticmethod
    def complex_multi_blueprint_builder() -> ScenarioDataBuilder:
        """Create complex scenario with multiple interacting blueprints."""
        builder = ScenarioDataBuilder()

        # Create basic building blocks
        basic_brick = BlueprintTemplates.two_tier_blueprint(4, 4, "mesh", 10.0)
        builder.with_blueprint("basic_brick", basic_brick)

        # Create aggregation layer
        agg_layer = {
            "groups": {
                "brick1": {"use_blueprint": "basic_brick"},
                "brick2": {"use_blueprint": "basic_brick"},
                "agg_spine": {"node_count": 8, "name_template": "agg-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "brick1/tier2",
                    "target": "agg_spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": 20, "cost": 1},
                },
                {
                    "source": "brick2/tier2",
                    "target": "agg_spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": 20, "cost": 1},
                },
            ],
        }
        builder.with_blueprint("agg_layer", agg_layer)

        # Create core layer
        core_layer = {
            "groups": {
                "agg1": {"use_blueprint": "agg_layer"},
                "agg2": {"use_blueprint": "agg_layer"},
                "core_spine": {"node_count": 4, "name_template": "core-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "agg1/agg_spine",
                    "target": "core_spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": 40, "cost": 1},
                },
                {
                    "source": "agg2/agg_spine",
                    "target": "core_spine",
                    "pattern": "mesh",
                    "link_params": {"capacity": 40, "cost": 1},
                },
            ],
        }
        builder.with_blueprint("core_layer", core_layer)

        # Use in network
        builder.data["network"] = {
            "name": "complex_multi_blueprint",
            "groups": {"datacenter": {"use_blueprint": "core_layer"}},
        }

        # Add capacity analysis workflow
        workflow = WorkflowTemplates.capacity_analysis_workflow(
            "datacenter/agg1/brick1/tier1/.*", "datacenter/agg2/brick2/tier1/.*"
        )
        builder.data["workflow"] = workflow

        return builder
