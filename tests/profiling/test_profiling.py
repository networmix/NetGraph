"""Tests for performance profiling instrumentation."""

import time
import tracemalloc
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import ngraph.profiling.profiler as profiler_module
from ngraph.profiling.profiler import (
    PerformanceProfiler,
    PerformanceReporter,
    ProfileResults,
    StepProfile,
)


class TestPerformanceProfiler:
    """Test the PerformanceProfiler class."""

    def test_scenario_end_without_start(self):
        """end_scenario() without start_scenario() leaves total_wall_time at 0."""
        profiler = PerformanceProfiler()

        profiler.end_scenario()
        assert profiler.results.total_wall_time == 0.0

    def test_step_profiling_basic(self):
        """profile_step records step name, type, wall time and call counts."""
        profiler = PerformanceProfiler()

        with profiler.profile_step("test_step", "TestStep"):
            time.sleep(0.3)  # waiting, not computing

        assert len(profiler.results.step_profiles) == 1
        profile = profiler.results.step_profiles[0]
        assert profile.step_name == "test_step"
        assert profile.step_type == "TestStep"
        assert profile.wall_time >= 0.3
        # Process CPU time, not the wall time spent in the sleep.
        assert profile.cpu_time < 0.1
        assert profile.function_calls >= 1

    def test_step_profiling_with_memory(self):
        """Test step profiling with memory tracking enabled."""
        profiler = PerformanceProfiler(track_memory=True)

        with profiler.profile_step("mem_step", "MemStep"):
            block = bytearray(2_000_000)
            del block

        (profile,) = profiler.results.step_profiles
        assert profile.step_name == "mem_step"
        assert profile.memory_peak is not None and profile.memory_peak >= 2_000_000

    def test_memory_peak_is_none_without_tracking_or_when_already_tracing(self, caplog):
        """No tracking: None; another tracemalloc session: None and a warning."""
        profiler = PerformanceProfiler()
        with profiler.profile_step("plain", "Step"):
            _ = bytearray(1_000_000)
        assert profiler.results.step_profiles[0].memory_peak is None
        tracking = PerformanceProfiler(track_memory=True)
        tracemalloc.start()
        try:
            with caplog.at_level("WARNING", logger="ngraph"):
                with tracking.profile_step("traced", "Step"):
                    _ = bytearray(1_000_000)
            assert tracemalloc.is_tracing()
        finally:
            tracemalloc.stop()
        assert tracking.results.step_profiles[0].memory_peak is None
        assert any("already tracing" in r.getMessage() for r in caplog.records)

    @patch("cProfile.Profile")
    def test_function_calls_sum_primitive_calls(self, mock_profile_class):
        """function_calls sums cProfile's primitive calls (cc), not all calls (nc)."""
        mock_profile_class.return_value = MagicMock()
        mock_stats = MagicMock()
        # pstats.Stats.stats values are tuples: (cc, nc, tt, ct, callers)
        mock_stats.stats = {
            ("file.py", 1, "func1"): (10, 40, 0.1, 0.1, {}),
            ("file.py", 2, "func2"): (5, 20, 0.05, 0.05, {}),
        }
        with patch("pstats.Stats", return_value=mock_stats):
            profiler = PerformanceProfiler()
            with profiler.profile_step("test_step", "TestStep"):
                pass
        (profile,) = profiler.results.step_profiles
        assert profile.function_calls == 15
        assert profile.cprofile_stats is mock_stats

    @pytest.mark.parametrize("fails", [False, True])
    def test_cpu_time_is_the_process_cpu_clock(self, monkeypatch, fails):
        """Deterministic clocks: wall 1, process CPU 2, calling thread 0.1, cProfile 0.7."""

        def clock(*values):
            readings = iter(values)
            return lambda: next(readings)

        monkeypatch.setattr(
            profiler_module,
            "time",
            SimpleNamespace(
                perf_counter=clock(0.0, 10.0, 11.0, 1.0),
                process_time=clock(5.0, 7.0),
                thread_time=clock(3.0, 3.1),
            ),
        )
        mock_stats = MagicMock()
        mock_stats.stats = {("f.py", 1, "g"): (3, 3, 0.7, 0.7, {})}
        profiler = PerformanceProfiler()
        profiler.start_scenario()
        with patch("pstats.Stats", return_value=mock_stats):
            if fails:
                with pytest.raises(RuntimeError):
                    with profiler.profile_step("step", "Step"):
                        raise RuntimeError("step failed")
            else:
                with profiler.profile_step("step", "Step"):
                    pass
        profiler.end_scenario()
        profiler.analyze_performance()
        (profile,) = profiler.results.step_profiles
        assert (profile.wall_time, profile.cpu_time) == (1.0, 2.0)
        assert profiler.results.total_cpu_time == 2.0
        assert profiler.results.analysis_summary["cpu_efficiency"] == 2.0
        report = PerformanceReporter(profiler.results).generate_report()
        assert "Total CPU Time (process, all threads): 2.000 seconds" in report
        assert (
            "CPU Efficiency: 200.0% (process CPU across all threads / wall time; "
            "can exceed 100%)" in report
        )

    def test_total_cpu_is_the_sum_and_step_efficiency_is_not_capped(self, monkeypatch):
        """Two steps, wall 1 and 1, process CPU 2 and 3: total 5, the second at 300 %."""

        def clock(*values):
            readings = iter(values)
            return lambda: next(readings)

        monkeypatch.setattr(
            profiler_module,
            "time",
            SimpleNamespace(
                perf_counter=clock(0.0, 10.0, 11.0, 20.0, 21.0, 2.0),
                process_time=clock(0.0, 2.0, 5.0, 8.0),
                thread_time=clock(0.0, 0.1, 0.2, 0.3),
            ),
        )
        mock_stats = MagicMock()
        mock_stats.stats = {}
        profiler = PerformanceProfiler()
        profiler.start_scenario()
        with patch("pstats.Stats", return_value=mock_stats):
            for name in ("one", "two"):
                with profiler.profile_step(name, "Step"):
                    pass
        profiler.end_scenario()
        profiler.analyze_performance()
        assert [p.cpu_time for p in profiler.results.step_profiles] == [2.0, 3.0]
        assert profiler.results.total_cpu_time == 5.0
        report = PerformanceReporter(profiler.results).generate_report()
        assert (
            "   CPU Efficiency: 300.0% (CPU-intensive workload)" in report.splitlines()
        )

    def test_analyze_performance_no_profiles(self):
        """Test performance analysis with no step profiles."""
        profiler = PerformanceProfiler()
        profiler.analyze_performance()

        assert profiler.results.bottlenecks == []
        assert profiler.results.analysis_summary == {}

    def test_analyze_performance_with_bottlenecks(self):
        """Test performance analysis that identifies bottlenecks."""
        profiler = PerformanceProfiler()
        profiler.results.total_wall_time = 10.0

        # Add step profiles with one bottleneck (>10% of total time)
        fast_step = StepProfile("fast_step", "FastStep", 1.0, 0.8, 100)
        slow_step = StepProfile("slow_step", "SlowStep", 8.0, 7.5, 1000)  # 80% of total
        profiler.results.step_profiles = [fast_step, slow_step]

        profiler.analyze_performance()

        # Should identify the slow step as a bottleneck
        assert len(profiler.results.bottlenecks) == 1
        bottleneck = profiler.results.bottlenecks[0]
        assert bottleneck["step_name"] == "slow_step"
        assert bottleneck["percentage"] == 80.0

        summary = profiler.results.analysis_summary
        assert summary["total_steps"] == 2
        assert summary["slowest_step"] == "slow_step"
        assert summary["bottleneck_count"] == 1


