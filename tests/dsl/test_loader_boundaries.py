"""Loader refusals preserve declaration context before producing domain objects."""

import signal

import pytest
import yaml
from yaml import YAMLError

from ngraph import Component, ComponentsLibrary, Scenario
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.utils.yaml_utils import declared


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *args: pytest.fail("case exceeded 3 seconds")
    )
    signal.alarm(3)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


@pytest.mark.parametrize("bad", [False, 0, [], "", True, 1, [1]])
def test_components_container_is_not_defaulted_by_truthiness(bad):
    source = yaml.safe_dump({"components": bad})
    with pytest.raises(ValueError) as error:
        ComponentsLibrary.from_yaml(source)
    assert str(error.value) == f"components = {bad!r}: expected a mapping"
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source)
    assert str(error.value).startswith(f"components = {bad!r}:")


@pytest.mark.parametrize("value", [None, {}])
def test_components_empty_controls(value):
    source = yaml.safe_dump({"components": value})
    assert ComponentsLibrary.from_yaml(source).components == {}
    assert Scenario.from_yaml(source).components_library.components == {}
    assert ComponentsLibrary.from_yaml("c: {ports: 2}").get("c") == Component(
        "c", ports=2
    )


@pytest.mark.parametrize("source", ["c: [", "c: {ports: ]", "c: !unknown x"])
@pytest.mark.parametrize(
    "loader,label",
    [
        (ComponentsLibrary.from_yaml, "components"),
        (Scenario.from_yaml, "scenario"),
        (load_scenario_yaml, "scenario"),
    ],
)
def test_yaml_syntax_refusal_has_one_class_and_original_cause(source, loader, label):
    with pytest.raises(ValueError) as error:
        loader(source)
    assert type(error.value) is ValueError
    assert isinstance(error.value.__cause__, YAMLError)
    assert (
        str(error.value)
        == f"{label} = {source!r}: invalid YAML: {error.value.__cause__}"
    )
    loader("{}")


@pytest.mark.parametrize("bad", [7, False, None, {}, []])
@pytest.mark.parametrize("loader", [load_scenario_yaml, Scenario.from_yaml])
@pytest.mark.parametrize("prefix", [[], ["first"]])
def test_risk_group_shape_names_its_position_and_value(bad, loader, prefix):
    with pytest.raises(ValueError) as error:
        loader(yaml.safe_dump({"risk_groups": prefix + [bad]}))
    assert (
        str(error.value)
        == f"risk_groups[{len(prefix)}] = {bad!r}: RiskGroup entry must be a string, dict with 'name' field, or dict with 'generate' field"
    )
    loader("risk_groups: [first, {name: second}]")


@pytest.mark.parametrize(
    "source,message",
    [
        ("[]", "components = []: expected a mapping"),
        ("false", "components = False: expected a mapping"),
        ("c: false", "components.c: expected a mapping, got False"),
        ("c: {children: []}", "components.c.children: expected a mapping, got []"),
        (
            "c: {children: {d: false}}",
            "components.c.children.d: expected a mapping, got False",
        ),
        (
            "c: {name: false}",
            "components.c.name: mismatched name; expected 'c', got False",
        ),
    ],
)
def test_standalone_component_shape_refusals_keep_the_path_and_value(source, message):
    with pytest.raises(ValueError) as error:
        ComponentsLibrary.from_yaml(source)
    assert str(error.value) == message
    assert (
        ComponentsLibrary.from_yaml("c: {children: {d: {}}}")
        .get("c")
        .children["d"]
        .name
        == "d"
    )


@pytest.mark.parametrize(
    "template,kind",
    [
        ("{0}", IndexError),
        ("{n.foo}", AttributeError),
        ("{x}", KeyError),
        ("{", ValueError),
    ],
)
def test_node_template_is_checked_before_building_nodes(template, kind):
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(
            yaml.safe_dump(
                {"network": {"nodes": {"G": {"count": 2, "template": template}}}}
            )
        )
    cause = error.value.__cause__
    assert isinstance(cause, kind)
    assert (
        str(error.value)
        == f"network.nodes.G.template: invalid template {template!r}: {cause}"
    )
    assert list(
        Scenario.from_yaml(
            "network: {nodes: {G: {count: 2, template: 'n-{n}'}}}"
        ).network.nodes
    ) == ["G/n-1", "G/n-2"]


