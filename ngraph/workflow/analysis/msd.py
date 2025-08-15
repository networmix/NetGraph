"""Analyzer for Maximum Supported Demand (MSD) step."""

from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .base import NotebookAnalyzer


class MSDAnalyzer(NotebookAnalyzer):
    def get_description(self) -> str:
        return "Summarizes MSD (alpha*) and probe traces"

    def analyze(self, results: dict[str, Any], **kwargs) -> dict[str, Any]:
        step_name_obj = kwargs.get("step_name")
        step_name: str = str(step_name_obj) if step_name_obj is not None else ""
        if not step_name:
            raise ValueError("step_name is required for MSD analysis")

        step = results.get("steps", {}).get(step_name, {})
        data = step.get("data", {}) or {}

        alpha_star = float(data.get("alpha_star", float("nan")))
        acceptance_rule = (data.get("context", {}) or {}).get("acceptance_rule", "")
        # Collect probe trace if available
        probes = data.get("results", []) or data.get("probes", [])
        trace_rows = []
        for p in probes:
            trace_rows.append(
                dict(
                    alpha=float(p.get("alpha", float("nan"))),
                    feasible=bool(p.get("feasible", p.get("accepted", False))),
                    min_placement_ratio=float(
                        p.get("min_placement_ratio", float("nan"))
                    ),
                )
            )
        trace = pd.DataFrame(trace_rows).sort_values("alpha")

        return {
            "status": "success",
            "step_name": step_name,
            "alpha_star": alpha_star,
            "acceptance_rule": acceptance_rule,
            "trace": trace,
        }

    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        name = analysis.get("step_name", "Unknown")
        alpha_star = analysis.get("alpha_star", float("nan"))
        rule = analysis.get("acceptance_rule", "")
        trace: pd.DataFrame = analysis["trace"]

        print(f"✅ MSD for {name}: alpha* = {alpha_star:.4g}  (rule: {rule})")
        if trace.empty:
            print("  No probe trace available.")
            return

        plt.figure(figsize=(4.8, 3.0))  # pragma: no cover - display-only
        sns.lineplot(
            data=trace,
            x="alpha",
            y="min_placement_ratio",
            marker="o",
            label="min placement ratio",
        )  # pragma: no cover - display-only
        sns.scatterplot(
            data=trace,
            x="alpha",
            y="min_placement_ratio",
            hue=trace["feasible"].map({True: "feasible", False: "infeasible"}),
            legend=True,
        )  # pragma: no cover - display-only
        plt.axvline(
            alpha_star, linestyle="--", linewidth=1.0, label="alpha*"
        )  # pragma: no cover - display-only
        plt.xlabel("Alpha")  # pragma: no cover - display-only
        plt.ylabel(
            "Min placement ratio across pairs"
        )  # pragma: no cover - display-only
        plt.title(
            f"MSD bracketing/bisection trace — {name}"
        )  # pragma: no cover - display-only
        plt.grid(True, linestyle=":", linewidth=0.5)  # pragma: no cover - display-only
        plt.show()  # pragma: no cover - display-only