class TestPerformanceReporter:
    """Test the PerformanceReporter class."""

    def test_generate_report_no_data(self):
        """Test generating report with no profiling data."""
        results = ProfileResults()
        reporter = PerformanceReporter(results)

        report = reporter.generate_report()
        assert "No profiling data available to report." in report

    def test_generate_report_basic(self):
        """Test generating basic performance report."""
        results = ProfileResults()
        results.total_wall_time = 5.0
        results.total_cpu_time = 4.5
        results.total_function_calls = 1000

        step1 = StepProfile("step1", "Step1", 2.0, 1.8, 400)
        step2 = StepProfile("step2", "Step2", 3.0, 2.7, 600)
        results.step_profiles = [step1, step2]

        results.analysis_summary = {
            "total_steps": 2,
            "slowest_step": "step2",
            "slowest_step_time": 3.0,
            "bottleneck_count": 0,
            "avg_step_time": 2.5,
            "cpu_efficiency": 0.9,
            "total_function_calls": 1000,
            "calls_per_second": 200.0,
        }

        reporter = PerformanceReporter(results)
        report = reporter.generate_report()

        assert "NETGRAPH PERFORMANCE PROFILING REPORT" in report
        assert "1. SUMMARY" in report
        assert "WORKFLOW STEP TIMING ANALYSIS" in report
        assert "Total Execution Time: 5.000 seconds" in report
        assert "CPU Efficiency: 90.0%" in report
        assert "step1" in report
        assert "step2" in report

    def test_generate_report_with_bottlenecks(self):
        """Test generating report with identified bottlenecks."""
        results = ProfileResults()
        results.total_wall_time = 10.0

        step1 = StepProfile("fast_step", "FastStep", 1.0, 0.9, 100)
        step2 = StepProfile("slow_step", "SlowStep", 8.0, 7.5, 800)
        results.step_profiles = [step1, step2]

        bottleneck = {
            "step_name": "slow_step",
            "step_type": "SlowStep",
            "wall_time": 8.0,
            "cpu_time": 7.5,
            "percentage": 80.0,
            "function_calls": 800,
            "efficiency_ratio": 0.9375,
        }
        results.bottlenecks = [bottleneck]

        results.analysis_summary = {
            "bottleneck_count": 1,
            "cpu_efficiency": 0.84,
            "calls_per_second": 90.0,
        }

        reporter = PerformanceReporter(results)
        report = reporter.generate_report()

        assert "PERFORMANCE BOTTLENECK ANALYSIS" in report
        assert "Bottleneck #1: slow_step" in report
        assert "80.0% of total" in report

    @patch("pstats.Stats")
    def test_generate_report_detailed(self, mock_stats_class):
        """Test generating detailed report with function analysis."""
        results = ProfileResults()
        results.total_wall_time = 5.0

        # Setup mock stats for detailed analysis
        mock_stats = MagicMock()
        # pstats.Stats.stats values are tuples: (cc, nc, tt, ct, callers)
        mock_stats.stats = {
            ("file.py", 1, "func1"): (
                100,
                100,
                1.0,
                1.0,
                {},
            ),  # (cc, nc, tt, ct, callers)
            ("file.py", 2, "func2"): (50, 50, 0.5, 0.5, {}),
        }

        # Add step profile with bottleneck
        step_profile = StepProfile(
            "slow_step", "SlowStep", 3.0, 2.5, 500, cprofile_stats=mock_stats
        )
        results.step_profiles = [step_profile]

        bottleneck = {
            "step_name": "slow_step",
            "step_type": "SlowStep",
            "wall_time": 3.0,
            "cpu_time": 2.5,
            "percentage": 60.0,
            "function_calls": 500,
            "efficiency_ratio": 0.833,
        }
        results.bottlenecks = [bottleneck]

        reporter = PerformanceReporter(results)
        report = reporter.generate_report()

        assert "DETAILED FUNCTION ANALYSIS" in report
        assert (
            "Top functions by cProfile internal time (profiled thread) in 'slow_step':"
            in report
        )
        assert "file.py:1(func1)" in report
        assert "Top CPU-consuming" not in report

    def test_insights_and_recommendations(self):
        """Test performance insights generation."""
        results = ProfileResults()

        # Add step profiles to prevent early return
        step_profile = StepProfile("io_step", "IOStep", 2.0, 0.4, 1000)
        results.step_profiles = [step_profile]

        results.analysis_summary = {
            "cpu_efficiency": 0.3,  # Low efficiency
            "calls_per_second": 500,  # Low call rate
        }
        results.bottlenecks = [
            {
                "step_name": "io_step",
                "step_type": "IOStep",
                "wall_time": 2.0,
                "cpu_time": 0.4,
                "percentage": 100.0,
                "function_calls": 1000,
                "efficiency_ratio": 0.2,  # I/O bound
            }
        ]

        reporter = PerformanceReporter(results)
        report = reporter.generate_report()

        assert "PERFORMANCE BOTTLENECK ANALYSIS" in report
        assert "I/O-bound workload" in report
        assert "Investigate I/O operations" in report


