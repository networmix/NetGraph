#!/usr/bin/env python3
"""Complexity plots and JSON export for benchmark results."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # Headless backend; must be set before importing pyplot
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import seaborn as sns  # noqa: E402

from .analysis import PerformanceAnalyzer, _fit_power_law
from .core import BenchmarkResult


class PerformanceVisualizer:
    """Write complexity plots and the results JSON for benchmark runs."""

    def __init__(self, plots_dir: Path = Path("dev/perf_plots")):
        self.plots_dir = plots_dir
        self.plots_dir.mkdir(parents=True, exist_ok=True)
        self._configure_style()

    def _configure_style(self) -> None:
        """Configure seaborn styling for plots."""
        sns.set_theme(style="whitegrid", palette="deep")
        sns.set_context("paper", font_scale=1.2)

        plt.rcParams.update(
            {
                "figure.dpi": 300,
                "savefig.dpi": 300,
                "savefig.bbox": "tight",
                "savefig.facecolor": "white",
                "savefig.edgecolor": "none",
                "font.size": 11,
                "axes.labelsize": 12,
                "axes.titlesize": 14,
                "xtick.labelsize": 10,
                "ytick.labelsize": 10,
                "legend.fontsize": 10,
                "legend.title_fontsize": 11,
            }
        )

    def create_summary_report(
        self, analyzer: PerformanceAnalyzer, timestamp: str
    ) -> None:
        """Write a complexity plot for each run whose profile enables plots.

        Args:
            analyzer: Performance analyzer with benchmark results.
            timestamp: Suffix shared by the plot file names of one run.
        """
        if not analyzer.runs:
            print("No benchmark results to visualize")
            return

        for run in analyzer.runs:
            if run.profile.analysis.generates_plots():
                self.plot_complexity_analysis(run, timestamp)

    def plot_complexity_analysis(self, run: BenchmarkResult, timestamp: str) -> None:
        """Plot measured times, the expected model, and a power-law fit.

        Writes ``{task}_{profile_name}_{timestamp}_complexity.png`` under
        ``plots_dir``. Only this run's samples are plotted and fitted.

        Args:
            run: Benchmark result of one profile.
            timestamp: Suffix shared by the plot file names of one run.
        """
        task = run.task
        profile_name = run.profile.name
        samples = run.samples
        if len(samples) < 2:
            print(f"Insufficient samples for {task.name} complexity plot")
            return

        sorted_samples = sorted(samples, key=lambda s: s.numeric_problem_size())

        SECONDS_TO_MS = 1000
        sizes = np.array([s.numeric_problem_size() for s in sorted_samples])
        times = np.array([s.mean_time * SECONDS_TO_MS for s in sorted_samples])
        errors = np.array([s.std_dev * SECONDS_TO_MS for s in sorted_samples])

        fig, ax = plt.subplots(figsize=(10, 6))

        ax.errorbar(
            sizes,
            times,
            yerr=errors,
            fmt="o",
            capsize=4,
            capthick=1.5,
            markersize=6,
            linewidth=2,
            label="Measured Performance",
            color=sns.color_palette("deep")[0],
        )

        model = run.profile.analysis.expected

        # Anchor the expected curve at the smallest measured size.
        baseline_size = sizes[0]
        baseline_time = times[0]

        CURVE_SAMPLES = 200
        curve_sizes = np.linspace(min(sizes), max(sizes), CURVE_SAMPLES)
        theory_times = np.array(
            [
                model.calculate_expected_time(
                    baseline_time / SECONDS_TO_MS, int(baseline_size), int(size)
                )
                * SECONDS_TO_MS
                for size in curve_sizes
            ]
        )

        ax.plot(
            curve_sizes,
            theory_times,
            "--",
            linewidth=2,
            alpha=0.8,
            label=f"Expected {model.display_name}",
            color=sns.color_palette("deep")[1],
        )

        try:
            empirical_exponent, r_squared = _fit_power_law(sorted_samples)

            # y = a * x^b with a chosen so the curve passes through the
            # smallest sample; the fit's own intercept is not used.
            baseline_log_size = math.log(baseline_size)
            baseline_log_time = math.log(baseline_time / SECONDS_TO_MS)
            log_constant = baseline_log_time - empirical_exponent * baseline_log_size

            empirical_times = np.array(
                [
                    math.exp(log_constant + empirical_exponent * math.log(size))
                    * SECONDS_TO_MS
                    for size in curve_sizes
                ]
            )

            ax.plot(
                curve_sizes,
                empirical_times,
                "-",
                linewidth=2,
                alpha=0.9,
                label=f"Empirical Fit (R^2 = {r_squared:.3f})",
                color=sns.color_palette("deep")[2],
            )
        except (ValueError, ZeroDivisionError, OverflowError) as e:
            print(f"    Warning: Could not generate empirical fit line: {e}")
        except Exception as e:
            print(f"    Warning: Unexpected error generating empirical fit: {e}")

        ax.set_xlabel("Problem Size", fontweight="bold")
        ax.set_ylabel("Runtime (ms)", fontweight="bold")
        ax.set_title(
            f"{task.name.replace('_', ' ').title()} Performance Scaling",
            fontweight="bold",
            pad=20,
        )

        ax.grid(True, alpha=0.3)
        ax.legend(frameon=True, fancybox=True, shadow=True)
        plt.tight_layout()

        plot_path = (
            self.plots_dir / f"{task.name}_{profile_name}_{timestamp}_complexity.png"
        )
        plt.savefig(plot_path)
        plt.close()

        print(f"  • Complexity plot: {plot_path}")

    def export_results_json(
        self,
        analyzer: PerformanceAnalyzer,
        profile_results: list[tuple[str, BenchmarkResult]],
        filepath: Path,
    ) -> None:
        """Write per-profile samples, settings, and fits to ``filepath``.

        Also prints a summary table of all profiles.
        """
        data = {"profiles": []}

        for _, result in profile_results:
            task = result.task
            complexity_summary = analyzer.get_complexity_summary(result)

            profile_data = {
                "name": result.profile.name,
                "task": task.name,
                "samples": [],
                "config": {
                    "expected_complexity": result.profile.analysis.expected.display_name,
                    "fit_tolerance_pct": result.profile.analysis.fit_tol_pct,
                    "regression_tolerance_pct": result.profile.analysis.regression_tol_pct,
                    "iterations": result.profile.iterations,
                },
                "metadata": {
                    "run_id": result.run_id,
                    "started_at": result.started_at,
                    "finished_at": result.finished_at,
                },
            }

            for sample in result.samples:
                profile_data["samples"].append(
                    {
                        "case_name": sample.case.name,
                        "problem_size": str(sample.problem_size),
                        "numeric_problem_size": sample.numeric_problem_size(),
                        "mean_time": sample.mean_time,
                        "median_time": sample.median_time,
                        "std_dev": sample.std_dev,
                        "min_time": sample.min_time,
                        "max_time": sample.max_time,
                        "rounds": sample.rounds,
                        "timestamp": sample.timestamp,
                    }
                )

            if complexity_summary:
                profile_data["analysis_results"] = {
                    "complexity_analysis": complexity_summary,
                    "performance_summary": {
                        "fastest_time": result.min_time,
                        "slowest_time": result.max_time,
                        "total_rounds": result.total_rounds,
                    },
                }

            data["profiles"].append(profile_data)

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        print(f"  • Results JSON: {filepath}")
        KB_BYTES = 1024
        print(f"    Size: {filepath.stat().st_size / KB_BYTES:.1f} KB")

        self._print_results_summary(profile_results)

    def _print_results_summary(
        self, profile_results: list[tuple[str, BenchmarkResult]]
    ) -> None:
        """Print a summary table of all benchmark results."""
        profile_names = [name for name, _ in profile_results]
        profile_width = max(len(name) for name in profile_names + ["Profile", "Total"])

        print("\n  Execution Summary:")
        print(
            f"  {'Profile':>{profile_width}} {'Samples':>10} {'Wall Time':>12} {'Min':>10} {'Max':>10} {'Mean':>10}"
        )
        print(
            f"  {'-' * profile_width} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}"
        )

        total_wall_time = 0.0

        for profile_name, result in profile_results:
            wall_time = result.total_execution_time()
            total_wall_time += wall_time

            SECONDS_TO_MS = 1000
            all_times = [s.mean_time * SECONDS_TO_MS for s in result.samples]
            min_time = min(all_times)
            max_time = max(all_times)
            mean_time = sum(all_times) / len(all_times)

            print(
                f"  {profile_name:>{profile_width}} {len(result.samples):>10} "
                f"{wall_time:>10.2f}s {min_time:>8.2f}ms {max_time:>8.2f}ms {mean_time:>8.2f}ms"
            )

        print(
            f"  {'-' * profile_width} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 10} {'-' * 10}"
        )
        print(f"  {'Total':>{profile_width}} {' ':>10} {total_wall_time:>10.2f}s")
        print("\n  Wall time is mean time x rounds; warm-up calls are excluded")
