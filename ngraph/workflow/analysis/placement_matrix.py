"""Placement analysis utilities for flow_results (unified design).

Consumes results produced by ``TrafficMatrixPlacementAnalysis`` with the new
schema under step["data"]["flow_results"]. Builds matrices of mean placed
volume by pair (overall and per priority), with basic statistics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .base import NotebookAnalyzer


class PlacementMatrixAnalyzer(NotebookAnalyzer):
    """Analyze placed Gbps envelopes and display matrices/statistics."""

    def get_description(self) -> str:
        """Return a short description of the analyzer purpose."""
        return "Processes placement envelope data into matrices and summaries"

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze ``flow_results`` for a given step.

        Args:
            results: Results document containing a ``steps`` mapping.
            **kwargs: Must include ``step_name`` identifying the step.

        Returns:
            A dictionary with combined and per-priority matrices and statistics.

        Raises:
            ValueError: If ``step_name`` is missing or data is not available.
        """
        step_name: Optional[str] = kwargs.get("step_name")
        if not step_name:
            raise ValueError("step_name required for placement matrix analysis")

        steps_map = results.get("steps", {}) if isinstance(results, dict) else {}
        step_data = steps_map.get(step_name, {})
        data_obj = step_data.get("data", {}) if isinstance(step_data, dict) else {}
        flow_results = (
            data_obj.get("flow_results", []) if isinstance(data_obj, dict) else []
        )
        if not flow_results:
            raise ValueError(f"No flow_results data found for step: {step_name}")

        # Convert flow_results into rows with mean placed per pair and priority
        matrix_data = self._extract_matrix_data_from_flow_results(flow_results)
        if not matrix_data:
            raise ValueError(f"No valid placement data in step: {step_name}")

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
        """Convenience wrapper that analyzes and renders one step."""
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

    def _extract_matrix_data_from_flow_results(
        self, flow_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return rows of mean placed volume per (src, dst, priority).

        Args:
            flow_results: List of iteration dictionaries, each with ``flows``.

        Returns:
            List of row dictionaries with keys: ``source``, ``destination``,
            ``value`` (mean placed), and ``priority``.
        """
        # Collect placed values by (src,dst,prio)
        from collections import defaultdict

        buckets: Dict[tuple[str, str, int], list[float]] = defaultdict(list)
        for iteration in flow_results:
            flows = iteration.get("flows", []) if isinstance(iteration, dict) else []
            for rec in flows:
                try:
                    src = str(rec.get("source", ""))
                    dst = str(rec.get("destination", ""))
                    prio = int(rec.get("priority", 0))
                    placed = float(rec.get("placed", 0.0))
                except Exception:
                    continue
                buckets[(src, dst, prio)].append(placed)

        rows: List[Dict[str, Any]] = []
        for (src, dst, prio), vals in buckets.items():
            if not src or not dst:
                continue
            mean_val = float(sum(vals) / len(vals)) if vals else 0.0
            rows.append(
                {
                    "source": src,
                    "destination": dst,
                    "value": mean_val,
                    "priority": prio,
                }
            )
        return rows

    @staticmethod
    def _create_matrix(df_matrix: pd.DataFrame) -> pd.DataFrame:
        """Pivot rows into a source×destination matrix of mean placed values."""
        return df_matrix.pivot_table(
            index="source",
            columns="destination",
            values="value",
            aggfunc="mean",
            fill_value=0.0,
        )

    @staticmethod
    def _calculate_statistics(placement_matrix: pd.DataFrame) -> Dict[str, Any]:
        """Compute basic statistics for a placement matrix."""
        values = placement_matrix.values
        non_zero = values[values > 0]
        if len(non_zero) == 0:
            return {"has_data": False}
        return {
            "has_data": True,
            "value_min": float(non_zero.min()),
            "value_max": float(non_zero.max()),
            "value_mean": float(non_zero.mean()),
            "num_sources": len(placement_matrix.index),
            "num_destinations": len(placement_matrix.columns),
        }

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Render per-priority placement matrices with summary statistics."""
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
                f"  Placed Gbps range: {stats['value_min']:.2f} - {stats['value_max']:.2f} (mean {stats['value_mean']:.2f})"
            )

            matrix_display = matrices[prio].copy()
            matrix_display.index.name = "Source"
            matrix_display.columns.name = "Destination"
            if not matrix_display.empty:
                md = matrix_display.applymap(fmt)
                show(
                    md,
                    caption=f"Placed Matrix (priority {prio}) - {step_name}",
                    scrollY="400px",
                    scrollX=True,
                    scrollCollapse=True,
                    paging=False,
                )
