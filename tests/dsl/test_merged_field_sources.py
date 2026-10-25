"""A merged definition is checked at each field's supplying declaration."""

import copy
import json
import signal
from pathlib import Path

import pytest
import yaml

from ngraph import ComponentsLibrary, Scenario
from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.dsl.loader import load_scenario_yaml

# Independent census of every node-definition field, checked against the schema.
FIELDS = {
    "disabled": ("false", False, {}),
    "attrs": (3, {"role": "edge"}, {}),
    "risk_groups": (3, [], {}),
    "count": (0, 1, {}),
    "template": (3, "n-{n}", {}),
    "nodes": (3, {"L": {}}, {"nodes": {"L": {}}}),
    "blueprint": (3, "leaf", {"blueprint": "leaf"}),
    "params": (3, {}, {"blueprint": "leaf"}),
}
STYLES = (
    "direct",
    "blueprint",
    "blueprint-root",
    "flat",
    "dotted",
    "node",
    "subtree",
    "nested-params",
    "deep-params",
)


@pytest.fixture(autouse=True)
def bounded_case():
    def expired(*_):
        raise TimeoutError("declaration case exceeded four seconds")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(4)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def document(field, value, style, definition=None):
    definition = copy.deepcopy(FIELDS[field][2] if definition is None else definition)
    d = {
        "blueprints": {"leaf": {"nodes": {"L": {}}}},
        "network": {"nodes": {}},
    }
    supplied = {**definition, field: value}
    path = "network.nodes.P.params."
    if style == "direct":
        d["network"]["nodes"]["P"] = {"nodes": {"H": supplied}}
        return d, "network.nodes.P.nodes.H." + field
    d["network"]["nodes"]["P"] = {"blueprint": "unit"}
    if style == "blueprint-root":
        d["blueprints"]["unit"] = {"nodes": {"G": supplied}}
        return d, "blueprints.unit.nodes.G." + field
    if style == "blueprint":
        d["blueprints"]["unit"] = {"nodes": {"G": {"nodes": {"H": supplied}}}}
        return d, "blueprints.unit.nodes.G.nodes.H." + field
    if style == "flat":
        d["blueprints"]["unit"] = {"nodes": {"G": definition}}
        params = {"G." + field: value}
        path += "G." + field
    elif style in ("dotted", "node", "subtree"):
        d["blueprints"]["unit"] = {"nodes": {"G": {"nodes": {"H": definition}}}}
        params = {
            "dotted": {"G.nodes.H." + field: value},
            "node": {"G.nodes.H": supplied},
            "subtree": {"G.nodes": {"H": supplied}},
        }[style]
        path += "G.nodes.H." + field
    elif style == "nested-params":
        d["blueprints"]["unit"] = {"nodes": {"G": {"blueprint": "inner"}}}
        d["blueprints"]["inner"] = {"nodes": {"H": definition}}
        params = {"G.params": {"H." + field: value}}
        path += "G.params.H." + field
    else:
        assert style == "deep-params"
        d["blueprints"]["unit"] = {"nodes": {"G": {"blueprint": "inner"}}}
        d["blueprints"]["inner"] = {"nodes": {"H": {"blueprint": "deep"}}}
        d["blueprints"]["deep"] = {"nodes": {"J": definition}}
        params = {"G.params": {"H.params": {"J." + field: value}}}
        path += "G.params.H.params.J." + field
    d["network"]["nodes"]["P"]["params"] = params
    return d, path


def test_field_census_matches_schema():
    schema = json.loads(
        (Path(__file__).parents[2] / "ngraph/schemas/scenario.json").read_text()
    )
    assert set(FIELDS) == set(schema["$defs"]["nodeDefinition"]["properties"])


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("entry", ["yaml", "expansion"])
def test_each_field_uses_its_supplying_source(field, style, entry):
    bad, good, _ = FIELDS[field]
    control, _ = document(field, good, style)
    broken, path = document(field, bad, style)

    def load(d):
        return (
            Scenario.from_yaml(yaml.safe_dump(d, sort_keys=False)).network
            if entry == "yaml"
            else expand_network_dsl(d)
        )

    assert load(control).nodes
    original = copy.deepcopy(broken)
    with pytest.raises(ValueError) as error:
        load(broken)
    assert type(error.value) is ValueError
    assert str(error.value).startswith(path), str(error.value)
    assert repr(bad) in str(error.value), str(error.value)
    assert broken == original


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("field", ["disabled", "attrs", "risk_groups"])
@pytest.mark.parametrize("parent_kind", ["nodes", "blueprint"])
def test_common_fields_on_parents_use_the_same_rule(style, field, parent_kind):
    definition = {parent_kind: {"L": {}} if parent_kind == "nodes" else "leaf"}
    bad, good, _ = FIELDS[field]
    control, _ = document(field, good, style, definition)
    broken, path = document(field, bad, style, definition)
    assert expand_network_dsl(control).nodes
    with pytest.raises(ValueError) as error:
        expand_network_dsl(broken)
    assert str(error.value).startswith(path + ":"), str(error.value)
    assert repr(bad) in str(error.value)


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("template", ["{missing}", "{n[0]}", "{n.absent}", "{n:wrong}"])
def test_template_semantics_keep_the_same_source(style, template):
    broken, path = document("template", template, style)
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(broken, sort_keys=False))
    assert str(error.value).startswith(path + ":"), str(error.value)
    assert repr(template) in str(error.value)


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize(
    "field,bad,suffix,raw",
    [
        ("attrs", {"role": [float("inf")]}, ".role[0]", "inf"),
        ("attrs", {"role": b"edge"}, ".role", "b'edge'"),
        ("risk_groups", [3], "", "3"),
        ("risk_groups", [""], "", "''"),
        ("risk_groups", ["r[3-1]"], "", "'r[3-1]'"),
    ],
)
def test_collection_elements_keep_source_and_raw_value(style, field, bad, suffix, raw):
    broken, path = document(field, bad, style)
    with pytest.raises(ValueError) as error:
        expand_network_dsl(broken)
    assert str(error.value).startswith(path + suffix + ":"), str(error.value)
    assert raw in str(error.value)


