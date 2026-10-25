"""The hardware inventory and its two readers, the explorer and CostPower.

Every expected value is derived by hand from the rules: a platform's totals are
its component's totals (children included) times the hardware count; a link end
counts only where its endpoint has a platform; an exclusive end rounds its count
up in the bill of materials only; the enabled view keeps enabled nodes and
active links (the link and both end nodes enabled).

Fixture F: Chassis = capex 1000 + 2 x 50 = 1100, power 100 + 2 x 5 = 110,
capacity 400, 8 ports; Optic = 10 / 2 / 100, 1 port; Optic2 = 8 / 1 / 50,
2 ports. Uses (capex/power): a 2x Chassis 2200/220, b 1100/110, c (disabled)
1100/110, e 0.5x 550/55; L1 a 10/2 + b 10/2; L2 a 10/2 + c 10/2 (inactive:
c disabled); L3 b 0.5x Optic2 4/0.5 (BOM 1, exclusive), d has no platform;
L4 (disabled) a 20/4 + e 10/2; L5 e 12/1.5 + b 12/1.5 (BOM 2, exclusive);
L6 a 20/4 + b 20/4.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from ngraph import cli
from ngraph.explorer import NetworkExplorer
from ngraph.export import write_json
from ngraph.hardware import hardware_inventory, link_active
from ngraph.model.components import (
    Component,
    ComponentsLibrary,
    resolve_link_end,
    resolve_link_end_components,
    resolve_node_hardware,
)
from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.cost_power import CostPower

COUNT_TEXT = "Hardware 'count' must be a finite positive number, got"


def _hw(name, count=None):
    spec = {"component": name}
    if count is not None:
        spec["count"] = count
    return {"hardware": spec}


def _end(name, count, **extra):
    return {"component": name, "count": count, **extra}


def _fixture():
    lib = ComponentsLibrary(
        {
            "Chassis": Component(
                "Chassis",
                capex=1000.0,
                power_watts=100.0,
                capacity=400.0,
                ports=8,
                children={
                    "LC": Component("LC", capex=50.0, power_watts=5.0, ports=8, count=2)
                },
            ),
            "Optic": Component(
                "Optic", capex=10.0, power_watts=2.0, capacity=100.0, ports=1
            ),
            "Optic2": Component(
                "Optic2", capex=8.0, power_watts=1.0, capacity=50.0, ports=2
            ),
        }
    )
    net = Network()
    net.add_node(Node("dc1/a", attrs=_hw("Chassis", 2)))
    net.add_node(Node("dc1/b", attrs=_hw("Chassis", 1)))
    net.add_node(Node("dc2/c", disabled=True, attrs=_hw("Chassis", 1)))
    net.add_node(Node("dc2/d"))
    net.add_node(Node("e", attrs=_hw("Chassis", 0.5)))
    for src, dst, cap, ends, disabled in (
        ("dc1/a", "dc1/b", 100, (_end("Optic", 1), _end("Optic", 1)), False),
        ("dc1/a", "dc2/c", 100, (_end("Optic", 1), _end("Optic", 1)), False),
        (
            "dc1/b",
            "dc2/d",
            50,
            (_end("Optic2", 0.5, exclusive=True), _end("Optic", 1)),
            False,
        ),
        ("dc1/a", "e", 100, (_end("Optic", 2), _end("Optic", 1)), True),
        (
            "e",
            "dc1/b",
            50,
            (_end("Optic2", 1.5), _end("Optic2", 1.5, exclusive=True)),
            False,
        ),
        ("dc1/a", "dc1/b", 300, (_end("Optic", 2), _end("Optic", 2)), False),
    ):
        attrs = {"hardware": {"source": ends[0], "target": ends[1]}}
        net.add_link(Link(src, dst, cap, disabled=disabled, attrs=attrs))
    return net, lib


def _cost_power(net, lib, include_disabled, level=2):
    step = CostPower(
        name="cp", include_disabled=include_disabled, aggregation_level=level
    )
    result = run(prepare(Scenario(net, (step,), components_library=lib)))
    return {
        lvl: [
            (
                r.path,
                r.platform_capex,
                r.platform_power_watts,
                r.optics_capex,
                r.optics_power_watts,
                r.capex_total,
                r.power_total_watts,
            )
            for r in rows
        ]
        for lvl, rows in result.steps[0].result.levels.items()
    }


def _explore(net, lib, strict=False):
    return NetworkExplorer.explore_network(net, lib, strict_validation=strict)


# ------------------------------------------------------------------ inventory rows


def test_inventory_rows_of_fixture_f_in_order():
    """H1, H3, H4, H6: one row per installed item, nodes first, then each link's ends."""
    net, lib = _fixture()
    uses = hardware_inventory(net, lib).uses
    got = [
        (
            u.node,
            u.link,
            u.end,
            u.component.name,
            u.count,
            u.bom_count,
            u.capex,
            u.power_watts,
            u.capacity,
            u.active,
        )
        for u in uses
    ]
    assert got == [
        ("dc1/a", None, None, "Chassis", 2.0, 2.0, 2200.0, 220.0, 800.0, True),
        ("dc1/b", None, None, "Chassis", 1.0, 1.0, 1100.0, 110.0, 400.0, True),
        ("dc2/c", None, None, "Chassis", 1.0, 1.0, 1100.0, 110.0, 400.0, False),
        ("e", None, None, "Chassis", 0.5, 0.5, 550.0, 55.0, 200.0, True),
        ("dc1/a", "dc1/a|dc1/b|0", "source", "Optic", 1.0, 1.0, 10.0, 2.0, 100.0, True),
        ("dc1/b", "dc1/a|dc1/b|0", "target", "Optic", 1.0, 1.0, 10.0, 2.0, 100.0, True),
        (
            "dc1/a",
            "dc1/a|dc2/c|0",
            "source",
            "Optic",
            1.0,
            1.0,
            10.0,
            2.0,
            100.0,
            False,
        ),
        (
            "dc2/c",
            "dc1/a|dc2/c|0",
            "target",
            "Optic",
            1.0,
            1.0,
            10.0,
            2.0,
            100.0,
            False,
        ),
        ("dc1/b", "dc1/b|dc2/d|0", "source", "Optic2", 0.5, 1.0, 4.0, 0.5, 25.0, True),
        ("dc1/a", "dc1/a|e|0", "source", "Optic", 2.0, 2.0, 20.0, 4.0, 200.0, False),
        ("e", "dc1/a|e|0", "target", "Optic", 1.0, 1.0, 10.0, 2.0, 100.0, False),
        ("e", "e|dc1/b|0", "source", "Optic2", 1.5, 1.5, 12.0, 1.5, 75.0, True),
        ("dc1/b", "e|dc1/b|0", "target", "Optic2", 1.5, 2.0, 12.0, 1.5, 75.0, True),
        ("dc1/a", "dc1/a|dc1/b|1", "source", "Optic", 2.0, 2.0, 20.0, 4.0, 200.0, True),
        ("dc1/b", "dc1/a|dc1/b|1", "target", "Optic", 2.0, 2.0, 20.0, 4.0, 200.0, True),
    ]
    assert hardware_inventory(net, lib).unknown == ()


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({}, True),
        ({"link_disabled": True}, False),
        ({"source_disabled": True}, False),
        ({"target_disabled": True}, False),
    ],
)
def test_link_active_needs_the_link_and_both_end_nodes(change, expected):
    """H6: each of the three terms alone makes a link inactive."""
    net = Network()
    net.add_node(Node("s", disabled=change.get("source_disabled", False)))
    net.add_node(Node("t", disabled=change.get("target_disabled", False)))
    net.add_link(Link("s", "t", disabled=change.get("link_disabled", False)))
    assert link_active(net, net.links["s|t|0"]) is expected


