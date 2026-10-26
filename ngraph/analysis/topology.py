"""Compile named physical links and finite TE ingresses into one native graph."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, cast

import netgraph_core as ngc

from ngraph.analysis.units import LIMIT, quantize, validate_resolution
from ngraph.model.network import DirectedLink, Network
from ngraph.results import SyntheticIngress

if TYPE_CHECKING:
    from ngraph.model.demand import RouteSpec, WeightSpec


@dataclass(frozen=True)
class PreparedTopology:
    """One engine graph with its network labels; per-edge arrays follow ``edge_refs``.

    ``pool_heads`` maps each finite TE ingress pool to its synthetic head node;
    ``pool_budgets`` holds a pool's lossy offer budget in units, when it has one.
    """

    graph: ngc.Graph
    node_names: tuple[str, ...]
    node_id_by_name: Mapping[str, int]
    edge_refs: tuple[DirectedLink | SyntheticIngress, ...]
    edges_by_link: Mapping[str, tuple[int, int]]
    disabled: ngc.Eligibility
    q: float
    pool_heads: Mapping[str, int]
    pool_budgets: Mapping[str, int]
    _edge_id_by_ref: Mapping[DirectedLink | SyntheticIngress, int] = field(
        repr=False, compare=False
    )


def _empty() -> Mapping:
    return MappingProxyType({})


@dataclass(frozen=True)
class NamedRoutes:
    """Declared routes, supports and weights, and their native forms on one graph."""

    route_specs: Mapping[str, RouteSpec] = field(default_factory=_empty)
    weight_specs: Mapping[str, WeightSpec] = field(default_factory=_empty)
    routes: Mapping[str, ngc.RouteDefinition] = field(default_factory=_empty)
    supports: Mapping[str, ngc.PredecessorDAG] = field(default_factory=_empty)
    weights: Mapping[str, tuple[int, ...]] = field(default_factory=_empty)

    def vector(self, name: str) -> tuple[int, ...]:
        """The named explicit edge weights."""
        if name not in self.weights:
            raise ValueError(f"weights.{name}: unknown weights")
        return self.weights[name]


NO_ROUTES = NamedRoutes()


def outgoing_units(network: Network, q: float) -> Counter[str]:
    """Each node's outgoing directed capacity in units at q."""
    outgoing: Counter[str] = Counter()
    for link_id, link in network.links.items():
        units = quantize(link.capacity, q, f"link.{link_id}.capacity")
        outgoing[link.source] += units
        outgoing[link.target] += units
    return outgoing


def compile_topology(
    network: Network,
    q: float,
    *,
    pools: Mapping[str, tuple[str, ...]] | None = None,
    budgets: Mapping[str, int] | None = None,
) -> PreparedTopology:
    """Compile a candidate graph, refusing directed capacity/cost sums out of range.

    A pool's attachments carry its source's outgoing capacity, or its lossy
    offer budget (units) when that is larger.
    """
    budgets = dict(budgets or {})
    validate_resolution(q)
    names = tuple(sorted(network.nodes))
    node_ids = {name: i for i, name in enumerate(names)}
    for name, node in network.nodes.items():
        # Each node checks its own name; the network checks it is the node's key.
        if node.name != name:
            raise ValueError(f"node {name!r}: invalid named identity")
    pool_members = dict(pools or {})
    heads = {name: len(names) + i for i, name in enumerate(sorted(pool_members))}
    sources, targets, capacities, costs, refs = [], [], [], [], []
    for link_id, link in sorted(network.links.items()):
        if (
            link.id != link_id
            or link.source not in node_ids
            or link.target not in node_ids
        ):
            raise ValueError(f"link {link_id}: invalid identity or endpoints")
        capacity = quantize(link.capacity, q, f"link.{link_id}.capacity")
        cost = link.cost  # an integer in [1, 2^62), checked by the link
        for direction, source, target in (
            ("forward", link.source, link.target),
            ("reverse", link.target, link.source),
        ):
            sources.append(node_ids[source])
            targets.append(node_ids[target])
            capacities.append(capacity)
            costs.append(cost)
            refs.append(
                DirectedLink(link_id, cast(Literal["forward", "reverse"], direction))
            )
    outgoing = outgoing_units(network, q) if heads else Counter()
    for pool_id, head in heads.items():
        members = tuple(sorted(set(pool_members[pool_id])))
        if not members:
            raise ValueError(f"pool.{pool_id}: sources must not be empty")
        for source in members:
            if source not in node_ids:
                raise ValueError(f"pool.{pool_id}: unknown source {source}")
            sources.append(head)
            targets.append(node_ids[source])
            capacities.append(max(outgoing[source], budgets.get(pool_id, 0)))
            costs.append(1)
            refs.append(SyntheticIngress(pool_id, source))
    capsum, costsum = sum(capacities), sum(costs)
    if capsum >= LIMIT:
        raise ValueError(f"topology augmented capacity sum {capsum} must be below 2^62")
    if costsum >= LIMIT:
        raise ValueError(f"topology augmented cost sum {costsum} must be below 2^62")
    graph = ngc.Graph(len(names) + len(heads), sources, targets, capacities, costs, q)
    edge_refs = tuple(refs[int(position)] for position in graph.input_positions())
    edge_ids = {ref: i for i, ref in enumerate(edge_refs)}
    links = {
        link: (
            edge_ids[DirectedLink(link, "forward")],
            edge_ids[DirectedLink(link, "reverse")],
        )
        for link in network.links
    }
    excluded_nodes = [
        node_ids[name] for name, node in network.nodes.items() if node.disabled
    ]
    excluded_edges = [
        edge
        for link_id, link in network.links.items()
        if link.disabled
        for edge in links[link_id]
    ]
    disabled = graph.eligibility(
        excluded_nodes=excluded_nodes, excluded_edges=excluded_edges
    )
    return PreparedTopology(
        graph,
        names,
        MappingProxyType(node_ids),
        edge_refs,
        MappingProxyType(links),
        disabled,
        q,
        MappingProxyType(heads),
        MappingProxyType({p: b for p, b in budgets.items() if p in heads}),
        MappingProxyType(edge_ids),
    )


def eligibility(
    topology: PreparedTopology, excluded_nodes=(), excluded_links=()
) -> ngc.Eligibility:
    """Intersect physical failures with declared disabled nodes and links."""
    nodes, edges = [], []
    for name in excluded_nodes:
        if name not in topology.node_id_by_name:
            raise ValueError(f"failure: unknown node {name}")
        nodes.append(topology.node_id_by_name[name])
    for link in excluded_links:
        if link not in topology.edges_by_link:
            raise ValueError(f"failure: unknown link {link}")
        edges.extend(topology.edges_by_link[link])
    return ngc.Eligibility.intersect(
        topology.disabled,
        topology.graph.eligibility(excluded_nodes=nodes, excluded_edges=edges),
    )
