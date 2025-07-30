#!/usr/bin/env python3
"""Benchmark profile catalogue."""

from __future__ import annotations

from .core import (
    N_LOG_N,
    BenchmarkCase,
    BenchmarkProfile,
    BenchmarkTask,
    ComplexityAnalysisSpec,
)
from .topology import Clos2TierTopology, Grid2DTopology

BENCHMARK_PROFILES: list[BenchmarkProfile] = [
    BenchmarkProfile(
        name="spf_complexity_clos2tier",
        cases=[
            BenchmarkCase(
                name="spf_clos2tier_10_10",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Clos2TierTopology(leaf_count=10, spine_count=10)},
                problem_size="100 * log(20)",  # This is Dijkstra, so E log V
            ),
            BenchmarkCase(
                name="spf_clos2tier_100_100",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Clos2TierTopology(leaf_count=100, spine_count=100)},
                problem_size="10000 * log(200)",
            ),
            BenchmarkCase(
                name="spf_clos2tier_200_200",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Clos2TierTopology(leaf_count=200, spine_count=200)},
                problem_size="40000 * log(400)",
            ),
            BenchmarkCase(
                name="spf_clos2tier_400_400",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Clos2TierTopology(leaf_count=400, spine_count=400)},
                problem_size="160000 * log(800)",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
    BenchmarkProfile(
        name="spf_complexity_grid2d",
        cases=[
            BenchmarkCase(
                name="spf_grid2d_10_10",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Grid2DTopology(rows=10, cols=10)},
                problem_size="180 * log(100)",  # This is Dijkstra, so E log V
            ),
            BenchmarkCase(
                name="spf_grid2d_100_100",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Grid2DTopology(rows=100, cols=100)},
                problem_size="19800 * log(10000)",
            ),
            BenchmarkCase(
                name="spf_grid2d_200_200",
                task=BenchmarkTask.SHORTEST_PATH,
                inputs={"topology": Grid2DTopology(rows=200, cols=200)},
                problem_size="79600 * log(40000)",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
    BenchmarkProfile(
        name="spf_complexity_clos2tier_networkx",
        cases=[
            BenchmarkCase(
                name="spf_clos2tier_10_10",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Clos2TierTopology(leaf_count=10, spine_count=10)},
                problem_size="100 * log(20)",  # This is Dijkstra, so E log V
            ),
            BenchmarkCase(
                name="spf_clos2tier_100_100",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Clos2TierTopology(leaf_count=100, spine_count=100)},
                problem_size="10000 * log(200)",
            ),
            BenchmarkCase(
                name="spf_clos2tier_200_200",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Clos2TierTopology(leaf_count=200, spine_count=200)},
                problem_size="40000 * log(400)",
            ),
            BenchmarkCase(
                name="spf_clos2tier_400_400",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Clos2TierTopology(leaf_count=400, spine_count=400)},
                problem_size="160000 * log(800)",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
    BenchmarkProfile(
        name="spf_complexity_grid2d_networkx",
        cases=[
            BenchmarkCase(
                name="spf_grid2d_10_10_networkx",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Grid2DTopology(rows=10, cols=10)},
                problem_size="180 * log(100)",  # This is Dijkstra, so E log V
            ),
            BenchmarkCase(
                name="spf_grid2d_100_100_networkx",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Grid2DTopology(rows=100, cols=100)},
                problem_size="19800 * log(10000)",
            ),
            BenchmarkCase(
                name="spf_grid2d_200_200_networkx",
                task=BenchmarkTask.SHORTEST_PATH_NETWORKX,
                inputs={"topology": Grid2DTopology(rows=200, cols=200)},
                problem_size="79600 * log(40000)",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
    BenchmarkProfile(
        name="max_flow_complexity_clos2tier",
        cases=[
            BenchmarkCase(
                name="max_flow_clos2tier_10_10",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Clos2TierTopology(leaf_count=10, spine_count=10)},
                problem_size="100",
            ),
            BenchmarkCase(
                name="max_flow_clos2tier_100_100",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Clos2TierTopology(leaf_count=100, spine_count=100)},
                problem_size="10000",
            ),
            BenchmarkCase(
                name="max_flow_clos2tier_200_200",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Clos2TierTopology(leaf_count=200, spine_count=200)},
                problem_size="40000",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
    BenchmarkProfile(
        name="max_flow_complexity_grid2d",
        cases=[
            BenchmarkCase(
                name="max_flow_grid2d_10_10",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Grid2DTopology(rows=10, cols=10)},
                problem_size="100",
            ),
            BenchmarkCase(
                name="max_flow_grid2d_100_100",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Grid2DTopology(rows=100, cols=100)},
                problem_size="10000",
            ),
            BenchmarkCase(
                name="max_flow_grid2d_200_200",
                task=BenchmarkTask.MAX_FLOW,
                inputs={"topology": Grid2DTopology(rows=200, cols=200)},
                problem_size="40000",
            ),
        ],
        analysis=ComplexityAnalysisSpec(
            expected=N_LOG_N,
            fit_tol_pct=30.0,
            regression_tol_pct=50.0,
            plots=True,
        ),
        iterations=100,
    ),
]


def get_profile_by_name(name: str) -> BenchmarkProfile:
    """Get benchmark profile by name."""
    for profile in BENCHMARK_PROFILES:
        if profile.name == name:
            return profile
    raise KeyError(
        f"Unknown profile '{name}'. Available: {[p.name for p in BENCHMARK_PROFILES]}"
    )


def get_profile_names() -> list[str]:
    """Get list of available profile names."""
    return [profile.name for profile in BENCHMARK_PROFILES]


__all__ = [
    "BENCHMARK_PROFILES",
    "get_profile_by_name",
    "get_profile_names",
]
