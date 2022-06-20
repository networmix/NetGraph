from typing import Dict, Hashable


class PathBundle:
    def __init__(self, src_node: Hashable, dst_node: Hashable, pred: Dict):
        self.src_node: Hashable = src_node
        self.dst_node: Hashable = dst_node
        self.pred: Dict = pred