def test_dotted_json_descendant_keeps_its_own_source():
    d, _ = document("attrs", {}, "dotted", {"attrs": {"old": "default"}})
    params = d["network"]["nodes"]["P"]["params"]
    params.clear()
    params["G.nodes.H.attrs.role"] = [float("inf")]
    with pytest.raises(ValueError) as error:
        expand_network_dsl(d)
    assert str(error.value).startswith(
        "network.nodes.P.params.G.nodes.H.attrs.role[0]:"
    )
    assert "inf" in str(error.value)


def test_inheritance_cannot_hide_invalid_child_fields():
    for field in ("disabled", "attrs", "risk_groups"):
        bad = FIELDS[field][0]
        d, path = document(field, bad, "blueprint")
        d["network"]["nodes"]["P"].update(
            disabled=True, attrs={"parent": "yes"}, risk_groups=["parent"]
        )
        with pytest.raises(ValueError) as error:
            expand_network_dsl(d)
        assert str(error.value).startswith(path + ":")
        assert repr(bad) in str(error.value)


def test_untouched_blueprint_field_keeps_blueprint_source():
    d, path = document("attrs", 3, "blueprint")
    d["network"]["nodes"]["P"]["params"] = {"G.nodes.H.disabled": True}
    with pytest.raises(ValueError) as error:
        expand_network_dsl(d)
    assert str(error.value).startswith(path + ":")
    assert "3" in str(error.value)


def test_valid_inheritance_preserves_values():
    d, _ = document("attrs", {"child": "yes", "shared": "child"}, "dotted")
    d["network"]["nodes"]["P"].update(
        disabled=True, attrs={"parent": "yes", "shared": "parent"}, risk_groups=["R"]
    )
    node = next(iter(expand_network_dsl(d).nodes.values()))
    assert node.disabled is True
    assert node.attrs == {"parent": "yes", "child": "yes", "shared": "child"}
    assert node.risk_groups == frozenset({"R"})


@pytest.mark.parametrize(
    "loader", [Scenario.from_yaml, load_scenario_yaml, ComponentsLibrary.from_yaml]
)
@pytest.mark.parametrize("character", ["\x00", "\x0c", "\x7f"])
def test_yaml_reader_initialization_has_the_same_refusal_boundary(loader, character):
    good = 'components: {c: {description: "ab"}}'
    bad = good.replace("ab", "a" + character + "b")
    loader(good)
    with pytest.raises(ValueError) as error:
        loader(bad)
    assert type(error.value) is ValueError
    assert isinstance(error.value.__cause__, yaml.reader.ReaderError)
    assert "invalid YAML" in str(error.value)
    assert repr(bad) in str(error.value)


def test_yaml_reader_is_disposed_only_after_successful_initialization(monkeypatch):
    from ngraph.utils import yaml_load

    disposed = []
    dispose = yaml_load._InputLoader.dispose

    def record(loader):
        disposed.append(loader)
        dispose(loader)

    monkeypatch.setattr(yaml_load._InputLoader, "dispose", record)
    with pytest.raises(ValueError):
        yaml_load._load_yaml("\x00", "scenario")
    assert disposed == []
    assert yaml_load._load_yaml("a: 1", "scenario") == {"a": 1}
    assert len(disposed) == 1
    with pytest.raises(ValueError):
        yaml_load._load_yaml("a: [", "scenario")
    assert len(disposed) == 2


@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("field", FIELDS)
def test_null_is_a_supplied_invalid_node_field(field, style):
    control, _ = document(field, FIELDS[field][1], style)
    broken, path = document(field, None, style)
    assert expand_network_dsl(control).nodes
    with pytest.raises(ValueError) as error:
        expand_network_dsl(broken)
    assert str(error.value).startswith(path + ":"), str(error.value)
    assert "None" in str(error.value)


@pytest.mark.parametrize("style", STYLES)
def test_nested_definition_shape_uses_its_supplying_source(style):
    broken, path = document("nodes", {"L": 3}, style)
    with pytest.raises(ValueError) as error:
        expand_network_dsl(broken)
    assert str(error.value).startswith(path + ".L:"), str(error.value)
    assert "3" in str(error.value)


@pytest.mark.parametrize("style", STYLES)
def test_unknown_field_keeps_source_and_value(style):
    broken, path = document("unknown", 3, style, {})
    with pytest.raises(ValueError) as error:
        expand_network_dsl(broken)
    assert str(error.value).startswith(path + ":"), str(error.value)
    assert "3" in str(error.value)
