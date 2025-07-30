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
    """Tests demonstrating network topology templates."""

    def test_linear_network_template(self):
        """Test linear network template creates correct topology."""
        nodes = ["A", "B", "C", "D"]
        network_data = NetworkTemplates.linear_network(nodes, link_capacity=15.0)

        # Validate structure
        assert len(network_data["nodes"]) == 4
        assert len(network_data["links"]) == 3  # 4 nodes = 3 links in linear

        # Validate links connect correctly
        expected_links = [("A", "B"), ("B", "C"), ("C", "D")]
        actual_links = [
            (link["source"], link["target"]) for link in network_data["links"]
        ]
        assert actual_links == expected_links

        # Validate capacity
        for link in network_data["links"]:
            assert link["link_params"]["capacity"] == 15.0

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
    """Tests demonstrating blueprint templates."""

    def test_simple_group_blueprint(self):
        """Test simple group blueprint template."""
        blueprint = BlueprintTemplates.simple_group_blueprint(
            "servers", 5, "srv-{node_num}"
        )

        assert "groups" in blueprint
        assert "servers" in blueprint["groups"]
        assert blueprint["groups"]["servers"]["node_count"] == 5
        assert blueprint["groups"]["servers"]["name_template"] == "srv-{node_num}"

    def test_two_tier_blueprint(self):
        """Test two-tier blueprint template creates leaf-spine structure."""
        blueprint = BlueprintTemplates.two_tier_blueprint(
            tier1_count=6, tier2_count=4, pattern="mesh", link_capacity=25.0
        )

        # Validate groups
        assert len(blueprint["groups"]) == 2
        assert blueprint["groups"]["tier1"]["node_count"] == 6
        assert blueprint["groups"]["tier2"]["node_count"] == 4

        # Validate adjacency
        assert len(blueprint["adjacency"]) == 1
        adjacency = blueprint["adjacency"][0]
        assert adjacency["source"] == "/tier1"
        assert adjacency["target"] == "/tier2"
        assert adjacency["pattern"] == "mesh"
        assert adjacency["link_params"]["capacity"] == 25.0

    def test_three_tier_clos_blueprint(self):
        """Test three-tier Clos blueprint template."""
        blueprint = BlueprintTemplates.three_tier_clos_blueprint(
            leaf_count=8, spine_count=4, super_spine_count=2, link_capacity=40.0
        )

        # Validate groups
        assert len(blueprint["groups"]) == 3
        assert blueprint["groups"]["leaf"]["node_count"] == 8
        assert blueprint["groups"]["spine"]["node_count"] == 4
        assert blueprint["groups"]["super_spine"]["node_count"] == 2

        # Validate adjacency patterns
        assert len(blueprint["adjacency"]) == 2
        # Should have leaf->spine and spine->super_spine connections


@pytest.mark.slow
class TestFailurePolicyTemplates:
    """Tests demonstrating failure policy templates."""

    def test_single_link_failure_template(self):
        """Test single link failure policy template."""
        policy = FailurePolicyTemplates.single_link_failure()

        assert policy["attrs"]["name"] == "single_link_failure"
        assert len(policy["rules"]) == 1

        rule = policy["rules"][0]
        assert rule["entity_scope"] == "link"
        assert rule["rule_type"] == "choice"
        assert rule["count"] == 1

    def test_multiple_failure_template(self):
        """Test multiple failure policy template."""
        policy = FailurePolicyTemplates.multiple_failure("node", 3)

        assert policy["attrs"]["name"] == "multiple_node_failure"
        assert len(policy["rules"]) == 1

        rule = policy["rules"][0]
        assert rule["entity_scope"] == "node"
        assert rule["count"] == 3

    def test_risk_group_failure_template(self):
        """Test risk group failure policy template."""
        policy = FailurePolicyTemplates.risk_group_failure("datacenter_a")

        assert policy["attrs"]["name"] == "datacenter_a_failure"
        assert policy["fail_risk_groups"] is True
        assert len(policy["rules"]) == 1

        rule = policy["rules"][0]
        assert rule["entity_scope"] == "link"
        assert rule["rule_type"] == "conditional"
        assert "datacenter_a" in rule["conditions"][0]


