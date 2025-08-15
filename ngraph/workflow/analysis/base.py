"""Base classes for notebook analysis components.

Defines a minimal interface for notebook-oriented analyzers that compute
results and render them inline. Concrete analyzers implement ``analyze()``,
``display_analysis()``, and ``get_description()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class NotebookAnalyzer(ABC):
    """Base class for notebook analysis components.

    Subclasses should provide a pure computation method (``analyze``) and a
    rendering method (``display_analysis``). Use ``analyze_and_display`` as a
    convenience to run both.
    """

    @abstractmethod
    def analyze(self, results: dict[str, Any], **kwargs) -> dict[str, Any]:
        """Return analysis outputs for a given results document.

        Args:
            results: Results document containing workflow data for the analyzer.
            **kwargs: Analyzer-specific parameters (e.g. ``step_name``).

        Returns:
            A dictionary with analyzer-specific keys and values.
        """
        raise NotImplementedError

    @abstractmethod
    def get_description(self) -> str:
        """Return a concise description of the analyzer purpose."""
        raise NotImplementedError

    def analyze_and_display(self, results: dict[str, Any], **kwargs) -> None:
        """Analyze results and render them in notebook format."""
        analysis = self.analyze(results, **kwargs)
        self.display_analysis(analysis, **kwargs)

    @abstractmethod
    def display_analysis(self, analysis: dict[str, Any], **kwargs) -> None:
        """Render analysis outputs in notebook format."""
        raise NotImplementedError


@dataclass
class AnalysisContext:
    """Carry context information for analysis execution.

    Attributes:
        step_name: Name of the workflow step being analyzed.
        results: The full results document.
        config: Analyzer configuration or parameters for the step.
    """

    step_name: str
    results: dict[str, Any]
    config: dict[str, Any]
