"""Every declaration refuses at its source, retaining its supplied value."""

import copy
import signal

import pytest
import yaml
from jsonschema import ValidationError

from ngraph import ComponentsLibrary, Scenario
from ngraph.dsl.loader import load_scenario_yaml


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *args: pytest.fail("case exceeded 4 seconds")
    )
    signal.alarm(4)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


def source(data):
    return yaml.safe_dump(data, sort_keys=False)


def template_declaration(template, depth, blueprint, override=False):
    # Build the nesting from the leaf, keeping the declaration path independently.
    nodes = {"G": {"count": 2, "template": template}}
    parts = ["G"]
    for i in range(depth):
        nodes = {f"parent{i}": {"nodes": nodes}}
        parts.insert(0, f"parent{i}")
    path = ".nodes.".join(parts)
    if blueprint:
        doc = {
            "blueprints": {"unit": {"nodes": nodes}},
            "network": {"nodes": {"p": {"blueprint": "unit"}}},
        }
        location = "blueprints.unit.nodes." + path + ".template"
        if override:
            assert depth == 0
            doc["blueprints"]["unit"]["nodes"]["G"]["template"] = "n-{n}"
            doc["network"]["nodes"]["p"]["params"] = {"G.template": template}
            location = "network.nodes.p.params.G.template"
    else:
        doc = {"network": {"nodes": nodes}}
        location = "network.nodes." + path + ".template"
    return doc, location


@pytest.mark.parametrize(
    "template", ["{", "{missing}", "{}", "{n.missing}", "{n[0]}", "{n.real[0]}"]
)
@pytest.mark.parametrize(
    "depth,blueprint,override",
    [(d, b, False) for d in range(3) for b in (False, True)] + [(0, True, True)],
)
def test_every_format_failure_names_the_actual_template(
    template, depth, blueprint, override
):
    data, path = template_declaration(template, depth, blueprint, override)
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source(data))
    assert type(error.value) is ValueError
    assert str(error.value).startswith(f"{path}: invalid template {template!r}:")
    assert error.value.__cause__ is not None
    good, _ = template_declaration("n-{n}", depth, blueprint, override)
    assert len(Scenario.from_yaml(source(good)).network.nodes) == 2


