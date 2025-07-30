#!/usr/bin/env python3
"""NetGraph Performance Analysis Module.

This module benchmarks and processes NetGraph network modeling operations.

Core Components:
- BenchmarkProfile: Direct topology configuration
- BenchmarkSample: Single benchmark measurement
- BenchmarkResult: Collection of samples from one profile
- PerformanceAnalyzer: Analysis and reporting engine
- BenchmarkRunner: Execution engine
- PerformanceVisualizer: Chart and plot generation

Usage:
    from dev.perf import BenchmarkRunner, BENCHMARK_PROFILES

    runner = BenchmarkRunner()
    profile = BENCHMARK_PROFILES[0]  # Get first profile
    result = runner.run_profile(profile)

    # Analyze performance
    from dev.perf import PerformanceAnalyzer
    analyzer = PerformanceAnalyzer()
    analyzer.add_run(result)

    # Generate plots
    from dev.perf import PerformanceVisualizer
    viz = PerformanceVisualizer()
    viz.plot_complexity_analysis(analyzer, "shortest_path")
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
