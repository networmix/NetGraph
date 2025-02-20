from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Set, Tuple

from ngraph.lib.graph import EdgeID, StrictMultiDiGraph, NodeID
from ngraph.lib.algorithms.base import MIN_CAP, MIN_FLOW, FlowPlacement


def _init_graph_data(
    flow_graph: StrictMultiDiGraph,
    pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
    init_node: NodeID,
    flow_placement: FlowPlacement,
    capacity_attr: str,
    flow_attr: str,
) -> Tuple[
    Dict[NodeID, Dict[NodeID, Tuple[EdgeID, ...]]],
    Dict[NodeID, int],
    Dict[NodeID, Dict[NodeID, float]],
    Dict[NodeID, Dict[NodeID, float]],
]:
    """
    Build the necessary data structures for the flow algorithm:
      - `succ`: Reversed adjacency mapping, where each key is a node and its value is a
        dict mapping adjacent nodes (from which flow can arrive) to the tuple of edge IDs.
      - `levels`: Stores the BFS level (distance) for each node (used in Dinic's algorithm).
      - `residual_cap`: Residual capacity for each edge in the reversed orientation.
      - `flow_dict`: Tracks the net flow on each edge (initialized to zero).

    For PROPORTIONAL mode, the residual capacity in the reversed graph is the sum of the available
    capacity on all parallel forward edges (if above a threshold MIN_CAP). For EQUAL_BALANCED mode,
    the reversed edge capacity is set as the minimum available capacity among parallel edges multiplied
    by the number of such edges.

    Args:
        flow_graph: The multigraph with capacity and flow attributes on edges.
        pred: Forward adjacency mapping: node -> (adjacent node -> list of EdgeIDs).
        init_node: Starting node for the reverse BFS (typically the destination in forward flow).
        flow_placement: Strategy for distributing flow (PROPORTIONAL or EQUAL_BALANCED).
        capacity_attr: Name of the capacity attribute.
        flow_attr: Name of the flow attribute.

    Returns:
        A tuple containing:
          - succ: The reversed adjacency dict.
          - levels: A dict mapping each node to its BFS level.
          - residual_cap: The residual capacities in the reversed graph.
          - flow_dict: The net flow on each edge (initially zero).
    """
    edges = flow_graph.get_edges()

    # Reversed adjacency: For each edge u->v in forward sense, store v->u in succ.
    succ: Dict[NodeID, Dict[NodeID, Tuple[EdgeID, ...]]] = defaultdict(dict)
    # Levels for BFS/DFS (initially empty)
    levels: Dict[NodeID, int] = {}
    # Residual capacities in the reversed orientation
    residual_cap: Dict[NodeID, Dict[NodeID, float]] = defaultdict(dict)
    # Net flow (will be updated during DFS/BFS)
    flow_dict: Dict[NodeID, Dict[NodeID, float]] = defaultdict(dict)

    visited: Set[NodeID] = set()
    queue: Deque[NodeID] = deque([init_node])

    # Perform a BFS starting from init_node (destination in forward graph)
    while queue:
        node = queue.popleft()
        visited.add(node)

        # Initialize level to -1 (unvisited) if not already set
        if node not in levels:
            levels[node] = -1

        # Process incoming edges in the forward (pred) graph to build the reversed structure
        for adj_node, edge_list in pred.get(node, {}).items():
            # Record the reversed edge: from adj_node -> node with all corresponding edge IDs.
            if node not in succ[adj_node]:
                succ[adj_node][node] = tuple(edge_list)

            # Calculate available capacity for each parallel edge (cap - flow)
            capacities = []
            for eid in edge_list:
                cap_val = edges[eid][3][capacity_attr]
                flow_val = edges[eid][3][flow_attr]
                # Only consider nonnegative available capacity
                c = max(0.0, cap_val - flow_val)
                capacities.append(c)

            if flow_placement == FlowPlacement.PROPORTIONAL:
                # Sum capacities of parallel edges as the available capacity in reverse.
                fwd_capacity = sum(capacities)
                residual_cap[node][adj_node] = (
                    fwd_capacity if fwd_capacity >= MIN_CAP else 0.0
                )
                # In the reverse graph, the backward edge starts with zero capacity.
                residual_cap[adj_node][node] = 0.0

            elif flow_placement == FlowPlacement.EQUAL_BALANCED:
                # Use the minimum available capacity multiplied by the number of parallel edges.
                if capacities:
                    rev_cap = min(capacities) * len(capacities)
                    residual_cap[adj_node][node] = (
                        rev_cap if rev_cap >= MIN_CAP else 0.0
                    )
                else:
                    residual_cap[adj_node][node] = 0.0
                # The forward edge is unused in this BFS phase.
                residual_cap[node][adj_node] = 0.0

            else:
                raise ValueError(f"Unsupported flow placement: {flow_placement}")

            # Initialize net flow for both orientations to zero.
            flow_dict[node][adj_node] = 0.0
            flow_dict[adj_node][node] = 0.0

            # Add adjacent node to the BFS queue if not already visited.
            if adj_node not in visited:
                queue.append(adj_node)

    # Ensure every node in the graph appears in the reversed adjacency map.
    for n in flow_graph.nodes():
        succ.setdefault(n, {})

    return succ, levels, residual_cap, flow_dict


