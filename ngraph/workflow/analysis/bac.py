"""Bandwidth-Availability Curve (BAC) from ``flow_results``.

Supports both MaxFlow and TrafficMatrixPlacement steps. For each failure
iteration, aggregate delivered bandwidth (sum of ``placed`` over all DC-DC
pairs). Compute the empirical availability curve and summary quantiles.

This enhanced version optionally normalizes the x-axis by the offered demand
volume (when available via per-flow ``demand`` fields) to improve comparison
across scenarios of different scale. It preserves existing outputs and overlay
behavior for compatibility.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .base import NotebookAnalyzer


class BACAnalyzer(NotebookAnalyzer):
    def get_description(self) -> str:
        """Return a short description of the BAC analyzer.

        Returns:
            Description of BAC with note about optional demand-normalized view.
        """
        return (
            "Computes BAC (availability vs bandwidth) from flow_results; "
            "optionally normalizes by offered demand if available"
        )

    # ---------- public API ----------

    def analyze(self, results: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Analyze delivered bandwidth to build an availability curve.

        Args:
            results: Results document.
            **kwargs: ``step_name`` (required), optional ``mode`` and
                ``try_overlay``.

        Returns:
            A dictionary containing the delivered series, quantiles, and an
            optional overlay series when a sibling step matches failure ids.
        """
        step_name_obj = kwargs.get("step_name")
        step_name: str = str(step_name_obj) if step_name_obj is not None else ""
        mode: str = kwargs.get("mode", "auto")  # 'placement' | 'maxflow' | 'auto'
        if not step_name:
            raise ValueError("step_name is required for BAC analysis")

        steps = results.get("steps", {})
        step = steps.get(step_name, {})
        data = step.get("data", {}) or {}
        flow_results = data.get("flow_results", [])
        if not isinstance(flow_results, list) or not flow_results:
            raise ValueError(f"No flow_results in step: {step_name}")

        # Determine semantic mode if 'auto'
        step_type = (results.get("workflow", {}).get(step_name, {}) or {}).get(
            "step_type", ""
        )
        if mode == "auto":
            mode = "placement" if step_type == "TrafficMatrixPlacement" else "maxflow"

        # total delivered per iteration
        delivered, failure_ids = self._delivered_series(flow_results)
        if not delivered:
            raise ValueError("No delivered totals computed (are flows empty?)")

        series = pd.Series(delivered)
        maximum = float(series.max())
        quantiles = self._quantiles(series, [0.50, 0.90, 0.95, 0.99, 0.999, 0.9999])

        # Estimate offered demand as the first non-zero total demand observed
        # across iterations (assumed constant across failures). Fallback to
        # maximum delivered if demand is unavailable in the data.
        offered = 0.0
        for it in flow_results:
            it_demand = 0.0
            flows = it.get("flows", [])
            for rec in flows:
                try:
                    src = rec.get("source", "")
                    dst = rec.get("destination", "")
                    if not src or not dst or src == dst:
                        continue
                    it_demand += float(rec.get("demand", 0.0))
                except Exception:
                    continue
            if it_demand > 0.0:
                offered = it_demand
                break
        if offered <= 0.0:
            offered = maximum

        # Availability at common demand thresholds (as fraction of iterations)
        def availability_at_thresholds(
            values: pd.Series, offered_value: float
        ) -> dict[float, float]:
            if offered_value <= 0.0:
                return {}
            counts: dict[float, float] = {}
            total = float(len(values)) if len(values) > 0 else 1.0
            for pct in (90.0, 95.0, 99.0, 99.9, 99.99):
                threshold = (pct / 100.0) * offered_value
                counts[pct] = float((values >= threshold).sum()) / total
            return counts

        availability = availability_at_thresholds(series, offered)

        # AUC of BAC on normalized axis equals mean(min(delivered/offered, 1)).
        # Provides a single-score resilience indicator in [0, 1].
        auc_normalized = 1.0
        if offered > 0.0 and len(series) > 0:
            norm = series.astype(float) / offered
            clipped = norm.clip(upper=1.0)
            auc_normalized = float(clipped.mean())

        # Try to find a sibling step to overlay (Placement vs MaxFlow)
        overlay = None
        overlay_label = None
        if kwargs.get("try_overlay", True):
            sibling_type = (
                "MaxFlow" if mode == "placement" else "TrafficMatrixPlacement"
            )
            sib = self._find_sibling_by_failure_ids(
                results, step_name, step_type=sibling_type, failure_ids=failure_ids
            )
            if sib:
                ov_series, _ = self._delivered_series(
                    sib.get("data", {}).get("flow_results", [])
                )
                overlay = pd.Series(ov_series) if ov_series else None
                overlay_label = sibling_type

        return {
            "status": "success",
            "step_name": step_name,
            "mode": mode,
            "delivered_series": series,
            "max_value": maximum,
            "quantiles": quantiles,
            "failure_ids": failure_ids,
            "overlay_series": overlay,
            "overlay_label": overlay_label,
            "total_offered": float(offered),
            "availability_at_percent": availability,
            "auc_normalized": auc_normalized,
        }

    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        """Render the BAC with optional overlay comparison.

        The x-axis is normalized to percent of offered demand when available;
        otherwise it displays absolute Gbps.
        """
        name = analysis.get("step_name", "Unknown")
        mode = analysis.get("mode", "maxflow")
        s: pd.Series = analysis["delivered_series"]
        overlay: Optional[pd.Series] = analysis.get("overlay_series")
        overlay_label: Optional[str] = analysis.get("overlay_label")

        max_value = float(analysis["max_value"])  # absolute peak delivered
        qs = analysis["quantiles"]
        offered = float(analysis.get("total_offered", 0.0))

        def _fmt_pct_label(prob: float) -> str:
            pct = prob * 100.0
            text = f"{pct:.4f}".rstrip("0").rstrip(".")
            return f"p{text}"

        print(
            f"✅ BAC for {name} [{mode}] — iterations={len(s)}  peak={max_value:.2f} Gbps"
        )
        if offered > 0.0:
            q_abs = ", ".join(
                [f"{_fmt_pct_label(p)}={v:.2f} Gbps" for p, v in qs.items()]
            )
            q_pct = ", ".join(
                [
                    f"{_fmt_pct_label(p)}={(v / offered) * 100:.2f}%"
                    for p, v in qs.items()
                ]
            )
            print(f"  Offered demand: {offered:.2f} Gbps")
            print(f"  Quantiles: {q_abs}  |  {q_pct}")
            avail = analysis.get("availability_at_percent", {})
            if isinstance(avail, dict) and avail:

                def _fmt_thr(k: float) -> str:
                    if float(k).is_integer():
                        return f"{int(k)}%"
                    sthr = f"{k:.2f}".rstrip("0").rstrip(".")
                    return f"{sthr}%"

                summary = ", ".join(
                    [f"≥{_fmt_thr(k)}: {v:.2f}" for k, v in sorted(avail.items())]
                )
                print(f"  Availability at demand thresholds: {summary}")
            auc = float(analysis.get("auc_normalized", 0.0))
            print(f"  BAC area-under-curve (normalized): {auc * 100:.1f}%")
        else:
            print(
                "  Quantiles (Gbps): "
                + ", ".join([f"{_fmt_pct_label(p)}={v:.2f}" for p, v in qs.items()])
            )

        # Availability curves (1 - CDF) with absolute bandwidth on x-axis
        def availability_curve(series: pd.Series):
            xs = np.sort(np.asarray(series.values, dtype=float))
            cdf = np.arange(1, len(xs) + 1) / len(xs)
            avail = 1.0 - cdf
            return xs, avail

        x, a = availability_curve(s)
        plt.figure(figsize=(8.0, 5.0))  # pragma: no cover - display-only
        # Normalize x-axis to percent of offered demand when available
        if offered > 0.0:
            x_plot = (x / offered) * 100.0
            x_label = "Delivered bandwidth (% of demand)"
        else:
            x_plot = x
            x_label = "Delivered bandwidth (Gbps)"
        sns.lineplot(
            x=x_plot, y=a, drawstyle="steps-post", label=mode.capitalize()
        )  # pragma: no cover - display-only
        if overlay is not None and len(overlay) == len(s):
            xo, ao = availability_curve(overlay)
            if offered > 0.0:
                xo = (xo / offered) * 100.0
            sns.lineplot(
                x=xo, y=ao, drawstyle="steps-post", label=overlay_label or "overlay"
            )  # pragma: no cover - display-only

        plt.xlabel(x_label)
        plt.ylabel("Availability (≥x)")
        plt.title(f"Bandwidth-Availability Curve — {name}")
        plt.grid(True, linestyle=":", linewidth=0.5)  # pragma: no cover - display-only
        plt.show()  # pragma: no cover - display-only

    # ---------- helpers ----------

    @staticmethod
    def _delivered_series(
        flow_results: list[dict[str, Any]],
    ) -> tuple[list[float], list[str]]:
        series: list[float] = []
        fids: list[str] = []
        for it in flow_results:
            flows = it.get("flows", [])
            total = 0.0
            for rec in flows:
                # Exclude self-loops and zero-demand artifacts
                src = rec.get("source", "")
                dst = rec.get("destination", "")
                if not src or not dst or src == dst:
                    continue
                placed = float(rec.get("placed", 0.0))
                total += placed
            series.append(total)
            fids.append(str(it.get("failure_id", f"it{len(series) - 1}")))
        return series, fids

    @staticmethod
    def _quantiles(series: pd.Series, probs: Sequence[float]) -> dict[float, float]:
        return {p: float(series.quantile(p, interpolation="lower")) for p in probs}

    @staticmethod
    def _find_sibling_by_failure_ids(
        results: dict[str, Any], step_name: str, step_type: str, failure_ids: list[str]
    ) -> Optional[dict[str, Any]]:
        wf = results.get("workflow", {})
        steps = results.get("steps", {})
        target = None
        for name, meta in wf.items():
            if name == step_name:  # skip self
                continue
            if meta.get("step_type") != step_type:
                continue
            data = steps.get(name, {}).get("data", {}) or {}
            fr = data.get("flow_results", [])
            fids = [str(it.get("failure_id", "")) for it in fr]
            if fids and set(fids) == set(failure_ids):
                target = steps.get(name, {})
                break
        return target
