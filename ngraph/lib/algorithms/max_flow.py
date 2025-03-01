from __future__ import annotations

from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.place_flow import place_flow_on_graph
from ngraph.lib.algorithms.base import EdgeSelect, FlowPlacement
from ngraph.lib.graph import NodeID, StrictMultiDiGraph
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.algorithms.edge_select import edge_select_fabric


def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> float:
    """
    Compute the maximum flow between two nodes in a directed multi-graph,
    using an iterative shortest-path augmentation approach.

    By default, this function:
      1. Creates or re-initializes a flow-aware copy of the graph (using ``init_flow_graph``).
      2. Repeatedly finds a path from ``src_node`` to any reachable node via ``spf`` with
         capacity constraints (through ``EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING``).
      3. Places flow along that path (using ``place_flow_on_graph``) until no augmenting path
         remains or the capacities are exhausted.

    If ``shortest_path=True``, it will run only one iteration of path-finding and flow placement,
    returning the flow placed by that single augmentation (not the true max flow).

    Args:
        graph (StrictMultiDiGraph):
            The original graph containing capacity/flow attributes on each edge.
        src_node (NodeID):
            The source node for flow.
        dst_node (NodeID):
            The destination node for flow.
        flow_placement (FlowPlacement):
            Determines how flow is split among parallel edges of equal cost.
            Defaults to ``FlowPlacement.PROPORTIONAL``.
        shortest_path (bool):
            If True, place flow only once along the first shortest path found and return
            immediately, rather than iterating to find the true max flow.
        reset_flow_graph (bool):
            If True, reset any existing flow data (e.g., attributes in ``flow_attr`` and
            ``flows_attr``). Defaults to False.
        capacity_attr (str):
            The name of the capacity attribute on edges. Defaults to "capacity".
        flow_attr (str):
            The name of the aggregated flow attribute on edges. Defaults to "flow".
        flows_attr (str):
            The name of the per-flow dictionary attribute on edges. Defaults to "flows".
        copy_graph (bool):
            If True, work on a copy of the original graph so it remains unmodified.
            Defaults to True.

    Returns:
        float: The total flow placed between ``src_node`` and ``dst_node``.
               If ``shortest_path=True``, this is the flow placed by a single augmentation.

    Examples:
        >>> g = StrictMultiDiGraph()
        >>> g.add_node('A')
        >>> g.add_node('B')
        >>> g.add_node('C')
        >>> _ = g.add_edge('A', 'B', capacity=10.0, flow=0.0, flows={})
        >>> _ = g.add_edge('B', 'C', capacity=5.0, flow=0.0, flows={})
        >>> max_flow_value = calc_max_flow(g, 'A', 'C')
        >>> print(max_flow_value)
        5.0
    """
    # Initialize a flow-aware graph (copy or in-place).
    flow_graph = init_flow_graph(
        graph.copy() if copy_graph else graph,
        flow_attr,
        flows_attr,
        reset_flow_graph,
    )

    # Prepare the edge selection function (selects edges with capacity remaining).
    edge_select_func = edge_select_fabric(EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING)

    # First path-finding iteration.
    _, pred = spf(flow_graph, src_node, edge_select_func=edge_select_func)
    flow_meta = place_flow_on_graph(
        flow_graph,
        src_node,
        dst_node,
        pred,
        flow_placement=flow_placement,
        capacity_attr=capacity_attr,
        flow_attr=flow_attr,
        flows_attr=flows_attr,
    )
    max_flow: float = flow_meta.placed_flow

    # If only one path (single augmentation) is desired, return early.
    if shortest_path:
        return max_flow

    # Otherwise, repeatedly find augmenting paths until no new flow can be placed.
    while True:
        _, pred = spf(flow_graph, src_node, edge_select_func=edge_select_func)
        if dst_node not in pred:
            # No path found; we've reached the max flow.
            break

        flow_meta = place_flow_on_graph(
            flow_graph,
            src_node,
            dst_node,
            pred,
            flow_placement=flow_placement,
            capacity_attr=capacity_attr,
            flow_attr=flow_attr,
            flows_attr=flows_attr,
        )
        if flow_meta.placed_flow <= 0:
            # No additional flow could be placed; we're at capacity.
            break

        max_flow += flow_meta.placed_flow

    return max_flow