# ------------------------------------------------------------------ explorer sums


def test_explorer_bom_and_totals_on_fixture_f():
    """H2, H3, H4, H6: BOM counts (exclusive ends rounded up) and totals, both views."""
    net, lib = _fixture()
    explorer = _explore(net, lib)
    root = explorer.root_node
    assert list(root.stats.bom.items()) == [
        ("Chassis", 4.5),
        ("Optic", 11.0),
        ("Optic2", 4.5),
    ]
    assert list(root.active_stats.bom.items()) == [
        ("Chassis", 3.5),
        ("Optic", 6.0),
        ("Optic2", 4.5),
    ]
    assert explorer.get_bom() == {"Chassis": 4.5, "Optic": 11.0, "Optic2": 4.5}
    assert explorer.get_bom(include_disabled=False) == {
        "Chassis": 3.5,
        "Optic": 6.0,
        "Optic2": 4.5,
    }
    assert (root.stats.total_capex, root.stats.total_power) == (5088.0, 520.5)
    assert (root.active_stats.total_capex, root.active_stats.total_power) == (
        3938.0,
        400.5,
    )
    dc1, dc2 = root.children["dc1"], root.children["dc2"]
    assert (dc1.stats.total_capex, dc1.stats.total_power) == (3406.0, 350.0)
    assert (dc2.stats.total_capex, dc2.stats.total_power) == (1110.0, 112.0)
    assert (dc2.active_stats.total_capex, dc2.active_stats.bom) == (0.0, {})
    assert dict(dc1.children["a"].stats.bom) == {"Chassis": 2.0, "Optic": 6.0}
    assert dict(dc1.children["b"].stats.bom) == {
        "Chassis": 1.0,
        "Optic": 3.0,
        "Optic2": 3.0,
    }


def test_explorer_enabled_link_counts_use_link_active():
    """H6: the root sees L1, L3, L5, L6 active (capacity 500); all six in the all view."""
    net, lib = _fixture()
    root = _explore(net, lib).root_node
    assert (
        root.active_stats.internal_link_count,
        root.active_stats.internal_link_capacity,
    ) == (
        4,
        500.0,
    )
    assert (root.stats.internal_link_count, root.stats.internal_link_capacity) == (
        6,
        700.0,
    )
    dc2 = root.children["dc2"]
    assert dc2.active_stats.external_link_count == 1  # L3 to d; L2 to c is inactive
    assert dc2.stats.external_link_count == 2


