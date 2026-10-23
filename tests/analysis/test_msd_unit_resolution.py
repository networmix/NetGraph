"""Positive physical leaves must receive units before a probe verifies feasibility."""

import json
from importlib.resources import files
from io import StringIO

import pytest
from jsonschema import validate

from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    MSDQuery,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    maximum_supported_demand,
    prepare,
    run,
    write_json,
)


def prepared(*, linked=True, mixed=False, volume=4, q=None):
    n = Network(nodes={x: Node(x) for x in ("A", "B", "C")})
    n.add_link(Link("A", "B" if linked else "C", 3))
    d = DemandSpec(
        Selector("^A$"),
        Selector("^[BC]$" if mixed else "^B$"),
        volume,
        mode="pairwise" if mixed else "combine",
    )
    return prepare(
        Scenario(
            n,
            demand_sets={"d": DemandSet("d", (d,))},
            units=UnitsSettings("auto" if q is None else q),
        ),
        demand_sets=("d",),
    )


@pytest.mark.parametrize("mixed", [False, True])
def test_unroutable_positive_leaf_is_none_feasible_at_resolution(mixed):
    p = prepared(linked=mixed, mixed=mixed, volume=2 if mixed else 4)
    result = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], export_probe_rows=True)
    )
    assert result.search_status == "none_feasible"
    assert result.stop_reason == "unit_resolution"
    assert (
        result.alpha_feasible
        is result.best_probe_index
        is result.best_rows
        is result.best_accounting
        is None
    )
    assert result.upper_certificate is None
    assert any(h.outcome == "below_resolution" for h in result.history)
    assert not any(h.outcome == "feasible" for h in result.history)
    for h in result.history:
        if h.outcome == "below_resolution":
            assert any(
                r.reference_request_units == 0 for r in result.probe_rows[h.index]
            )
    out = StringIO()
    write_json(result, out)
    value = json.loads(out.getvalue())
    assert value["analysis"]["stop_reason"] == "unit_resolution"
    assert any(h["outcome"] == "below_resolution" for h in value["analysis"]["history"])
    validate(
        value, json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
    )


def test_nominal_zero_probe_grows_to_verified_nonzero_best():
    p = prepared(volume=0.25, q=1)
    result = maximum_supported_demand(
        p, MSDQuery(p.demand_sets["d"], export_probe_rows=True)
    )
    assert result.history[0].alpha.value == 1
    assert result.history[0].outcome == "below_resolution"
    assert result.alpha_feasible is not None
    assert result.alpha_feasible.value == 13.9921875
    assert result.history[result.best_probe_index].outcome == "feasible"
    assert all(row.reference_request_units >= 1 for row in result.best_rows)
    cert = result.upper_certificate
    assert cert is not None
    assert result.history[cert.lower_probe_index].outcome == "feasible"
    assert result.history[cert.upper_probe_index].outcome == "infeasible"


def test_alpha_from_none_feasible_msd_refuses_without_placing():
    s = Scenario.from_yaml("""
network:
  nodes: {A: {}, B: {}, C: {}}
  links: [{source: A, target: B, capacity: 3}]
demands:
  d: [{source: ^A$, target: '^[BC]$', volume: 2, mode: pairwise}]
workflow:
  - {type: MaximumSupportedDemand, name: msd, demand_set: d}
  - {type: TrafficMatrixPlacement, name: placement, demand_set: d, alpha_from_step: msd}
""")
    with pytest.raises(
        ValueError, match="alpha_from_step 'msd': no tested feasible alpha"
    ):
        run(prepare(s))
