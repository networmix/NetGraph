from typing import Literal, Union, overload

from ngraph.lib.algorithms.base import EdgeSelect, FlowPlacement
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.algorithms.place_flow import place_flow_on_graph
from ngraph.lib.algorithms.spf import spf
from ngraph.lib.algorithms.types import FlowSummary
from ngraph.lib.graph import NodeID, StrictMultiDiGraph


@overload
def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    return_summary: Literal[False] = False,
    return_graph: Literal[False] = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> float: ...


@overload
def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    return_summary: Literal[True],
    return_graph: Literal[False] = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> tuple[float, FlowSummary]: ...


@overload
def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    return_summary: Literal[False] = False,
    return_graph: Literal[True],
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> tuple[float, StrictMultiDiGraph]: ...


@overload
def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    return_summary: Literal[True],
    return_graph: Literal[True],
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> tuple[float, FlowSummary, StrictMultiDiGraph]: ...


def calc_max_flow(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    return_summary: bool = False,
    return_graph: bool = False,
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    shortest_path: bool = False,
    reset_flow_graph: bool = False,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    copy_graph: bool = True,
) -> Union[float, tuple]:
    """Compute the maximum flow between two nodes in a directed multi-graph,
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
        return_summary (bool):
            If True, return a FlowSummary with detailed flow analytics.
            Defaults to False.
        return_graph (bool):
            If True, return the mutated flow graph along with other results.
            Defaults to False.
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
        Union[float, tuple]:
            - If neither return_summary nor return_graph: float (total flow)
            - If return_summary only: tuple[float, FlowSummary]
            - If both flags: tuple[float, FlowSummary, StrictMultiDiGraph]

    Notes:
        - For large graphs or performance-critical scenarios, consider specialized max-flow
          algorithms (e.g., Dinic, Edmond-Karp) for better scaling.
        - When using return_summary or return_graph, callers must unpack the returned tuple.

    Examples:
        >>> g = StrictMultiDiGraph()
        >>> g.add_node('A')
        >>> g.add_node('B')
        >>> g.add_node('C')
        >>> g.add_edge('A', 'B', capacity=10.0, flow=0.0, flows={}, cost=1)
        >>> g.add_edge('B', 'C', capacity=5.0, flow=0.0, flows={}, cost=1)
        >>>
        >>> # Basic usage (scalar return)
        >>> max_flow_value = calc_max_flow(g, 'A', 'C')
        >>> print(max_flow_value)
        5.0
        >>>
        >>> # With flow summary analytics
        >>> flow, summary = calc_max_flow(g, 'A', 'C', return_summary=True)
        >>> print(f"Min-cut edges: {summary.min_cut}")
        >>>
        >>> # With both summary and mutated graph
        >>> flow, summary, flow_graph = calc_max_flow(
        ...     g, 'A', 'C', return_summary=True, return_graph=True
        ... )
        >>> # flow_graph contains the flow assignments
    """
    # Handle self-loop case: when source equals destination, max flow is always 0
    # Degenerate case (s == t):
    # Flow value |f| is the net surplus at the vertex.
    # Conservation forces that surplus to zero, so the
    # only feasible (and thus maximum) flow value is 0.
    if src_node == dst_node:
        if return_summary or return_graph:
            # For consistency, we need to create a minimal flow graph for summary/graph returns
            flow_graph = init_flow_graph(
                graph.copy() if copy_graph else graph,
                flow_attr,
                flows_attr,
                reset_flow_graph,
            )
            return _build_return_value(
                0.0,
                flow_graph,
                src_node,
                return_summary,
                return_graph,
                capacity_attr,
                flow_attr,
            )
        else:
            return 0.0

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
        return _build_return_value(
            max_flow,
            flow_graph,
            src_node,
            return_summary,
            return_graph,
            capacity_attr,
            flow_attr,
        )

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

    return _build_return_value(
        max_flow,
        flow_graph,
        src_node,
        return_summary,
        return_graph,
        capacity_attr,
        flow_attr,
    )


def _build_return_value(
    max_flow: float,
    flow_graph: StrictMultiDiGraph,
    src_node: NodeID,
    return_summary: bool,
    return_graph: bool,
    capacity_attr: str,
    flow_attr: str,
) -> Union[float, tuple]:
    """Build the appropriate return value based on the requested flags."""
    if not (return_summary or return_graph):
        return max_flow

    summary = None
    if return_summary:
        summary = _build_flow_summary(
            max_flow, flow_graph, src_node, capacity_attr, flow_attr
        )

    ret: list = [max_flow]
    if return_summary:
        ret.append(summary)
    if return_graph:
        ret.append(flow_graph)

    return tuple(ret) if len(ret) > 1 else ret[0]