def test_a_link_whose_source_node_is_disabled_is_inactive():
    """H6: link c->a with optics, c disabled: 20 capex in the all view, none enabled."""
    lib = ComponentsLibrary(
        {
            "Chassis": Component("Chassis"),
            "Optic": Component("Optic", capex=10.0),
        }
    )
    net = Network()
    net.add_node(Node("a", attrs=_hw("Chassis")))
    net.add_node(Node("c", disabled=True, attrs=_hw("Chassis")))
    net.add_link(
        Link(
            "c",
            "a",
            attrs={
                "hardware": {"source": _end("Optic", 1), "target": _end("Optic", 1)}
            },
        )
    )
    root = _explore(net, lib).root_node
    assert root.stats.total_capex == 20.0
    assert root.active_stats.total_capex == 0.0
    assert root.active_stats.internal_link_count == 0
    assert _cost_power(net, lib, False, 0) == {0: [("", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]}


# ------------------------------------------------------------------ CostPower levels


def test_cost_power_levels_of_fixture_f_both_views():
    """H7, H8, H10: optics at their own endpoint; level paths; no row without hardware."""
    net, lib = _fixture()
    assert _cost_power(net, lib, True) == {
        0: [("", 4950.0, 495.0, 138.0, 25.5, 5088.0, 520.5)],
        1: [
            ("dc1", 3300.0, 330.0, 106.0, 20.0, 3406.0, 350.0),
            ("dc2", 1100.0, 110.0, 10.0, 2.0, 1110.0, 112.0),
            ("e", 550.0, 55.0, 22.0, 3.5, 572.0, 58.5),
        ],
        2: [
            ("dc1/a", 2200.0, 220.0, 60.0, 12.0, 2260.0, 232.0),
            ("dc1/b", 1100.0, 110.0, 46.0, 8.0, 1146.0, 118.0),
            ("dc2/c", 1100.0, 110.0, 10.0, 2.0, 1110.0, 112.0),
            ("e", 550.0, 55.0, 22.0, 3.5, 572.0, 58.5),
        ],
    }
    assert _cost_power(net, lib, False) == {
        0: [("", 3850.0, 385.0, 88.0, 15.5, 3938.0, 400.5)],
        1: [
            ("dc1", 3300.0, 330.0, 76.0, 14.0, 3376.0, 344.0),
            ("e", 550.0, 55.0, 12.0, 1.5, 562.0, 56.5),
        ],
        2: [
            ("dc1/a", 2200.0, 220.0, 30.0, 6.0, 2230.0, 226.0),
            ("dc1/b", 1100.0, 110.0, 46.0, 8.0, 1146.0, 118.0),
            ("e", 550.0, 55.0, 12.0, 1.5, 562.0, 56.5),
        ],
    }


def test_cost_power_drops_empty_segments_the_explorer_keeps_them():
    """H9: node x//y groups as x/y in CostPower; the explorer tree is x -> '' -> y."""
    lib = ComponentsLibrary({"Chassis": Component("Chassis", capex=3.0)})
    net = Network()
    net.add_node(Node("x//y", attrs=_hw("Chassis")))
    net.add_node(Node("w", attrs=_hw("Chassis")))
    assert _cost_power(net, lib, True, 2) == {
        0: [("", 6.0, 0.0, 0.0, 0.0, 6.0, 0.0)],
        1: [("w", 3.0, 0.0, 0.0, 0.0, 3.0, 0.0), ("x", 3.0, 0.0, 0.0, 0.0, 3.0, 0.0)],
        2: [("w", 3.0, 0.0, 0.0, 0.0, 3.0, 0.0), ("x/y", 3.0, 0.0, 0.0, 0.0, 3.0, 0.0)],
    }
    root = _explore(net, lib).root_node
    assert root.children["x"].children[""].children["y"].stats.total_capex == 3.0


def test_zero_valued_hardware_makes_its_row_and_bom_entry_and_changes_nothing_else():
    """H11: a zero component adds its BOM entry and zero rows; every F amount stays."""
    net, lib = _fixture()
    before = (_cost_power(net, lib, True), _explore(net, lib).root_node.stats)
    lib.components["Zero"] = Component("Zero")
    net.add_node(Node("z/a", attrs=_hw("Zero")))
    after_rows = _cost_power(net, lib, True)
    root = _explore(net, lib).root_node
    assert (root.stats.total_capex, root.stats.total_power) == (
        before[1].total_capex,
        before[1].total_power,
    )
    # The new node's platform comes before every link end in the inventory.
    assert list(root.stats.bom.items()) == [
        ("Chassis", 4.5),
        ("Zero", 1.0),
        ("Optic", 11.0),
        ("Optic2", 4.5),
    ]
    assert after_rows[0] == before[0][0]
    assert after_rows[1] == [*before[0][1], ("z", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]
    assert after_rows[2] == [*before[0][2], ("z/a", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)]


def test_everything_inactive_gives_no_rows_and_an_empty_enabled_bom():
    """H12: no zero root row when nothing is enabled."""
    lib = ComponentsLibrary({"Chassis": Component("Chassis", capex=1.0)})
    net = Network()
    net.add_node(Node("x/a", disabled=True, attrs=_hw("Chassis")))
    assert _cost_power(net, lib, False, 1) == {0: [], 1: []}
    explorer = _explore(net, lib)
    assert explorer.get_bom(include_disabled=False) == {}
    assert explorer.root_node.active_stats.total_capex == 0.0


def test_sums_add_nodes_in_order_then_link_ends():
    """H13: float sums depend on the order; nodes come first, in node order."""
    lib = ComponentsLibrary(
        {"U": Component("U", capex=1.0), "Big": Component("Big", capex=1e16)}
    )
    net = Network()
    net.add_node(Node("q/x", attrs=_hw("U")))
    net.add_node(Node("q/y", attrs=_hw("U")))
    net.add_link(Link("q/x", "q/y", attrs={"hardware": {"source": _end("Big", 1)}}))
    # (0 + 1 + 1) + 1e16 is exact; links first would give (1e16 + 1) + 1 = 1e16.
    assert _explore(net, lib).root_node.stats.total_capex == 1.0000000000000002e16
    net = Network()
    net.add_node(Node("p/x", attrs=_hw("Big")))
    net.add_node(Node("p/y", attrs=_hw("U")))
    net.add_node(Node("p/z", attrs=_hw("U")))
    # (1e16 + 1) + 1 rounds to 1e16; the reverse order would give 1e16 + 2.
    assert _cost_power(net, lib, True, 0)[0][0][1] == 1e16


# ------------------------------------------------------------------ validation


def test_utilization_and_link_issues_of_fixture_f():
    """H5, H14, H15, H16: enabled nodes with capacity; ports at the raw count; min end limit."""
    net, lib = _fixture()
    explorer = _explore(net, lib)
    util = {u.node_name: u for u in explorer.get_node_utilization()}
    assert sorted(util) == ["dc1/a", "dc1/b", "e"]
    rows = {
        name: (
            u.component_name,
            u.hw_count,
            u.capacity_supported,
            u.attached_capacity_active,
            u.capacity_utilization,
            u.ports_available,
            u.ports_used,
            u.ports_utilization,
            u.capacity_violation,
            u.ports_violation,
        )
        for name, u in util.items()
    }
    assert rows == {
        "dc1/a": ("Chassis", 2.0, 800.0, 400.0, 0.5, 16.0, 3.0, 0.1875, False, False),
        "dc1/b": ("Chassis", 1.0, 400.0, 500.0, 1.25, 8.0, 7.0, 0.875, True, False),
        "e": ("Chassis", 0.5, 200.0, 50.0, 0.25, 4.0, 3.0, 0.75, False, False),
    }
    issues = [
        (i.source, i.target, i.capacity, i.limit, i.reason)
        for i in explorer.get_link_issues()
    ]
    assert issues == [("dc1/a", "dc1/b", 300.0, 200.0, "link_capacity_exceeds_end_hw")]


def test_link_limit_is_the_smaller_end():
    """H16: ends of capacity 100 and 200 limit a 150 link to 100."""
    lib = ComponentsLibrary(
        {
            "C": Component("C", capacity=1000.0),
            "O": Component("O", capacity=100.0),
        }
    )
    net = Network()
    net.add_node(Node("A", attrs=_hw("C")))
    net.add_node(Node("B", attrs=_hw("C")))
    net.add_link(
        Link(
            "A",
            "B",
            150,
            attrs={"hardware": {"source": _end("O", 1), "target": _end("O", 2)}},
        )
    )
    issues = _explore(net, lib).get_link_issues()
    assert [(i.capacity, i.limit) for i in issues] == [(150.0, 100.0)]
    with pytest.raises(ValueError) as exc:
        _explore(net, lib, strict=True)
    assert str(exc.value) == (
        "Link 'A->B' capacity 150 exceeds per-end hardware capacity limit 100 "
        "(min of src/dst ends)."
    )


def test_strict_mode_reports_the_first_node_violation():
    """H17: nodes before links; b's capacity 500 > 400 is the first violation."""
    net, lib = _fixture()
    with pytest.raises(ValueError) as exc:
        _explore(net, lib, strict=True)
    assert str(exc.value) == (
        "Node 'dc1/b' total attached capacity 500 exceeds hardware capacity 400 "
        "from component 'Chassis' (hw_count=1)."
    )


P_LIB = ComponentsLibrary(
    {
        "C": Component("C", capacity=100.0, ports=1),
        "O": Component("O", capacity=100.0, ports=1),
    }
)


def _two_defects(on_link):
    net = Network()
    net.add_node(Node("n1", attrs=_hw("C")))
    net.add_node(Node("n2"))
    net.add_node(Node("n3", attrs=_hw("C") if on_link else _hw("C", 0)))
    net.add_link(Link("n1", "n2", 200))
    if on_link:
        net.add_link(
            Link(
                "n3",
                "n2",
                1,
                disabled=True,
                attrs={"hardware": {"source": _end("O", -1)}},
            )
        )
    return net


@pytest.mark.parametrize(
    ("on_link", "text"),
    [
        (False, f"node n3: {COUNT_TEXT} 0"),
        (True, f"link n3|n2|0 source end: {COUNT_TEXT} -1"),
    ],
)
def test_invalid_hardware_is_refused_before_any_capacity_check(on_link, text):
    """H17b: an over-capacity n1 and a later invalid count: the count is reported, everywhere."""
    net = _two_defects(on_link)
    for strict in (True, False):
        with pytest.raises(ValueError) as exc:
            _explore(net, P_LIB, strict=strict)
        assert str(exc.value) == text
    for include_disabled in (True, False):
        with pytest.raises(ValueError) as exc:
            _cost_power(net, P_LIB, include_disabled, 0)
        assert str(exc.value) == text


def _refusals(net):
    """The error of each reader: the explorer strict and not, CostPower in both views."""
    errors = []
    for strict in (True, False):
        with pytest.raises(ValueError) as exc:
            _explore(net, P_LIB, strict=strict)
        errors.append(exc.value)
    for include_disabled in (True, False):
        with pytest.raises(ValueError) as exc:
            _cost_power(net, P_LIB, include_disabled, 0)
        errors.append(exc.value)
    return errors


def _a_to_b(a_hw=None, link_hw=None):
    net = Network()
    net.add_node(Node("a", attrs=_hw("C") if a_hw is None else {"hardware": a_hw}))
    net.add_node(Node("b", attrs=_hw("C")))
    attrs = {} if link_hw is None else {"hardware": link_hw}
    net.add_link(Link("a", "b", 1, attrs=attrs))
    return net


@pytest.mark.parametrize(
    ("a_count", "text"),
    [
        (0, f"node a: {COUNT_TEXT} 0"),
        (1, f"link a|b|0 source end: {COUNT_TEXT} -1"),
    ],
)
def test_refusals_take_nodes_first_then_each_links_source_then_target_end(
    a_count, text
):
    """A node defect and both ends of a later link invalid: the first in that order."""
    ends = {"source": _end("O", -1), "target": _end("O", -2)}
    net = _a_to_b({"component": "C", "count": a_count}, ends)
    for error in _refusals(net):
        assert str(error) == text


@pytest.mark.parametrize(
    ("a_hw", "link_hw", "text"),
    [
        ({"component": "C", "count": 0}, None, f"node a: {COUNT_TEXT} 0"),
        (None, "bad", "link a|b|0: hardware must be a mapping, got 'bad'"),
        (None, {"source": _end("O", 0)}, f"link a|b|0 source end: {COUNT_TEXT} 0"),
        (None, {"target": _end("O", 0)}, f"link a|b|0 target end: {COUNT_TEXT} 0"),
    ],
)
def test_a_refusal_keeps_the_resolver_error_as_its_cause(a_hw, link_hw, text):
    """The labelled error is raised from the resolver's, whose text has no label."""
    for error in _refusals(_a_to_b(a_hw, link_hw)):
        assert str(error) == text
        assert type(error.__cause__) is ValueError
        assert str(error.__cause__) == text.split(": ", 1)[1]


def test_a_tiny_fractional_count_is_kept_exactly_in_the_bom():
    """A count of 2**-53 adds to an empty BOM unrounded, in both views and the subtree."""
    net = Network()
    net.add_node(Node("dc/a", attrs=_hw("C", 2**-53)))
    explorer = _explore(net, P_LIB)
    assert explorer.get_bom() == explorer.get_bom(include_disabled=False)
    assert explorer.get_bom() == {"C": 2**-53}
    dc = explorer.root_node.children["dc"]
    assert dc.stats.bom == dc.active_stats.bom == {"C": 2**-53}


def test_self_loop_ends_both_use_ports():
    """H18: two optic ends at one node use two ports; attached capacity counts the link once."""
    lib = ComponentsLibrary(
        {
            "C": Component("C", capex=1.0, capacity=100.0, ports=4),
            "O": Component("O", capex=10.0, capacity=100.0, ports=1),
        }
    )
    net = Network()
    net.add_node(Node("s", attrs=_hw("C")))
    net.add_link(
        Link(
            "s",
            "s",
            10,
            attrs={"hardware": {"source": _end("O", 1), "target": _end("O", 1)}},
        )
    )
    explorer = _explore(net, lib)
    (util,) = explorer.get_node_utilization()
    assert (util.ports_used, util.attached_capacity_active) == (2.0, 10.0)
    assert explorer.root_node.stats.total_capex == 21.0
    assert explorer.get_bom() == {"C": 1.0, "O": 2.0}


def test_unknown_components_warn_in_the_explorer_only(caplog):
    """H20: the explorer warns about unknown names at nodes and both link ends
    (an end without a name, or with an empty one, does not warn); CostPower is silent."""
    lib = ComponentsLibrary({"C": Component("C")})
    net = Network()
    net.add_node(Node("n1", attrs={"hardware": {"component": "nope"}}))
    net.add_node(Node("n2", attrs={"hardware": {"count": 2}}))
    net.add_node(Node("n3", attrs=_hw("C")))
    net.add_node(Node("n4", attrs={"hardware": {}}))
    net.add_link(
        Link(
            "n3",
            "n1",
            attrs={
                "hardware": {
                    "source": {"component": "gone"},
                    "target": {"component": "gone2"},
                }
            },
        )
    )
    net.add_link(
        Link(
            "n1",
            "n3",
            attrs={"hardware": {"source": {"component": ""}, "target": {"count": 1}}},
        )
    )
    with caplog.at_level("WARNING", logger="ngraph"):
        _cost_power(net, lib, True, 0)
    assert [r for r in caplog.records if r.levelname == "WARNING"] == []
    with caplog.at_level("WARNING", logger="ngraph"):
        _explore(net, lib)
    assert [r.getMessage() for r in caplog.records if r.levelname == "WARNING"] == [
        "Node 'n1' references unknown node hardware component 'nope'.",
        "Node 'n2' references unknown node hardware component 'None'.",
        "Link 'n3->n1' unknown src hardware component 'gone'.",
        "Link 'n3->n1' unknown dst hardware component 'gone2'.",
    ]
    assert hardware_inventory(net, lib).unknown == (
        ("n1", None, "nope"),
        ("n2", None, None),
        ("n3|n1|0", "source", "gone"),
        ("n3|n1|0", "target", "gone2"),
    )


# ------------------------------------------------------------------ refusals


def _disabled_link_count(count):
    net = Network()
    net.add_node(Node("a", attrs=_hw("C")))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(
        Link(
            "a", "b", 1, disabled=True, attrs={"hardware": {"source": _end("O", count)}}
        )
    )
    return net


@pytest.mark.parametrize("count", [0, -1, True, "2"])
def test_an_invalid_count_on_an_inactive_link_is_refused_in_both_views(count):
    """H19: CostPower's enabled view refuses it too (it used to skip inactive links)."""
    text = f"link a|b|0 source end: {COUNT_TEXT} {count!r}"
    net = _disabled_link_count(count)
    for include_disabled in (True, False):
        with pytest.raises(ValueError) as exc:
            _cost_power(net, P_LIB, include_disabled, 0)
        assert str(exc.value) == text
    with pytest.raises(ValueError) as exc:
        _explore(net, P_LIB)
    assert str(exc.value) == text


def test_an_invalid_count_on_a_disabled_node_names_the_node():
    """H19: the node's refusal carries its name."""
    net = Network()
    net.add_node(Node("a", disabled=True, attrs=_hw("C", 0)))
    with pytest.raises(ValueError) as exc:
        _cost_power(net, P_LIB, False, 0)
    assert str(exc.value) == f"node a: {COUNT_TEXT} 0"


BIG = 10**309


def test_a_count_too_large_for_a_float_is_an_invalid_count():
    """H19b: 10**309 is refused with the count text, not an OverflowError."""
    with pytest.raises(ValueError) as exc:
        resolve_node_hardware(_hw("C", BIG), P_LIB)
    assert str(exc.value) == f"{COUNT_TEXT} {BIG!r}"
    with pytest.raises(ValueError, match="Hardware 'count'"):
        resolve_link_end(_end("O", BIG), P_LIB)
    node_case = Network()
    node_case.add_node(Node("a", attrs=_hw("C", BIG)))
    cases = [(node_case, f"node a: {COUNT_TEXT} {BIG!r}")]
    for disabled in (False, True):
        net = Network()
        net.add_node(Node("a", attrs=_hw("C")))
        net.add_node(Node("b"))
        net.add_link(
            Link(
                "a",
                "b",
                1,
                disabled=disabled,
                attrs={"hardware": {"source": _end("O", BIG)}},
            )
        )
        cases.append((net, f"link a|b|0 source end: {COUNT_TEXT} {BIG!r}"))
    for net, text in cases:
        for strict in (True, False):
            with pytest.raises(ValueError) as exc:
                _explore(net, P_LIB, strict=strict)
            assert str(exc.value) == text
        for include_disabled in (True, False):
            with pytest.raises(ValueError) as exc:
                _cost_power(net, P_LIB, include_disabled, 0)
            assert str(exc.value) == text


HUGE = 10**5000
HUGE_TEXT = "1" + "0" * 5000


class Count(int):
    """An int subclass the resolvers accept as a count."""


def test_a_count_past_the_int_to_str_digit_limit_keeps_the_count_text():
    """10**5000 has more digits than Python's int-to-str limit; the text still shows them,
    for an int subclass and a negative count too."""
    for call in (
        lambda: resolve_node_hardware(_hw("C", HUGE), P_LIB),
        lambda: resolve_link_end(_end("O", HUGE), P_LIB),
    ):
        with pytest.raises(ValueError) as exc:
            call()
        assert str(exc.value) == f"{COUNT_TEXT} {HUGE_TEXT}"
    assert resolve_node_hardware(_hw("C", Count(2)), P_LIB)[1] == 2.0
    for call in (
        lambda: resolve_node_hardware(_hw("C", Count(HUGE)), P_LIB),
        lambda: resolve_link_end(_end("O", Count(HUGE)), P_LIB),
    ):
        with pytest.raises(ValueError) as exc:
            call()
        assert str(exc.value) == f"{COUNT_TEXT} {HUGE_TEXT}"
    with pytest.raises(ValueError) as exc:
        resolve_link_end(_end("O", -HUGE), P_LIB)
    assert str(exc.value) == f"{COUNT_TEXT} -{HUGE_TEXT}"
    with pytest.raises(ValueError) as exc:
        hardware_inventory(_a_to_b({"component": "C", "count": -HUGE}), P_LIB)
    assert str(exc.value) == f"node a: {COUNT_TEXT} -{HUGE_TEXT}"
    cases = [
        (
            _a_to_b({"component": "C", "count": HUGE}),
            f"node a: {COUNT_TEXT} {HUGE_TEXT}",
        ),
    ]
    for end in ("source", "target"):
        cases.append(
            (
                _a_to_b(link_hw={end: _end("O", HUGE)}),
                f"link a|b|0 {end} end: {COUNT_TEXT} {HUGE_TEXT}",
            )
        )
    for net, text in cases:
        with pytest.raises(ValueError) as exc:
            hardware_inventory(net, P_LIB)
        assert str(exc.value) == text
        for error in _refusals(net):
            assert str(error) == text


def _inspect(tmp_path, yaml_text):
    path = tmp_path / "s.yaml"
    path.write_text(yaml_text)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.main(["--quiet", "inspect", str(path)])
    return [line.strip() for line in out.getvalue().splitlines() if "Hierarchy" in line]


def test_inspect_reports_invalid_hardware_and_exits_zero(tmp_path):
    """H19b, H25: inspect prints the refusal under the hierarchy and finishes."""
    big_count = (
        "network:\n  nodes:\n    a: {attrs: {hardware: {component: C, count: "
        + str(BIG)
        + "}}}\ncomponents:\n  C: {capacity: 100}\n"
    )
    lines = _inspect(tmp_path, big_count)
    assert lines == [
        f"Network Hierarchy: Unable to analyze (node a: {COUNT_TEXT} {BIG!r})"
    ]
    lines = _inspect(
        tmp_path,
        "network:\n  nodes:\n    a: {attrs: {hardware: C}}\ncomponents:\n  C: {}\n",
    )
    assert lines == [
        "Network Hierarchy: Unable to analyze (node a: hardware must be a mapping, got 'C')"
    ]


def test_capacity_overflow_reaches_the_export_refusal():
    """H22: two capex-1e308 platforms sum to inf; the JSON export refuses it."""
    lib = ComponentsLibrary({"Max": Component("Max", capex=1e308)})
    net = Network()
    net.add_node(Node("p/a", attrs=_hw("Max")))
    net.add_node(Node("p/b", attrs=_hw("Max")))
    step = CostPower(name="cp", include_disabled=True, aggregation_level=0)
    result = run(prepare(Scenario(net, (step,), components_library=lib)))
    assert result.steps[0].result.levels[0][0].platform_capex == float("inf")
    # Python 3.12 and later append the value (": inf") to this message.
    with pytest.raises(
        ValueError, match="Out of range float values are not JSON compliant"
    ):
        write_json(result, io.StringIO())
    assert _explore(net, lib).root_node.stats.total_capex == float("inf")


@pytest.mark.parametrize(
    ("node_hw", "link_hw", "key", "text"),
    [
        ("C", None, None, "node a: hardware must be a mapping, got 'C'"),
        (["C"], None, None, "node a: hardware must be a mapping, got ['C']"),
        (5, None, None, "node a: hardware must be a mapping, got 5"),
        (None, "C", None, "link a|b|0: hardware must be a mapping, got 'C'"),
        (None, "", None, "link a|b|0: hardware must be a mapping, got ''"),
        (
            None,
            {"target": ""},
            None,
            "link a|b|0 target end: hardware must be a mapping, got ''",
        ),
        (
            None,
            {"source": "O"},
            None,
            "link a|b|0 source end: hardware must be a mapping, got 'O'",
        ),
        (
            None,
            {"target": "O"},
            None,
            "link a|b|0 target end: hardware must be a mapping, got 'O'",
        ),
        (
            None,
            {"source": "O"},
            "L9",
            "link L9 source end: hardware must be a mapping, got 'O'",
        ),
    ],
)
def test_a_hardware_value_that_is_not_a_mapping_is_refused(node_hw, link_hw, key, text):
    """H25: node, link and each end; the label names where the value is."""
    net = Network()
    net.add_node(
        Node("a", attrs=_hw("C") if node_hw is None else {"hardware": node_hw})
    )
    net.add_node(Node("b", attrs=_hw("C")))
    link = Link("a", "b", 1, attrs={} if link_hw is None else {"hardware": link_hw})
    if key is None:
        net.add_link(link)
    else:
        net.links[key] = link
    for strict in (True, False):
        with pytest.raises(ValueError) as exc:
            _explore(net, P_LIB, strict=strict)
        assert str(exc.value) == text
    if key is not None:
        return  # preparation refuses a link stored under a key other than its id
    for include_disabled in (True, False):
        with pytest.raises(ValueError) as exc:
            _cost_power(net, P_LIB, include_disabled, 0)
        assert str(exc.value) == text


def test_the_resolvers_refuse_non_mappings_and_take_null_as_absent():
    """H25: the public resolvers share the shape rule."""
    for call, value in (
        (lambda: resolve_node_hardware({"hardware": "C"}, P_LIB), "'C'"),
        (lambda: resolve_link_end("O", P_LIB), "'O'"),
        (lambda: resolve_link_end_components({"hardware": "C"}, P_LIB), "'C'"),
        (
            lambda: resolve_link_end_components({"hardware": {"target": "O"}}, P_LIB),
            "'O'",
        ),
    ):
        with pytest.raises(ValueError) as exc:
            call()
        assert str(exc.value) == f"hardware must be a mapping, got {value}"
    assert resolve_node_hardware({"hardware": None}, P_LIB) == (None, 1.0)
    assert resolve_link_end_components(
        {"hardware": {"source": None, "target": {"component": "O", "count": 2}}}, P_LIB
    ) == ((None, 1.0, False), (P_LIB.components["O"], 2.0, False))
    assert resolve_link_end({"component": "O", "exclusive": True}, P_LIB) == (
        P_LIB.components["O"],
        1.0,
        True,
    )
    assert resolve_link_end({"count": 3}, P_LIB) == (None, 3.0, False)


# ------------------------------------------------------------------ ports


def _port_case(count):
    net = Network()
    net.add_node(Node("a", attrs=_hw("C")))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(Link("a", "b", 1, attrs={"hardware": {"source": _end("O", count)}}))
    return net


def _util(explorer, name):
    (row,) = [u for u in explorer.get_node_utilization() if u.node_name == name]
    return (
        row.node_name,
        row.component_name,
        row.hw_count,
        row.capacity_supported,
        row.attached_capacity_active,
        row.capacity_utilization,
        row.ports_available,
        row.ports_used,
        row.ports_utilization,
        row.capacity_violation,
        row.ports_violation,
    )


def test_a_positive_port_overflow_is_a_violation():
    """H26: 2 ports used of 1 on a capacity-safe node."""
    explorer = _explore(_port_case(2), P_LIB)
    assert _util(explorer, "a") == (
        "a",
        "C",
        1.0,
        100.0,
        1.0,
        0.01,
        1.0,
        2.0,
        2.0,
        False,
        True,
    )
    assert _util(explorer, "b") == (
        "b",
        "C",
        1.0,
        100.0,
        1.0,
        0.01,
        1.0,
        0.0,
        0.0,
        False,
        False,
    )
    with pytest.raises(ValueError) as exc:
        _explore(_port_case(2), P_LIB, strict=True)
    assert str(exc.value) == (
        "Node 'a' requires 2 ports for link optics but only 1 ports are available on 'C' (count=1)."
    )


def test_the_port_margin_is_1e_minus_9():
    """H26: 1 + 5e-10 ports fit one port; 1 + 2e-9 do not."""
    within = _explore(_port_case(1.0000000005), P_LIB, strict=True)
    assert _util(within, "a")[-1] is False
    explorer = _explore(_port_case(1.000000002), P_LIB)
    assert _util(explorer, "a")[-1] is True
    with pytest.raises(ValueError) as exc:
        _explore(_port_case(1.000000002), P_LIB, strict=True)
    assert str(exc.value) == (
        "Node 'a' requires 1 ports for link optics but only 1 ports are available on 'C' (count=1)."
    )


def test_a_one_port_self_loop_with_two_optics_is_refused_in_strict_mode():
    """H26, D4: two optic ends at a one-port node."""
    net = Network()
    net.add_node(Node("s", attrs=_hw("C")))
    net.add_link(
        Link(
            "s",
            "s",
            10,
            attrs={"hardware": {"source": _end("O", 1), "target": _end("O", 1)}},
        )
    )
    assert _util(_explore(net, P_LIB), "s")[-4:] == (2.0, 2.0, False, True)
    with pytest.raises(ValueError) as exc:
        _explore(net, P_LIB, strict=True)
    assert str(exc.value) == (
        "Node 's' requires 2 ports for link optics but only 1 ports are available on 'C' (count=1)."
    )


def test_capacity_is_reported_before_ports_at_one_node():
    """H26: a node over both limits reports its capacity first."""
    net = Network()
    net.add_node(Node("a", attrs=_hw("C")))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(Link("a", "b", 150, attrs={"hardware": {"source": _end("O", 2)}}))
    assert _util(_explore(net, P_LIB), "a")[-2:] == (True, True)
    with pytest.raises(ValueError) as exc:
        _explore(net, P_LIB, strict=True)
    assert str(exc.value) == (
        "Node 'a' total attached capacity 150 exceeds hardware capacity 100 "
        "from component 'C' (hw_count=1)."
    )


def test_the_shipped_scenario_with_components_reads_one_inventory():
    """H24 (named gate in the stage script); here: backbone's CostPower and explorer agree."""
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "scenarios/backbone_clos.yml"
    ).read_text()
    scenario = Scenario.from_yaml(text)
    inventory = hardware_inventory(scenario.network, scenario.components_library)
    explorer = _explore(scenario.network, scenario.components_library)
    rows = _cost_power(scenario.network, scenario.components_library, True, 0)
    assert len(inventory.uses) == 1540
    assert rows[0][0][5] == pytest.approx(explorer.root_node.stats.total_capex)
    assert rows[0][0][5] == pytest.approx(sum(u.capex for u in inventory.uses))


def test_an_empty_component_name_is_none_on_a_node_and_looked_up_on_a_link_end():
    """H21 (D13, unchanged): a node needs a nonempty name; a link end looks any name up."""
    lib = ComponentsLibrary(
        {"": Component("", capex=5.0), "C": Component("C", capex=1.0)}
    )
    net = Network()
    net.add_node(Node("a", attrs={"hardware": {"component": ""}}))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(Link("b", "b", attrs={"hardware": {"source": {"component": ""}}}))
    uses = hardware_inventory(net, lib).uses
    assert [(u.node, u.component.name, u.capex) for u in uses] == [
        ("b", "C", 1.0),
        ("b", "", 5.0),
    ]


def test_a_zero_capacity_end_forms_no_limit():
    """H16: the limit needs both ends' capacity positive."""
    lib = ComponentsLibrary(
        {
            "C": Component("C", capacity=1000.0),
            "O": Component("O", capacity=100.0),
            "Z": Component("Z"),
        }
    )
    net = Network()
    net.add_node(Node("A", attrs=_hw("C")))
    net.add_node(Node("B", attrs=_hw("C")))
    net.add_link(
        Link(
            "A",
            "B",
            150,
            attrs={"hardware": {"source": _end("O", 1), "target": _end("Z", 1)}},
        )
    )
    assert _explore(net, lib, strict=True).get_link_issues() == []


def test_attached_capacity_equal_to_the_platform_is_no_violation():
    """H15: the check is strictly greater."""
    net = Network()
    net.add_node(Node("a", attrs=_hw("C")))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(Link("a", "b", 100))
    explorer = _explore(net, P_LIB, strict=True)
    assert _util(explorer, "a")[3:6] == (100.0, 100.0, 1.0)
    assert _util(explorer, "a")[-2] is False


def test_a_platform_without_ports_has_no_port_check():
    """H26: ports are checked only when the platform declares some."""
    lib = ComponentsLibrary(
        {
            "C": Component("C", capacity=100.0),
            "O": Component("O", capacity=100.0, ports=1),
        }
    )
    net = Network()
    net.add_node(Node("a", attrs=_hw("C")))
    net.add_node(Node("b", attrs=_hw("C")))
    net.add_link(Link("a", "b", 1, attrs={"hardware": {"source": _end("O", 3)}}))
    explorer = _explore(net, lib, strict=True)
    assert _util(explorer, "a")[6:] == (0.0, 3.0, 0.0, False, False)


@pytest.mark.parametrize("inactive", ["link", "target node"])
def test_an_inactive_link_over_its_optics_has_no_issue(inactive):
    """H16: only active links are checked against their ends' limit."""
    lib = ComponentsLibrary(
        {"C": Component("C", capacity=1000.0), "O": Component("O", capacity=100.0)}
    )
    net = Network()
    net.add_node(Node("A", attrs=_hw("C")))
    net.add_node(Node("B", disabled=inactive == "target node", attrs=_hw("C")))
    ends = {"source": _end("O", 1), "target": _end("O", 1)}
    net.add_link(
        Link("A", "B", 300, disabled=inactive == "link", attrs={"hardware": ends})
    )
    assert _explore(net, lib, strict=True).get_link_issues() == []
    net.add_link(Link("A", "A", 300, attrs={"hardware": ends}))
    assert [
        (i.source, i.capacity, i.limit) for i in _explore(net, lib).get_link_issues()
    ] == [("A", 300.0, 100.0)]
