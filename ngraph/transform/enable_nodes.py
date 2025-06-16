"""Network transformation for enabling/disabling nodes."""

from __future__ import annotations

import itertools
from typing import List

from ngraph.network import Network, Node
from ngraph.transform.base import NetworkTransform, Scenario, register_transform


@register_transform("EnableNodes")
class EnableNodesTransform(NetworkTransform):
    """Enable *count* disabled nodes that match *path*.

    Ordering is configurable; default is lexical by node name.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: EnableNodes
            name: "enable_edge_nodes"      # Optional: Custom name for this step
            path: "^edge/.*"               # Regex pattern to match nodes to enable
            count: 5                       # Number of nodes to enable
            order: "name"                  # Selection order: "name", "random", or "reverse"
        ```

    Args:
        path: Regex pattern to match disabled nodes that should be enabled.
        count: Number of nodes to enable (must be positive integer).
        order: Selection strategy when multiple nodes match:
            - "name": Sort by node name (lexical order)
            - "reverse": Sort by node name in reverse order
            - "random": Random selection order
    """

    def __init__(
        self,
        path: str,
        count: int,
        order: str = "name",  # 'name' | 'random' | 'reverse'
    ):
        self.path = path
        self.count = count
        self.order = order
        self.label = f"Enable {count} nodes @ '{path}'"

    def apply(self, scenario: Scenario) -> None:
        net: Network = scenario.network
        groups = net.select_node_groups_by_path(self.path)
        candidates: List[Node] = [
            n for _lbl, nodes in groups.items() for n in nodes if n.disabled
        ]

        if self.order == "reverse":
            candidates.sort(key=lambda n: n.name, reverse=True)
        elif self.order == "random":
            import random as _rnd

            _rnd.shuffle(candidates)
        else:  # default 'name'
            candidates.sort(key=lambda n: n.name)

        for node in itertools.islice(candidates, self.count):
            node.disabled = False
