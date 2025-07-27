"""Maximum flow analysis for workflow results.

This module contains `FlowAnalyzer`, which processes maximum flow computation
results from workflow steps, computes statistics, and generates visualizations
for flow capacity analysis.
"""

import importlib
from typing import Any, Dict

import matplotlib.pyplot as plt
import pandas as pd

from .base import NotebookAnalyzer


class FlowAnalyzer(NotebookAnalyzer):
    """Processes maximum flow computation results into statistical summaries.

    Extracts max_flow results from workflow step data, computes flow statistics
    including capacity distribution metrics, and generates tabular visualizations
    for notebook output.
    """

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze flow results and create visualizations.

        Args:
            results: Dictionary containing all workflow step results.
            **kwargs: Additional arguments (unused for flow analysis).

        Returns:
            Dictionary containing flow analysis results with statistics and visualization data.

        Raises:
            ValueError: If no flow analysis results found.
            RuntimeError: If analysis computation fails.
        """
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
            raise ValueError("No flow analysis results found in any workflow step")

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
            raise RuntimeError(f"Error analyzing flow results: {e}") from e

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
        return "Processes maximum flow computation results into statistical summaries"

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display flow analysis results.

        Args:
            analysis: Analysis results dictionary from the analyze method.
            **kwargs: Additional arguments (unused).
        """
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
            except Exception as exc:  # pragma: no cover
                print(f"⚠️  Visualization error: {exc}")

    def analyze_capacity_probe(self, results: Dict[str, Any], **kwargs) -> None:
        """Analyze and display capacity probe results for a specific step.

        Args:
            results: Dictionary containing all workflow step results.
            **kwargs: Additional arguments including step_name.

        Raises:
            ValueError: If step_name is missing, no data found, or no capacity probe results found.
        """
        step_name = kwargs.get("step_name", "")
        if not step_name:
            raise ValueError("No step name provided for capacity probe analysis")

        step_data = results.get(step_name, {})
        if not step_data:
            raise ValueError(f"No data found for step: {step_name}")

        # Extract flow results for this specific step
        flow_results = []
        for key, value in step_data.items():
            if key.startswith("max_flow:"):
                flow_path = key.replace("max_flow:", "").strip("[]")
                flow_results.append(
                    {
                        "flow_path": flow_path,
                        "max_flow": value,
                    }
                )

        if not flow_results:
            raise ValueError(f"No capacity probe results found in step: {step_name}")

        print(f"🚰 Capacity Probe Results: {step_name}")
        print("=" * 50)

        df_flows = pd.DataFrame(flow_results)

        # Display summary statistics
        print("Flow Statistics:")
        print(f"  Total probes: {len(flow_results):,}")
        print(f"  Max flow: {df_flows['max_flow'].max():,.2f}")
        print(f"  Min flow: {df_flows['max_flow'].min():,.2f}")
        print(f"  Average flow: {df_flows['max_flow'].mean():,.2f}")
        print(f"  Total capacity: {df_flows['max_flow'].sum():,.2f}")

        # Display table
        print("\nDetailed Results:")
        _get_show()(
            df_flows,
            caption=f"Capacity Probe Results - {step_name}",
            scrollY="300px",
            scrollCollapse=True,
            paging=True,
        )

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
