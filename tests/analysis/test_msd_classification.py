"""Sufficient MSD proofs and an independently enumerated feasibility re-entry."""

from itertools import product

import netgraph_core as ngc
import pytest

from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from tests.prepared import prepare_network


def _classification(model, count=1):
    network = Network(nodes={name: Node(name) for name in ("s", "t")})
    network.add_link(Link("s", "t", 4, 3))
    prepared = prepare_network(network)
    config = ngc.FlowPolicyConfig(routing=model(prepared.topology))
    demands = resolve_demands(
        prepared,
        DemandSet(
            "load",
            tuple(
                DemandSpec(Selector("^s$"), Selector("^t$"), 1, config)
                for _ in range(count)
            ),
        ),
    )
    return maximum_supported_demand(
        prepared,
        MSDQuery(demands, alpha_tolerance=1, max_bracket_iters=4),
    )


@pytest.mark.parametrize(
    "model",
    [
        lambda _: ngc.ShortestPaths(),
        lambda _: ngc.ShortestPaths(
            tie_break=ngc.RouteTieBreak.HIGHER_CAPACITY, multipath=False
        ),
        lambda _: ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.CAPACITY,
        ),
        lambda _: ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights=[3, 2],
        ),
        lambda topology: ngc.Pinned(
            ngc.ForwardingProgram.from_dag(
                topology.graph,
                [0],
                [1],
                ngc.spf(
                    topology.graph, [1], ngc.SpfOptions(direction=ngc.Direction.REVERSE)
                ).dag,
            )
        ),
    ],
)
def test_static_programs_have_only_tested_upper_certificates(model):
    result = _classification(model, count=2)
    assert result.proof == "fixed_program" and result.monotone_proven
    certificate = result.upper_certificate
    assert certificate is not None
    assert certificate.lower == result.alpha_feasible
    assert result.history[certificate.lower_probe_index].outcome == "feasible"
    assert result.history[certificate.upper_probe_index].outcome == "infeasible"
    assert certificate.lower.value < certificate.upper.value


@pytest.mark.parametrize(
    "model",
    [
        lambda _: ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
        lambda _: ngc.ShortestPaths(allocation=ngc.RouteAllocation.OPTIMIZED),
        lambda _: ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.OPTIMIZED,
            source_allocation=ngc.SourceAllocation.EQUAL,
        ),
    ],
)
def test_single_controller_proof_does_not_extend_to_two_controllers(model):
    single = _classification(model)
    assert single.proof == "single_controller" and single.monotone_proven
    assert single.upper_certificate is not None
    multiple = _classification(model, count=2)
    assert multiple.proof == "unproved" and not multiple.monotone_proven
    assert multiple.upper_certificate is None


@pytest.mark.parametrize(
    "model",
    [
        lambda _: ngc.ShortestPaths(
            tie_break=ngc.RouteTieBreak.HIGHER_AVAILABLE_CAPACITY, multipath=False
        ),
        lambda _: ngc.ShortestPaths(
            tie_break=ngc.RouteTieBreak.HIGHER_HEADROOM, multipath=False
        ),
        lambda _: ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.RESIDUAL_SNAPSHOT,
        ),
        lambda _: ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.OPTIMIZED,
            tie_break=ngc.RouteTieBreak.HIGHER_HEADROOM,
            multipath=False,
        ),
        lambda _: ngc.DistributedTE(ngc.TunnelCount(2)),
        lambda _: ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        ),
    ],
)
def test_dynamic_route_choices_and_tunnel_redesigns_are_unproved(model):
    result = _classification(model)
    assert result.proof == "unproved" and not result.monotone_proven
    assert result.upper_certificate is None


FIVE_EDGES = ((0, 1, 1), (1, 2, 1), (2, 3, 1), (0, 2, 3), (1, 3, 3))


def _integer_optimum(available, source, target, offer):
    best = None
    for vector in product(*(range(capacity + 1) for capacity in available)):
        balance = [0] * 4
        cost = 0
        for units, (tail, head, unit_cost) in zip(vector, FIVE_EDGES, strict=True):
            balance[tail] -= units
            balance[head] += units
            cost += units * unit_cost
        delivered = balance[target]
        if balance[source] != -delivered or not 0 <= delivered <= offer:
            continue
        if any(
            value for node, value in enumerate(balance) if node not in (source, target)
        ):
            continue
        rank = (-delivered, cost, vector)
        if best is None or rank < best:
            best = rank
    assert best is not None
    return -best[0], best[1], best[2]


def test_two_ordered_controllers_have_feasibility_reentry_and_exact_optima():
    # A directed native witness, with no new directed physical-network input.
    graph = ngc.Graph(
        4,
        [edge[0] for edge in FIVE_EDGES],
        [edge[1] for edge in FIVE_EDGES],
        [4] * 5,
        [edge[2] for edge in FIVE_EDGES],
        1,
    )
    ledger = ngc.FlowLedger(graph)
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    policies = (
        ngc.FlowPolicy(ledger, [0], [3], config),
        ngc.FlowPolicy(ledger, [1], [2], config),
    )
    permutation = [int(position) for position in graph.input_positions()]
    feasible = []
    first_vectors = ((2, 2, 2, 0, 0), (4, 4, 4, 0, 0), (4, 2, 4, 2, 2), (4, 0, 4, 4, 4))
    try:
        for alpha, expected_first, expected_second in zip(
            (0.25, 0.5, 0.75, 1), first_vectors, (1, 0, 2, 4), strict=True
        ):
            for policy in policies:
                policy.remove()
            assert all(value == 0 for value in ledger.carried())
            offers = (int(8 * alpha), int(4 * alpha))
            results = ngc.apply_actions(
                ledger,
                [
                    ngc.Replace(policy, offer)
                    for policy, offer in zip(policies, offers, strict=True)
                ],
                mode=ngc.BatchMode.ORDERED,
                outputs=ngc.OutputOptions(edge_flows=True, min_cut=True),
            )
            available = [4] * 5
            for index, (result, offer, endpoints) in enumerate(
                zip(results, offers, ((0, 3), (1, 2)), strict=True)
            ):
                optimum, cost, expected = _integer_optimum(available, *endpoints, offer)
                actual = [0] * 5
                for edge_id, input_position in enumerate(permutation):
                    actual[input_position] = int(result.edge_flows[edge_id])
                assert tuple(actual) == expected
                assert result.delivered == optimum and result.total_cost == cost
                assert (
                    result.requested == offer and result.unadmitted == offer - optimum
                )
                assert result.source_drops == 0 and result.edge_drops == []
                assert result.by_source[0].delivered == optimum
                if result.min_cut is not None:
                    assert (
                        sum(available[permutation[edge]] for edge in result.min_cut)
                        == optimum
                    )
                if index == 0:
                    assert expected == expected_first
                else:
                    assert optimum == expected_second
                available = [
                    capacity - units
                    for capacity, units in zip(available, actual, strict=True)
                ]
            feasible.append(
                all(
                    result.delivered == offer
                    for result, offer in zip(results, offers, strict=True)
                )
            )
        assert feasible == [True, False, False, True]
    finally:
        for policy in policies:
            policy.remove()
    assert all(value == 0 for value in ledger.carried())