def _set_levels_bfs(
    start_node: NodeID,
    levels: Dict[NodeID, int],
    residual_cap: Dict[NodeID, Dict[NodeID, float]],
) -> None:
    """
    Perform a BFS on the reversed residual graph to assign levels for Dinic's algorithm.
    An edge is considered if its residual capacity is at least MIN_CAP.

    Args:
        start_node: The starting node for the BFS (acts as the source in the reversed graph).
        levels: A dict mapping each node to its level (updated in-place).
        residual_cap: Residual capacity for each edge in the reversed graph.
    """
    # Reset all node levels to -1 (unvisited)
    for nd in levels:
        levels[nd] = -1
    levels[start_node] = 0

    queue: Deque[NodeID] = deque([start_node])
    while queue:
        u = queue.popleft()
        # Explore all neighbors of u in the reversed graph
        for v, cap_uv in residual_cap[u].items():
            # Only traverse edges with sufficient capacity and unvisited nodes.
            if cap_uv >= MIN_CAP and levels[v] < 0:
                levels[v] = levels[u] + 1
                queue.append(v)


def _push_flow_dfs(
    current: NodeID,
    sink: NodeID,
    flow_in: float,
    residual_cap: Dict[NodeID, Dict[NodeID, float]],
    flow_dict: Dict[NodeID, Dict[NodeID, float]],
    levels: Dict[NodeID, int],
) -> float:
    """
    Recursively push flow from `current` to `sink` in the reversed residual graph using DFS.
    Only paths that follow the level structure (levels[nxt] == levels[current] + 1) are considered.

    Args:
        current: The current node in the DFS.
        sink: The target node in the reversed orientation.
        flow_in: The amount of flow available to push from the current node.
        residual_cap: The residual capacities of edges.
        flow_dict: Records the net flow pushed along each edge.
        levels: Node levels as determined by BFS.

    Returns:
        The total amount of flow successfully pushed from `current` to `sink`.
    """
    # Base case: reached sink, return the available flow.
    if current == sink:
        return flow_in

    total_pushed = 0.0
    # Make a static list of neighbors to avoid issues if residual_cap is updated during iteration.
    neighbors = list(residual_cap[current].items())

    for nxt, capacity_uv in neighbors:
        # Skip edges that don't have enough residual capacity.
        if capacity_uv < MIN_CAP:
            continue
        # Only consider neighbors that are exactly one level deeper.
        if levels.get(nxt, -1) != levels[current] + 1:
            continue

        # Determine how much flow can be pushed along the current edge.
        flow_to_push = min(flow_in, capacity_uv)
        if flow_to_push < MIN_FLOW:
            continue

        pushed = _push_flow_dfs(
            nxt, sink, flow_to_push, residual_cap, flow_dict, levels
        )
        if pushed >= MIN_FLOW:
            # Decrease residual capacity on forward edge and increase on reverse edge.
            residual_cap[current][nxt] -= pushed
            residual_cap[nxt][current] += pushed

            # Update net flow (note: in reversed orientation)
            flow_dict[current][nxt] += pushed
            flow_dict[nxt][current] -= pushed

            flow_in -= pushed
            total_pushed += pushed

            # Stop if no more flow can be pushed from the current node.
            if flow_in < MIN_FLOW:
                break

    return total_pushed


