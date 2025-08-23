"""Power/Cost analyzer for CostPower workflow step.

Computes absolute and unit-normalised metrics per aggregation level path
(typically level 2 "sites").

Inputs:
- CostPower step data under ``steps[step_name]["data"]`` with ``levels`` and
  ``context.aggregation_level``.
- Delivered traffic from a ``TrafficMatrixPlacement`` step (auto-detected or
  provided via ``traffic_step``), using baseline iteration if available.

Outputs:
- site_metrics: mapping path -> {power_total_watts, capex_total, delivered_gbps}
- normalized_metrics: mapping path -> {power_per_unit, cost_per_unit}

Display renders tables (itables.show) and simple bar charts (seaborn).
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

import pandas as pd
import seaborn as sns
from matplotlib import pyplot as plt

from .base import NotebookAnalyzer


class CostPowerAnalysis(NotebookAnalyzer):
    """Analyze power and capex per site and normalise by delivered traffic.

    The analyzer aggregates absolute metrics from the CostPower step and
    attributes delivered traffic to sites based on the baseline iteration of a
    TrafficMatrixPlacement step. Ratios are computed as W/{unit} and $/{unit}.
    """

    def get_description(self) -> str:
        return (
            "Compute per-site power and capex; normalise by delivered traffic "
            "(W per unit, $ per unit)."
        )

    def analyze(self, results: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        """Compute absolute and normalised metrics per site.

        Args:
            results: Results document with ``steps`` and ``workflow`` mappings.
            **kwargs: ``step_name`` (required), optional ``traffic_step`` and
                ``unit`` (one of {"Gbps", "Mbps", "Tbps"}).

        Returns:
            Dictionary with site and normalised metrics suitable for display.

        Raises:
            ValueError: If required inputs are missing or malformed.
        """

        step_name_obj = kwargs.get("step_name")
        step_name: str = str(step_name_obj) if step_name_obj is not None else ""
        if not step_name:
            raise ValueError(
                "step_name (CostPower step) is required for CostPowerAnalysis"
            )

        steps_map = results.get("steps", {}) if isinstance(results, dict) else {}
        step_data = steps_map.get(step_name, {}) if isinstance(steps_map, dict) else {}
        data_obj = step_data.get("data", {}) if isinstance(step_data, dict) else {}

        ctx = data_obj.get("context", {}) if isinstance(data_obj, dict) else {}
        agg_level = int(ctx.get("aggregation_level", 2))

        levels = data_obj.get("levels", {}) if isinstance(data_obj, dict) else {}
        level_key = str(agg_level)
        entries = levels.get(level_key, []) if isinstance(levels, dict) else []
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"No CostPower data found at level {agg_level}")

        # Seed site metrics with absolute CostPower values
        site_metrics: Dict[str, Dict[str, float]] = {}
        for entry in entries:
            site = str(entry.get("path", ""))
            site_metrics[site] = {
                "power_total_watts": float(entry.get("power_total_watts", 0.0)),
                "capex_total": float(entry.get("capex_total", 0.0)),
                "delivered_gbps": 0.0,
            }

        # Locate TrafficMatrixPlacement step for delivered volumes
        traffic_step_name: Optional[str] = kwargs.get("traffic_step")
        if not traffic_step_name:
            workflow_meta = results.get("workflow", {})
            if isinstance(workflow_meta, dict) and workflow_meta:
                candidates: list[tuple[int, str]] = []
                for name, meta in workflow_meta.items():
                    if str(meta.get("step_type")) == "TrafficMatrixPlacement":
                        order = int(meta.get("execution_order", 1_000_000))
                        candidates.append((order, name))
                if candidates:
                    traffic_step_name = sorted(candidates)[0][1]

        if not traffic_step_name:
            raise ValueError(
                "No TrafficMatrixPlacement step found for delivered demand normalisation"
            )

        tp_step = steps_map.get(traffic_step_name, {})
        tp_data = tp_step.get("data", {}) if isinstance(tp_step, dict) else {}
        flow_results = (
            tp_data.get("flow_results", []) if isinstance(tp_data, dict) else []
        )
        if not isinstance(flow_results, list) or not flow_results:
            raise ValueError(
                f"No flow_results data found for step: {traffic_step_name}"
            )

        # Prefer baseline iteration(s); else fallback to first iteration
        base_iter = None
        for it in flow_results:
            fid = str(it.get("failure_id", ""))
            if fid.lower() == "baseline":
                base_iter = it
                break
        if base_iter is None:
            base_iter = flow_results[0]
        base_flows = base_iter.get("flows", []) if isinstance(base_iter, dict) else []
        if not isinstance(base_flows, list):
            base_flows = []

        def path_at_level(name: str, level: int) -> str:
            """Return prefix of ``name`` up to ``level`` components.

            Empty/short names yield the available prefix (possibly empty string).
            """

            if not name:
                return ""
            parts = [p for p in str(name).replace("|", "/").split("/") if p]
            if level <= 0:
                return ""
            if len(parts) <= level:
                return "/".join(parts)
            return "/".join(parts[:level])

        # Attribute delivered volumes to both endpoints' sites (count once if same)
        for rec in base_flows:
            src = str(rec.get("source", ""))
            dst = str(rec.get("destination", ""))
            placed = float(rec.get("placed", 0.0))
            if not src or not dst or placed <= 0.0:
                continue

            src_site = path_at_level(src, agg_level)
            dst_site = path_at_level(dst, agg_level)

            if src_site:
                site_metrics.setdefault(
                    src_site,
                    {
                        "power_total_watts": 0.0,
                        "capex_total": 0.0,
                        "delivered_gbps": 0.0,
                    },
                )
                site_metrics[src_site]["delivered_gbps"] += placed
            if dst_site and dst_site != src_site:
                site_metrics.setdefault(
                    dst_site,
                    {
                        "power_total_watts": 0.0,
                        "capex_total": 0.0,
                        "delivered_gbps": 0.0,
                    },
                )
                site_metrics[dst_site]["delivered_gbps"] += placed

        # Unit conversion factors relative to Gbps
        unit_param = str(kwargs.get("unit", "Gbps"))
        unit = unit_param[0].upper() + unit_param[1:].lower() if unit_param else "Gbps"
        factors = {"Gbps": 1.0, "Mbps": 1000.0, "Tbps": 0.001}
        if unit not in factors:
            unit = "Gbps"
        factor = float(factors[unit])

        normalized_metrics: Dict[str, Dict[str, float]] = {}
        for site, vals in site_metrics.items():
            delivered_unit = float(vals.get("delivered_gbps", 0.0)) * factor
            power = float(vals.get("power_total_watts", 0.0))
            cost = float(vals.get("capex_total", 0.0))
            if delivered_unit > 1e-12:
                normalized_metrics[site] = {
                    "power_per_unit": power / delivered_unit,
                    "cost_per_unit": cost / delivered_unit,
                }
            else:
                normalized_metrics[site] = {
                    "power_per_unit": math.inf if power > 0.0 else 0.0,
                    "cost_per_unit": math.inf if cost > 0.0 else 0.0,
                }

        return {
            "status": "success",
            "step_name": step_name,
            "agg_level": int(agg_level),
            "unit": unit,
            "site_metrics": site_metrics,
            "normalized_metrics": normalized_metrics,
            "traffic_step_used": traffic_step_name,
        }

    def display_analysis(self, analysis: Dict[str, Any], **kwargs: Any) -> None:
        """Render absolute and normalised metrics tables and bar charts.

        Args:
            analysis: Output of ``analyze``.
        """

        level = int(analysis.get("agg_level", 2))
        unit = str(analysis.get("unit", "Gbps"))
        site_metrics = analysis.get("site_metrics", {})
        norm_metrics = analysis.get("normalized_metrics", {})
        if not isinstance(site_metrics, dict) or not site_metrics:
            print("❌ No data available for CostPowerAnalysis")
            return

        # Build DataFrames
        sites = sorted(site_metrics.keys())
        delivered_factor = (
            1.0 if unit == "Gbps" else (1000.0 if unit == "Mbps" else 0.001)
        )
        abs_rows = []
        norm_rows = []
        for s in sites:
            sm = site_metrics.get(s, {})
            nm = norm_metrics.get(s, {})
            abs_rows.append(
                {
                    "Site": s,
                    f"Delivered ({unit})": float(sm.get("delivered_gbps", 0.0))
                    * delivered_factor,
                    "Power (W)": float(sm.get("power_total_watts", 0.0)),
                    "Cost ($)": float(sm.get("capex_total", 0.0)),
                }
            )
            norm_rows.append(
                {
                    "Site": s,
                    f"W per {unit}": float(nm.get("power_per_unit", 0.0)),
                    f"$ per {unit}": float(nm.get("cost_per_unit", 0.0)),
                }
            )

        df_abs = pd.DataFrame(abs_rows).set_index("Site")
        df_norm = pd.DataFrame(norm_rows).set_index("Site")

        def _fmt(x: float) -> str:
            if x is None:
                return "N/A"
            try:
                xv = float(x)
            except Exception:
                return "N/A"
            if not math.isfinite(xv):
                return "N/A"
            return f"{xv:.2f}"

        # Column-wise map to formatted strings to satisfy static typing
        df_abs_fmt = df_abs.apply(lambda col: col.map(_fmt))
        df_norm_fmt = df_norm.apply(lambda col: col.map(_fmt))

        print(f"📊 Power/Cost Analysis (Level {level} sites, traffic unit = {unit})")
        try:
            from . import show  # pragma: no cover - display-only

            show(
                df_abs_fmt,
                caption=f"Absolute Power and Cost per Site (Level {level})",
                scrollY="300px",
                scrollX=True,
                scrollCollapse=True,
                paging=False,
            )
            show(
                df_norm_fmt,
                caption=f"Normalized Metrics per Site (W/{unit} & $/{unit})",
                scrollY="300px",
                scrollX=True,
                scrollCollapse=True,
                paging=False,
            )
        except Exception:
            # Fallback to plain print when interactive table display is unavailable
            print("\n[Absolute Power and Cost per Site]")
            print(df_abs_fmt.to_string())
            print(f"\n[Normalized W/{unit} & $/{unit} per Site]")
            print(df_norm_fmt.to_string())

        # Visualisations (omit infinities/NaN by displaying zeros)
        sns.set_style("whitegrid")
        n_sites = len(sites)
        fig_w = max(8.0, min(2.0 + 0.6 * n_sites, 15.0))
        fig_h = 5.0

        plt.figure(figsize=(fig_w, fig_h))  # pragma: no cover - display-only
        sns.barplot(
            x=df_abs.index, y=df_abs["Power (W)"].astype(float), color="steelblue"
        )
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Power (W)")
        plt.title("Power Consumption by Site")
        plt.tight_layout()
        plt.show()  # pragma: no cover - display-only

        plt.figure(figsize=(fig_w, fig_h))  # pragma: no cover - display-only
        sns.barplot(x=df_abs.index, y=df_abs["Cost ($)"].astype(float), color="orange")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel("Cost ($)")
        plt.title("Cost by Site")
        plt.tight_layout()
        plt.show()  # pragma: no cover - display-only

        pow_vals = [
            0.0
            if (not isinstance(v, (int, float)) or not math.isfinite(float(v)))
            else float(v)
            for v in df_norm[f"W per {unit}"].values
        ]
        plt.figure(figsize=(fig_w, fig_h))  # pragma: no cover - display-only
        sns.barplot(x=df_norm.index, y=pow_vals, color="seagreen")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel(f"W per {unit}")
        plt.title(f"Power per {unit} Delivered by Site")
        plt.tight_layout()
        plt.show()  # pragma: no cover - display-only

        cost_vals = [
            0.0
            if (not isinstance(v, (int, float)) or not math.isfinite(float(v)))
            else float(v)
            for v in df_norm[f"$ per {unit}"].values
        ]
        plt.figure(figsize=(fig_w, fig_h))  # pragma: no cover - display-only
        sns.barplot(x=df_norm.index, y=cost_vals, color="purple")
        plt.xticks(rotation=30, ha="right")
        plt.ylabel(f"$ per {unit}")
        plt.title(f"Cost per {unit} Delivered by Site")
        plt.tight_layout()
        plt.show()  # pragma: no cover - display-only
