"""Tests for CapacityMatrixAnalyzer."""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from ngraph.monte_carlo.results import CapacityEnvelopeResults
from ngraph.results_artifacts import CapacityEnvelope
from ngraph.workflow.analysis.capacity_matrix import CapacityMatrixAnalyzer


@pytest.fixture
def mock_envelope_data() -> Dict[str, Any]:
    """Create mock envelope data for testing."""
    return {
        "A->B": {
            "min": 5.0,
            "max": 10.0,
            "mean": 7.5,
            "frequencies": {"5.0": 2, "10.0": 3},
            "stdev": 2.5,
            "total_samples": 5,
        },
        "B->C": {
            "min": 8.0,
            "max": 15.0,
            "mean": 12.0,
            "frequencies": {"8.0": 1, "12.0": 2, "15.0": 2},
            "stdev": 3.0,
            "total_samples": 5,
        },
        "A<->C": {
            "min": 3.0,
            "max": 6.0,
            "mean": 4.5,
            "frequencies": {"3.0": 1, "6.0": 4},
            "stdev": 1.5,
            "total_samples": 5,
        },
    }


@pytest.fixture
def mock_capacity_envelope_results(mock_envelope_data) -> CapacityEnvelopeResults:
    """Create mock CapacityEnvelopeResults for testing."""
    envelopes = {}
    for flow_key, data in mock_envelope_data.items():
        envelope = Mock(spec=CapacityEnvelope)
        envelope.to_dict.return_value = data
        envelope.mean_capacity = data["mean"]
        envelope.min_capacity = data["min"]
        envelope.max_capacity = data["max"]
        envelope.stdev_capacity = data["stdev"]
        envelope.total_samples = data["total_samples"]
        envelope.get_percentile = Mock(
            side_effect=lambda p, min_val=data["min"], max_val=data["max"]: min_val
            + (max_val - min_val) * p / 100
        )
        envelope.expand_to_values = Mock(
            return_value=[data["min"]] * 2 + [data["max"]] * 3
        )
        envelopes[flow_key] = envelope

    return CapacityEnvelopeResults(
        envelopes=envelopes,
        failure_patterns={},
        source_pattern="^A$",
        sink_pattern="^C$",
        mode="combine",
        iterations=5,
        metadata={},
    )


@pytest.fixture
def analyzer() -> CapacityMatrixAnalyzer:
    """Create CapacityMatrixAnalyzer instance."""
    return CapacityMatrixAnalyzer()


