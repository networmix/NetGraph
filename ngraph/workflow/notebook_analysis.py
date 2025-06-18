"""Notebook analysis components for NetGraph workflow results.

This module provides specialized analyzers for processing and visualizing network analysis
results in Jupyter notebooks. Each component handles specific data types and provides
both programmatic analysis and interactive display capabilities.

Core Components:
    NotebookAnalyzer: Abstract base class defining the analysis interface. All analyzers
        implement analyze() for data processing and display_analysis() for notebook output.
        Provides analyze_and_display() convenience method that chains analysis and display.

    AnalysisContext: Immutable dataclass containing execution context (step name, results,
        config) passed between analysis components for state management.

Utility Components:
    PackageManager: Handles runtime dependency verification and installation. Checks
        for required packages (itables, matplotlib) using importlib, installs missing
        packages via subprocess, and configures visualization environments (seaborn
        styling, itables display options, matplotlib backends).

    DataLoader: Provides robust JSON file loading with comprehensive error handling.
        Validates file existence, JSON format correctness, and expected data structure.
        Returns detailed status information including step counts and validation results.

Data Analyzers:
    CapacityMatrixAnalyzer: Processes capacity envelope data from network flow analysis.
        Extracts flow path information (source->destination, bidirectional), parses
        capacity values from various data structures, creates pivot tables for matrix
        visualization, and calculates flow density statistics. Handles self-loop exclusion
        and zero-flow inclusion for accurate network topology representation.

    FlowAnalyzer: Processes maximum flow calculation results. Extracts flow paths and
        values from workflow step data, computes flow statistics (min/max/avg/total),
        and generates comparative visualizations across multiple analysis steps using
        matplotlib bar charts.

    SummaryAnalyzer: Aggregates results across all workflow steps. Categorizes steps
        by analysis type (capacity envelopes, flow calculations, other), provides
        high-level metrics for workflow completion status and data distribution.
"""

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

        # Count all non-self-loop flows for analysis (including zero flows)
        non_self_loop_flows = 0

        for source in capacity_matrix.index:
            for dest in capacity_matrix.columns:
                if source != dest:  # Exclude only self-loops, include zero flows
                    capacity_val = capacity_matrix.loc[source, dest]
                    try:
                        numeric_val = pd.to_numeric(capacity_val, errors="coerce")
                        if pd.notna(
                            numeric_val
                        ):  # Include zero flows, exclude only NaN
                            non_self_loop_flows += 1
                    except (ValueError, TypeError):
                        continue

        # Calculate meaningful flow density
        num_nodes = len(capacity_matrix.index)
        total_possible_flows = num_nodes * (num_nodes - 1)  # Exclude self-loops
        flow_density = (
            non_self_loop_flows / total_possible_flows * 100
            if total_possible_flows > 0
            else 0
        )

        return {
            "has_data": True,
            "total_flows": non_self_loop_flows,
            "total_possible": total_possible_flows,
            "flow_density": flow_density,
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
        # Create capacity ranking table (max to min, including zero flows)
        capacity_ranking = []
        for source in capacity_matrix.index:
            for dest in capacity_matrix.columns:
                if source != dest:  # Exclude only self-loops, include zero flows
                    capacity_val = capacity_matrix.loc[source, dest]
                    try:
                        numeric_val = pd.to_numeric(capacity_val, errors="coerce")
                        if pd.notna(
                            numeric_val
                        ):  # Include zero flows, exclude only NaN
                            capacity_ranking.append(
                                {
                                    "Source": source,
                                    "Destination": dest,
                                    "Capacity": float(numeric_val),
                                    "Flow Path": f"{source} -> {dest}",
                                }
                            )
                    except (ValueError, TypeError):
                        continue

        # Sort by capacity (descending)
        capacity_ranking.sort(key=lambda x: x["Capacity"], reverse=True)
        capacity_ranking_df = pd.DataFrame(capacity_ranking)

        return {
            "matrix_display": capacity_matrix.reset_index(),
            "capacity_ranking": capacity_ranking_df,
            "has_data": capacity_matrix.sum().sum() > 0,
            "has_ranking_data": len(capacity_ranking) > 0,
        }

    def get_description(self) -> str:
        return "Analyzes network capacity envelopes"

    def _format_dataframe_for_display(self, df: pd.DataFrame) -> pd.DataFrame:
        """Format numeric columns in DataFrame with thousands separators for display.

        Args:
            df: Input DataFrame to format.

        Returns:
            A copy of the DataFrame with numeric values formatted with commas.
        """
        if df.empty:
            return df

        df_formatted = df.copy()
        for col in df_formatted.select_dtypes(include=["number"]):
            df_formatted[col] = df_formatted[col].map(
                lambda x: f"{x:,.0f}"
                if pd.notna(x) and x == int(x)
                else f"{x:,.1f}"
                if pd.notna(x)
                else x
            )
        return df_formatted

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
            f"  Flows: {stats['total_flows']:,}/{stats['total_possible']:,} ({stats['flow_density']:.1f}%)"
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
            # Display full capacity matrix
            matrix_display = viz_data["matrix_display"]
            matrix_display_formatted = self._format_dataframe_for_display(
                matrix_display
            )
            print("\n🔢 Full Capacity Matrix:")
            show(
                matrix_display_formatted,
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

    def analyze_flow_availability(
        self, results: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """Analyze total flow samples to create flow availability distribution (CDF).

        This method creates a cumulative distribution function (CDF) showing the
        probability that network flow performance is at or below a given level.
        The analysis processes total_flow_samples from Monte Carlo simulations
        to characterize network performance under failure scenarios.

        Args:
            results: Analysis results containing total_capacity_samples
            **kwargs: Additional parameters including step_name

        Returns:
            Dictionary containing:
            - flow_cdf: List of (flow_value, cumulative_probability) tuples
            - statistics: Summary statistics including percentiles
            - maximum_flow: Peak flow value observed (typically baseline)
            - status: Analysis status
        """
        step_name = kwargs.get("step_name")
        if not step_name:
            return {"status": "error", "message": "step_name required"}

        step_data = results.get(step_name, {})
        total_flow_samples = step_data.get("total_capacity_samples", [])

        if not total_flow_samples:
            return {
                "status": "no_data",
                "message": f"No total flow samples for {step_name}",
            }

        try:
            # Sort samples in ascending order for CDF construction
            sorted_samples = sorted(total_flow_samples)
            n_samples = len(sorted_samples)

            # Get maximum flow for normalization
            maximum_flow = max(sorted_samples)

            if maximum_flow == 0:
                return {
                    "status": "invalid_data",
                    "message": "All flow samples are zero",
                }

            # Create CDF: (relative_flow_fraction, cumulative_probability)
            flow_cdf = []
            for i, flow in enumerate(sorted_samples):
                # Cumulative probability that flow ≤ current value
                cumulative_prob = (i + 1) / n_samples
                relative_flow = flow / maximum_flow  # As fraction 0-1
                flow_cdf.append((relative_flow, cumulative_prob))

            # Create complementary CDF for availability analysis
            # (relative_flow_fraction, probability_of_achieving_at_least_this_flow)
            availability_curve = []
            for relative_flow, cum_prob in flow_cdf:
                availability_prob = 1 - cum_prob  # P(Flow ≥ flow) as fraction
                availability_curve.append((relative_flow, availability_prob))

            # Calculate key statistics
            statistics = self._calculate_flow_statistics(
                total_flow_samples, maximum_flow
            )

            # Prepare data for visualization
            viz_data = self._prepare_flow_cdf_visualization_data(
                flow_cdf, availability_curve, maximum_flow
            )

            return {
                "status": "success",
                "step_name": step_name,
                "flow_cdf": flow_cdf,
                "availability_curve": availability_curve,
                "statistics": statistics,
                "maximum_flow": maximum_flow,
                "total_samples": n_samples,
                "visualization_data": viz_data,
            }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Error analyzing flow availability: {str(e)}",
                "step_name": step_name,
            }

    def _calculate_flow_statistics(
        self, samples: List[float], maximum_flow: float
    ) -> Dict[str, Any]:
        """Calculate statistics for flow availability analysis."""
        if not samples or maximum_flow == 0:
            return {"has_data": False}

        # Key percentiles for flow distribution
        percentiles = [5, 10, 25, 50, 75, 90, 95, 99]
        flow_percentiles = {}

        sorted_samples = sorted(samples)
        n_samples = len(samples)

        for p in percentiles:
            # What flow value is exceeded (100-p)% of the time?
            idx = int((p / 100) * n_samples)
            if idx >= n_samples:
                idx = n_samples - 1
            elif idx < 0:
                idx = 0

            flow_at_percentile = sorted_samples[idx]
            relative_flow = (flow_at_percentile / maximum_flow) * 100
            flow_percentiles[f"p{p}"] = {
                "absolute": flow_at_percentile,
                "relative": relative_flow,
            }

        # Calculate additional statistics
        mean_flow = sum(samples) / len(samples)
        std_flow = pd.Series(samples).std()

        return {
            "has_data": True,
            "maximum_flow": maximum_flow,
            "minimum_flow": min(samples),
            "mean_flow": mean_flow,
            "median_flow": flow_percentiles["p50"]["absolute"],
            "flow_range": maximum_flow - min(samples),
            "flow_std": std_flow,
            "relative_mean": (mean_flow / maximum_flow) * 100,
            "relative_min": (min(samples) / maximum_flow) * 100,
            "relative_std": (std_flow / maximum_flow) * 100,
            "flow_percentiles": flow_percentiles,
            "total_samples": len(samples),
            "coefficient_of_variation": (std_flow / mean_flow) * 100
            if mean_flow > 0
            else 0,
        }

    def _prepare_flow_cdf_visualization_data(
        self,
        flow_cdf: List[tuple[float, float]],
        availability_curve: List[tuple[float, float]],
        maximum_flow: float,
    ) -> Dict[str, Any]:
        """Prepare data structure for flow CDF and percentile plot visualization."""
        if not flow_cdf or not availability_curve:
            return {"has_data": False}

        # Extract data for CDF plotting
        flow_values = [point[0] for point in flow_cdf]
        cumulative_probs = [point[1] for point in flow_cdf]

        # Create percentile plot data (percentile → flow value at that percentile)
        # Lower percentiles show higher flows (flows exceeded most of the time)
        percentiles = []
        flow_at_percentiles = []

        for rel_flow, avail_prob in availability_curve:
            # avail_prob = P(Flow ≥ rel_flow) = reliability/availability
            # percentile = (1 - avail_prob) = P(Flow < rel_flow)
            # But for network reliability, we want the exceedance percentile
            # So percentile = avail_prob (probability this flow is exceeded)
            percentile = avail_prob  # As fraction 0-1
            percentiles.append(percentile)
            flow_at_percentiles.append(rel_flow)

        # Create reliability thresholds for analysis
        reliability_thresholds = [99, 95, 90, 80, 70, 50]  # Reliability levels (%)
        threshold_flows = {}

        for threshold in reliability_thresholds:
            # Find flow value that is exceeded at this reliability level
            target_availability = threshold / 100  # Convert percentage to fraction
            flow_at_threshold = 0

            for rel_flow, avail_prob in availability_curve:
                if avail_prob >= target_availability:  # avail_prob is now a fraction
                    flow_at_threshold = rel_flow
                    break

            threshold_flows[f"{threshold}%"] = flow_at_threshold

        # Statistical measures for academic analysis
        # Gini coefficient for inequality measurement
        sorted_flows = sorted(flow_values)
        n = len(sorted_flows)
        cumsum = sum((i + 1) * flow for i, flow in enumerate(sorted_flows))
        total_sum = sum(sorted_flows)
        gini = (2 * cumsum) / (n * total_sum) - (n + 1) / n if total_sum > 0 else 0

        return {
            "has_data": True,
            "cdf_data": {
                "flow_values": flow_values,
                "cumulative_probabilities": cumulative_probs,
            },
            "percentile_data": {
                "percentiles": percentiles,
                "flow_at_percentiles": flow_at_percentiles,
            },
            "reliability_thresholds": threshold_flows,
            "distribution_metrics": {
                "gini_coefficient": gini,
                "flow_range_ratio": max(flow_values)
                - min(flow_values),  # Already relative
                "quartile_coefficient": self._calculate_quartile_coefficient(
                    sorted_flows
                ),
            },
        }

    def _calculate_quartile_coefficient(self, sorted_values: List[float]) -> float:
        """Calculate quartile coefficient of dispersion."""
        if len(sorted_values) < 4:
            return 0.0

        n = len(sorted_values)
        q1_idx = n // 4
        q3_idx = 3 * n // 4

        q1 = sorted_values[q1_idx]
        q3 = sorted_values[q3_idx]

        return (q3 - q1) / (q3 + q1) if (q3 + q1) > 0 else 0.0

    def analyze_and_display_flow_availability(
        self, results: Dict[str, Any], step_name: str
    ) -> None:
        """Analyze and display flow availability distribution with CDF visualization."""
        print(f"📊 Flow Availability Distribution Analysis: {step_name}")
        print("=" * 70)

        result = self.analyze_flow_availability(results, step_name=step_name)

        if result["status"] != "success":
            print(f"❌ Analysis failed: {result.get('message', 'Unknown error')}")
            return

        # Extract results
        stats = result["statistics"]
        viz_data = result["visualization_data"]
        maximum_flow = result["maximum_flow"]
        total_samples = result["total_samples"]

        # Display summary statistics
        print(f"🔢 Sample Statistics (n={total_samples}):")
        print(f"   Maximum Flow: {maximum_flow:.2f}")
        print(
            f"   Mean Flow:    {stats['mean_flow']:.2f} ({stats['relative_mean']:.1f}%)"
        )
        print(
            f"   Median Flow:  {stats['median_flow']:.2f} ({stats['flow_percentiles']['p50']['relative']:.1f}%)"
        )
        print(
            f"   Std Dev:      {stats['flow_std']:.2f} ({stats['relative_std']:.1f}%)"
        )
        print(f"   CV:           {stats['coefficient_of_variation']:.1f}%")
        print()

        # Display key percentiles
        print("📈 Flow Distribution Percentiles:")
        key_percentiles = ["p5", "p10", "p25", "p50", "p75", "p90", "p95", "p99"]
        for p_name in key_percentiles:
            if p_name in stats["flow_percentiles"]:
                p_data = stats["flow_percentiles"][p_name]
                percentile_num = p_name[1:]
                print(
                    f"   {percentile_num:>2}th percentile: {p_data['absolute']:8.2f} ({p_data['relative']:5.1f}%)"
                )
        print()

        # Display reliability analysis
        print("🎯 Network Reliability Analysis:")
        thresholds = viz_data["reliability_thresholds"]
        for reliability in ["99%", "95%", "90%", "80%"]:
            if reliability in thresholds:
                flow_fraction = thresholds[reliability]
                flow_pct = (
                    flow_fraction * 100
                )  # Convert fraction to percentage for display
                print(
                    f"   {reliability} reliability: ≥{flow_pct:5.1f}% of maximum flow"
                )
        print()

        # Display distribution characteristics
        print("📐 Distribution Characteristics:")
        dist_metrics = viz_data["distribution_metrics"]
        print(f"   Gini Coefficient:     {dist_metrics['gini_coefficient']:.3f}")
        print(f"   Quartile Coefficient: {dist_metrics['quartile_coefficient']:.3f}")
        print(f"   Range Ratio:          {dist_metrics['flow_range_ratio']:.3f}")
        print()

        # Create CDF visualization
        self._display_flow_cdf_plot(result)

        # Academic interpretation
        self._display_flow_distribution_interpretation(stats, viz_data)

    def _display_flow_cdf_plot(self, analysis_result: Dict[str, Any]) -> None:
        """Display flow CDF and percentile plots using matplotlib."""
        try:
            import matplotlib.pyplot as plt

            viz_data = analysis_result["visualization_data"]
            cdf_data = viz_data["cdf_data"]
            percentile_data = viz_data["percentile_data"]

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

            # Plot CDF
            ax1.plot(
                cdf_data["flow_values"],
                cdf_data["cumulative_probabilities"],
                "b-",
                linewidth=2,
                label="Empirical CDF",
            )
            ax1.set_xlabel("Relative Flow")
            ax1.set_ylabel("Cumulative Probability")
            ax1.set_title("Flow Distribution (CDF)")
            ax1.grid(True, alpha=0.3)
            ax1.legend()

            # Plot percentile curve (percentile → flow at that percentile)
            ax2.plot(
                percentile_data["percentiles"],
                percentile_data["flow_at_percentiles"],
                "r-",
                linewidth=2,
                label="Reliability Curve",
            )
            ax2.set_xlabel("Reliability Level")
            ax2.set_ylabel("Relative Flow")
            ax2.set_title("Flow at Reliability Levels")
            ax2.grid(True, alpha=0.3)
            ax2.legend()

            plt.tight_layout()
            plt.show()

        except ImportError:
            print(
                "📊 Visualization requires matplotlib. Install with: pip install matplotlib"
            )
        except Exception as e:
            print(f"⚠️  Visualization error: {e}")

    def _display_flow_distribution_interpretation(
        self, stats: Dict[str, Any], viz_data: Dict[str, Any]
    ) -> None:
        """Provide academic interpretation of flow distribution characteristics."""
        print("🎓 Statistical Interpretation:")

        # Coefficient of variation analysis
        cv = stats["coefficient_of_variation"]
        if cv < 10:
            variability = "low variability"
        elif cv < 25:
            variability = "moderate variability"
        elif cv < 50:
            variability = "high variability"
        else:
            variability = "very high variability"

        print(f"   • Flow distribution exhibits {variability} (CV = {cv:.1f}%)")

        # Gini coefficient analysis
        gini = viz_data["distribution_metrics"]["gini_coefficient"]
        if gini < 0.2:
            inequality = "relatively uniform"
        elif gini < 0.4:
            inequality = "moderate inequality"
        elif gini < 0.6:
            inequality = "substantial inequality"
        else:
            inequality = "high inequality"

        print(f"   • Performance distribution is {inequality} (Gini = {gini:.3f})")

        # Reliability assessment
        p95_rel = stats["flow_percentiles"]["p95"]["relative"]
        p5_rel = stats["flow_percentiles"]["p5"]["relative"]
        reliability_range = p95_rel - p5_rel

        if reliability_range < 10:
            reliability = "highly reliable"
        elif reliability_range < 25:
            reliability = "moderately reliable"
        elif reliability_range < 50:
            reliability = "variable performance"
        else:
            reliability = "unreliable performance"

        print(
            f"   • Network demonstrates {reliability} (90% range: {reliability_range:.1f}%)"
        )

        # Tail risk analysis
        p5_absolute = stats["flow_percentiles"]["p5"]["relative"]
        if p5_absolute < 25:
            tail_risk = "significant tail risk"
        elif p5_absolute < 50:
            tail_risk = "moderate tail risk"
        elif p5_absolute < 75:
            tail_risk = "limited tail risk"
        else:
            tail_risk = "minimal tail risk"

        print(
            f"   • Analysis indicates {tail_risk} (5th percentile at {p5_absolute:.1f}%)"
        )


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
