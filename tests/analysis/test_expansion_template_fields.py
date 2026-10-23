"""The durable physical template has every declared field and fixed leaf order."""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from fractions import Fraction

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    prepare,
)
from ngraph.model.demand import PRESETS
from tests.results.test_report_field_plants import exact


def plain(value):
    # This reader uses dataclass fields directly, independently of the exporter;
    # the native config is checked by identity instead.
    if is_dataclass(value):
        return {
            field.name: plain(getattr(value, field.name))
            for field in fields(value)
            if field.name != "config"
        }
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    if isinstance(value, Mapping):
        return {key: plain(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(child) for child in value]
    return value


def oracle():
    network = Network(nodes={name: Node(name) for name in ("s0", "s1", "t0", "t1")})
    for source in ("s0", "s1"):
        for target in ("t0", "t1"):
            network.add_link(Link(source, target, 100, 1))
    demand_set = DemandSet(
        "load",
        (
            DemandSpec(
                Selector("^s"),
                Selector("^t"),
                10,
                id="service",
                priority=3,
                mode="pairwise",
            ),
        ),
    )
    value = prepare(
        Scenario(network, demand_sets={"load": demand_set}, units=UnitsSettings(1)),
        demand_sets=("load",),
    ).demand_sets["load"]
    expected = [
        {
            "source": {
                "path": "^s",
                "group_by": None,
                "match": None,
                "active_only": None,
            },
            "target": {
                "path": "^t",
                "group_by": None,
                "match": None,
                "active_only": None,
            },
            "priority": 3,
            "policy": FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            "base_id": "service",
            "declaration_ordinal": 0,
            "expand_leaf_index": None,
            "physical_volume": 10.0,
            "mode": "pairwise",
            "group_mode": "flatten",
            "root": {
                "label": "demands.load[0](service).pairs",
                "children": [
                    {
                        "id": f"service|{i}",
                        "order": i,
                        "endpoints": {"sources": [source], "destinations": [target]},
                        "discard_reason": None,
                    }
                    for i, (source, target) in enumerate(
                        (("s0", "t0"), ("s0", "t1"), ("s1", "t0"), ("s1", "t1"))
                    )
                ],
            },
        }
    ]
    exact(plain(value.expansion_template), expected)
    preset = PRESETS[FlowPolicyPreset.SHORTEST_PATHS_ECMP]
    assert value.expansion_template[0].config is preset
    assert [row.nominal_units for row in value.demands] == [3, 3, 2, 2]
    return value.expansion_template, expected


def test_complete_expansion_template_and_canonical_leaf_order():
    oracle()


def test_template_reader_rejects_missing_null_and_near_values():
    from copy import deepcopy
    from dataclasses import is_dataclass

    import pytest

    from tests.results.test_native_field_plants import at
    from tests.results.test_report_field_plants import field_paths, near

    value, expected = oracle()
    paths = tuple(field_paths(expected))
    caught = equivalent = 0
    for path in paths:
        for mode in ("missing", "null", "wrong"):
            if mode == "null" and at(expected, path) is None:
                equivalent += 1
                continue
            # Native configs cannot be copied; the copy shares them.
            broken = deepcopy(
                value, {id(parent.config): parent.config for parent in value}
            )
            parent = broken
            for name in path[:-1]:
                parent = getattr(parent, name) if is_dataclass(parent) else parent[name]
            name = path[-1]
            assert is_dataclass(parent) and isinstance(name, str)
            original = getattr(parent, name)
            if mode == "missing":
                object.__delattr__(parent, name)
                if hasattr(parent, name) and getattr(parent, name) == original:
                    # A dataclass class default is the same public value after
                    # removal of its instance slot; that plant is equivalent.
                    equivalent += 1
                    continue
            else:
                object.__setattr__(
                    parent, name, None if mode == "null" else near(plain(original))
                )
            with pytest.raises((AssertionError, AttributeError)):
                exact(plain(broken), expected)
            caught += 1
    exact(plain(value), expected)
    assert caught + equivalent == len(paths) * 3
    print(
        f"TEMPLATE FIELD PLANTS: {len(paths)} paths; {caught} caught; {equivalent} equivalent default/null values"
    )
