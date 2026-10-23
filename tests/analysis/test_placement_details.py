"""Native requested arrays and physical cost bins describe carried traffic."""

import netgraph_core as ngc

from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


def test_placement_requested_costs_and_edges():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C", "D")})
    for source, target, cost in (
        ("A", "B", 1),
        ("B", "D", 1),
        ("A", "C", 2),
        ("C", "D", 2),
    ):
        network.add_link(Link(source, target, 100, cost))
    demands = DemandSet("load", (DemandSpec(Selector("^A$"), Selector("^D$"), 150),))
    prepared = prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    query = PlacementQuery(
        prepared.demand_sets["load"],
        workers=1,
        outputs=ngc.OutputOptions(edge_flows=True),
        export_cost_distribution=True,
    )
    (row,) = place(prepared, query).cases[0].states["converged"].rows
    assert row.result.requested == 150 and row.result.delivered == 100
    assert row.result.unadmitted == 50 and row.result.source_drops == 0
    assert [
        (bin.cost, bin.physical_path_cost, bin.delivered_units)
        for bin in row.cost_distribution.bins
    ] == [(2, 2, 100)]
    actual = {
        (ref.link, ref.direction): int(units)
        for ref, units in zip(
            prepared.topology.edge_refs, row.result.edge_flows, strict=True
        )
        if units
    }
    assert actual == {("A|B|0", "forward"): 100, ("B|D|0", "forward"): 100}
    assert (
        sum(bin.delivered_units for bin in row.cost_distribution.bins)
        == row.result.delivered
    )
    (default,) = (
        place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
        .cases[0]
        .states["converged"]
        .rows
    )
    assert default.cost_distribution is default.result.edge_flows is None
