"""Tests for monte_carlo.functions module."""

from unittest.mock import MagicMock, patch

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.monte_carlo.functions import (
    demand_placement_analysis,
    max_flow_analysis,
    sensitivity_analysis,
)


class TestMaxFlowAnalysis:
    """Test max_flow_analysis function."""

    def test_max_flow_analysis_basic(self) -> None:
        """Test basic max_flow_analysis functionality."""
        # Mock NetworkView
        mock_network_view = MagicMock()
        # max_flow returns a dict, not a list
        mock_network_view.max_flow.return_value = {
            ("datacenter", "edge"): 100.0,
            ("edge", "datacenter"): 80.0,
        }

        result = max_flow_analysis(
            network_view=mock_network_view,
            source_regex="datacenter.*",
            sink_regex="edge.*",
            mode="combine",
        )

        # Verify function called NetworkView.max_flow with correct parameters
        mock_network_view.max_flow.assert_called_once_with(
            "datacenter.*",
            "edge.*",
            mode="combine",
            shortest_path=False,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        # Verify return format
        assert result == [
            ("datacenter", "edge", 100.0),
            ("edge", "datacenter", 80.0),
        ]

    def test_max_flow_analysis_with_optional_params(self) -> None:
        """Test max_flow_analysis with optional parameters."""
        mock_network_view = MagicMock()
        mock_network_view.max_flow.return_value = {("A", "B"): 50.0}

        result = max_flow_analysis(
            network_view=mock_network_view,
            source_regex="A.*",
            sink_regex="B.*",
            mode="pairwise",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            extra_param="ignored",
        )

        mock_network_view.max_flow.assert_called_once_with(
            "A.*",
            "B.*",
            mode="pairwise",
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
        )

        assert result == [("A", "B", 50.0)]

    def test_max_flow_analysis_empty_result(self) -> None:
        """Test max_flow_analysis with empty result."""
        mock_network_view = MagicMock()
        mock_network_view.max_flow.return_value = {}

        result = max_flow_analysis(
            network_view=mock_network_view,
            source_regex="nonexistent.*",
            sink_regex="also_nonexistent.*",
        )

        assert result == []


class TestDemandPlacementAnalysis:
    """Test demand_placement_analysis function."""

    def test_demand_placement_analysis_basic(self) -> None:
        """Test basic demand_placement_analysis functionality."""
        mock_network_view = MagicMock()

        # Mock TrafficManager and its behavior
        with (
            patch("ngraph.monte_carlo.functions.TrafficManager") as MockTrafficManager,
            patch(
                "ngraph.monte_carlo.functions.TrafficMatrixSet"
            ) as MockTrafficMatrixSet,
            patch("ngraph.monte_carlo.functions.TrafficDemand") as MockTrafficDemand,
        ):
            # Setup mock demands
            mock_demand1 = MagicMock()
            mock_demand1.volume = 100.0
            mock_demand1.placed_demand = 80.0
            mock_demand1.priority = 0

            mock_demand2 = MagicMock()
            mock_demand2.volume = 50.0
            mock_demand2.placed_demand = 50.0
            mock_demand2.priority = 1

            MockTrafficDemand.side_effect = [mock_demand1, mock_demand2]

            # Setup mock TrafficManager
            mock_tm = MockTrafficManager.return_value
            mock_tm.demands = [mock_demand1, mock_demand2]
            mock_tm.place_all_demands.return_value = 130.0

            # Setup mock TrafficMatrixSet
            mock_tms = MockTrafficMatrixSet.return_value

            demands_config = [
                {
                    "source_path": "A",
                    "sink_path": "B",
                    "demand": 100.0,
                    "mode": "full_mesh",
                    "priority": 0,
                },
                {
                    "source_path": "C",
                    "sink_path": "D",
                    "demand": 50.0,
                    "priority": 1,
                },
            ]

            result = demand_placement_analysis(
                network_view=mock_network_view,
                demands_config=demands_config,
                placement_rounds=25,
            )

            # Verify TrafficDemand creation
            assert MockTrafficDemand.call_count == 2
            MockTrafficDemand.assert_any_call(
                source_path="A",
                sink_path="B",
                demand=100.0,
                mode="full_mesh",
                flow_policy_config=None,
                priority=0,
            )

            # Verify TrafficManager setup
            MockTrafficManager.assert_called_once_with(
                network=mock_network_view,
                traffic_matrix_set=mock_tms,
                matrix_name="main",
            )

            mock_tm.build_graph.assert_called_once()
            mock_tm.expand_demands.assert_called_once()
            mock_tm.place_all_demands.assert_called_once_with(placement_rounds=25)

            # Verify results structure
            assert "total_placed" in result
            assert "priority_results" in result
            assert result["total_placed"] == 130.0

            priority_results = result["priority_results"]
            assert 0 in priority_results
            assert 1 in priority_results

            # Check priority 0 results - note: field is 'demand_count', not 'count'
            p0_results = priority_results[0]
            assert p0_results["total_volume"] == 100.0
            assert p0_results["placed_volume"] == 80.0
            assert p0_results["placement_ratio"] == 0.8
            assert p0_results["demand_count"] == 1

            # Check priority 1 results
            p1_results = priority_results[1]
            assert p1_results["total_volume"] == 50.0
            assert p1_results["placed_volume"] == 50.0
            assert p1_results["placement_ratio"] == 1.0
            assert p1_results["demand_count"] == 1


class TestSensitivityAnalysis:
    """Test sensitivity_analysis function."""

    def test_sensitivity_analysis_basic(self) -> None:
        """Test basic sensitivity_analysis functionality."""
        mock_network_view = MagicMock()

        # Mock sensitivity_analysis result with nested dict structure
        mock_sensitivity_result = {
            ("datacenter", "edge"): {
                ("node", "A", "type"): 0.15,
                ("link", "A", "B"): 0.08,
            },
            ("edge", "datacenter"): {
                ("node", "B", "type"): 0.12,
                ("link", "B", "C"): 0.05,
            },
        }
        mock_network_view.sensitivity_analysis.return_value = mock_sensitivity_result

        result = sensitivity_analysis(
            network_view=mock_network_view,
            source_regex="datacenter.*",
            sink_regex="edge.*",
            mode="combine",
        )

        # Verify function called NetworkView.sensitivity_analysis with correct parameters
        mock_network_view.sensitivity_analysis.assert_called_once_with(
            "datacenter.*",
            "edge.*",
            mode="combine",
            shortest_path=False,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        # Verify result format conversion
        expected_result = {
            "datacenter->edge": {
                "('node', 'A', 'type')": 0.15,
                "('link', 'A', 'B')": 0.08,
            },
            "edge->datacenter": {
                "('node', 'B', 'type')": 0.12,
                "('link', 'B', 'C')": 0.05,
            },
        }
        assert result == expected_result

    def test_sensitivity_analysis_empty_result(self) -> None:
        """Test sensitivity_analysis with empty result."""
        mock_network_view = MagicMock()
        mock_network_view.sensitivity_analysis.return_value = {}

        result = sensitivity_analysis(
            network_view=mock_network_view,
            source_regex="nonexistent.*",
            sink_regex="also_nonexistent.*",
        )

        assert result == {}
