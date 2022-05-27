from __future__ import annotations
from itertools import repeat
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import (
    Any,
    Callable,
    Dict,
    Hashable,
    List,
    Optional,
    Set,
    Tuple,
    Generator,
    NamedTuple,
)

from ngraph.graph import MultiDiGraph
from ngraph.algorithms import spf, bfs, common


class PathAlg(IntEnum):
    """
    Types of path finding algorithms
    """

    SPF = 1
    BFS = 2


class EdgeFlowPlacement(IntEnum):
    # load balancing across parallel edges proportional to remaining capacity
    PROPORTIONAL = 1
    # use edge with max remaining capacity, no load balancing across parallel edges
    MAX_SINGLE_FLOW = 2
    # equal load balancing across parallel edges
    EQUAL_BALANCED = 3


class FlowRouting(IntEnum):
    NODE_BY_NODE = 1
    SOURCE_ROUTED = 2


class FlowPolicyConfig(IntEnum):
    SHORTEST_PATHS_BALANCED_NODE_BY_NODE = 1
    ALL_PATHS_PROPORTIONAL_SOURCE_ROUTED = 2
    SHORTEST_PATHS_PROPORTIONAL_SOURCE_ROUTED = 3


@dataclass
class FlowPolicy:
    flow_routing: FlowRouting
    path_alg: PathAlg
    edge_flow_placement: EdgeFlowPlacement
    edge_select: common.EdgeSelect

    def get_path_iter(
        self,
        flow_graph: MultiDiGraph,
        src_node: Hashable,
        dst_node: Hashable,
    ) -> Optional[Generator]:
        edge_select_func = common.edge_select_fabric(edge_select=self.edge_select)
        if self.path_alg == PathAlg.BFS:
            _, pred = bfs.bfs(
                flow_graph, src_node=src_node, edge_select_func=edge_select_func
            )
            if dst_node in pred:
                return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)
        elif self.path_alg == PathAlg.SPF:
            _, pred = spf.spf(
                flow_graph, src_node=src_node, edge_select_func=edge_select_func
            )
            if dst_node in pred:
                return common.resolve_paths_to_nodes_edges(src_node, dst_node, pred)


@dataclass
class Flow:
    src_node: Hashable
    dst_node: Hashable
    flow: float
    flow_policy: FlowPolicy
    label: Optional[Any] = None
    placed_flow: float = 0

    def place_flow(
        self,
        flow_graph: MultiDiGraph,
        path: Optional[Tuple] = None,
        max_fraction: float = 1,
    ) -> Tuple[float, float]:
        to_place = min(self.flow - self.placed_flow, self.flow * max_fraction)
        if path:
            placed_flow, to_place = place_flow(
                flow_graph,
                path,
                to_place,
                self.label,
                edge_flow_placement=self.flow_policy.edge_flow_placement,
            )
            self.placed_flow += placed_flow
            return placed_flow, self.flow - self.placed_flow

        if self.flow_policy.flow_routing == FlowRouting.NODE_BY_NODE:
            placed_flow, to_place = place_flow_balanced(
                flow_graph,
                self.src_node,
                self.dst_node,
                to_place,
                self.label,
            )
            self.placed_flow += placed_flow
            return placed_flow, self.flow - self.placed_flow

        if self.flow_policy.flow_routing == FlowRouting.SOURCE_ROUTED:
            total_placed = 0
            if path_iter := self.flow_policy.get_path_iter(
                flow_graph,
                self.src_node,
                self.dst_node,
            ):
                for path in path_iter:
                    if to_place > 0:
                        placed_flow, to_place = place_flow(
                            flow_graph,
                            path,
                            to_place,
                            self.label,
                        )
                        total_placed += placed_flow
                    else:
                        break
            self.placed_flow += total_placed
            return total_placed, self.flow - self.placed_flow


@dataclass
class NodeCapacity:
    node_id: Hashable
    edges: Set[int] = field(default_factory=set)
    edges_max_flow: Dict[Tuple[int], float] = field(default_factory=dict)
    max_balanced_flow: float = 0
    downstream_nodes: Dict[Tuple[int], Set[Hashable]] = field(default_factory=dict)
    flow_fraction: float = 0


class PathElementCapacity(NamedTuple):
    node_id: Hashable
    edges: Tuple[int]
    total_cap: float
    max_edge_cap: float
    min_edge_cap: float
    max_edge_cap_id: int
    min_edge_cap_id: int
    total_rem_cap: float
    max_edge_rem_cap: float
    min_edge_rem_cap: float
    max_edge_rem_cap_id: int
    min_edge_rem_cap_id: int
    edge_count: int


