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


# Two routes of capacity 1 each: (a) costs 2 and 3, (b) costs 25 and 29 (two links each).
ROUTES = {
    "a": ((1, 1), (1, 2)),
    "b": ((12, 13), (14, 15)),
}
TWO_TUNNELS = (
    "{routing: {type: distributed_te, tunnel_count: {per_head: 2}, "
    'cost_ceiling: {type: stretch, value: "STRETCH"}}, admission: lossy}'
)
ASK_TWO = {
    "capacity": f"""
workflow:
  - {{type: MaxFlow, name: ask, source: "^s$", target: "^t$", offer: 2,
     design_demand: 2, workers: 1, model: {TWO_TUNNELS}}}
""",
    "placement": f"""
demands:
  d: [{{source: "^s$", target: "^t$", volume: 2, model: {TWO_TUNNELS}}}]
workflow:
  - {{type: TrafficMatrixPlacement, name: ask, demand_set: d, workers: 1}}
""",
}


@pytest.mark.parametrize("question", sorted(ASK_TWO))
@pytest.mark.parametrize(
    "network,stretch,delivered",
    [
        # 2 x 3/2 = 3: the cost-3 route is inside the inclusive ceiling.
        ("a", "1.5", 2),
        # 2 x 1.49999999999999999 < 3 exactly; as a binary64 float the stretch is 1.5.
        ("a", "1.49999999999999999", 1),
        # 25 x 29/25 = 29 exactly; the binary64 product is 28.999999999999996.
        ("b", "1.16", 2),
        # 25 x 1.15 = 28.75 < 29.
        ("b", "1.15", 1),
    ],
)
def test_a_decimal_stretch_is_exact_and_inclusive(
    question, network, stretch, delivered
):
    links = "\n".join(
        f"    - {{source: {u}, target: {v}, capacity: 1, cost: {cost}}}"
        for (first, second), mid in zip(ROUTES[network], ("x", "y"), strict=True)
        for u, v, cost in (("s", mid, first), (mid, "t", second))
    )
    text = (
        f"units: {{resolution: 1}}\nnetwork:\n  nodes: {{s: {{}}, x: {{}}, y: {{}}, t: {{}}}}\n"
        f"  links:\n{links}\n" + ASK_TWO[question]
    ).replace("STRETCH", stretch)
    step = run(prepare(Scenario.from_yaml(text))).steps[0]
    row = step.result.cases[0].states["converged"].rows[0]
    assert row.result.delivered == delivered