class TestCapacityMatrixAnalyzer:
    """Test suite for CapacityMatrixAnalyzer."""

    def test_get_description(self, analyzer):
        """Test get_description returns expected string."""
        description = analyzer.get_description()
        assert isinstance(description, str)
        assert "capacity envelope" in description.lower()
        assert "matrices" in description.lower()

    def test_parse_flow_path_directed(self, analyzer):
        """Test _parse_flow_path with directed flow."""
        result = analyzer._parse_flow_path("A->B")
        expected = {
            "source": "A",
            "destination": "B",
            "direction": "directed",
        }
        assert result == expected

    def test_parse_flow_path_bidirectional(self, analyzer):
        """Test _parse_flow_path with bidirectional flow."""
        result = analyzer._parse_flow_path("A<->B")
        expected = {
            "source": "A",
            "destination": "B",
            "direction": "bidirectional",
        }
        assert result == expected

    def test_parse_flow_path_with_whitespace(self, analyzer):
        """Test _parse_flow_path handles whitespace."""
        result = analyzer._parse_flow_path("  A  ->  B  ")
        expected = {
            "source": "A",
            "destination": "B",
            "direction": "directed",
        }
        assert result == expected

    def test_parse_flow_path_invalid(self, analyzer):
        """Test _parse_flow_path with invalid format."""
        result = analyzer._parse_flow_path("invalid_flow")
        assert result is None

        result = analyzer._parse_flow_path("")
        assert result is None

    def test_extract_capacity_value_number(self, analyzer):
        """Test _extract_capacity_value with numeric values."""
        assert analyzer._extract_capacity_value(42) == 42.0
        assert analyzer._extract_capacity_value(3.14) == 3.14
        assert analyzer._extract_capacity_value(0) == 0.0

    def test_extract_capacity_value_dict_with_max(self, analyzer):
        """Test _extract_capacity_value with dictionary containing max."""
        data = {"max": 15.5, "min": 5.0, "mean": 10.0}
        assert analyzer._extract_capacity_value(data) == 15.5

    def test_extract_capacity_value_dict_without_max(self, analyzer):
        """Test _extract_capacity_value with dictionary missing max."""
        data = {"min": 5.0, "mean": 10.0}
        assert analyzer._extract_capacity_value(data) is None

    def test_extract_capacity_value_invalid_types(self, analyzer):
        """Test _extract_capacity_value with invalid types."""
        assert analyzer._extract_capacity_value("string") is None
        assert analyzer._extract_capacity_value([1, 2, 3]) is None
        assert analyzer._extract_capacity_value(None) is None

    def test_extract_matrix_data(self, analyzer, mock_envelope_data):
        """Test _extract_matrix_data with valid envelope data."""
        result = analyzer._extract_matrix_data(mock_envelope_data)

        assert len(result) == 3

        # Check first flow (A->B)
        flow_ab = next(item for item in result if item["flow_path"] == "A->B")
        assert flow_ab["source"] == "A"
        assert flow_ab["destination"] == "B"
        assert flow_ab["capacity"] == 10.0  # max value
        assert flow_ab["direction"] == "directed"

        # Check bidirectional flow (A<->C)
        flow_ac = next(item for item in result if item["flow_path"] == "A<->C")
        assert flow_ac["direction"] == "bidirectional"

    def test_extract_matrix_data_empty(self, analyzer):
        """Test _extract_matrix_data with empty input."""
        result = analyzer._extract_matrix_data({})
        assert result == []

    def test_extract_matrix_data_invalid_flows(self, analyzer):
        """Test _extract_matrix_data filters invalid flows."""
        invalid_data = {
            "invalid_flow_format": {"max": 10.0},
            "A->B": {"no_max_field": True},
            "C->D": {"max": "invalid_number"},
        }
        result = analyzer._extract_matrix_data(invalid_data)
        assert result == []

    def test_create_capacity_matrix(self, analyzer):
        """Test _create_capacity_matrix creates proper pivot table."""
        matrix_data = [
            {"source": "A", "destination": "B", "capacity": 10.0},
            {"source": "A", "destination": "C", "capacity": 8.0},
            {"source": "B", "destination": "C", "capacity": 15.0},
        ]
        df = pd.DataFrame(matrix_data)
        result = analyzer._create_capacity_matrix(df)

        assert isinstance(result, pd.DataFrame)
        assert result.loc["A", "B"] == 10.0
        assert result.loc["A", "C"] == 8.0
        assert result.loc["B", "C"] == 15.0

        # The pivot table only includes sources and destinations that exist in the data
        # Missing values are filled with 0 for existing combinations
        assert len(result.index) >= 2  # A, B
        assert len(result.columns) >= 2  # B, C

    def test_calculate_statistics_with_data(self, analyzer):
        """Test _calculate_statistics with valid capacity matrix."""
        data = {"A": [0, 10, 8], "B": [0, 0, 15], "C": [0, 0, 0]}
        df = pd.DataFrame(data, index=["A", "B", "C"])

        stats = analyzer._calculate_statistics(df)

        assert stats["has_data"] is True
        # The method counts all numeric non-self-loop entries, not just non-zero
        assert stats["total_flows"] == 6  # A->B, A->C, B->A, B->C, C->A, C->B
        assert stats["num_sources"] == 3
        assert stats["num_destinations"] == 3
        assert stats["capacity_min"] == 8.0
        assert stats["capacity_max"] == 15.0
        assert stats["capacity_mean"] == pytest.approx(11.0, rel=1e-2)
        assert stats["flow_density"] == pytest.approx(100.0, rel=1e-2)  # 6/6 * 100

    def test_calculate_statistics_no_data(self, analyzer):
        """Test _calculate_statistics with empty matrix."""
        df = pd.DataFrame()
        stats = analyzer._calculate_statistics(df)
        assert stats["has_data"] is False

    def test_calculate_statistics_all_zeros(self, analyzer):
        """Test _calculate_statistics with all zero capacities."""
        data = {"A": [0, 0], "B": [0, 0]}
        df = pd.DataFrame(data, index=["A", "B"])
        stats = analyzer._calculate_statistics(df)
        assert stats["has_data"] is False

    def test_analyze_workflow_mode(self, analyzer, mock_envelope_data):
        """Test analyze method with workflow results format."""
        results = {"envelope_step": {"capacity_envelopes": mock_envelope_data}}

        analysis = analyzer.analyze(results, step_name="envelope_step")

        assert analysis["status"] == "success"
        assert analysis["step_name"] == "envelope_step"
        assert "matrix_data" in analysis
        assert "capacity_matrix" in analysis
        assert "statistics" in analysis
        assert "visualization_data" in analysis

        # Check matrix data structure
        assert len(analysis["matrix_data"]) == 3

        # Check statistics
        stats = analysis["statistics"]
        assert stats["has_data"] is True
        assert stats["total_flows"] > 0

    def test_analyze_missing_step_name(self, analyzer):
        """Test analyze method raises error when step_name is missing."""
        results = {"some_step": {"capacity_envelopes": {}}}

        with pytest.raises(ValueError, match="step_name required"):
            analyzer.analyze(results)

    def test_analyze_missing_step_data(self, analyzer):
        """Test analyze method raises error when step data is missing."""
        results = {}

        with pytest.raises(ValueError, match="No capacity envelope data found"):
            analyzer.analyze(results, step_name="nonexistent_step")

    def test_analyze_empty_envelopes(self, analyzer):
        """Test analyze method raises error when envelopes are empty."""
        results = {"envelope_step": {"capacity_envelopes": {}}}

        with pytest.raises(ValueError, match="No capacity envelope data found"):
            analyzer.analyze(results, step_name="envelope_step")

    def test_analyze_results_direct_mode(
        self, analyzer, mock_capacity_envelope_results
    ):
        """Test analyze_results method with CapacityEnvelopeResults object."""
        analysis = analyzer.analyze_results(mock_capacity_envelope_results)

        assert analysis["status"] == "success"
        assert analysis["step_name"] == "^A$->^C$"
        assert "matrix_data" in analysis
        assert "capacity_matrix" in analysis
        assert "statistics" in analysis
        assert "visualization_data" in analysis
        assert "envelope_results" in analysis

        # Verify original object is preserved
        assert analysis["envelope_results"] is mock_capacity_envelope_results

    def test_analyze_results_empty_envelopes(self, analyzer):
        """Test analyze_results raises error with empty envelopes."""
        empty_results = CapacityEnvelopeResults(
            envelopes={},
            failure_patterns={},
            source_pattern="A",
            sink_pattern="B",
            mode="combine",
            iterations=1,
            metadata={},
        )

        # The method raises RuntimeError, not ValueError, due to exception wrapping
        with pytest.raises(
            RuntimeError, match="Error analyzing capacity envelope results"
        ):
            analyzer.analyze_results(empty_results)

    @patch("matplotlib.pyplot.show")
    def test_display_capacity_distributions_single_flow(
        self, mock_show, analyzer, mock_capacity_envelope_results
    ):
        """Test display_capacity_distributions with single flow."""
        with patch("builtins.print") as mock_print:
            analyzer.display_capacity_distributions(
                mock_capacity_envelope_results, flow_key="A->B"
            )

            # Verify print statements were called
            mock_print.assert_called()
            mock_show.assert_called_once()

    @patch("matplotlib.pyplot.show")
    def test_display_capacity_distributions_all_flows(
        self, mock_show, analyzer, mock_capacity_envelope_results
    ):
        """Test display_capacity_distributions with all flows."""
        with patch("builtins.print") as mock_print:
            analyzer.display_capacity_distributions(mock_capacity_envelope_results)

            mock_print.assert_called()
            mock_show.assert_called_once()

    @patch("matplotlib.pyplot.show")
    def test_display_percentile_comparison(
        self, mock_show, analyzer, mock_capacity_envelope_results
    ):
        """Test display_percentile_comparison method."""
        with patch("builtins.print") as mock_print:
            analyzer.display_percentile_comparison(mock_capacity_envelope_results)

            mock_print.assert_called()
            mock_show.assert_called_once()

    def test_prepare_visualization_data(self, analyzer):
        """Test _prepare_visualization_data creates proper structure."""
        data = {"A": [0, 10, 8], "B": [5, 0, 15], "C": [3, 12, 0]}
        df = pd.DataFrame(data, index=["A", "B", "C"])

        viz_data = analyzer._prepare_visualization_data(df)

        # Convert numpy bool to Python bool for comparison
        assert bool(viz_data["has_data"]) is True
        assert viz_data["has_ranking_data"] is True
        assert isinstance(viz_data["matrix_display"], pd.DataFrame)
        assert isinstance(viz_data["capacity_ranking"], pd.DataFrame)

        # Check ranking is sorted by capacity (descending)
        ranking = viz_data["capacity_ranking"]
        assert len(ranking) > 0
        capacities = ranking["Capacity"].tolist()
        assert capacities == sorted(capacities, reverse=True)

    def test_format_dataframe_for_display(self, analyzer):
        """Test _format_dataframe_for_display applies proper formatting."""
        data = {"A": [1000.0, 2500.5], "B": [3000, 4200.7]}
        df = pd.DataFrame(data)

        formatted = analyzer._format_dataframe_for_display(df)

        # Check that large integers are formatted with commas
        assert "1,000" in str(formatted.iloc[0, 0])
        assert "3,000" in str(formatted.iloc[0, 1])  # Column B, row 0

        # Check that floats are formatted appropriately
        assert "2,500.5" in str(formatted.iloc[1, 0]) or "2,500.1" in str(
            formatted.iloc[1, 0]
        )

    def test_format_dataframe_empty(self, analyzer):
        """Test _format_dataframe_for_display with empty DataFrame."""
        df = pd.DataFrame()
        result = analyzer._format_dataframe_for_display(df)
        assert result.empty


