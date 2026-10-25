"""Pinned eligibility retains compiled paths and splits over surviving entries."""

import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    PinnedRoutes,
    PlacementQuery,
    RouteSpec,
    Scenario,
    Selector,
    UnitsSettings,
    place,
    prepare,
)


def test_failed_pinned_route_gets_zero_and_survivor_gets_full_offer():
    n = Network(nodes={k: Node(k) for k in ("s", "a", "b", "t")})
    for s, t in [("s", "a"), ("a", "t"), ("s", "b"), ("b", "t")]:
        n.add_link(Link(s, t, 20))
    ds = DemandSet(
        "d",
        (DemandSpec(Selector("^s$"), Selector("^t$"), 10, PinnedRoutes(("a", "b"))),),
    )
    p = prepare(
        Scenario(
            n,
            demand_sets={"d": ds},
            routes={
                "a": RouteSpec("s", nodes=("s", "a", "t")),
                "b": RouteSpec("s", nodes=("s", "b", "t")),
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )
    failure = FailurePolicy(modes=[FailureMode(1, [FailureRule("node", path="^a$")])])
    result = place(
        p,
        PlacementQuery(
            p.demand_sets["d"], failures=FailureRequest(failure, 1, seed=1), workers=1
        ),
    )
    native = [c.states["converged"].rows[0].result for c in result.cases]
    assert [[f.assigned for f in r.by_tunnel] for r in native] == [[5, 5], [0, 10]]
    assert [r.delivered for r in native] == [10, 10]
    assert not native[1].edge_drops and native[1].unadmitted == 0


def test_named_pinned_dag_refuses_residual_snapshot_with_capacity_control():
    text = """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 20}]
supports:
  support:
    edges: [{link: 's|t|0', direction: forward}]
routes:
  dag: {head: s, support: support}
demands:
  d:
    - {source: ^s$, target: ^t$, volume: 1, model: {routing: {type: pinned, routes: [dag], allocation: weighted, weight_basis: BASIS}}}
workflow: [{type: TrafficMatrixPlacement, demand_set: d}]
"""
    prepare(Scenario.from_yaml(text.replace("BASIS", "capacity")))
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(text.replace("BASIS", "residual_snapshot"))
    message = str(error.value.__cause__)
    assert (
        "residual_snapshot" in message
        and "capacity" in message
        and "explicit" in message
    )
