"""Requested mixed-cost DAG reports give a reason, never an invented histogram."""

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    DirectedLink,
    Link,
    Network,
    Node,
    PinnedRoutes,
    PlacementQuery,
    RouteSpec,
    Scenario,
    Selector,
    SupportSpec,
    UnitsSettings,
    capacity,
    place,
    prepare,
)
from tests.results.test_analysis_wire import project


@pytest.mark.parametrize("analysis_kind", ["placement", "capacity"])
def test_mixed_cost_named_dag_has_explicit_unavailable_reason(analysis_kind):
    network = Network(nodes={name: Node(name) for name in ("a", "x", "y", "t")})
    edges = []
    for source, target, cost in (
        ("a", "x", 1),
        ("x", "t", 1),
        ("a", "y", 2),
        ("y", "t", 2),
    ):
        network.add_link(Link(source, target, 4, cost))
        edges.append(DirectedLink(f"{source}|{target}|0", "forward"))
    demands = DemandSet(
        "load", (DemandSpec(Selector("^a$"), Selector("^t$"), 4, PinnedRoutes(("r",))),)
    )
    context = prepare(
        Scenario(
            network,
            demand_sets={"load": demands},
            supports={"s": SupportSpec(tuple(edges))},
            routes={"r": RouteSpec("a", support="s")},
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )
    if analysis_kind == "placement":
        result = place(
            context,
            PlacementQuery(
                context.demand_sets["load"], workers=1, export_cost_distribution=True
            ),
        )
    else:
        result = capacity(
            context,
            CapacityQuery(
                Selector("^a$"),
                Selector("^t$"),
                context.demand_sets["load"].demands[0].config,
                offer=4,
                workers=1,
                export_cost_distribution=True,
            ),
        )
    (row,) = result.cases[0].states["converged"].rows
    assert row.result.delivered == 4
    assert row.cost_distribution is None
    assert dict(row.unavailable_outputs) == {"cost_distribution": "mixed_cost_dag"}
    with pytest.raises(TypeError):
        row.unavailable_outputs["cost_distribution"] = "unsupported_model"
    wire = project(result)["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    assert "cost_distribution" not in wire
    assert wire["unavailable_outputs"] == {"cost_distribution": "mixed_cost_dag"}


@pytest.mark.parametrize("analysis_kind", ["placement", "capacity"])
def test_equal_controller_decomposition_has_supported_path_costs(analysis_kind):
    network = Network(nodes={name: Node(name) for name in ("a", "t")})
    network.add_link(Link("a", "t", 4, 2))
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.EQUAL)
    )
    demands = DemandSet(
        "load", (DemandSpec(Selector("^a$"), Selector("^t$"), 4, config),)
    )
    context = prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    if analysis_kind == "placement":
        result = place(
            context,
            PlacementQuery(
                context.demand_sets["load"], workers=1, export_cost_distribution=True
            ),
        )
    else:
        result = capacity(
            context,
            CapacityQuery(
                Selector("^a$"),
                Selector("^t$"),
                config,
                offer=4,
                workers=1,
                export_cost_distribution=True,
            ),
        )
    (row,) = result.cases[0].states["converged"].rows
    assert row.result.delivered == 4
    assert row.result.total_cost == 8
    assert len(row.result.by_tunnel) == 1
    assert row.result.by_tunnel[0].delivered == 4
    assert row.cost_distribution is not None
    assert row.cost_distribution.kind == "delivered_by_path_cost"
    assert [
        (item.cost, item.physical_path_cost, item.delivered_units)
        for item in row.cost_distribution.bins
    ] == [(2, 2, 4)]
    assert dict(row.unavailable_outputs) == {}
    wire = project(result)["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    assert wire["cost_distribution"] == {
        "kind": "delivered_by_path_cost",
        "cost_domain": "physical_network",
        "bins": [{"cost": 2, "physical_path_cost": 2, "delivered_units": 4}],
    }
    assert "unavailable_outputs" not in wire


@pytest.mark.parametrize("analysis_kind", ["placement", "capacity"])
@pytest.mark.parametrize(
    ("capacity_", "volume", "joined", "bins"),
    [
        # Capacity 1, design and offer 2: each tunnel is sized 1. The first takes the
        # cost-2 route and holds it, so the second is routed on the residual over the
        # cost-3 route. Bins (2, 1) and (3, 1), total cost 5; binning by the minimum
        # route cost would give (2, 2).
        (1, 2, [(2, 1), (3, 1)], [(2, 2, 1), (3, 3, 1)]),
        # Capacity 2, design and offer 3: H(3, [1, 1]) sizes the tunnels 2 and 1. The
        # first reserves the cost-2 route's 2, the second the cost-3 route's 1. The
        # deliveries differ, so swapping the tunnels' costs would give (2, 1), (3, 2).
        (2, 3, [(2, 2), (3, 1)], [(2, 2, 2), (3, 3, 1)]),
    ],
)
def test_two_t1_tunnels_report_one_bin_per_tunnel_path_cost(
    analysis_kind, capacity_, volume, joined, bins
):
    # Routes s-x-t (cost 1 + 1) and s-y-t (cost 1 + 2); T1 with two tunnels, q = 1.
    # (T1 records no native total cost; the bins carry it.)
    network = Network(nodes={name: Node(name) for name in ("s", "x", "y", "t")})
    for source, target, cost in (
        ("s", "x", 1),
        ("x", "t", 1),
        ("s", "y", 1),
        ("y", "t", 2),
    ):
        network.add_link(Link(source, target, capacity_, cost))
    config = ngc.FlowPolicyConfig(
        routing=ngc.DistributedTE(ngc.TunnelCount(2)), admission=ngc.Admission.LOSSY
    )
    demands = DemandSet(
        "load", (DemandSpec(Selector("^s$"), Selector("^t$"), volume, config),)
    )
    context = prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    if analysis_kind == "placement":
        result = place(
            context,
            PlacementQuery(
                context.demand_sets["load"], workers=1, export_cost_distribution=True
            ),
        )
    else:
        result = capacity(
            context,
            CapacityQuery(
                Selector("^s$"),
                Selector("^t$"),
                config,
                offer=volume,
                design_demand=volume,
                workers=1,
                export_cost_distribution=True,
            ),
        )
    (row,) = result.cases[0].states["converged"].rows
    assert row.result.delivered == volume and row.result.total_cost is None
    # The entry join: each tunnel's own delivery against its own path cost.
    costs = {t.entry_id: t.path_cost for t in row.result.program.tunnels}
    assert (
        sorted((costs[t.entry_id], t.delivered) for t in row.result.by_tunnel) == joined
    )
    assert row.cost_distribution.kind == "delivered_by_path_cost"
    assert [
        (item.cost, item.physical_path_cost, item.delivered_units)
        for item in row.cost_distribution.bins
    ] == bins
    assert sum(
        item.cost * item.delivered_units for item in row.cost_distribution.bins
    ) == sum(c * d for c, d in joined)
    wire = project(result)["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    assert wire["cost_distribution"]["bins"] == [
        {"cost": c, "physical_path_cost": p, "delivered_units": d} for c, p, d in bins
    ]
