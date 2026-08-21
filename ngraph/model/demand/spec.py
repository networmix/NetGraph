"""Traffic demand specification.

Defines `TrafficDemand`, a user-facing specification used by demand expansion
and placement. Routing behavior is selected via an optional `FlowPolicyPreset`.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

from ngraph.model.flow.policy_config import FlowPolicyPreset, serialize_policy_preset
from ngraph.types.base import Mode
from ngraph.utils.ids import new_base64_uuid

# Derived from the Mode enum so the vocabulary is defined once.
_VALID_MODES = tuple(m.name.lower() for m in Mode)
_VALID_GROUP_MODES = ("flatten", "per_group", "group_pairwise")


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
            "attrs": dict(self.attrs),
        }