def expanding(kind, expansion, path="${x}"):
    row = {"expand": expansion}
    data = {"network": {"nodes": {"A": {}, "B": {}}}}
    if kind == "demand":
        row.update(source=path, target="B", id="d-${x}")
        data["demands"] = {"d": [row]}
        label = "demands.d[0]"
    elif kind == "node":
        row["path"] = path
        data["network"]["node_rules"] = [row]
        label = "network.node_rules[0]"
    else:
        row.update(source=path, target="B")
        data["network"]["link_rules"] = [row]
        label = "network.link_rules[0]"
    return data, row, label


@pytest.mark.parametrize("kind", ["demand", "node", "link"])
@pytest.mark.parametrize("failure", ["variable", "zip", "size"])
def test_expansion_refusals_are_labelled_before_lazy_substitution(kind, failure):
    expansion = {"vars": {"x": ["A", "B"]}}
    path = "${zz}" if failure == "variable" else "${x}"
    if failure == "zip":
        expansion = {"mode": "zip", "vars": {"x": ["A"], "y": [1, 2]}}
    elif failure == "size":
        expansion = {"vars": {"x": list(range(101)), "y": list(range(101))}}
    data, row, label = expanding(kind, expansion, path)
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False))
    message = str(error.value)
    assert message.startswith(f"{label} = {row!r}: ")
    assert error.value.__cause__ is not None
    if failure == "variable":
        assert isinstance(error.value.__cause__, KeyError)
        assert "$zz" in message
    elif failure == "zip":
        assert (
            "zip expansion requires equal-length lists; got lengths [1, 2]" in message
        )
    else:
        assert "10201 items (limit: 10000)" in message
    control, _, _ = expanding(kind, {"vars": {"x": ["A", "B"]}})
    scenario = Scenario.from_yaml(yaml.safe_dump(control))
    if kind == "demand":
        assert [d.id for d in scenario.demand_sets["d"].demands] == ["d-A", "d-B"]


def test_expanded_demand_identity_refuses_the_value():
    data, _, _ = expanding("demand", {"vars": {"x": [7]}})
    data["demands"]["d"][0]["source"] = "A"
    data["demands"]["d"][0]["id"] = "${x}"
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert str(error.value) == "demands.d[0].id: expected nonempty string, got 7"
    data["demands"]["d"][0]["id"] = "d-${x}"
    assert (
        Scenario.from_yaml(yaml.safe_dump(data)).demand_sets["d"].demands[0].id == "d-7"
    )


@pytest.mark.parametrize("kind", [TypeError, KeyError])
def test_declared_converts_lower_level_type_and_key_errors(kind):
    failure = kind("bad raw input")

    def refuse():
        raise failure

    with pytest.raises(ValueError) as error:
        declared("network.links[2] (A->B)", refuse)
    assert str(error.value) == f"network.links[2] (A->B): {failure}"
    assert error.value.__cause__ is failure
    assert declared("network.links[2] (A->B)", lambda: 7) == 7


@pytest.mark.parametrize("kind", [TypeError, KeyError])
def test_scenario_fallback_converts_type_and_key_errors(monkeypatch, kind):
    import ngraph.dsl.loader as loader

    original = loader.load_scenario_yaml
    failure = kind("bad source")

    def refuse(source):
        raise failure

    monkeypatch.setattr(loader, "load_scenario_yaml", refuse)
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml("{}")
    assert str(error.value) == f"scenario = '{{}}': {failure}"
    assert error.value.__cause__ is failure
    monkeypatch.setattr(loader, "load_scenario_yaml", original)
    assert Scenario.from_yaml("{}").network.nodes == {}


@pytest.mark.parametrize("key,raw", [("attrs", {"x": float("inf")}), ("path", "[")])
def test_node_rule_properties_have_consistent_labels(key, raw):
    data = {"network": {"nodes": {"A": {}}, "node_rules": [{key: raw}]}}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    expected = (
        "network.node_rules[0].attrs.x: expected finite JSON data, got float = inf"
        if key == "attrs"
        else "network.node_rules[0].path: invalid pattern '[': unterminated character set at position 0"
    )
    assert str(error.value) == expected
    data["network"]["node_rules"][0][key] = {"x": 1} if key == "attrs" else "A"
    assert "A" in Scenario.from_yaml(yaml.safe_dump(data)).network.nodes


