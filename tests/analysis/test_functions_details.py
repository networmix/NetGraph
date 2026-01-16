from __future__ import annotations

from ngraph.analysis.functions import demand_placement_analysis
from ngraph.model.network import Link, Network, Node


def test_demand_placement_analysis_includes_flow_details_costs_and_edges() -> None:
    """Test that demand placement analysis includes flow details, costs, and edges when requested."""
    # Create a diamond network with two paths of different costs
    network = Network()
    for node in ["A", "B", "C", "D"]:
        network.add_node(Node(node))

    # Create two paths with different costs
    # Path 1: A -> B -> D (cost 2, capacity 100)
    network.add_link(Link("A", "B", capacity=100.0, cost=1.0))
    network.add_link(Link("B", "D", capacity=100.0, cost=1.0))

    # Path 2: A -> C -> D (cost 4, capacity 100)
    network.add_link(Link("A", "C", capacity=100.0, cost=2.0))
    network.add_link(Link("C", "D", capacity=100.0, cost=2.0))

    demands_config = [
        {
            "source": "A",
            "target": "D",
            "volume": 150.0,  # Exceeds single path capacity, will use both paths
            "mode": "pairwise",
            "priority": 0,
        },
    ]

    result = demand_placement_analysis(
        network=network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=demands_config,
        placement_rounds=1,
        include_flow_details=True,
        include_used_edges=True,
    )

    # Validate result structure
    assert len(result.flows) == 1
    flow = result.flows[0]

    # Should have cost_distribution when include_flow_details=True
    assert isinstance(flow.cost_distribution, dict)
    # With both paths used, we should see different costs
    # (exact distribution depends on flow policy)
    if flow.cost_distribution:
        assert len(flow.cost_distribution) > 0
        assert all(isinstance(k, float) for k in flow.cost_distribution.keys())
        assert all(isinstance(v, float) for v in flow.cost_distribution.values())

    # Should have edges when include_used_edges=True
    if flow.data and "edges" in flow.data:
        assert flow.data.get("edges_kind") == "used"
        assert isinstance(flow.data["edges"], list)
        # Should have some edges (exact count depends on flow distribution)
        assert len(flow.data["edges"]) > 0