def _equal_balance_bfs(
    src_node: NodeID,
    succ: Dict[NodeID, Dict[NodeID, Tuple[EdgeID, ...]]],
    flow_dict: Dict[NodeID, Dict[NodeID, float]],
) -> None:
    """
    Perform a BFS-like pass to distribute a nominal flow of 1.0 from `src_node`
    over the reversed adjacency (succ), splitting flow equally among all outgoing parallel edges.
    This method does not verify capacities; it simply assigns relative flow amounts.

    Args:
        src_node: The starting node from which a nominal flow of 1.0 is injected.
        succ: The reversed adjacency dict where succ[u][v] is a tuple of edges from u to v.
        flow_dict: The net flow dictionary to be updated with the BFS distribution.
    """
    # Calculate the total count of parallel edges leaving each node.
    node_split: Dict[NodeID, int] = {}
    for node, neighbors in succ.items():
        node_split[node] = sum(len(edge_tuple) for edge_tuple in neighbors.values())

    # Initialize BFS with src_node and a starting flow of 1.0.
    queue: Deque[Tuple[NodeID, float]] = deque([(src_node, 1.0)])
    visited: Set[NodeID] = set()

    while queue:
        node, incoming_flow = queue.popleft()
        visited.add(node)

        # Get total number of outgoing parallel edges.
        split_count = node_split[
            node
        ]  # Previously caused KeyError if node wasn't in succ
        if split_count <= 0 or incoming_flow < MIN_FLOW:
            continue

        # Distribute the incoming flow proportionally based on number of edges.
        for nxt, edge_tuple in succ[node].items():
            if not edge_tuple:
                continue  # Skip if there are no edges to next node.
            # Compute the fraction of flow for this neighbor.
            push_flow = (incoming_flow * len(edge_tuple)) / float(split_count)
            if push_flow < MIN_FLOW:
                continue

            # Update net flow in the reversed direction.
            flow_dict[node][nxt] += push_flow
            flow_dict[nxt][node] -= push_flow

            # Continue BFS for neighbor if not yet visited.
            if nxt not in visited:
                queue.append((nxt, push_flow))