class TestProfilerIntegration:
    """Integration tests for the profiling system."""

    def test_end_to_end_profiling(self):
        """Test start, two profiled steps, end, analysis, and report."""
        profiler = PerformanceProfiler()

        profiler.start_scenario()

        with profiler.profile_step("step1", "Step1"):
            time.sleep(0.01)

        with profiler.profile_step("step2", "Step2"):
            time.sleep(0.02)

        profiler.end_scenario()
        profiler.analyze_performance()

        assert len(profiler.results.step_profiles) == 2
        assert profiler.results.total_wall_time > 0
        assert profiler.results.analysis_summary["total_steps"] == 2

        reporter = PerformanceReporter(profiler.results)
        report = reporter.generate_report()
        assert "step1" in report
        assert "step2" in report

    def test_profiler_exception_handling(self):
        """Test profiler behavior when step execution raises exception."""
        profiler = PerformanceProfiler()

        with pytest.raises(ValueError):
            with profiler.profile_step("error_step", "ErrorStep"):
                raise ValueError("Test error")

        # Should still have profile data despite exception
        assert len(profiler.results.step_profiles) == 1
        profile = profiler.results.step_profiles[0]
        assert profile.step_name == "error_step"
        assert profile.wall_time > 0


def test_step_report_has_only_live_step_profile_fields():
    profile = StepProfile("one", "BuildGraph", 1.0, 0.5, 7)
    assert set(vars(profile)) == {
        "step_name",
        "step_type",
        "wall_time",
        "cpu_time",
        "function_calls",
        "memory_peak",
        "cprofile_stats",
    }
    results = ProfileResults(step_profiles=[profile], total_wall_time=1.0)
    report = PerformanceReporter(results).generate_report()
    assert "one" in report and "BuildGraph" in report
    assert "Workers" not in report


