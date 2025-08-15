"""Capacity matrix analysis.

Consumes ``flow_results`` (from MaxFlow step). Builds node→node capacity matrix
using the maximum placed value observed per pair across iterations (i.e., the
capacity ceiling under the tested failure set). Provides stats and a heatmap.

This enhanced version augments printed statistics (quartiles, density wording)
and is designed to be extended with distribution plots. To preserve test
stability and headless environments, histogram/CDF plots are not emitted here;
they can be added in notebooks explicitly if desired.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .base import NotebookAnalyzer


class CapacityMatrixAnalyzer(NotebookAnalyzer):
    """Analyze max-flow capacities into matrices/statistics/plots."""

    def get_description(self) -> str:
        """Return the analyzer description."""
        return "Processes max-flow results into capacity matrices and statistics"

    # ---------- public API ----------

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        step_name: Optional[str] = kwargs.get("step_name")
        if not step_name:
            raise ValueError("step_name required for capacity matrix analysis")

        step_data = results.get("steps", {}).get(step_name, {})
        flow_results = (step_data.get("data", {}) or {}).get("flow_results", [])
        if not flow_results:
            raise ValueError(f"No flow_results data found for step: {step_name}")

        # Compute max placed per (src,dst) over all iterations
        max_by_pair: Dict[Tuple[str, str], float] = {}
        for it in flow_results:
            for rec in it.get("flows", []):
                src = str(rec.get("source", ""))
                dst = str(rec.get("destination", ""))
                if not src or not dst:
                    continue
                placed = float(rec.get("placed", 0.0))
                key = (src, dst)
                if placed > max_by_pair.get(key, 0.0):
                    max_by_pair[key] = placed

        if not max_by_pair:
            raise ValueError(f"No valid capacity data in step: {step_name}")

        df = pd.DataFrame(
            [
                {"source": s, "destination": d, "capacity": v}
                for (s, d), v in max_by_pair.items()
            ]
        )
        cap_matrix = df.pivot_table(
            index="source",
            columns="destination",
            values="capacity",
            aggfunc="max",
            fill_value=0.0,
        )

        stats = self._stats(cap_matrix)

        return {
            "status": "success",
            "step_name": step_name,
            "capacity_matrix": cap_matrix,
            "statistics": stats,
        }

    def analyze_and_display_step(self, results: Dict[str, Any], **kwargs) -> None:
        """Analyze and render capacity matrix for a single workflow step.

        Args:
            results: Results document containing workflow steps.
            **kwargs: Must include ``step_name`` identifying the step to analyze.

        Raises:
            Exception: Re-raises any error from ``analyze`` after printing a concise message.
        """
        step_name = kwargs.get("step_name")
        if not step_name:
            print("❌ No step name provided for capacity matrix analysis")
            return

        try:
            analysis = self.analyze(results, step_name=step_name)
            self.display_analysis(analysis)
        except Exception as e:
            print(f"❌ Capacity matrix analysis failed: {e}")
            raise

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        step = analysis.get("step_name", "Unknown")
        matrix: pd.DataFrame = analysis["capacity_matrix"]
        stats = analysis["statistics"]
        print(f"✅ Capacity Matrix for {step}")
        if not stats["has_data"]:
            print("No capacity data available")
            return

        print("Matrix Statistics:")
        print(
            f"  Sources: {stats['num_sources']:,}   Destinations: {stats['num_destinations']:,}"
        )
        print(
            f"  Flows with capacity >0: {stats['total_flows']:,}/{stats['total_possible']:,} "
            f"({stats['flow_density']:.1f}% density)"
        )
        print(
            f"  Capacity range: {stats['min']:.2f}–{stats['max']:.2f}  "
            f"mean={stats['mean']:.2f}  p50={stats['p50']:.2f}  p25={stats['p25']:.2f}  p75={stats['p75']:.2f}"
        )

        # Heatmap
        # Scale figure size with matrix dimensions; bias toward readability
        plt.figure(  # pragma: no cover - display-only
            figsize=(
                min(12, 2.0 + 0.35 * max(3, matrix.shape[1])),
                min(9, 2.0 + 0.35 * max(3, matrix.shape[0])),
            )
        )
        sns.heatmap(  # pragma: no cover - display-only
            matrix.replace(0.0, np.nan),
            annot=False,
            fmt=".0f",
            cbar_kws={"label": "Gbps"},
            linewidths=0.0,
            square=False,
        )
        plt.title(f"Node→Node Capacity — max over iterations — {step}")
        plt.xlabel("Destination")
        plt.ylabel("Source")
        plt.show()  # pragma: no cover - display-only

        # Distribution plots of non-zero capacities (histogram and CDF)
        vals = matrix.values.astype(float).ravel()
        nonzero = vals[vals > 0.0]
        if nonzero.size > 0:
            plt.figure(figsize=(8.0, 5.0))  # pragma: no cover - display-only
            sns.histplot(nonzero, bins=20, color="steelblue")
            plt.xlabel("Max capacity per flow (Gbps)")
            plt.ylabel("Number of flow pairs")
            plt.title(f"Distribution of Pair Capacity — {step}")
            plt.tight_layout()  # pragma: no cover - display-only
            plt.show()  # pragma: no cover - display-only

            nz_sorted = np.sort(nonzero)
            cum = np.arange(1, nz_sorted.size + 1, dtype=float) / nz_sorted.size
            plt.figure(figsize=(8.0, 5.0))  # pragma: no cover - display-only
            sns.lineplot(x=nz_sorted, y=cum, drawstyle="steps-pre")
            plt.xlabel("Capacity (Gbps)")
            plt.ylabel("Fraction of flows ≤ x")
            plt.title(f"CDF of Flow Capacity — {step}")
            plt.grid(True, linestyle=":", linewidth=0.5)
            plt.tight_layout()  # pragma: no cover - display-only
            plt.show()  # pragma: no cover - display-only

    # ---------- helpers ----------

    @staticmethod
    def _stats(mat: pd.DataFrame) -> Dict[str, Any]:
        vals = mat.values
        non_zero = vals[vals > 0]
        if non_zero.size == 0:
            return {"has_data": False}
        num_nodes = len(mat.index)
        total_possible = num_nodes * (num_nodes - 1)
        non_self = sum(
            1
            for s in mat.index
            for d in mat.columns
            if s != d and cast(float, mat.loc[s, d]) > 0.0
        )
        density = (non_self / total_possible * 100.0) if total_possible else 0.0
        # Ensure float dtype for statistics to satisfy type checker
        s = pd.Series(np.asarray(non_zero, dtype=float).ravel())
        return {
            "has_data": True,
            "num_sources": len(mat.index),
            "num_destinations": len(mat.columns),
            "total_possible": total_possible,
            "total_flows": non_self,
            "flow_density": density,
            "min": float(s.min()),
            "max": float(s.max()),
            "mean": float(s.mean()),
            "p25": float(s.quantile(0.25)),
            "p50": float(s.quantile(0.50)),
            "p75": float(s.quantile(0.75)),
        }
