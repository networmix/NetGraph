"""
Example tests demonstrating the use of modular test data templates.

Shows how the template system improves test data organization, reduces
duplication, and enables rapid creation of test scenarios.
"""

import pytest

from ngraph.scenario import Scenario

from .expectations import (
    SCENARIO_1_EXPECTATIONS,
    SCENARIO_3_EXPECTATIONS,
)
from .helpers import create_scenario_helper
from .test_data_templates import (
    BlueprintTemplates,
    CommonScenarios,
    FailurePolicyTemplates,
    NetworkTemplates,
    ScenarioTemplateBuilder,
    TrafficDemandTemplates,
    WorkflowTemplates,
)


@pytest.mark.slow
class TestNetworkTemplates:
    """Keep only a minimal sanity check for templates; detailed tests belong to unit level."""

    def test_linear_network_template_minimal(self):
        nodes = ["A", "B", "C", "D"]
        network_data = NetworkTemplates.linear_network(nodes, link_capacity=15.0)
        assert len(network_data["nodes"]) == 4
        assert len(network_data["links"]) == 3

    def test_star_network_template(self):
        """Test star network template creates correct topology."""
        center = "HUB"
        leaves = ["A", "B", "C"]
        network_data = NetworkTemplates.star_network(center, leaves, link_capacity=20.0)

        # Validate structure
        assert len(network_data["nodes"]) == 4  # center + 3 leaves
        assert len(network_data["links"]) == 3  # center connected to each leaf

        # All links should originate from center
        for link in network_data["links"]:
            assert link["source"] == center
            assert link["target"] in leaves
            assert link["link_params"]["capacity"] == 20.0

    def test_mesh_network_template(self):
        """Test full mesh network template creates all-to-all connectivity."""
        nodes = ["A", "B", "C"]
        network_data = NetworkTemplates.mesh_network(nodes, link_capacity=5.0)

        # Validate structure
        assert len(network_data["nodes"]) == 3
        assert len(network_data["links"]) == 6  # 3 nodes = 3*2 = 6 directed links

        # Every node should connect to every other node
        link_pairs = [
            (link["source"], link["target"]) for link in network_data["links"]
        ]
        expected_pairs = [
            ("A", "B"),
            ("A", "C"),
            ("B", "A"),
            ("B", "C"),
            ("C", "A"),
            ("C", "B"),
        ]
        assert set(link_pairs) == set(expected_pairs)

    def test_tree_network_template(self):
        """Test tree network template creates hierarchical structure."""
        network_data = NetworkTemplates.tree_network(
            depth=2, branching_factor=2, link_capacity=10.0
        )

        # Depth 2 with branching 2: root + 2 children + 4 grandchildren = 7 nodes
        assert len(network_data["nodes"]) == 7
        # 6 links connecting them in tree structure
        assert len(network_data["links"]) == 6


@pytest.mark.slow
class TestBlueprintTemplates:
    def test_simple_group_blueprint_minimal(self):
        blueprint = BlueprintTemplates.simple_group_blueprint(
            "servers", 5, "srv-{node_num}"
        )
        assert blueprint["groups"]["servers"]["node_count"] == 5


@pytest.mark.slow
class TestFailurePolicyTemplates:
    def test_single_link_failure_template_minimal(self):
        policy = FailurePolicyTemplates.single_link_failure()
        assert "modes" in policy and len(policy["modes"]) == 1
        assert len(policy["modes"][0]["rules"]) == 1


@pytest.mark.slow
class TestTrafficDemandTemplates:
    def test_all_to_all_uniform_demands_minimal(self):
        nodes = ["A", "B", "C"]
        demands = TrafficDemandTemplates.all_to_all_uniform(nodes, demand_value=15.0)
        assert len(demands) == 6


@pytest.mark.slow
class TestWorkflowTemplates:
    def test_basic_build_workflow_minimal(self):
        workflow = WorkflowTemplates.basic_build_workflow()
        assert len(workflow) == 1
        assert workflow[0]["step_type"] == "BuildGraph"


@pytest.mark.slow
class TestScenarioTemplateBuilder:
    def test_linear_backbone_scenario_minimal(self):
        cities = ["NYC", "CHI", "DEN", "SFO"]
        yaml_content = (
            ScenarioTemplateBuilder("test_backbone", "1.0")
            .with_linear_backbone(cities, link_capacity=100.0)
            .with_uniform_traffic(cities, demand_value=25.0)
            .with_single_link_failures()
            .with_capacity_analysis("NYC", "SFO")
            .build()
        )
        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")
        assert len(graph.nodes) == 4


