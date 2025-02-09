from dataclasses import dataclass, field
from random import random


@dataclass(slots=True)
class FailurePolicy:
    """
    Mapping from element tag to failure probability.
    """

    failure_probabilities: dict[str, float] = field(default_factory=dict)
    distribution: str = "uniform"

    def test_failure(self, tag: str) -> bool:
        if self.distribution == "uniform":
            return random() < self.failure_probabilities.get(tag, 0)
        else:
            raise ValueError(f"Unsupported distribution: {self.distribution}")
