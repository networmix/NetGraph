"""Tests for CapacityMatrixAnalyzer with new results schema."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from ngraph.workflow.analysis.capacity_matrix import CapacityMatrixAnalyzer


@pytest.fixture
def analyzer() -> CapacityMatrixAnalyzer:
    return CapacityMatrixAnalyzer()


def _make_flow_results() -> list[dict[str, Any]]:
    # Two iterations with flows A->B and B->C
    return [
        {
            "flows": [
                {"source": "A", "destination": "B", "placed": 10.0},
                {"source": "B", "destination": "C", "placed": 8.0},
            ],
        },
        {
            "flows": [
                {"source": "A", "destination": "B", "placed": 12.0},
                {"source": "B", "destination": "C", "placed": 15.0},
            ],
        },
    ]


class TestCapacityMatrixAnalyzer:
    def test_get_description(self, analyzer):
        desc = analyzer.get_description()
        assert isinstance(desc, str) and "capacity" in desc.lower()

    def test_analyze_workflow_mode(self, analyzer):
        results = {
            "steps": {
                "envelope_step": {"data": {"flow_results": _make_flow_results()}},
            }
        }
        analysis = analyzer.analyze(results, step_name="envelope_step")
        assert analysis["status"] == "success"
        assert analysis["step_name"] == "envelope_step"
        assert isinstance(analysis["capacity_matrix"], pd.DataFrame)
        stats = analysis["statistics"]
        assert stats["has_data"] is True

    def test_analyze_missing_step_name(self, analyzer):
        with pytest.raises(ValueError, match="step_name required"):
            analyzer.analyze({}, step_name=None)  # type: ignore[arg-type]

    def test_analyze_missing_step_data(self, analyzer):
        results = {"steps": {}}
        with pytest.raises(ValueError, match="No flow_results data"):
            analyzer.analyze(results, step_name="nonexistent_step")

    def test_analyze_empty_flow_results(self, analyzer):
        results = {"steps": {"envelope": {"data": {"flow_results": []}}}}
        with pytest.raises(ValueError, match="No flow_results data"):
            analyzer.analyze(results, step_name="envelope")

    def test_extract_matrix_data_internal(self, analyzer):
        # Internal helper validation via analyze path already covers it;
        # keep a direct call for coverage on edge parsing.
        flows = _make_flow_results()
        results = {"steps": {"s": {"data": {"flow_results": flows}}}}
        analysis = analyzer.analyze(results, step_name="s")
        md = analysis["matrix_data"]
        assert any(row["flow_path"].startswith("A->B") for row in md)
        assert any(row["flow_path"].startswith("B->C") for row in md)

    @patch("matplotlib.pyplot.show")
    def test_display_analysis_smoke(self, mock_show, analyzer):
        results = {"steps": {"s": {"data": {"flow_results": _make_flow_results()}}}}
        analysis = analyzer.analyze(results, step_name="s")
        with patch("builtins.print"):
            analyzer.display_analysis(analysis)
        # show() is used by itables in other contexts; this call may not happen here, keep smoke-only.


class TestConvenience:
    def test_analyze_and_display_all_steps(self, analyzer, capsys: Any):
        results = {
            "steps": {
                "s1": {"data": {"flow_results": _make_flow_results()}},
                "skip": {"data": {}},
                "s2": {"data": {"flow_results": _make_flow_results()}},
            }
        }
        with patch.object(analyzer, "display_analysis") as mock_display:
            with patch("builtins.print"):
                analyzer.analyze_and_display_all_steps(results)
            assert mock_display.call_count == 2

    def test_analyze_and_display_all_steps_no_data(self, analyzer, capsys: Any):
        results = {"steps": {"s1": {"data": {}}, "s2": {"data": {}}}}
        with patch("builtins.print") as mock_print:
            analyzer.analyze_and_display_all_steps(results)
            calls = [str(c) for c in mock_print.call_args_list]
            assert any("No steps with flow_results" in c for c in calls)
