"""Provenance follows key/index tuples, including literal punctuation in keys."""

import signal

import numpy as np
import pytest
import yaml

from ngraph import Scenario
from ngraph.dsl.blueprints import expand
from ngraph.utils.values import frozen_attrs

CASES = [
    ("rate.avg", {"avg": 5}, {"avg": float("inf")}, ".avg"),
    ("rate[0]", [5], [float("inf")], "[0]"),
    ("rate[avg", {"avg": 5}, {"avg": float("inf")}, ".avg"),
    ("rate]avg", {"avg": 5}, {"avg": float("inf")}, ".avg"),
    ("rate].avg", {"avg": 5}, {"avg": float("inf")}, ".avg"),
    ("rate.[0]", [5], [float("inf")], "[0]"),
    ("rate[0].avg", [{"avg": 5}], [{"avg": float("inf")}], "[0].avg"),
    ("rate.avg[0]", {"avg": [5]}, {"avg": [float("inf")]}, ".avg[0]"),
]
STYLES = (
    "default",
    "nested-node",
    "attrs",
    "node",
    "subtree",
    "nested-params",
    "deep-params",
)


@pytest.fixture(autouse=True)
def bounded_case():
    def expired(*_):
        raise TimeoutError("structured path case exceeded four seconds")

    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(4)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def document(key, value, override, style, boxed):
    attrs = {"box": {key: value}} if boxed else {key: value}
    group = {"attrs": attrs}
    d = {"blueprints": {}, "network": {"nodes": {"P": {"blueprint": "unit"}}}}
    params = {}
    if style in ("nested-params", "deep-params"):
        d["blueprints"]["unit"] = {"nodes": {"G": {"blueprint": "inner"}}}
        if style == "nested-params":
            d["blueprints"]["inner"] = {"nodes": {"H": group}}
            owner = "blueprints.inner.nodes.H.attrs"
            target = "H.attrs"
            nested = params
            params["G.params"] = nested = {}
            source = "network.nodes.P.params.G.params.H.attrs"
        else:
            d["blueprints"]["inner"] = {"nodes": {"H": {"blueprint": "deep"}}}
            d["blueprints"]["deep"] = {"nodes": {"J": group}}
            owner = "blueprints.deep.nodes.J.attrs"
            params["G.params"] = {"H.params": {}}
            nested = params["G.params"]["H.params"]
            target = "J.attrs"
            source = "network.nodes.P.params.G.params.H.params.J.attrs"
    else:
        if style == "default":
            d["blueprints"]["unit"] = {"nodes": {"G": group}}
            target = "G.attrs"
            owner = "blueprints.unit.nodes.G.attrs"
        else:
            d["blueprints"]["unit"] = {"nodes": {"G": {"nodes": {"H": group}}}}
            target = "G.nodes.H.attrs"
            owner = "blueprints.unit.nodes.G.nodes.H.attrs"
        nested = params
        source = "network.nodes.P.params." + target
        if style == "attrs":
            params[target] = attrs
            owner = source
        elif style == "node":
            params["G.nodes.H"] = group
            owner = source
        elif style == "subtree":
            params["G.nodes"] = {"H": group}
            owner = source
    tail = ".box" if boxed else ""
    nested[target + tail + ".rate"] = override
    d["network"]["nodes"]["P"]["params"] = params
    return d, owner + tail + "." + key, source + tail + ".rate"


def load(d, entry):
    return (
        Scenario.from_yaml(yaml.safe_dump(d, sort_keys=False)).network
        if entry == "yaml"
        else expand.expand_network_dsl(d)
    )


@pytest.mark.parametrize("key,valid,invalid,suffix", CASES)
@pytest.mark.parametrize("style", STYLES)
@pytest.mark.parametrize("boxed", [False, True])
@pytest.mark.parametrize("nested_value", [False, True])
@pytest.mark.parametrize("entry", ["yaml", "expansion"])
def test_literal_key_and_real_descendant_have_distinct_suppliers(
    key, valid, invalid, suffix, style, boxed, nested_value, entry
):
    good = {"x": [7]} if nested_value else 7
    bad = {"x": [float("inf")]} if nested_value else float("inf")
    ending = ".x[0]" if nested_value else ""
    control, _, _ = document(key, good, valid, style, boxed)
    node = next(iter(load(control, entry).nodes.values()))
    expected = {key: good, "rate": valid}
    assert node.attrs == ({"box": expected} if boxed else expected)

    broken, literal_source, _ = document(key, bad, valid, style, boxed)
    with pytest.raises(ValueError) as error:
        load(broken, entry)
    assert type(error.value) is ValueError
    assert (
        str(error.value)
        == literal_source + ending + ": expected finite JSON data, got float = inf"
    )

    broken, _, override_source = document(key, good, invalid, style, boxed)
    with pytest.raises(ValueError) as error:
        load(broken, entry)
    assert type(error.value) is ValueError
    assert (
        str(error.value)
        == override_source + suffix + ": expected finite JSON data, got float = inf"
    )


