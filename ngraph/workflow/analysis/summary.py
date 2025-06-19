"""Summary analysis for notebook results."""

from typing import Any, Dict

from .base import NotebookAnalyzer


class SummaryAnalyzer(NotebookAnalyzer):
    """Provides summary analysis of all results."""

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze and summarize all results."""
        total_steps = len(results)
        capacity_steps = len(
            [
                s
                for s, data in results.items()
                if isinstance(data, dict) and "capacity_envelopes" in data
            ]
        )
        flow_steps = len(
            [
                s
                for s, data in results.items()
                if isinstance(data, dict)
                and any(k.startswith("max_flow:") for k in data.keys())
            ]
        )
        other_steps = total_steps - capacity_steps - flow_steps

        return {
            "status": "success",
            "total_steps": total_steps,
            "capacity_steps": capacity_steps,
            "flow_steps": flow_steps,
            "other_steps": other_steps,
        }

    def get_description(self) -> str:
        return "Provides summary of all analysis results"

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display summary analysis."""
        print("📊 NetGraph Analysis Summary")
        print("=" * 40)

        stats = analysis
        print(f"Total Analysis Steps: {stats['total_steps']:,}")
        print(f"Capacity Envelope Steps: {stats['capacity_steps']:,}")
        print(f"Flow Analysis Steps: {stats['flow_steps']:,}")
        print(f"Other Data Steps: {stats['other_steps']:,}")

        if stats["total_steps"] > 0:
            print(
                f"\n✅ Analysis complete. Processed {stats['total_steps']:,} workflow steps."
            )
        else:
            print("\n❌ No analysis results found.")

    def analyze_and_display_summary(self, results: Dict[str, Any]) -> None:
        """Analyze and display summary."""
        analysis = self.analyze(results)
        self.display_analysis(analysis)
