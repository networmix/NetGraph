"""Network transformation for enabling/disabling nodes."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

from ngraph.network import Network, Node
from ngraph.workflow.transform.base import NetworkTransform, register_transform


@register_transform("EnableNodes")
@dataclass
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
            seed: 42                       # Optional: Seed for reproducible random selection
        ```

    Args:
        path: Regex pattern to match disabled nodes that should be enabled.
        count: Number of nodes to enable (must be positive integer).
        order: Selection strategy when multiple nodes match:
            - "name": Sort by node name (lexical order)
            - "reverse": Sort by node name in reverse order
            - "random": Random selection order
        seed: Optional seed for reproducible random operations when order="random".
    """

    path: str
    count: int
    order: str = "name"  # 'name' | 'random' | 'reverse'
    seed: Optional[int] = None

    def __post_init__(self):
        self.label = f"Enable {self.count} nodes @ '{self.path}'"

    def apply(self, scenario: "Scenario") -> None:
        net: Network = scenario.network
        groups = net.select_node_groups_by_path(self.path)
        candidates: List[Node] = [
            n for _lbl, nodes in groups.items() for n in nodes if n.disabled
        ]

        if self.order == "reverse":
            candidates.sort(key=lambda n: n.name, reverse=True)
        elif self.order == "random":
            if self.seed is not None:
                # Use seeded random state for deterministic results
                rng = random.Random(self.seed)
                rng.shuffle(candidates)
            else:
                # Use global random state
                random.shuffle(candidates)
        else:  # default 'name'
            candidates.sort(key=lambda n: n.name)

        for node in itertools.islice(candidates, self.count):
            node.disabled = False
