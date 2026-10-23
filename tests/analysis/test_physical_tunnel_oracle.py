"""Physical-head count, reservation/traffic and dead/live witnesses."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.topology import compile_topology
from ngraph.model.network import Link, Network, Node


def network(heads, links):
    model = Network()
    for name in (*heads, "t"):
        model.add_node(Node(name))
    for source, capacity, cost in links:
        model.add_link(Link(source, "t", capacity, cost))
    return compile_topology(model, 1)


def evaluate(
    topology, model, design, offer, admission=ngc.Admission.LOSSLESS, sources=None
):
    return ngc.evaluate_demand(
        topology.graph,
        [index for name, index in topology.node_id_by_name.items() if name != "t"]
        if sources is None
        else sources,
        [topology.node_id_by_name["t"]],
        ngc.EvaluationOptions(
            ngc.FlowPolicyConfig(routing=model, admission=admission),
            design_demand=design,
            offer=offer,
            outputs=ngc.OutputOptions(edge_flows=True, edge_reservations=True),
        ),
    )


def forward(topology, vector):
    return tuple(
        int(vector[topology.edges_by_link[link][0]])
        for link in sorted(topology.edges_by_link)
    )


def test_t1_two_heads_get_n_each_in_round_order():
    topology = network(("a", "b"), (("a", 10, 1), ("b", 10, 3)))
    result = evaluate(topology, ngc.DistributedTE(ngc.TunnelCount(2)), 5, 5)
    assert result.plan.design_by_head == ((0, 3), (1, 2))
    assert result.plan.tunnels_per_head == 2
    assert [
        (t.entry_id, t.head, t.requested_bandwidth, t.reserved_bandwidth)
        for t in result.program.tunnels
    ] == [(0, 0, 2, 2), (1, 1, 1, 1), (2, 0, 1, 1), (3, 1, 1, 1)]
    assert [flow.delivered for flow in result.by_tunnel] == [2, 1, 1, 1]
    assert result.plan.total_reserved_bandwidth == 5
    assert forward(topology, result.edge_flows) == (3, 2)
    assert forward(topology, result.edge_reservations) == (3, 2)
    assert result.delivered == 5 and result.unadmitted == 0
    assert result.plan.max_bandwidth_per_tunnel is None
    assert result.plan.max_fractional_bandwidth_per_tunnel is None
    assert result.plan.planned_bandwidth_per_tunnel is None
    assert result.plan.total_planned_bandwidth is None
    assert result.plan.total_tunnel_cost is None
    assert result.plan.headroom_penalty is None
    assert result.plan.max_lossless_offer is None
    assert result.plan.heads_with_capacity is None
    assert result.plan.insufficient_resolution is None


def test_t1_holds_do_not_cap_or_add_to_carried_traffic():
    topology = network(("a",), (("a", 5, 1), ("a", 5, 2)))
    result = evaluate(
        topology, ngc.DistributedTE(ngc.TunnelCount(2)), 8, 10, ngc.Admission.LOSSY
    )
    assert [t.reserved_bandwidth for t in result.program.tunnels] == [4, 4]
    assert result.plan.total_reserved_bandwidth == 8
    assert forward(topology, result.edge_reservations) == (4, 4)
    assert forward(topology, result.edge_flows) == (5, 5)
    assert result.offered == result.admitted == result.delivered == 10
    assert result.source_drops == 0 and result.edge_drops == []
    assert [flow.assigned for flow in result.by_tunnel] == [5, 5]
    assert [flow.delivered for flow in result.by_tunnel] == [5, 5]


def test_t1_zero_design_installs_up_zero_request_tunnels():
    topology = network(("a",), (("a", 10, 1),))
    result = evaluate(
        topology, ngc.DistributedTE(ngc.TunnelCount(2)), 0, 4, ngc.Admission.LOSSY
    )
    assert len(result.program.tunnels) == 2
    assert all(
        t.status == ngc.TunnelStatus.UP
        and t.requested_bandwidth == t.reserved_bandwidth == 0
        for t in result.program.tunnels
    )
    assert result.plan.total_reserved_bandwidth == 0
    assert [flow.delivered for flow in result.by_tunnel] == [2, 2]
    assert forward(topology, result.edge_flows) == (4,)
    assert not result.edge_reservations.any()


def test_t1_zero_share_uses_zero_capacity_static_route():
    topology = network(("a",), (("a", 0, 1), ("a", 10, 2)))
    model = ngc.DistributedTE(ngc.TunnelCount(2))
    lossy = evaluate(topology, model, 1, 2, ngc.Admission.LOSSY)
    assert [t.requested_bandwidth for t in lossy.program.tunnels] == [1, 0]
    assert [t.path_cost for t in lossy.program.tunnels] == [2, 1]
    assert lossy.delivered == 1 and sum(amount for _, amount in lossy.edge_drops) == 1
    assert lossy.offered == lossy.delivered + lossy.source_drops + sum(
        amount for _, amount in lossy.edge_drops
    )
    assert [flow.delivered for flow in lossy.by_tunnel] == [1, 0]
    assert [flow.total_edge_drops for flow in lossy.by_tunnel] == [0, 1]
    assert evaluate(topology, model, 1, 2).delivered == 1


def test_t2_unequal_capacity_heads_common_count_and_equal_injections():
    topology = network(("a", "b"), (("a", 3, 1), ("b", 8, 3)))
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL, tunnel_count=ngc.TunnelCount(2)
    )
    result = evaluate(topology, model, 6, 6)
    assert result.plan.max_fractional_bandwidth_per_tunnel == Fraction(3, 2)
    assert (
        result.plan.max_bandwidth_per_tunnel
        == result.plan.planned_bandwidth_per_tunnel
        == 1
    )
    assert result.plan.total_planned_bandwidth == 4
    assert result.plan.max_lossless_offer == 6
    assert result.plan.total_tunnel_cost == 8
    assert result.plan.headroom_penalty is None
    assert result.plan.heads_with_capacity == (0, 1)
    assert result.plan.design_by_head == ((0, 3), (1, 3))
    assert [(t.entry_id, t.head) for t in result.program.tunnels] == [
        (0, 0),
        (1, 1),
        (2, 0),
        (3, 1),
    ]
    assert forward(topology, result.edge_flows) == (3, 3)
    assert result.delivered == 6 and result.unadmitted == 0
    assert not result.edge_reservations.any()
    optimized = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.OPTIMIZED,
        tunnel_count=ngc.TunnelCount(2),
    )
    with pytest.raises(
        ValueError, match="several sources requires source_allocation=EQUAL"
    ):
        evaluate(topology, optimized, 6, 6)
    assert evaluate(topology, optimized, 2, 2, sources=[0]).delivered == 2


def test_t2_live_fraction_below_one_and_dead_head_are_distinct():
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL, tunnel_count=ngc.TunnelCount(16)
    )
    tiny = network(("a", "b"), (("a", 1, 1), ("b", 100, 3)))
    result = evaluate(tiny, model, 32, 32)
    assert result.plan.max_fractional_bandwidth_per_tunnel == Fraction(1, 16)
    assert (
        result.plan.max_bandwidth_per_tunnel
        == result.plan.planned_bandwidth_per_tunnel
        == 0
    )
    assert result.plan.insufficient_resolution
    assert result.plan.heads_with_capacity == (0, 1)
    assert result.program.tunnels == ()
    assert result.delivered == 0 and result.unadmitted == 32
    lossy = evaluate(tiny, model, 32, 32, ngc.Admission.LOSSY)
    assert lossy.delivered == 0 and lossy.source_drops == 32
    dead = network(("a", "b"), (("a", 0, 1), ("b", 10, 3)))
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL, tunnel_count=ngc.TunnelCount(2)
    )
    result = evaluate(dead, model, 10, 10, ngc.Admission.LOSSY)
    assert result.plan.max_fractional_bandwidth_per_tunnel == Fraction(5)
    assert result.plan.max_bandwidth_per_tunnel == 5
    assert result.plan.planned_bandwidth_per_tunnel == 3
    assert result.plan.total_planned_bandwidth == 6
    assert result.plan.heads_with_capacity == (1,)
    assert not result.plan.insufficient_resolution
    assert [t.entry_id for t in result.program.tunnels] == [1, 3]
    assert result.delivered == result.source_drops == 5
    assert result.edge_drops == []
    assert evaluate(dead, model, 10, 10).delivered == 0


def test_t2_up_to_uses_one_common_count_and_small_count_can_avoid_zero_units():
    topology = network(("a", "b"), (("a", 6, 1), ("b", 3, 1), ("b", 3, 2)))
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL,
        tunnel_count=ngc.TunnelCount(2, up_to=True),
    )
    result = evaluate(topology, model, 12, 12)
    assert result.plan.tunnels_per_head == 2
    assert (
        result.plan.max_bandwidth_per_tunnel
        == result.plan.planned_bandwidth_per_tunnel
        == 3
    )
    assert result.plan.total_planned_bandwidth == result.delivered == 12
    assert forward(topology, result.edge_flows) == (6, 3, 3)
    tiny = network(("a", "b"), (("a", 1, 1), ("b", 100, 3)))
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL,
        tunnel_count=ngc.TunnelCount(3, up_to=True),
    )
    result = evaluate(tiny, model, 2, 2)
    assert result.plan.tunnels_per_head == 1
    assert (
        result.plan.max_bandwidth_per_tunnel
        == result.plan.planned_bandwidth_per_tunnel
        == 1
    )
    assert result.delivered == 2


def test_t2_zero_design_planned_bandwidth_does_not_police_offer():
    topology = network(("a",), (("a", 10, 1),))
    model = ngc.CentralizedTE(
        source_allocation=ngc.SourceAllocation.EQUAL, tunnel_count=ngc.TunnelCount(2)
    )
    result = evaluate(topology, model, 0, 4, ngc.Admission.LOSSY)
    assert result.plan.max_fractional_bandwidth_per_tunnel == Fraction(5)
    assert result.plan.max_bandwidth_per_tunnel == 5
    assert result.plan.planned_bandwidth_per_tunnel == 1
    assert result.plan.total_planned_bandwidth == 2
    assert result.plan.max_lossless_offer == 10
    assert result.delivered == 4
    assert forward(topology, result.edge_flows) == (4,)
    assert (
        result.plan.total_reserved_bandwidth == 0 and not result.edge_reservations.any()
    )


@pytest.mark.parametrize(
    "ceiling,delivered",
    [
        (ngc.AbsoluteCost(1), 0),
        (ngc.AbsoluteCost(2), 1),
        (ngc.CostStretch(Fraction(1)), 0),
        (ngc.CostStretch(Fraction(2)), 1),
    ],
)
def test_t1_inclusive_cost_ceiling_uses_static_base_even_if_zero_capacity(
    ceiling, delivered
):
    topology = network(("a",), (("a", 0, 1), ("a", 10, 2)))
    model = ngc.DistributedTE(ngc.TunnelCount(1), cost_ceiling=ceiling)
    result = evaluate(topology, model, 1, 1)
    assert result.delivered == delivered
    assert result.unadmitted == 1 - delivered
    if delivered:
        assert result.program.tunnels[0].path_cost == 2
    else:
        assert (
            result.program.tunnels[0].status == ngc.TunnelStatus.COST_CEILING_EXCEEDED
        )


def test_t1_up_to_refusal_has_exact_count_control():
    topology = network(("a",), (("a", 10, 1),))
    with pytest.raises(
        ValueError, match="DistributedTE requires an exact tunnel count"
    ):
        evaluate(topology, ngc.DistributedTE(ngc.TunnelCount(2, up_to=True)), 2, 2)
    assert (
        evaluate(topology, ngc.DistributedTE(ngc.TunnelCount(2)), 2, 2).delivered == 2
    )
