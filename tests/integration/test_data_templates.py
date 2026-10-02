"""
Test data templates for scenario testing.

Template categories:
- NetworkTemplates: Common network topologies (linear, star, mesh, tree)
- BlueprintTemplates: Reusable blueprint patterns for hierarchies
- FailurePolicyTemplates: Standard failure scenario configurations
- TrafficDemandTemplates: Traffic demand patterns and distributions
- WorkflowTemplates: Common analysis workflow configurations
- ScenarioTemplateBuilder: High-level builder for complete scenarios
- CommonScenarios: Pre-built scenarios for typical use cases
"""

from typing import Any, Dict, List, Optional

from .helpers import ScenarioDataBuilder


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
                    "capacity": link_capacity,
                    "cost": 1,
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
                    "capacity": link_capacity,
                    "cost": 1,
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
                            "capacity": link_capacity,
                            "cost": 1,
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

                    links.append(
                        {
                            "source": parent_name,
                            "target": child_name,
                            "capacity": link_capacity,
                            "cost": 1,
                        }
                    )

                    queue.append((child_name, current_depth + 1))
                    node_id += 1

        return {"nodes": nodes, "links": links}


class BlueprintTemplates:
    """Templates for common blueprint patterns."""

    @staticmethod
    def simple_group_blueprint(
        group_name: str, count: int, template: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a simple blueprint with one group of nodes."""
        if template is None:
            template = f"{group_name}-{{n}}"

        return {"nodes": {group_name: {"count": count, "template": template}}}

    @staticmethod
    def two_tier_blueprint(
        tier1_count: int = 4,
        tier2_count: int = 4,
        pattern: str = "mesh",
        link_capacity: float = 10.0,
    ) -> Dict[str, Any]:
        """Create a two-tier blueprint (leaf-spine pattern)."""
        return {
            "nodes": {
                "tier1": {"count": tier1_count, "template": "t1-{n}"},
                "tier2": {"count": tier2_count, "template": "t2-{n}"},
            },
            "links": [
                {
                    "source": "/tier1",
                    "target": "/tier2",
                    "pattern": pattern,
                    "capacity": link_capacity,
                    "cost": 1,
                }
            ],
        }


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
                    "rules": [{"scope": "link", "mode": "choice", "count": 1}],
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
                    "rules": [{"scope": "node", "mode": "choice", "count": 1}],
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
            for target in node_names:
                if source != target:  # Skip self-demands
                    demands.append(
                        {
                            "source": source,
                            "target": target,
                            "volume": demand_value,
                        }
                    )
        return demands


class WorkflowTemplates:
    """Templates for common workflow patterns."""

    @staticmethod
    def basic_build_workflow() -> List[Dict[str, Any]]:
        """Basic workflow that just builds the graph."""
        return [{"type": "BuildGraph", "name": "build_graph"}]

    @staticmethod
    def capacity_analysis_workflow(
        source_pattern: str, target_pattern: str, modes: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Workflow for capacity analysis between source and target patterns."""
        if modes is None:
            modes = ["combine", "pairwise"]

        workflow = [{"type": "BuildGraph", "name": "build_graph"}]

        for i, mode in enumerate(modes):
            workflow.append(
                {
                    "type": "MaxFlow",
                    "name": f"capacity_analysis_{i}",
                    "source": source_pattern,
                    "target": target_pattern,
                    "mode": mode,
                    "iterations": 1,
                    "failure_policy": None,
                    "shortest_path": True,
                }
            )

        return workflow


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

    def with_uniform_traffic(
        self, node_patterns: List[str], demand_value: float = 50.0
    ) -> "ScenarioTemplateBuilder":
        """Add uniform traffic demands between node patterns."""
        demands = []
        for source_pattern in node_patterns:
            for target_pattern in node_patterns:
                if source_pattern != target_pattern:
                    demands.append(
                        {
                            "source": source_pattern,
                            "target": target_pattern,
                            "volume": demand_value,
                        }
                    )

        if "demands" not in self.builder.data:
            self.builder.data["demands"] = {}
        self.builder.data["demands"]["default"] = demands

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


class CommonScenarios:
    """Pre-built scenario templates for common testing patterns."""

    @staticmethod
    def minimal_test_scenario() -> str:
        """Three-node A-B-C line with a BuildGraph step."""
        from typing import Any, Dict

        from .helpers import ScenarioDataBuilder

        builder = ScenarioDataBuilder()
        builder.with_simple_nodes(["A", "B", "C"])
        builder.with_simple_links([("A", "B", 1.0), ("B", "C", 1.0)])
        builder.with_workflow_step("BuildGraph", "build_graph")
        network_data: Dict[str, Any] = builder.data["network"]
        network_data["name"] = "minimal_test"
        network_data["version"] = "1.0"
        return builder.build_yaml()
