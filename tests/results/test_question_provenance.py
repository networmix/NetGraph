"""Recorded questions name a workflow's policy, its seed source and a pinned split."""

import json
from io import StringIO

import pytest

from ngraph import (
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    PlacementQuery,
    Scenario,
    place,
    prepare,
    run,
    write_json,
)

NETWORK = """
seed: 42
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 20}]
failures:
  links:
    modes: [{weight: 1, rules: [{scope: link, mode: choice, count: 1}]}]
demands:
  d:
    - {source: ^s$, target: ^t$, volume: 4}
"""


def exported(value):
    output = StringIO()
    write_json(value, output)
    return json.loads(output.getvalue())


@pytest.mark.parametrize(
    "seed,source", [("", "scenario"), (", seed: 5", "step")], ids=["derived", "step"]
)
def test_a_workflow_question_names_its_policy_and_the_sample_its_seed(seed, source):
    text = NETWORK + (
        "workflow:\n  - {type: TrafficMatrixPlacement, name: tm, demand_set: d,"
        f" failure_policy: links, iterations: 3{seed}}}\n"
    )
    (step,) = exported(run(prepare(Scenario.from_yaml(text))))["steps"]
    failures = step["question"]["failures"]
    assert failures["policy_name"] == "links" and failures["inline_policy"] is None
    assert failures["iterations"] == 3 and failures["seed"] == step["step_seed"]
    assert step["result"]["metadata"]["sampling"]["seed_source"] == source


def test_a_library_question_records_its_unnamed_policy_inline():
    prepared = prepare(Scenario.from_yaml(NETWORK), demand_sets=("d",))
    policy = FailurePolicy(
        {"why": "test"}, modes=[FailureMode(1, [FailureRule("link", mode="all")])]
    )
    value = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["d"], failures=FailureRequest(policy, 2, 7), workers=1
        ),
    )
    analysis = exported(value)["analysis"]
    failures = analysis["query"]["failures"]
    assert failures["policy_name"] is None
    assert failures["inline_policy"]["attrs"] == {"why": "test"}
    assert failures["inline_policy"]["modes"][0]["rules"][0]["mode"] == "all"
    assert analysis["metadata"]["sampling"]["seed_source"] == "query"


PINNED = """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 20}]
supports:
  support:
    edges: [{link: 's|t|0', direction: forward}]
routes:
  dag: {head: s, support: support}
  path: {head: s, nodes: [s, t]}
demands:
  d:
    - {source: ^s$, target: ^t$, volume: 1, model: {routing: {type: pinned, routes: [ROUTE]SPLIT}}}
workflow: [{type: TrafficMatrixPlacement, name: tm, demand_set: d}]
"""


@pytest.mark.parametrize(
    "route,split,allocation,basis",
    [
        (
            "dag",
            ", allocation: weighted, weight_basis: capacity",
            "weighted",
            "capacity",
        ),
        ("dag", ", allocation: weighted", "weighted", "capacity"),
        ("dag", "", "equal", None),
        ("path", "", None, None),
    ],
)
def test_a_named_pinned_model_records_its_split_only_over_a_support(
    route, split, allocation, basis
):
    text = PINNED.replace("ROUTE", route).replace("SPLIT", split)
    (step,) = exported(run(prepare(Scenario.from_yaml(text))))["steps"]
    model = step["question"]["demands"][0]["model"]
    assert model["routing"] == "pinned" and model["route_names"] == [route]
    assert (model["allocation"], model["weight_basis"]) == (allocation, basis)
    assert model["supplied_program"] is False
