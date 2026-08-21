"""Regression tests for worker-profile merging.

merge_child_profiles() previously globbed ``*_worker_*.pstats`` while workers
in analysis/failure_manager.py write ``{analysis_name}_thread_{tid}_{uuid}.pstats``,
so worker profiles were never merged into step profiles.
"""

import cProfile
import pstats
import threading
import uuid
from pathlib import Path
from typing import Any

import pytest

from ngraph.analysis.failure_manager import _generic_worker
from ngraph.profiling.profiler import PerformanceProfiler


def _dump_worker_style_profile(profile_dir: Path, analysis_name: str) -> Path:
    """Dump a real cProfile run using the exact worker filename convention.

    Mirrors the writer side in ngraph/analysis/failure_manager.py
    (_generic_worker), which this test suite must keep in sync with.
    """
    profiler = cProfile.Profile()
    try:
        profiler.enable()
    except ValueError:
        pytest.skip("another profiler is active; cannot exercise cProfile")
    sum(range(1000))
    profiler.disable()

    unique_id = uuid.uuid4().hex[:8]
    thread_id = threading.current_thread().ident
    profile_path = (
        profile_dir / f"{analysis_name}_thread_{thread_id}_{unique_id}.pstats"
    )
    pstats.Stats(profiler).dump_stats(profile_path)
    return profile_path


def test_merge_child_profiles_matches_worker_file_naming(tmp_path: Path) -> None:
    """Files named per the worker convention are merged and then removed."""
    perf = PerformanceProfiler()
    with perf.profile_step("step1", "MaxFlowStep"):
        sum(range(100))

    worker_file = _dump_worker_style_profile(tmp_path, "max_flow_analysis")
    baseline_calls = perf.results.step_profiles[0].function_calls

    perf.merge_child_profiles(tmp_path, "step1")

    step_profile = perf.results.step_profiles[0]
    assert step_profile.worker_profiles_merged == 1
    assert step_profile.function_calls > baseline_calls
    # Merged worker files are cleaned up
    assert not worker_file.exists()


def test_generic_worker_profiles_round_trip(tmp_path: Path, monkeypatch) -> None:
    """Profiles written by the real worker are merged into the step profile."""
    monkeypatch.setenv("NGRAPH_PROFILE_DIR", str(tmp_path))

    def dummy_analysis(
        network: Any, excluded_nodes: set[str], excluded_links: set[str]
    ) -> int:
        return sum(range(500))

    args = (None, set(), set(), dummy_analysis, {}, 0, False, "dummy_analysis")
    result = _generic_worker(args)
    assert result == sum(range(500))

    written = list(tmp_path.glob("*.pstats"))
    if not written:
        pytest.skip("worker profiling disabled (another profiler is active)")

    perf = PerformanceProfiler()
    with perf.profile_step("dummy_step", "DummyStep"):
        pass

    perf.merge_child_profiles(tmp_path, "dummy_step")

    step_profile = perf.results.step_profiles[0]
    assert step_profile.worker_profiles_merged == len(written)
    assert list(tmp_path.glob("*.pstats")) == []
