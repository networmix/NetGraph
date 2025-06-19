"""Flow analysis for notebook results."""

import importlib
from typing import Any, Dict

import pandas as pd

from .base import NotebookAnalyzer


class FlowAnalyzer(NotebookAnalyzer):
    """Analyzes maximum flow results."""

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze flow results and create visualizations."""
        flow_results = []

        for step_name, step_data in results.items():
            if isinstance(step_data, dict):
                for key, value in step_data.items():
                    if key.startswith("max_flow:"):
                        flow_path = key.replace("max_flow:", "").strip("[]")
                        flow_results.append(
                            {
                                "step": step_name,
                                "flow_path": flow_path,
                                "max_flow": value,
                            }
                        )

        if not flow_results:
            return {"status": "no_data", "message": "No flow analysis results found"}

        try:
            df_flows = pd.DataFrame(flow_results)
            statistics = self._calculate_flow_statistics(df_flows)
            visualization_data = self._prepare_flow_visualization(df_flows)

            return {
                "status": "success",
                "flow_data": flow_results,
                "dataframe": df_flows,
                "statistics": statistics,
                "visualization_data": visualization_data,
            }

        except Exception as e:
            return {"status": "error", "message": f"Error analyzing flows: {str(e)}"}

    def _calculate_flow_statistics(self, df_flows: pd.DataFrame) -> Dict[str, Any]:
        """Calculate flow statistics."""
        return {
            "total_flows": len(df_flows),
            "unique_steps": df_flows["step"].nunique(),
            "max_flow": float(df_flows["max_flow"].max()),
            "min_flow": float(df_flows["max_flow"].min()),
            "avg_flow": float(df_flows["max_flow"].mean()),
            "total_capacity": float(df_flows["max_flow"].sum()),
        }

    def _prepare_flow_visualization(self, df_flows: pd.DataFrame) -> Dict[str, Any]:
        """Prepare flow data for visualization."""
        return {
            "flow_table": df_flows,
            "steps": df_flows["step"].unique().tolist(),
            "has_multiple_steps": df_flows["step"].nunique() > 1,
        }

    def get_description(self) -> str:
        return "Analyzes maximum flow calculations"

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display flow analysis results."""
        if analysis["status"] != "success":
            print(f"❌ {analysis['message']}")
            return

        print("✅ Maximum Flow Analysis")

        stats = analysis["statistics"]
        print("Flow Statistics:")
        print(f"  Total flows: {stats['total_flows']:,}")
        print(f"  Analysis steps: {stats['unique_steps']:,}")
        print(f"  Flow range: {stats['min_flow']:,.2f} - {stats['max_flow']:,.2f}")
        print(f"  Average flow: {stats['avg_flow']:,.2f}")
        print(f"  Total capacity: {stats['total_capacity']:,.2f}")

        flow_df = analysis["dataframe"]

        _get_show()(
            flow_df,
            caption="Maximum Flow Results",
            scrollY="300px",
            scrollCollapse=True,
            paging=True,
        )

        # Create visualization if multiple steps
        viz_data = analysis["visualization_data"]
        if viz_data["has_multiple_steps"]:
            try:
                import matplotlib.pyplot as plt

                fig, ax = plt.subplots(figsize=(12, 6))

                for step in viz_data["steps"]:
                    step_data = flow_df[flow_df["step"] == step]
                    ax.barh(
                        range(len(step_data)),
                        step_data["max_flow"],
                        label=step,
                        alpha=0.7,
                    )

                ax.set_xlabel("Maximum Flow")
                ax.set_title("Maximum Flow Results by Analysis Step")
                ax.legend()
                plt.tight_layout()
                plt.show()
            except ImportError:
                print("Matplotlib not available for visualization")

    def analyze_and_display_all(self, results: Dict[str, Any]) -> None:
        """Analyze and display all flow results."""
        analysis = self.analyze(results)
        self.display_analysis(analysis)


# Helper to fetch the `show` implementation from the analysis module.
# Defined early so that it is available in the class methods below.


def _get_show():
    """Return the `show` function from the analysis module."""
    wrapper = importlib.import_module("ngraph.workflow.analysis")
    return wrapper.show
