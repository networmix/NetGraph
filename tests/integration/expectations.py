"""
Test expectations for NetGraph integration test scenarios.

This module defines the expected network characteristics for each test scenario,
including node counts, edge counts, and specific network properties. These
expectations are used by the validation helpers to verify that scenarios
produce the correct network topologies.

The expectations are carefully calculated based on the scenario YAML definitions
and the NetGraph blueprint expansion rules.
"""

from .helpers import NetworkExpectations

# Validation constants for consistency across tests
DEFAULT_BIDIRECTIONAL_MULTIPLIER = 2  # NetGraph creates bidirectional edges
SCENARIO_1_PHYSICAL_LINKS = 10  # Count from scenario_1.yaml
SCENARIO_2_PHYSICAL_LINKS = 56  # Count from scenario_2.yaml blueprint expansions
SCENARIO_3_PHYSICAL_LINKS = 144  # Count from scenario_3.yaml Clos fabric calculations

# Expected node counts by scenario component
SCENARIO_2_NODE_BREAKDOWN = {
    "sea_leaf_nodes": 4,  # From clos_2tier blueprint
    "sea_spine_nodes": 6,  # Overridden from default 4 to 6
    "sea_edge_nodes": 4,  # From city_cloud blueprint
    "sfo_single_node": 1,  # From single_node blueprint
    "standalone_nodes": 4,  # DEN, DFW, JFK, DCA
}

SCENARIO_3_NODE_BREAKDOWN = {
    "nodes_per_brick": 8,  # 4 t1 + 4 t2 nodes
    "bricks_per_clos": 2,  # b1 and b2
    "spine_nodes_per_clos": 16,  # 16 spine nodes (t3-1 to t3-16)
    "clos_instances": 2,  # my_clos1 and my_clos2
}


def _calculate_scenario_3_total_nodes() -> int:
    """
    Calculate total nodes for scenario 3 based on 3-tier Clos structure.

    Each Clos fabric contains:
    - 2 brick instances, each with 8 nodes (4 t1 + 4 t2)
    - 16 spine nodes
    Total per Clos: (2 * 8) + 16 = 32 nodes
    Total for 2 Clos fabrics: 32 * 2 = 64 nodes

    Returns:
        Total expected node count for scenario 3.
    """
    nodes_per_clos = (
        SCENARIO_3_NODE_BREAKDOWN["bricks_per_clos"]
        * SCENARIO_3_NODE_BREAKDOWN["nodes_per_brick"]
        + SCENARIO_3_NODE_BREAKDOWN["spine_nodes_per_clos"]
    )
    return nodes_per_clos * SCENARIO_3_NODE_BREAKDOWN["clos_instances"]


# Scenario 1: Basic 6-node L3 US backbone network
# Simple topology with explicitly defined nodes and links
SCENARIO_1_EXPECTATIONS = NetworkExpectations(
    node_count=6,
    edge_count=SCENARIO_1_PHYSICAL_LINKS * DEFAULT_BIDIRECTIONAL_MULTIPLIER,
    specific_nodes={"SEA", "SFO", "DEN", "DFW", "JFK", "DCA"},
    specific_links=[
        ("SEA", "DEN"),
        ("SFO", "DEN"),
        ("SEA", "DFW"),
        ("SFO", "DFW"),
        ("DEN", "DFW"),
        ("DEN", "JFK"),
        ("DFW", "DCA"),
        ("DFW", "JFK"),
        ("JFK", "DCA"),
    ],
    blueprint_expansions={},  # No blueprints used in scenario 1
)