class TestFlowAvailabilityAnalysis:
    """Test suite for flow availability analysis methods."""

    @pytest.fixture
    def flow_envelope_data(self) -> Dict[str, Any]:
        """Create envelope data with frequencies for flow availability testing."""
        return {
            "A->B": {
                "frequencies": {"5.0": 10, "8.0": 20, "10.0": 15},
                "max": 10.0,
                "mean": 7.5,
            },
            "B->C": {
                "frequencies": {"3.0": 5, "6.0": 15, "9.0": 25},
                "max": 9.0,
                "mean": 6.8,
            },
            # Self-loop that should be skipped
            "A->A": {
                "frequencies": {"12.0": 30},
                "max": 12.0,
                "mean": 12.0,
            },
        }

    def test_analyze_flow_availability(self, analyzer, flow_envelope_data):
        """Test analyze_flow_availability creates proper CDF analysis."""
        results = {"envelope_step": {"capacity_envelopes": flow_envelope_data}}

        analysis = analyzer.analyze_flow_availability(
            results, step_name="envelope_step"
        )

        assert analysis["status"] == "success"
        assert analysis["step_name"] == "envelope_step"
        assert "flow_cdf" in analysis
        assert "availability_curve" in analysis
        assert "statistics" in analysis
        assert "maximum_flow" in analysis
        assert analysis["skipped_self_loops"] == 1  # A->A should be skipped
        assert analysis["aggregated_flows"] == 2  # A->B and B->C

        # Verify CDF structure
        cdf = analysis["flow_cdf"]
        assert len(cdf) > 0
        assert all(isinstance(point, tuple) and len(point) == 2 for point in cdf)

        # Verify availability curve
        availability = analysis["availability_curve"]
        assert len(availability) > 0

    def test_analyze_flow_availability_missing_step_name(self, analyzer):
        """Test analyze_flow_availability raises error when step_name is missing."""
        results = {"some_step": {"capacity_envelopes": {}}}

        with pytest.raises(ValueError, match="step_name required"):
            analyzer.analyze_flow_availability(results)

    def test_analyze_flow_availability_no_envelopes(self, analyzer):
        """Test analyze_flow_availability raises error when no envelopes found."""
        results = {"envelope_step": {}}

        with pytest.raises(ValueError, match="No capacity envelopes found"):
            analyzer.analyze_flow_availability(results, step_name="envelope_step")

    def test_analyze_flow_availability_only_self_loops(self, analyzer):
        """Test analyze_flow_availability raises error when only self-loops present."""
        self_loop_data = {
            "A->A": {"frequencies": {"10.0": 5}, "max": 10.0},
            "B->B": {"frequencies": {"8.0": 3}, "max": 8.0},
        }
        results = {"envelope_step": {"capacity_envelopes": self_loop_data}}

        with pytest.raises(ValueError, match="All .* flows .* are self-loops"):
            analyzer.analyze_flow_availability(results, step_name="envelope_step")

    def test_analyze_flow_availability_invalid_frequency_data(self, analyzer):
        """Test analyze_flow_availability handles invalid frequency data."""
        invalid_data = {
            "A->B": {
                "frequencies": {"invalid": "not_a_number"},
                "max": 10.0,
            }
        }
        results = {"envelope_step": {"capacity_envelopes": invalid_data}}

        with pytest.raises(ValueError, match="Invalid capacity frequency data"):
            analyzer.analyze_flow_availability(results, step_name="envelope_step")

    def test_calculate_flow_statistics(self, analyzer):
        """Test _calculate_flow_statistics computes correct metrics."""
        samples = [3.0, 5.0, 7.0, 9.0, 11.0]
        maximum_flow = 11.0

        stats = analyzer._calculate_flow_statistics(samples, maximum_flow)

        assert stats["has_data"] is True
        assert stats["maximum_flow"] == 11.0
        assert stats["minimum_flow"] == 3.0
        assert stats["mean_flow"] == 7.0
        assert stats["median_flow"] == 7.0
        assert stats["total_samples"] == 5
        assert stats["relative_mean"] == pytest.approx(63.64, rel=1e-2)  # 7/11 * 100

    def test_calculate_flow_statistics_empty(self, analyzer):
        """Test _calculate_flow_statistics with empty samples."""
        stats = analyzer._calculate_flow_statistics([], 0)
        assert stats["has_data"] is False

    def test_prepare_flow_cdf_visualization_data(self, analyzer):
        """Test _prepare_flow_cdf_visualization_data creates proper structure."""
        flow_cdf = [(0.5, 0.2), (0.8, 0.6), (1.0, 1.0)]
        availability_curve = [(0.5, 0.8), (0.8, 0.4), (1.0, 0.0)]
        maximum_flow = 10.0

        viz_data = analyzer._prepare_flow_cdf_visualization_data(
            flow_cdf, availability_curve, maximum_flow
        )

        assert viz_data["has_data"] is True
        assert "cdf_data" in viz_data
        assert "percentile_data" in viz_data
        assert "reliability_thresholds" in viz_data
        assert "distribution_metrics" in viz_data

        # Check threshold calculations
        thresholds = viz_data["reliability_thresholds"]
        assert "99%" in thresholds
        assert "95%" in thresholds
        assert "50%" in thresholds

    def test_calculate_quartile_coefficient(self, analyzer):
        """Test _calculate_quartile_coefficient calculation."""
        values = [1, 2, 3, 4, 5, 6, 7, 8]
        result = analyzer._calculate_quartile_coefficient(values)

        # Q1 = values[2] = 3, Q3 = values[6] = 7
        # (Q3 - Q1) / (Q3 + Q1) = (7 - 3) / (7 + 3) = 4/10 = 0.4
        assert result == pytest.approx(0.4, rel=1e-2)

    def test_calculate_quartile_coefficient_small_sample(self, analyzer):
        """Test _calculate_quartile_coefficient with small sample."""
        values = [1, 2]
        result = analyzer._calculate_quartile_coefficient(values)
        assert result == 0.0

    @patch("builtins.print")
    @patch("matplotlib.pyplot.show")
    def test_analyze_and_display_flow_availability(
        self, mock_show, mock_print, analyzer, flow_envelope_data
    ):
        """Test analyze_and_display_flow_availability integration."""
        results = {"envelope_step": {"capacity_envelopes": flow_envelope_data}}

        # Should not raise an exception
        analyzer.analyze_and_display_flow_availability(
            results, step_name="envelope_step"
        )

        # Verify that print and show were called
        mock_print.assert_called()
        mock_show.assert_called()

    def test_analyze_and_display_flow_availability_missing_step(self, analyzer):
        """Test analyze_and_display_flow_availability raises error for missing step."""
        results = {}

        with pytest.raises(ValueError, match="No step name provided"):
            analyzer.analyze_and_display_flow_availability(results)