@pytest.mark.parametrize("name", ["g", "g[1-2]"])
def test_membership_errors_keep_position_across_generate_and_bracket_entries(name):
    data = {
        "risk_groups": [
            {"generate": {"scope": "node", "group_by": "role", "name": "r-${value}"}},
            {"name": name, "membership": {"scope": "node", "path": "["}},
        ]
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value)
        == "risk_groups[1].membership.path: invalid pattern '[': unterminated character set at position 0"
    )
    data["risk_groups"][1]["membership"]["path"] = ".*"
    assert (
        "g" in Scenario.from_yaml(yaml.safe_dump(data)).network.risk_groups
        if name == "g"
        else "g1" in Scenario.from_yaml(yaml.safe_dump(data)).network.risk_groups
    )


def test_membership_match_value_error_has_the_complete_path():
    data = {
        "risk_groups": [
            "first",
            {
                "name": "g",
                "membership": {
                    "scope": "node",
                    "match": {
                        "conditions": [{"attr": "x", "op": "==", "value": float("inf")}]
                    },
                },
            },
        ]
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value)
        == "risk_groups[1].membership.match.conditions[0].value: expected finite JSON data, got float = inf"
    )
    data["risk_groups"][1]["membership"]["match"]["conditions"][0]["value"] = 1
    assert "g" in Scenario.from_yaml(yaml.safe_dump(data)).network.risk_groups


@pytest.mark.parametrize(
    "preset,model",
    [
        (None, None),
        (None, {"routing": {"type": "shortest_paths"}}),
        ("SHORTEST_PATHS_ECMP", None),
    ],
)
def test_maxflow_nulls_do_not_conflict_with_the_other_representation(preset, model):
    row = {
        "type": "MaxFlow",
        "source": "A",
        "target": "B",
        "preset": preset,
        "model": model,
    }
    explicit = Scenario.from_yaml(yaml.safe_dump({"workflow": [row]})).workflow[0]
    omitted = Scenario.from_yaml(
        yaml.safe_dump({"workflow": [{k: v for k, v in row.items() if v is not None}]})
    ).workflow[0]
    assert explicit.preset == omitted.preset
    assert explicit.model == omitted.model
    # Two actual declarations remain exclusive.
    row.update(
        preset="SHORTEST_PATHS_ECMP", model={"routing": {"type": "shortest_paths"}}
    )
    from tests.dsl.test_input_boundaries import VALIDATOR

    assert list(VALIDATOR.iter_errors({"workflow": [row]}))
    with pytest.raises(ValueError):
        Scenario.from_yaml(yaml.safe_dump({"workflow": [row]}))


def test_unknown_variable_in_a_link_entry_keeps_the_entry_and_cause():
    row = {"source": "${zz}", "target": "B", "expand": {"vars": {"x": ["A"]}}}
    data = {"network": {"nodes": {"A": {}, "B": {}}, "links": [row]}}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value)
        == "network.links[0] (${zz}->B): \"Variable '$zz' not found in expand.vars\""
    )
    assert isinstance(error.value.__cause__, KeyError)
    row["source"] = "${x}"
    assert list(Scenario.from_yaml(yaml.safe_dump(data)).network.links) == ["A|B|0"]


def test_component_unknown_fields_include_the_complete_declaration():
    with pytest.raises(ValueError) as error:
        ComponentsLibrary.from_yaml("p: {children: {c: {unknown: 7}}}")
    assert (
        str(error.value)
        == "components.p.children.c = {'unknown': 7}: unrecognized key(s): unknown. Put custom data under 'attrs'."
    )
    assert ComponentsLibrary.from_yaml("p: {children: {c: {attrs: {unknown: 7}}}}").get(
        "p"
    ).children["c"].attrs == {"unknown": 7}


def test_nested_risk_group_properties_keep_the_unfiltered_entry_position():
    data = {
        "risk_groups": [
            {"generate": {"scope": "node", "group_by": "role", "name": "r-${value}"}},
            {"name": "p", "children": [{"name": "c", "attrs": {"x": float("inf")}}]},
        ]
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value)
        == "risk_groups[1].children[0].attrs.x: expected finite JSON data, got float = inf"
    )
    data["risk_groups"][1]["children"][0]["attrs"]["x"] = 1
    assert Scenario.from_yaml(yaml.safe_dump(data)).network.risk_groups["p"].children[
        0
    ].attrs == {"x": 1}