def test_a_step_at_exactly_ten_percent_is_no_bottleneck():
    """Bottleneck iff the wall share is above 10 %."""
    profiler = PerformanceProfiler()
    profiler.results.total_wall_time = 10.0
    profiler.results.step_profiles = [
        StepProfile("tenth", "Step", 1.0, 1.0, 1),
        StepProfile("rest", "Step", 9.0, 9.0, 1),
    ]
    profiler.analyze_performance()
    assert [b["step_name"] for b in profiler.results.bottlenecks] == ["rest"]


def test_top_functions_are_ranked_by_internal_time():
    """The function table lists cProfile internal time, highest first."""
    stats = MagicMock()
    stats.stats = {
        ("f.py", 1, "many_calls"): (100, 100, 0.1, 0.1, {}),
        ("f.py", 2, "slow"): (1, 1, 1.0, 1.0, {}),
    }
    results = ProfileResults(
        step_profiles=[StepProfile("s", "Step", 2.0, 2.0, 101, cprofile_stats=stats)],
        total_wall_time=2.0,
        bottlenecks=[
            {
                "step_name": "s",
                "step_type": "Step",
                "wall_time": 2.0,
                "cpu_time": 2.0,
                "percentage": 100.0,
                "function_calls": 101,
                "efficiency_ratio": 1.0,
            }
        ],
    )
    report = PerformanceReporter(results).generate_report()
    assert report.index("f.py:2(slow)") < report.index("f.py:1(many_calls)")


@pytest.mark.parametrize(
    ("efficiency", "workload", "advice"),
    [
        (2.0, "CPU-intensive workload", "Consider algorithmic optimization"),
        (1.05, "CPU-intensive workload", "Consider algorithmic optimization"),
        (0.9, "CPU-intensive workload", "Consider algorithmic optimization"),
        (0.5, "Mixed workload", "Profile individual functions"),
        (0.2, "I/O-bound workload", "Investigate I/O operations"),
    ],
)
def test_bottleneck_classes_keep_their_thresholds(efficiency, workload, advice):
    """No class above 100 %; the CPU-intensive advice does not suggest parallelization."""
    results = ProfileResults(
        step_profiles=[StepProfile("s", "Step", 1.0, efficiency, 1)],
        total_wall_time=1.0,
        bottlenecks=[
            {
                "step_name": "s",
                "step_type": "Step",
                "wall_time": 1.0,
                "cpu_time": efficiency,
                "percentage": 100.0,
                "function_calls": 1,
                "efficiency_ratio": efficiency,
            }
        ],
    )
    report = PerformanceReporter(results).generate_report()
    assert f"({workload})" in report
    assert f"Recommendation: {advice}" in report
    assert "parallelization" not in report
