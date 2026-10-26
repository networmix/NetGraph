"""The documented examples execute against the installed native engine."""

import contextlib
import io
import re
from pathlib import Path

import pytest
import yaml

from tests.docs.pages import GENERATED, fences, pages, workspace

PYTHON_PAGES = tuple(
    page
    for page in pages()
    if page not in GENERATED and any(f.lang == "python" for f in fences(page))
)


def test_every_page_with_python_examples_is_run():
    assert set(PYTHON_PAGES) >= {
        "README.md",
        "docs/concepts.md",
        "docs/examples/basic.md",
        "docs/examples/clos-fabric.md",
        "docs/getting-started/tutorial.md",
        "docs/reference/api.md",
        "docs/reference/dsl.md",
        "docs/reference/schemas.md",
    }


@pytest.mark.parametrize("page", PYTHON_PAGES)
def test_documented_python_client(page, tmp_path, monkeypatch):
    """Each Python example runs in order, in a reader's working directory, and prints
    exactly the output the page shows after it (nothing, if the page shows none)."""
    monkeypatch.chdir(workspace(tmp_path))
    namespace = {"__name__": "__documented_client__"}
    found = fences(page)
    for index, block in enumerate(found):
        if block.lang != "python":
            continue
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            exec(compile(block.text, f"{page}:{block.line}", "exec"), namespace)
        shown = found[index + 1] if index + 1 < len(found) else None
        expected = shown.text if shown is not None and shown.marker == "output" else ""
        assert printed.getvalue() == expected, f"{page}:{block.line}"


def test_every_shown_output_follows_a_python_example():
    for page in pages():
        found = fences(page)
        for index, block in enumerate(found):
            if block.marker == "output":
                assert block.lang == "text" and index > 0, f"{page}:{block.line}"
                assert found[index - 1].lang == "python", f"{page}:{block.line}"


class UniqueKeyLoader(yaml.SafeLoader):
    """PyYAML's safe loader, refusing a key repeated in one mapping (YAML keeps the last)."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue  # `<<` merges a mapping; several merges are not a repeat
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"repeated key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_example(block):
    return yaml.load(block, Loader=UniqueKeyLoader)


def _escape(token):
    return token.replace("~", "~0").replace("/", "~1")


def _resolve(schema, pointer):
    """The node a JSON pointer names, following a node that is only a ``$ref``."""
    node = schema
    for token in pointer.removeprefix("#").split("/")[1:]:
        node = node[token.replace("~1", "/").replace("~0", "~")]
    while set(node) <= {"$ref", "description"} and "$ref" in node:
        pointer = node["$ref"]
        node = _resolve(schema, pointer)[0]
    return node, pointer


def fragment_contexts(schema, pointer, data):
    """(key, pointer to its schema) for each key of the block, in the object ``pointer`` names.

    A block is one mapping, or a list of mappings (one example per item); every key must
    be a property of that object, match one of its patterns or fall under its additional
    properties schema.
    """
    container, at = _resolve(schema, pointer)
    items = data if isinstance(data, list) else [data]
    assert items, "empty fragment"
    out = []
    for item in items:
        assert isinstance(item, dict) and item, (
            f"fragment item is not a mapping: {item!r}"
        )
        for key in item:
            if key in container.get("properties", {}):
                out.append((key, f"{at}/properties/{_escape(key)}"))
                continue
            pattern = next(
                (
                    p
                    for p in container.get("patternProperties", {})
                    if re.search(p, key)
                ),
                None,
            )
            if pattern is not None:
                out.append((key, f"{at}/patternProperties/{_escape(pattern)}"))
            elif isinstance(container.get("additionalProperties"), dict):
                out.append((key, f"{at}/additionalProperties"))
            else:
                raise AssertionError(f"{key!r} is not a key of {pointer}")
    return out


def check_example(kind, argument, block):
    """Check one marked (or unmarked) YAML example; shared with the skill's examples."""
    import json
    from importlib import resources

    import jsonschema

    from ngraph.scenario import Scenario, prepare

    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    validator = jsonschema.validators.validator_for(schema)(schema)
    data = load_example(block)
    if kind == "fragment":
        items = data if isinstance(data, list) else [data]
        contexts = iter(fragment_contexts(schema, argument, data))
        for item in items:
            for value in item.values():
                _, at = next(contexts)
                validator.evolve(schema={"$ref": at}).validate(value)
    elif kind == "unprepared":
        validator.validate(data)
    elif kind == "refusal":
        with pytest.raises(ValueError, match=re.escape(argument)):
            prepare(Scenario.from_yaml(block))
    else:
        prepare(Scenario.from_yaml(block))


