"""Tests for performance profiling instrumentation."""

import time
from unittest.mock import MagicMock, patch

import pytest

from ngraph.profiling import (
    PerformanceProfiler,
    PerformanceReporter,
    ProfileResults,
    StepProfile,
)


class TestStepProfile:
    """Test the StepProfile dataclass."""

    def test_step_profile_creation(self):
        """Test creating a StepProfile instance."""
        profile = StepProfile(
            step_name="test_step",
            step_type="TestStep",
            wall_time=1.5,
            cpu_time=1.2,
            function_calls=1000,
        )

        assert profile.step_name == "test_step"
        assert profile.step_type == "TestStep"
        assert profile.wall_time == 1.5
        assert profile.cpu_time == 1.2
        assert profile.function_calls == 1000
        assert profile.memory_peak is None
        assert profile.cprofile_stats is None


class TestProfileResults:
    """Test the ProfileResults dataclass."""

    def test_profile_results_creation(self):
        """Test creating a ProfileResults instance."""
        results = ProfileResults()

        assert results.step_profiles == []
        assert results.total_wall_time == 0.0
        assert results.total_cpu_time == 0.0
        assert results.total_function_calls == 0
        assert results.bottlenecks == []
        assert results.analysis_summary == {}


class TestPerformanceProfiler:
    """Test the PerformanceProfiler class."""

    def test_profiler_initialization(self):
        """Test profiler initialization."""
        profiler = PerformanceProfiler()
        assert profiler.results is not None
        assert profiler._scenario_start_time is None
        assert profiler._scenario_end_time is None

    def test_scenario_timing(self):
        """Test scenario-level timing."""
        profiler = PerformanceProfiler()

        profiler.start_scenario()
        assert profiler._scenario_start_time is not None

        time.sleep(0.01)  # Small delay for testing

        profiler.end_scenario()
        assert profiler._scenario_end_time is not None
        assert profiler.results.total_wall_time > 0

    def test_scenario_end_without_start(self):
        """Test ending scenario profiling without starting."""
        profiler = PerformanceProfiler()

        # Should handle gracefully
        profiler.end_scenario()
        assert profiler.results.total_wall_time == 0.0

    def test_step_profiling_basic(self):
        """Test basic step profiling."""
        profiler = PerformanceProfiler()

        with profiler.profile_step("test_step", "TestStep"):
            time.sleep(0.01)  # Small delay for testing

        assert len(profiler.results.step_profiles) == 1
        profile = profiler.results.step_profiles[0]
        assert profile.step_name == "test_step"
        assert profile.step_type == "TestStep"
        assert profile.wall_time > 0
        assert profile.cpu_time >= 0.0  # Always has CPU profiling now
        assert profile.function_calls >= 0

    @patch("cProfile.Profile")
    def test_step_profiling_detail(self, mock_profile_class):
        """Test step profiling with detail mode."""
        # Setup mock cProfile
        mock_profiler = MagicMock()
        mock_profile_class.return_value = mock_profiler

        # Mock stats data
        mock_stats = MagicMock()
        # pstats.Stats.stats values are tuples: (cc, nc, tt, ct, callers)
        # cc=call count, nc=number of calls, tt=total time, ct=cumulative time
        mock_stats.stats = {
            ("file.py", 1, "func1"): (
                10,
                10,
                0.1,
                0.1,
                {},
            ),  # (cc, nc, tt, ct, callers)
            ("file.py", 2, "func2"): (5, 5, 0.05, 0.05, {}),
        }

        with patch("pstats.Stats", return_value=mock_stats):
            profiler = PerformanceProfiler()

            with profiler.profile_step("test_step", "TestStep"):
                time.sleep(0.01)

        assert len(profiler.results.step_profiles) == 1
        profile = profiler.results.step_profiles[0]
        assert profile.step_name == "test_step"
        assert profile.step_type == "TestStep"
        assert profile.wall_time > 0
        assert (
            pytest.approx(profile.cpu_time, rel=1e-3) == 0.15
        )  # Sum of totaltime values
        assert profile.function_calls == 15  # Sum of callcount values
        assert profile.cprofile_stats is not None

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

        # Check analysis summary
        summary = profiler.results.analysis_summary
        assert summary["total_steps"] == 2
        assert summary["slowest_step"] == "slow_step"
        assert summary["bottleneck_count"] == 1

    @patch("pstats.Stats")
    def test_get_top_functions(self, mock_stats_class):
        """Test getting top functions for a step."""
        # Setup mock stats
        mock_stats = MagicMock()
        # pstats.Stats.stats values are tuples: (cc, nc, tt, ct, callers)
        mock_stats.stats = {
            ("file.py", 1, "func1"): (
                20,
                20,
                0.2,
                0.2,
                {},
            ),  # (cc, nc, tt, ct, callers)
            ("file.py", 2, "func2"): (10, 10, 0.1, 0.1, {}),
            ("file.py", 3, "func3"): (5, 5, 0.05, 0.05, {}),
        }

        profiler = PerformanceProfiler()
        step_profile = StepProfile(
            "test_step", "TestStep", 1.0, 0.35, 35, cprofile_stats=mock_stats
        )
        profiler.results.step_profiles.append(step_profile)

        top_functions = profiler.get_top_functions("test_step", limit=2)

        assert len(top_functions) == 2
        assert top_functions[0][0] == "file.py:1(func1)"
        assert top_functions[0][1] == 0.2  # total time (tt)
        assert top_functions[0][2] == 20  # call count (cc)

    def test_get_top_functions_no_step(self):
        """Test getting top functions for non-existent step."""
        profiler = PerformanceProfiler()

        top_functions = profiler.get_top_functions("nonexistent_step")
        assert top_functions == []

    @patch("pathlib.Path.open")
    def test_save_detailed_profile(self, mock_open):
        """Test saving detailed profile data."""
        from pathlib import Path

        mock_stats = MagicMock()
        mock_stats.dump_stats = MagicMock()

        profiler = PerformanceProfiler()
        step_profile = StepProfile(
            "test_step", "TestStep", 1.0, 0.8, 100, cprofile_stats=mock_stats
        )
        profiler.results.step_profiles.append(step_profile)

        output_path = Path("test_profile.prof")
        profiler.save_detailed_profile(output_path, "test_step")

        mock_stats.dump_stats.assert_called_once_with(str(output_path))


