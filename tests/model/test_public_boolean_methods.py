"""Public read methods check booleans before using them or returning early."""

import numpy as np
import pytest

from ngraph import Component, ComponentsLibrary, Link, Network, NetworkExplorer, Node


@pytest.mark.parametrize("raw", ["false", 0, None, [], {}])
@pytest.mark.parametrize(
    "field",
    [
        "get_bom.include_disabled",
        "print_tree.skip_leaves",
        "print_tree.detailed",
        "print_tree.include_disabled",
        "find_links.any_direction",
    ],
)
@pytest.mark.parametrize("built", [False, True])
def test_public_read_flags_refuse_truthiness(raw, field, built):
    n = Network(
        nodes={
            s: Node(s, disabled=s == "b", attrs={"hardware": {"component": "p"}})
            for s in ("a", "b")
        }
    )
    n.add_link(Link("a", "b", 1))
    lib = ComponentsLibrary({"p": Component("p")})
    e = (
        NetworkExplorer.explore_network(n, lib, strict_validation=False)
        if built
        else NetworkExplorer(n, lib)
    )
    method, argument = field.split(".")
    with pytest.raises(ValueError, match=field):
        if method == "find_links":
            n.find_links(source_regex="b", **{argument: raw})
        else:
            getattr(e, method)(**{argument: raw})


@pytest.mark.parametrize("raw", [True, False, np.bool_(True), np.bool_(False)])
def test_legal_public_flags_keep_the_enabled_and_reverse_views(raw, capsys):
    n = Network(
        nodes={
            s: Node(s, disabled=s == "b", attrs={"hardware": {"component": "p"}})
            for s in ("a", "b")
        }
    )
    n.add_link(Link("a", "b", 1))
    lib = ComponentsLibrary({"p": Component("p")})
    e = NetworkExplorer.explore_network(n, lib, strict_validation=False)
    assert e.get_bom(include_disabled=raw) == {"p": 2.0 if bool(raw) else 1.0}
    assert n.find_links(source_regex="^b$", any_direction=raw) == (
        list(n.links.values()) if bool(raw) else []
    )
    e.print_tree(skip_leaves=raw, detailed=raw, include_disabled=raw)
    assert "Nodes=" in capsys.readouterr().out


@pytest.mark.parametrize("raw", ["false", 0, None, [], {}, 10**309, float("inf")])
@pytest.mark.parametrize("method", ["disable_risk_group", "enable_risk_group"])
@pytest.mark.parametrize("known", [False, True])
def test_risk_edit_flags_refuse_before_mutation_or_unknown_return(raw, method, known):
    n = risk_network(disabled=method == "enable_risk_group")
    before = (dict(n.nodes), dict(n.links), dict(n.risk_groups))
    with pytest.raises(ValueError, match=method + r"\.recursive"):
        getattr(n, method)("parent" if known else "unknown", recursive=raw)
    assert (n.nodes, n.links, n.risk_groups) == before


def risk_network(disabled):
    from ngraph import RiskGroup

    n = Network(
        nodes={
            "p": Node("p", disabled=disabled, risk_groups=["parent"]),
            "c": Node("c", disabled=disabled, risk_groups=["child"]),
        },
        risk_groups={"parent": RiskGroup("parent", children=[RiskGroup("child")])},
    )
    n.add_link(Link("p", "c", 1, disabled=disabled, risk_groups=["child"]))
    return n


@pytest.mark.parametrize("raw", [True, False, np.bool_(True), np.bool_(False)])
@pytest.mark.parametrize("method", ["disable_risk_group", "enable_risk_group"])
def test_boolean_risk_edits_preserve_direct_and_recursive_members(raw, method):
    enabling = method == "enable_risk_group"
    n = risk_network(disabled=enabling)
    getattr(n, method)("parent", recursive=raw)
    assert n.nodes["p"].disabled is (not enabling)
    assert n.nodes["c"].disabled is ((not enabling) if bool(raw) else enabling)
    assert [link.disabled for link in n.links.values()] == [
        (not enabling) if bool(raw) else enabling
    ]
    before = (dict(n.nodes), dict(n.links))
    getattr(n, method)("unknown", recursive=raw)
    assert (n.nodes, n.links) == before