class TestErrorHandling:
    """Test suite for error handling and edge cases."""

    def test_analyze_with_exception_in_processing(self, analyzer):
        """Test analyze method handles exceptions in processing."""
        # Create data that will cause an exception during processing
        invalid_results = {
            "test_step": {"capacity_envelopes": {"invalid": "this will cause an error"}}
        }

        with pytest.raises(RuntimeError, match="Error analyzing capacity matrix"):
            analyzer.analyze(invalid_results, step_name="test_step")

    def test_analyze_results_with_exception(self, analyzer):
        """Test analyze_results method handles exceptions."""
        # Create a mock that will raise an exception
        mock_results = Mock(spec=CapacityEnvelopeResults)
        mock_results.envelopes = {"test": Mock()}
        mock_results.envelopes["test"].to_dict.side_effect = Exception("Mock error")
        mock_results.source_pattern = "A"
        mock_results.sink_pattern = "B"

        with pytest.raises(
            RuntimeError, match="Error analyzing capacity envelope results"
        ):
            analyzer.analyze_results(mock_results)

    @patch("builtins.print")
    def test_display_analysis_no_data(self, mock_print, analyzer):
        """Test display_analysis handles case with no data."""
        analysis = {
            "step_name": "test_step",
            "statistics": {"has_data": False},
            "visualization_data": {"has_data": False},
        }

        # Should not raise an exception
        analyzer.display_analysis(analysis)

        # Verify appropriate message was printed
        mock_print.assert_called()

    @patch("builtins.print")
    def test_analyze_and_display_step_missing_step_name(self, mock_print, analyzer):
        """Test analyze_and_display_step handles missing step_name."""
        results = {}

        # Should print error message, not raise exception
        analyzer.analyze_and_display_step(results)

        mock_print.assert_called()
        # Check that error message was printed
        calls = [str(call) for call in mock_print.call_args_list]
        assert any("❌" in call for call in calls)

    def test_analyze_flow_availability_all_zero_flows(self, analyzer):
        """Test analyze_flow_availability handles all zero flow case."""
        zero_flow_data = {
            "A->B": {
                "frequencies": {"0.0": 10},
                "max": 0.0,
                "mean": 0.0,
            }
        }
        results = {"envelope_step": {"capacity_envelopes": zero_flow_data}}

        # The method raises RuntimeError, not ValueError, due to exception wrapping
        with pytest.raises(RuntimeError, match="Error analyzing flow availability"):
            analyzer.analyze_flow_availability(results, step_name="envelope_step")


