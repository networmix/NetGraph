"""Resolve declared physical routes, supports and weights into native programs."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

import netgraph_core as ngc

from ngraph.analysis.topology import NamedRoutes, PreparedTopology
from ngraph.model.demand import PinnedRoutes, RouteSpec, SupportSpec, WeightSpec
from ngraph.model.network import DirectedLink
from ngraph.results import Endpoints


def edge_id(topology: PreparedTopology, ref: DirectedLink, label: str) -> int:
    if not isinstance(ref, DirectedLink) or ref not in topology._edge_id_by_ref:
        raise ValueError(f"{label}: unknown directed physical link {ref}")
    return topology._edge_id_by_ref[ref]


def dag_from_edges(graph: ngc.Graph, edges) -> ngc.PredecessorDAG:
    """One native DAG over a set of EdgeIds; validation (cycles included) is native."""
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    by_child = [[] for _ in range(graph.num_nodes())]
    for edge in edges:
        by_child[int(targets[edge])].append(edge)
    offsets, parents, via = [0], [], []
    for group in by_child:
        for edge in sorted(group):
            parents.append(int(sources[edge]))
            via.append(edge)
        offsets.append(len(via))
    return ngc.PredecessorDAG.from_csr(graph, offsets, parents, via)


def support_dag(
    topology: PreparedTopology, spec: SupportSpec, label: str
) -> ngc.PredecessorDAG:
    """Build the declared DAG once, validating duplicate and cyclic supports natively."""
    edges = [edge_id(topology, ref, label) for ref in spec.edges]
    if len(set(edges)) != len(edges):
        raise ValueError(f"{label}: duplicate support edge")
    try:
        return dag_from_edges(topology.graph, edges)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label}: {exc}") from exc


def domain_dag(
    topology: PreparedTopology,
    domain: frozenset[int],
    edge: frozenset[int],
    destination: int,
    mask: ngc.Eligibility,
) -> ngc.PredecessorDAG:
    """The routes toward one BGP-edge destination through one IGP domain.

    Exits are domain nodes with an eligible link to the destination; one
    reverse search from all of them, inside the domain and blind to capacity,
    gives each domain node its nearest exits. The DAG adds every eligible exit
    link and every eligible uplink from another BGP-edge node into a domain
    node that reaches an exit; nothing enters a BGP-edge node but the
    destination, so no other one carries transit. No exit gives an empty DAG.
    """
    graph = topology.graph
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    allowed = mask.edge_allowed()
    usable = [e for e in range(graph.num_edges()) if allowed[e]]
    exit_links = [
        e
        for e in usable
        if int(targets[e]) == destination and int(sources[e]) in domain
    ]
    if not exit_links:
        return dag_from_edges(graph, ())
    inside = ngc.Eligibility.intersect(
        mask,
        graph.eligibility(
            excluded_nodes=[n for n in range(graph.num_nodes()) if n not in domain]
        ),
    )
    search = ngc.spf(
        graph,
        sorted({int(sources[e]) for e in exit_links}),
        ngc.SpfOptions(ngc.Direction.REVERSE, eligibility=inside),
    )
    costs = search.costs
    assert costs is not None
    uplinks = [
        e
        for e in usable
        if int(sources[e]) in edge
        and int(sources[e]) != destination
        and int(targets[e]) in domain
        and costs[int(targets[e])] != ngc.UNREACHABLE
    ]
    tight = [int(e) for e in search.dag.via_edges()]
    return dag_from_edges(graph, {*tight, *exit_links, *uplinks})


def explicit_weights(
    topology: PreparedTopology, spec: WeightSpec, label: str
) -> tuple[int, ...]:
    """Unlisted edges have weight zero; duplicates are errors, never summed."""
    values = [0] * topology.graph.num_edges()
    seen = set()
    for entry in spec.entries:
        edge = edge_id(topology, entry.edge, label)
        if edge in seen:
            raise ValueError(f"{label}: duplicate weight for {entry.edge}")
        seen.add(edge)
        values[edge] = entry.value
    return tuple(values)


def hop_index(topology: PreparedTopology) -> dict[tuple[int, int], int]:
    """The cheapest enabled physical edge of each node pair, by (cost, link, direction)."""
    allowed = topology.disabled.edge_allowed()
    sources, destinations, costs = (
        topology.graph.edge_sources(),
        topology.graph.edge_destinations(),
        topology.graph.edge_costs(),
    )
    best: dict[tuple[int, int], tuple[int, str, str, int]] = {}
    for i, ref in enumerate(topology.edge_refs):
        if isinstance(ref, DirectedLink) and allowed[i]:
            pair = (int(sources[i]), int(destinations[i]))
            candidate = (int(costs[i]), ref.link, ref.direction, i)
            if pair not in best or candidate < best[pair]:
                best[pair] = candidate
    return {pair: candidate[3] for pair, candidate in best.items()}


def route_definition(
    topology: PreparedTopology,
    spec: RouteSpec,
    supports: Mapping[str, ngc.PredecessorDAG],
    hops_by_pair: Mapping[tuple[int, int], int],
    label: str,
) -> ngc.RouteDefinition:
    if spec.head not in topology.node_id_by_name:
        raise ValueError(f"{label}: unknown head {spec.head}")
    head = topology.node_id_by_name[spec.head]
    if spec.support is not None:
        if spec.support not in supports:
            raise ValueError(f"{label}: unknown support {spec.support}")
        route = supports[spec.support]
    else:
        allowed = topology.disabled.edge_allowed()
        if spec.nodes is not None:
            if len(spec.nodes) < 2:
                raise ValueError(f"{label}: a node route needs at least two nodes")
            hops = []
            for source, target in zip(spec.nodes, spec.nodes[1:], strict=False):
                if (
                    source not in topology.node_id_by_name
                    or target not in topology.node_id_by_name
                ):
                    raise ValueError(f"{label}: unknown node in hop {source}->{target}")
                pair = (
                    topology.node_id_by_name[source],
                    topology.node_id_by_name[target],
                )
                if pair not in hops_by_pair:
                    raise ValueError(
                        f"{label}: no enabled physical hop {source}->{target}"
                    )
                hops.append([hops_by_pair[pair]])
        else:
            assert spec.edges is not None
            hops = [[edge_id(topology, ref, label)] for ref in spec.edges]
            for ref, (edge,) in zip(spec.edges, hops, strict=True):
                if not allowed[edge]:
                    raise ValueError(f"{label}: disabled link {ref.link} or endpoint")
        if not hops or int(topology.graph.edge_sources()[hops[0][0]]) != head:
            raise ValueError(f"{label}: path must begin at its declared head")
        try:
            route = ngc.Path(topology.graph, hops)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{label}: {exc}") from exc
    return ngc.RouteDefinition(head, route, weight=spec.weight)


def compile_named(topology, *, routes=None, supports=None, weights=None):
    """Validate all named references and own one native value per graph/name."""
    route_specs = dict(routes or {})
    compiled_supports = {
        name: support_dag(topology, spec, f"support.{name}")
        for name, spec in (supports or {}).items()
    }
    compiled_weights = {
        name: explicit_weights(topology, spec, f"weights.{name}")
        for name, spec in (weights or {}).items()
    }
    # Node routes share one index of the cheapest enabled hop per node pair.
    hops = (
        hop_index(topology)
        if any(spec.nodes is not None for spec in route_specs.values())
        else {}
    )
    return NamedRoutes(
        MappingProxyType(route_specs),
        MappingProxyType(dict(supports or {})),
        MappingProxyType(dict(weights or {})),
        MappingProxyType(
            {
                name: route_definition(
                    topology, spec, compiled_supports, hops, f"route.{name}"
                )
                for name, spec in route_specs.items()
            }
        ),
        MappingProxyType(compiled_supports),
        MappingProxyType(compiled_weights),
    )


def validate_pinned(declaration, routes, weights):
    if not declaration.routes:
        raise ValueError("pinned.routes: expected a nonempty ordered list")
    for name in declaration.routes:
        if name not in routes:
            raise ValueError(f"route.{name}: unknown route")
    has_dag = any(routes[name].support is not None for name in declaration.routes)
    if not has_dag and any(
        value is not None
        for value in (
            declaration.allocation,
            declaration.weight_basis,
            declaration.edge_weights,
        )
    ):
        raise ValueError("pinned: split fields require a DAG route")
    if declaration.allocation not in (
        None,
        ngc.RouteAllocation.EQUAL,
        ngc.RouteAllocation.WEIGHTED,
    ):
        raise ValueError("pinned.allocation: expected equal or weighted")
    if declaration.weight_basis not in (
        None,
        ngc.WeightBasis.CAPACITY,
        ngc.WeightBasis.EXPLICIT,
    ):
        raise ValueError("pinned.weight_basis: expected capacity or explicit")
    if declaration.allocation != ngc.RouteAllocation.WEIGHTED and (
        declaration.weight_basis is not None or declaration.edge_weights is not None
    ):
        raise ValueError("pinned: weights require weighted allocation")
    if (declaration.weight_basis == ngc.WeightBasis.EXPLICIT) != (
        declaration.edge_weights is not None
    ):
        raise ValueError(
            "pinned: explicit basis requires named edge_weights and conversely"
        )
    if declaration.edge_weights is not None and declaration.edge_weights not in weights:
        raise ValueError(f"weights.{declaration.edge_weights}: unknown weights")


def pinned_config(
    topology: PreparedTopology,
    endpoints: Endpoints,
    declaration: PinnedRoutes,
    named: NamedRoutes,
) -> ngc.FlowPolicyConfig:
    validate_pinned(declaration, named.route_specs, named.weight_specs)
    definitions = [named.routes[name] for name in declaration.routes]
    vector = None
    if declaration.edge_weights is not None:
        vector = named.vector(declaration.edge_weights)
    program = ngc.ForwardingProgram.from_routes(
        topology.graph,
        [topology.node_id_by_name[n] for n in endpoints.sources],
        [topology.node_id_by_name[n] for n in endpoints.destinations],
        definitions,
        allocation=declaration.allocation,
        weight_basis=declaration.weight_basis,
        edge_weights=vector,
    )
    return ngc.FlowPolicyConfig(
        routing=ngc.Pinned(program), admission=declaration.admission
    )