@pytest.mark.slow
class TestTrafficDemandTemplates:
    """Tests demonstrating traffic demand templates."""

    def test_all_to_all_uniform_demands(self):
        """Test all-to-all uniform traffic demand template."""
        nodes = ["A", "B", "C"]
        demands = TrafficDemandTemplates.all_to_all_uniform(nodes, demand_value=15.0)

        # 3 nodes = 3*2 = 6 demands (excluding self-demands)
        assert len(demands) == 6

        # Validate demand structure
        for demand in demands:
            assert demand["demand"] == 15.0
            assert demand["source_path"] != demand["sink_path"]  # No self-demands

    def test_star_traffic_pattern(self):
        """Test star traffic pattern template."""
        center = "HUB"
        leaves = ["A", "B", "C"]
        demands = TrafficDemandTemplates.star_traffic(center, leaves, demand_value=10.0)

        # 3 leaves * 2 directions = 6 demands
        assert len(demands) == 6

        # Half should be leaves->center, half center->leaves
        to_center = [d for d in demands if d["sink_path"] == center]
        from_center = [d for d in demands if d["source_path"] == center]
        assert len(to_center) == 3
        assert len(from_center) == 3

    def test_random_demands_reproducibility(self):
        """Test that random demands are reproducible with same seed."""
        nodes = ["A", "B", "C", "D"]

        demands1 = TrafficDemandTemplates.random_demands(nodes, 5, seed=42)
        demands2 = TrafficDemandTemplates.random_demands(nodes, 5, seed=42)

        # Should be identical with same seed
        assert demands1 == demands2
        assert len(demands1) == 5

    def test_hotspot_traffic_pattern(self):
        """Test hotspot traffic pattern template."""
        hotspots = ["HOT1", "HOT2"]
        others = ["A", "B", "C"]
        demands = TrafficDemandTemplates.hotspot_traffic(
            hotspots, others, hotspot_demand=50.0, normal_demand=5.0
        )

        # Should have high-demand traffic to hotspots and normal inter-node traffic
        hotspot_demands = [d for d in demands if d["sink_path"] in hotspots]
        normal_demands = [d for d in demands if d["sink_path"] not in hotspots]

        assert len(hotspot_demands) > 0
        assert len(normal_demands) > 0

        # Validate demand values
        for demand in hotspot_demands:
            assert demand["demand"] == 50.0
        for demand in normal_demands:
            assert demand["demand"] == 5.0


@pytest.mark.slow
class TestWorkflowTemplates:
    """Tests demonstrating workflow templates."""

    def test_basic_build_workflow(self):
        """Test basic build workflow template."""
        workflow = WorkflowTemplates.basic_build_workflow()

        assert len(workflow) == 1
        assert workflow[0]["step_type"] == "BuildGraph"
        assert workflow[0]["name"] == "build_graph"

    def test_capacity_analysis_workflow(self):
        """Test capacity analysis workflow template."""
        workflow = WorkflowTemplates.capacity_analysis_workflow(
            "source_pattern", "sink_pattern", modes=["combine", "pairwise"]
        )

        assert len(workflow) == 3  # BuildGraph + 2 CapacityProbe steps
        assert workflow[0]["step_type"] == "BuildGraph"
        assert workflow[1]["step_type"] == "CapacityProbe"
        assert workflow[2]["step_type"] == "CapacityProbe"

        # Different modes
        assert workflow[1]["mode"] == "combine"
        assert workflow[2]["mode"] == "pairwise"

    def test_comprehensive_analysis_workflow(self):
        """Test comprehensive analysis workflow template."""
        workflow = WorkflowTemplates.comprehensive_analysis_workflow("src", "dst")

        assert len(workflow) == 4  # BuildGraph + multiple analysis steps
        step_types = [step["step_type"] for step in workflow]
        assert "BuildGraph" in step_types
        assert "CapacityProbe" in step_types
        assert "CapacityEnvelopeAnalysis" in step_types


