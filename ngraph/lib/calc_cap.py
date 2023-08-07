from __future__ import annotations
from collections import deque
from typing import (
    Deque,
    Dict,
    List,
    Set,
    Tuple,
)
from ngraph.lib.common import FlowPlacement
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID


class CalculateCapacity:
    @staticmethod
    def _init(
        flow_graph: MultiDiGraph,
        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
        src_node: NodeID,
        flow_placement: FlowPlacement,
        capacity_attr: str = "capacity",
        flow_attr: str = "flow",
    ) -> Tuple[
        Dict[NodeID, Dict[NodeID, Tuple[EdgeID]]],
        Dict[NodeID, int],
        Dict[NodeID, Dict[NodeID, float]],
    ]:
        """
        Initialize the data structures needed for Dinic's algorithm.
        """
        edges = flow_graph.get_edges()
        succ: Dict[NodeID, Dict[NodeID, Tuple[EdgeID]]] = {}
        levels: Dict[NodeID, int] = {}
        residual_cap_dict: Dict[NodeID, Dict[NodeID, float]] = {}
        flow_dict: Dict[NodeID, Dict[NodeID, float]] = {}

        visited: Set[NodeID] = set()
        queue: Deque[NodeID] = deque([src_node])
        while queue:
            node = queue.popleft()
            visited.add(node)
            succ.setdefault(node, {})
            levels.setdefault(node, -1)
            residual_cap_dict.setdefault(node, {})
            flow_dict.setdefault(node, {})

            for adj_node, edge_list in pred.get(node, {}).items():
                edge_tuple = tuple(edge_list)
                succ.setdefault(adj_node, {})[node] = edge_tuple
                residual_cap_dict.setdefault(adj_node, {})
                flow_dict.setdefault(adj_node, {})

                if flow_placement == FlowPlacement.PROPORTIONAL:
                    residual_cap_dict[node][adj_node] = sum(
                        edges[edge][3][capacity_attr] - edges[edge][3][flow_attr]
                        for edge in edge_tuple
                    )
                    residual_cap_dict[adj_node][node] = 0
                elif flow_placement == FlowPlacement.EQUAL_BALANCED:
                    residual_cap_dict[adj_node][node] = min(
                        edges[edge][3][capacity_attr] - edges[edge][3][flow_attr]
                        for edge in edge_tuple
                    ) * len(edge_tuple)
                else:
                    raise ValueError(
                        f"Flow placement {flow_placement} is not supported."
                    )

                flow_dict[node][adj_node] = 0
                flow_dict[adj_node][node] = 0
                if adj_node not in visited:
                    queue.append(adj_node)

        return succ, levels, residual_cap_dict, flow_dict

    @staticmethod
    def _set_levels_bfs(
        src_node: NodeID,
        levels: Dict[NodeID, int],
        residual_cap_dict: Dict[NodeID, Dict[NodeID, float]],
    ) -> Dict[NodeID, int]:
        """
        The first step of Dinic's algorithm:
        Use Breadth-first search to find if more flow can be pushed through the graph
        and assign levels to each node along the way.
        """

        for node in levels:
            levels[node] = -1

        levels[src_node] = 0
        queue: Deque[NodeID] = deque([src_node])

        while queue:
            node = queue.popleft()
            for next_node, residual_cap in residual_cap_dict[node].items():
                if levels[next_node] < 0 and residual_cap > 0:
                    levels[next_node] = levels[node] + 1
                    queue.append(next_node)
        return levels

    @staticmethod
    def _equal_balance_bfs(
        src_node: NodeID,
        succ: Dict[NodeID, Dict[NodeID, Tuple[EdgeID]]],
        flow_dict: Dict[NodeID, Dict[NodeID, float]],
    ) -> Dict[NodeID, Dict[NodeID, float]]:
        node_split: Dict[NodeID, int] = {}
        for node in succ:
            node_split.setdefault(node, 0)
            for next_node, next_edge_tuple in succ[node].items():
                node_split[node] += len(next_edge_tuple)

        queue: Deque[Tuple[NodeID, float]] = deque([(src_node, 1)])
        while queue:
            node, flow = queue.popleft()
            for next_node, next_edge_tuple in succ[node].items():
                next_flow = flow * len(next_edge_tuple) / node_split[node]
                flow_dict[node][next_node] += next_flow
                flow_dict[next_node][node] -= next_flow
                queue.append((next_node, next_flow))
        return flow_dict

    @classmethod
    def _push_flow_dfs(
        cls,
        src_node: NodeID,
        dst_node: NodeID,
        flow: float,
        residual_cap_dict: Dict[NodeID, Dict[NodeID, float]],
        flow_dict: Dict[NodeID, Dict[NodeID, float]],
        levels: Dict[NodeID, int],
    ) -> float:
        """
        The second step of Dinic's algorithm:
        Use Depth-first search to push flow through the graph.
        """
        if src_node == dst_node:
            return flow

        tmp_flow = 0
        for next_node, residual_cap in residual_cap_dict[src_node].items():
            if levels[next_node] == levels[src_node] + 1 and residual_cap > 0:
                if next_node != dst_node and levels[next_node] >= levels[dst_node]:
                    continue
                pushed_flow = cls._push_flow_dfs(
                    next_node,
                    dst_node,
                    min(residual_cap, flow),
                    residual_cap_dict,
                    flow_dict,
                    levels,
                )
                if pushed_flow > 0:
                    residual_cap_dict[src_node][next_node] -= pushed_flow
                    residual_cap_dict[next_node][src_node] += pushed_flow
                    flow_dict[src_node][next_node] += pushed_flow
                    flow_dict[next_node][src_node] -= pushed_flow
                    tmp_flow += pushed_flow
                    flow -= pushed_flow
        return tmp_flow

    @classmethod
    def calc_graph_cap(
        cls,
        flow_graph: MultiDiGraph,
        src_node: NodeID,
        dst_node: NodeID,
        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]],
        flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL,
        capacity_attr: str = "capacity",
        flow_attr: str = "flow",
    ) -> Tuple[float, Dict[NodeID, Dict[NodeID, float]]]:
        """
        Calculate capacity between src_node and dst_node in a flow graph
        using a Dinic's algorithm.
        """

        # Check if src_node and dst_node are in the graph
        if src_node not in flow_graph or dst_node not in flow_graph:
            raise ValueError(
                f"Source node {src_node} or destination node {dst_node} not found in the graph."
            )

        succ, levels, residual_cap_dict, flow_dict = cls._init(
            flow_graph, pred, dst_node, flow_placement, capacity_attr, flow_attr
        )

        if flow_placement == FlowPlacement.PROPORTIONAL:
            total_flow = 0
            while (
                levels := cls._set_levels_bfs(dst_node, levels, residual_cap_dict)
            ).get(src_node, 0) > 0:
                tmp_flow = cls._push_flow_dfs(
                    dst_node,
                    src_node,
                    float("inf"),
                    residual_cap_dict,
                    flow_dict,
                    levels,
                )
                total_flow += tmp_flow

            for node in flow_dict:
                for next_node in flow_dict[node]:
                    if total_flow:
                        flow_dict[node][next_node] /= -total_flow
                    else:
                        flow_dict[node][next_node] = 0

        elif flow_placement == FlowPlacement.EQUAL_BALANCED:
            flow_dict = cls._equal_balance_bfs(src_node, succ, flow_dict)
            total_flow = float("inf")
            for node in succ:
                for next_node in succ[node]:
                    total_flow = min(
                        total_flow,
                        residual_cap_dict[node][next_node] / flow_dict[node][next_node],
                    )

        else:
            raise ValueError(f"Flow placement {flow_placement} is not supported.")

        return total_flow, flow_dict
