"""Profiling for NetGraph workflow execution.

Times each workflow step: wall clock, and process CPU time across all threads
(native work included). ``cProfile`` records the Python calls of the profiled
thread, and ``tracemalloc`` can record peak memory. Steps that take more than
10% of total wall time are reported as bottlenecks.
"""

from __future__ import annotations

import cProfile
import pstats
import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple

from ngraph.logging import get_logger
from ngraph.utils.values import flag

logger = get_logger(__name__)


def _top_functions(stats: pstats.Stats, limit: int) -> List[Tuple[str, float, int]]:
    """Return (function, total_time, call_count) for the `limit` costliest functions.

    Reads the `stats` mapping of pstats (values are (cc, nc, tt, ct, callers)),
    which typeshed does not declare, hence the getattr.
    """
    stats_data = getattr(stats, "stats", {})
    ranked = sorted(stats_data.items(), key=lambda item: item[1][2], reverse=True)
    return [
        (f"{func[0]}:{func[1]}({func[2]})", stat[2], stat[0])
        for func, stat in ranked[:limit]
    ]


@dataclass
class StepProfile:
    """Performance profile data for a single workflow step.

    Attributes:
        step_name: Name of the workflow step.
        step_type: Class name of the workflow step.
        wall_time: Total wall-clock time in seconds.
        cpu_time: Process CPU time in seconds over the step, all threads and
            native work included; it can exceed ``wall_time``.
        function_calls: Number of function calls during execution.
        memory_peak: Peak traced memory in bytes; None unless memory
            tracking ran for this step.
        cprofile_stats: cProfile statistics for this step.
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
        total_cpu_time: Total process CPU time across all steps.
        total_function_calls: Total function calls across all steps.
        bottlenecks: List of performance bottlenecks (>10% execution time).
        analysis_summary: Aggregate metrics computed by ``analyze_performance``.
    """

    step_profiles: List[StepProfile] = field(default_factory=list)
    total_wall_time: float = 0.0
    total_cpu_time: float = 0.0
    total_function_calls: int = 0
    bottlenecks: List[Dict[str, Any]] = field(default_factory=list)
    analysis_summary: Dict[str, Any] = field(default_factory=dict)


