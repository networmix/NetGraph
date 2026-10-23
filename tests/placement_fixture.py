"""Owned typed matrix fixtures; all traffic goes through the public native path."""

import netgraph_core as ngc

from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Condition, Selector
from ngraph.scenario import Scenario, prepare


def network_of(edges, *, nodes=()):
    names = set(nodes) | {name for edge in edges for name in edge[:2]}
    network = Network(nodes={name: Node(name) for name in sorted(names)})
    for source, target, amount, cost in edges:
        network.add_link(Link(source, target, amount, cost))
    return network


def demand(
    source, target, volume, policy=FlowPolicyPreset.SHORTEST_PATHS_ECMP, **kwargs
):
    return DemandSpec(Selector(source), Selector(target), volume, policy, **kwargs)


def matrix(network, specs, *, q=1, excluded_nodes=(), excluded_links=(), details=False):
    prepared = prepare(
        Scenario(
            network,
            demand_sets={"load": DemandSet("load", tuple(specs))},
            units=UnitsSettings(q),
        ),
        demand_sets=("load",),
    )
    rules = []
    for scope, names in (("node", excluded_nodes), ("link", excluded_links)):
        if names:
            rules.append(
                FailureRule(
                    scope,
                    [Condition("name" if scope == "node" else "id", "in", list(names))],
                )
            )
    failures = (
        FailureRequest(FailurePolicy(modes=[FailureMode(1, rules)]), 1, 42)
        if rules
        else None
    )
    result = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"],
            failures=failures,
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=details),
            export_cost_distribution=details,
        ),
    )
    return prepared, result.cases[-1].states["converged"]


def named_flows(prepared, row):
    return {
        (ref.link, ref.direction): int(value)
        for ref, value in zip(
            prepared.topology.edge_refs, row.result.edge_flows, strict=True
        )
        if value
    }
