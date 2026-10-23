"""A declared DistributedTE cost ceiling reaches the native model it builds."""

import pytest

from ngraph import Scenario, prepare, run

# The only positive-capacity route costs 2; the shortest one costs 1 and has
# capacity 0. A ceiling of cost 1 (or stretch 1) leaves no usable tunnel; a
# ceiling of 2 admits the cost-2 route, which carries the whole unit.
NETWORK = """
units: {resolution: 1}
network:
  nodes: {s: {}, t: {}}
  links:
    - {source: s, target: t, capacity: 0, cost: 1}
    - {source: s, target: t, capacity: 4, cost: 2}
"""
MODEL = (
    "{routing: {type: distributed_te, tunnel_count: {per_head: 1}, "
    "cost_ceiling: CEILING}}"
)
QUESTIONS = {
    "capacity": f"""
workflow:
  - {{type: MaxFlow, name: ask, source: "^s$", target: "^t$", offer: 1,
     design_demand: 1, workers: 1, model: {MODEL}}}
""",
    "placement": f"""
demands:
  d: [{{source: "^s$", target: "^t$", volume: 1, model: {MODEL}}}]
workflow:
  - {{type: TrafficMatrixPlacement, name: ask, demand_set: d, workers: 1}}
""",
}


@pytest.mark.parametrize("question", sorted(QUESTIONS))
@pytest.mark.parametrize(
    "ceiling,delivered",
    [
        ("{type: absolute, value: 1}", 0),
        ("{type: absolute, value: 2}", 1),
        ('{type: stretch, value: "1"}', 0),
        ('{type: stretch, value: "2"}', 1),
    ],
    ids=["absolute-1", "absolute-2", "stretch-1", "stretch-2"],
)
def test_declared_cost_ceilings_admit_only_routes_within_them(
    question, ceiling, delivered
):
    text = (NETWORK + QUESTIONS[question]).replace("CEILING", ceiling)
    step = run(prepare(Scenario.from_yaml(text))).steps[0]
    row = step.result.cases[0].states["converged"].rows[0]
    assert row.result.delivered == delivered
