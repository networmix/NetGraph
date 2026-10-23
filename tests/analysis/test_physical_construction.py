"""Physical inputs normalize before preparation, including NumPy numeric amounts."""

import numpy as np
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    prepare,
    run,
)
from ngraph.workflow.max_flow_step import MaxFlow
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


@pytest.mark.parametrize("kind", [np.int64, np.float32])
def test_numpy_link_capacity_normalizes_at_construction_and_routes(kind):
    link = Link("s", "t", kind(10))
    assert type(link.capacity) is float and link.capacity == 10.0
    network = Network(nodes={name: Node(name) for name in ("s", "t")})
    network.add_link(link)
    step = MaxFlow(
        name="cap", source=Selector("^s$"), target=Selector("^t$"), workers=1
    )
    prepared = prepare(Scenario(network, (step,), units=UnitsSettings(1)))
    result = run(prepared).steps[0].result.cases[0].states["converged"].rows[0].result
    # One s-t link: its capacity is both a feasible flow and the source cut.
    assert result.delivered == 10
    assert type(prepared.scenario.network.links["s|t|0"].capacity) is float
    assert Link("s", "t", kind(0)).capacity == 0.0


@pytest.mark.parametrize(
    "bad", [True, np.bool_(False), -1, float("nan"), float("inf"), "10"]
)
def test_link_capacity_invalid_physical_input_refuses_at_construction(bad):
    with pytest.raises(ValueError, match=r"^link s->t\.capacity: expected a finite"):
        Link("s", "t", bad)
    assert Link("s", "t", np.float32(10)).capacity == 10.0


def test_numpy_msd_alphas_normalize_at_step_construction_and_verify_alpha_max():
    params = dict(
        alpha_start=np.float32(1),
        growth_factor=np.float32(2),
        alpha_min=np.float32(0.125),
        alpha_max=np.float32(4),
        alpha_tolerance=np.float32(0.125),
    )
    step = MaximumSupportedDemand(name="msd", demand_set="d", **params)
    for name, value in params.items():
        assert type(getattr(step, name)) is float and getattr(step, name) == float(
            value
        )
    n = Network(nodes={name: Node(name) for name in ("s", "t")})
    n.add_link(Link("s", "t", np.int64(10)))
    s = Scenario(
        n,
        (step,),
        demand_sets={
            "d": DemandSet(
                "d", (DemandSpec(Selector("^s$"), Selector("^t$"), np.float32(2)),)
            )
        },
        units=UnitsSettings(1),
    )
    p = prepare(s)
    result = run(p).steps[0].result
    # Every tested alpha in 1,2,4 asks at most 8 units on a capacity10 link.
    assert result.alpha_feasible.value == 4
    assert [probe.alpha.value for probe in result.history] == [1, 2, 4]
    assert all(probe.outcome == "feasible" for probe in result.history)
    assert result.query.alpha_start == 1 and result.query.alpha_max == 4


@pytest.mark.parametrize("input_kind", ["python", "yaml"])
@pytest.mark.parametrize("source,target", [("A", "B"), ("B", "A")])
def test_negative_capacity_refusal_names_endpoints_in_python_and_yaml(
    input_kind, source, target
):
    text = f"""
network:
  nodes: {{{source}: {{}}, {target}: {{}}}}
  links: [{{source: {source}, target: {target}, capacity: -1}}]
"""
    with pytest.raises(ValueError) as error:
        if input_kind == "python":
            Link(source, target, -1)
        else:
            Scenario.from_yaml(text)
    assert (
        str(error.value)
        == f"link {source}->{target}.capacity: expected a finite nonnegative amount"
    )
    if input_kind == "python":
        assert Link(source, target, 1).capacity == 1.0
    else:
        scenario = Scenario.from_yaml(text.replace("capacity: -1", "capacity: 1"))
        link = next(iter(scenario.network.links.values()))
        assert (link.source, link.target, link.capacity) == (source, target, 1.0)
