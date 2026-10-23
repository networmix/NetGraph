"""Independent two-route integer-slot oracles for lossless TE pool presets."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.placement import (
    PlacementQuery,
    place,
    policy_roster,
    remove_policies,
    replace_matrix,
)
from ngraph.analysis.topology import eligibility
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.results import SyntheticIngress
from ngraph.scenario import Scenario, prepare


def count_vectors(count, cheap, wide, size):
    """Every integer path-count vector, tested against both path bottlenecks."""
    return tuple(
        (left, count - left)
        for left in range(count + 1)
        if left * size <= cheap and (count - left) * size <= wide
    )


def fluid_oracle(count, cheap, wide):
    # The only simple routes from h terminate at t: h-s1-t or h-s2-t.
    candidates = []
    for left in range(count + 1):
        right = count - left
        limits = []
        if left:
            limits.append(Fraction(cheap, left))
        if right:
            limits.append(Fraction(wide, right))
        candidates.append(min(limits))
    return max(candidates)


def integer_oracle(count, cheap, wide, design):
    fractional = fluid_oracle(count, cheap, wide)
    maximum = fractional.numerator // fractional.denominator
    if maximum == 0:
        return fractional, 0, 0, (0, 0), 0
    working = min(maximum, max(1, (design + count - 1) // count))
    vectors = count_vectors(count, cheap, wide, working)
    # J=2*ncheap+4*nwide; the cheaper vector is unique in these witnesses.
    vector = min(vectors, key=lambda row: 2 * row[0] + 4 * row[1])
    # Native's canonical decomposition puts the lower-id cheap route first.
    route_capacities = (cheap,) * vector[0] + (wide,) * vector[1]
    route_group = (0,) * vector[0] + (1,) * vector[1]
    maximum_offer = 0
    for offer in range(cheap + wide + 1):
        base, remainder = divmod(offer, count)
        carried = [0, 0]
        for index, group in enumerate(route_group):
            carried[group] += base + (index < remainder)
        if carried[0] <= cheap and carried[1] <= wide:
            maximum_offer = offer
    assert len(route_capacities) == count
    return fractional, maximum, working, vector, maximum_offer


def up_to_oracle(limit, cheap, wide, design):
    best = None
    for count in range(1, limit + 1):
        row = integer_oracle(count, cheap, wide, design)
        score = row[4]
        if best is None or score > best[1][4]:
            best = (count, row)
        if score >= design:
            return count, row
    return best


def prepared(preset, *, copies=1, design=32):
    network = Network()
    for name in ("s2", "t", "s1"):
        network.add_node(Node(name))
    network.add_link(Link("s1", "t", 16, 1))
    network.add_link(Link("s2", "t", 32, 3))
    specs = DemandSet(
        "load",
        tuple(
            DemandSpec(Selector("^s"), Selector("^t$"), design, preset)
            for _ in range(copies)
        ),
    )
    preparation = prepare(
        Scenario(network, demand_sets={"load": specs}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    return preparation, preparation.demand_sets["load"]


def verify(topology, demand, native, expected, count, design, cheap, wide):
    fractional, maximum, working, vector, maximum_offer = expected
    plan = native.plan
    assert plan.max_fractional_bandwidth_per_tunnel == fractional
    assert plan.max_bandwidth_per_tunnel == maximum
    assert plan.planned_bandwidth_per_tunnel == working
    assert plan.tunnels_per_head == count
    assert plan.total_reserved_bandwidth == 0
    assert plan.total_planned_bandwidth == count * working
    assert plan.total_tunnel_cost == 2 * vector[0] + 4 * vector[1]
    penalty = 2 * sum(
        ((1 << 32) * (baseline - available + slot * working)) // baseline
        for baseline, available, copies in (
            (16, cheap, vector[0]),
            (32, wide, vector[1]),
        )
        for slot in range(1, copies + 1)
    )
    assert plan.headroom_penalty == penalty
    assert plan.max_lossless_offer == maximum_offer
    assert plan.insufficient_resolution is (maximum == 0 and cheap + wide > 0)
    (head,) = native.program.sources
    assert head >= len(topology.node_names)
    assert plan.design_by_head == ((head, design),)
    assert plan.heads_with_capacity == ((head,) if cheap + wide else ())
    assert demand.pool.head.physical_sources == ("s1", "s2")
    assert (
        demand.pool.offer_limit_units == 0 and demand.pool.synthetic_ingress_cost == 1
    )
    assert native.delivered == min(design, maximum_offer)
    assert native.unadmitted == design - native.delivered
    assert native.admitted == native.delivered
    assert native.source_drops == 0 and native.edge_drops == []
    assert native.total_cost is None and native.marginal_cost_curve is None
    assert native.min_cut is None
    assert len(native.program.tunnels) == count
    assert [tunnel.entry_id for tunnel in native.program.tunnels] == list(range(count))
    assert all(
        tunnel.planned_bandwidth == working and tunnel.reserved_bandwidth == 0
        for tunnel in native.program.tunnels
    )
    by_entry = {flow.entry_id: flow for flow in native.by_tunnel}
    actual_counts = [0, 0]
    actual_delivery = [0, 0]
    for tunnel in native.program.tunnels:
        assert tunnel.status == ngc.TunnelStatus.UP
        assert tunnel.requested_bandwidth == 0
        assert tunnel.weight == 1
        assert len(tunnel.edges) == 2
        ingress = topology.edge_refs[tunnel.edges[0]]
        assert isinstance(ingress, SyntheticIngress)
        group = 0 if ingress.source == "s1" else 1
        actual_counts[group] += 1
        assert tunnel.path_cost == (2 if group == 0 else 4)
        actual_delivery[group] += by_entry[tunnel.entry_id].delivered
        assert by_entry[tunnel.entry_id].assigned == by_entry[tunnel.entry_id].delivered
        assert by_entry[tunnel.entry_id].total_edge_drops == 0
    assert tuple(actual_counts) == vector
    flows = native.edge_flows
    named = {ref: int(flows[index]) for index, ref in enumerate(topology.edge_refs)}
    for index, source in enumerate(("s1", "s2")):
        ingress = SyntheticIngress(demand.pool.head.pool_id, source)
        assert named[ingress] == actual_delivery[index]
        forward, reverse = topology.edges_by_link[f"{source}|t|0"]
        assert int(flows[forward]) == actual_delivery[index]
        assert int(flows[reverse]) == 0
    assert actual_delivery[0] <= cheap and actual_delivery[1] <= wide
    assert sum(actual_delivery) == native.delivered
    assert not native.edge_reservations.any()


@pytest.mark.parametrize(
    "preset", [FlowPolicyPreset.TE_ECMP_16_LSP, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP]
)
@pytest.mark.parametrize(
    "failed_node,failed_link,cheap,wide",
    [
        (None, None, 16, 32),
        ("s1", None, 0, 32),
        (None, "s2|t|0", 16, 0),
        (None, "s1|t|0", 0, 32),
    ],
)
def test_pool_counts_fraction_floor_working_size_costs_and_failures(
    preset, failed_node, failed_link, cheap, wide
):
    context, demands = prepared(preset)
    topology = context.topology
    mask = eligibility(
        topology,
        excluded_nodes=() if failed_node is None else (failed_node,),
        excluded_links=() if failed_link is None else (failed_link,),
    )
    if preset == FlowPolicyPreset.TE_ECMP_16_LSP:
        count, expected = 16, integer_oracle(16, cheap, wide, 32)
    else:
        count, expected = up_to_oracle(256, cheap, wide, 32)
    ledger, owners = policy_roster(topology, demands.demands, mask)
    try:
        (result,) = replace_matrix(
            ledger,
            owners,
            [32],
            ngc.OutputOptions(edge_flows=True, edge_reservations=True, min_cut=True),
        )
        verify(topology, demands.demands[0], result, expected, count, 32, cheap, wide)
        if not failed_node and not failed_link and count == 16:
            assert expected[:3] == (Fraction(32, 11), 2, 2)
            assert expected[3] == (8, 8)
    finally:
        remove_policies(owners)
    assert not ledger.carried().any() and not ledger.reserved().any()


def test_up_to_finite_design_changes_working_route_and_keeps_its_maximum():
    context, demands = prepared(FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP, design=16)
    result = place(
        context,
        PlacementQuery(
            demands,
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=True, edge_reservations=True),
            export_cost_distribution=True,
        ),
    )
    (row,) = result.cases[0].states["converged"].rows
    count, expected = up_to_oracle(256, 16, 32, 16)
    verify(
        context.topology, demands.demands[0], row.result, expected, count, 16, 16, 32
    )
    assert expected[:4] == (Fraction(32), 32, 16, (1, 0))
    assert [
        (bin.cost, bin.physical_path_cost, bin.delivered_units)
        for bin in row.cost_distribution.bins
    ] == [(2, 1, 16)]


@pytest.mark.parametrize(
    "preset,first,second",
    [
        (FlowPolicyPreset.TE_ECMP_16_LSP, (16, 16), (0, 16)),
        (FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP, (0, 32), (16, 0)),
    ],
)
def test_multiple_pools_compete_on_one_physical_ledger(preset, first, second):
    context, demands = prepared(preset, copies=2)
    analysis = place(
        context,
        PlacementQuery(demands, workers=1, outputs=ngc.OutputOptions(edge_flows=True)),
    )
    rows = analysis.cases[0].states["converged"].rows
    assert [row.result.delivered for row in rows] == [32, 16]
    assert analysis.cases[0].states["converged"].totals.delivered_units == 48
    for row, expected in zip(rows, (first, second), strict=True):
        flows = row.result.edge_flows
        actual = tuple(
            int(flows[context.topology.edges_by_link[f"{source}|t|0"][0]])
            for source in ("s1", "s2")
        )
        assert actual == expected
        assert sum(actual) == row.result.delivered
    assert rows[0].pool.head.pool_id != rows[1].pool.head.pool_id


def test_a_pool_reused_with_other_sources_is_refused_and_the_same_sources_rebind():
    network = Network(nodes={name: Node(name) for name in ("s1", "s2", "t")})
    network.add_link(Link("s1", "t", 16))
    network.add_link(Link("s2", "t", 0))

    def demands(source):
        spec = DemandSpec(
            Selector(f"^{source}$"),
            Selector("^t$"),
            16,
            FlowPolicyPreset.TE_ECMP_16_LSP,
        )
        return DemandSet("d", (spec,))

    prepared = prepare(
        Scenario(network, demand_sets={"d": demands("s1")}, units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    # The pool d|0|0 is s1's ingress; s2 would deliver 0 through its own.
    with pytest.raises(
        ValueError,
        match=r"demand set d: pools \['d\|0\|0'\] select other sources than "
        "their prepared ingress; prepare again",
    ):
        resolve_demands(prepared, demands("s2"))
    again = resolve_demands(prepared, demands("s1"))
    assert again == prepared.demand_sets["d"]
    row = place(prepared, PlacementQuery(again, workers=1)).cases[0]
    assert row.states["converged"].rows[0].result.delivered == 16
    best = maximum_supported_demand(prepared, MSDQuery(again)).alpha_feasible
    assert best is not None
    assert (
        best
        == maximum_supported_demand(
            prepared, MSDQuery(prepared.demand_sets["d"])
        ).alpha_feasible
    )
