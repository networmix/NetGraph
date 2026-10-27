"""Parsing and overrides retain the declaration that supplied each refused value."""

import signal

import numpy as np
import pytest
import yaml

from ngraph import Component, ComponentsLibrary, Network, Node, Scenario, prepare, run
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.workflow import CostPower


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *args: pytest.fail("case exceeded 4 seconds")
    )
    signal.alarm(4)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


LOADERS = [load_scenario_yaml, Scenario.from_yaml, ComponentsLibrary.from_yaml]


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize(
    "tag,value,good", [("int", "bad", "1"), ("float", "bad", "1.0")]
)
def test_other_failed_scalar_conversions_share_the_same_source_boundary(
    loader, tag, value, good
):
    source = f"components: {{c: {{count: !!{tag} {value}}}}}"
    with pytest.raises(ValueError) as error:
        loader(source)
    assert type(error.value) is ValueError
    assert str(error.value).startswith(
        "components.c.count: invalid YAML scalar at line 1, column "
    )
    assert f"{value!r} (3 characters)" in str(error.value)
    assert type(error.value.__cause__) is ValueError
    loader(source.replace(value, good))


@pytest.mark.parametrize("loader", LOADERS)
def test_shared_parser_retains_syntax_cause_and_does_not_change_regular_yaml(loader):
    with pytest.raises(ValueError) as error:
        loader("components: {c: [}")
    assert type(error.value) is ValueError
    assert isinstance(error.value.__cause__, yaml.YAMLError)
    assert "line 1, column" in str(error.value)
    loader("components: {c: {count: 2}}")


def override_document(value, kind, *, parent="P", group="G"):
    doc = {
        "blueprints": {
            "unit": {"nodes": {group: {"nodes": {"H": {"template": "n-{n}"}}}}}
        },
        "network": {"nodes": {parent: {"blueprint": "unit"}}},
    }
    if kind == "nodes":
        overrides = {f"{group}.nodes": {"H": {"template": value}}}
        tail = f"{group}.nodes.H.template"
    elif kind == "node":
        overrides = {f"{group}.nodes.H": {"template": value}}
        tail = f"{group}.nodes.H.template"
    elif kind == "dotted":
        overrides = {f"{group}.nodes.H.template": value}
        tail = f"{group}.nodes.H.template"
    elif kind == "params":
        doc["blueprints"]["inner"] = {"nodes": {"H": {"template": "n-{n}"}}}
        doc["blueprints"]["unit"]["nodes"][group] = {"blueprint": "inner"}
        overrides = {f"{group}.params": {"H.template": value}}
        tail = f"{group}.params.H.template"
    elif kind == "deep-params":
        doc["blueprints"]["inner"] = {"nodes": {"H": {"blueprint": "leaf"}}}
        doc["blueprints"]["leaf"] = {"nodes": {"L": {"template": "n-{n}"}}}
        doc["blueprints"]["unit"]["nodes"][group] = {"blueprint": "inner"}
        overrides = {f"{group}.params": {"H.params": {"L.template": value}}}
        tail = f"{group}.params.H.params.L.template"
    else:
        doc["blueprints"]["unit"]["nodes"][group] = {"template": "n-{n}"}
        overrides = {f"{group}.template": value}
        tail = f"{group}.template"
    doc["network"]["nodes"][parent]["params"] = overrides
    return doc, f"network.nodes.{parent}.params.{tail}"


@pytest.mark.parametrize(
    "kind", ["direct", "nodes", "node", "dotted", "params", "deep-params"]
)
@pytest.mark.parametrize("value", [3, "{n[0]}", "{missing}"])
@pytest.mark.parametrize("parent,group", [("P", "G"), ("site[1-2]", "rack.a")])
def test_overrides_keep_field_and_subtree_sources_through_every_merge(
    kind, value, parent, group
):
    doc, path = override_document(value, kind, parent=parent, group=group)
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False))
    assert type(error.value) is ValueError
    assert str(error.value).startswith(path + ":"), str(error.value)
    assert repr(value) in str(error.value)
    good, _ = override_document("n-{n}", kind, parent=parent, group=group)
    assert len(Scenario.from_yaml(yaml.safe_dump(good)).network.nodes) == (
        2 if "[" in parent else 1
    )


