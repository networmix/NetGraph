#!/usr/bin/env python3
"""Executor that turns a `BenchmarkProfile` into a `BenchmarkResult`."""

from __future__ import annotations

import gc
import statistics
import time
from typing import Any, Callable

import netgraph_core
import networkx as nx

from ngraph.analysis import AnalysisContext

from .core import (
    BenchmarkCase,
    BenchmarkProfile,
    BenchmarkResult,
    BenchmarkSample,
    BenchmarkTask,
)
from .topology import Topology


def _time_func(func: Callable[[], Any], runs: int) -> dict[str, float]:
    """Time ``func`` over ``runs`` calls after up to 10 untimed warm-up calls.

    Automatic GC is off while timing, to reduce variance.

    Args:
        func: Zero-argument callable to time.
        runs: Number of timing runs to perform.

    Returns:
        Dictionary with timing statistics: mean, median, std, min, max, rounds.
    """
    gc_was_enabled = gc.isenabled()
    gc.disable()

    try:
        gc.collect()

        WARMUP_RUNS = 10
        for _ in range(min(WARMUP_RUNS, runs)):
            func()

        samples = []
        NANOSECONDS_TO_SECONDS = 1e9
        for _ in range(runs):
            # Collect gen 0 between runs so garbage does not pile up with GC off.
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
        if gc_was_enabled:
            gc.enable()


def _execute_spf_benchmark(case: BenchmarkCase, iterations: int) -> BenchmarkSample:
    """Time NetGraph-Core SPF from node 0 over all min-cost edges.

    The network and Core graph are built once, outside the timed loop.

    Args:
        case: Benchmark case containing topology and configuration.
        iterations: Number of timing iterations to perform.

    Returns:
        BenchmarkSample with timing statistics and metadata.
    """
    topology: Topology = case.inputs["topology"]
    network = topology.create_network()
    ctx = AnalysisContext.from_network(network)
    algs = ctx.algorithms
    source_id = 0

    # All parallel min-cost edges; capacity is ignored.
    edge_selection = netgraph_core.EdgeSelection(
        multi_edge=True,
        require_capacity=False,
        tie_break=netgraph_core.EdgeTieBreak.DETERMINISTIC,
    )

    def run_spf():
        return algs.spf(ctx.handle, source_id, selection=edge_selection)

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
    """Time NetworkX ``dijkstra_predecessor_and_distance`` as a baseline for Core SPF.

    The network and NetworkX MultiDiGraph are built once, outside the timed
    loop. The source is the first node.

    Args:
        case: Benchmark case containing topology and configuration.
        iterations: Number of timing iterations to perform.

    Returns:
        BenchmarkSample with timing statistics and metadata.
    """
    topology: Topology = case.inputs["topology"]
    network = topology.create_network()

    nx_graph = nx.MultiDiGraph()
    for node_name, node in network.nodes.items():
        if not node.disabled:
            nx_graph.add_node(node_name)

    # Links are bidirectional; add one edge per direction.
    for _, link in network.links.items():
        if not link.disabled:
            nx_graph.add_edge(
                link.source, link.target, capacity=link.capacity, cost=link.cost
            )
            nx_graph.add_edge(
                link.target, link.source, capacity=link.capacity, cost=link.cost
            )

    source = next(iter(nx_graph.nodes))

    def run_spf():
        return nx.dijkstra_predecessor_and_distance(nx_graph, source, weight="cost")

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
    """Time NetGraph-Core max flow from the first node ID to the last.

    Uses proportional placement over all paths (``shortest_path=False``). The
    network and Core graph are built once, outside the timed loop.

    Args:
        case: Benchmark case containing topology and configuration.
        iterations: Number of timing iterations to perform.

    Returns:
        BenchmarkSample with timing statistics and metadata.
    """
    topology: Topology = case.inputs["topology"]
    network = topology.create_network()
    ctx = AnalysisContext.from_network(network)
    algs = ctx.algorithms
    source_id = 0
    sink_id = ctx.multidigraph.num_nodes() - 1

    def run_max_flow():
        flow_value, _ = algs.max_flow(
            ctx.handle,
            source_id,
            sink_id,
            flow_placement=netgraph_core.FlowPlacement.PROPORTIONAL,
            shortest_path=False,
        )
        return flow_value

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
