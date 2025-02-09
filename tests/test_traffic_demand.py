import pytest
from ngraph.traffic_demand import TrafficDemand


def test_traffic_demand_defaults():
    """
    Test creation of TrafficDemand with default values.
    """
    demand = TrafficDemand(source="NodeA", target="NodeB")
    assert demand.source == "NodeA"
    assert demand.target == "NodeB"
    assert demand.priority == 0
    assert demand.demand == 0.0
    assert demand.demand_placed == 0.0
    assert demand.demand_unplaced == 0.0
    assert demand.attrs == {}


def test_traffic_demand_custom_values():
    """
    Test creation of TrafficDemand with custom values.
    """
    demand = TrafficDemand(
        source="SourceNode",
        target="TargetNode",
        priority=5,
        demand=42.5,
        demand_placed=10.0,
        demand_unplaced=32.5,
        attrs={"description": "test"},
    )
    assert demand.source == "SourceNode"
    assert demand.target == "TargetNode"
    assert demand.priority == 5
    assert demand.demand == 42.5
    assert demand.demand_placed == 10.0
    assert demand.demand_unplaced == 32.5
    assert demand.attrs == {"description": "test"}


def test_traffic_demand_attrs_modification():
    """
    Test that the attrs dictionary can be modified after instantiation.
    """
    demand = TrafficDemand(source="NodeA", target="NodeB")
    demand.attrs["key"] = "value"
    assert demand.attrs == {"key": "value"}


def test_traffic_demand_partial_kwargs():
    """
    Test initialization with only a subset of fields, ensuring defaults work.
    """
    demand = TrafficDemand(source="NodeA", target="NodeC", demand=15.0)
    assert demand.source == "NodeA"
    assert demand.target == "NodeC"
    assert demand.demand == 15.0
    # Check the defaults
    assert demand.priority == 0
    assert demand.demand_placed == 0.0
    assert demand.demand_unplaced == 0.0
    assert demand.attrs == {}