# Every kind of declared object, not one row per previously reported failure.
ENTRIES = {
    "network": ({"network": 0}, {"network": {}}),
    "network.nodes": ({"network": {"nodes": 0}}, {"network": {"nodes": {}}}),
    "network.nodes.A": (
        {"network": {"nodes": {"A": 0}}},
        {"network": {"nodes": {"A": {}}}},
    ),
    "network.links[0]": (
        {"network": {"links": [0]}},
        {
            "network": {
                "nodes": {"A": {}, "B": {}},
                "links": [{"source": "A", "target": "B"}],
            }
        },
    ),
    "network.node_rules[0]": (
        {"network": {"node_rules": [0]}},
        {"network": {"node_rules": [{"path": ".*", "disabled": False}]}},
    ),
    "network.link_rules[0]": (
        {"network": {"link_rules": [0]}},
        {"network": {"link_rules": [{"source": ".*", "target": ".*", "cost": 1}]}},
    ),
    "blueprints.unit": ({"blueprints": {"unit": 0}}, {"blueprints": {"unit": {}}}),
    "components.c": ({"components": {"c": 0}}, {"components": {"c": {}}}),
    "components.p.children.c": (
        {"components": {"p": {"children": {"c": 0}}}},
        {"components": {"p": {"children": {"c": {}}}}},
    ),
    "risk_groups[0]": ({"risk_groups": [0]}, {"risk_groups": ["R"]}),
    "risk_groups[0].children[0]": (
        {"risk_groups": [{"name": "R", "children": [0]}]},
        {"risk_groups": [{"name": "R", "children": ["child"]}]},
    ),
    "risk_groups[0].generate": (
        {"risk_groups": [{"generate": 0}]},
        {
            "risk_groups": [
                {
                    "generate": {
                        "scope": "node",
                        "group_by": "role",
                        "name": "r-${value}",
                    }
                }
            ]
        },
    ),
    "risk_groups[0].membership": (
        {"risk_groups": [{"name": "R", "membership": 0}]},
        {"risk_groups": [{"name": "R", "membership": {"scope": "node", "path": ".*"}}]},
    ),
    "workflow[0]": ({"workflow": [0]}, {"workflow": [{"type": "BuildGraph"}]}),
    "failures.fp": (
        {"failures": {"fp": 0}},
        {"failures": {"fp": {"modes": [{"weight": 1, "rules": []}]}}},
    ),
    "failures.fp.modes[0]": (
        {"failures": {"fp": {"modes": [0]}}},
        {"failures": {"fp": {"modes": [{"weight": 1, "rules": []}]}}},
    ),
    "failures.fp.modes[0].rules[0]": (
        {"failures": {"fp": {"modes": [{"weight": 1, "rules": [0]}]}}},
        {
            "failures": {
                "fp": {
                    "modes": [
                        {"weight": 1, "rules": [{"scope": "node", "mode": "all"}]}
                    ]
                }
            }
        },
    ),
    "demands.d[0]": (
        {"demands": {"d": [0]}},
        {"demands": {"d": [{"source": "A", "target": "B", "volume": 1}]}},
    ),
    "units": ({"units": 0}, {"units": {}}),
    "routing": ({"routing": 0}, {"routing": {"igp_domain": ".*", "bgp_edge": ".*"}}),
    "wcmp_controller": ({"wcmp_controller": 0}, {"wcmp_controller": {}}),
    "routes.r": (
        {"routes": {"r": 0}},
        {"routes": {"r": {"head": "A", "nodes": ["A", "B"]}}},
    ),
    "supports.s": (
        {"supports": {"s": 0}},
        {"supports": {"s": {"edges": [{"link": "A|B|0", "direction": "forward"}]}}},
    ),
    "weights.w": (
        {"weights": {"w": 0}},
        {
            "weights": {
                "w": {
                    "entries": [
                        {"edge": {"link": "A|B|0", "direction": "forward"}, "value": 1}
                    ]
                }
            }
        },
    ),
    "forwarding_groups.f": (
        {"forwarding_groups": {"f": 0}},
        {
            "forwarding_groups": {
                "f": {
                    "router": "A",
                    "groups": [
                        {
                            "children": [
                                {"edge": {"link": "A|B|0", "direction": "forward"}}
                            ]
                        }
                    ],
                }
            }
        },
    ),
}


# Every object kind in the closed schema has a refusal and a valid control.
SCHEMA_ENTRIES = {
    "riskGroupChild": "risk_groups[0].children[0]",
    "nodeDefinition": "network.nodes.A",
    "linkDefinition": "network.links[0]",
    "component": "components.c",
    "supportSpec": "supports.s",
    "weightSpec": "weights.w",
    "routeSpec": "routes.r",
}


def add_schema_entry(definition, path, base, good):
    valid = copy.deepcopy(base)
    node = valid
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = good
    invalid = copy.deepcopy(valid)
    node = invalid
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = 0
    label = "".join(f"[{v}]" if isinstance(v, int) else "." + v for v in path).lstrip(
        "."
    )
    ENTRIES[label] = invalid, valid
    SCHEMA_ENTRIES[definition] = label