@pytest.mark.parametrize("key", ["rate.avg", "rate[0]", "rate]avg", "", ".[0]"])
@pytest.mark.parametrize("shape", ["scalar", "list", "mapping", "list-mapping"])
def test_json_refusal_retains_literal_keys_and_positions(key, shape):
    if shape == "scalar":
        bad, good, path = {key: float("inf")}, {key: 3}, (key,)
    elif shape == "list":
        bad, good, path = {key: [0, float("inf")]}, {key: [0, 3]}, (key, 1)
    elif shape == "mapping":
        bad, good, path = (
            {"outer": {key: float("inf")}},
            {"outer": {key: 3}},
            ("outer", key),
        )
    else:
        bad, good, path = (
            {"outer": [{key: float("inf")}]},
            {"outer": [{key: 3}]},
            ("outer", 0, key),
        )
    assert frozen_attrs(good) == good
    with pytest.raises(ValueError) as error:
        frozen_attrs(bad, "arbitrary.label[0]")
    assert type(error.value) is ValueError
    assert error.value.__dict__["_input_path"] == path
    assert (
        error.value.__dict__["_input_detail"]
        == "expected finite JSON data, got float = inf"
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("disabled", "false"),
        ("attrs", 3),
        ("risk_groups", 3),
        ("count", 0),
        ("template", 3),
        ("nodes", 3),
        ("blueprint", 3),
        ("params", 3),
    ],
)
def test_each_field_checker_reports_its_root_without_parsing_a_label(field, bad):
    with pytest.raises(ValueError) as error:
        expand._NODE_FIELD_CHECKS[field](bad, "unrelated.label[0]:prefix")
    assert type(error.value) is ValueError
    assert error.value.__dict__["_input_path"] == ()
    assert "unrelated.label" not in error.value.__dict__["_input_detail"]
    assert repr(bad) in error.value.__dict__["_input_detail"]


def test_readable_message_cannot_change_source_selection(monkeypatch):
    checker = expand._NODE_FIELD_CHECKS["attrs"]

    def changed_message(value, label):
        try:
            return checker(value, label)
        except ValueError as error:
            error.args = ("attrs.rate.avg: misleading human text",)
            raise

    monkeypatch.setitem(expand._NODE_FIELD_CHECKS, "attrs", changed_message)
    d, source, _ = document("rate.avg", float("inf"), {"avg": 5}, "default", False)
    with pytest.raises(ValueError) as error:
        expand.expand_network_dsl(d)
    assert str(error.value) == source + ": expected finite JSON data, got float = inf"


@pytest.mark.parametrize(
    "parts,expected",
    [
        (("attrs", "rate.avg"), "attrs-source.rate.avg"),
        (("attrs", "rate", "avg"), "rate-source.avg"),
        (("attrs", "rate[0]"), "attrs-source.rate[0]"),
        (("attrs", "rate", 0), "rate-source[0]"),
        (("attrs", "rows", 1, "x"), "row-source.x"),
        (("attrs", "rows", "1", "x"), "attrs-source.rows.1.x"),
        (("template",), "node-source.template"),
    ],
)
def test_source_is_the_longest_tuple_prefix(parts, expected):
    sources = {
        (): "node-source",
        ("attrs",): "attrs-source",
        ("attrs", "rate"): "rate-source",
        ("attrs", "rows", 1): "row-source",
    }
    assert expand._source_path(sources, parts, "fallback") == expected


def test_numpy_json_scalars_keep_paths_and_plain_valid_values():
    assert frozen_attrs(
        {np.str_("rate.avg"): [np.bool_(True), np.int64(3), np.float64(5)]}
    ) == {"rate.avg": [True, 3, 5.0]}
    with pytest.raises(ValueError) as error:
        frozen_attrs({np.str_("rate.avg"): [np.float64("inf")]})
    assert error.value.__dict__["_input_path"] == ("rate.avg", 0)
    assert type(error.value.__dict__["_input_path"][0]) is str
