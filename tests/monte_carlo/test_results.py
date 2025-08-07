"""Tests for monte_carlo.results module."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from ngraph.monte_carlo.results import (
    CapacityEnvelopeResults,
    DemandPlacementResults,
    SensitivityResults,
)


class TestCapacityEnvelopeResults:
    """Test CapacityEnvelopeResults class."""

    def test_capacity_envelope_results_creation(self) -> None:
        """Test basic CapacityEnvelopeResults creation."""
        mock_envelope1 = MagicMock()
        mock_envelope2 = MagicMock()

        envelopes = {
            "datacenter->edge": mock_envelope1,
            "edge->datacenter": mock_envelope2,
        }

        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={"test": "value"},
        )

        assert result.envelopes == envelopes
        assert result.iterations == 100
        assert result.source_pattern == "datacenter.*"
        assert result.sink_pattern == "edge.*"
        assert result.mode == "combine"
        assert result.metadata == {"test": "value"}

    def test_flow_keys(self) -> None:
        """Test flow_keys property."""
        mock_envelope1 = MagicMock()
        mock_envelope2 = MagicMock()

        envelopes = {
            "datacenter->edge": mock_envelope1,
            "edge->datacenter": mock_envelope2,
        }

        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        assert result.flow_keys() == ["datacenter->edge", "edge->datacenter"]

    def test_get_envelope_success(self) -> None:
        """Test get_envelope method with valid key."""
        mock_envelope = MagicMock()
        envelopes = {"datacenter->edge": mock_envelope}

        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        assert result.get_envelope("datacenter->edge") == mock_envelope

    def test_get_envelope_key_error(self) -> None:
        """Test get_envelope method with invalid key."""
        mock_envelope = MagicMock()
        envelopes = {"datacenter->edge": mock_envelope}

        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        with pytest.raises(KeyError) as exc_info:
            result.get_envelope("nonexistent->flow")

        assert "Flow key 'nonexistent->flow' not found" in str(exc_info.value)
        assert "Available: datacenter->edge" in str(exc_info.value)

    def test_summary_statistics(self) -> None:
        """Test summary_statistics method."""
        # Mock envelope with all required attributes
        mock_envelope = MagicMock()
        mock_envelope.mean_capacity = 100.0
        mock_envelope.stdev_capacity = 10.0
        mock_envelope.min_capacity = 80.0
        mock_envelope.max_capacity = 120.0
        mock_envelope.total_samples = 1000
        mock_envelope.get_percentile.side_effect = lambda p: {
            5: 85.0,
            25: 95.0,
            50: 100.0,
            75: 105.0,
            95: 115.0,
        }[p]

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        stats = result.summary_statistics()

        assert "datacenter->edge" in stats
        flow_stats = stats["datacenter->edge"]
        assert flow_stats["mean"] == 100.0
        assert flow_stats["std"] == 10.0
        assert flow_stats["min"] == 80.0
        assert flow_stats["max"] == 120.0
        assert flow_stats["samples"] == 1000
        assert flow_stats["p5"] == 85.0
        assert flow_stats["p95"] == 115.0

    def test_to_dataframe(self) -> None:
        """Test to_dataframe method."""
        mock_envelope = MagicMock()
        mock_envelope.mean_capacity = 100.0
        mock_envelope.stdev_capacity = 10.0
        mock_envelope.min_capacity = 80.0
        mock_envelope.max_capacity = 120.0
        mock_envelope.total_samples = 1000
        mock_envelope.get_percentile.side_effect = lambda p: {
            5: 85.0,
            25: 95.0,
            50: 100.0,
            75: 105.0,
            95: 115.0,
        }[p]

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        df = result.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert "datacenter->edge" in df.index
        assert df.loc["datacenter->edge", "mean"] == 100.0

    def test_get_failure_pattern_summary_no_patterns(self) -> None:
        """Test get_failure_pattern_summary with no patterns."""
        result = CapacityEnvelopeResults(
            envelopes={},
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        df = result.get_failure_pattern_summary()

        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_get_failure_pattern_summary_with_patterns(self) -> None:
        """Test get_failure_pattern_summary with actual patterns."""
        mock_pattern = MagicMock()
        mock_pattern.count = 5
        mock_pattern.is_baseline = False
        mock_pattern.excluded_nodes = ["node1", "node2"]
        mock_pattern.excluded_links = ["link1"]
        mock_pattern.capacity_matrix = {"datacenter->edge": 80.0}

        failure_patterns = {"pattern1": mock_pattern}
        result = CapacityEnvelopeResults(
            envelopes={},
            failure_patterns=failure_patterns,  # type: ignore
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        df = result.get_failure_pattern_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]["pattern_key"] == "pattern1"
        assert df.iloc[0]["count"] == 5
        assert df.iloc[0]["failed_nodes"] == 2
        assert df.iloc[0]["failed_links"] == 1
        assert df.iloc[0]["total_failures"] == 3
        assert df.iloc[0]["capacity_datacenter->edge"] == 80.0

    def test_export_summary(self) -> None:
        """Test export_summary method."""
        mock_envelope = MagicMock()
        mock_envelope.mean_capacity = 100.0
        mock_envelope.stdev_capacity = 10.0
        mock_envelope.min_capacity = 80.0
        mock_envelope.max_capacity = 120.0
        mock_envelope.total_samples = 1000
        mock_envelope.get_percentile.side_effect = lambda p: {
            5: 85.0,
            25: 95.0,
            50: 100.0,
            75: 105.0,
            95: 115.0,
        }[p]

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={"test": "value"},
        )

        summary = result.export_summary()

        assert isinstance(summary, dict)
        assert "iterations" in summary
        assert "metadata" in summary
        assert "summary_statistics" in summary  # Correct key name
        assert summary["iterations"] == 100
        assert summary["metadata"] == {"test": "value"}

    def test_get_cost_distribution(self) -> None:
        """Test get_cost_distribution method."""
        # Mock envelope with flow summary stats
        mock_envelope = MagicMock()
        mock_envelope.flow_summary_stats = {
            "cost_distribution_stats": {
                2.0: {"mean": 3.0, "min": 2.0, "max": 4.0, "total_samples": 5},
                4.0: {"mean": 1.5, "min": 1.0, "max": 2.0, "total_samples": 3},
            }
        }

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        cost_dist = result.get_cost_distribution("datacenter->edge")

        assert 2.0 in cost_dist
        assert 4.0 in cost_dist
        assert cost_dist[2.0]["mean"] == 3.0
        assert cost_dist[4.0]["total_samples"] == 3

    def test_get_cost_distribution_empty(self) -> None:
        """Test get_cost_distribution with no flow summary stats."""
        mock_envelope = MagicMock()
        mock_envelope.flow_summary_stats = {}

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        cost_dist = result.get_cost_distribution("datacenter->edge")
        assert cost_dist == {}

    def test_get_min_cut_frequencies(self) -> None:
        """Test get_min_cut_frequencies method."""
        mock_envelope = MagicMock()
        mock_envelope.flow_summary_stats = {
            "min_cut_frequencies": {
                "('A', 'B', 'link1')": 15,
                "('B', 'C', 'link2')": 8,
            }
        }

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        min_cuts = result.get_min_cut_frequencies("datacenter->edge")

        assert "('A', 'B', 'link1')" in min_cuts
        assert min_cuts["('A', 'B', 'link1')"] == 15
        assert min_cuts["('B', 'C', 'link2')"] == 8

    def test_cost_distribution_summary(self) -> None:
        """Test cost_distribution_summary method."""
        # Mock multiple envelopes with cost distribution data
        mock_envelope1 = MagicMock()
        mock_envelope1.flow_summary_stats = {
            "cost_distribution_stats": {
                2.0: {
                    "mean": 5.0,
                    "min": 4.0,
                    "max": 6.0,
                    "total_samples": 10,
                    "frequencies": {"5.0": 8, "4.0": 2},
                },
                3.0: {
                    "mean": 3.0,
                    "min": 3.0,
                    "max": 3.0,
                    "total_samples": 5,
                    "frequencies": {"3.0": 5},
                },
            }
        }

        mock_envelope2 = MagicMock()
        mock_envelope2.flow_summary_stats = {
            "cost_distribution_stats": {
                1.5: {
                    "mean": 2.0,
                    "min": 1.5,
                    "max": 2.5,
                    "total_samples": 8,
                    "frequencies": {"2.0": 6, "1.5": 2},
                },
            }
        }

        envelopes = {
            "datacenter->edge": mock_envelope1,
            "edge->datacenter": mock_envelope2,
        }
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        df = result.cost_distribution_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3  # 2 cost levels in envelope1 + 1 in envelope2

        expected_columns = [
            "flow_key",
            "cost",
            "mean_flow",
            "min_flow",
            "max_flow",
            "total_samples",
            "unique_values",
        ]
        for col in expected_columns:
            assert col in df.columns

        # Check specific data
        cost_2_row = df[
            (df["flow_key"] == "datacenter->edge") & (df["cost"] == 2.0)
        ].iloc[0]
        assert cost_2_row["mean_flow"] == 5.0
        assert cost_2_row["total_samples"] == 10
        assert cost_2_row["unique_values"] == 2  # 2 unique frequencies

    def test_cost_distribution_summary_empty(self) -> None:
        """Test cost_distribution_summary with no cost distribution data."""
        mock_envelope = MagicMock()
        mock_envelope.flow_summary_stats = {}

        envelopes = {"datacenter->edge": mock_envelope}
        result = CapacityEnvelopeResults(
            envelopes=envelopes,  # type: ignore
            failure_patterns={},
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            iterations=100,
            metadata={},
        )

        df = result.cost_distribution_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0


class TestDemandPlacementResults:
    """Test DemandPlacementResults class."""

    def test_demand_placement_results_creation(self) -> None:
        """Test basic DemandPlacementResults creation."""
        raw_results = {
            "results": [
                {"overall_placement_ratio": 0.8},
                {"overall_placement_ratio": 0.9},
            ]
        }

        result = DemandPlacementResults(
            raw_results=raw_results,
            iterations=100,
            baseline={"baseline_value": 1.0},
            failure_patterns={"pattern1": "data"},
            metadata={"test": "value"},
        )

        assert result.raw_results == raw_results
        assert result.iterations == 100
        assert result.baseline == {"baseline_value": 1.0}
        assert result.failure_patterns == {"pattern1": "data"}
        assert result.metadata == {"test": "value"}

    def test_post_init_defaults(self) -> None:
        """Test post_init sets proper defaults."""
        raw_results = {"results": []}

        result = DemandPlacementResults(
            raw_results=raw_results,
            iterations=100,
        )

        assert result.baseline is None
        assert result.failure_patterns == {}  # post_init sets empty dict, not None
        assert result.metadata == {}  # post_init sets empty dict, not None

    def test_success_rate_distribution(self) -> None:
        """Test success_rate_distribution method."""
        raw_results = {
            "results": [
                {"overall_placement_ratio": 0.8},
                {"overall_placement_ratio": 0.9},
                {"overall_placement_ratio": 0.7},
            ]
        }

        result = DemandPlacementResults(raw_results=raw_results, iterations=100)

        df = result.success_rate_distribution()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3
        assert "iteration" in df.columns
        assert "success_rate" in df.columns
        assert df["success_rate"].tolist() == [0.8, 0.9, 0.7]
        assert df["iteration"].tolist() == [0, 1, 2]

    def test_summary_statistics(self) -> None:
        """Test summary_statistics method."""
        raw_results = {
            "results": [
                {"overall_placement_ratio": 0.8},
                {"overall_placement_ratio": 0.9},
                {"overall_placement_ratio": 1.0},
                {"overall_placement_ratio": 0.7},
                {"overall_placement_ratio": 0.85},
            ]
        }

        result = DemandPlacementResults(raw_results=raw_results, iterations=100)

        stats = result.summary_statistics()

        assert isinstance(stats, dict)
        required_keys = ["mean", "std", "min", "max", "p5", "p25", "p50", "p75", "p95"]
        for key in required_keys:
            assert key in stats
            assert isinstance(stats[key], float)

        # Verify some basic properties
        assert stats["min"] <= stats["mean"] <= stats["max"]
        assert stats["p5"] <= stats["p50"] <= stats["p95"]


class TestSensitivityResults:
    """Test SensitivityResults class."""

    def test_sensitivity_results_creation(self) -> None:
        """Test basic SensitivityResults creation."""
        raw_results = {"sensitivity_data": "test"}

        result = SensitivityResults(
            raw_results=raw_results,
            iterations=100,
            baseline={"baseline_value": 1.0},
            failure_patterns={"pattern1": "data"},
            metadata={"test": "value"},
        )

        assert result.raw_results == raw_results
        assert result.iterations == 100
        assert result.baseline == {"baseline_value": 1.0}
        assert result.failure_patterns == {"pattern1": "data"}
        assert result.metadata == {"test": "value"}

    def test_sensitivity_post_init_defaults(self) -> None:
        """Test post_init sets proper defaults."""
        raw_results = {"sensitivity_data": "test"}

        result = SensitivityResults(
            raw_results=raw_results,
            iterations=100,
        )

        assert result.baseline is None
        assert result.failure_patterns == {}  # post_init sets empty dict, not None
        assert result.metadata == {}  # post_init sets empty dict, not None

    def test_component_impact_distribution(self) -> None:
        """Test component_impact_distribution method."""
        component_scores = {
            "flow_1": {
                "component_a": {"mean": 0.8, "max": 1.0, "min": 0.6, "count": 10},
                "component_b": {"mean": 0.6, "max": 0.8, "min": 0.4, "count": 10},
            },
            "flow_2": {
                "component_a": {"mean": 0.9, "max": 1.0, "min": 0.8, "count": 5},
            },
        }

        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=100,
            component_scores=component_scores,
        )

        df = result.component_impact_distribution()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3  # Two components in flow_1, one in flow_2
        assert "flow_key" in df.columns
        assert "component" in df.columns
        assert "mean_impact" in df.columns
        assert "max_impact" in df.columns

        # Check specific values
        comp_a_flow_1 = df[
            (df["flow_key"] == "flow_1") & (df["component"] == "component_a")
        ].iloc[0]
        assert comp_a_flow_1["mean_impact"] == 0.8
        assert comp_a_flow_1["max_impact"] == 1.0

    def test_component_impact_distribution_empty_scores(self) -> None:
        """Test component_impact_distribution with empty scores."""
        result = SensitivityResults(raw_results={"results": []}, iterations=100)

        df = result.component_impact_distribution()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_flow_keys(self) -> None:
        """Test flow_keys method."""
        component_scores = {
            "flow_1": {"component_a": {"mean": 0.8}},
            "flow_2": {"component_b": {"mean": 0.6}},
        }

        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=100,
            component_scores=component_scores,
        )

        keys = result.flow_keys()
        assert set(keys) == {"flow_1", "flow_2"}

    def test_get_flow_sensitivity(self) -> None:
        """Test get_flow_sensitivity method."""
        component_scores = {
            "flow_1": {
                "component_a": {"mean": 0.8, "max": 1.0, "min": 0.6},
                "component_b": {"mean": 0.6, "max": 0.8, "min": 0.4},
            }
        }

        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=100,
            component_scores=component_scores,
        )

        sensitivity = result.get_flow_sensitivity("flow_1")
        assert sensitivity == component_scores["flow_1"]

    def test_get_flow_sensitivity_missing_key(self) -> None:
        """Test get_flow_sensitivity with missing flow key."""
        result = SensitivityResults(raw_results={"test": "data"}, iterations=100)

        with pytest.raises(KeyError, match="Flow key 'missing_flow' not found"):
            result.get_flow_sensitivity("missing_flow")

    def test_summary_statistics(self) -> None:
        """Test summary_statistics method."""
        component_scores = {
            "flow_1": {
                "comp_a": {"mean": 0.8, "max": 1.0, "min": 0.6},
                "comp_b": {"mean": 0.6, "max": 0.8, "min": 0.4},
            },
            "flow_2": {
                "comp_a": {"mean": 0.9, "max": 1.0, "min": 0.8},
                "comp_b": {"mean": 0.7, "max": 0.9, "min": 0.5},
            },
        }

        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=100,
            component_scores=component_scores,
        )

        stats = result.summary_statistics()

        assert isinstance(stats, dict)
        # Should have aggregated stats for comp_a and comp_b
        assert "comp_a" in stats
        assert "comp_b" in stats

        # Check comp_a stats (aggregated from both flows: 0.8 and 0.9)
        comp_a_stats = stats["comp_a"]
        assert "mean_impact" in comp_a_stats
        assert "max_impact" in comp_a_stats
        assert "min_impact" in comp_a_stats
        assert "flow_count" in comp_a_stats
        assert comp_a_stats["flow_count"] == 2
        assert (
            abs(comp_a_stats["mean_impact"] - 0.85) < 0.001
        )  # Handle floating point precision

    def test_get_failure_pattern_summary_empty(self) -> None:
        """Test get_failure_pattern_summary with no patterns."""
        result = SensitivityResults(
            raw_results={"results": []}, iterations=100, failure_patterns={}
        )

        df = result.get_failure_pattern_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0

    def test_get_failure_pattern_summary_with_patterns(self) -> None:
        """Test get_failure_pattern_summary with actual patterns."""
        failure_patterns = {
            "pattern_1": {
                "count": 10,
                "is_baseline": False,
                "excluded_nodes": ["node_a", "node_b"],
                "excluded_links": ["link_x"],
                "sensitivity_result": {
                    "flow_1": {"comp_a": 0.8, "comp_b": 0.6},
                    "flow_2": {"comp_a": 0.7, "comp_b": 0.5},
                },
            },
            "pattern_2": {
                "count": 5,
                "is_baseline": True,
                "excluded_nodes": [],
                "excluded_links": [],
                "sensitivity_result": {
                    "flow_1": {"comp_a": 0.9, "comp_b": 0.8},
                },
            },
        }

        result = SensitivityResults(
            raw_results={"results": []},
            iterations=100,
            failure_patterns=failure_patterns,
        )

        df = result.get_failure_pattern_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2

        # Check columns
        expected_cols = [
            "pattern_key",
            "count",
            "is_baseline",
            "failed_nodes",
            "failed_links",
            "total_failures",
        ]
        for col in expected_cols:
            assert col in df.columns

        # Check pattern 1 data
        row1 = df[df["pattern_key"] == "pattern_1"].iloc[0]
        assert row1["count"] == 10
        assert not row1["is_baseline"]
        assert row1["failed_nodes"] == 2
        assert row1["failed_links"] == 1
        assert row1["total_failures"] == 3
        assert "avg_sensitivity_flow_1" in df.columns
        assert row1["avg_sensitivity_flow_1"] == 0.7  # (0.8 + 0.6) / 2

        # Check pattern 2 data
        row2 = df[df["pattern_key"] == "pattern_2"].iloc[0]
        assert row2["count"] == 5
        assert row2["is_baseline"]
        assert row2["failed_nodes"] == 0
        assert row2["failed_links"] == 0
        assert row2["total_failures"] == 0

    def test_get_failure_pattern_summary_missing_fields(self) -> None:
        """Test get_failure_pattern_summary with missing optional fields."""
        failure_patterns = {
            "incomplete_pattern": {
                "count": 3,
                # Missing optional fields
            }
        }

        result = SensitivityResults(
            raw_results={"results": []},
            iterations=100,
            failure_patterns=failure_patterns,
        )

        df = result.get_failure_pattern_summary()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1

        row = df.iloc[0]
        assert row["count"] == 3
        assert not row["is_baseline"]  # Default value
        assert row["failed_nodes"] == 0  # Default for missing excluded_nodes
        assert row["failed_links"] == 0  # Default for missing excluded_links
        assert row["total_failures"] == 0

    def test_export_summary(self) -> None:
        """Test export_summary method."""
        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=100,
            source_pattern="datacenter.*",
            sink_pattern="edge.*",
            mode="combine",
            component_scores={
                "flow_1": {"comp_a": {"mean": 0.8, "max": 1.0, "min": 0.6}}
            },
            failure_patterns={"pattern_1": {"data": "test"}},
            metadata={"test": "value"},
        )

        summary = result.export_summary()

        assert isinstance(summary, dict)
        required_keys = [
            "source_pattern",
            "sink_pattern",
            "mode",
            "iterations",
            "metadata",
            "component_scores",
            "failure_patterns",
            "summary_statistics",
        ]
        for key in required_keys:
            assert key in summary

        assert summary["source_pattern"] == "datacenter.*"
        assert summary["sink_pattern"] == "edge.*"
        assert summary["mode"] == "combine"
        assert summary["iterations"] == 100
        assert summary["metadata"] == {"test": "value"}
        assert summary["component_scores"] == {
            "flow_1": {"comp_a": {"mean": 0.8, "max": 1.0, "min": 0.6}}
        }
        assert summary["failure_patterns"] == {"pattern_1": {"data": "test"}}

    def test_export_summary_defaults(self) -> None:
        """Test export_summary with default/None values."""
        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=50,
        )

        summary = result.export_summary()

        assert isinstance(summary, dict)
        assert summary["source_pattern"] is None
        assert summary["sink_pattern"] is None
        assert summary["mode"] is None
        assert summary["iterations"] == 50
        assert summary["metadata"] == {}
        assert summary["component_scores"] == {}
        assert summary["failure_patterns"] == {}
