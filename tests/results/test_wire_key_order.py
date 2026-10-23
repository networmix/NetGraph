"""JSON keys keep their decided order; plain records follow their declarations."""

import json
from io import StringIO

import netgraph_core as ngc

from ngraph import (
    CapacityQuery,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
    write_json,
)
from ngraph.export import _PLAIN, layout, project


def wire():
    network = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    network.add_link(Link("a", "t", 3, 1))
    network.add_link(Link("b", "t", 2, 1))
    prepared = prepare(Scenario(network, units=UnitsSettings(1)))
    policy = FailurePolicy(modes=[FailureMode(1, [FailureRule("node", path="^b$")])])
    value = capacity(
        prepared,
        CapacityQuery(
            Selector("^(a|t)$"),
            Selector("^(t)$"),
            ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
            "pairwise",
            failures=FailureRequest(policy, 2, 5, True),
            workers=1,
        ),
    )
    output = StringIO()
    write_json(value, output)
    return json.loads(output.getvalue())


def test_exported_keys_keep_their_hand_written_order():
    data = wire()
    assert list(data) == ["metadata", "analysis", "units_report"]
    # A standalone analysis is written with its producer's identity, unseeded.
    from ngraph.analysis.metadata import run_metadata

    assert data["metadata"]["seed"] is None
    assert data["metadata"] == project(run_metadata())
    assert list(data["metadata"]) == [
        "schema_version",
        "netgraph_version",
        "core_version",
        "core_extension_sha256",
        "python_version",
        "seed",
    ]
    assert list(data["units_report"])[:8] == [
        "q",
        "exponent",
        "mode",
        "precision",
        "target_met",
        "input_convention",
        "display_convention",
        "scope",
    ]
    analysis = data["analysis"]
    assert list(analysis["metadata"]["sampling"]) == [
        "random_rule_algorithm",
        "rng",
        "python_version",
        "seed",
        "seed_source",
        "draw_seed_rule",
        "entity_order",
        "rule_order",
        "iterations",
    ]
    assert list(analysis["outputs"]["native"]) == [
        "edge_flows",
        "residual",
        "edge_reservations",
        "saturated_boundary_edges",
        "min_cut",
    ]
    rows = analysis["cases"][0]["states"]["converged"]["rows"]
    assert [list(row) for row in rows if row["kind"] == "self"] == [
        ["kind", "id", "node", "capacity_units"]
    ]
    trace = analysis["cases"][1]["case"]["trace"]
    assert list(trace) == [
        "draw_index",
        "mode_index",
        "mode_attrs",
        "selections",
        "expanded_nodes",
        "expanded_links",
    ]
    assert list(trace["selections"][0]) == ["rule_index", "scope", "selected"]
    assert list(analysis["query"]) == [
        "kind",
        "source",
        "target",
        "mode",
        "model",
        "offer",
        "design_demand",
        "failures",
    ]


def test_every_plain_record_writes_its_constants_and_fields_in_declared_order():
    from fractions import Fraction

    from ngraph.results import ExactAlpha, PoolHead, PoolMetadata, SplitConstraint

    split = SplitConstraint(
        "router", "x", Fraction(3, 2), "observed", 2, Fraction(1), True
    )
    assert list(project(split)) == [
        "kind",
        "label",
        "incoming_physical",
        "basis",
        "members",
        "q_upper_bound",
        "met",
    ]
    assert project(split)["incoming_physical"] == {"numerator": 3, "denominator": 2}
    pool = project(PoolMetadata(PoolHead("p", ("a", "b"))))
    assert pool == {
        "head": {"pool_id": "p", "physical_sources": ["a", "b"]},
        "offer_limit_units": 0,
        "synthetic_ingress_cost": 1,
    }
    assert list(project(ExactAlpha(0.5, 1, 2))) == ["value", "numerator", "denominator"]
    for kind in _PLAIN:
        assert set(layout(kind)) >= {field for field in kind.__dataclass_fields__}
