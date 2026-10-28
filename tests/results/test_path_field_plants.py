"""Named path output has exact ordered hops, costs and omission rules."""

import netgraph_core as ngc
import pytest

from ngraph import PathQuery, Selector, paths
from tests.results.test_analysis_wire import prepared, project
from tests.results.test_report_field_plants import exact


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
