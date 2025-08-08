#!/usr/bin/env python3
"""Core data structures for NetGraph performance analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class BenchmarkTask(Enum):
    """Supported benchmark tasks."""

    SHORTEST_PATH = auto()
    SHORTEST_PATH_NETWORKX = auto()
    MAX_FLOW = auto()
    # Add more tasks as they are implemented


@dataclass
class ComplexityModel:
    """Lightweight complexity model for performance analysis."""

    name: str
    expected_exponent: float
    display_name: str = ""

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name.replace("_", " ")

    def calculate_expected_time(
        self,
        baseline_time: float,
        baseline_size: int,
        target_size: int,
    ) -> float:
        """Calculate expected runtime for target_size given this complexity model."""
        if baseline_size <= 0 or target_size <= 0:
            raise ValueError("sizes must be positive")

        ratio = target_size / baseline_size

        if self.name == "linear":
            return baseline_time * ratio
        elif self.name == "n_log_n":
            baseline_log = 1.0 if baseline_size == 1 else math.log(baseline_size)
            target_log = 1.0 if target_size == 1 else math.log(target_size)
            return baseline_time * ratio * (target_log / baseline_log)
        elif self.name == "quadratic":
            return baseline_time * ratio**2
        elif self.name == "cubic":
            return baseline_time * ratio**3
        else:
            # Generic power law scaling
            return baseline_time * (ratio**self.expected_exponent)

    def interpret_exponent(self, empirical_exponent: float) -> str:
        """Interpret empirical exponent into human-readable complexity description.

        Thresholds based on common algorithmic complexity classes:
        - < 1.2: near-linear (close to O(n))
        - 1.2-1.8: sub-quadratic (between O(n) and O(n^2))
        - 1.8-2.5: quadratic (close to O(n^2))
        - > 2.5: super-quadratic (worse than O(n^2))

        Args:
            empirical_exponent: Measured scaling exponent from power law fit.

        Returns:
            Human-readable complexity description.
        """
        # Complexity interpretation thresholds
        LINEAR_THRESHOLD = 1.2
        QUADRATIC_THRESHOLD = 1.8
        SUPER_QUADRATIC_THRESHOLD = 2.5

        if empirical_exponent < LINEAR_THRESHOLD:
            return "near-linear"
        elif empirical_exponent < QUADRATIC_THRESHOLD:
            return "sub-quadratic"
        elif empirical_exponent < SUPER_QUADRATIC_THRESHOLD:
            return "quadratic"
        else:
            return "super-quadratic"


# Predefined complexity models
LINEAR = ComplexityModel("linear", 1.0, "Linear O(n)")
N_LOG_N = ComplexityModel("n_log_n", 1.1, "n log n")
QUADRATIC = ComplexityModel("quadratic", 2.0, "Quadratic O(n^2)")
CUBIC = ComplexityModel("cubic", 3.0, "Cubic O(n^3)")


@dataclass
class ComplexityAnalysisSpec:
    """Configuration for time-complexity analysis."""

    expected: ComplexityModel
    fit_tol_pct: float = 20.0  # max % deviation of empirical exponent
    regression_tol_pct: float = 30.0  # max % runtime above model curve
    plots: bool = True

    def should_scan_regressions(self) -> bool:
        return self.regression_tol_pct > 0

    def generates_plots(self) -> bool:
        return self.plots


@dataclass(frozen=True)
class BenchmarkCase:
    """Immutable description of how to run one test case."""

    name: str
    task: BenchmarkTask
    problem_size: str
    inputs: dict[str, Any]  # e.g. topology object
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("case.name must not be empty")

    def numeric_problem_size(self) -> float:
        """Get the numeric value of problem_size.

        Supports simple math expressions using standard functions.
        Examples: "100", "10 * log(10)", "2 ** 8", "sqrt(100)"

        Returns:
            Numeric problem size value.

        Raises:
            ValueError: If problem_size cannot be evaluated safely.
        """
        if not isinstance(self.problem_size, str):
            raise ValueError(f"problem_size must be str, got {type(self.problem_size)}")

        # Validate expression contains only allowed characters
        allowed_chars = set("0123456789+-*/.() abcdefghijklmnopqrstuvwxyz_")
        if not all(c in allowed_chars for c in self.problem_size.lower()):
            raise ValueError(f"Invalid characters in problem_size: {self.problem_size}")

        # Create restricted namespace - only math functions, no builtins
        safe_globals = {
            "__builtins__": {},
            "math": math,
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "sqrt": math.sqrt,
            "pow": math.pow,
            "exp": math.exp,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "pi": math.pi,
            "e": math.e,
        }
        try:
            result = eval(self.problem_size, safe_globals, {})
            if not isinstance(result, (int, float)):
                raise ValueError(
                    f"Expression must evaluate to a number, got {type(result)}"
                )
            return float(result)
        except Exception as e:
            raise ValueError(
                f"Invalid problem_size expression '{self.problem_size}': {e}"
            ) from e


@dataclass
class BenchmarkProfile:
    """A logical benchmark suite (scaling series or batch)."""

    name: str
    cases: list[BenchmarkCase]
    analysis: ComplexityAnalysisSpec
    iterations: int = 5

    def __post_init__(self) -> None:
        if self.iterations <= 0:
            raise ValueError("iterations must be > 0")
        if not self.cases:
            raise ValueError("profile must contain at least one BenchmarkCase")

    @property
    def tasks(self) -> list[BenchmarkTask]:
        return list({c.task for c in self.cases})


@dataclass
class BenchmarkSample:
    """Concrete measurement produced by executing a case."""

    case: BenchmarkCase
    problem_size: str
    mean_time: float
    median_time: float
    std_dev: float
    min_time: float
    max_time: float
    rounds: int
    timestamp: str

    def __post_init__(self) -> None:
        if self.mean_time <= 0:
            raise ValueError("mean_time must be positive")
        if self.rounds <= 0:
            raise ValueError("rounds must be positive")

    @property
    def name(self) -> str:
        return f"{self.case.task.name}:{self.problem_size}"

    @property
    def time_ms(self) -> float:
        """Convert mean time from seconds to milliseconds."""
        SECONDS_TO_MS = 1000
        return self.mean_time * SECONDS_TO_MS

    def numeric_problem_size(self) -> float:
        """Get the numeric value of problem_size."""
        return self.case.numeric_problem_size()


@dataclass
class BenchmarkResult:
    """Collection of samples produced by one profile execution."""

    profile: BenchmarkProfile
    samples: list[BenchmarkSample]
    run_id: str
    started_at: str
    finished_at: str

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError("result must contain at least one sample")

    @property
    def task(self) -> BenchmarkTask:
        return self.samples[0].case.task

    @property
    def min_time(self) -> float:
        return min(s.min_time for s in self.samples)

    @property
    def max_time(self) -> float:
        return max(s.max_time for s in self.samples)

    @property
    def total_rounds(self) -> int:
        return sum(s.rounds for s in self.samples)

    def total_execution_time(self) -> float:
        """Calculate total benchmark execution time in seconds."""
        return sum(s.mean_time * s.rounds for s in self.samples)


def calculate_expected_time(
    baseline_time: float,
    baseline_size: int,
    target_size: int,
    complexity: str,
) -> float:
    """Calculate expected runtime for target_size given baseline performance.

    Args:
        baseline_time: Measured time at baseline_size
        baseline_size: Input size for baseline measurement
        target_size: Input size for prediction
        complexity: Complexity class ("linear", "n_log_n", "quadratic", "cubic")

    Returns:
        Expected runtime at target_size
    """
    if complexity == "linear":
        model = LINEAR
    elif complexity == "n_log_n":
        model = N_LOG_N
    elif complexity == "quadratic":
        model = QUADRATIC
    elif complexity == "cubic":
        model = CUBIC
    else:
        raise ValueError(f"Unknown complexity: {complexity}")

    return model.calculate_expected_time(baseline_time, baseline_size, target_size)
