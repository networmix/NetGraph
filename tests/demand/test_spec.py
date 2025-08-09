from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig


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
