"""Immutable demand inputs keep physical values and acquire stable preparation IDs."""

from dataclasses import FrozenInstanceError, replace

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    prepare,
)


def test_defaults_and_id_generation() -> None:
    demand = DemandSpec(Selector("^Src$"), Selector("^Dst$"), 0)
    assert demand.priority == 0 and demand.volume == 0.0 and demand.mode == "combine"
    assert demand.attrs == {} and demand.id is None
    network = Network()
    for name in ("Src", "Dst"):
        network.add_node(Node(name))
    scenario = Scenario(
        network,
        demand_sets={"load": DemandSet("load", (demand,))},
        units=UnitsSettings(1),
    )
    first, second = (prepare(scenario, demand_sets=("load",)) for _ in range(2))
    assert [d.id for d in first.demand_sets["load"].demands] == ["load|0|0"]
    assert first.demand_sets["load"].expansion_template[0].base_id == "load|0"
    assert (
        first.demand_sets["load"].demands[0].id
        == second.demand_sets["load"].demands[0].id
    )
    assert demand.id is None


def test_explicit_id_preserved() -> None:
    demand = DemandSpec(Selector("^Src$"), Selector("^Dst$"), 100, id="my-explicit-id")
    assert demand.id == "my-explicit-id"
    network = Network()
    for name in ("Src", "Dst"):
        network.add_node(Node(name))
    scenario = Scenario(
        network,
        demand_sets={"load": DemandSet("load", (demand,))},
        units=UnitsSettings(1),
    )
    value = prepare(scenario, demand_sets=("load",)).demand_sets["load"]
    assert value.expansion_template[0].base_id == "my-explicit-id"
    assert (
        value.demands[0].base_id == "my-explicit-id"
        and value.demands[0].id == "my-explicit-id|0"
    )


def test_attrs_isolation_between_instances() -> None:
    original = {"nested": ["original"]}
    first = DemandSpec(Selector("A"), Selector("B"), 0, attrs=original)
    second = DemandSpec(Selector("A"), Selector("B"), 0)
    original["nested"].append("changed")
    assert first.attrs == {"nested": ["original"]} and second.attrs == {}
    with pytest.raises(TypeError):
        first.attrs["extra"] = 1
    assert (
        DemandSpec(Selector("A"), Selector("B"), 0, attrs={"extra": 1}).attrs["extra"]
        == 1
    )


def test_custom_assignment_including_policy_config() -> None:
    demand = DemandSpec(
        Selector("SourceNode"),
        Selector("TargetNode"),
        42.5,
        priority=5,
        attrs={"description": "test"},
        mode="pairwise",
        policy=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
    )
    assert demand.source.path == "SourceNode" and demand.target.path == "TargetNode"
    assert demand.priority == 5 and demand.volume == 42.5 and demand.mode == "pairwise"
    assert (
        demand.attrs == {"description": "test"}
        and demand.policy == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    with pytest.raises(FrozenInstanceError):
        demand.volume = 43
    changed = replace(demand, volume=43)
    assert changed.volume == 43 and demand.volume == 42.5


def test_policy_requires_a_typed_model_or_preset() -> None:
    for value in ("SHORTEST_PATHS_ECMP", 1, {}, True):
        with pytest.raises(TypeError, match="demand.policy"):
            DemandSpec(Selector("A"), Selector("B"), 0, policy=value)
    config = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    assert DemandSpec(Selector("A"), Selector("B"), 0, policy=config).policy is config
