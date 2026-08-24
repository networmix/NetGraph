"""Resolution of explicit routes into Core path bundles.

Turns the `StaticPath` entries on a demand into the `PredDAG` bundles that
`FlowPolicy.set_static_paths` pins traffic to. A bundle is a single simple
path: one edge per hop, so a route that names adjacent nodes with parallel
links between them picks one of those links (see `StaticPath`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Sequence, Tuple

import netgraph_core

from ngraph.model.demand.spec import StaticPath

if TYPE_CHECKING:
    from ngraph.analysis.context import AnalysisContext

__all__ = ["build_static_path_bundles"]

# Bundles depend only on the static graph, not on the per-iteration masks
# (Core prunes them against the masks itself), so they are resolved once per
# context and reused across Monte Carlo iterations and MSD probes. The cache
# lives on the context so it dies with it.
_CACHE_ATTR = "_static_path_bundle_cache"


def _disabled_edge_ids(ctx: "AnalysisContext") -> frozenset:
    """Core edge ids belonging to administratively disabled links."""
    link_edges = ctx.link_id_to_edge_indices
    return frozenset(
        int(edge_id)
        for link_id in ctx.disabled_link_ids
        for edge_id in link_edges.get(link_id, ())
    )


def _hop_edge(
    src_id: int, dst_id: int, adjacency, cost, ext_ids, disabled_edges
) -> int:
    """Return the edge id to use for one node-to-node hop.

    Picks the cheapest enabled edge from src_id to dst_id, breaking ties by
    external edge id so the choice is stable across identical scenario
    builds. Disabled links are skipped: pinning a route to one would take the
    route down for the whole run even when an enabled parallel link exists.
    Walks the source's adjacency row, so cost is proportional to that node's
    degree rather than to the size of the graph.
    """
    row, col, adj_edge = adjacency
    best = -1
    best_key: Tuple[int, int] = (0, 0)
    for i in range(int(row[src_id]), int(row[src_id + 1])):
        if int(col[i]) != dst_id:
            continue
        edge_id = int(adj_edge[i])
        if edge_id in disabled_edges:
            continue
        key = (int(cost[edge_id]), int(ext_ids[edge_id]))
        if best < 0 or key < best_key:
            best, best_key = edge_id, key
    return best


def _edges_from_nodes(ctx: "AnalysisContext", path: StaticPath) -> List[int]:
    """Resolve a node-sequence route to one Core edge per hop."""
    graph = ctx.multidigraph
    adjacency = (
        graph.row_offsets_view(),
        graph.col_indices_view(),
        graph.adj_edge_index_view(),
    )
    cost = graph.cost_view()
    ext_ids = graph.ext_edge_ids_view()
    disabled_edges = _disabled_edge_ids(ctx)

    edges: List[int] = []
    for u, v in zip(path.nodes, path.nodes[1:], strict=False):
        for name in (u, v):
            if name not in ctx.node_mapper.node_id_of:
                raise ValueError(
                    f"Static path names unknown node {name!r}; "
                    f"route was {list(path.nodes)}"
                )
        u_id = ctx.node_mapper.to_id(u)
        v_id = ctx.node_mapper.to_id(v)
        edge_id = _hop_edge(u_id, v_id, adjacency, cost, ext_ids, disabled_edges)
        if edge_id < 0:
            raise ValueError(
                f"Static path hop {u!r} -> {v!r} has no enabled link; "
                f"route was {list(path.nodes)}"
            )
        edges.append(edge_id)
    return edges


def _edges_from_links(
    ctx: "AnalysisContext", path: StaticPath, src_id: int
) -> List[int]:
    """Resolve a link-id route to Core edges, following the traversal order."""
    graph = ctx.multidigraph
    edge_src = graph.edge_src_view()
    edge_dst = graph.edge_dst_view()
    link_edges = ctx.link_id_to_edge_indices

    current = src_id
    edges: List[int] = []
    for link_id in path.links:
        candidates = link_edges.get(link_id)
        if not candidates:
            raise ValueError(
                f"Static path names unknown link {link_id!r}; "
                f"route was {list(path.links)}"
            )
        # A link has a forward and (for bidirectional links) a reverse edge;
        # pick whichever leaves the node the route has reached.
        if link_id in ctx.disabled_link_ids:
            raise ValueError(
                f"Static path names disabled link {link_id!r}; a route pinned to "
                "a disabled link can never carry traffic"
            )
        chosen = next(
            (int(e) for e in candidates if int(edge_src[int(e)]) == current), None
        )
        if chosen is None:
            reached = ctx.node_mapper.to_name(current)
            raise ValueError(
                f"Static path link {link_id!r} does not leave node {reached!r}; "
                f"route was {list(path.links)}"
            )
        edges.append(chosen)
        current = int(edge_dst[chosen])
    return edges


def build_static_path_bundles(
    ctx: "AnalysisContext",
    paths: Sequence[StaticPath],
    src_name: str,
    dst_name: str,
) -> List[netgraph_core.PredDAG]:
    """Build the Core path bundles a demand is pinned to.

    Args:
        ctx: Context holding the built graph; routes resolve against it.
        paths: Routes to pin, in the order flows should be created.
        src_name: Node every route must start at.
        dst_name: Node every route must end at.

    Returns:
        One `PredDAG` per route, in the given order. Results are cached per
        context, so repeated calls during a Monte Carlo run resolve once.

    Raises:
        ValueError: If an endpoint is absent from the context graph, if a
            route names an unknown node or a disabled/unknown link, has a hop
            whose nodes are joined only by disabled links, has a hop with
            no link, traverses a link that does not leave the node it has
            reached, does not run from `src_name` to `dst_name`, or revisits
            a node (a pinned route must be a simple path).
    """
    cache_key = (src_name, dst_name, tuple(paths))
    per_ctx: Optional[Dict[tuple, List[netgraph_core.PredDAG]]] = getattr(
        ctx, _CACHE_ATTR, None
    )
    if per_ctx is None:
        per_ctx = {}
        setattr(ctx, _CACHE_ATTR, per_ctx)
    cached = per_ctx.get(cache_key)
    if cached is not None:
        return cached

    graph = ctx.multidigraph
    edge_src = graph.edge_src_view()
    edge_dst = graph.edge_dst_view()
    for name in (src_name, dst_name):
        if name not in ctx.node_mapper.node_id_of:
            raise ValueError(
                f"Demand endpoint {name!r} is not in the analysis context graph, "
                "so its static paths cannot be resolved"
            )
    src_id = ctx.node_mapper.to_id(src_name)
    dst_id = ctx.node_mapper.to_id(dst_name)

    bundles: List[netgraph_core.PredDAG] = []
    for path in paths:
        if path.nodes:
            if path.nodes[0] != src_name or path.nodes[-1] != dst_name:
                raise ValueError(
                    f"Static path must run from {src_name!r} to {dst_name!r}, "
                    f"but runs from {path.nodes[0]!r} to {path.nodes[-1]!r}"
                )
            edges = _edges_from_nodes(ctx, path)
        else:
            edges = _edges_from_links(ctx, path, src_id)

        if int(edge_src[edges[0]]) != src_id or int(edge_dst[edges[-1]]) != dst_id:
            start = ctx.node_mapper.to_name(int(edge_src[edges[0]]))
            end = ctx.node_mapper.to_name(int(edge_dst[edges[-1]]))
            raise ValueError(
                f"Static path must run from {src_name!r} to {dst_name!r}, "
                f"but runs from {start!r} to {end!r}"
            )

        try:
            bundles.append(netgraph_core.PredDAG.from_edges(graph, edges))
        except ValueError as exc:
            route = list(path.nodes or path.links)
            raise ValueError(f"Invalid static path {route}: {exc}") from exc

    per_ctx[cache_key] = bundles
    return bundles
