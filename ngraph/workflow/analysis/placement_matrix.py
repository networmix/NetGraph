"""Placement analysis utilities for ``flow_results`` (unified design).

Consumes results produced by ``TrafficMatrixPlacementAnalysis`` with the new
schema under ``step["data"]["flow_results"]``. Builds matrices of mean placed
volume by pair (overall and per priority), with basic statistics.

This enhanced version also computes delivery fraction statistics (placed/
demand) per flow instance to quantify drops and renders simple distributions
(histogram and CDF) when demand is present, while preserving existing outputs
so tests remain stable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

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

        # Compute overall delivery ratio and collect per-instance fractions if demand exists
        total_demand_volume = 0.0
        total_placed_volume = 0.0
        fraction_records: list[dict[str, float]] = []
        for iteration in flow_results:
            for rec in iteration.get("flows", []):
                try:
                    demand = float(rec.get("demand", 0.0))
                    placed = float(rec.get("placed", 0.0))
                except Exception:
                    continue
                if demand > 0.0:
                    fraction_records.append(
                        {
                            "fraction": placed / demand,
                            "priority": float(rec.get("priority", 0)),
                        }
                    )
                total_demand_volume += demand
                total_placed_volume += placed

        overall_delivery_ratio = (
            total_placed_volume / total_demand_volume
            if total_demand_volume > 0.0
            else 1.0
        )

        # Fraction percentiles as compact robustness summary
        fraction_percentiles: dict[str, float] = {}
        if fraction_records:
            arr = np.asarray([r["fraction"] for r in fraction_records], dtype=float)
            for label, q in (("p50", 0.5), ("p90", 0.9), ("p95", 0.95), ("p99", 0.99)):
                try:
                    fraction_percentiles[label] = float(np.quantile(arr, q))
                except Exception:
                    continue

        return {
            "status": "success",
            "step_name": step_name,
            "matrix_data": matrix_data,
            "placement_matrix": placement_matrix,
            "statistics": statistics,
            "placement_matrices": placement_matrices,
            "statistics_by_priority": statistics_by_priority,
            "overall_delivery_ratio": float(overall_delivery_ratio),
            "fraction_records": fraction_records,
            "fraction_percentiles": fraction_percentiles,
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

        for prio in sorted(matrices.keys()):  # pragma: no cover - display-only
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
            if not matrix_display.empty:  # pragma: no cover - display-only
                md = matrix_display.applymap(fmt)
                show(
                    md,
                    caption=f"Placed Matrix (priority {prio}) - {step_name}",
                    scrollY="400px",
                    scrollX=True,
                    scrollCollapse=True,
                    paging=False,
                )
        # Summary delivery ratio when demand is provided in the inputs
        ratio = analysis.get("overall_delivery_ratio")
        if isinstance(ratio, float):
            print(f"\nOverall delivered traffic: {ratio * 100:.1f}% of offered demand")
            fr_p = analysis.get("fraction_percentiles", {})
            if isinstance(fr_p, dict) and fr_p:

                def _fmt_pct_label(prob: float) -> str:
                    pct = prob * 100.0
                    text = f"{pct:.4f}".rstrip("0").rstrip(".")
                    return f"p{text}"

                # fr_p keys are percentile labels already; reconstruct from mapping to keep uniform look
                label_map = {0.5: "p50", 0.9: "p90", 0.95: "p95", 0.99: "p99"}
                ordered = [
                    (k, v)
                    for k, v in (
                        (label_map.get(0.5), fr_p.get("p50")),
                        (label_map.get(0.9), fr_p.get("p90")),
                        (label_map.get(0.95), fr_p.get("p95")),
                        (label_map.get(0.99), fr_p.get("p99")),
                    )
                    if k and v is not None
                ]
                summary = ", ".join([f"{k}={(v * 100):.2f}%" for k, v in ordered])
                print(f"  Delivered fraction percentiles: {summary}")

        # Distribution plots of per-flow delivery fractions if available
        frac_records = analysis.get("fraction_records")
        if isinstance(frac_records, list) and frac_records:
            df_frac = pd.DataFrame(frac_records)
            total = len(df_frac)
            full = int((df_frac["fraction"] >= 0.999).sum())
            zero = int((df_frac["fraction"] <= 1e-9).sum())
            print(
                f"  Flow instances fully delivered: {full}/{total} ({full / total * 100:.1f}%)"
            )
            print(
                f"  Flow instances completely dropped: {zero}/{total} ({zero / total * 100:.1f}%)"
            )

            plt.figure(figsize=(8.0, 5.0))  # pragma: no cover - display-only
            if "priority" in df_frac.columns and df_frac["priority"].nunique() > 1:
                sns.histplot(
                    data=df_frac,
                    x="fraction",
                    hue="priority",
                    bins=20,
                    multiple="layer",
                    alpha=0.6,
                )
                plt.legend(title="Priority")
            else:
                sns.histplot(
                    x=df_frac["fraction"].to_numpy(), bins=20, color="forestgreen"
                )
            plt.xlabel("Fraction of demand delivered")
            plt.ylabel("Number of flow occurrences")
            plt.title(f"Distribution of Delivered Fractions — {step_name}")
            plt.tight_layout()  # pragma: no cover - display-only
            plt.show()  # pragma: no cover - display-only

            vals = np.sort(df_frac["fraction"].to_numpy())
            cum = np.linspace(1.0 / len(vals), 1.0, len(vals))
            plt.figure(figsize=(8.0, 5.0))  # pragma: no cover - display-only
            sns.lineplot(x=vals, y=cum, drawstyle="steps-pre")
            plt.xlabel("Fraction of demand delivered")
            plt.ylabel("Fraction of flow instances ≤ x")
            plt.title(f"CDF of Demand Satisfaction — {step_name}")
            plt.grid(True, linestyle=":", linewidth=0.5)
            plt.tight_layout()  # pragma: no cover - display-only
            plt.show()  # pragma: no cover - display-only
