"""Notebook analysis components."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import itables.options as itables_opt
import matplotlib.pyplot as plt
import pandas as pd
from itables import show


class NotebookAnalyzer(ABC):
    """Base class for notebook analysis components."""

    @abstractmethod
    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Perform the analysis and return results."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get a description of what this analyzer does."""
        pass

    def analyze_and_display(self, results: Dict[str, Any], **kwargs) -> None:
        """Analyze results and display them in notebook format."""
        analysis = self.analyze(results, **kwargs)
        self.display_analysis(analysis, **kwargs)

    @abstractmethod
    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display analysis results in notebook format."""
        pass


@dataclass
class AnalysisContext:
    """Context information for analysis execution."""

    step_name: str
    results: Dict[str, Any]
    config: Dict[str, Any]


class CapacityMatrixAnalyzer(NotebookAnalyzer):
    """Analyzes capacity envelope data and creates matrices."""

    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Analyze capacity envelopes and create matrix visualization."""
        step_name = kwargs.get("step_name")
        if not step_name:
            return {"status": "error", "message": "step_name required"}

        step_data = results.get(step_name, {})
        envelopes = step_data.get("capacity_envelopes", {})

        if not envelopes:
            return {"status": "no_data", "message": f"No data for {step_name}"}

        try:
            matrix_data = self._extract_matrix_data(envelopes)
            if not matrix_data:
                return {
                    "status": "no_valid_data",
                    "message": f"No valid data in {step_name}",
                }

            df_matrix = pd.DataFrame(matrix_data)
            capacity_matrix = self._create_capacity_matrix(df_matrix)
            statistics = self._calculate_statistics(capacity_matrix)

            return {
                "status": "success",
                "step_name": step_name,
                "matrix_data": matrix_data,
                "capacity_matrix": capacity_matrix,
                "statistics": statistics,
                "visualization_data": self._prepare_visualization_data(capacity_matrix),
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error analyzing capacity matrix: {str(e)}",
                "step_name": step_name,
            }

    def _extract_matrix_data(self, envelopes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract matrix data from envelope data."""
        matrix_data = []

        for flow_path, envelope_data in envelopes.items():
            parsed_flow = self._parse_flow_path(flow_path)
            capacity = self._extract_capacity_value(envelope_data)

            if parsed_flow and capacity is not None:
                matrix_data.append(
                    {
                        "source": parsed_flow["source"],
                        "destination": parsed_flow["destination"],
                        "capacity": capacity,
                        "flow_path": flow_path,
                        "direction": parsed_flow["direction"],
                    }
                )

        return matrix_data

    def _parse_flow_path(self, flow_path: str) -> Optional[Dict[str, str]]:
        """Parse flow path to extract source and destination."""
        if "<->" in flow_path:
            source, destination = flow_path.split("<->", 1)
            return {
                "source": source.strip(),
                "destination": destination.strip(),
                "direction": "bidirectional",
            }
        elif "->" in flow_path:
            source, destination = flow_path.split("->", 1)
            return {
                "source": source.strip(),
                "destination": destination.strip(),
                "direction": "directed",
            }
        return None

    def _extract_capacity_value(self, envelope_data: Any) -> Optional[float]:
        """Extract capacity value from envelope data."""
        if isinstance(envelope_data, (int, float)):
            return float(envelope_data)

        if isinstance(envelope_data, dict):
            # Try different possible keys for capacity
            for key in [
                "capacity",
                "max_capacity",
                "envelope",
                "value",
                "max_value",
                "values",
            ]:
                if key in envelope_data:
                    cap_val = envelope_data[key]
                    if isinstance(cap_val, (list, tuple)) and len(cap_val) > 0:
                        return float(max(cap_val))
                    elif isinstance(cap_val, (int, float)):
                        return float(cap_val)

        return None

    def _create_capacity_matrix(self, df_matrix: pd.DataFrame) -> pd.DataFrame:
        """Create pivot table for matrix view."""
        return df_matrix.pivot_table(
            index="source",
            columns="destination",
            values="capacity",
            aggfunc="max",
            fill_value=0,
        )

    def _calculate_statistics(self, capacity_matrix: pd.DataFrame) -> Dict[str, Any]:
        """Calculate matrix statistics."""
        non_zero_values = capacity_matrix.values[capacity_matrix.values > 0]

        if len(non_zero_values) == 0:
            return {"has_data": False}

        # Count all non-self-loop connections for flow analysis
        non_self_loop_connections = 0

        for source in capacity_matrix.index:
            for dest in capacity_matrix.columns:
                if source != dest:  # Exclude self-loops
                    non_self_loop_connections += 1

        # Calculate meaningful connection density
        num_nodes = len(capacity_matrix.index)
        total_possible_connections = num_nodes * (num_nodes - 1)  # Exclude self-loops
        connection_density = (
            non_self_loop_connections / total_possible_connections * 100
            if total_possible_connections > 0
            else 0
        )

        return {
            "has_data": True,
            "total_connections": non_self_loop_connections,
            "total_possible": total_possible_connections,
            "connection_density": connection_density,
            "capacity_min": float(non_zero_values.min()),
            "capacity_max": float(non_zero_values.max()),
            "capacity_mean": float(non_zero_values.mean()),
            "capacity_p25": float(pd.Series(non_zero_values).quantile(0.25)),
            "capacity_p50": float(pd.Series(non_zero_values).quantile(0.50)),
            "capacity_p75": float(pd.Series(non_zero_values).quantile(0.75)),
            "num_sources": len(capacity_matrix.index),
            "num_destinations": len(capacity_matrix.columns),
        }

    def _prepare_visualization_data(
        self, capacity_matrix: pd.DataFrame
    ) -> Dict[str, Any]:
        """Prepare data for visualization."""
        return {
            "matrix_display": capacity_matrix.reset_index(),
            "has_data": capacity_matrix.sum().sum() > 0,
        }

    def get_description(self) -> str:
        return "Analyzes network capacity envelopes"

    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display capacity matrix analysis results."""
        if analysis["status"] != "success":
            print(f"❌ {analysis['message']}")
            return

        step_name = analysis.get("step_name", "Unknown")
        print(f"✅ Analyzing capacity matrix for {step_name}")

        stats = analysis["statistics"]
        if not stats["has_data"]:
            print("No capacity data available")
            return

        print("Matrix Statistics:")
        print(f"  Sources: {stats['num_sources']:,} nodes")
        print(f"  Destinations: {stats['num_destinations']:,} nodes")
        print(
            f"  Connections: {stats['total_connections']:,}/{stats['total_possible']:,} ({stats['connection_density']:.1f}%)"
        )
        print(
            f"  Capacity range: {stats['capacity_min']:,.2f} - {stats['capacity_max']:,.2f}"
        )
        print("  Capacity statistics:")
        print(f"    Mean: {stats['capacity_mean']:,.2f}")
        print(f"    P25: {stats['capacity_p25']:,.2f}")
        print(f"    P50 (median): {stats['capacity_p50']:,.2f}")
        print(f"    P75: {stats['capacity_p75']:,.2f}")

        viz_data = analysis["visualization_data"]
        if viz_data["has_data"]:
            matrix_display = viz_data["matrix_display"]

            show(
                matrix_display,
                caption=f"Capacity Matrix - {step_name}",
                scrollY="400px",
                scrollX=True,
                scrollCollapse=True,
                paging=False,
            )

    def analyze_and_display_all_steps(self, results: Dict[str, Any]) -> None:
        """Analyze and display capacity matrices for all relevant steps."""
        found_data = False

        for step_name, step_data in results.items():
            if isinstance(step_data, dict) and "capacity_envelopes" in step_data:
                found_data = True
                analysis = self.analyze(results, step_name=step_name)
                self.display_analysis(analysis)
                print()  # Add spacing between steps

        if not found_data:
            print("No capacity envelope data found in results")


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

        show(
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


class PackageManager:
    """Manages package installation and imports for notebooks."""

    REQUIRED_PACKAGES = {
        "itables": "itables",
        "matplotlib": "matplotlib",
    }

    @classmethod
    def check_and_install_packages(cls) -> Dict[str, Any]:
        """Check for required packages and install if missing."""
        import importlib
        import subprocess
        import sys

        missing_packages = []

        for package_name, pip_name in cls.REQUIRED_PACKAGES.items():
            try:
                importlib.import_module(package_name)
            except ImportError:
                missing_packages.append(pip_name)

        result = {
            "missing_packages": missing_packages,
            "installation_needed": len(missing_packages) > 0,
        }

        if missing_packages:
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install"] + missing_packages
                )
                result["installation_success"] = True
                result["message"] = (
                    f"Successfully installed: {', '.join(missing_packages)}"
                )
            except subprocess.CalledProcessError as e:
                result["installation_success"] = False
                result["error"] = str(e)
                result["message"] = f"Installation failed: {e}"
        else:
            result["message"] = "All required packages are available"

        return result

    @classmethod
    def setup_environment(cls) -> Dict[str, Any]:
        """Set up the complete notebook environment."""
        # Check and install packages
        install_result = cls.check_and_install_packages()

        if not install_result.get("installation_success", True):
            return install_result

        try:
            # Configure matplotlib
            plt.style.use("seaborn-v0_8")

            # Configure itables
            itables_opt.lengthMenu = [10, 25, 50, 100, 500, -1]
            itables_opt.maxBytes = 10**7  # 10MB limit
            itables_opt.maxColumns = 200  # Allow more columns

            # Configure warnings
            import warnings

            warnings.filterwarnings("ignore")

            return {
                "status": "success",
                "message": "Environment setup complete",
                **install_result,
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Environment setup failed: {str(e)}",
                **install_result,
            }


class DataLoader:
    """Handles loading and validation of analysis results."""

    @staticmethod
    def load_results(json_path: Union[str, Path]) -> Dict[str, Any]:
        """Load results from JSON file with comprehensive error handling."""
        json_path = Path(json_path)

        result = {
            "file_path": str(json_path),
            "success": False,
            "results": {},
            "message": "",
        }

        try:
            if not json_path.exists():
                result["message"] = f"Results file not found: {json_path}"
                return result

            with open(json_path, "r", encoding="utf-8") as f:
                results = json.load(f)

            if not isinstance(results, dict):
                result["message"] = "Invalid results format - expected dictionary"
                return result

            result.update(
                {
                    "success": True,
                    "results": results,
                    "message": f"Loaded {len(results):,} analysis steps from {json_path.name}",
                    "step_count": len(results),
                    "step_names": list(results.keys()),
                }
            )

        except json.JSONDecodeError as e:
            result["message"] = f"Invalid JSON format: {str(e)}"
        except Exception as e:
            result["message"] = f"Error loading results: {str(e)}"

        return result


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


# Example of how to use these classes:
def example_usage():
    """Example of how the new approach works."""

    # Load data (this is actual Python code, not a string template!)
    loader = DataLoader()
    load_result = loader.load_results("results.json")

    if load_result["success"]:
        results = load_result["results"]

        # Analyze capacity matrices
        capacity_analyzer = CapacityMatrixAnalyzer()
        for step_name in results.keys():
            analysis = capacity_analyzer.analyze(results, step_name=step_name)

            if analysis["status"] == "success":
                print(f"✅ Capacity analysis for {step_name}: {analysis['statistics']}")
            else:
                print(f"❌ {analysis['message']}")

        # Analyze flows
        flow_analyzer = FlowAnalyzer()
        flow_analysis = flow_analyzer.analyze(results)

        if flow_analysis["status"] == "success":
            print(f"✅ Flow analysis: {flow_analysis['statistics']}")
    else:
        print(f"❌ {load_result['message']}")
