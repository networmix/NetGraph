"""Bandwidth-Availability Curve (BAC) from ``flow_results``.

Supports both MaxFlow and TrafficMatrixPlacement steps. For each failure
iteration, aggregate delivered bandwidth (sum of `placed` over all DC-DC pairs).
Compute the empirical availability curve and summary quantiles. Optionally,
overlay Placement vs MaxFlow when a sibling step with the same failure_id set is found.
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
        """Return a short description of the BAC analyzer."""
        return "Computes BAC (availability vs bandwidth) from flow_results"

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
        quantiles = self._quantiles(series, [0.50, 0.90, 0.95, 0.99])

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
        }

    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        """Render the BAC with optional overlay comparison."""
        name = analysis.get("step_name", "Unknown")
        mode = analysis.get("mode", "maxflow")
        s: pd.Series = analysis["delivered_series"]
        overlay: Optional[pd.Series] = analysis.get("overlay_series")
        overlay_label: Optional[str] = analysis.get("overlay_label")

        max_value = analysis["max_value"]
        qs = analysis["quantiles"]

        print(
            f"✅ BAC for {name} [{mode}] — iterations={len(s)}  peak={max_value:.2f} Gbps"
        )
        print(
            "  Quantiles (Gbps): "
            + ", ".join([f"p{int(p * 100)}={v:.2f}" for p, v in qs.items()])
        )

        # Availability curves (1 - CDF) with absolute bandwidth on x-axis
        def availability_curve(series: pd.Series):
            xs = np.sort(np.asarray(series.values, dtype=float))
            cdf = np.arange(1, len(xs) + 1) / len(xs)
            avail = 1.0 - cdf
            return xs, avail

        x, a = availability_curve(s)
        plt.figure(figsize=(9, 5.5))  # pragma: no cover - display-only
        sns.lineplot(
            x=x, y=a, drawstyle="steps-post", label=mode.capitalize()
        )  # pragma: no cover - display-only
        if overlay is not None and len(overlay) == len(s):
            xo, ao = availability_curve(overlay)
            sns.lineplot(
                x=xo, y=ao, drawstyle="steps-post", label=overlay_label or "overlay"
            )  # pragma: no cover - display-only

        plt.xlabel("Delivered bandwidth (Gbps)")
        plt.ylabel("Availability (≥x)")
        plt.title(f"Bandwidth-Availability Curve - {name}")
        plt.grid(True, linestyle=":", linewidth=0.5)  # pragma: no cover - display-only
        plt.tight_layout()  # pragma: no cover - display-only
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
