from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset as FlowPolicyConfig


def test_defaults_and_id_generation() -> None:
    """TrafficDemand sets sane defaults and generates a unique, structured id."""
    demand = TrafficDemand(source_path="Src", sink_path="Dst")

    # Defaults
    assert demand.priority == 0
    assert demand.demand == 0.0
    assert demand.demand_placed == 0.0
    assert demand.mode == "combine"
    assert demand.attrs == {}

    # ID structure: "<source>|<sink>|<uuid>" and uniqueness across instances
    parts = demand.id.split("|")
    assert parts[0] == "Src"
    assert parts[1] == "Dst"
    assert len(parts) == 3
    assert all(parts)

    demand2 = TrafficDemand(source_path="Src", sink_path="Dst")
    assert demand2.id != demand.id


def test_explicit_id_preserved() -> None:
    """TrafficDemand with explicit ID preserves it unchanged."""
    demand = TrafficDemand(
        id="my-explicit-id",
        source_path="Src",
        sink_path="Dst",
        demand=100.0,
    )
    assert demand.id == "my-explicit-id"


def test_explicit_id_round_trip() -> None:
    """TrafficDemand ID survives serialization to dict and reconstruction."""
    original = TrafficDemand(source_path="A", sink_path="B", demand=50.0)
    original_id = original.id

    # Simulate serialization (as done in workflow steps)
    config = {
        "id": original.id,
        "source_path": original.source_path,
        "sink_path": original.sink_path,
        "demand": original.demand,
        "mode": original.mode,
        "priority": original.priority,
    }

    # Simulate reconstruction (as done in flow.py)
    reconstructed = TrafficDemand(
        id=config.get("id"),
        source_path=config["source_path"],
        sink_path=config["sink_path"],
        demand=config["demand"],
        mode=config.get("mode", "pairwise"),
        priority=config.get("priority", 0),
    )

    assert reconstructed.id == original_id


def test_attrs_isolation_between_instances() -> None:
    """Each instance gets its own attrs dict; mutating one does not affect others."""
    d1 = TrafficDemand(source_path="A", sink_path="B")
    d2 = TrafficDemand(source_path="A", sink_path="B")

    d1.attrs["k"] = "v"
    assert d1.attrs == {"k": "v"}
    assert d2.attrs == {}


def test_custom_assignment_including_policy_config() -> None:
    """Custom field values are preserved, including mode and policy config."""
    demand = TrafficDemand(
        source_path="SourceNode",
        sink_path="TargetNode",
        priority=5,
        demand=42.5,
        demand_placed=10.0,
        attrs={"description": "test"},
        mode="pairwise",
        flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )

    assert demand.source_path == "SourceNode"
    assert demand.sink_path == "TargetNode"
    assert demand.priority == 5
    assert demand.demand == 42.5
    assert demand.demand_placed == 10.0
    assert demand.attrs == {"description": "test"}
    assert demand.mode == "pairwise"
    assert demand.flow_policy_config == FlowPolicyConfig.SHORTEST_PATHS_ECMP
