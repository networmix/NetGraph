"""Tests for monte_carlo.functions module."""

from unittest.mock import MagicMock, patch

from ngraph.algorithms.base import FlowPlacement
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
            {"src": "datacenter", "dst": "edge", "metric": "capacity", "value": 100.0},
            {"src": "edge", "dst": "datacenter", "metric": "capacity", "value": 80.0},
        ]

    def test_max_flow_analysis_with_summary(self) -> None:
        """Test include_flow_summary=True path and return shape."""
        mock_network_view = MagicMock()
        summary_obj_1 = {"min_cut_frequencies": {"('A','B')": 3}}
        summary_obj_2 = {"min_cut_frequencies": {"('B','A')": 1}}
        mock_network_view.max_flow_with_summary.return_value = {
            ("X", "Y"): (10.0, summary_obj_1),
            ("Y", "X"): (5.0, summary_obj_2),
        }

        result = max_flow_analysis(
            network_view=mock_network_view,
            source_regex="X.*",
            sink_regex="Y.*",
            include_flow_summary=True,
        )

        mock_network_view.max_flow_with_summary.assert_called_once_with(
            "X.*",
            "Y.*",
            mode="combine",
            shortest_path=False,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        fr_xy = next(fr for fr in result if fr["src"] == "X" and fr["dst"] == "Y")
        assert fr_xy["metric"] == "capacity" and fr_xy["value"] == 10.0
        assert isinstance(fr_xy.get("stats"), dict)
        fr_yx = next(fr for fr in result if fr["src"] == "Y" and fr["dst"] == "X")
        assert fr_yx["metric"] == "capacity" and fr_yx["value"] == 5.0

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

        assert result == [{"src": "A", "dst": "B", "metric": "capacity", "value": 50.0}]

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
                    "mode": "pairwise",
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
                mode="pairwise",
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

            # Verify results structure (dict with per-demand records and summary)
            assert isinstance(result, dict)
            assert "demands" in result and "summary" in result
            demands = result["demands"]
            assert isinstance(demands, list) and len(demands) == 2
            dr = sorted(demands, key=lambda x: x["priority"])  # type: ignore[arg-type]
            assert dr[0]["placement_ratio"] == 0.8 and dr[0]["priority"] == 0
            assert dr[1]["placement_ratio"] == 1.0 and dr[1]["priority"] == 1
            summary = result["summary"]
            assert summary["total_offered_gbps"] == 150.0
            assert summary["total_placed_gbps"] == 130.0
            from pytest import approx

            assert summary["overall_ratio"] == approx(130.0 / 150.0)

    def test_demand_placement_analysis_zero_total_demand(self) -> None:
        """Handles zero total demand without division by zero."""
        mock_network_view = MagicMock()

        with (
            patch("ngraph.monte_carlo.functions.TrafficManager") as MockTrafficManager,
            patch(
                "ngraph.monte_carlo.functions.TrafficMatrixSet"
            ) as MockTrafficMatrixSet,
            patch("ngraph.monte_carlo.functions.TrafficDemand") as MockTrafficDemand,
        ):
            # Create a single zero-volume demand
            mock_demand = MagicMock()
            mock_demand.volume = 0.0
            mock_demand.placed_demand = 0.0
            mock_demand.priority = 0
            MockTrafficDemand.return_value = mock_demand

            mock_tm = MockTrafficManager.return_value
            mock_tm.demands = [mock_demand]
            mock_tm.place_all_demands.return_value = 0.0

            _ = MockTrafficMatrixSet.return_value

            demands_config = [
                {
                    "source_path": "A",
                    "sink_path": "B",
                    "demand": 0.0,
                }
            ]

            result = demand_placement_analysis(
                network_view=mock_network_view,
                demands_config=demands_config,
                placement_rounds=1,
            )

            assert isinstance(result, dict)
            assert "demands" in result and "summary" in result
            demands = result["demands"]
            assert isinstance(demands, list) and len(demands) == 1
            assert demands[0]["placement_ratio"] == 0.0
            summary = result["summary"]
            assert summary["total_offered_gbps"] == 0.0
            assert summary["total_placed_gbps"] == 0.0
            assert summary["overall_ratio"] == 1.0


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
