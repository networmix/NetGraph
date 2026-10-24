"""Opt-in exact path-cost bins or native marginal-cost pieces."""

from collections import defaultdict
from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

import netgraph_core as ngc

from ngraph.analysis.topology import PreparedTopology
from ngraph.results import (
    CostReport,
    CostUnavailableReason,
    DeliveredByPathCost,
    MarginalCostBin,
    MarginalCurve,
    PathCostBin,
)


def cost_distribution(
    topology: PreparedTopology,
    config: ngc.FlowPolicyConfig,
    result: ngc.PlacementResult,
    destinations,
    mask: ngc.Eligibility,
    *,
    pool=None,
    records=None,
    shortest_costs=None,
    programmed=False,
) -> tuple[
    CostReport | None, Mapping[Literal["cost_distribution"], CostUnavailableReason]
]:
    """Project only determined costs; callers invoke this only when requested.

    A demand the WCMP controller ``programmed`` forwards on a pooled table,
    which does not attribute delivery to walk costs.
    """
    if programmed:
        return None, MappingProxyType({"cost_distribution": "controller_table"})
    model = config.routing
    domain: Literal["analysis_graph", "physical_network"] = (
        "analysis_graph" if pool is not None else "physical_network"
    )
    if (
        isinstance(model, ngc.CentralizedTE)
        and model.tunnel_count is None
        and model.support is None
        and model.source_allocation == ngc.SourceAllocation.OPTIMIZED
    ):
        curve = result.marginal_cost_curve
        if curve is None and result.delivered:
            raise ValueError(
                "cost_distribution: unrestricted controller omitted its curve"
            )
        return MarginalCurve(
            domain,
            tuple(MarginalCostBin(cost, units) for cost, units in (curve or ())),
        ), MappingProxyType({})
    bins = defaultdict(int)
    if isinstance(model, ngc.ShortestPaths):
        if records is not None:
            for record in records:
                delivered = record.delivered
                if delivered:
                    cost = record.min_route_cost
                    if cost is None:
                        raise ValueError(
                            "cost_distribution: positive shortest-path delivery has no route cost"
                        )
                    bins[cost] += delivered
        else:
            # Native cost-only SPF supplies the cost, without placing traffic again.
            costs = shortest_costs
            if costs is None:
                search = ngc.spf(
                    topology.graph,
                    destinations,
                    ngc.SpfOptions(ngc.Direction.REVERSE, eligibility=mask),
                )
                costs = search.costs
            assert costs is not None
            sources = result.by_source
            for source in sources:
                delivered = source.delivered
                if delivered:
                    cost = int(costs[source.source])
                    if cost == ngc.UNREACHABLE:
                        raise ValueError(
                            "cost_distribution: positive source delivery has no route cost"
                        )
                    bins[cost] += delivered
    else:
        program = result.program
        tunnels = program.tunnels if program is not None else ()
        costs = {tunnel.entry_id: tunnel.path_cost for tunnel in tunnels}
        flows = result.by_tunnel
        accounted = 0
        for flow in flows:
            delivered = flow.delivered
            if not delivered:
                continue
            cost = costs.get(flow.entry_id)
            if cost is None:
                raise ValueError(
                    f"cost_distribution: positive entry {flow.entry_id} delivery has no path cost"
                )
            bins[cost] += delivered
            accounted += delivered
        if accounted != result.delivered:
            reason = (
                "mixed_cost_dag"
                if isinstance(model, ngc.Pinned)
                else "unsupported_model"
            )
            return None, MappingProxyType({"cost_distribution": reason})
    subtraction = 1 if pool is not None else 0
    return DeliveredByPathCost(
        domain,
        tuple(
            PathCostBin(cost, cost - subtraction, delivered)
            for cost, delivered in sorted(bins.items())
        ),
    ), MappingProxyType({})