@pytest.mark.parametrize("command", ["run", "inspect"])
@pytest.mark.parametrize("template", ["{0}", "{n.foo}"])
def test_cli_template_failure_exits_one_with_the_field_and_value(
    tmp_path, capsys, command, template
):
    from ngraph import cli

    source = tmp_path / "scenario.yaml"
    source.write_text(
        yaml.safe_dump(
            {"network": {"nodes": {"G": {"count": 1, "template": template}}}}
        )
    )
    with pytest.raises(SystemExit) as error:
        cli.main([command, str(source)])
    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert f"network.nodes.G.template: invalid template {template!r}:" in stderr


def test_link_entry_count_is_checked_once_before_creating_parallel_links(monkeypatch):
    import ngraph.dsl.blueprints.expand as expansion

    original = expansion.integer
    counts = []

    def checked(value, label, **kwargs):
        if label.endswith(".count"):
            counts.append(label)
        return original(value, label, **kwargs)

    monkeypatch.setattr(expansion, "integer", checked)
    scenario = Scenario.from_yaml(
        "network: {nodes: {A: {}, B: {}}, links: [{source: A, target: B, count: 2}]}"
    )
    assert len(scenario.network.links) == 2
    assert counts == ["network.links[0] (A->B).count"]


@pytest.mark.parametrize(
    "membership,message",
    [
        (
            {"scope": "node", "match": {"conditions": []}},
            "risk_groups[1].membership.match.conditions: expected at least one condition, got []",
        ),
        (
            {"scope": "node"},
            "risk_groups[1].membership: expected at least 'path' or 'match', got {'scope': 'node'}",
        ),
    ],
)
def test_membership_shape_errors_keep_the_field_and_value(membership, message):
    data = {"risk_groups": ["first", {"name": "g", "membership": membership}]}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert str(error.value) == message
    data["risk_groups"][1]["membership"] = {"scope": "node", "path": ".*"}
    assert "g" in Scenario.from_yaml(yaml.safe_dump(data)).network.risk_groups


@pytest.mark.parametrize("kind", ["demand", "node", "link"])
@pytest.mark.parametrize("expand", [None, {"vars": {}}])
def test_unexpanded_and_empty_expansions_preserve_the_declaration(kind, expand):
    data, row, _ = expanding(kind, {"vars": {}}, "A")
    if expand is None:
        del row["expand"]
    if kind == "demand":
        row["id"] = "d"
    else:
        row["attrs"] = {"checked": True}
    data["network"]["links"] = [{"source": "A", "target": "B"}]
    scenario = Scenario.from_yaml(yaml.safe_dump(data))
    if kind == "demand":
        assert [d.id for d in scenario.demand_sets["d"].demands] == ["d"]
        assert scenario.demand_sets["d"].demands[0].expand_leaf_index is None
    elif kind == "node":
        assert scenario.network.nodes["A"].attrs == {"checked": True}
    else:
        assert scenario.network.links["A|B|0"].attrs == {"checked": True}


@pytest.mark.parametrize(
    "child,message",
    [
        (
            7,
            "risk_groups[1].children[0]: RiskGroup entry must be a string or dict, got 7",
        ),
        (
            {},
            "risk_groups[1].children[0]: RiskGroup entry missing 'name' field, got {}",
        ),
        (
            {"generate": {}},
            "risk_groups[1].children[0]: 'generate' blocks not allowed in children, got {'generate': {}}",
        ),
        (
            {"name": "c", "disabled": False},
            "risk_groups[1].children[0] = {'name': 'c', 'disabled': False}: 'disabled' not allowed in children; define the group at top level and reference it as a child",
        ),
        (
            {"name": "c", "membership": {}},
            "risk_groups[1].children[0] = {'name': 'c', 'membership': {}}: 'membership' rules not allowed in children; define the group at top level and reference it as a child",
        ),
    ],
)
def test_risk_group_builder_shape_siblings_keep_nested_paths(child, message):
    from ngraph.model.risk import build_risk_groups

    with pytest.raises(ValueError) as error:
        build_risk_groups(["first", {"name": "p", "children": [child]}])
    assert str(error.value) == message
    groups, generated = build_risk_groups(["first", {"name": "p", "children": ["c"]}])
    assert groups[1].children[0].name == "c" and generated == []