def calc_graph_capacity(
    flow_graph: StrictMultiDiGraph,
    src_node: NodeID,
    dst_node: NodeID,
    pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[float, Dict[NodeID, Dict[NodeID, float]]]:
    """
    Calculate the maximum feasible flow from src_node to dst_node (in forward sense)
    using either the PROPORTIONAL or EQUAL_BALANCED approach.

    In PROPORTIONAL mode (Dinic-like):
      1. Build the reversed residual graph from dst_node.
      2. Use BFS to create a level graph and DFS to push blocking flows.
      3. Sum the reversed flows from dst_node to src_node and normalize them to obtain
         the forward flow values.

    In EQUAL_BALANCED mode:
      1. Perform a BFS pass from src_node over the reversed adjacency,
         distributing a nominal flow of 1.0.
      2. Determine the scaling ratio so that no edge capacity is exceeded.
      3. Scale the flow assignments and normalize the flows.

    Args:
        flow_graph: The multigraph with capacity and flow attributes.
        src_node: The source node in the forward graph.
        dst_node: The destination node in the forward graph.
        pred: Forward adjacency mapping: node -> (adjacent node -> list of EdgeIDs).
        flow_placement: Flow distribution strategy (PROPORTIONAL or EQUAL_BALANCED).
        capacity_attr: Name of the capacity attribute.
        flow_attr: Name of the flow attribute.

    Returns:
        A tuple containing:
          - total_flow: The maximum feasible flow value from src_node to dst_node.
          - flow_dict: A dictionary mapping (u, v) to net flow values (positive indicates forward flow).
    """
    if src_node not in flow_graph or dst_node not in flow_graph:
        raise ValueError(
            f"Source node {src_node} or destination node {dst_node} not found in the graph."
        )

    # Build the reversed adjacency structures starting from dst_node.
    succ, levels, residual_cap, flow_dict = _init_graph_data(
        flow_graph=flow_graph,
        pred=pred,
        init_node=dst_node,
        flow_placement=flow_placement,
        capacity_attr=capacity_attr,
        flow_attr=flow_attr,
    )

    total_flow = 0.0

    if flow_placement == FlowPlacement.PROPORTIONAL:
        # Apply a reversed version of Dinic's algorithm:
        # Repeatedly build the level graph and push flow until no more flow can be sent.
        while True:
            _set_levels_bfs(dst_node, levels, residual_cap)
            # If src_node is unreachable (level <= 0), then no more flow can be pushed.
            if levels.get(src_node, -1) <= 0:
                break

            pushed = _push_flow_dfs(
                current=dst_node,
                sink=src_node,
                flow_in=float("inf"),
                residual_cap=residual_cap,
                flow_dict=flow_dict,
                levels=levels,
            )
            if pushed < MIN_FLOW:
                break
            total_flow += pushed

        if total_flow < MIN_FLOW:
            # No flow found; reset all flow values to zero.
            total_flow = 0.0
            for u in flow_dict:
                for v in flow_dict[u]:
                    flow_dict[u][v] = 0.0
        else:
            # Convert the accumulated reversed flows to the forward flow convention.
            for u in flow_dict:
                for v in flow_dict[u]:
                    flow_dict[u][v] = -(flow_dict[u][v] / total_flow)

    elif flow_placement == FlowPlacement.EQUAL_BALANCED:
        # Step 1: Distribute a nominal flow of 1.0 from src_node over the reversed graph.
        _equal_balance_bfs(src_node, succ, flow_dict)

        # Step 2: Determine the minimum ratio across edges to ensure capacities are not exceeded.
        min_ratio = float("inf")
        for u, neighbors in succ.items():
            for v in neighbors:
                assigned_flow = flow_dict[u][v]
                if assigned_flow >= MIN_FLOW:
                    cap_uv = residual_cap[u].get(v, 0.0)
                    if assigned_flow > 0.0:
                        ratio = cap_uv / assigned_flow
                        if ratio < min_ratio:
                            min_ratio = ratio

        if min_ratio == float("inf") or min_ratio < MIN_FLOW:
            # No feasible flow could be established.
            total_flow = 0.0
        else:
            total_flow = min_ratio
            # Scale the BFS distribution so that the flow fits within capacities.
            for u in flow_dict:
                for v in flow_dict[u]:
                    val = flow_dict[u][v] * total_flow
                    flow_dict[u][v] = val if abs(val) >= MIN_FLOW else 0.0

            # Normalize flows to represent the forward direction.
            for u in flow_dict:
                for v in flow_dict[u]:
                    flow_dict[u][v] /= total_flow

    else:
        raise ValueError(f"Unsupported flow placement: {flow_placement}")

    # Clamp very small flows to zero for cleanliness.
    for u in flow_dict:
        for v in flow_dict[u]:
            if abs(flow_dict[u][v]) < MIN_FLOW:
                flow_dict[u][v] = 0.0

    return total_flow, flow_dict
