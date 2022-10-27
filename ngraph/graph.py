from __future__ import annotations
from pickle import dumps, loads
from typing import Any, Callable, Dict, Hashable, Iterator, Optional, Tuple


NodeID = Hashable
SrcNodeID = NodeID
DstNodeID = NodeID
EdgeID = int
AttrDict = Dict[Hashable, Any]
EdgeTuple = Tuple[SrcNodeID, DstNodeID, EdgeID, AttrDict]


class MultiDiGraph:
    """
    This class implements a data structure representing a Directed Multigraph.
    The intent is to keep this class largely compatible with NetworkX library while making edges first-class entities.
    By definition, the edges of a directed graph are directed and there could be several parallel edges
    between a pair of nodes (so it is a multigraph).
    A graph consists of nodes and edges. Nodes are kept straight in a Python dictionary. Edges are adjacency-encoded,
    and, at the same time, each edge has its own identity in a form of a unique index.
    Nodes, edges and the graph itself can have associated attributes.
    The adjacency structure is implemented with Python nested dictionaries:
        {src_node: {dst_node: edge_id: {**edge_attr}}}
    Edges are stored as tuples indexed by unique ids:
        {edge_id: (src_node, dst_node, edge_id, {**edge_attr})}
    Attributes:
        _graph: dictionary for graph attributes
        _nodes: dictionary for nodes
        _edges: dictionary for edges
        _succ: dictionary for outgoing adjacencies (successors, in other words, adjacent destination nodes)
        _pred: dictionary for incoming adjacencies (predecessors, in other words, adjacent source nodes)
        _next_edge_id: all edges are unique, hence it is the index for the next added edge
    """

    def __init__(self, **attr: AttrDict) -> None:
        self._graph: AttrDict = attr
        self._nodes: Dict[NodeID, AttrDict] = {}
        self._edges: Dict[EdgeID, EdgeTuple] = {}
        self._succ: Dict[
            SrcNodeID, Dict[DstNodeID, Dict[EdgeID, AttrDict]]
        ] = {}  # dictionary for outgoing adjacencies (successors)
        self._pred: Dict[
            DstNodeID, Dict[SrcNodeID, Dict[EdgeID, AttrDict]]
        ] = {}  # dictionary for incoming adjacencies (predecessors)

        self._next_edge_id: EdgeID = 0  # the index for the next added edge

        self._adj = self._succ  # alias for compatibility with NetworkX

    def __contains__(self, node: NodeID) -> bool:
        """
        Enables expressions like "node" in graph
        Returns:
            True if node_id is in the graph and False otherwise.
        """
        return node in self._nodes

    def __getitem__(self, node: NodeID) -> Dict:
        """
        Making MultiDiGraph objects subscriptable.
        Returns {dst_node: edge_id: {**edge_attr}}
        """
        return self._succ[node]

    def __iter__(self) -> Iterator:
        """
        Making MultiDiGraph objects iterable by their nodes
        """
        return iter(self._nodes.keys())

    def __len__(self) -> int:
        """
        Return the number of nodes as the length of the graph.
        Returns:
            The number of nodes in the graph.
        """
        return len(self._nodes)

    def copy(self) -> MultiDiGraph:
        """
        Make a deep copy of the graph and return it.
        Pickle is used for performance reasons.

        Returns:
            MultiDiGraph - copy of the graph.
        """
        return loads(dumps(self))

    def get_next_edge_id(self) -> EdgeID:
        next_edge_id = self._next_edge_id
        self._next_edge_id += 1
        return next_edge_id

    def add_node(self, node_to_add: NodeID, **attr: AttrDict) -> None:
        """
        Add a single node with optional attributes. If the node is present - do nothing.
        Args:
            node_to_add: node identifier.
                Can be any hashable Python object.
            attr: optional node attributes in a form of keyword arguments (k=v pairs).
        """
        if node_to_add not in self._nodes:
            self._nodes[node_to_add] = attr
            self._succ[node_to_add] = {}
            self._pred[node_to_add] = {}

    def add_edge(
        self,
        src_node: NodeID,
        dst_node: NodeID,
        edge_id: Optional[EdgeID] = None,
        **attr: AttrDict,
    ) -> None:
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
        if edge_id is None:
            edge_id = self.get_next_edge_id()

        if src_node not in self._nodes:
            self.add_node(src_node)

        if dst_node not in self._nodes:
            self.add_node(dst_node)

        self._edges[edge_id] = (src_node, dst_node, edge_id, attr)
        self._succ[src_node].setdefault(dst_node, {})[edge_id] = attr
        self._pred[dst_node].setdefault(src_node, {})[edge_id] = attr

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
        if src_node not in self._nodes or dst_node not in self._nodes:
            return

        if edge_id is not None:
            if edge_id not in self._edges:
                return

            del self._edges[edge_id]
            del self._succ[src_node][dst_node][edge_id]
            del self._pred[dst_node][src_node][edge_id]
            if not self._succ[src_node][dst_node]:
                del self._succ[src_node][dst_node]
                del self._pred[dst_node][src_node]

        else:
            for _edge_id in self._succ[src_node][dst_node]:
                del self._edges[_edge_id]
            del self._succ[src_node][dst_node]
            del self._pred[dst_node][src_node]

    def remove_node(self, node_to_remove: NodeID) -> None:
        """
        Remove a node. It also removes all the edges this node participates in.
        If the node doesn't exist, it will do nothing.
        Args:
            node_to_remove: node identifier.
        """
        if node_to_remove not in self._nodes:
            return

        for remote_node in list(self._succ[node_to_remove].keys()):
            self.remove_edge(node_to_remove, remote_node)
            self.remove_edge(remote_node, node_to_remove)

        del self._succ[node_to_remove]
        del self._pred[node_to_remove]
        del self._nodes[node_to_remove]

    def get_adj_out(self) -> Dict[SrcNodeID, Dict[DstNodeID, Dict[EdgeID, AttrDict]]]:
        """
        Get a dictionary with outgoing adjacencies (successors).
        The format is:
        {src_node: {dst_node: edge_id: {**edge_attr}}}
        Do not remove or add any adjacencies using this dictionary.
        It will break the consistency of the graph object.
        Use only respective graph methods for that purpose.
        Returns:
            A dict with all outgoing adjacencies.
        """
        return self._succ

    def get_adj_in(self) -> Dict[DstNodeID, Dict[SrcNodeID, Dict[EdgeID, AttrDict]]]:
        """
        Get a dictionary with incoming adjacencies (predecessors).
        The format is:
        {dst_node: {src_node: edge_id: {**edge_attr}}}
        Do not remove or add any adjacencies using this dictionary.
        It will break the consistency of the graph object.
        Use only respective graph methods for that purpose.
        Returns:
            A dict with all incoming adjacencies.
        """
        return self._pred

    def get_attr(self) -> AttrDict:
        """
        Get a dictionary with all graph attributes.
        Returns:
            A dict with all graph attributes.
        """
        return self._graph

    def get_nodes(self) -> Dict[NodeID, AttrDict]:
        """
        Get a dictionary with all nodes and their attributes.
        Returns:
            A dict with all node_ids maped into their attributes.
        """
        return self._nodes

    def get_edges(self) -> Dict[EdgeID, EdgeTuple]:
        """
        Get a dictionary with all edges and their attributes.
        Edges are stored as tuples indexed by their unique ids:
            {edge_id: (src_node, dst_node, edge_id, {**edge_attr})}
        Returns:
            A dict with all edge_ids maped into their attributes.
        """
        return self._edges

    def filter(
        self,
        node_filter: Callable[[NodeID, Dict], bool] = lambda node_id, node_attr: True,
        edge_filter: Callable[[NodeID, Tuple], bool] = lambda edge_id, edge_tuple: True,
    ) -> MultiDiGraph:
        graph = self.copy()

        for node_id, node_attr in self.get_nodes().items():
            if not node_filter(node_id, node_attr):
                graph.remove_node(node_id)

        for edge_id, edge_tuple in self.get_edges().items():
            if not edge_filter(edge_id, edge_tuple):
                graph.remove_edge(edge_tuple[0], edge_tuple[1], edge_tuple[2])
        return graph

    def is_directed(self) -> bool:
        return True

    def edges(self) -> Iterator[Tuple[SrcNodeID, DstNodeID]]:
        for edge_tuple in self._edges.values():
            yield edge_tuple[0], edge_tuple[1]

    def nodes(self) -> Iterator[NodeID]:
        for node in self._nodes:
            yield node

    def neighbors(self, node) -> Iterator[NodeID]:
        """
        Returns an iterator over neighbors of a given node.
        Compatibility with NetworkX.
        """
        return iter(self._adj[node])