_base = {
    "workflow": [
        {
            "type": "MaxFlow",
            "source": {"path": "A"},
            "target": "B",
            "model": {"routing": {"type": "shortest_paths"}},
        }
    ]
}
add_schema_entry(
    "model", ["workflow", 0, "model"], _base, {"routing": {"type": "shortest_paths"}}
)
add_schema_entry(
    "routingModel",
    ["workflow", 0, "model", "routing"],
    _base,
    {"type": "shortest_paths"},
)
add_schema_entry("outputs", ["workflow", 0, "outputs"], _base, {})
add_schema_entry("nodeSelector", ["workflow", 0, "source"], _base, {"path": "A"})
SCHEMA_ENTRIES["selectorOrString"] = SCHEMA_ENTRIES["nodeSelector"]
_base["workflow"][0]["source"]["match"] = {
    "conditions": [{"attr": "role", "op": "exists"}]
}
add_schema_entry(
    "matchSpec",
    ["workflow", 0, "source", "match"],
    _base,
    {"conditions": [{"attr": "role", "op": "exists"}]},
)
add_schema_entry(
    "condition",
    ["workflow", 0, "source", "match", "conditions", 0],
    _base,
    {"attr": "role", "op": "exists"},
)
_base["workflow"][0]["model"]["routing"] = {
    "type": "distributed_te",
    "tunnel_count": {"per_head": 1},
}
add_schema_entry(
    "tunnelCount",
    ["workflow", 0, "model", "routing", "tunnel_count"],
    _base,
    {"per_head": 1},
)
add_schema_entry(
    "costCeiling",
    ["workflow", 0, "model", "routing", "cost_ceiling"],
    _base,
    {"type": "absolute", "value": 2},
)
_base = {"demands": {"d": [{"source": "A", "target": "B", "volume": 1}]}}
add_schema_entry(
    "expandBlock", ["demands", "d", 0, "expand"], _base, {"vars": {"x": [1]}}
)
_base = {
    "routes": {"r": {"head": "A", "edges": [{"link": "A|B|0", "direction": "forward"}]}}
}
add_schema_entry(
    "directedLink",
    ["routes", "r", "edges", 0],
    _base,
    {"link": "A|B|0", "direction": "forward"},
)
_base = {
    "routing": {"igp_domain": ".*", "bgp_edge": ".*"},
    "wcmp_controller": {},
    "forwarding_groups": {
        "f": {
            "router": "A",
            "groups": [
                {"children": [{"edge": {"link": "A|B|0", "direction": "forward"}}]}
            ],
        }
    },
}
add_schema_entry(
    "groupChild",
    ["forwarding_groups", "f", "groups", 0, "children", 0],
    _base,
    {"edge": {"link": "A|B|0", "direction": "forward"}},
)


def test_every_closed_schema_declaration_kind_has_a_refusal_and_valid_control():
    import json
    from importlib import resources

    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
    )
    # Presets are scalar enum fields, not declared objects.
    assert set(schema["$defs"]) == set(SCHEMA_ENTRIES) | {"preset"}
    assert set(SCHEMA_ENTRIES.values()) <= set(ENTRIES)


for _key in ("routing", "wcmp_controller", "forwarding_groups.f"):
    ENTRIES[_key][1].setdefault("routing", {"igp_domain": ".*", "bgp_edge": ".*"})
    ENTRIES[_key][1].setdefault("wcmp_controller", {})


@pytest.mark.parametrize("path", ENTRIES)
@pytest.mark.parametrize("loader", [Scenario.from_yaml, load_scenario_yaml])
def test_every_declared_entry_has_a_position_and_raw_value(path, loader):
    bad, good = ENTRIES[path]
    with pytest.raises(ValueError) as error:
        loader(source(bad))
    assert type(error.value) is ValueError
    assert str(error.value).startswith(path), str(error.value)
    assert "0" in str(error.value)
    loader(source(good))


@pytest.mark.parametrize("path", [p for p in ENTRIES if p.startswith("components.")])
def test_standalone_component_entries_follow_the_same_rule(path):
    bad, good = ENTRIES[path]
    with pytest.raises(ValueError) as error:
        ComponentsLibrary.from_yaml(source(bad))
    assert type(error.value) is ValueError
    assert str(error.value).startswith(path) and "0" in str(error.value)
    ComponentsLibrary.from_yaml(source(good))


@pytest.mark.parametrize("position", [0, 2])
@pytest.mark.parametrize("bad", [[], {}, [1]])
def test_generation_retains_its_source_position_and_resolved_raw_value(position, bad):
    data = {
        "network": {"nodes": {"A": {"attrs": {"role": bad}}}},
        "risk_groups": [f"prefix{i}" for i in range(position)]
        + [{"generate": {"scope": "node", "group_by": "role", "name": "r-${value}"}}],
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source(data))
    assert str(error.value).startswith(f"risk_groups[{position}].generate.group_by:")
    assert f"got {bad!r}" in str(error.value)
    good = copy.deepcopy(data)
    good["network"]["nodes"]["A"]["attrs"]["role"] = "leaf"
    assert "r-leaf" in Scenario.from_yaml(source(good)).network.risk_groups


