"""Named path output has exact ordered hops, costs and omission rules."""

from copy import deepcopy

import jsonschema
import netgraph_core as ngc
import pytest

import ngraph.export as exporting
from ngraph import PathQuery, Selector, paths
from tests.results.test_analysis_wire import prepared, project
from tests.results.test_native_field_plants import at
from tests.results.test_report_field_plants import change, exact, field_paths


def oracle(variant):
    context = prepared()
    options = (
        ngc.KspOptions(2) if variant == "ksp" else ngc.SpfOptions(ngc.Direction.FORWARD)
    )
    if variant == "unreachable":
        options = ngc.SpfOptions(
            ngc.Direction.FORWARD,
            eligibility=context.topology.graph.eligibility(
                excluded_nodes=[context.topology.node_id_by_name["t"]]
            ),
        )
    source, target = Selector("^a$"), Selector("^a$" if variant == "self" else "^t$")
    value = paths(
        context,
        PathQuery(source, target, options=options, costs_only=variant == "costs"),
    )
    cheap = {
        "source": "a",
        "destination": "t",
        "cost": 3,
        "hops": [
            [{"link": "a|b|0", "direction": "forward"}],
            [{"link": "b|t|0", "direction": "forward"}],
        ],
    }
    direct = {
        "source": "a",
        "destination": "t",
        "cost": 5,
        "hops": [[{"link": "a|t|0", "direction": "forward"}]],
    }
    row = {
        "id": "pair-000000",
        "endpoints": {
            "sources": ["a"],
            "destinations": ["a" if variant == "self" else "t"],
        },
        "kind": "self" if variant == "self" else "paths",
        "cost": {"self": 0, "unreachable": None}.get(variant, 3),
    }
    if variant != "costs":
        row["paths"] = (
            []
            if variant in ("self", "unreachable")
            else ([cheap, direct] if variant == "ksp" else [cheap])
        )
    expected = {
        "kind": "paths",
        "metadata": {"workers": 1, "sampling": None},
        "algorithm": "ksp" if variant == "ksp" else "spf",
        "mode": "combine",
        "costs_only": variant == "costs",
        "rows": [row],
    }
    wire = project(value)["analysis"]
    del wire["query"]
    exact(wire, expected)


@pytest.mark.parametrize("variant", ["spf", "ksp", "costs", "self", "unreachable"])
def test_named_path_fields_are_exact(variant):
    oracle(variant)


@pytest.mark.parametrize("variant", ["spf", "ksp", "costs", "self", "unreachable"])
def test_path_exporter_field_plants_are_caught(monkeypatch, variant):
    original = exporting._paths
    cls = next(
        cls for cls, encoder in exporting._EXPORTERS.items() if encoder is original
    )
    observed = []

    def capture(*args, **kwargs):
        value = original(*args, **kwargs)
        observed.append(deepcopy(value))
        return value

    with monkeypatch.context() as patch:
        patch.setitem(exporting._EXPORTERS, cls, capture)
        oracle(variant)
    (baseline,) = observed
    caught = equivalent = 0
    paths = tuple(field_paths(baseline))
    for path in paths:
        for mode in ("missing", "null", "wrong"):
            if mode == "null" and at(baseline, path) is None:
                equivalent += 1
                continue

            def planted(*args, path=path, mode=mode, **kwargs):
                value = original(*args, **kwargs)
                change(value, path, mode)
                return value

            with monkeypatch.context() as patch:
                patch.setitem(exporting._EXPORTERS, cls, planted)
                with pytest.raises((AssertionError, jsonschema.ValidationError)):
                    oracle(variant)
            caught += 1
    oracle(variant)
    assert caught + equivalent == len(paths) * 3
    print(
        f"PATH FIELD PLANTS: {variant}; {len(paths)} paths; {caught} caught; {equivalent} equivalent null->null"
    )
