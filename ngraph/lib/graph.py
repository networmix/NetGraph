from __future__ import annotations
from pickle import dumps, loads
from typing import Any, Callable, Dict, Hashable, Iterator, Optional, Tuple

import networkx as nx


NodeID = Hashable
EdgeID = Hashable
AttrDict = Dict[Hashable, Any]
EdgeTuple = Tuple[NodeID, NodeID, EdgeID, AttrDict]


class MultiDiGraph(nx.MultiDiGraph):
    """
    This class is a wrapper around NetworkX MultiDiGraph.
    It makes edge ids unique and provides a convenient way to access edges by their ids.
    """

    def __init__(self, incoming_graph_data=None, multigraph_input=None, **attr) -> None:
        super().__init__(
            incoming_graph_data=incoming_graph_data,
            multigraph_input=multigraph_input,
            **attr,
        )
        self._edges: Dict[EdgeID, EdgeTuple] = {}
        self._next_edge_id: EdgeID = 0  # the index for the next added edge

    def new_edge_key(self, src_node: NodeID, dst_node: NodeID) -> EdgeID:
        """
        Get a new unique edge id between src_node and dst_node.
        Overriding this method is necessary because NetworkX
        has a different default implementation of edge ids.
        Args:
            src_node: source node identifier.
            dst_node: destination node identifier.
        Returns:
            A new unique edge id.
        """
        next_edge_id = self._next_edge_id
        self._next_edge_id += 1
        return next_edge_id

    def copy(self) -> MultiDiGraph:
        """
        Make a deep copy of the graph and return it.
        Pickle is used for performance reasons.

        Returns:
            MultiDiGraph - copy of the graph.
        """
        return loads(dumps(self))

    def add_edge(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        edge_id: Optional[EdgeID] = None,
        **attr: AttrDict,
    ) -> EdgeID:
        """
        Add a single edge between src_node and dst_node with optional attributes.
        If optional edge_id is supplied, this method checks if an edge with such id already exists.
        If it does not exist - the method creates it. Otherwise, it replaces the attributes.
        In the case where source and/or destination nodes do not exist, the method creates them.
        Args:
            src_node: source node identifier.
            dst_node: destination node identifier.
            edge_id: optional unique edge id.
            attr: optional node attributes in a form of keyword arguments (k=v pairs).
        """
        edge_id = super().add_edge(src_node, dst_node, key=edge_id, **attr)
        self._edges[edge_id] = (
            src_node,
            dst_node,
            edge_id,
            self[src_node][dst_node][edge_id],
        )
        return edge_id

    def remove_edge(
        self, src_node: NodeID, dst_node: NodeID, edge_id: Optional[EdgeID] = None
    ) -> None:
        """
        Remove an edge between src_node and dst_node.
        If edge_id is given, it will remove
        that edge or, if it doesn't exist, it will do nothing.
        If the are multiple edges between the given source and dstination nodes,
        all of them will be removed (obeying provided direction).
        Args:
            src_node: source node identifier.
            dst_node: destination node identifier.
            edge_id: optional unique edge id.
        """
        if src_node not in self or dst_node not in self:
            return

        if edge_id is not None:
            if edge_id not in self.succ[src_node][dst_node]:
                raise ValueError(
                    f"Edge with id {edge_id} does not exist between {src_node} and {dst_node}."
                )
            self.remove_edge_by_id(edge_id)

        else:
            for edge_id in tuple(self.succ[src_node][dst_node]):
                del self._edges[edge_id]
                super().remove_edge(src_node, dst_node)

    def remove_edge_by_id(self, edge_id: EdgeID) -> None:
        """
        Remove an edge by its id.
        Args:
            edge_id: edge identifier.
        """
        if edge_id not in self._edges:
            raise ValueError(f"Edge with id {edge_id} does not exist.")

        src_node, dst_node, _, _ = self._edges[edge_id]
        del self._edges[edge_id]
        super().remove_edge(src_node, dst_node, key=edge_id)

    def remove_node(self, node_to_remove: NodeID) -> None:
        """
        Remove a node. It also removes all the edges this node participates in.
        If the node doesn't exist, it will do nothing.
        Args:
            node_to_remove: node identifier.
        """
        if node_to_remove not in self:
            return

        for remote_node in list(self.succ[node_to_remove].keys()):
            self.remove_edge(node_to_remove, remote_node)
            self.remove_edge(remote_node, node_to_remove)

        super().remove_node(node_to_remove)

    def get_nodes(self) -> Dict[NodeID, AttrDict]:
        """
        Get a dictionary with all nodes and their attributes.
        Returns:
            A dict with all node_ids maped into their attributes.
        """
        return {node_id: node_data for node_id, node_data in self.nodes.items()}

    def get_edges(self) -> Dict[EdgeID, EdgeTuple]:
        """
        Get a dictionary with all edges and their attributes.
        Edges are stored as tuples indexed by their unique ids:
            {edge_id: (src_node, dst_node, edge_id, {**edge_attr})}
        Returns:
            A dict with all edge_ids maped into their attributes.
        """
        return self._edges

    def get_edge_attr(self, edge_id: EdgeID) -> AttrDict:
        """
        Get a dictionary with all edge attributes by edge id.
        Returns:
            A dict with all edge attributes.
        """
        return self._edges[edge_id][3]
