"""Flow policy configuration for NetGraph.

Preset traffic routing configurations used by demand placement and flow
analysis.

Public API:
    FlowPolicyPreset: Enum of common flow policy configurations
    create_flow_policy: Factory function to create FlowPolicy instances
    serialize_policy_preset: Serialize preset to string for JSON storage
"""

from ngraph.model.flow.policy_config import (
    FlowPolicyPreset,
    create_flow_policy,
    serialize_policy_preset,
)

__all__ = [
    "FlowPolicyPreset",
    "create_flow_policy",
    "serialize_policy_preset",
]
