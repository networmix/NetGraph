"""Model checks on the prepared graph, with no eligible traffic and no solve."""

import netgraph_core as ngc


def validate_model(topology, config, options=None, *, pairs=()):
    """Check one materialized model with no eligible traffic and no solve."""
    graph = topology.graph
    nothing = graph.eligibility(excluded_nodes=range(graph.num_nodes()))
    if options is None:
        options = ngc.EvaluationOptions(
            config,
            offer=0,
            design_demand=0 if isinstance(config.routing, ngc.DistributedTE) else None,
        )
    checked = ngc.EvaluationOptions(
        config,
        eligibility=nothing,
        offer=options.offer,
        design_demand=options.design_demand,
        cache=options.cache,
    )
    if isinstance(config.routing, ngc.Pinned):
        program = config.routing.program
        ngc.evaluate_demand(graph, program.sources, program.destinations, checked)
    else:
        ngc.evaluate_pairs(graph, pairs, checked, workers=1)
