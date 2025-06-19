"""Base classes for notebook analysis components."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict


class NotebookAnalyzer(ABC):
    """Base class for notebook analysis components."""

    @abstractmethod
    def analyze(self, results: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """Perform the analysis and return results."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get a description of what this analyzer does."""
        pass

    def analyze_and_display(self, results: Dict[str, Any], **kwargs) -> None:
        """Analyze results and display them in notebook format."""
        analysis = self.analyze(results, **kwargs)
        self.display_analysis(analysis, **kwargs)

    @abstractmethod
    def display_analysis(self, analysis: Dict[str, Any], **kwargs) -> None:
        """Display analysis results in notebook format."""
        pass


@dataclass
class AnalysisContext:
    """Context information for analysis execution."""

    step_name: str
    results: Dict[str, Any]
    config: Dict[str, Any]
