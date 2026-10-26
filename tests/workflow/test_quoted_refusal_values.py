"""Quoted diagnostic values use repr, including non-text inputs."""

import pytest

from ngraph.model.selectors import parse_match_spec
from ngraph.workflow.parse import build_workflow_steps


@pytest.mark.parametrize(
    "value",
    ["bad", "a'b", r"a\b", 3, True, None, "x" * 100000],
    ids=["plain", "quote", "backslash", "integer", "flag", "null", "long"],
)
def test_match_logic_uses_the_common_value_format(value):
    rendered = repr(value)
    shown = rendered if len(rendered) <= 60 else rendered[:57] + "..."
    with pytest.raises(ValueError) as error:
        parse_match_spec({"logic": value})
    assert str(error.value) == f"Invalid logic {shown} in match. Must be 'and' or 'or'."
    assert len(str(error.value)) < 500
    parse_match_spec({"logic": "or"})


@pytest.mark.parametrize(
    "name",
    ["bad", "a'b", r"a\b", 3, "x" * 100],
    ids=["plain", "quote", "backslash", "integer", "long"],
)
def test_step_name_in_unknown_key_context_uses_repr(name):
    entry = {"type": "BuildGraph", "name": name, "bogus": 1}
    rendered = repr(name)
    shown = rendered if len(rendered) <= 60 else rendered[:57] + "..."
    location = f"workflow[0] (name {shown})" if isinstance(name, str) else "workflow[0]"
    raw = repr(entry)
    raw = raw if len(raw) <= 60 else raw[:57] + "..."
    reason = f"Unrecognized key(s) in workflow step {shown}: bogus. Allowed keys are: ['add_reverse', 'name', 'seed']"
    reason = reason if len(reason) <= 220 else reason[:217] + "..."
    with pytest.raises(ValueError) as error:
        build_workflow_steps([entry], lambda name: None)
    assert str(error.value) == f"{location} = {raw}: {reason}"
    assert len(str(error.value)) < 500
    build_workflow_steps([{"type": "BuildGraph", "name": "good"}], lambda name: None)