def _build_flow_summary(
    total_flow: float,
    flow_graph: StrictMultiDiGraph,
    src_node: NodeID,
    capacity_attr: str,
    flow_attr: str,
) -> FlowSummary:
    """Build a FlowSummary from the flow graph state."""
    edge_flow = {}
    residual_cap = {}

    # Extract flow and residual capacity for each edge
    for u, v, k, d in flow_graph.edges(data=True, keys=True):
        edge = (u, v, k)
        f = d.get(flow_attr, 0.0)
        edge_flow[edge] = f
        residual_cap[edge] = d[capacity_attr] - f

    # BFS in residual graph to find reachable nodes from source
    reachable = set()
    stack = [src_node]
    while stack:
        n = stack.pop()
        if n in reachable:
            continue
        reachable.add(n)
        for _, nbr, _, d in flow_graph.out_edges(n, data=True, keys=True):
            if d[capacity_attr] - d.get(flow_attr, 0.0) > 0 and nbr not in reachable:
                stack.append(nbr)

    # Find min-cut edges (saturated edges crossing the cut)
    min_cut = [
        (u, v, k)
        for u, v, k, d in flow_graph.edges(data=True, keys=True)
        if u in reachable
        and v not in reachable
        and d[capacity_attr] - d.get(flow_attr, 0.0) == 0
    ]

    return FlowSummary(
        total_flow=total_flow,
        edge_flow=edge_flow,
        residual_cap=residual_cap,
        reachable=reachable,
        min_cut=min_cut,
    )


def saturated_edges(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    tolerance: float = 1e-10,
    **kwargs,
) -> list[tuple]:
    """Identify saturated (bottleneck) edges in the max flow solution.

    Args:
        graph: The graph to analyze
        src_node: Source node
        dst_node: Destination node
        capacity_attr: Name of capacity attribute
        flow_attr: Name of flow attribute
        tolerance: Tolerance for considering an edge saturated
        **kwargs: Additional arguments passed to calc_max_flow

    Returns:
        List of saturated edge tuples (u, v, k) where residual capacity <= tolerance
    """
    result = calc_max_flow(
        graph,
        src_node,
        dst_node,
        return_summary=True,
        capacity_attr=capacity_attr,
        flow_attr=flow_attr,
        **kwargs,
    )
    # Ensure we have a tuple to unpack
    if isinstance(result, tuple) and len(result) >= 2:
        _, summary = result
    else:
        raise ValueError(
            "Expected tuple return from calc_max_flow with return_summary=True"
        )

    return [
        edge for edge, residual in summary.residual_cap.items() if residual <= tolerance
    ]


def run_sensitivity(
    graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    *,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    change_amount: float = 1.0,
    **kwargs,
) -> dict[tuple, float]:
    """Perform sensitivity analysis to identify high-impact capacity changes.

    Tests changing each saturated edge capacity by change_amount and measures
    the resulting change in total flow. Positive values increase capacity,
    negative values decrease capacity (with validation to prevent negative capacities).

    Args:
        graph: The graph to analyze
        src_node: Source node
        dst_node: Destination node
        capacity_attr: Name of capacity attribute
        flow_attr: Name of flow attribute
        change_amount: Amount to change capacity for testing (positive=increase, negative=decrease)
        **kwargs: Additional arguments passed to calc_max_flow

    Returns:
        Dictionary mapping edge tuples to flow change when capacity is modified
    """
    # Get baseline flow and identify saturated edges - ensure scalar return
    baseline_flow = calc_max_flow(
        graph,
        src_node,
        dst_node,
        return_summary=False,
        return_graph=False,
        capacity_attr=capacity_attr,
        flow_attr=flow_attr,
        **kwargs,
    )
    assert isinstance(baseline_flow, (int, float))

    saturated = saturated_edges(
        graph,
        src_node,
        dst_node,
        capacity_attr=capacity_attr,
        flow_attr=flow_attr,
        **kwargs,
    )

    sensitivity = {}

    for edge in saturated:
        u, v, k = edge

        # Create modified graph with changed edge capacity
        test_graph = graph.copy()
        edge_data = test_graph.get_edge_data(u, v, k)
        if edge_data is not None:
            # Create a mutable copy of the edge data
            edge_data = dict(edge_data)
            original_capacity = edge_data[capacity_attr]
            new_capacity = original_capacity + change_amount

            # If the change would result in negative capacity, set to 0
            if new_capacity < 0:
                new_capacity = 0

            edge_data[capacity_attr] = new_capacity
            test_graph.remove_edge(u, v, k)
            test_graph.add_edge(u, v, k, **edge_data)

            # Calculate new max flow - ensure scalar return
            new_flow = calc_max_flow(
                test_graph,
                src_node,
                dst_node,
                return_summary=False,
                return_graph=False,
                capacity_attr=capacity_attr,
                flow_attr=flow_attr,
                **kwargs,
            )
            assert isinstance(new_flow, (int, float))

            # Record flow change
            sensitivity[edge] = new_flow - baseline_flow

    return sensitivity