class PerformanceProfiler:
    """CPU profiler for NetGraph workflow execution.

    Profiles each workflow step with cProfile and flags steps that take more
    than 10% of total wall time as bottlenecks.
    """

    def __init__(self, track_memory: bool = False):
        """Initialize the performance profiler.

        Args:
            track_memory: If True, record peak memory per step using tracemalloc.
        """
        self.results = ProfileResults()
        self._scenario_start_time: Optional[float] = None
        self._scenario_end_time: Optional[float] = None
        self._track_memory: bool = flag(
            track_memory, "PerformanceProfiler.track_memory"
        )

    def start_scenario(self) -> None:
        """Record the scenario start time."""
        self._scenario_start_time = time.perf_counter()
        logger.debug("Started scenario-level profiling")

    def end_scenario(self) -> None:
        """Record total wall time and sum CPU time and calls across steps.

        Logs a warning and returns early if ``start_scenario`` was not called.
        """
        if self._scenario_start_time is None:
            logger.warning(
                "Scenario profiling ended without start - timing may be inaccurate"
            )
            return

        self._scenario_end_time = time.perf_counter()
        self.results.total_wall_time = (
            self._scenario_end_time - self._scenario_start_time
        )

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
        """Profile the enclosed block as one workflow step.

        A StepProfile is appended when the block exits, including on error.

        Args:
            step_name: Name of the workflow step being profiled.
            step_type: Class name of the workflow step.

        Yields:
            None
        """
        logger.debug(f"Starting profiling for step: {step_name} ({step_type})")

        start_time = time.perf_counter()
        start_cpu = time.process_time()
        profiler = cProfile.Profile()
        profiler.enable()

        # Per-step tracemalloc, when requested, to capture peak memory. Skipped
        # while another session is tracing, since stopping ours would end it.
        track_memory = self._track_memory and not tracemalloc.is_tracing()
        if track_memory:
            tracemalloc.start()
        elif self._track_memory:
            logger.warning(
                "tracemalloc is already tracing; peak memory for step %s is not "
                "recorded",
                step_name,
            )

        try:
            yield
        finally:
            # The CPU reading sits inside the wall-clock window.
            cpu_time = time.process_time() - start_cpu
            wall_time = time.perf_counter() - start_time

            profiler.disable()

            stats = pstats.Stats(profiler)

            # pstats keeps per-function tuples (cc, nc, tt, ct, callers) in an
            # undeclared `stats` attribute: primitive calls, total calls,
            # internal time, cumulative time. Calls sum cc.
            stats_data = getattr(stats, "stats", {})
            function_calls = sum(stat_tuple[0] for stat_tuple in stats_data.values())

            memory_peak: Optional[float] = None
            if track_memory:
                memory_peak = float(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()

            step_profile = StepProfile(
                step_name=step_name,
                step_type=step_type,
                wall_time=wall_time,
                cpu_time=cpu_time,
                function_calls=function_calls,
                memory_peak=memory_peak,
                cprofile_stats=stats,
            )

            self.results.step_profiles.append(step_profile)

            logger.debug(
                f"Completed profiling for step: {step_name} "
                f"({wall_time:.3f}s wall, {cpu_time:.3f}s CPU, {function_calls:,} calls)"
            )

    def analyze_performance(self) -> None:
        """Flag steps above 10% of total wall time and fill ``analysis_summary``.

        Call after ``end_scenario``, which sets the total wall time.
        """
        if not self.results.step_profiles:
            logger.warning("No step profiles available for analysis")
            return

        logger.debug("Starting performance analysis")

        sorted_steps = sorted(
            self.results.step_profiles, key=lambda p: p.wall_time, reverse=True
        )

        total_time = self.results.total_wall_time
        step_percentages = []

        for step in sorted_steps:
            if total_time > 0:
                percentage = (step.wall_time / total_time) * 100
                step_percentages.append((step, percentage))

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


class PerformanceReporter:
    """Render profiling results as a plain-text report.

    Covers per-step timing, bottleneck identification, and tuning suggestions.
    """

    def __init__(self, results: ProfileResults):
        """Initialize the performance reporter.

        Args:
            results: Profiling data, after ``analyze_performance`` has run.
        """
        self.results = results

    def generate_report(self) -> str:
        """Render the full report.

        Sections: summary, step timings, bottlenecks (when any), and top
        functions per bottleneck step.

        Returns:
            Report text, or a one-line message when no steps were profiled.
        """
        if not self.results.step_profiles:
            return "No profiling data available to report."

        report_lines = []
        report_lines.extend(
            ["=" * 80, "NETGRAPH PERFORMANCE PROFILING REPORT", "=" * 80, ""]
        )
        report_lines.extend(self._generate_summary())
        report_lines.extend(self._generate_timing_analysis())
        if self.results.bottlenecks:
            report_lines.extend(self._generate_bottleneck_analysis())
        report_lines.extend(self._generate_detailed_analysis())
        report_lines.extend(["", "=" * 80, "END OF PERFORMANCE REPORT", "=" * 80])

        return "\n".join(report_lines)

    def _generate_summary(self) -> List[str]:
        """Return section 1: totals, CPU efficiency, and call rate."""
        summary = self.results.analysis_summary

        lines = [
            "1. SUMMARY",
            "-" * 40,
            f"Total Execution Time: {self.results.total_wall_time:.3f} seconds",
            f"Total CPU Time (process, all threads): {self.results.total_cpu_time:.3f} seconds",
            f"CPU Efficiency: {summary.get('cpu_efficiency', 0.0):.1%} "
            "(process CPU across all threads / wall time; can exceed 100%)",
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
        """Return section 2: one table row per step, slowest first."""
        lines = ["2. WORKFLOW STEP TIMING ANALYSIS", "-" * 40, ""]

        sorted_steps = sorted(
            self.results.step_profiles, key=lambda p: p.wall_time, reverse=True
        )

        headers = [
            "Step Name",
            "Type",
            "Wall Time",
            "CPU Time",
            "Calls",
            "% Total",
            "Memory",
        ]

        col_widths = [len(h) for h in headers]

        table_data = []
        for step in sorted_steps:
            percentage = (
                (step.wall_time / self.results.total_wall_time) * 100
                if self.results.total_wall_time > 0
                else 0
            )
            mem_str = "-"
            if step.memory_peak is not None:
                mem_mb = float(step.memory_peak) / (1024 * 1024)
                mem_str = f"{mem_mb:.1f}MB"

            row = [
                step.step_name,
                step.step_type,
                f"{step.wall_time:.3f}s",
                f"{step.cpu_time:.3f}s",
                f"{step.function_calls:,}",
                f"{percentage:.1f}%",
                mem_str,
            ]
            table_data.append(row)

            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(cell))

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
        """Return section 3, classifying each bottleneck by CPU/wall ratio."""
        lines = ["3. PERFORMANCE BOTTLENECK ANALYSIS", "-" * 40, ""]

        for i, bottleneck in enumerate(self.results.bottlenecks, 1):
            efficiency = bottleneck["efficiency_ratio"]

            # A low CPU/wall ratio means the step spent most of its time waiting.
            if efficiency < 0.3:
                workload_type = "I/O-bound workload"
                recommendation = "Investigate I/O operations, external dependencies, or process coordination"
            elif efficiency > 0.8:
                workload_type = "CPU-intensive workload"
                recommendation = "Consider algorithmic optimization"
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
        """Return section 4: top five functions per bottleneck step.

        The functions are ranked by cProfile's internal time, which covers the
        profiled thread only; worker threads count only in the process CPU.
        """
        lines = ["4. DETAILED FUNCTION ANALYSIS", "-" * 40, ""]

        for bottleneck in self.results.bottlenecks:
            step_name = bottleneck["step_name"]
            lines.append(
                "Top functions by cProfile internal time (profiled thread) in "
                f"'{step_name}':"
            )

            profiler = None
            for profile in self.results.step_profiles:
                if profile.step_name == step_name:
                    profiler = profile
                    break

            if profiler and profiler.cprofile_stats:
                for func_name, total_time, calls in _top_functions(
                    profiler.cprofile_stats, 5
                ):
                    lines.append(f"   {func_name}")
                    lines.append(f"      Time: {total_time:.4f}s, Calls: {calls:,}")

                lines.append("")
            else:
                lines.append("   No detailed profiling data available")
                lines.append("")

        return lines