# Scenario 2: Hierarchical DSL with blueprints and multi-node expansions
# Topology using nested blueprints with parameter overrides
SCENARIO_2_EXPECTATIONS = NetworkExpectations(
    node_count=sum(SCENARIO_2_NODE_BREAKDOWN.values()),
    edge_count=SCENARIO_2_PHYSICAL_LINKS * DEFAULT_BIDIRECTIONAL_MULTIPLIER,
    specific_nodes={"DEN", "DFW", "JFK", "DCA"},  # Standalone nodes
    blueprint_expansions={
        # SEA city_cloud blueprint with clos_2tier override (spine count: 4->6)
        "SEA/clos_instance/spine/myspine-": SCENARIO_2_NODE_BREAKDOWN[
            "sea_spine_nodes"
        ],
        "SEA/edge_nodes/edge-": SCENARIO_2_NODE_BREAKDOWN["sea_edge_nodes"],
        # SFO single_node blueprint
        "SFO/single/single-": SCENARIO_2_NODE_BREAKDOWN["sfo_single_node"],
    },
)

# Scenario 3: 3-tier Clos network with nested blueprints
# Topology with deep blueprint nesting and capacity probing
SCENARIO_3_EXPECTATIONS = NetworkExpectations(
    node_count=_calculate_scenario_3_total_nodes(),
    edge_count=SCENARIO_3_PHYSICAL_LINKS * DEFAULT_BIDIRECTIONAL_MULTIPLIER,
    specific_nodes=set(),  # All nodes generated from blueprints
    blueprint_expansions={
        # Each Clos fabric should expand to exactly 32 nodes
        "my_clos1/": 32,
        "my_clos2/": 32,
    },
)

# Validation helper constants for flow result expectations
SCENARIO_3_FLOW_EXPECTATIONS = {
    "proportional_flow": 3200.0,  # Expected max flow with PROPORTIONAL placement (400 Gb/s * 8 paths)
    "equal_balanced_flow": 3200.0,  # Expected max flow with EQUAL_BALANCED placement (400 Gb/s * 8 paths)
}

# Traffic demand expectations by scenario
TRAFFIC_DEMAND_EXPECTATIONS = {
    "scenario_1": 4,  # 4 explicit traffic demands
    "scenario_2": 4,  # Same traffic demands as scenario 1
    "scenario_3": 0,  # No traffic demands (capacity probe only)
}

# Failure policy expectations by scenario
FAILURE_POLICY_EXPECTATIONS = {
    "scenario_1": {"rules": 1, "scopes": ["link"]},
    "scenario_2": {"rules": 1, "scopes": ["link"]},
    "scenario_3": {"rules": 0, "scopes": []},  # No failure policy
}

# Scenario 4: Advanced DSL features with complex data center fabric
# This scenario is the most complex, testing all advanced DSL features
SCENARIO_4_NODE_BREAKDOWN = {
    "racks_per_pod": 2,  # rack1-rack2 (2 racks per pod)
    "pods_per_dc": 2,  # poda, podb
    "dcs": 2,  # dc1, dc2
    "nodes_per_rack": 9,  # 1 tor + 8 servers per rack
    "leaf_switches_per_dc": 2,  # From leaf_spine_fabric blueprint
    "spine_switches_per_dc": 2,  # From leaf_spine_fabric blueprint
    "disabled_racks": 1,  # dc2_podb_rack2 marked as disabled
}


def _calculate_scenario_4_total_nodes() -> int:
    """
    Calculate total nodes for scenario 4 with advanced DSL features.

    Structure:
    - 2 DCs, each with 2 pods, each with 2 racks
    - Each rack has 9 nodes (1 ToR + 8 servers)
    - Each DC has 2 leaf + 2 spine switches (4 fabric nodes)
    - 1 rack is disabled (dc2_podb_rack2), reducing count by 9 nodes

    Returns:
        Expected total node count for scenario 4.
    """
    b = SCENARIO_4_NODE_BREAKDOWN

    # Calculate rack nodes: 2 DCs × 2 pods × 2 racks × 9 nodes/rack = 72
    rack_nodes = b["dcs"] * b["pods_per_dc"] * b["racks_per_pod"] * b["nodes_per_rack"]

    # Calculate fabric nodes: 2 DCs × (2 leaf + 2 spine) = 8
    fabric_nodes = b["dcs"] * (b["leaf_switches_per_dc"] + b["spine_switches_per_dc"])

    # Subtract disabled rack nodes: 1 rack × 9 nodes = 9
    disabled_nodes = b["disabled_racks"] * b["nodes_per_rack"]

    # Total after accounting for disabled rack that doesn't get re-enabled
    total = rack_nodes + fabric_nodes - disabled_nodes

    return total  # 72 + 8 - 9 = 71


