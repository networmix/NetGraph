from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ngraph.lib.graph import StrictMultiDiGraph, NodeID, EdgeID, AttrDict
from ngraph.lib.algorithms.base import Cost, MIN_CAP, EdgeSelect


def edge_select_fabric(
    edge_select: EdgeSelect,
    select_value: Optional[Any] = None,
    edge_select_func: Optional[
        Callable[
            [
                StrictMultiDiGraph,
                NodeID,
                NodeID,
                Dict[EdgeID, AttrDict],
                Optional[Set[EdgeID]],
                Optional[Set[NodeID]],
            ],
            Tuple[Cost, List[EdgeID]],
        ]
    ] = None,
    excluded_edges: Optional[Set[EdgeID]] = None,
    excluded_nodes: Optional[Set[NodeID]] = None,
    cost_attr: str = "cost",
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Callable[
    [
        StrictMultiDiGraph,
        NodeID,
        NodeID,
        Dict[EdgeID, AttrDict],
        Optional[Set[EdgeID]],
        Optional[Set[NodeID]],
    ],
    Tuple[Cost, List[EdgeID]],
]:
    """
    Creates (fabricates) a function that selects edges between two nodes according
    to a given EdgeSelect strategy (or a user-defined function).

    Args:
        edge_select: An EdgeSelect enum specifying the selection strategy.
        select_value: An optional numeric threshold or scaling factor for capacity checks.
        edge_select_func: A user-supplied function if edge_select=USER_DEFINED.
        excluded_edges: A set of edges to ignore entirely.
        excluded_nodes: A set of nodes to skip.
        cost_attr: The edge attribute name representing cost/metric.
        capacity_attr: The edge attribute name representing capacity.
        flow_attr: The edge attribute name representing current flow.

    Returns:
        A function with signature:
            (graph, src_node, dst_node, edges_dict, excluded_edges, excluded_nodes) ->
            (selected_cost, [list_of_edge_ids])
        where `selected_cost` is the numeric cost used by the path-finding algorithm
        (e.g. Dijkstra), and `[list_of_edge_ids]` is the set (or subset) of edges chosen.
    """

    # --------------------------------------------------------------------------
    # Internal selection routines (closed over the above arguments).
    # Each of these returns (cost, [edge_ids]) indicating which edges are chosen.
    # --------------------------------------------------------------------------

    def get_all_min_cost_edges(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """Return all edges with the minimal cost among those available."""
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        edge_list: List[EdgeID] = []
        min_cost = float("inf")
        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue
            cost_val = attr[cost_attr]

            if cost_val < min_cost:
                min_cost = cost_val
                edge_list = [edge_id]
            elif abs(cost_val - min_cost) < 1e-12:
                # If cost_val == min_cost
                edge_list.append(edge_id)

        return min_cost, edge_list

    def get_single_min_cost_edge(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """Return exactly one edge: the single lowest-cost edge."""
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        chosen_edge: List[EdgeID] = []
        min_cost = float("inf")
        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue
            cost_val = attr[cost_attr]

            if cost_val < min_cost:
                min_cost = cost_val
                chosen_edge = [edge_id]

        return min_cost, chosen_edge

    def get_all_edges_with_cap_remaining(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """
        Return all edges that have remaining capacity >= min_cap, ignoring
        their cost except for reporting the minimal one found.
        """
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        edge_list: List[EdgeID] = []
        min_cost = float("inf")
        min_cap = select_value if select_value is not None else MIN_CAP

        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue

            if (attr[capacity_attr] - attr[flow_attr]) >= min_cap:
                cost_val = attr[cost_attr]
                min_cost = min(min_cost, cost_val)
                edge_list.append(edge_id)

        return min_cost, edge_list

    def get_all_min_cost_edges_with_cap_remaining(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """
        Return all edges that have remaining capacity >= min_cap,
        among those with the minimum cost.
        """
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        edge_list: List[EdgeID] = []
        min_cost = float("inf")
        min_cap = select_value if select_value is not None else MIN_CAP

        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue

            available_cap = attr[capacity_attr] - attr[flow_attr]
            if available_cap >= min_cap:
                cost_val = attr[cost_attr]
                if cost_val < min_cost:
                    min_cost = cost_val
                    edge_list = [edge_id]
                elif abs(cost_val - min_cost) < 1e-12:
                    edge_list.append(edge_id)

        return min_cost, edge_list

    def get_single_min_cost_edge_with_cap_remaining(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """
        Return exactly one edge with the minimal cost among those with
        remaining capacity >= min_cap.
        """
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        chosen_edge: List[EdgeID] = []
        min_cost = float("inf")
        min_cap = select_value if select_value is not None else MIN_CAP

        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue

            if (attr[capacity_attr] - attr[flow_attr]) >= min_cap:
                cost_val = attr[cost_attr]
                if cost_val < min_cost:
                    min_cost = cost_val
                    chosen_edge = [edge_id]

        return min_cost, chosen_edge

    def get_single_min_cost_edge_with_cap_remaining_load_factored(
        graph: StrictMultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        edges_map: Dict[EdgeID, AttrDict],
        ignored_edges: Optional[Set[EdgeID]] = None,
        ignored_nodes: Optional[Set[NodeID]] = None,
    ) -> Tuple[Cost, List[EdgeID]]:
        """
        Return exactly one edge, factoring both 'cost_attr' and load level
        into a combined cost:
            combined_cost = (cost * 100) + round((flow / capacity) * 10)
        Only edges with remaining capacity >= min_cap are considered.
        """
        if ignored_nodes and dst_node in ignored_nodes:
            return float("inf"), []

        chosen_edge: List[EdgeID] = []
        min_cost_factor = float("inf")
        min_cap = select_value if select_value is not None else MIN_CAP

        for edge_id, attr in edges_map.items():
            if ignored_edges and edge_id in ignored_edges:
                continue

            remaining_cap = attr[capacity_attr] - attr[flow_attr]
            if remaining_cap >= min_cap:
                load_factor = round((attr[flow_attr] / attr[capacity_attr]) * 10)
                cost_val = attr[cost_attr] * 100 + load_factor
                if cost_val < min_cost_factor:
                    min_cost_factor = cost_val
                    chosen_edge = [edge_id]

        return float(min_cost_factor), chosen_edge

    # --------------------------------------------------------------------------
    # Fabric: map the EdgeSelect enum to the appropriate inner function.
    # --------------------------------------------------------------------------
    if edge_select == EdgeSelect.ALL_MIN_COST:
        return get_all_min_cost_edges
    elif edge_select == EdgeSelect.SINGLE_MIN_COST:
        return get_single_min_cost_edge
    elif edge_select == EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING:
        return get_all_min_cost_edges_with_cap_remaining
    elif edge_select == EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING:
        return get_all_edges_with_cap_remaining
    elif edge_select == EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING:
        return get_single_min_cost_edge_with_cap_remaining
    elif edge_select == EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED:
        return get_single_min_cost_edge_with_cap_remaining_load_factored
    elif edge_select == EdgeSelect.USER_DEFINED:
        if edge_select_func is None:
            raise ValueError(
                "edge_select=USER_DEFINED requires 'edge_select_func' to be provided."
            )
        return edge_select_func
    else:
        raise ValueError(f"Unknown edge_select value {edge_select}")