@pytest.mark.parametrize(
    "kind", ["workflow", "explicit-group", "generated-group", "generated-collision"]
)
def test_duplicate_names_retain_the_offending_source_position_and_value(kind):
    if kind == "workflow":
        data = {"workflow": [{"type": "BuildGraph", "name": "same"}] * 2}
        path, raw = "workflow[1] (name 'same').name", "same"
        good = {
            "workflow": [
                {"type": "BuildGraph", "name": "first"},
                {"type": "BuildGraph", "name": "second"},
            ]
        }
    elif kind == "explicit-group":
        data = {"risk_groups": ["same", "same"]}
        path, raw = "risk_groups[1].name", "same"
        good = {"risk_groups": ["first", "second"]}
    else:
        data = {
            "network": {
                "nodes": {
                    "A": {"attrs": {"role": 1}},
                    "B": {
                        "attrs": {"role": "1" if kind == "generated-collision" else 2}
                    },
                }
            },
            "risk_groups": ([] if kind == "generated-collision" else ["r-1"])
            + [
                {
                    "generate": {
                        "scope": "node",
                        "group_by": "role",
                        "name": "r-${value}",
                    }
                }
            ],
        }
        path = f"risk_groups[{len(data['risk_groups']) - 1}].generate.name"
        raw = "r-${value}"
        good = copy.deepcopy(data)
        good["network"]["nodes"]["B"]["attrs"]["role"] = 2
        good["risk_groups"] = [good["risk_groups"][-1]]
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source(data))
    assert type(error.value) is ValueError
    assert str(error.value).startswith(path) and repr(raw) in str(error.value)
    Scenario.from_yaml(source(good))


@pytest.mark.parametrize("command", ["run", "inspect"])
@pytest.mark.parametrize("case", ["template", "generation", "duplicate"])
def test_cli_refusals_keep_the_declaration_path_and_value(
    tmp_path, capsys, command, case
):
    from ngraph.cli import main

    if case == "template":
        data, path = template_declaration("{n[0]}", 1, True)
        text, shown = source(data), repr("{n[0]}")
    elif case == "generation":
        text = "network: {nodes: {A: {attrs: {role: []}}}}\nrisk_groups: [{generate: {scope: node, group_by: role, name: 'r-${value}'}}]"
        path, shown = "risk_groups[0].generate.group_by", "[]"
    else:
        text = (
            "workflow: [{type: BuildGraph, name: same}, {type: BuildGraph, name: same}]"
        )
        path, shown = "workflow[1] (name 'same').name", "'same'"
    filename = tmp_path / "scenario.yml"
    filename.write_text(text)
    with pytest.raises(SystemExit) as error:
        main([command, str(filename)])
    assert error.value.code == 1
    stderr = capsys.readouterr().err
    assert path in stderr and shown in stderr


def test_unknown_top_level_key_has_the_documented_exception_and_cause():
    from pathlib import Path

    with pytest.raises(ValueError) as error:
        load_scenario_yaml("unknown: 7")
    assert type(error.value) is ValueError
    assert isinstance(error.value.__cause__, ValidationError)
    assert str(error.value).startswith("scenario = {'unknown': 7}:")
    document = Path(__file__).resolve().parents[2] / "docs/reference/dsl.md"
    assert (
        "with a `ValueError` whose cause is the schema's `ValidationError`"
        in document.read_text()
    )
    assert "with `jsonschema.ValidationError`" not in document.read_text()


@pytest.mark.parametrize("blueprint", [False, True])
def test_bracket_expansion_retains_the_unexpanded_template_declaration(blueprint):
    data, path = template_declaration("{n[0]}", 0, blueprint)
    nodes = (
        data["blueprints"]["unit"]["nodes"] if blueprint else data["network"]["nodes"]
    )
    nodes["G[1-2]"] = nodes.pop("G")
    path = path.replace(".G.template", ".G[1-2].template")
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source(data))
    assert str(error.value).startswith(path + ": invalid template '{n[0]}':")
    nodes["G[1-2]"]["template"] = "n-{n}"
    assert len(Scenario.from_yaml(source(data)).network.nodes) == 4


@pytest.mark.parametrize("raw", ["", " ", None])
def test_duplicate_automatic_step_name_retains_the_supplied_spelling(raw):
    duplicate = {"type": "BuildGraph"}
    if raw is not None:
        duplicate["name"] = raw
    data = {"workflow": [{"type": "BuildGraph", "name": "BuildGraph_1"}, duplicate]}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(source(data))
    assert str(error.value) == (
        f"workflow[1] (name 'BuildGraph_1').name = {raw!r}: Duplicate workflow step name 'BuildGraph_1'. "
        f"Each step must have a unique name; got {raw!r}."
    )
    data["workflow"][0]["name"] = "distinct"
    assert len(Scenario.from_yaml(source(data)).workflow) == 2