class TestConvenienceMethods:
    """Test suite for convenience and integration methods."""

    def test_analyze_and_display_all_steps(self, analyzer, mock_envelope_data):
        """Test analyze_and_display_all_steps processes multiple steps."""
        results = {
            "step1": {
                "capacity_envelopes": mock_envelope_data,
                "other_data": "ignored",
            },
            "step2": {"capacity_envelopes": mock_envelope_data},
            "step3": {"no_envelopes": "should be skipped"},
        }

        with patch.object(analyzer, "display_analysis") as mock_display:
            with patch("builtins.print"):
                analyzer.analyze_and_display_all_steps(results)

                # Should process step1 and step2, skip step3
                assert mock_display.call_count == 2

    def test_analyze_and_display_all_steps_no_data(self, analyzer):
        """Test analyze_and_display_all_steps handles no capacity envelope data."""
        results = {
            "step1": {"other_data": "no envelopes"},
            "step2": {"more_data": "still no envelopes"},
        }

        with patch("builtins.print") as mock_print:
            analyzer.analyze_and_display_all_steps(results)

            mock_print.assert_called()
            # Check that "no data" message was printed
            calls = [str(call) for call in mock_print.call_args_list]
            assert any("No capacity envelope data found" in call for call in calls)

    @patch("matplotlib.pyplot.show")
    def test_analyze_and_display_envelope_results_integration(
        self, mock_show, analyzer, mock_capacity_envelope_results
    ):
        """Test analyze_and_display_envelope_results full integration."""
        with patch("builtins.print") as mock_print:
            with patch.object(analyzer, "display_analysis") as mock_display:
                analyzer.analyze_and_display_envelope_results(
                    mock_capacity_envelope_results
                )

                # Verify all display methods were called
                mock_display.assert_called_once()
                mock_show.assert_called()  # Multiple plots should be shown
                mock_print.assert_called()

    def test_get_show_function_import(self):
        """Test that _get_show function can import the show function."""
        from ngraph.workflow.analysis.capacity_matrix import _get_show

        # Should not raise an exception
        show_func = _get_show()
        assert callable(show_func)
