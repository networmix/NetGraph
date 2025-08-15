"""Tests for monte_carlo.results module (SensitivityResults only after refactor)."""

import pandas as pd
import pytest

from ngraph.monte_carlo.results import SensitivityResults


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

    def test_get_flow_sensitivity_keyerror_message(self) -> None:
        """KeyError message contains available keys or 'none'."""
        result = SensitivityResults(
            raw_results={"test": "data"},
            iterations=1,
            component_scores={},
        )

        with pytest.raises(KeyError) as exc:
            result.get_flow_sensitivity("x->y")

        msg = str(exc.value)
        assert "Flow key 'x->y' not found" in msg
        assert "Available:" in msg
