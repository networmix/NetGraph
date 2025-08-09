"""Placement envelope analysis utilities.

Processes placement envelope results from TrafficMatrixPlacementAnalysis into
placement matrices and summaries suitable for notebooks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .base import NotebookAnalyzer


class PlacementMatrixAnalyzer(NotebookAnalyzer):
    """Analyze placement envelopes and display matrices/statistics."""

    def get_description(self) -> str:  # noqa: D401 – simple return
        return "Processes placement envelope data into matrices and summaries"

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze placement envelopes for a given step.

        Expects results[step_name]["placement_envelopes"] to be a dict keyed by
        "src->dst|prio=K" mapping to a dict containing:
          - source, sink, priority
          - mean, min, max, stdev, total_samples
          - frequencies
        """
        step_name: Optional[str] = kwargs.get("step_name")
        if not step_name:
            raise ValueError("step_name required for placement matrix analysis")

        step_data = results.get(step_name, {})
        envelopes = step_data.get("placement_envelopes", {})
        if not envelopes:
            raise ValueError(f"No placement envelope data found for step: {step_name}")

        matrix_data = self._extract_matrix_data(envelopes)
        if not matrix_data:
            raise ValueError(f"No valid placement envelope data in step: {step_name}")

        df_matrix = pd.DataFrame(matrix_data)
        # Build per-priority matrices and stats
        placement_matrices: Dict[int, pd.DataFrame] = {}
        statistics_by_priority: Dict[int, Dict[str, Any]] = {}
        for prio in sorted({int(row["priority"]) for row in matrix_data}):
            df_p = df_matrix[df_matrix["priority"] == prio]
            pm = self._create_matrix(df_p)
            placement_matrices[prio] = pm
            statistics_by_priority[prio] = self._calculate_statistics(pm)

        # Combined matrix
        placement_matrix = self._create_matrix(df_matrix)
        statistics = self._calculate_statistics(placement_matrix)

        return {
            "status": "success",
            "step_name": step_name,
            "matrix_data": matrix_data,
            "placement_matrix": placement_matrix,
            "statistics": statistics,
            "placement_matrices": placement_matrices,
            "statistics_by_priority": statistics_by_priority,
        }

    def analyze_and_display_step(self, results: Dict[str, Any], **kwargs) -> None:
        step_name = kwargs.get("step_name")
        if not step_name:
            print("❌ No step name provided for placement matrix analysis")
            return

        try:
            analysis = self.analyze(results, step_name=step_name)
            self.display_analysis(analysis)
        except Exception as e:
            print(f"❌ Placement matrix analysis failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_matrix_data(self, envelopes: Dict[str, Any]) -> List[Dict[str, Any]]:
        data: List[Dict[str, Any]] = []
        for flow_key, env in envelopes.items():
            if not isinstance(env, dict):
                continue
            src = env.get("src") or env.get("source")
            dst = env.get("dst") or env.get("sink")
            prio = env.get("priority", 0)
            mean_ratio = env.get("mean")
            if src is None or dst is None or mean_ratio is None:
                continue
            data.append(
                {
                    "source": str(src),
                    "destination": str(dst),
                    "ratio": float(mean_ratio),
                    "flow_path": flow_key,
                    "priority": int(prio),
                }
            )
        return data

    @staticmethod
    def _create_matrix(df_matrix: pd.DataFrame) -> pd.DataFrame:
        return df_matrix.pivot_table(
            index="source",
            columns="destination",
            values="ratio",
            aggfunc="mean",
            fill_value=0.0,
        )

    @staticmethod
    def _calculate_statistics(placement_matrix: pd.DataFrame) -> Dict[str, Any]:
        values = placement_matrix.values
        non_zero = values[values > 0]
        if len(non_zero) == 0:
            return {"has_data": False}
        return {
            "has_data": True,
            "ratio_min": float(non_zero.min()),
            "ratio_max": float(non_zero.max()),
            "ratio_mean": float(non_zero.mean()),
            "num_sources": len(placement_matrix.index),
            "num_destinations": len(placement_matrix.columns),
        }

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:  # noqa: D401
        step_name = analysis.get("step_name", "Unknown")
        print(f"✅ Analyzing placement matrix for {step_name}")
        from . import show  # lazy import to avoid circular

        def fmt(x: float) -> str:
            return f"{x:.2f}"

        matrices = analysis.get("placement_matrices", {})
        stats_by_prio = analysis.get("statistics_by_priority", {})

        if not matrices:
            print("No placement data available")
            return

        for prio in sorted(matrices.keys()):
            print(f"\nPriority {prio}")
            stats = stats_by_prio.get(prio, {"has_data": False})
            if not stats.get("has_data"):
                print("  No data")
                continue
            print(f"  Sources: {stats['num_sources']:,} nodes")
            print(f"  Destinations: {stats['num_destinations']:,} columns")
            print(
                f"  Placement ratio range: {stats['ratio_min']:.2f} - {stats['ratio_max']:.2f} (mean {stats['ratio_mean']:.2f})"
            )

            matrix_display = matrices[prio].copy()
            matrix_display.index.name = "Source"
            matrix_display.columns.name = "Destination"
            if not matrix_display.empty:
                md = matrix_display.applymap(fmt)
                show(
                    md,
                    caption=f"Placement Matrix (priority {prio}) - {step_name}",
                    scrollY="400px",
                    scrollX=True,
                    scrollCollapse=True,
                    paging=False,
                )
