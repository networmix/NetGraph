from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.place_flow import place_flow_on_graph
from ngraph.lib.algorithms.base import EdgeSelect, FlowPlacement
from ngraph.lib.graph import NodeID, StrictMultiDiGraph
from ngraph.lib.algorithms.flow_init import init_flow_graph


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
      1. Creates or re-initializes a flow-aware copy of the graph (via ``init_flow_graph``).
      2. Repeatedly finds a path from ``src_node`` to ``dst_node`` using ``spf`` with
         capacity constraints (``EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING``).
      3. Places flow along that path (via ``place_flow_on_graph``) until no augmenting path
         remains or the capacities are exhausted.

    If ``shortest_path=True``, the function performs only one iteration (single augmentation)
    and returns the flow placed along that single path (not the true max flow).

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
            immediately, rather than iterating for the true max flow.
        reset_flow_graph (bool):
            If True, reset any existing flow data (e.g., ``flow_attr``, ``flows_attr``).
            Defaults to False.
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
        float:
            The total flow placed between ``src_node`` and ``dst_node``. If ``shortest_path=True``,
            this is just the flow from a single augmentation.

    Notes:
        - For large graphs or performance-critical scenarios, consider specialized max-flow
          algorithms (e.g., Dinic, Edmond-Karp) for better scaling.

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

    # First path-finding iteration.
    _, pred = spf(
        flow_graph, src_node, edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING
    )
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
    max_flow = flow_meta.placed_flow

    # If only one path (single augmentation) is desired, return early.
    if shortest_path:
        return max_flow

    # Otherwise, repeatedly find augmenting paths until no new flow can be placed.
    while True:
        _, pred = spf(
            flow_graph, src_node, edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING
        )
        if dst_node not in pred:
            # No path found; we've reached max flow.
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
            # No additional flow could be placed; at capacity.
            break

        max_flow += flow_meta.placed_flow

    return max_flow