@pytest.mark.slow
class TestScenarioTemplateBuilder:
    """Tests demonstrating the high-level scenario template builder."""

    def test_linear_backbone_scenario(self):
        """Test building a complete linear backbone scenario."""
        cities = ["NYC", "CHI", "DEN", "SFO"]
        yaml_content = (
            ScenarioTemplateBuilder("test_backbone", "1.0")
            .with_linear_backbone(cities, link_capacity=100.0)
            .with_uniform_traffic(cities, demand_value=25.0)
            .with_single_link_failures()
            .with_capacity_analysis("NYC", "SFO")
            .build()
        )

        # Parse and validate the generated scenario
        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        # Validate network structure
        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        assert len(graph.nodes) == 4
        assert len(graph.edges) == 6  # 3 physical links * 2 directions

    def test_clos_fabric_scenario(self):
        """Test building a scenario with Clos fabric blueprint."""
        yaml_content = (
            ScenarioTemplateBuilder("test_clos", "1.0")
            .with_clos_fabric("fabric1", leaf_count=4, spine_count=2)
            .with_capacity_analysis("fabric1/tier1/.*", "fabric1/tier2/.*")
            .build()
        )

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        # 4 leaf + 2 spine = 6 nodes
        assert len(graph.nodes) == 6


@pytest.mark.slow
class TestCommonScenarios:
    """Tests demonstrating pre-built common scenario templates."""

    def test_simple_linear_with_failures(self):
        """Test simple linear scenario with failures."""
        yaml_content = CommonScenarios.simple_linear_with_failures(node_count=5)

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        # Validate basic structure
        assert len(graph.nodes) == 5
        assert len(graph.edges) == 8  # 4 physical links * 2 directions

        # Should have failure policy
        policy = scenario.failure_policy_set.get_default_policy()
        assert policy is not None
        assert len(policy.rules) == 1

    def test_us_backbone_network(self):
        """Test US backbone network scenario."""
        yaml_content = CommonScenarios.us_backbone_network()

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        # Should have 8 major cities
        assert len(graph.nodes) == 8

        # Should have coordinates for visualization
        for node_name in ["NYC", "SFO", "CHI"]:
            if node_name in scenario.network.nodes:
                node = scenario.network.nodes[node_name]
                assert "coords" in node.attrs

    def test_minimal_test_scenario(self):
        """Test minimal scenario for basic testing."""
        yaml_content = CommonScenarios.minimal_test_scenario()

        scenario = Scenario.from_yaml(yaml_content)
        scenario.run()

        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        # Minimal: 3 nodes, 2 links
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 4  # 2 physical links * 2 directions


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
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

        assert len(graph.nodes) >= 3  # At least backbone nodes
        assert scenario.failure_policy_set.get_default_policy() is not None

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

            graph = scenario.results.get("build_graph", "graph")
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
            {"source_path": "SEA", "sink_path": "JFK", "demand": 50},
            {"source_path": "SFO", "sink_path": "DCA", "demand": 50},
            {"source_path": "SEA", "sink_path": "DCA", "demand": 50},
            {"source_path": "SFO", "sink_path": "JFK", "demand": 50},
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
        graph = scenario.results.get("build_graph", "graph")
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
            {"source_path": "SEA", "sink_path": "JFK", "demand": 50},
            {"source_path": "SFO", "sink_path": "DCA", "demand": 50},
            {"source_path": "SEA", "sink_path": "DCA", "demand": 50},
            {"source_path": "SFO", "sink_path": "JFK", "demand": 50},
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
        graph = scenario.results.get("build_graph", "graph")
        helper.set_graph(graph)

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
                "step_type": "CapacityProbe",
                "name": "capacity_probe",
                "source_path": "my_clos1/b.*/t1",
                "sink_path": "my_clos2/b.*/t1",
                "mode": "combine",
                "probe_reverse": True,
                "shortest_path": True,
                "flow_placement": "PROPORTIONAL",
            },
            {
                "step_type": "CapacityProbe",
                "name": "capacity_probe2",
                "source_path": "my_clos1/b.*/t1",
                "sink_path": "my_clos2/b.*/t1",
                "mode": "combine",
                "probe_reverse": True,
                "shortest_path": True,
                "flow_placement": "EQUAL_BALANCED",
            },
        ]
        builder.builder.data["workflow"] = workflow

        # Test the template-based scenario
        scenario = builder.builder.build_scenario()
        scenario.run()

        helper = create_scenario_helper(scenario)
        graph = scenario.results.get("build_graph", "graph")
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
            graph = scenario.results.get("build_graph", "graph")

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
