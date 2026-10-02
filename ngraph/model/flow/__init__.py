"""Flow policy configuration for NetGraph.

Preset traffic routing configurations used by demand placement and flow
analysis.

Public API:
    FlowPolicyPreset: Enum of common flow policy configurations
    create_flow_policy: Factory function to create FlowPolicy instances
"""

from ngraph.model.flow.policy_config import (
    FlowPolicyPreset,
    create_flow_policy,
)

__all__ = [
    "FlowPolicyPreset",
    "create_flow_policy",
]
