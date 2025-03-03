import pytest
from ngraph.traffic_demand import TrafficDemand


def test_traffic_demand_defaults():
    """
    Test creation of TrafficDemand with default values.
    """
    demand = TrafficDemand(source_path="NodeA", sink_path="NodeB")
    assert demand.source_path == "NodeA"
    assert demand.sink_path == "NodeB"
    assert demand.priority == 0
    assert demand.demand == 0.0
    assert demand.demand_placed == 0.0
    assert demand.attrs == {}


def test_traffic_demand_custom_values():
    """
    Test creation of TrafficDemand with custom values.
    """
    demand = TrafficDemand(
        source_path="SourceNode",
        sink_path="TargetNode",
        priority=5,
        demand=42.5,
        demand_placed=10.0,
        attrs={"description": "test"},
    )
    assert demand.source_path == "SourceNode"
    assert demand.sink_path == "TargetNode"
    assert demand.priority == 5
    assert demand.demand == 42.5
    assert demand.demand_placed == 10.0
    assert demand.attrs == {"description": "test"}


def test_traffic_demand_attrs_modification():
    """
    Test that the attrs dictionary can be modified after instantiation.
    """
    demand = TrafficDemand(source_path="NodeA", sink_path="NodeB")
    demand.attrs["key"] = "value"
    assert demand.attrs == {"key": "value"}


def test_traffic_demand_partial_kwargs():
    """
    Test initialization with only a subset of fields, ensuring defaults work.
    """
    demand = TrafficDemand(source_path="NodeA", sink_path="NodeC", demand=15.0)
    assert demand.source_path == "NodeA"
    assert demand.sink_path == "NodeC"
    assert demand.demand == 15.0
    # Check the defaults
    assert demand.priority == 0
    assert demand.demand_placed == 0.0
    assert demand.attrs == {}
