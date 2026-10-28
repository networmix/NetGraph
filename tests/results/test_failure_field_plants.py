"""First-draw traces and sampling receipts have independent complete wire values."""

import sys

import pytest

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
)
from ngraph.model.risk import RiskGroup
from tests.results.test_analysis_wire import project
from tests.results.test_report_field_plants import exact


def oracle(seed_source):
    network = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    network.add_link(Link("a", "b", 2, 1))
    network.add_link(Link("b", "t", 2, 2))
    network.add_link(Link("a", "t", 3, 5))
    network.risk_groups["fiber"] = RiskGroup("fiber")
    network.replace_node("b", risk_groups={"fiber"})
    policy = FailurePolicy(
        seed=7 if seed_source != "unseeded" else None,
        modes=[
            FailureMode(
                1,
                [FailureRule("risk_group", mode="all", path="^fiber$")],
                attrs={"cause": "maintenance"},
            )
        ],
    )
    request = FailureRequest(
        policy, 3, seed=11 if seed_source == "query" else None, failure_trace=True
    )
    value = capacity(
        prepare(Scenario(network, units=UnitsSettings(1))),
        CapacityQuery(Selector("^a$"), Selector("^t$"), failures=request, workers=2),
    )
    wire = project(value)["analysis"]
    exact(
        wire["metadata"],
        {
            "workers": 2,
            "sampling": {
                "random_rule_algorithm": "per_entity_bernoulli",
                "rng": "random.Random",
                "python_version": sys.version.split()[0],
                "seed": {"query": 11, "policy": 7, "unseeded": None}[seed_source],
                "seed_source": seed_source,
                "draw_seed_rule": "base_plus_draw_index",
                "entity_order": "sorted_identifier",
                "rule_order": "declaration",
                "iterations": 3,
            },
        },
    )
    expected = [
        {
            "id": "baseline",
            "kind": "baseline",
            "pattern": {"excluded_nodes": [], "excluded_links": []},
            "occurrences": 0,
        },
        {
            "id": "failure-000001",
            "kind": "failure",
            "pattern": {"excluded_nodes": ["b"], "excluded_links": []},
            "occurrences": 3,
            "trace": {
                "draw_index": 0,
                "mode_index": 0,
                "mode_attrs": {"cause": "maintenance"},
                "selections": [
                    {"rule_index": 0, "scope": "risk_group", "selected": ["fiber"]}
                ],
                "expanded_nodes": ["b"],
                "expanded_links": [],
            },
        },
    ]
    assert all(set(case) == {"case", "states"} for case in wire["cases"])
    actual = [case["case"] for case in wire["cases"]]
    exact(actual, expected)
    # Baseline cut5 becomes direct3 when b is unavailable; both cases retain the
    # declared converged-state mapping and exactly one row.
    assert [
        case["states"]["converged"]["rows"][0]["result"]["delivered_units"]
        for case in wire["cases"]
    ] == [5, 3]


@pytest.mark.parametrize("seed_source", ["query", "policy", "unseeded"])
def test_trace_and_sampling_fields_are_exact(seed_source):
    oracle(seed_source)
