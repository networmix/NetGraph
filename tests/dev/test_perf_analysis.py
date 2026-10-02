"""Complexity fits in dev/perf are computed per profile run."""

from dev.perf.analysis import PerformanceAnalyzer
from dev.perf.core import (
    LINEAR,
    QUADRATIC,
    BenchmarkCase,
    BenchmarkProfile,
    BenchmarkResult,
    BenchmarkSample,
    BenchmarkTask,
    ComplexityAnalysisSpec,
    ComplexityModel,
)


def _run(name: str, model: ComplexityModel, times: dict[int, float]) -> BenchmarkResult:
    cases = [
        BenchmarkCase(f"{name}_{n}", BenchmarkTask.SHORTEST_PATH, str(n), {})
        for n in times
    ]
    profile = BenchmarkProfile(name, cases, ComplexityAnalysisSpec(model))
    samples = [
        BenchmarkSample(case, case.problem_size, t, t, 0.0, t, t, 5, "t0")
        for case, t in zip(cases, times.values(), strict=True)
    ]
    return BenchmarkResult(profile, samples, name, "t0", "t1")


def test_profiles_sharing_a_task_are_fitted_separately() -> None:
    linear = _run("linear", LINEAR, {10: 0.01, 100: 0.1, 1000: 1.0})
    quadratic = _run("quadratic", QUADRATIC, {10: 0.001, 100: 0.1, 1000: 10.0})
    analyzer = PerformanceAnalyzer()
    analyzer.add_runs([linear, quadratic])

    linear_fit = analyzer.get_complexity_summary(linear)
    quadratic_fit = analyzer.get_complexity_summary(quadratic)

    assert linear_fit["samples"] == 3
    assert quadratic_fit["samples"] == 3
    assert abs(linear_fit["empirical_exponent"] - 1.0) < 1e-9
    assert abs(quadratic_fit["empirical_exponent"] - 2.0) < 1e-9
