"""Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. Routing behavior is selected via an optional `FlowPolicyPreset`,
or pinned to explicit routes with `StaticPath`.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, Union

from ngraph.model.flow.policy_config import FlowPolicyPreset, serialize_policy_preset
from ngraph.types.base import Mode
from ngraph.utils.ids import new_base64_uuid

# Derived from the Mode enum so the vocabulary is defined once.
_VALID_MODES = tuple(m.name.lower() for m in Mode)
_VALID_GROUP_MODES = ("flatten", "per_group", "group_pairwise")


@dataclass(frozen=True)
class StaticPath:
    """One explicit route a demand can be pinned to (an MPLS-style LSP).

    Give exactly one of `nodes` or `links`:

    - `nodes`: the node names the route visits, source first and target last.
      Each consecutive pair must be adjacent. When several parallel links
      connect a pair, the cheapest is used (ties broken by link id); name the
      link explicitly to choose a different one.
    - `links`: the link ids the route traverses, in order. Unambiguous when
      parallel links exist. A link may be traversed in either direction.

    Attributes:
        nodes: Node names along the route, or empty when `links` is given.
        links: Link ids along the route, or empty when `nodes` is given.
    """

    nodes: Tuple[str, ...] = ()
    links: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.nodes) == bool(self.links):
            raise ValueError("StaticPath requires exactly one of 'nodes' or 'links'")
        if self.nodes and len(self.nodes) < 2:
            raise ValueError("StaticPath 'nodes' needs at least a source and a target")


@dataclass
class TrafficDemand:
    """Traffic demand specification using unified selectors.

    Attributes:
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        volume: Total demand volume.
        priority: Priority class (lower = higher priority).
        mode: Node pairing mode ("combine" or "pairwise").
        group_mode: How grouped nodes produce demands
            ("flatten", "per_group", "group_pairwise").
        flow_policy: Policy preset for routing.
        static_paths: Explicit routes to pin this demand to. When set, the
            demand is placed only on these routes: one flow per route, and a
            route broken by a failure carries nothing rather than rerouting.
            Requires selectors matching exactly one source and one target.
        attrs: Arbitrary user metadata.
        id: Unique identifier. Auto-generated if empty.
    """

    source: Union[str, Dict[str, Any]] = ""
    target: Union[str, Dict[str, Any]] = ""
    volume: float = 0.0
    priority: int = 0
    mode: str = "combine"
    group_mode: str = "flatten"
    flow_policy: Optional[FlowPolicyPreset] = None
    static_paths: Tuple[StaticPath, ...] = ()
    attrs: Dict[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        """Validate mode fields and generate id if not provided."""
        if self.mode not in _VALID_MODES:
            raise ValueError(
                f"Unknown demand mode '{self.mode}'. "
                f"Expected one of: {', '.join(_VALID_MODES)}"
            )
        if self.group_mode not in _VALID_GROUP_MODES:
            raise ValueError(
                f"Unknown demand group_mode '{self.group_mode}'. "
                f"Expected one of: {', '.join(_VALID_GROUP_MODES)}"
            )
        for path in self.static_paths:
            if not isinstance(path, StaticPath):
                raise ValueError(
                    f"static_paths entries must be StaticPath objects, got "
                    f"{type(path).__name__}"
                )
        if not self.id:
            # Build a stable identifier from source/target
            src_key = self.source if isinstance(self.source, str) else str(self.source)
            tgt_key = self.target if isinstance(self.target, str) else str(self.target)
            self.id = f"{src_key}|{tgt_key}|{new_base64_uuid()}"

    def to_dict(self) -> Dict[str, Any]:
        """Return the canonical serialized form (results output, snapshots).

        The flow policy is serialized to its preset name; use the raw
        `flow_policy` attribute for analysis wire formats that expect the
        preset object.
        """
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "volume": float(self.volume),
            "priority": int(self.priority),
            "mode": self.mode,
            "group_mode": self.group_mode,
            "flow_policy": serialize_policy_preset(self.flow_policy),
            "static_paths": [
                {"nodes": list(p.nodes)} if p.nodes else {"links": list(p.links)}
                for p in self.static_paths
            ],
            "attrs": dict(self.attrs),
        }
