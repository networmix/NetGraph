from typing import Any, Dict, Hashable
from ngraph.graph import MultiDiGraph


class MultiDiGraphNX(MultiDiGraph):
    """
    This class implements a Directed Multigraph compatible with NetworkX library.
    """

    def __init__(self, **attr: Dict[Any, Any]):
        super().__init__(**attr)
        self._succ = self._adj_out

    def __getitem__(self, node: Hashable):
        return self._adj_out[node]

    def is_directed(self) -> bool:
        return True
