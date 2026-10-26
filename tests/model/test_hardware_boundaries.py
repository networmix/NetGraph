"""Hardware flags and arithmetic stay valid before results reach JSON."""

import math
from dataclasses import asdict
from io import StringIO

import numpy as np
import pytest

from ngraph import (
    Component,
    ComponentsLibrary,
    Link,
    Network,
    NetworkExplorer,
    Node,
    Scenario,
    prepare,
    run,
    write_json,
)
from ngraph.hardware import hardware_inventory
from ngraph.model.components import totals_with_multiplier
from ngraph.workflow import CostPower

FIELDS = [
    ("capex", "total_capex"),
    ("power_watts", "total_power"),
    ("power_watts_max", "total_power_max"),
    ("capacity", "total_capacity"),
]


def hardware_nodes(component, count=1, disabled=False, second=False):
    library = ComponentsLibrary(
        {"p": component, "o": Component("o", capacity=100, ports=1)}
    )
    names = ("a", "b") if second else ("a",)
    n = Network(
        nodes={
            s: Node(
                s,
                disabled=disabled,
                attrs={"hardware": {"component": "p", "count": count}},
            )
            for s in names
        }
    )
    return n, library


@pytest.mark.parametrize("raw", ["false", 0, 1, [], {}, None])
@pytest.mark.parametrize("disabled", [False, True])
@pytest.mark.parametrize("yaml_input", [False, True])
def test_exclusive_uses_the_boolean_rule_with_the_link_end_label(
    raw, disabled, yaml_input
):
    import yaml

    n, library = hardware_nodes(Component("p", capacity=100, ports=2), second=True)
    n.add_link(
        Link(
            "a",
            "b",
            10,
            disabled=disabled,
            attrs={
                "hardware": {
                    "source": {"component": "o", "count": 0.5, "exclusive": raw}
                }
            },
        )
    )
    scenario = Scenario(n, [CostPower()], components_library=library)
    if yaml_input:
        scenario = Scenario.from_yaml(
            yaml.safe_dump(
                {
                    "network": {
                        "nodes": {
                            "a": {"attrs": {"hardware": {"component": "p"}}},
                            "b": {},
                        },
                        "links": [
                            {
                                "source": "a",
                                "target": "b",
                                "capacity": 10,
                                "disabled": disabled,
                                "attrs": {
                                    "hardware": {
                                        "source": {
                                            "component": "o",
                                            "count": 0.5,
                                            "exclusive": raw,
                                        }
                                    }
                                },
                            }
                        ],
                    },
                    "components": {"p": {"capacity": 100}, "o": {"capacity": 100}},
                    "workflow": [{"type": "CostPower"}],
                }
            )
        )
    with pytest.raises(ValueError, match=r"link a\|b\|0 source end: .*exclusive"):
        run(prepare(scenario))


@pytest.mark.parametrize(
    "raw,expected",
    [(False, 0.5), (True, 1), (np.bool_(False), 0.5), (np.bool_(True), 1)],
)
def test_boolean_exclusive_preserves_fractional_and_rounded_counts(raw, expected):
    n, lib = hardware_nodes(Component("p", capacity=100, ports=2), second=True)
    # Metadata JSON requires actual bool; direct resolver also accepts NumPy bool.
    from ngraph.model.components import resolve_link_end

    assert resolve_link_end(
        {"component": "o", "exclusive": raw, "count": 0.5}, lib
    ) == (lib.get("o"), 0.5, bool(raw))
    n.add_link(
        Link(
            "a",
            "b",
            10,
            attrs={
                "hardware": {
                    "source": {"component": "o", "exclusive": bool(raw), "count": 0.5}
                }
            },
        )
    )
    use = hardware_inventory(n, lib).uses[-1]
    assert use.count == 0.5 and use.bom_count == expected
    assert use.node == "a" and use.link == "a|b|0" and use.end == "source"


@pytest.mark.parametrize("field,method", FIELDS)
@pytest.mark.parametrize(
    "shape", ["internal_count", "child_sum", "parent_count", "external_count"]
)
def test_component_arithmetic_refuses_overflow_and_accepts_a_finite_control(
    field, method, shape
):
    for magnitude, overflow in ((1e308, True), (1e307, False)):
        child = Component("child", **{field: magnitude})
        if shape == "child_sum":
            component = Component("p", **{field: magnitude}, children={"child": child})
        elif shape == "parent_count":
            component = Component("p", count=2, children={"child": child})
        else:
            component = Component(
                "p", count=2 if shape == "internal_count" else 1, **{field: magnitude}
            )
        call = (
            (lambda component=component: totals_with_multiplier(component, 2))
            if shape == "external_count" and field != "power_watts_max"
            else (lambda component=component: getattr(component, method)())
        )
        # Peak power has no external multiplier in the public three-metric helper.
        if shape == "external_count" and field == "power_watts_max":
            assert totals_with_multiplier(component, 2) == (0.0, 0.0, 0.0)
            assert component.total_power_max() == magnitude
            continue
        if overflow:
            with pytest.raises(ValueError, match=f"component p.{field}"):
                call()
        else:
            answer = call()
            if isinstance(answer, tuple):
                assert answer == tuple(
                    2 * magnitude if f == field else 0
                    for f in ("capex", "power_watts", "capacity")
                )
            else:
                assert answer == 2 * magnitude