@pytest.mark.slow
class TestCommonScenarios:
    def test_minimal_test_scenario_minimal(self):
        yaml_content = CommonScenarios.minimal_test_scenario()
        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")
        assert len(graph.nodes) == 3


@pytest.mark.slow
class TestTemplateComposition:
    """Tests demonstrating composition of multiple templates."""

    def test_combining_multiple_templates(self):
        """Test combining different template types in one scenario."""
        # Create a complex scenario using multiple templates
        builder = ScenarioTemplateBuilder("complex_test", "1.0")

        # Add a linear backbone
        backbone_nodes = ["A", "B", "C"]
        backbone_data = NetworkTemplates.linear_network(backbone_nodes, 50.0)
        builder.builder.data["network"] = backbone_data
        builder.builder.data["network"]["name"] = "complex_test"
        builder.builder.data["network"]["version"] = "1.0"

        # Add Clos fabric blueprint
        clos_blueprint = BlueprintTemplates.two_tier_blueprint(4, 4, "mesh", 25.0)
        builder.builder.with_blueprint("clos", clos_blueprint)

        # Add traffic demands
        demands = TrafficDemandTemplates.all_to_all_uniform(backbone_nodes, 10.0)
        builder.builder.data["traffic_matrix_set"] = {"default": demands}

        # Add failure policy
        policy = FailurePolicyTemplates.single_link_failure()
        builder.builder.with_failure_policy("single_link", policy)

        # Add workflow
        workflow = WorkflowTemplates.capacity_analysis_workflow("A", "C")
        builder.builder.data["workflow"] = workflow

        # Build and test
        yaml_content = builder.build()
        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        # Validate the complex scenario works
        helper = create_scenario_helper(scenario)
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")
        helper.set_graph(graph)

        assert len(graph.nodes) >= 3  # At least backbone nodes
        assert len(scenario.failure_policy_set.get_all_policies()) > 0

    def test_template_parameterization(self):
        """Test that templates can be easily parameterized for different scales."""
        scales = [
            {"nodes": 3, "capacity": 10.0},
            {"nodes": 5, "capacity": 50.0},
            {"nodes": 8, "capacity": 100.0},
        ]

        for scale in scales:
            nodes = [f"N{i}" for i in range(scale["nodes"])]

            # Build scenario with explicit workflow step
            builder = ScenarioTemplateBuilder(f"scale_test_{scale['nodes']}", "1.0")
            builder.with_linear_backbone(
                nodes, scale["capacity"], add_coordinates=False
            )
            builder.with_uniform_traffic(nodes, demand_value=scale["capacity"] / 10)

            # Ensure BuildGraph step is included
            builder.builder.with_workflow_step("BuildGraph", "build_graph")

            yaml_content = builder.build()

            scenario = Scenario.from_yaml(yaml_content)
            scenario.run()

            exported = scenario.results.to_dict()
            graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
            import networkx as nx

            graph = nx.node_link_graph(graph_dict, edges="edges")
            assert graph is not None, (
                f"BuildGraph should produce a graph for scale {scale['nodes']}"
            )
            assert len(graph.nodes) == scale["nodes"]

            # Validate link capacities match scale
            for _u, _v, data in graph.edges(data=True):
                assert data.get("capacity") == scale["capacity"]


@pytest.mark.slow
class TestTemplateValidation:
    """Tests for template validation and error handling."""

    def test_template_parameter_validation(self):
        """Test that templates validate parameters appropriately."""
        # Test edge case parameters that should work (NetGraph is permissive)
        # Empty node list should work (creates empty network)
        network_empty = NetworkTemplates.linear_network([])
        assert network_empty["nodes"] == {}
        assert network_empty["links"] == []

        # Zero count should work
        blueprint_zero = BlueprintTemplates.two_tier_blueprint(tier1_count=0)
        assert blueprint_zero["groups"]["tier1"]["node_count"] == 0

        # Negative demands might be allowed in NetGraph - test actual behavior
        demands_negative = TrafficDemandTemplates.all_to_all_uniform(
            ["A", "B"], demand_value=-5.0
        )
        # Should create demands but with negative values
        assert len(demands_negative) == 2  # A->B and B->A
        for demand in demands_negative:
            assert demand["demand"] == -5.0

    def test_template_consistency(self):
        """Test that templates produce consistent results."""
        # Same parameters should produce same results
        nodes = ["X", "Y", "Z"]

        network1 = NetworkTemplates.linear_network(nodes, 15.0)
        network2 = NetworkTemplates.linear_network(nodes, 15.0)

        assert network1 == network2

        demands1 = TrafficDemandTemplates.all_to_all_uniform(nodes, 5.0)
        demands2 = TrafficDemandTemplates.all_to_all_uniform(nodes, 5.0)

        assert demands1 == demands2


