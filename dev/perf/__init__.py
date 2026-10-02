#!/usr/bin/env python3
"""Benchmarks for NetGraph operations, with complexity fits and plots.

Main components:
- BenchmarkProfile: Named set of cases analyzed together
- BenchmarkSample: Timing statistics for one case
- BenchmarkResult: Samples from one profile run
- PerformanceAnalyzer: Prints summaries, complexity fits, and regressions
- BenchmarkRunner: Runs profiles and collects samples
- PerformanceVisualizer: Writes plots and the results JSON

Usage:
    from dev.perf import BenchmarkRunner, BENCHMARK_PROFILES

    runner = BenchmarkRunner()
    profile = BENCHMARK_PROFILES[0]
    result = runner.run_profile(profile)

    from dev.perf import PerformanceAnalyzer
    analyzer = PerformanceAnalyzer()
    analyzer.add_run(result)
    analyzer.print_analysis_report()

    from dev.perf import PerformanceVisualizer
    viz = PerformanceVisualizer()
    viz.create_summary_report(analyzer, timestamp="manual")
"""

from __future__ import annotations

from .analysis import PerformanceAnalyzer
from .core import (
    CUBIC,
    LINEAR,
    N_LOG_N,
    QUADRATIC,
    BenchmarkProfile,
    BenchmarkResult,
    BenchmarkSample,
    BenchmarkTask,
    ComplexityAnalysisSpec,
    ComplexityModel,
    calculate_expected_time,
)
from .profiles import BENCHMARK_PROFILES, get_profile_by_name, get_profile_names
from .runner import BenchmarkRunner
from .topology import Clos2TierTopology, Topology
from .visualization import PerformanceVisualizer

__all__ = [
    # Core data structures
    "BenchmarkProfile",
    "BenchmarkResult",
    "BenchmarkSample",
    "BenchmarkTask",
    "ComplexityAnalysisSpec",
    "ComplexityModel",
    # Complexity models
    "LINEAR",
    "N_LOG_N",
    "QUADRATIC",
    "CUBIC",
    # Analysis
    "PerformanceAnalyzer",
    # Execution
    "BenchmarkRunner",
    # Visualization
    "PerformanceVisualizer",
    # Topology
    "Topology",
    "Clos2TierTopology",
    # Benchmark profiles
    "BENCHMARK_PROFILES",
    "get_profile_by_name",
    "get_profile_names",
    # Utilities
    "calculate_expected_time",
]
