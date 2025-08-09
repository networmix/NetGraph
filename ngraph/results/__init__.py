"""Results store and metadata for workflow steps.

Exports the generic results container and its associated metadata. Concrete
artifact dataclasses live in ``ngraph.results.artifacts``.
"""

from __future__ import annotations

from .store import Results, WorkflowStepMetadata

__all__ = ["Results", "WorkflowStepMetadata"]
