"""Performance profiling instrumentation for NetGraph workflow execution.

CPU profiler with workflow step timing, function analysis, and bottleneck detection.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from ngraph.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StepProfile:
    """Performance profile data for a single workflow step.

    Attributes:
        step_name: Name of the workflow step.
        step_type: Type/class name of the workflow step.
        wall_time: Total wall-clock time in seconds.
        cpu_time: CPU time spent in step execution.
        function_calls: Number of function calls during execution.
        memory_peak: Peak memory usage during step (if available).
        cprofile_stats: Detailed cProfile statistics object.
    """

    step_name: str
    step_type: str
    wall_time: float
    cpu_time: float
    function_calls: int
    memory_peak: Optional[float] = None
    cprofile_stats: Optional[pstats.Stats] = None


@dataclass
class ProfileResults:
    """Profiling results for a scenario execution.

    Attributes:
        step_profiles: List of individual step performance profiles.
        total_wall_time: Total wall-clock time for entire scenario.
        total_cpu_time: Total CPU time across all steps.
        total_function_calls: Total function calls across all steps.
        bottlenecks: List of performance bottlenecks (>10% execution time).
        analysis_summary: Performance metrics and statistics.
    """

    step_profiles: List[StepProfile] = field(default_factory=list)
    total_wall_time: float = 0.0
    total_cpu_time: float = 0.0
    total_function_calls: int = 0
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class PerformanceProfiler:
    """CPU profiler for NetGraph workflow execution.

    Profiles workflow steps using cProfile and identifies bottlenecks.
    """

    def __init__(self):
        """Initialize the performance profiler."""
        self.results = ProfileResults()
        self._scenario_start_time: Optional[float] = None
        self._scenario_end_time: Optional[float] = None

    def start_scenario(self) -> None:
        """Start profiling for the entire scenario execution."""
        self._scenario_start_time = time.perf_counter()
        logger.debug("Started scenario-level profiling")

    def end_scenario(self) -> None:
        """End profiling for the entire scenario execution."""
        if self._scenario_start_time is None:
            logger.warning(
                "Scenario profiling ended without start - timing may be inaccurate"
            )
            return

        self._scenario_end_time = time.perf_counter()
        self.results.total_wall_time = (
            self._scenario_end_time - self._scenario_start_time
        )

        # Calculate aggregate statistics
        self.results.total_cpu_time = sum(
            p.cpu_time for p in self.results.step_profiles
        )
        self.results.total_function_calls = sum(
            p.function_calls for p in self.results.step_profiles
        )

        logger.debug(
            f"Scenario profiling completed: {self.results.total_wall_time:.3f}s wall time"
        )

    @contextmanager
    def profile_step(
        self, step_name: str, step_type: str
    ) -> Generator[None, None, None]:
        """Context manager for profiling individual workflow steps.

        Args:
            step_name: Name of the workflow step being profiled.
            step_type: Type/class name of the workflow step.

        Yields:
            None
        """
        logger.debug(f"Starting profiling for step: {step_name} ({step_type})")

        # Initialize profiling data
        start_time = time.perf_counter()
        profiler = cProfile.Profile()
        profiler.enable()

        try:
            yield
        finally:
            # Capture end time
            end_time = time.perf_counter()
            wall_time = end_time - start_time

            # Capture CPU profiling data
            profiler.disable()

            # Create stats object for analysis
            stats_stream = io.StringIO()
            stats = pstats.Stats(profiler, stream=stats_stream)

            # Extract CPU time and function call counts
            # Access stats data through the stats attribute (pstats internal structure)
            stats_data = getattr(stats, "stats", {})
            # stats_data values are tuples: (cc, nc, tt, ct, callers)
            # cc=call count, nc=number of calls, tt=total time, ct=cumulative time
            cpu_time = sum(
                stat_tuple[2] for stat_tuple in stats_data.values()
            )  # tt = total time
            function_calls = sum(
                stat_tuple[0] for stat_tuple in stats_data.values()
            )  # cc = call count

            # Create step profile
            step_profile = StepProfile(
                step_name=step_name,
                step_type=step_type,
                wall_time=wall_time,
                cpu_time=cpu_time,
                function_calls=function_calls,
                cprofile_stats=stats,
            )

            self.results.step_profiles.append(step_profile)

            logger.debug(
                f"Completed profiling for step: {step_name} "
                f"({wall_time:.3f}s wall, {cpu_time:.3f}s CPU, {function_calls:,} calls)"
            )

    def analyze_performance(self) -> None:
        """Analyze profiling results and identify bottlenecks.

        Calculates timing percentages and identifies steps consuming >10% of execution time.
        """
        if not self.results.step_profiles:
            logger.warning("No step profiles available for analysis")
            return

        logger.debug("Starting performance analysis")

        # Identify time-consuming steps
        sorted_steps = sorted(
            self.results.step_profiles, key=lambda p: p.wall_time, reverse=True
        )

        # Calculate percentage of total time for each step
        total_time = self.results.total_wall_time
        step_percentages = []

        for step in sorted_steps:
            if total_time > 0:
                percentage = (step.wall_time / total_time) * 100
                step_percentages.append((step, percentage))

        # Identify bottlenecks (steps taking >10% of total time)
        bottlenecks = []
        for step, percentage in step_percentages:
            if percentage > 10.0:
                bottleneck = {
                    "step_name": step.step_name,
                    "step_type": step.step_type,
                    "wall_time": step.wall_time,
                    "cpu_time": step.cpu_time,
                    "percentage": percentage,
                    "function_calls": step.function_calls,
                    "efficiency_ratio": step.cpu_time / step.wall_time
                    if step.wall_time > 0
                    else 0.0,
                }
                bottlenecks.append(bottleneck)

        self.results.bottlenecks = bottlenecks

        # Generate analysis summary
        self.results.analysis_summary = {
            "total_steps": len(self.results.step_profiles),
            "slowest_step": sorted_steps[0].step_name if sorted_steps else None,
            "slowest_step_time": sorted_steps[0].wall_time if sorted_steps else 0.0,
            "bottleneck_count": len(bottlenecks),
            "avg_step_time": total_time / len(self.results.step_profiles)
            if self.results.step_profiles
            else 0.0,
            "cpu_efficiency": (self.results.total_cpu_time / total_time)
            if total_time > 0
            else 0.0,
            "total_function_calls": self.results.total_function_calls,
            "calls_per_second": self.results.total_function_calls / total_time
            if total_time > 0
            else 0.0,
        }

        logger.debug(
            f"Performance analysis completed: {len(bottlenecks)} bottlenecks identified"
        )

    def get_top_functions(
        self, step_name: str, limit: int = 10
    ) -> List[Tuple[str, float, int]]:
        """Get the top CPU-consuming functions for a specific step.

        Args:
            step_name: Name of the workflow step to analyze.
            limit: Maximum number of functions to return.

        Returns:
            List of tuples containing (function_name, cpu_time, call_count).
        """
        step_profile = next(
            (p for p in self.results.step_profiles if p.step_name == step_name), None
        )
        if not step_profile or not step_profile.cprofile_stats:
            return []

        stats = step_profile.cprofile_stats

        # Sort by total time and extract top functions
        # Access stats data through the stats attribute (pstats internal structure)
        stats_data = getattr(stats, "stats", {})
        # stats_data values are tuples: (cc, nc, tt, ct, callers)
        sorted_stats = sorted(
            stats_data.items(),
            key=lambda x: x[1][2],
            reverse=True,  # Sort by total time (tt)
        )

        top_functions = []
        for func_info, stat_tuple in sorted_stats[:limit]:
            func_name = f"{func_info[0]}:{func_info[1]}({func_info[2]})"
            # stat_tuple = (cc, nc, tt, ct, callers)
            top_functions.append(
                (func_name, stat_tuple[2], stat_tuple[0])
            )  # (name, total_time, call_count)

        return top_functions

    def save_detailed_profile(
        self, output_path: Path, step_name: Optional[str] = None
    ) -> None:
        """Save detailed profiling data to a file.

        Args:
            output_path: Path where the profile data should be saved.
            step_name: Optional step name to save profile for specific step only.
        """
        if step_name:
            step_profile = next(
                (p for p in self.results.step_profiles if p.step_name == step_name),
                None,
            )
            if step_profile and step_profile.cprofile_stats:
                step_profile.cprofile_stats.dump_stats(str(output_path))
                logger.info(
                    f"Detailed profile for step '{step_name}' saved to: {output_path}"
                )
            else:
                logger.warning(
                    f"No detailed profile data available for step: {step_name}"
                )
        else:
            # Save combined profile data (if available)
            logger.warning("Combined profile saving not yet implemented")


class PerformanceReporter:
    """Formats and displays performance profiling results.

    Generates text reports with timing analysis, bottleneck identification, and optimization suggestions.
    """

    def __init__(self, results: ProfileResults):
        """Initialize the performance reporter.

        Args:
            results: ProfileResults object containing profiling data to report.
        """
        self.results = results

    def generate_report(self) -> str:
        """Generate performance report.

        Returns:
            Formatted performance report string.
        """
        if not self.results.step_profiles:
            return "No profiling data available to report."

        report_lines = []

        # Report header
        report_lines.extend(
            ["=" * 80, "NETGRAPH PERFORMANCE PROFILING REPORT", "=" * 80, ""]
        )

        # Executive summary
        report_lines.extend(self._generate_executive_summary())

        # Step-by-step timing analysis
        report_lines.extend(self._generate_timing_analysis())

        # Bottleneck analysis
        if self.results.bottlenecks:
            report_lines.extend(self._generate_bottleneck_analysis())

        # Detailed function analysis
        report_lines.extend(self._generate_detailed_analysis())

        # Report footer
        report_lines.extend(["", "=" * 80, "END OF PERFORMANCE REPORT", "=" * 80])

        return "\n".join(report_lines)

    def _generate_executive_summary(self) -> List[str]:
        """Generate executive summary section of the report."""
        summary = self.results.analysis_summary

        lines = [
            "1. SUMMARY",
            "-" * 40,
            f"Total Execution Time: {self.results.total_wall_time:.3f} seconds",
            f"Total CPU Time: {self.results.total_cpu_time:.3f} seconds",
            f"CPU Efficiency: {summary.get('cpu_efficiency', 0.0):.1%}",
            f"Total Workflow Steps: {summary.get('total_steps', 0)}",
            f"Average Step Time: {summary.get('avg_step_time', 0.0):.3f} seconds",
            f"Total Function Calls: {summary.get('total_function_calls', 0):,}",
            f"Function Calls/Second: {summary.get('calls_per_second', 0.0):,.0f}",
            "",
        ]

        if summary.get("bottleneck_count", 0) > 0:
            lines.append(
                f"{summary['bottleneck_count']} performance bottleneck(s) identified"
            )
            lines.append("")

        return lines

    def _generate_timing_analysis(self) -> List[str]:
        """Generate step-by-step timing analysis section."""
        lines = ["2. WORKFLOW STEP TIMING ANALYSIS", "-" * 40, ""]

        # Sort steps by execution time
        sorted_steps = sorted(
            self.results.step_profiles, key=lambda p: p.wall_time, reverse=True
        )

        # Create formatted table
        headers = ["Step Name", "Type", "Wall Time", "CPU Time", "Calls", "% Total"]

        # Calculate column widths
        col_widths = [len(h) for h in headers]

        table_data = []
        for step in sorted_steps:
            percentage = (
                (step.wall_time / self.results.total_wall_time) * 100
                if self.results.total_wall_time > 0
                else 0
            )
            row = [
                step.step_name,
                step.step_type,
                f"{step.wall_time:.3f}s",
                f"{step.cpu_time:.3f}s",
                f"{step.function_calls:,}",
                f"{percentage:.1f}%",
            ]
            table_data.append(row)

            # Update column widths
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))

        # Format table
        separator = "  "
        header_line = separator.join(
            h.ljust(col_widths[i]) for i, h in enumerate(headers)
        )
        lines.append(header_line)
        lines.append("-" * len(header_line))

        for row in table_data:
            line = separator.join(
                cell.ljust(col_widths[i]) for i, cell in enumerate(row)
            )
            lines.append(line)

        lines.append("")
        return lines

    def _generate_bottleneck_analysis(self) -> List[str]:
        """Generate bottleneck analysis section."""
        lines = ["3. PERFORMANCE BOTTLENECK ANALYSIS", "-" * 40, ""]

        for i, bottleneck in enumerate(self.results.bottlenecks, 1):
            efficiency = bottleneck["efficiency_ratio"]

            # Classify workload type and generate specific recommendation
            if efficiency < 0.3:
                workload_type = "I/O-bound workload"
                recommendation = "Investigate I/O operations, external dependencies, or process coordination"
            elif efficiency > 0.8:
                workload_type = "CPU-intensive workload"
                recommendation = "Consider algorithmic optimization or parallelization"
            else:
                workload_type = "Mixed workload"
                recommendation = (
                    "Profile individual functions to identify optimization targets"
                )

            lines.extend(
                [
                    f"Bottleneck #{i}: {bottleneck['step_name']} ({bottleneck['step_type']})",
                    f"   Wall Time: {bottleneck['wall_time']:.3f}s ({bottleneck['percentage']:.1f}% of total)",
                    f"   CPU Time: {bottleneck['cpu_time']:.3f}s",
                    f"   Function Calls: {bottleneck['function_calls']:,}",
                    f"   CPU Efficiency: {bottleneck['efficiency_ratio']:.1%} ({workload_type})",
                    f"   Recommendation: {recommendation}",
                    "",
                ]
            )

        return lines

    def _generate_detailed_analysis(self) -> List[str]:
        """Generate detailed function-level analysis section."""
        lines = ["4. DETAILED FUNCTION ANALYSIS", "-" * 40, ""]

        # Show top functions for each bottleneck step
        for bottleneck in self.results.bottlenecks:
            step_name = bottleneck["step_name"]
            lines.append(f"Top CPU-consuming functions in '{step_name}':")

            # Get profiler reference to access top functions
            profiler = None
            for profile in self.results.step_profiles:
                if profile.step_name == step_name:
                    profiler = profile
                    break

            if profiler and profiler.cprofile_stats:
                # Access stats data through the stats attribute (pstats internal structure)
                stats_data = getattr(profiler.cprofile_stats, "stats", {})

                # Sort by total time and get top 5
                # stats_data values are tuples: (cc, nc, tt, ct, callers)
                sorted_funcs = sorted(
                    stats_data.items(),
                    key=lambda x: x[1][2],
                    reverse=True,  # Sort by total time (tt)
                )[:5]

                for func_info, stat_tuple in sorted_funcs:
                    func_name = f"{func_info[0]}:{func_info[1]}({func_info[2]})"
                    lines.append(f"   {func_name}")
                    # stat_tuple = (cc, nc, tt, ct, callers)
                    lines.append(
                        f"      Time: {stat_tuple[2]:.4f}s, Calls: {stat_tuple[0]:,}"
                    )

                lines.append("")
            else:
                lines.append("   No detailed profiling data available")
                lines.append("")

        return lines