@pytest.mark.slow
class TestMainScenarioVariants:
    """Template-based variants of main scenarios for testing different configurations."""

    def test_scenario_1_template_variant(self):
        """Template-based recreation of scenario 1 functionality."""
        # Recreate scenario 1 using templates
        backbone_nodes = ["SEA", "SFO", "DEN", "DFW", "JFK", "DCA"]

        builder = ScenarioTemplateBuilder("scenario_1_template", "1.0")

        # Create network structure matching scenario 1
        network_data = NetworkTemplates.linear_network(
            backbone_nodes[:2], 200.0
        )  # SEA-SFO base

        # Add additional backbone links to match scenario 1 topology
        additional_links = [
            ("SEA", "DEN", 200.0),
            ("SFO", "DEN", 200.0),
            ("SEA", "DFW", 200.0),
            ("SFO", "DFW", 200.0),
            ("DEN", "DFW", 400.0),  # Will add second parallel link
            ("DEN", "JFK", 200.0),
            ("DFW", "DCA", 200.0),
            ("DFW", "JFK", 200.0),
            ("JFK", "DCA", 100.0),
        ]

        # Build network manually for this complex topology
        network_data = {
            "name": "scenario_1_template",
            "version": "1.0",
            "nodes": {node: {} for node in backbone_nodes},
            "links": [],
        }

        for source, target, capacity in additional_links:
            network_data["links"].append(
                {
                    "source": source,
                    "target": target,
                    "link_params": {"capacity": capacity, "cost": 1},
                }
            )

        # Add second DEN-DFW link for parallel connection
        network_data["links"].append(
            {
                "source": "DEN",
                "target": "DFW",
                "link_params": {"capacity": 400.0, "cost": 1},
            }
        )

        builder.builder.data["network"] = network_data

        # Add traffic demands matching scenario 1
        demands = [
            {"source": "SEA", "sink": "JFK", "demand": 50},
            {"source": "SFO", "sink": "DCA", "demand": 50},
            {"source": "SEA", "sink": "DCA", "demand": 50},
            {"source": "SFO", "sink": "JFK", "demand": 50},
        ]
        builder.builder.data["traffic_matrix_set"] = {"default": demands}

        # Add failure policy matching scenario 1
        policy = FailurePolicyTemplates.single_link_failure()
        policy["attrs"]["name"] = "anySingleLink"
        policy["attrs"]["description"] = (
            "Evaluate traffic routing under any single link failure."
        )
        builder.builder.with_failure_policy("single_link", policy)

        # Add workflow
        workflow = WorkflowTemplates.basic_build_workflow()
        builder.builder.data["workflow"] = workflow

        # Test the template-based scenario
        scenario = builder.builder.build_scenario()
        scenario.run()

        helper = create_scenario_helper(scenario)
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")
        helper.set_graph(graph)

        # Validate it matches scenario 1 expectations
        helper.validate_network_structure(SCENARIO_1_EXPECTATIONS)
        helper.validate_traffic_demands(4)

    def test_scenario_2_template_variant(self):
        """Template-based recreation of scenario 2 blueprint functionality."""
        builder = ScenarioTemplateBuilder("scenario_2_template", "1.0")

        # Create blueprints matching scenario 2
        clos_2tier = BlueprintTemplates.two_tier_blueprint(
            tier1_count=4, tier2_count=4, pattern="mesh", link_capacity=100.0
        )
        # Rename groups to match scenario 2
        clos_2tier["groups"] = {
            "leaf": clos_2tier["groups"]["tier1"],
            "spine": clos_2tier["groups"]["tier2"],
        }
        clos_2tier["adjacency"][0]["source"] = "/leaf"
        clos_2tier["adjacency"][0]["target"] = "/spine"

        builder.builder.with_blueprint("clos_2tier", clos_2tier)

        # Create city_cloud blueprint that uses clos_2tier
        city_cloud = {
            "groups": {
                "clos_instance": {
                    "use_blueprint": "clos_2tier",
                    "parameters": {
                        "spine.node_count": 6,
                        "spine.name_template": "myspine-{node_num}",
                    },
                },
                "edge_nodes": {"node_count": 4, "name_template": "edge-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "/clos_instance/leaf",
                    "target": "/edge_nodes",
                    "pattern": "mesh",
                    "link_params": {"capacity": 100, "cost": 1000},
                }
            ],
        }
        builder.builder.with_blueprint("city_cloud", city_cloud)

        # Create single_node blueprint
        single_node = BlueprintTemplates.simple_group_blueprint(
            "single", 1, "single-{node_num}"
        )
        builder.builder.with_blueprint("single_node", single_node)

        # Create network using blueprints
        network_data = {
            "name": "scenario_2_template",
            "version": "1.1",
            "groups": {
                "SEA": {"use_blueprint": "city_cloud"},
                "SFO": {"use_blueprint": "single_node"},
            },
            "nodes": {"DEN": {}, "DFW": {}, "JFK": {}, "DCA": {}},
            "links": [
                {
                    "source": "DEN",
                    "target": "DFW",
                    "link_params": {"capacity": 400, "cost": 7102},
                },
                {
                    "source": "DEN",
                    "target": "DFW",
                    "link_params": {"capacity": 400, "cost": 7102},
                },
                {
                    "source": "DEN",
                    "target": "JFK",
                    "link_params": {"capacity": 200, "cost": 7500},
                },
                {
                    "source": "DFW",
                    "target": "DCA",
                    "link_params": {"capacity": 200, "cost": 8000},
                },
                {
                    "source": "DFW",
                    "target": "JFK",
                    "link_params": {"capacity": 200, "cost": 9500},
                },
                {
                    "source": "JFK",
                    "target": "DCA",
                    "link_params": {"capacity": 100, "cost": 1714},
                },
            ],
            "adjacency": [
                {
                    "source": "/SFO",
                    "target": "/DEN",
                    "pattern": "mesh",
                    "link_params": {"capacity": 100, "cost": 7754},
                },
                {
                    "source": "/SFO",
                    "target": "/DFW",
                    "pattern": "mesh",
                    "link_params": {"capacity": 200, "cost": 10000},
                },
                {
                    "source": "/SEA/edge_nodes",
                    "target": "/DEN",
                    "pattern": "mesh",
                    "link_params": {"capacity": 100, "cost": 6846},
                },
                {
                    "source": "/SEA/edge_nodes",
                    "target": "/DFW",
                    "pattern": "mesh",
                    "link_params": {"capacity": 100, "cost": 9600},
                },
            ],
        }
        builder.builder.data["network"] = network_data

        # Add traffic and failure policy same as scenario 1
        demands = [
            {"source": "SEA", "sink": "JFK", "demand": 50},
            {"source": "SFO", "sink": "DCA", "demand": 50},
            {"source": "SEA", "sink": "DCA", "demand": 50},
            {"source": "SFO", "sink": "JFK", "demand": 50},
        ]
        builder.builder.data["traffic_matrix_set"] = {"default": demands}

        policy = FailurePolicyTemplates.single_link_failure()
        policy["attrs"]["name"] = "anySingleLink"
        builder.builder.with_failure_policy("single_link", policy)

        workflow = WorkflowTemplates.basic_build_workflow()
        builder.builder.data["workflow"] = workflow

        # Test the template-based scenario
        scenario = builder.builder.build_scenario()
        scenario.run()

        helper = create_scenario_helper(scenario)
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")

        # Validate basic structure (exact match would require complex blueprint logic)
        assert len(graph.nodes) > 15  # Should have many nodes from blueprint expansion
        helper.validate_traffic_demands(4)

    def test_scenario_3_template_variant(self):
        """Template-based recreation of scenario 3 Clos functionality."""
        builder = ScenarioTemplateBuilder("scenario_3_template", "1.0")

        # Create brick_2tier blueprint
        brick_2tier = {
            "groups": {
                "t1": {"node_count": 4, "name_template": "t1-{node_num}"},
                "t2": {"node_count": 4, "name_template": "t2-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "/t1",
                    "target": "/t2",
                    "pattern": "mesh",
                    "link_params": {"capacity": 2, "cost": 1},
                }
            ],
        }
        builder.builder.with_blueprint("brick_2tier", brick_2tier)

        # Create 3tier_clos blueprint
        three_tier_clos = {
            "groups": {
                "b1": {"use_blueprint": "brick_2tier"},
                "b2": {"use_blueprint": "brick_2tier"},
                "spine": {"node_count": 16, "name_template": "t3-{node_num}"},
            },
            "adjacency": [
                {
                    "source": "b1/t2",
                    "target": "spine",
                    "pattern": "one_to_one",
                    "link_params": {"capacity": 2, "cost": 1},
                },
                {
                    "source": "b2/t2",
                    "target": "spine",
                    "pattern": "one_to_one",
                    "link_params": {"capacity": 2, "cost": 1},
                },
            ],
        }
        builder.builder.with_blueprint("3tier_clos", three_tier_clos)

        # Create network with two Clos instances
        network_data = {
            "name": "scenario_3_template",
            "version": "1.0",
            "groups": {
                "my_clos1": {"use_blueprint": "3tier_clos"},
                "my_clos2": {"use_blueprint": "3tier_clos"},
            },
            "adjacency": [
                {
                    "source": "my_clos1/spine",
                    "target": "my_clos2/spine",
                    "pattern": "one_to_one",
                    "link_params": {"capacity": 2, "cost": 1},
                }
            ],
        }
        builder.builder.data["network"] = network_data

        # Add capacity probe workflow
        workflow = [
            {"step_type": "BuildGraph", "name": "build_graph"},
            {
                "step_type": "MaxFlow",
                "name": "capacity_analysis",
                "source": "my_clos1/b.*/t1",
                "sink": "my_clos2/b.*/t1",
                "mode": "combine",
                "shortest_path": True,
                "flow_placement": "PROPORTIONAL",
                "iterations": 1,
                "baseline": False,
                "failure_policy": None,
            },
            {
                "step_type": "MaxFlow",
                "name": "capacity_analysis2",
                "source": "my_clos1/b.*/t1",
                "sink": "my_clos2/b.*/t1",
                "mode": "combine",
                "shortest_path": True,
                "flow_placement": "EQUAL_BALANCED",
                "iterations": 1,
                "baseline": False,
                "failure_policy": None,
            },
        ]
        builder.builder.data["workflow"] = workflow

        # Test the template-based scenario
        scenario = builder.builder.build_scenario()
        scenario.run()

        helper = create_scenario_helper(scenario)
        exported = scenario.results.to_dict()
        graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
        import networkx as nx

        graph = nx.node_link_graph(graph_dict, edges="edges")
        helper.set_graph(graph)

        # Validate basic structure matches scenario 3
        helper.validate_network_structure(SCENARIO_3_EXPECTATIONS)
        helper.validate_traffic_demands(0)  # No traffic demands in scenario 3

    def test_parameterized_backbone_scenarios(self):
        """Test creating multiple backbone configurations using templates."""
        configs = [
            {"cities": ["A", "B", "C"], "capacity": 100.0, "demand": 25.0},
            {"cities": ["NYC", "CHI", "SFO"], "capacity": 200.0, "demand": 50.0},
            {"cities": ["LON", "PAR", "BER", "ROM"], "capacity": 150.0, "demand": 30.0},
        ]

        for i, config in enumerate(configs):
            builder = ScenarioTemplateBuilder(f"backbone_{i}", "1.0")

            # Use linear backbone template
            builder.with_linear_backbone(
                config["cities"],
                link_capacity=config["capacity"],
                add_coordinates=False,
            )
            builder.with_uniform_traffic(
                config["cities"], demand_value=config["demand"]
            )
            builder.with_single_link_failures()
            builder.with_capacity_analysis(config["cities"][0], config["cities"][-1])

            scenario_yaml = builder.build()
            scenario = Scenario.from_yaml(scenario_yaml)
            scenario.run()

            # Validate each configuration
            helper = create_scenario_helper(scenario)
            exported = scenario.results.to_dict()
            graph_dict = exported["steps"]["build_graph"]["data"]["graph"]
            import networkx as nx

            graph = nx.node_link_graph(graph_dict, edges="edges")

            # Check for None graph and provide better error message
            assert graph is not None, (
                f"Build graph failed for configuration {i}: {config}"
            )

            helper.set_graph(graph)

            expected_nodes = len(config["cities"])
            expected_edges = (expected_nodes - 1) * 2  # Linear topology, bidirectional

            assert len(graph.nodes) == expected_nodes
            assert len(graph.edges) == expected_edges

            # Validate link capacities
            for _u, _v, data in graph.edges(data=True):
                assert data.get("capacity") == config["capacity"]
