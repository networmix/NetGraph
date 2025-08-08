#!/usr/bin/env python3
"""Analysis engine for NetGraph performance benchmarks."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .core import BenchmarkResult, BenchmarkSample, BenchmarkTask


def _fit_power_law(samples: list[BenchmarkSample]) -> tuple[float, float]:
    """Fit power law to benchmark samples using least squares regression.

    Performs linear regression in log space to fit y = a * x^b model.
    Calculates R^2 goodness of fit metric.

    Args:
        samples: List of benchmark samples with problem sizes and timings.

    Returns:
        Tuple of (exponent, r_squared) where exponent is the power law
        exponent and r_squared is the goodness of fit (0-1).

    Raises:
        ValueError: If fewer than 2 samples provided.
    """
    if len(samples) < 2:
        raise ValueError("Need at least 2 samples for power law fitting")

    # Convert to log space for linear regression
    log_sizes = [math.log(s.numeric_problem_size()) for s in samples]
    log_times = [math.log(s.mean_time) for s in samples]

    # Least squares regression in log space
    n = len(samples)
    sum_x = sum(log_sizes)
    sum_y = sum(log_times)
    sum_xy = sum(x * y for x, y in zip(log_sizes, log_times, strict=False))
    sum_x2 = sum(x * x for x in log_sizes)

    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

    # Calculate R^2
    y_mean = sum_y / n
    ss_tot = sum((y - y_mean) ** 2 for y in log_times)
    ss_res = sum(
        (log_times[i] - (slope * log_sizes[i] + (sum_y - slope * sum_x) / n)) ** 2
        for i in range(n)
    )
    r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0

    return slope, r_squared


class PerformanceAnalyzer:
    """Processes benchmark results and detects performance regressions."""

    def __init__(self, results_dir: Path | None = None):
        self.results_dir = results_dir or Path("dev/perf_results")
        self.runs: list[BenchmarkResult] = []

    def add_run(self, result: BenchmarkResult) -> None:
        """Add a benchmark result to the analyzer.

        Args:
            result: Benchmark result to add for analysis.
        """
        self.runs.append(result)

    def add_runs(self, results: list[BenchmarkResult]) -> None:
        """Add multiple benchmark results to the analyzer.

        Args:
            results: List of benchmark results to add for analysis.
        """
        self.runs.extend(results)

    def print_analysis_report(self) -> None:
        """Print analysis report to stdout."""
        if not self.runs:
            print("No benchmark results to analyze")
            return

        for run in self.runs:
            self._print_run_summary(run)

            if run.profile.analysis.generates_plots():
                self._print_complexity_analysis(run)

    def _print_run_summary(self, run: BenchmarkResult) -> None:
        """Print summary of a single benchmark run."""
        samples = sorted(run.samples, key=lambda s: s.numeric_problem_size())

        print(f"\nProfile: {run.profile.name}")
        print(f"Task: {run.profile.tasks[0].name}")
        print("Configuration:")
        print(f"  Cases: {len(samples)}")
        print(f"  Iterations per case: {run.profile.iterations}")
        print(f"  Expected complexity: {run.profile.analysis.expected.display_name}")

        # Calculate statistics across all samples
        SECONDS_TO_MS = 1000
        all_times = [s.mean_time * SECONDS_TO_MS for s in samples]
        size_ratio = (
            samples[-1].numeric_problem_size() / samples[0].numeric_problem_size()
        )
        time_ratio = all_times[-1] / all_times[0]

        print("\nPerformance Statistics:")
        print(f"  Timing range: {min(all_times):.3f} - {max(all_times):.3f} ms")
        print(f"  Problem size growth: {size_ratio:.1f}x")
        print(f"  Time growth: {time_ratio:.1f}x")

        print("\nDetailed Results:")
        print(
            f"  {'Expression':>20} {'Size':>8} {'Mean':>10} {'StdDev':>10} {'CV%':>8} {'Status':>12}"
        )
        print(f"  {'-' * 20} {'-' * 8} {'-' * 10} {'-' * 10} {'-' * 8} {'-' * 12}")

        HIGH_VARIANCE_THRESHOLD = 20.0  # Coefficient of variation percentage
        for sample in samples:
            cv_pct = (
                (sample.std_dev / sample.mean_time * 100) if sample.mean_time > 0 else 0
            )
            status = "⚠ HIGH VAR" if cv_pct > HIGH_VARIANCE_THRESHOLD else "OK"
            numeric_size = int(sample.numeric_problem_size())

            print(
                f"  {sample.problem_size:>20} {numeric_size:>8} "
                f"{sample.time_ms:>8.3f}ms ±{sample.std_dev * SECONDS_TO_MS:>7.3f}ms "
                f"{cv_pct:>7.1f}% {status:>12}"
            )

        # Add interpretation note for high CV values
        high_cv_samples = [
            s
            for s in samples
            if (s.std_dev / s.mean_time * 100) > HIGH_VARIANCE_THRESHOLD
        ]
        if high_cv_samples:
            print(f"\n  ⚠ High variance detected (CV% > {HIGH_VARIANCE_THRESHOLD}%)")
            print(
                "    - May indicate: system load, thermal throttling, or insufficient samples"
            )
            print("    - Consider: increasing iterations or running in isolation")

    def _print_complexity_analysis(self, run: BenchmarkResult) -> None:
        """Print complexity analysis for a benchmark run."""
        samples = sorted(run.samples, key=lambda s: s.numeric_problem_size())

        if len(samples) < 2:
            print("\n✗ Insufficient samples for complexity analysis")
            return

        # Fit power law
        try:
            empirical_exponent, r_squared = _fit_power_law(samples)

            print("\nComplexity Analysis:")

            # Model comparison
            expected_exp = run.profile.analysis.expected.expected_exponent
            deviation_pct = abs(empirical_exponent - expected_exp) / expected_exp * 100
            interpreted = run.profile.analysis.expected.interpret_exponent(
                empirical_exponent
            )

            print("  Model Comparison:")
            print(
                f"    Expected:   {run.profile.analysis.expected.display_name} (exponent ≈ {expected_exp:.1f})"
            )
            print(
                f"    Measured:   {interpreted} (exponent = {empirical_exponent:.3f})"
            )
            # R^2 quality assessment thresholds
            EXCELLENT_R2_THRESHOLD = 0.99
            GOOD_R2_THRESHOLD = 0.95

            if r_squared > EXCELLENT_R2_THRESHOLD:
                quality = "(excellent)"
            elif r_squared > GOOD_R2_THRESHOLD:
                quality = "(good)"
            else:
                quality = "(fair)"

            print(f"    Fit quality: R^2 = {r_squared:.4f} {quality}")

            # Pass/fail assessment
            if deviation_pct <= run.profile.analysis.fit_tol_pct:
                print("\n  ✓ Performance matches expected complexity")
                print(
                    f"    Deviation: {deviation_pct:.1f}% (within {run.profile.analysis.fit_tol_pct:.0f}% tolerance)"
                )
            else:
                print("\n  ✗ Performance deviates from expected complexity")
                print(
                    f"    Deviation: {deviation_pct:.1f}% (exceeds {run.profile.analysis.fit_tol_pct:.0f}% tolerance)"
                )

            # Regression check with size mapping
            if run.profile.analysis.should_scan_regressions():
                regressions = self._find_performance_regressions(run, samples)
                if regressions:
                    print("\n  Regression Analysis:")
                    print(
                        f"    Tolerance: ±{run.profile.analysis.regression_tol_pct:.0f}% of model prediction"
                    )
                    print("    Violations:")

                    # Map numeric sizes back to expressions for clarity
                    size_to_expr = {
                        int(s.numeric_problem_size()): s.problem_size for s in samples
                    }

                    for size, deviation_pct in regressions:
                        expr = size_to_expr.get(size, f"size {size}")
                        print(
                            f"      • {expr:>20}: {deviation_pct:>6.1f}% slower than model"
                        )
                else:
                    print(
                        f"\n  ✓ All measurements within {run.profile.analysis.regression_tol_pct:.0f}% of model predictions"
                    )

        except (ValueError, ZeroDivisionError, OverflowError) as e:
            print(f"\n✗ Complexity analysis failed: {e}")
        except Exception as e:
            print(f"\n✗ Unexpected error in complexity analysis: {e}")

    def _find_performance_regressions(
        self, run: BenchmarkResult, samples: list[BenchmarkSample]
    ) -> list[tuple[int, float]]:
        """Find performance regressions against expected model.

        Compares actual performance against expected complexity model.
        Identifies samples that exceed regression tolerance threshold.

        Args:
            run: Benchmark result containing profile and analysis configuration.
            samples: List of benchmark samples sorted by problem size.

        Returns:
            List of (problem_size, deviation_percentage) tuples for regressions.
        """
        regressions = []
        baseline = samples[0]
        baseline_size = int(baseline.numeric_problem_size())

        for sample in samples[1:]:
            sample_size = int(sample.numeric_problem_size())

            # Calculate expected time based on model
            expected_time = run.profile.analysis.expected.calculate_expected_time(
                baseline.mean_time, baseline_size, sample_size
            )

            # Check if actual time exceeds expected by tolerance
            performance_ratio = sample.mean_time / expected_time
            if performance_ratio > 1 + run.profile.analysis.regression_tol_pct / 100:
                deviation_pct = (performance_ratio - 1) * 100
                regressions.append((sample_size, deviation_pct))

        return regressions

    def get_samples_by_task(self, task: BenchmarkTask) -> list[BenchmarkSample]:
        """Get all samples for a specific task across all runs."""
        samples = []
        for run in self.runs:
            if task in run.profile.tasks:
                samples.extend(run.samples)
        return samples

    def get_complexity_summary(self, task: BenchmarkTask) -> dict[str, Any]:
        """Get complexity analysis summary for a task."""
        samples = self.get_samples_by_task(task)
        if len(samples) < 2:
            return {}

        sorted_samples = sorted(samples, key=lambda s: s.numeric_problem_size())

        try:
            empirical_exponent, r_squared = _fit_power_law(sorted_samples)

            first_size = sorted_samples[0].numeric_problem_size()
            last_size = sorted_samples[-1].numeric_problem_size()

            # Get the expected complexity model from the first run containing this task
            expected_model = None
            for run in self.runs:
                if task in run.profile.tasks:
                    expected_model = run.profile.analysis.expected
                    break

            result = {
                "empirical_exponent": empirical_exponent,
                "r_squared": r_squared,
                "size_range": f"{first_size:.0f}-{last_size:.0f}",
                "samples": len(sorted_samples),
            }

            # Add interpreted complexity if we have a model
            if expected_model:
                result["interpreted_complexity"] = expected_model.interpret_exponent(
                    empirical_exponent
                )

            return result
        except (ValueError, ZeroDivisionError, OverflowError):
            return {}