@pytest.mark.parametrize("raw", ["false", 0, None, [], {}, 10**309, float("inf")])
@pytest.mark.parametrize("populated", [False, True])
def test_component_export_and_library_merge_refuse_nonboolean_flags(raw, populated):
    child = Component("child")
    comp = Component("p", children={"child": child} if populated else {})
    with pytest.raises(ValueError, match=r"Component.as_dict.include_children"):
        comp.as_dict(include_children=raw)
    lib = ComponentsLibrary({"p": comp} if populated else {})
    other = ComponentsLibrary({"p": Component("p", capex=3)} if populated else {})
    before = dict(lib.components)
    with pytest.raises(ValueError, match=r"ComponentsLibrary.merge.override"):
        lib.merge(other, override=raw)
    assert lib.components == before


@pytest.mark.parametrize("raw", [True, False, np.bool_(True), np.bool_(False)])
def test_boolean_component_export_and_merge_keep_both_choices(raw):
    child = Component("child")
    comp = Component("p", children={"child": child})
    expected = {
        "name": "p",
        "component_type": "generic",
        "description": "",
        "capex": 0.0,
        "power_watts": 0.0,
        "power_watts_max": 0.0,
        "capacity": 0.0,
        "ports": 0,
        "count": 1,
        "attrs": {},
    }
    if bool(raw):
        expected["children"] = {"child": {**expected, "name": "child", "children": {}}}
    assert comp.as_dict(include_children=raw) == expected
    replacement = Component("p", capex=3)
    new = Component("new")
    lib = ComponentsLibrary({"p": comp})
    other = ComponentsLibrary({"p": replacement, "new": new})
    assert lib.merge(other, override=raw) is lib
    assert lib.components == {"p": replacement if bool(raw) else comp, "new": new}
    assert other.components == {"p": replacement, "new": new}


@pytest.mark.parametrize("raw", ["false", 0, None, [], {}, 10**309, float("inf")])
def test_exported_selector_and_profiler_flags_refuse_truthiness(raw):
    from ngraph.model.selectors import Selector, parse_match_spec, select_nodes
    from ngraph.profiling import PerformanceProfiler

    with pytest.raises(ValueError, match=r"parse_match_spec.require_conditions"):
        parse_match_spec({}, require_conditions=raw)
    # A declared active_only does not excuse an invalid fallback argument.
    for selected in (Selector(path=".*"), Selector(path=".*", active_only=True)):
        with pytest.raises(ValueError, match=r"select_nodes.default_active_only"):
            select_nodes(Network(), selected, default_active_only=raw)
    with pytest.raises(ValueError, match=r"PerformanceProfiler.track_memory"):
        PerformanceProfiler(track_memory=raw)


@pytest.mark.parametrize("raw", [True, False, np.bool_(True), np.bool_(False)])
def test_boolean_selector_and_profiler_controls(raw):
    from ngraph.model.selectors import Selector, parse_match_spec, select_nodes
    from ngraph.profiling import PerformanceProfiler

    if bool(raw):
        with pytest.raises(ValueError, match="expected at least one condition"):
            parse_match_spec({}, require_conditions=raw)
    else:
        assert parse_match_spec({}, require_conditions=raw).conditions == ()
    parsed = parse_match_spec(
        {"conditions": [{"attr": "name", "op": "==", "value": "a"}]},
        require_conditions=raw,
    )
    assert [(c.attr, c.op, c.value) for c in parsed.conditions] == [("name", "==", "a")]
    n = Network(nodes={"a": Node("a"), "b": Node("b", disabled=True)})
    assert select_nodes(n, Selector(path=".*"), default_active_only=raw) == {
        ".*": [n.nodes["a"]] if bool(raw) else list(n.nodes.values())
    }
    p = PerformanceProfiler(track_memory=raw)
    assert p._track_memory is bool(raw)
