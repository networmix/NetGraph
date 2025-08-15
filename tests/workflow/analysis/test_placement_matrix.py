from typing import Any, Dict

import pandas as pd
import pytest

from ngraph.workflow.analysis.placement_matrix import PlacementMatrixAnalyzer


class TestPlacementMatrixAnalyzer:
    def test_analyze_requires_step_name(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        with pytest.raises(ValueError, match="step_name required"):
            analyzer.analyze({}, step_name=None)  # type: ignore[arg-type]

    def test_analyze_no_flow_results(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        results: Dict[str, Dict[str, Any]] = {"steps": {"step": {"data": {}}}}
        with pytest.raises(ValueError, match="No flow_results data"):
            analyzer.analyze(results, step_name="step")

    def test_extract_filter_and_analyze_happy_path(self) -> None:
        analyzer = PlacementMatrixAnalyzer()
        # Two iterations; one flow with missing fields should be ignored
        flow_results = [
            {
                "flows": [
                    {"source": "A", "destination": "B", "priority": 0, "placed": 8.0},
                    {"source": "A", "destination": "C", "priority": 1, "placed": 5.0},
                    {"source": "X", "priority": 0, "placed": 1.0},  # invalid, ignored
                ]
            },
            {"flows": []},
        ]
        results = {"steps": {"pm": {"data": {"flow_results": flow_results}}}}

        out = analyzer.analyze(results, step_name="pm")
        assert out["status"] == "success"
        assert out["step_name"] == "pm"

        matrix_data = out["matrix_data"]
        assert isinstance(matrix_data, list)
        assert len(matrix_data) == 2
        row0 = matrix_data[0]
        for key in ("source", "destination", "value", "priority"):
            assert key in row0

        pmatrix: pd.DataFrame = out["placement_matrix"]
        # Smoke: expected labels exist and values are non-negative
        assert "A" in pmatrix.index
        for c in ("B", "C"):
            assert c in pmatrix.columns
            assert float(pmatrix.loc["A", c]) >= 0.0  # type: ignore[arg-type]

        by_prio: Dict[int, pd.DataFrame] = out["placement_matrices"]
        assert set(by_prio.keys()) == {0, 1}
        assert float(by_prio[0].loc["A", "B"]) >= 0.0  # type: ignore[arg-type]

        stats: Dict[str, Any] = out["statistics"]
        assert stats["has_data"] is True
        assert stats["value_min"] <= stats["value_mean"] <= stats["value_max"]
        assert stats["num_sources"] >= 1
        assert stats["num_destinations"] >= 1

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
            analyzer.analyze_and_display_step({"steps": {}}, step_name="missing")
        captured = capsys.readouterr()
        assert "❌ Placement matrix analysis failed" in captured.out
