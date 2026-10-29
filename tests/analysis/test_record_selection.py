"""Native records are materialized only for report readers that need them."""

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    place,
    prepare,
)


@pytest.mark.parametrize("costs", [False, True])
@pytest.mark.parametrize(
    "kind",
    [
        "split",
        "optimized_spf",
        "residual",
        "t1",
        "t2",
        "equal",
        "weighted",
        "optimized",
    ],
)
def test_report_record_selection_has_numerical_and_getter_controls(
    kind, costs, monkeypatch
):
    if kind == "t1":
        model = ngc.DistributedTE(ngc.TunnelCount(1))
    elif kind in ("t2", "equal", "weighted", "optimized"):
        model = ngc.CentralizedTE(
            source_allocation=(
                ngc.SourceAllocation.OPTIMIZED
                if kind == "optimized"
                else ngc.SourceAllocation.WEIGHTED
                if kind == "weighted"
                else ngc.SourceAllocation.EQUAL
            ),
            source_weights=[1, 0, 0] if kind == "weighted" else None,
            tunnel_count=ngc.TunnelCount(1) if kind == "t2" else None,
        )
    else:
        model = ngc.ShortestPaths(
            allocation=(
                ngc.RouteAllocation.OPTIMIZED
                if kind == "optimized_spf"
                else ngc.RouteAllocation.WEIGHTED
                if kind == "residual"
                else ngc.RouteAllocation.EQUAL
            ),
            weight_basis=ngc.WeightBasis.RESIDUAL_SNAPSHOT
            if kind == "residual"
            else None,
        )
    network = Network(nodes={name: Node(name) for name in ("s", "x", "t")})
    network.add_link(Link("s", "x", 8, 1))
    network.add_link(Link("x", "t", 8, 2))
    prepared = prepare(
        Scenario(
            network,
            demand_sets={
                "load": DemandSet(
                    "load",
                    (
                        DemandSpec(
                            Selector("^s$"),
                            Selector("^t$"),
                            4,
                            ngc.FlowPolicyConfig(routing=model),
                        ),
                    ),
                )
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )
    original = ngc.FlowPolicy.records
    calls = []

    def records(owner):
        calls.append(owner)
        return original(owner)

    monkeypatch.setattr(ngc.FlowPolicy, "records", records)
    result = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"], workers=2, export_cost_distribution=costs
        ),
    )
    (row,) = result.cases[0].states["converged"].rows
    assert row.result.delivered == row.reference_request_units == 4
    assert row.result.source_drops == 0 and not row.result.edge_drops
    assert len(calls) == int(costs and kind in ("split", "residual", "optimized_spf"))
    report = row.cost_distribution
    if not costs:
        assert report is None and not row.unavailable_outputs
    elif kind == "optimized":
        assert report is not None and report.kind == "marginal_curve"
        assert [(item.marginal_cost, item.units) for item in report.bins] == [(3, 4)]
    else:
        assert report is not None and report.kind == "delivered_by_path_cost"
        assert [
            (item.cost, item.physical_path_cost, item.delivered_units)
            for item in report.bins
        ] == [(3, 3, 4)]


def test_later_residual_weights_use_capacity_left_by_earlier_demand():
    network = Network(nodes={name: Node(name) for name in ("s", "a", "b", "t")})
    for source, target, capacity in (
        ("s", "a", 4),
        ("a", "t", 4),
        ("s", "b", 8),
        ("b", "t", 8),
    ):
        network.add_link(Link(source, target, capacity, 1))
    models = (
        ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
        ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.RESIDUAL_SNAPSHOT,
        ),
    )
    prepared = prepare(
        Scenario(
            network,
            demand_sets={
                "load": DemandSet(
                    "load",
                    tuple(
                        DemandSpec(
                            Selector("^s$"),
                            Selector("^t$"),
                            4,
                            ngc.FlowPolicyConfig(routing=model),
                        )
                        for model in models
                    ),
                )
            },
            units=UnitsSettings(1, precision=0.2),
        ),
        demand_sets=("load",),
    )
    result = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"], outputs=ngc.OutputOptions(edge_flows=True)
        ),
    )
    first, second = result.cases[0].states["converged"].rows
    assert first.result.delivered == second.result.delivered == 4
    references = prepared.topology.edge_refs
    first_flows = dict(zip(references, first.result.edge_flows, strict=True))
    second_flows = dict(zip(references, second.result.edge_flows, strict=True))
    for reference in references:
        assert first_flows[reference] == (
            4
            if reference.direction == "forward" and reference.link in ("s|a|0", "a|t|0")
            else 0
        )
        assert second_flows[reference] == (
            4
            if reference.direction == "forward" and reference.link in ("s|b|0", "b|t|0")
            else 0
        )
    # The report is the preparation's input/count budget: L=12, Gamma=5,
    # c_min=4 and q1 give 5/4, outside p=1/5 even with exact routing.
    assert result.units_report.achieved_precision == 5 / 4
    assert not result.units_report.target_met
