from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset as FlowPolicyConfig


def test_defaults_and_id_generation() -> None:
    """TrafficDemand sets sane defaults and generates a unique, structured id."""
    demand = TrafficDemand(source="Src", target="Dst")

    # Defaults
    assert demand.priority == 0
    assert demand.volume == 0.0
    assert demand.volume_placed == 0.0
    assert demand.mode == "combine"
    assert demand.attrs == {}

    # ID structure: "<source>|<sink>|<uuid>" and uniqueness across instances
    parts = demand.id.split("|")
    assert parts[0] == "Src"
    assert parts[1] == "Dst"
    assert len(parts) == 3
    assert all(parts)

    demand2 = TrafficDemand(source="Src", target="Dst")
    assert demand2.id != demand.id


def test_explicit_id_preserved() -> None:
    """TrafficDemand with explicit ID preserves it unchanged."""
    demand = TrafficDemand(
        id="my-explicit-id",
        source="Src",
        target="Dst",
        volume=100.0,
    )
    assert demand.id == "my-explicit-id"


def test_explicit_id_round_trip() -> None:
    """TrafficDemand ID survives serialization to dict and reconstruction."""
    original = TrafficDemand(source="A", target="B", volume=50.0)
    original_id = original.id

    # Simulate serialization (as done in workflow steps)
    config = {
        "id": original.id,
        "source": original.source,
        "target": original.target,
        "volume": original.volume,
        "mode": original.mode,
        "priority": original.priority,
    }

    # Simulate reconstruction (as done in flow.py)
    reconstructed = TrafficDemand(
        id=config.get("id"),
        source=config["source"],
        target=config["target"],
        volume=config["volume"],
        mode=config.get("mode", "pairwise"),
        priority=config.get("priority", 0),
    )

    assert reconstructed.id == original_id


def test_attrs_isolation_between_instances() -> None:
    """Each instance gets its own attrs dict; mutating one does not affect others."""
    d1 = TrafficDemand(source="A", target="B")
    d2 = TrafficDemand(source="A", target="B")

    d1.attrs["k"] = "v"
    assert d1.attrs == {"k": "v"}
    assert d2.attrs == {}


def test_custom_assignment_including_policy_config() -> None:
    """Custom field values are preserved, including mode and policy config."""
    demand = TrafficDemand(
        source="SourceNode",
        target="TargetNode",
        priority=5,
        volume=42.5,
        volume_placed=10.0,
        attrs={"description": "test"},
        mode="pairwise",
        flow_policy=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
    )

    assert demand.source == "SourceNode"
    assert demand.target == "TargetNode"
    assert demand.priority == 5
    assert demand.volume == 42.5
    assert demand.volume_placed == 10.0
    assert demand.attrs == {"description": "test"}
    assert demand.mode == "pairwise"
    assert demand.flow_policy == FlowPolicyConfig.SHORTEST_PATHS_ECMP
