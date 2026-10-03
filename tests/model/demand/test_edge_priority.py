"""Demand ``edge_priority``: which per-edge value ranks equal-cost alternatives."""

import netgraph_core
import pytest

from ngraph.model.demand.builder import build_demand_set
from ngraph.model.demand.spec import VALID_EDGE_PRIORITIES, TrafficDemand
from ngraph.model.flow.policy_config import (
    FlowPolicyPreset,
    core_edge_priority,
    preset_config,
)


def test_edge_priority_round_trips_through_builder_and_to_dict():
    raw = {
        "tm": [
            {"source": "A", "target": "B", "volume": 1.0, "edge_priority": "headroom"}
        ]
    }
    demand = build_demand_set(raw).get_set("tm")[0]
    assert demand.edge_priority == "headroom"
    assert demand.to_dict()["edge_priority"] == "headroom"
    default = build_demand_set({"tm": [{"source": "A", "target": "B", "volume": 1.0}]})
    assert default.get_set("tm")[0].edge_priority is None
    assert default.get_set("tm")[0].to_dict()["edge_priority"] is None


@pytest.mark.parametrize("value", VALID_EDGE_PRIORITIES)
def test_every_valid_name_is_accepted(value):
    assert (
        TrafficDemand(
            source="A", target="B", volume=1.0, edge_priority=value
        ).edge_priority
        == value
    )


def test_unknown_edge_priority_is_rejected():
    with pytest.raises(ValueError, match="edge_priority"):
        TrafficDemand(source="A", target="B", volume=1.0, edge_priority="utilisation")


def test_core_mapping_and_preset_config():
    assert core_edge_priority(None) == netgraph_core.EdgePriority.RESIDUAL
    assert core_edge_priority("capacity") == netgraph_core.EdgePriority.CAPACITY
    assert core_edge_priority("headroom") == netgraph_core.EdgePriority.HEADROOM
    with pytest.raises(ValueError, match="edge_priority"):
        core_edge_priority("bogus")
    for preset in FlowPolicyPreset:
        assert (
            preset_config(preset).selection.priority
            == netgraph_core.EdgePriority.RESIDUAL
        )
        assert (
            preset_config(preset, "headroom").selection.priority
            == netgraph_core.EdgePriority.HEADROOM
        )