MARKER = re.compile(r"<!-- example: (fragment|unprepared|refusal)(?: (.*?))? -->\n\n$")


def _yaml_examples():
    root = Path(__file__).resolve().parents[2]
    for path in [root / "README.md", *sorted((root / "docs").rglob("*.md"))]:
        text = path.read_text()
        for index, match in enumerate(
            re.finditer(r"```yaml\n(.*?)```", text, re.DOTALL)
        ):
            found = MARKER.search(text[: match.start()][-200:])
            kind, argument = (found[1], found[2]) if found else ("scenario", None)
            yield pytest.param(
                kind, argument, match[1], id=f"{path.relative_to(root)}#{index}"
            )


EXAMPLES = tuple(_yaml_examples())


@pytest.mark.parametrize(("kind", "argument", "block"), EXAMPLES)
def test_documented_yaml_examples(kind, argument, block):
    """Every YAML example is a scenario that prepares, or is marked before its fence.

    `fragment <JSON pointer>`: the pointer names the schema object that holds the block's
    keys; each key (the wrapper included) must belong to that object and its value be
    valid there. A list block holds one such mapping per item. `unprepared`: a whole
    scenario valid against the schema whose references the page does not declare;
    `refusal <text>`: preparation refuses with that text. No block repeats a key.
    """
    check_example(kind, argument, block)


DEMAND = "#/properties/demands/additionalProperties/items"


@pytest.mark.parametrize(
    ("argument", "block", "message"),
    [
        # A misspelt wrapper key is not a key of the demand.
        (DEMAND, "modle:\n  admission: lossless\n", "'modle' is not a key"),
        # A repeated key: YAML would keep only the last example.
        (DEMAND, "source: {path: 7}\nsource: a\n", "repeated key 'source'"),
        # The value is checked in its context, not only for the key.
        (DEMAND, "- source: a\n- source: {path: 7}\n", "is not valid"),
        # A key under a closed object.
        (
            "#/$defs/matchSpec",
            "conditions: []\nflow_policy: x\n",
            "'flow_policy' is not a key",
        ),
    ],
)
def test_a_fragment_is_checked_in_its_schema_context(argument, block, message):
    with pytest.raises(
        (AssertionError, yaml.YAMLError, ValueError, Exception), match=message
    ):
        check_example("fragment", argument, block)


def test_every_marked_kind_occurs_and_the_examples_are_counted():
    kinds = [param.values[0] for param in EXAMPLES]
    assert {kind: kinds.count(kind) for kind in set(kinds)} == {
        "scenario": 38,
        "fragment": 11,
        "unprepared": 9,
        "refusal": 3,
    }


def test_every_scenario_schema_property_is_named_in_the_input_reference():
    # The YAML reference is dsl.md and workflow.md: a property is named there in inline
    # code (`name`, `name: value`, `a.name`) or as a key of a YAML example.
    import json
    from importlib import resources

    root = Path(__file__).resolve().parents[2]
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    names = set()

    def walk(node):
        if isinstance(node, dict):
            for name, value in node.get("properties", {}).items():
                names.add(name)
                walk(value)
            for value in node.values():
                if isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    text = "".join(
        (root / "docs/reference" / page).read_text()
        for page in ("dsl.md", "workflow.md")
    )
    blocks = " ".join(re.findall(r"```yaml\n(.*?)```", text, re.DOTALL))
    prose = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    inline = " ".join(re.findall(r"`([^`\n]+)`", prose))

    def named(name):
        word = rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])"
        return re.search(word, inline) or re.search(
            rf"(?:^|[\s{{,-]){re.escape(name)}:", blocks
        )

    assert len(names) > 100
    assert sorted(name for name in names if not named(name)) == []
