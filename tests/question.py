"""The recorded question of an analysis or a workflow step, as it is exported."""

from ngraph.export import question
from ngraph.results import StepResult


def asked(value):
    """The question JSON of an analysis result or of a completed step."""
    if isinstance(value, StepResult):
        return question(value.question, getattr(value.result, "prepared", None))
    return question(value.query, value.prepared)