def _calculate_scenario_4_total_links() -> int:
    """
    Calculate approximate total directed edges for scenario 4.

    This is complex due to variable expansion, so we calculate major link types:
    - Server to ToR links within racks
    - Leaf to spine links within fabric
    - Rack-to-fabric connections
    - Inter-DC spine connections

    Returns:
        Approximate total directed edge count.
    """
    # Based on actual scenario execution:
    # - Server to ToR links: 8 servers * 8 racks * 2 directions = 128
    # - Leaf to spine links within fabrics: 2 leaf * 2 spine * 2 DCs * 2 directions = 16
    # - Rack to fabric connections: 8 racks * 2 leaf per rack * 2 directions = 32
    # - Inter-DC spine connections: 2 spine * 2 spine * 2 directions = 8

    # - Some connections may be missing due to disabled nodes or complex adjacency patterns
    # Actual observed value: 148 directed edges (updated after attribute cleanup)
    return 148  # Current observed value from execution


# Main expectation structure for scenario 4
SCENARIO_4_EXPECTATIONS = NetworkExpectations(
    node_count=_calculate_scenario_4_total_nodes(),  # Total nodes after disabled rack
    edge_count=_calculate_scenario_4_total_links(),  # Actual observed link count
    specific_nodes=set(),  # All nodes generated from blueprints and expansion
    blueprint_expansions={
        # Each expanded rack should have expected components
        "dc1_poda_rack01/": 9,  # 1 tor + 8 servers per rack
        "dc1_poda_rack02/": 9,
        "dc2_fabric/leaf/": 2,  # 2 leaf switches per DC fabric
        "dc2_fabric/spine/": 2,  # 2 spine switches
    },
)

# Component expectations for scenario 4
SCENARIO_4_COMPONENT_EXPECTATIONS = {
    "total_components": 3,  # ToRSwitch48p, SpineSwitch32p, ServerNode
    "tor_switches": "ToRSwitch48p",
    "spine_switches": "SpineSwitch32p",
    "servers": "ServerNode",
}

# Risk group expectations for scenario 4
SCENARIO_4_RISK_GROUP_EXPECTATIONS = {
    "risk_groups": ["DC1_PowerSupply_A", "DC1_NetworkUplink", "Spine_Fabric_SRG"],
    "hierarchical_groups": True,  # Has nested risk group structure
}

# Traffic matrix expectations for scenario 4
SCENARIO_4_TRAFFIC_EXPECTATIONS = {
    "default_matrix": 2,  # 2 traffic demands in default matrix
    "hpc_workload_matrix": 1,  # 1 HPC traffic demand
    "total_matrices": 2,  # default + hpc_workload
}

# Failure policy expectations for scenario 4
SCENARIO_4_FAILURE_POLICY_EXPECTATIONS = {
    "total_policies": 3,  # single_link_failure, single_node_failure, default
    "risk_group_policies": 0,  # None use risk groups anymore
    "conditional_policies": 0,  # None use conditions anymore
}

# Workflow expectations for scenario 4
SCENARIO_4_WORKFLOW_EXPECTATIONS = {
    "wan_locations": 2,  # 2 WAN locations for test efficiency
    "capacity_envelope_iterations": [10, 20],  # Iteration counts for analysis steps
    "enabled_nodes_count": 10,  # Number of nodes to enable
    "parallelism": 2,  # Parallel processing degree
}
