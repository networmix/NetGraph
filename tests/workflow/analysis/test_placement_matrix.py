from typing import Any, Dict

import pandas as pd
import pytest

from ngraph.workflow.analysis.placement_matrix import PlacementMatrixAnalyzer


class TestPlacementMatrixAnalyzer:
    def test_analyze_requires_step_name(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        with pytest.raises(ValueError, match="step_name required"):
            analyzer.analyze({}, step_name=None)  # type: ignore[arg-type]

    def test_analyze_no_envelopes(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        results: Dict[str, Dict[str, Any]] = {"step": {"placed_gbps_envelopes": {}}}
        with pytest.raises(ValueError, match="No placed_gbps_envelopes data"):
            analyzer.analyze(results, step_name="step")

    def test_extract_filter_and_analyze_happy_path(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        # Mixed-quality input: some entries missing fields must be ignored
        envs = {
            "A->B|prio=0": {"src": "A", "dst": "B", "priority": 0, "mean": 8.0},
            "A->C|prio=1": {"source": "A", "sink": "C", "priority": 1, "mean": 5.0},
            # Invalid entries below should be skipped by _extract_matrix_data
            "bad1": {"src": "A", "dst": None, "mean": 0.1},
            "bad2": {"src": None, "dst": "B", "mean": 0.2},
            "bad3": {"src": "X", "dst": "Y", "priority": 2},
            "bad4": 42,
        }
        results = {"pm": {"placed_gbps_envelopes": envs}}

        out = analyzer.analyze(results, step_name="pm")
        assert out["status"] == "success"
        assert out["step_name"] == "pm"

        matrix_data = out["matrix_data"]
        # Only two valid rows should remain
        assert isinstance(matrix_data, list)
        assert len(matrix_data) == 2
        # Ensure schema
        row0 = matrix_data[0]
        for key in ("source", "destination", "gbps", "flow_path", "priority"):
            assert key in row0

        # Combined matrix should have sources as index and destinations as columns
        pmatrix: pd.DataFrame = out["placement_matrix"]
        assert set(pmatrix.index) == {"A"}
        assert set(pmatrix.columns) == {"B", "C"}
        assert pytest.approx(pmatrix.loc["A", "B"], rel=1e-9) == 8.0
        assert pytest.approx(pmatrix.loc["A", "C"], rel=1e-9) == 5.0

        # Per-priority matrices present for priorities 0 and 1
        by_prio: Dict[int, pd.DataFrame] = out["placement_matrices"]
        assert set(by_prio.keys()) == {0, 1}
        assert pytest.approx(by_prio[0].loc["A", "B"], rel=1e-9) == 8.0

        # Statistics computed with non-zero enforcement
        stats: Dict[str, Any] = out["statistics"]
        assert stats["has_data"] is True
        assert stats["gbps_min"] <= stats["gbps_mean"] <= stats["gbps_max"]
        assert stats["num_sources"] == 1
        assert stats["num_destinations"] == 2

    def test_calculate_statistics_empty_returns_flag(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        # Empty matrix yields has_data=False
        empty_matrix = pd.DataFrame()
        assert analyzer._calculate_statistics(empty_matrix) == {"has_data": False}

    def test_analyze_and_display_step_raises_and_prints_on_error(
        self, capsys: Any
    ) -> None:
        analyzer = PlacementMatrixAnalyzer()
        with pytest.raises(ValueError):
            analyzer.analyze_and_display_step({}, step_name="missing")
        captured = capsys.readouterr()
        # Should include the error banner
        assert "❌ Placement matrix analysis failed" in captured.out