@pytest.mark.parametrize("field", ["capex", "power_watts", "capacity"])
@pytest.mark.parametrize("end", [False, True])
@pytest.mark.parametrize("disabled", [False, True])
def test_inventory_overflow_names_its_node_or_link_end(field, end, disabled):
    n, lib = hardware_nodes(Component("p", capacity=100), second=True)
    lib.components["o"] = Component("o", **{field: 1e308})
    if end:
        n.add_link(
            Link(
                "a",
                "b",
                1,
                disabled=disabled,
                attrs={"hardware": {"target": {"component": "o", "count": 2}}},
            )
        )
        label = r"link a\|b\|0 target end"
    else:
        n.replace_node(
            "a", disabled=disabled, attrs={"hardware": {"component": "o", "count": 2}}
        )
        label = "node a"
    with pytest.raises(ValueError, match=label + ".*" + field):
        hardware_inventory(n, lib)


@pytest.mark.parametrize("field", ["capex", "power_watts"])
@pytest.mark.parametrize("mix", [False, True])
def test_aggregates_of_finite_uses_are_checked_before_publication(field, mix):
    for magnitude, overflow in ((1e308, True), (1e307, False)):
        n, lib = hardware_nodes(Component("p", **{field: magnitude}), second=not mix)
        if mix:
            n.add_node(Node("b"))
            lib.components["o"] = Component("o", **{field: magnitude})
            n.add_link(
                Link("a", "b", 1, attrs={"hardware": {"source": {"component": "o"}}})
            )
        scenario = Scenario(n, [CostPower()], components_library=lib)
        if overflow:
            with pytest.raises(
                ValueError,
                match=(
                    f"hardware path <root>.{'capex_total' if field == 'capex' else 'power_total_watts'}"
                    if mix
                    else f"hardware path <root> node b.{field}"
                ),
            ):
                run(prepare(scenario))
            with pytest.raises(ValueError, match=r"(node|link) .*total_(capex|power)"):
                NetworkExplorer.explore_network(n, lib, strict_validation=False)
        else:
            result = run(prepare(scenario))
            row = result.steps[0].result.levels[0][0]
            assert asdict(row) == {
                "path": "",
                "platform_capex": magnitude * (1 if mix else 2)
                if field == "capex"
                else 0,
                "platform_power_watts": magnitude * (1 if mix else 2)
                if field == "power_watts"
                else 0,
                "optics_capex": magnitude if field == "capex" and mix else 0,
                "optics_power_watts": magnitude
                if field == "power_watts" and mix
                else 0,
                "capex_total": 2 * magnitude if field == "capex" else 0,
                "power_total_watts": 2 * magnitude if field == "power_watts" else 0,
            }
            out = StringIO()
            write_json(result, out)
            assert "Infinity" not in out.getvalue()
            explorer = NetworkExplorer.explore_network(n, lib, strict_validation=False)
            assert explorer.root_node.stats.total_capex == row.capex_total
            assert explorer.root_node.stats.total_power == row.power_total_watts


def test_zero_metrics_with_huge_finite_counts_stay_zero():
    c = Component("p", count=10**308)
    assert (
        c.total_capex(),
        c.total_power(),
        c.total_power_max(),
        c.total_capacity(),
    ) == (0, 0, 0, 0)
    assert totals_with_multiplier(c, 1e308) == (0, 0, 0)
    n, lib = hardware_nodes(c, count=1e308)
    assert all(math.isfinite(use.bom_count) for use in hardware_inventory(n, lib).uses)
    result = run(prepare(Scenario(n, [CostPower()], components_library=lib)))
    write_json(result, StringIO())


@pytest.mark.parametrize(
    "case,field",
    [
        ("ports_available", "ports_available"),
        ("ports_used", "ports_used"),
        ("ports_used_sum", "ports_used"),
        ("port_ratio", "ports_utilization"),
        ("capacity_ratio", "capacity_utilization"),
        ("bom_sum", "bom.p"),
        ("attached_sum", "internal_link_capacity"),
    ],
)
def test_explorer_refuses_nonfinite_hardware_counts_and_utilization(case, field):
    n, lib = hardware_nodes(Component("p", capacity=1, ports=1), second=True)
    if case == "ports_available":
        lib.components["p"] = Component("p", capacity=1, ports=10**309)
    elif case == "ports_used_sum":
        lib.components["p"] = Component("p", capacity=1, ports=0)
        lib.components["o"] = Component("o", ports=2)
        for _ in range(2):
            n.add_link(
                Link(
                    "a",
                    "b",
                    0,
                    attrs={"hardware": {"source": {"component": "o", "count": 6e307}}},
                )
            )
    elif case in ("ports_used", "port_ratio"):
        lib.components["o"] = Component(
            "o", ports=10**309 if case == "ports_used" else 1
        )
        if case == "port_ratio":
            n.replace_node("a", attrs={"hardware": {"component": "p", "count": 1e-308}})
        n.add_link(
            Link(
                "a",
                "b",
                0,
                attrs={
                    "hardware": {
                        "source": {
                            "component": "o",
                            "count": 1 if case == "ports_used" else 1e308,
                        }
                    }
                },
            )
        )
    elif case == "capacity_ratio":
        lib.components["p"] = Component("p", capacity=1e-308)
        n.add_link(Link("a", "b", 1e308))
    elif case == "bom_sum":
        lib.components["p"] = Component("p")
        for s in ("a", "b"):
            n.replace_node(s, attrs={"hardware": {"component": "p", "count": 1e308}})
    else:
        n.add_link(Link("a", "b", 1e308))
        n.add_link(Link("a", "b", 1e308))
    with pytest.raises(ValueError, match=field):
        NetworkExplorer.explore_network(n, lib, strict_validation=False)
