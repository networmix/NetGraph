from __future__ import annotations

from unittest.mock import MagicMock, patch

from ngraph.monte_carlo.functions import demand_placement_analysis


def test_demand_placement_analysis_includes_flow_details_costs_and_edges() -> None:
    mock_network_view = MagicMock()

    with (
        patch("ngraph.monte_carlo.functions.TrafficManager") as MockTrafficManager,
        patch("ngraph.monte_carlo.functions.TrafficMatrixSet"),
        patch("ngraph.monte_carlo.functions.TrafficDemand") as MockTrafficDemand,
    ):
        # Two demands with flow_policy flows including placed_flow and path_bundle
        demand1 = MagicMock()
        demand1.volume = 10.0
        demand1.placed_demand = 8.0
        demand1.priority = 0
        # Flow objects under policy
        flow_a = MagicMock()
        flow_a.placed_flow = 5.0
        flow_a.path_bundle.cost = 2.0
        flow_a.path_bundle.edges = {"e1"}
        flow_b = MagicMock()
        flow_b.placed_flow = 3.0
        flow_b.path_bundle.cost = 3.0
        flow_b.path_bundle.edges = {"e2"}
        demand1.flow_policy.flows = {1: flow_a, 2: flow_b}

        demand2 = MagicMock()
        demand2.volume = 4.0
        demand2.placed_demand = 4.0
        demand2.priority = 1
        demand2.flow_policy.flows = {}

        MockTrafficDemand.side_effect = [demand1, demand2]
        mock_tm = MockTrafficManager.return_value
        mock_tm.demands = [demand1, demand2]

        demands_config = [
            {
                "source_path": "A",
                "sink_path": "B",
                "demand": 10.0,
                "mode": "pairwise",
                "priority": 0,
            },
            {
                "source_path": "C",
                "sink_path": "D",
                "demand": 4.0,
                "priority": 1,
            },
        ]

        result = demand_placement_analysis(
            network_view=mock_network_view,
            demands_config=demands_config,
            placement_rounds=1,
            include_flow_details=True,
            include_used_edges=True,
        )

        # Validate cost_distribution aggregated per demand path_bundle cost
        entries = list(result.flows)
        e0 = entries[0]
        if e0.demand != 10.0:
            e0 = entries[1]
        cd = e0.cost_distribution
        assert cd.get(2.0) == 5.0 and cd.get(3.0) == 3.0
        assert e0.data.get("edges_kind") == "used"
        # Edges collected across flows
        assert set(e0.data.get("edges", [])) == {"e1", "e2"}
