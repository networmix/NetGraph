from typing import Any, Dict, Generator
from ngraph.graph import MultiDiGraph


class MultiDiGraphNX(MultiDiGraph):
    """
    This class implements a Directed Multigraph compatible with NetworkX library.
    """

    def __init__(self, **attr: Dict[Any, Any]):
        super().__init__(**attr)
        self._succ = self._adj_out

    def is_directed(self) -> bool:
        return True

    def edges(self) -> Generator:
        for edge_tuple in self._edges.values():
            yield edge_tuple[0], edge_tuple[1]

    def nodes(self) -> Generator:
        for node in self._nodes:
            yield node
