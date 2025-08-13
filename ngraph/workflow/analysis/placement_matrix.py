"""Placement analysis utilities for placed Gbps envelopes (current design).

Consumes results produced by ``TrafficMatrixPlacementAnalysis`` with keys:
  - placed_gbps_envelopes: {"src->dst|prio=K": envelope}
  - offered_gbps_by_pair: {"src->dst|prio=K": float}
  - delivered_gbps_stats: {mean/min/max/stdev/samples/percentiles}
and builds matrices of mean placed Gbps by pair (overall and per priority),
with basic statistics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .base import NotebookAnalyzer


class PlacementMatrixAnalyzer(NotebookAnalyzer):
    """Analyze placed Gbps envelopes and display matrices/statistics."""

    def get_description(self) -> str:  # noqa: D401 - simple return
        return "Processes placement envelope data into matrices and summaries"

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze placed Gbps envelopes for a given step.

        Expects results[step_name]["placed_gbps_envelopes"] (dict keyed by
        "src->dst|prio=K") and produces matrices of mean placed Gbps.
        """
        step_name: Optional[str] = kwargs.get("step_name")
        if not step_name:
            raise ValueError("step_name required for placement matrix analysis")

        step_data = results.get(step_name, {})
        envelopes = step_data.get("placed_gbps_envelopes", {})
        if not envelopes:
            raise ValueError(
                f"No placed_gbps_envelopes data found for step: {step_name}"
            )

        matrix_data = self._extract_matrix_data(envelopes)
        if not matrix_data:
            raise ValueError(f"No valid placement envelope data in step: {step_name}")

        df_matrix = pd.DataFrame(matrix_data)
        # Build per-priority matrices and stats (Gbps)
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
            mean_gbps = env.get("mean")
            if src is None or dst is None or mean_gbps is None:
                continue
            data.append(
                {
                    "source": str(src),
                    "destination": str(dst),
                    "gbps": float(mean_gbps),
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
            values="gbps",
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
            "gbps_min": float(non_zero.min()),
            "gbps_max": float(non_zero.max()),
            "gbps_mean": float(non_zero.mean()),
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
                f"  Placed Gbps range: {stats['gbps_min']:.2f} - {stats['gbps_max']:.2f} (mean {stats['gbps_mean']:.2f})"
            )

            matrix_display = matrices[prio].copy()
            matrix_display.index.name = "Source"
            matrix_display.columns.name = "Destination"
            if not matrix_display.empty:
                md = matrix_display.applymap(fmt)
                show(
                    md,
                    caption=f"Placed Gbps Matrix (priority {prio}) - {step_name}",
                    scrollY="400px",
                    scrollX=True,
                    scrollCollapse=True,
                    paging=False,
                )