class TestPerformanceReporter:
    """Test the PerformanceReporter class."""

    def test_reporter_initialization(self):
        """Test reporter initialization."""
        results = ProfileResults()
        reporter = PerformanceReporter(results)
        assert reporter.results is results

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

        # Add step profiles
        step1 = StepProfile("step1", "Step1", 2.0, 1.8, 400)
        step2 = StepProfile("step2", "Step2", 3.0, 2.7, 600)
        results.step_profiles = [step1, step2]

        # Setup analysis summary
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

        # Add step profiles
        step1 = StepProfile("fast_step", "FastStep", 1.0, 0.9, 100)
        step2 = StepProfile("slow_step", "SlowStep", 8.0, 7.5, 800)
        results.step_profiles = [step1, step2]

        # Add bottleneck
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

        # Setup analysis summary
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

        # Add bottleneck
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
        assert "Top CPU-consuming functions in 'slow_step'" in report
        assert "file.py:1(func1)" in report

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
        """Test complete profiling workflow."""
        profiler = PerformanceProfiler()

        # Start scenario profiling
        profiler.start_scenario()

        # Profile some steps
        with profiler.profile_step("step1", "Step1"):
            time.sleep(0.01)

        with profiler.profile_step("step2", "Step2"):
            time.sleep(0.02)

        # End scenario profiling
        profiler.end_scenario()
        profiler.analyze_performance()

        # Verify results
        assert len(profiler.results.step_profiles) == 2
        assert profiler.results.total_wall_time > 0
        assert profiler.results.analysis_summary["total_steps"] == 2

        # Generate report
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
