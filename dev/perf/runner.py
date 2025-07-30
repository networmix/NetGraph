#!/usr/bin/env python3
"""Executor that turns a `BenchmarkProfile` into a `BenchmarkResult`."""

from __future__ import annotations

import gc
import statistics
import time
from typing import Any, Callable

import networkx as nx

from ngraph.lib.algorithms.max_flow import calc_max_flow
from ngraph.lib.algorithms.spf import spf

from .core import (
    BenchmarkCase,
    BenchmarkProfile,
    BenchmarkResult,
    BenchmarkSample,
    BenchmarkTask,
)
from .topology import Topology


def _time_func(func: Callable[[], Any], runs: int) -> dict[str, float]:
    """Time function execution over multiple runs.

    Includes GC control to reduce variance from garbage collection.
    Performs warm-up runs before timing to reduce JIT compilation effects.

    Args:
        func: Function to time (should take no arguments).
        runs: Number of timing runs to perform.

    Returns:
        Dictionary with timing statistics: mean, median, std, min, max, rounds.
    """
    # Disable GC during timing to reduce variance
    gc_was_enabled = gc.isenabled()
    gc.disable()

    try:
        # Force collection before timing
        gc.collect()

        # Warm-up runs to reduce JIT compilation and cache effects
        WARMUP_RUNS = 10
        for _ in range(min(WARMUP_RUNS, runs)):
            func()

        # Actual timing runs
        samples = []
        NANOSECONDS_TO_SECONDS = 1e9
        for _ in range(runs):
            # Force minor collection between runs to prevent buildup
            gc.collect(0)

            start = time.perf_counter_ns()
            func()
            samples.append((time.perf_counter_ns() - start) / NANOSECONDS_TO_SECONDS)

        return {
            "mean": statistics.mean(samples),
            "median": statistics.median(samples),
            "std": statistics.stdev(samples) if len(samples) > 1 else 0.0,
            "min": min(samples),
            "max": max(samples),
            "rounds": len(samples),
        }
    finally:
        # Re-enable GC if it was enabled before
        if gc_was_enabled:
            gc.enable()


def _execute_spf_benchmark(case: BenchmarkCase, iterations: int) -> BenchmarkSample:
    """Execute SPF benchmark for a given case.

    Creates network/graph once and reuses it across iterations to reduce variance.
    Uses the first node as the source for shortest path calculation.

    Args:
        case: Benchmark case containing topology and configuration.
        iterations: Number of timing iterations to perform.

    Returns:
        BenchmarkSample with timing statistics and metadata.
    """
    topology: Topology = case.inputs["topology"]

    # Create network and graph once outside timing loop
    network = topology.create_network()
    graph = network.to_strict_multidigraph()

    # Use first node as source for SPF
    source = next(iter(graph.nodes))

    # Create a closure that captures the graph and source
    def run_spf():
        return spf(graph, source)

    # Time the SPF execution
    timing_stats = _time_func(run_spf, iterations)

    return BenchmarkSample(
        case=case,
        problem_size=case.problem_size,
        mean_time=timing_stats["mean"],
        median_time=timing_stats["median"],
        std_dev=timing_stats["std"],
        min_time=timing_stats["min"],
        max_time=timing_stats["max"],
        rounds=int(timing_stats["rounds"]),
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _execute_spf_networkx_benchmark(
    case: BenchmarkCase, iterations: int
) -> BenchmarkSample:
    """Execute SPF benchmark for a given case.

    Creates network/graph once and reuses it across iterations to reduce variance.
    Uses the first node as the source for shortest path calculation.

    Args:
        case: Benchmark case containing topology and configuration.
        iterations: Number of timing iterations to perform.

    Returns:
        BenchmarkSample with timing statistics and metadata.
    """
    topology: Topology = case.inputs["topology"]

    # Create network and graph once outside timing loop
    network = topology.create_network()
    graph = network.to_strict_multidigraph()

    # Use first node as source for SPF
    source = next(iter(graph.nodes))

    # Create a closure that captures the graph and source
    def run_spf():
        return nx.dijkstra_predecessor_and_distance(graph, source)

    # Time the SPF execution
    timing_stats = _time_func(run_spf, iterations)

    return BenchmarkSample(
        case=case,
        problem_size=case.problem_size,
        mean_time=timing_stats["mean"],
        median_time=timing_stats["median"],
        std_dev=timing_stats["std"],
        min_time=timing_stats["min"],
        max_time=timing_stats["max"],
        rounds=int(timing_stats["rounds"]),
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


def _execute_max_flow_benchmark(
    case: BenchmarkCase, iterations: int
) -> BenchmarkSample:
    """Execute max flow benchmark for a given case."""
    topology: Topology = case.inputs["topology"]
    network = topology.create_network()
    graph = network.to_strict_multidigraph()

    # Use first node as source and last node as sink
    nodes = list(graph.nodes)
    source = nodes[0]
    sink = nodes[-1]

    # Create a closure that captures the graph and source
    def run_max_flow():
        return calc_max_flow(graph, source, sink)

    # Time the max flow execution
    timing_stats = _time_func(run_max_flow, iterations)

    return BenchmarkSample(
        case=case,
        problem_size=case.problem_size,
        mean_time=timing_stats["mean"],
        median_time=timing_stats["median"],
        std_dev=timing_stats["std"],
        min_time=timing_stats["min"],
        max_time=timing_stats["max"],
        rounds=int(timing_stats["rounds"]),
        timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
    )


class BenchmarkRunner:
    """Runs benchmark profiles and collects results."""

    def run_profile(self, profile: BenchmarkProfile) -> BenchmarkResult:
        """Run all cases in a benchmark profile.

        Args:
            profile: Benchmark profile containing cases and configuration.

        Returns:
            BenchmarkResult with all sample measurements and metadata.

        Raises:
            ValueError: If profile contains unsupported benchmark task.
        """
        samples = []
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")

        for i, case in enumerate(profile.cases, 1):
            print(f"    Case {i}/{len(profile.cases)}: {case.name}", end="", flush=True)

            if case.task == BenchmarkTask.SHORTEST_PATH:
                sample = _execute_spf_benchmark(case, profile.iterations)
            elif case.task == BenchmarkTask.SHORTEST_PATH_NETWORKX:
                sample = _execute_spf_networkx_benchmark(case, profile.iterations)
            elif case.task == BenchmarkTask.MAX_FLOW:
                sample = _execute_max_flow_benchmark(case, profile.iterations)
            else:
                raise ValueError(f"Unsupported benchmark task: {case.task}")

            samples.append(sample)
            SECONDS_TO_MS = 1000
            print(
                f" [{sample.time_ms:7.2f}ms ± {sample.std_dev * SECONDS_TO_MS:5.2f}ms]"
            )

        finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        return BenchmarkResult(
            profile=profile,
            samples=samples,
            run_id=str(time.time_ns()),
            started_at=started_at,
            finished_at=finished_at,
        )
