"""Latency (distance) and stretch from ``cost_distribution``.

For each iteration, compute:
  • mean distance per delivered Gbps (km/Gbps) aggregated across flows
  • stretch = (mean distance) / (pair-wise lower-bound distance)
Lower bound is approximated as the minimum observed path cost per (src, dst) in
the "baseline" iteration(s) of the same step (or, if absent, across all
iterations).

This enhanced version augments the display with a CDF of stretch values to show
the distribution across iterations, complementing the scatter plot view.
"""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .base import NotebookAnalyzer


class LatencyAnalyzer(NotebookAnalyzer):
    def get_description(self) -> str:
        """Return a short description of the latency analyzer.

        Returns:
            Description summarizing distance and stretch metrics with CDF view.
        """
        return (
            "Computes mean cost-km per Gbps and latency stretch; displays "
            "scatter and CDF of stretch"
        )

    # ---------- public API ----------

    def analyze(self, results: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Compute latency and stretch metrics for each failure iteration.

        Args:
            results: Results document.
            **kwargs: ``step_name`` is required.

        Returns:
            Dictionary containing a per-iteration metrics DataFrame and the
            lower-bound cost map per (src, dst).
        """
        step_name_obj = kwargs.get("step_name")
        step_name: str = str(step_name_obj) if step_name_obj is not None else ""
        if not step_name:
            raise ValueError("step_name is required for latency analysis")

        steps = results.get("steps", {})
        step = steps.get(step_name, {})
        data = step.get("data", {}) or {}
        flow_results = data.get("flow_results", [])
        if not flow_results:
            raise ValueError(f"No flow_results in step: {step_name}")

        # Build lower-bound distance per pair from baseline if available
        lb = self._lower_bounds_from_baseline(flow_results)

        per_iter_metrics: list[dict[str, float]] = []
        for it in flow_results:
            total_gbps = 0.0
            total_km_gbps = 0.0
            stretch_numer = 0.0
            stretch_denom = 0.0
            for rec in it.get("flows", []):
                src = str(rec.get("source", ""))
                dst = str(rec.get("destination", ""))
                if not src or not dst or src == dst:
                    continue
                placed = float(rec.get("placed", 0.0))
                if placed <= 0.0:
                    continue
                cd = rec.get("cost_distribution", {})
                if not isinstance(cd, dict) or not cd:
                    continue
                # mean cost for this flow
                km = 0.0
                vol = 0.0
                for k, v in cd.items():
                    try:
                        c = float(k)
                        w = float(v)
                    except Exception:
                        continue
                    km += c * w
                    vol += w
                if vol <= 0:
                    continue
                mean_cost = km / vol
                total_gbps += placed
                total_km_gbps += mean_cost * placed
                # stretch components
                lb_cost = lb.get((src, dst))
                if lb_cost and lb_cost > 0:
                    stretch_numer += mean_cost * placed
                    stretch_denom += lb_cost * placed

            mean_km_per_gbps = (total_km_gbps / total_gbps) if total_gbps > 0 else 0.0
            stretch = (stretch_numer / stretch_denom) if stretch_denom > 0 else np.nan
            row: dict[str, float] = {
                "mean_km_per_gbps": float(mean_km_per_gbps),
                "stretch": float(stretch) if not np.isnan(stretch) else float("nan"),
                "total_delivered_gbps": float(total_gbps),
            }
            # Attach failure_id separately to keep value types consistent
            metrics_with_id: dict[str, Any] = {
                "failure_id": str(it.get("failure_id", "")),
                **row,
            }
            per_iter_metrics.append(metrics_with_id)

        df = pd.DataFrame(per_iter_metrics)
        return {
            "status": "success",
            "step_name": step_name,
            "metrics": df,
            "lower_bounds": lb,
        }

    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        """Render the latency and stretch scatter plot with summary lines.

        Adds a CDF of stretch across iterations to expose distribution tails.
        """
        name = analysis.get("step_name", "Unknown")
        df: pd.DataFrame = analysis["metrics"]
        if df.empty:
            print(f"⚠️ No latency metrics for {name}")
            return

        print(f"✅ Latency/Stretch for {name} — iterations={len(df)}")

        # Compute tail stats to complement plots
        tail = df["stretch"].dropna()
        p95 = float(tail.quantile(0.95)) if not tail.empty else float("nan")
        p99 = float(tail.quantile(0.99)) if not tail.empty else float("nan")

        fig, ax = plt.subplots(figsize=(9, 5.5))  # pragma: no cover - display-only
        sns.scatterplot(
            data=df, x="mean_km_per_gbps", y="stretch", s=60
        )  # pragma: no cover - display-only
        ax.set_xlabel("Mean distance per Gbps (km/Gbps)")
        ax.set_ylabel("Latency stretch (avg path cost / baseline LB)")
        ax.set_title(f"Distance & Stretch by Failure Iteration - {name}")
        ax.grid(True, linestyle=":", linewidth=0.5)
        plt.tight_layout()  # pragma: no cover - display-only
        plt.show()  # pragma: no cover - display-only

        def _fmt_pct_label(prob: float) -> str:
            pct = prob * 100.0
            text = f"{pct:.4f}".rstrip("0").rstrip(".")
            return f"p{text}"

        print("  Summary:")
        print(
            f"    mean_km/Gbps: {df['mean_km_per_gbps'].mean():.1f}   p50: {df['mean_km_per_gbps'].median():.1f}"
        )
        if df["stretch"].notna().any():
            print(
                f"    stretch mean: {df['stretch'].mean():.3f}   p50: {df['stretch'].median():.3f}"
            )
            print(
                f"    stretch tail: {_fmt_pct_label(0.95)}={p95:.3f}   {_fmt_pct_label(0.99)}={p99:.3f}"
            )

        # CDF of stretch across iterations
        stretch_vals = sorted(df["stretch"].dropna().values.tolist())
        if stretch_vals:
            n = len(stretch_vals)
            cum = np.linspace(1.0 / n, 1.0, n)
            plt.figure(figsize=(8.5, 5.0))  # pragma: no cover - display-only
            sns.lineplot(x=stretch_vals, y=cum, drawstyle="steps-pre")
            plt.xlabel("Latency stretch")
            plt.ylabel("Fraction of iterations ≤ x")
            plt.title(f"CDF of Latency Stretch — {name}")
            plt.grid(True, linestyle=":", linewidth=0.5)
            plt.tight_layout()  # pragma: no cover - display-only
            plt.show()  # pragma: no cover - display-only

    # ---------- helpers ----------

    @staticmethod
    def _lower_bounds_from_baseline(
        flow_results: list[dict[str, Any]],
    ) -> dict[tuple[str, str], float]:
        """Return min observed cost per (src,dst) from baseline iteration(s) if available.
        If no explicit 'baseline' failure_id exists, fallback to min across all iterations.
        """

        def update_min(
            d: dict[tuple[str, str], float], k: tuple[str, str], v: float
        ) -> None:
            if v <= 0:
                return
            cur = d.get(k)
            d[k] = v if cur is None or v < cur else cur

        # Prefer 'baseline' iterations
        lbs: dict[tuple[str, str], float] = {}
        candidates = [
            it
            for it in flow_results
            if str(it.get("failure_id", "")).lower() == "baseline"
        ]
        if not candidates:
            candidates = flow_results

        for it in candidates:
            for rec in it.get("flows", []):
                src = str(rec.get("source", ""))
                dst = str(rec.get("destination", ""))
                if not src or not dst or src == dst:
                    continue
                cd = rec.get("cost_distribution", {})
                if not isinstance(cd, dict) or not cd:
                    continue
                try:
                    min_cost = min(float(k) for k in cd.keys())
                except Exception:
                    continue
                update_min(lbs, (src, dst), min_cost)
        return lbs
