"""Cost reports use delivered traffic and preserve marginal/path meanings."""

import netgraph_core as ngc

from ngraph.analysis.costs import cost_distribution
from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.placement import policy_roster, remove_policies, replace_matrix
from ngraph.analysis.topology import compile_topology
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.results import DeliveredByPathCost, MarginalCurve
from tests.prepared import prepare_network


def test_shortest_sources_have_distinct_exact_cost_bins():
    network = Network()
    for name in ("a", "b", "t"):
        network.add_node(Node(name))
    network.add_link(Link("a", "t", 3, 2))
    network.add_link(Link("b", "t", 4, 5))
    topology = compile_topology(network, 1)
    config = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    destinations = [topology.node_id_by_name["t"]]
    result = ngc.evaluate_demand(
        topology.graph,
        [topology.node_id_by_name["a"], topology.node_id_by_name["b"]],
        destinations,
        ngc.EvaluationOptions(config, offer=8),
    )
    report, unavailable = cost_distribution(
        topology, config, result, destinations, topology.disabled
    )
    # RR8 gives4/4: equal-source lossless prefix stops at6, giving3/3.
    assert isinstance(report, DeliveredByPathCost)
    assert [
        (row.cost, row.physical_path_cost, row.delivered_units) for row in report.bins
    ] == [(2, 2, 3), (5, 5, 3)]
    assert report.cost_domain == "physical_network" and not unavailable
    lossy = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
    )
    result = ngc.evaluate_demand(
        topology.graph, [0, 1], destinations, ngc.EvaluationOptions(lossy, offer=8)
    )
    report, unavailable = cost_distribution(
        topology, lossy, result, destinations, topology.disabled
    )
    assert [(row.cost, row.delivered_units) for row in report.bins] == [(2, 3), (5, 4)]
    assert not unavailable


def test_controller_curve_is_not_a_path_histogram():
    network = Network()
    for name in ("a", "b", "t"):
        network.add_node(Node(name))
    network.add_link(Link("a", "b", 2, 1))
    network.add_link(Link("b", "t", 2, 2))
    network.add_link(Link("a", "t", 3, 5))
    prepared = prepare_network(network)
    topology = prepared.topology
    demands = resolve_demands(
        prepared,
        DemandSet(
            "load",
            (
                DemandSpec(
                    Selector("^a$"),
                    Selector("^t$"),
                    5,
                    FlowPolicyPreset.TE_MAXFLOW_UNLIM,
                ),
            ),
        ),
    )
    ledger, policies = policy_roster(topology, demands.demands, topology.disabled)
    try:
        (result,) = replace_matrix(ledger, policies, [5])
        report, unavailable = cost_distribution(
            topology, demands.demands[0].config, result, [2], topology.disabled
        )
        assert isinstance(report, MarginalCurve)
        assert [(row.marginal_cost, row.units) for row in report.bins] == [
            (3, 2),
            (5, 3),
        ]
        assert (
            sum(row.marginal_cost * row.units for row in report.bins)
            == result.total_cost
            == 21
        )
        assert not unavailable
    finally:
        remove_policies(policies)
