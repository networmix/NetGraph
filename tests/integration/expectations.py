"""
Test expectations for NetGraph integration test scenarios.

Expected node counts, edge counts and named elements for each scenario,
derived from the scenario YAML and blueprint expansion rules. The validation
helpers compare built graphs against these values.
"""

from .helpers import NetworkExpectations

# Physical link counts per scenario
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
    count=6,
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
    count=sum(SCENARIO_2_NODE_BREAKDOWN.values()),
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
    count=_calculate_scenario_3_total_nodes(),
    edge_count=SCENARIO_3_PHYSICAL_LINKS * DEFAULT_BIDIRECTIONAL_MULTIPLIER,
    specific_nodes=set(),  # All nodes generated from blueprints
    blueprint_expansions={
        # Each Clos fabric should expand to exactly 32 nodes
        "my_clos1/": 32,
        "my_clos2/": 32,
    },
)


# Scenario 4: Advanced DSL features with complex data center fabric
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
    - 1 rack is disabled (dc2_podb_rack2) but still included in graph with disabled=True

    Returns:
        Expected total node count for scenario 4.
    """
    b = SCENARIO_4_NODE_BREAKDOWN

    # Calculate rack nodes: 2 DCs × 2 pods × 2 racks × 9 nodes/rack = 72
    rack_nodes = b["dcs"] * b["pods_per_dc"] * b["racks_per_pod"] * b["nodes_per_rack"]

    # Calculate fabric nodes: 2 DCs × (2 leaf + 2 spine) = 8
    fabric_nodes = b["dcs"] * (b["leaf_switches_per_dc"] + b["spine_switches_per_dc"])

    # Note: Disabled nodes are still included in the graph (with disabled=True attribute)
    # They are not subtracted from the total count
    total = rack_nodes + fabric_nodes

    return total  # 72 + 8 = 80


def _calculate_scenario_4_total_links() -> int:
    """
    Calculate total directed edges for scenario 4.

    BuildGraph adds a forward and a reverse edge for each link. The scenario
    has 92 physical links: 64 server-to-ToR, 16 ToR-to-leaf, 8 leaf-to-spine
    and 4 inter-DC spine links.

    Returns:
        Total directed edge count.
    """
    physical_links = 92
    return physical_links * DEFAULT_BIDIRECTIONAL_MULTIPLIER


SCENARIO_4_EXPECTATIONS = NetworkExpectations(
    count=_calculate_scenario_4_total_nodes(),  # Includes the disabled rack
    edge_count=_calculate_scenario_4_total_links(),  # 92 links * 2 directions
    specific_nodes=set(),  # All nodes generated from blueprints and expansion
    blueprint_expansions={
        "dc1_poda_rack01/": 9,  # 1 tor + 8 servers per rack
        "dc1_poda_rack02/": 9,
        "dc2_fabric/leaf/": 2,  # 2 leaf switches per DC fabric
        "dc2_fabric/spine/": 2,  # 2 spine switches
    },
)

SCENARIO_4_COMPONENT_EXPECTATIONS = {
    "total_components": 3,  # ToRSwitch48p, SpineSwitch32p, ServerNode
    "tor_switches": "ToRSwitch48p",
    "spine_switches": "SpineSwitch32p",
    "servers": "ServerNode",
}

# Uses fiber/facility domain model for risk groups
# Note: Only top-level risk groups are listed; children are nested inside parents
SCENARIO_4_RISK_GROUP_EXPECTATIONS = {
    "risk_groups": [
        "Building_DC1",
        "Building_DC2",
        "Room_DC1_Spine",
        "Room_DC2_Spine",
        "CoolingZone_DC1_R1_CZA",
        "PowerZone_DC1_Leaf",
        "PowerZone_DC2_Leaf",
        "Conduit_DC1_DC2_C1",
        "Path_DC1_DC2",
    ],
    "hierarchical_groups": True,  # Has nested risk group structure
}

SCENARIO_4_TRAFFIC_EXPECTATIONS = {
    "default_matrix": 2,  # 2 traffic demands in default matrix
    "hpc_workload_matrix": 1,  # 1 HPC traffic demand
    "total_matrices": 2,  # default + hpc_workload
}

SCENARIO_4_FAILURE_POLICY_EXPECTATIONS = {
    "total_policies": 3,  # single_link_failure, single_node_failure, default
    "risk_group_policies": 0,  # No policy uses risk groups
    "conditional_policies": 0,  # No policy uses conditions
}