def test_overridden_sibling_does_not_relabel_an_unchanged_blueprint_template():
    doc, _ = override_document("n-{n}", "dotted")
    doc["blueprints"]["unit"]["nodes"]["G"]["nodes"]["J"] = {"template": "{n[0]}"}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(doc))
    assert str(error.value).startswith("blueprints.unit.nodes.G.nodes.J.template:")
    doc["blueprints"]["unit"]["nodes"]["G"]["nodes"]["J"]["template"] = "j-{n}"
    assert len(Scenario.from_yaml(yaml.safe_dump(doc)).network.nodes) == 2


@pytest.mark.parametrize("position", [0, 1])
def test_subtree_then_field_assignment_preserves_both_actual_sources(position):
    doc, _ = override_document("n-{n}", "nodes")
    entries = [
        ("G.nodes", {"H": {"template": "h-{n}"}}),
        ("G.nodes.H.template", "h-{n}"),
    ]
    if position:
        entries.reverse()
    doc["network"]["nodes"]["P"]["params"] = dict(entries)
    assert (
        len(Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False)).network.nodes) == 1
    )
    final_key, value = entries[-1]
    if isinstance(value, dict):
        value["H"]["template"] = "{n[0]}"
    else:
        doc["network"]["nodes"]["P"]["params"][final_key] = "{n[0]}"
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False))
    assert str(error.value).startswith("network.nodes.P.params.G.nodes.H.template:")
    assert "'{n[0]}'" in str(error.value)


@pytest.mark.parametrize("key", [np.int64(1), np.uint64(1)])
@pytest.mark.parametrize("requested", [3, 1 << 62])
def test_numpy_integer_keys_are_hashed_and_compared(key, requested):
    levels = (
        run(
            prepare(
                Scenario(
                    Network(
                        nodes={
                            "a/b": Node("a/b", attrs={"hardware": {"component": "c"}})
                        }
                    ),
                    components_library=ComponentsLibrary(
                        {"c": Component("c", capex=7)}
                    ),
                    workflow=[CostPower(aggregation_level=requested)],
                )
            )
        )
        .steps[0]
        .result.levels
    )
    expected = {1: levels.rows[1]}
    assert [row.path for row in expected[1]] == ["a"]
    assert levels[key] == expected[key]
    assert levels.get(key) == expected.get(key)
    assert (key in levels) == (key in expected)
    assert len(levels.rows) == 3


@pytest.mark.parametrize("command", ["run", "inspect"])
@pytest.mark.parametrize("kind", ["dotted", "params"])
def test_cli_reports_the_scalar_or_override_that_supplied_the_value(
    tmp_path, capsys, command, kind
):
    from ngraph.cli import main

    doc, path = override_document("{n[0]}", kind)
    text, raw = yaml.safe_dump(doc), "'{n[0]}'"
    filename = tmp_path / "case.yml"
    filename.write_text(text)
    with pytest.raises(SystemExit) as error:
        main([command, str(filename)])
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert path in message and raw in message


@pytest.mark.parametrize("loader", LOADERS)
def test_invalid_explicit_boolean_scalar_has_the_same_refusal_boundary(loader):
    text = "components: {c: {attrs: {flag: !!bool bad}}}"
    loader(text.replace("bad", "true"))
    with pytest.raises(ValueError) as error:
        loader(text)
    assert type(error.value) is ValueError
    assert str(error.value).startswith(
        "components.c.attrs.flag: invalid YAML scalar at line 1, column "
    )
    assert "'bad' (3 characters)" in str(error.value)
    assert type(error.value.__cause__) is KeyError