class PathCapacity(NamedTuple):
    max_flow: float
    max_single_flow: float
    max_balanced_flow: float


def calc_path_capacity(
    flow_graph: MultiDiGraph,
    path: Tuple,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[PathCapacity, List[PathElementCapacity]]:
    """
    Determine capacity of a given path.
    """
    R_edges = flow_graph.get_edges()
    path_element_capacities: List[PathElementCapacity] = []
    max_flow = float("inf")
    max_single_flow = float("inf")
    max_balanced_flow = float("inf")

    for node_id, edge_tuple in path[:-1]:
        edge_cap_list = [R_edges[edge_id][3][capacity_attr] for edge_id in edge_tuple]
        edge_rem_cap_list = [
            R_edges[edge_id][3][capacity_attr] - R_edges[edge_id][3][flow_attr]
            for edge_id in edge_tuple
        ]

        total_cap = sum(edge_cap_list)
        max_edge_cap = max(edge_cap_list)
        min_edge_cap = min(edge_cap_list)
        max_edge_cap_id = edge_tuple[edge_cap_list.index(max_edge_cap)]
        min_edge_cap_id = edge_tuple[edge_cap_list.index(min_edge_cap)]
        total_rem_cap = sum(edge_rem_cap_list)
        max_edge_rem_cap = max(edge_rem_cap_list)
        min_edge_rem_cap = min(edge_rem_cap_list)
        max_edge_rem_cap_id = edge_tuple[edge_rem_cap_list.index(max_edge_rem_cap)]
        min_edge_rem_cap_id = edge_tuple[edge_rem_cap_list.index(min_edge_rem_cap)]
        edge_count = len(edge_cap_list)

        path_element_capacities.append(
            PathElementCapacity(
                node_id,
                edge_tuple,
                total_cap,
                max_edge_cap,
                min_edge_cap,
                max_edge_cap_id,
                min_edge_cap_id,
                total_rem_cap,
                max_edge_rem_cap,
                min_edge_rem_cap,
                max_edge_rem_cap_id,
                min_edge_rem_cap_id,
                edge_count,
            )
        )

        max_flow = min(max_flow, total_rem_cap)
        max_single_flow = min(max_flow, max_edge_rem_cap)
        max_balanced_flow = min(max_flow, min_edge_rem_cap * edge_count)
    return (
        PathCapacity(max_flow, max_single_flow, max_balanced_flow),
        path_element_capacities,
    )


def calc_capacity_balanced(
    flow_graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    pred: Dict,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
) -> Tuple[float, Dict[Hashable, NodeCapacity]]:
    R_edges = flow_graph.get_edges()
    node_capacities: Dict[Hashable, NodeCapacity] = {}
    succ: Dict[Hashable, Dict[Hashable, Tuple[int]]] = {}

    # Find node capacities and build successors
    queue = deque([dst_node])
    while queue:
        node = queue.popleft()
        for prev_hop, edge_list in pred[node].items():
            edge_tuple = tuple(edge_list)
            succ.setdefault(prev_hop, {})[node] = edge_tuple
            edge_cap_list = [
                R_edges[edge_id][3][capacity_attr] for edge_id in edge_tuple
            ]
            edge_rem_cap_list = [
                R_edges[edge_id][3][capacity_attr] - R_edges[edge_id][3][flow_attr]
                for edge_id in edge_tuple
            ]

            max_balanced_flow = min(edge_rem_cap_list) * len(edge_cap_list)
            if node in node_capacities:
                max_balanced_flow = min(
                    max_balanced_flow, node_capacities[node].max_balanced_flow
                )

            prev_hop_node_cap = (
                node_capacities[prev_hop]
                if prev_hop in node_capacities
                else NodeCapacity(prev_hop)
            )
            prev_hop_node_cap.downstream_nodes.setdefault(edge_tuple, set()).add(node)
            if node in node_capacities:
                for node_set in node_capacities[node].downstream_nodes.values():
                    prev_hop_node_cap.downstream_nodes[edge_tuple].update(node_set)
            prev_hop_node_cap.edges_max_flow[edge_tuple] = max_balanced_flow
            prev_hop_node_cap.edges.update(edge_tuple)
            prev_hop_node_cap.max_balanced_flow = min(
                [
                    edges_max_flow / len(edge_tuple)
                    for edge_tuple, edges_max_flow in prev_hop_node_cap.edges_max_flow.items()
                ]
            ) * len(prev_hop_node_cap.edges)
            node_capacities[prev_hop] = prev_hop_node_cap
            if prev_hop != src_node:
                queue.append(prev_hop)

    # Place a flow of 1.0 and see how it balances
    queue = deque([(src_node, 1)])
    while queue:
        node, flow_fraction = queue.popleft()
        node_capacities[node].flow_fraction += flow_fraction
        for next_hop, edge_tuple in succ[node].items():
            if next_hop != dst_node:
                next_hop_flow_fraction = (
                    flow_fraction / len(node_capacities[node].edges) * len(edge_tuple)
                )
                queue.append((next_hop, next_hop_flow_fraction))
    return (
        min(
            [
                node.max_balanced_flow / node.flow_fraction
                for node in node_capacities.values()
            ]
        ),
        node_capacities,
    )


def place_flow_balanced(
    flow_graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    flow: float = float("inf"),
    flow_label: Optional[Any] = None,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
) -> Tuple[float, float]:

    _, pred = spf.spf(flow_graph, src_node)
    max_flow, node_capacities = calc_capacity_balanced(
        flow_graph, src_node, dst_node, pred, capacity_attr, flow_attr
    )
    flow_index = (src_node, dst_node, flow_label)

    R_edges = flow_graph.get_edges()
    R_nodes = flow_graph.get_nodes()

    placed_flow = min(max_flow, flow)
    remaining_flow = max(flow - max_flow if flow != float("inf") else float("inf"), 0)

    for node, node_cap in node_capacities.items():
        node_res = R_nodes[node]
        node_res[flow_attr] += node_cap.flow_fraction * placed_flow
        node_res[flows_attr].setdefault(flow_index, 0)
        node_res[flows_attr][flow_index] += node_cap.flow_fraction * placed_flow
        edge_subflow = node_cap.flow_fraction * placed_flow / len(node_cap.edges)
        for edge_id in node_cap.edges:
            R_edges[edge_id][3][flow_attr] += edge_subflow
            R_edges[edge_id][3][flows_attr].setdefault(flow_index, 0)
            R_edges[edge_id][3][flows_attr][flow_index] += edge_subflow

    return placed_flow, remaining_flow


def place_flow(
    flow_graph: MultiDiGraph,
    path: Tuple,
    flow: float = float("inf"),
    flow_label: Optional[Any] = None,
    capacity_attr: str = "capacity",
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    edge_flow_placement: EdgeFlowPlacement = EdgeFlowPlacement.PROPORTIONAL,
) -> Tuple[float, float]:
    """
    Place flow along the given path from source to destinaton.
    """
    # Determine remaining path capacity
    path_capacity, path_element_capacities = calc_path_capacity(
        flow_graph, path, capacity_attr, flow_attr
    )

    # Place flow along the path
    if edge_flow_placement == EdgeFlowPlacement.PROPORTIONAL:
        max_flow = path_capacity.max_flow
    elif edge_flow_placement == EdgeFlowPlacement.MAX_SINGLE_FLOW:
        max_flow = path_capacity.max_single_flow
    elif edge_flow_placement == EdgeFlowPlacement.EQUAL_BALANCED:
        max_flow = path_capacity.max_balanced_flow
    else:
        raise RuntimeError(f"Unknown flow_placement {edge_flow_placement}")

    remaining_flow = max(flow - max_flow if flow != float("inf") else float("inf"), 0)
    placed_flow = min(max_flow, flow)
    if not placed_flow > 0:
        return 0, flow

    src_node = path[0][0]
    dst_node = path[-1][0]
    flow_index = (src_node, dst_node, flow_label)
    R_edges = flow_graph.get_edges()
    R_nodes = flow_graph.get_nodes()
    for node_edge_tuple, path_element_cap in zip(path, path_element_capacities):
        node_id, edge_tuple = node_edge_tuple
        R_nodes[node_id][flow_attr] += placed_flow
        R_nodes[node_id][flows_attr].setdefault(flow_index, 0)
        R_nodes[node_id][flows_attr][flow_index] += placed_flow
        for edge_id in edge_tuple:
            if edge_flow_placement == EdgeFlowPlacement.PROPORTIONAL:
                flow_fraction = (
                    placed_flow
                    / path_element_cap.total_rem_cap
                    * (
                        R_edges[edge_id][3][capacity_attr]
                        - R_edges[edge_id][3][flow_attr]
                    )
                )
            elif edge_flow_placement == EdgeFlowPlacement.MAX_SINGLE_FLOW:
                flow_fraction = (
                    placed_flow
                    if edge_id == path_element_cap.max_edge_rem_cap_id
                    else 0
                )

            elif edge_flow_placement == EdgeFlowPlacement.EQUAL_BALANCED:
                flow_fraction = (
                    path_element_cap.min_edge_rem_cap * path_element_cap.edge_count
                )
            if flow_fraction:
                R_edges[edge_id][3][flow_attr] += flow_fraction
                R_edges[edge_id][3][flows_attr].setdefault(flow_index, 0)
                R_edges[edge_id][3][flows_attr][flow_index] += flow_fraction

    return placed_flow, remaining_flow


def init_flow_graph(
    flow_graph: MultiDiGraph,
    flow_attr: str = "flow",
    flows_attr: str = "flows",
    reset_flow_graph: bool = True,
) -> MultiDiGraph:
    for edge_tuple in flow_graph.get_edges().values():
        edge_tuple[3].setdefault(flow_attr, 0)
        if reset_flow_graph:
            edge_tuple[3][flow_attr] = 0
        edge_tuple[3].setdefault(flows_attr, {})

    for node_dict in flow_graph.get_nodes().values():
        node_dict.setdefault(flow_attr, 0)
        if reset_flow_graph:
            node_dict[flow_attr] = 0
        node_dict.setdefault(flows_attr, {})
    return flow_graph


def calc_max_flow(
    graph: MultiDiGraph,
    src_node: Hashable,
    dst_node: Hashable,
    flow_policy_config: FlowPolicyConfig = FlowPolicyConfig.ALL_PATHS_PROPORTIONAL_SOURCE_ROUTED,
    flow_policy: Optional[FlowPolicy] = None,
    flow_label: Optional[Any] = None,
    inplace_flow_graph: bool = False,
    reset_flow_graph: bool = False,
) -> Tuple[float, MultiDiGraph]:

    flow_graph = init_flow_graph(
        graph if inplace_flow_graph else graph.copy(),
        flow_attr="flow",
        flows_attr="flows",
        reset_flow_graph=reset_flow_graph,
    )

    flow_policy = flow_policy if flow_policy else FLOW_POLICY_MAP[flow_policy_config]
    flow = Flow(src_node, dst_node, float("inf"), flow_policy, flow_label)
    place_flows(flow_graph, flows=[flow])
    return flow.placed_flow, flow_graph


def place_flows(
    flow_graph: MultiDiGraph,
    flows: List[Flow],
) -> Tuple[List[Flow], MultiDiGraph]:

    total_to_place = sum(flow.flow - flow.placed_flow for flow in flows)
    flow_fraction = (
        common.edge_find_fabric(edge_find=common.EdgeFind.MIN_CAP_REMAINING)(
            flow_graph
        )[0]
        / total_to_place
    )
    queue = deque(flows)
    while queue:
        flow = queue.popleft()
        placed_flow, to_place = flow.place_flow(flow_graph, max_fraction=flow_fraction)
        if to_place > 0 and placed_flow > 0:
            queue.append(flow)
    return flows, flow_graph


FLOW_POLICY_MAP = {
    FlowPolicyConfig.SHORTEST_PATHS_BALANCED_NODE_BY_NODE: FlowPolicy(
        flow_routing=FlowRouting.NODE_BY_NODE,
        path_alg=PathAlg.SPF,
        edge_flow_placement=EdgeFlowPlacement.EQUAL_BALANCED,
        edge_select=common.EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
    ),
    FlowPolicyConfig.ALL_PATHS_PROPORTIONAL_SOURCE_ROUTED: FlowPolicy(
        flow_routing=FlowRouting.SOURCE_ROUTED,
        path_alg=PathAlg.BFS,
        edge_flow_placement=EdgeFlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
    ),
    FlowPolicyConfig.SHORTEST_PATHS_PROPORTIONAL_SOURCE_ROUTED: FlowPolicy(
        flow_routing=FlowRouting.SOURCE_ROUTED,
        path_alg=PathAlg.SPF,
        edge_flow_placement=EdgeFlowPlacement.PROPORTIONAL,
        edge_select=common.EdgeSelect.ALL_MIN_COST,
    ),
}
