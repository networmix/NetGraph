"""High-level summary analyzer for results documents.

Provides quick counts of steps and basic categorisation by presence of
``flow_results`` in the new schema. Also contains a small helper for
``NetworkStats`` sections aimed at notebook usage.
"""

from typing import Any

from .base import NotebookAnalyzer


class SummaryAnalyzer(NotebookAnalyzer):
    """Compute simple counts and high-level summary statistics."""

    def analyze(self, results: dict[str, Any], **kwargs) -> dict[str, Any]:
        steps = results.get("steps", {}) if isinstance(results, dict) else {}
        total = len(steps)
        with_flow_results = sum(
            1
            for _, d in steps.items()
            if isinstance(d, dict)
            and isinstance(d.get("data"), dict)
            and isinstance(d["data"].get("flow_results"), list)
        )
        return {
            "status": "success",
            "total_steps": total,
            "steps_with_flow_results": with_flow_results,
            "other_steps": total - with_flow_results,
        }

    def get_description(self) -> str:
        return "Generates summary statistics and overviews of workflow results"

    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        print("📊 NetGraph Analysis Summary")
        print("=" * 40)
        print(f"Total Analysis Steps: {analysis['total_steps']:,}")
        print(f"Steps with flow_results: {analysis['steps_with_flow_results']:,}")
        print(f"Other Data Steps: {analysis['other_steps']:,}")
        if analysis["total_steps"] == 0:
            print("❌ No analysis results found")

    # Optional: a tiny helper for BuildGraph/NetworkStats sections
    def analyze_network_stats(self, results: dict[str, Any], **kwargs) -> None:
        """Display a small info line for ``NetworkStats`` steps."""
        step = kwargs.get("step_name")
        if not step:
            raise ValueError("No step name provided")
        steps = results.get("steps", {})
        s = steps.get(step, {})
        meta = s.get("data", {}) if isinstance(s, dict) else {}
        print(f"ℹ️ NetworkStats ({step}): keys={list(meta.keys())[:10]}")
