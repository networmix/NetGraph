"""The Claude skill's YAML examples (``.claude/skills``, a submodule) run on this NetGraph.

Every ```yaml block of the netgraph-dsl skill is a scenario that prepares, or is marked before its
fence like the documentation's examples (``<!-- example: fragment <JSON pointer> -->``,
``unprepared``, ``refusal <text>``) and checked by the same function. The submodule must be
checked out (``git submodule update --init``; CI checks it out).
"""

import re
from pathlib import Path

import pytest

from tests.integration.test_documented_clients import MARKER, check_example

SKILL = Path(__file__).resolve().parents[2] / ".claude/skills/netgraph-dsl"


def _examples():
    if not SKILL.is_dir():
        return [pytest.param(None, None, None, id="submodule-missing")]
    out = []
    for path in sorted(SKILL.rglob("*.md")):
        text = path.read_text()
        for index, match in enumerate(
            re.finditer(r"```yaml\n(.*?)```", text, re.DOTALL)
        ):
            found = MARKER.search(text[: match.start()][-200:])
            kind, argument = (found[1], found[2]) if found else ("scenario", None)
            out.append(
                pytest.param(
                    kind, argument, match[1], id=f"{path.relative_to(SKILL)}#{index}"
                )
            )
    return out


@pytest.mark.parametrize(("kind", "argument", "block"), _examples())
def test_skill_yaml_examples(kind, argument, block):
    if kind is None:
        pytest.fail("the .claude/skills submodule is not checked out")
    check_example(kind, argument, block)


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ("modle:\n  admission: lossless\n", "'modle' is not a key"),
        ("source: {path: 7}\nsource: a\n", "repeated key 'source'"),
    ],
)
def test_a_wrong_skill_fragment_is_refused(block, message):
    with pytest.raises(Exception, match=message):
        check_example(
            "fragment", "#/properties/demands/additionalProperties/items", block
        )
