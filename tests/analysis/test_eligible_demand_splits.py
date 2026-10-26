"""Hand-owned eligible trees check integer, physical and identity propagation."""

from copy import deepcopy
from dataclasses import dataclass, replace
from fractions import Fraction

import pytest
import yaml

from ngraph import Scenario, UnitsSettings, prepare
from ngraph.analysis.demands import leaf_amounts, resolve_demands, scaled_expansion


@dataclass(frozen=True)
class Leaf:
    sources: tuple = ()
    targets: tuple = ()
    reason: str | None = None


def pair(s, t):
    return Leaf((s,), (t,))


EMPTY = Leaf(reason="empty_selection")
SELF = Leaf(reason="self_pair")
FILTERED = Leaf(reason="filtered")
NODES = {
    "A": {"attrs": {"g": "x", "sg": "x", "tg": "y"}},
    "B": {"attrs": {"g": "y", "sg": "y", "tg": "z"}},
    "C": {"attrs": {"g": "y", "sg": "z", "tg": "z"}},
    "D": {"attrs": {"g": "z", "sg": "w", "tg": "w"}},
}


def case(
    source,
    target,
    tree,
    *,
    mode="pairwise",
    gm="flatten",
    volume=11,
    nodes=NODES,
    **extra,
):
    return (
        {
            "network": {
                "nodes": deepcopy(nodes),
                "links": [
                    {"source": s, "target": t, "capacity": 100, "cost": i + 1}
                    for i, (s, t) in enumerate(
                        zip(nodes, list(nodes)[1:], strict=False)
                    )
                ],
            },
            "demands": {
                "d": [
                    dict(
                        source=source,
                        target=target,
                        mode=mode,
                        group_mode=gm,
                        volume=volume,
                        **extra,
                    )
                ]
            },
        },
        tree,
    )


CASES = {}
for mode in ("combine", "pairwise"):
    for gm in ("flatten", "per_group", "group_pairwise"):
        reason = FILTERED if gm == "group_pairwise" else SELF
        CASES[f"{mode}_{gm}_self"] = case("^(A)$", "^(A)$", [reason], mode=mode, gm=gm)
        CASES[f"{mode}_{gm}_distinct"] = case(
            "^(A)$",
            "^(B)$",
            [EMPTY if gm == "per_group" and mode == "pairwise" else pair("A", "B")],
            mode=mode,
            gm=gm,
        )
CASES.update(
    {
        "matrix4": case(
            "^([ABCD])$",
            "^([ABCD])$",
            [[pair(s, t) for s in "ABCD" for t in "ABCD" if s != t]],
            volume=120,
        ),
        "odd_matrix2": case(
            "^([AB])$", "^([AB])$", [[pair("A", "B"), pair("B", "A")]], volume=5
        ),
        "per_group_mixed": case(
            {"path": "^[AB]$", "group_by": "g"},
            {"path": "^[AC]$", "group_by": "g"},
            [[[pair("B", "C")]]],
            gm="per_group",
        ),
        "per_group_combine_mixed": case(
            {"path": "^[AB]$", "group_by": "g"},
            "^A$",
            [[pair("B", "A")]],
            mode="combine",
            gm="per_group",
        ),
        "same_label_distinct_nodes": case(
            {"path": "^B$", "group_by": "g"},
            {"path": "^C$", "group_by": "g"},
            [FILTERED],
            gm="group_pairwise",
        ),
        "distinct_label_self_and_live": case(
            {"path": "^A$", "group_by": "sg"},
            {"path": "^[AB]$", "group_by": "tg"},
            [[[pair("A", "B")]]],
            gm="group_pairwise",
        ),
        "group_pairs_odd": case(
            "^([AB])$",
            "^([AB])$",
            [[[pair("A", "B")], [pair("B", "A")]]],
            gm="group_pairwise",
            volume=5,
        ),
        "group_pairwise_combine_odd": case(
            "^([AB])$",
            "^([AB])$",
            [[pair("A", "B"), pair("B", "A")]],
            mode="combine",
            gm="group_pairwise",
            volume=5,
        ),
        "empty_all": case("^missing$", "^B$", [EMPTY]),
        "expand_empty": case(
            "^${s}$",
            "^C$",
            [[pair("A", "C")], EMPTY],
            expand={"vars": {"s": ["A", "missing"]}},
        ),
        "expand_zip_self": case(
            "^${s}$",
            "^${t}$",
            [SELF, [pair("B", "C")]],
            expand={"mode": "zip", "vars": {"s": ["A", "B"], "t": ["A", "C"]}},
        ),
        "zero_matrix": case(
            "^([AB])$", "^([AB])$", [[pair("A", "B"), pair("B", "A")]], volume=0
        ),
        "subquantum": case(
            "^([AB])$", "^([AB])$", [[pair("A", "B"), pair("B", "A")]], volume=0.25
        ),
        "nested_odd": case(
            {"path": "^[AB]$", "group_by": "sg"},
            {"path": "^[CD]$", "group_by": "tg"},
            [[[pair("A", "D")], [pair("A", "C")], [pair("B", "D")], [pair("B", "C")]]],
            gm="group_pairwise",
        ),
        "no_shared_labels": case("^(A)$", "^(B)$", [EMPTY], gm="per_group"),
        "disconnected": case("^A$", "^D$", [[pair("A", "D")]]),
        "zero_capacity": case("^A$", "^B$", [[pair("A", "B")]]),
        "disabled_group": case("^([AB])$", "^C$", [[pair("A", "C")]]),
    }
)
CASES["combine_per_group_empty_targets"] = case(
    "^([AB])$", "^missing$", [[EMPTY, EMPTY]], mode="combine", gm="per_group"
)
CASES["disconnected"][0]["network"]["links"] = []
CASES["zero_capacity"][0]["network"]["links"][0]["capacity"] = 0
CASES["disabled_group"][0]["network"]["nodes"]["B"]["disabled"] = True
for mode in ("combine", "pairwise"):
    for name, names, source, target, branches, volume in (
        (
            "multigroup",
            ("A1", "A2", "B1", "B2"),
            "^([AB])",
            "^([AB])",
            [(("A1", "A2"), ("B1", "B2")), (("B1", "B2"), ("A1", "A2"))],
            11,
        ),
        (
            "unequal",
            ("x1", "x2", "y1", "z1", "z2", "z3"),
            "^([xy])",
            "^([yz])",
            [
                (("x1", "x2"), ("y1",)),
                (("x1", "x2"), ("z1", "z2", "z3")),
                (("y1",), ("z1", "z2", "z3")),
            ],
            13,
        ),
    ):
        tree = [
            Leaf(s, t) if mode == "combine" else [pair(a, b) for a in s for b in t]
            for s, t in branches
        ]
        CASES[f"{mode}_{name}"] = case(
            source,
            target,
            [tree],
            mode=mode,
            gm="group_pairwise",
            volume=volume,
            nodes={n: {} for n in names},
        )


def oracle(tree, total, physical):
    """Only fixture-owned trees and Python arithmetic; no production helpers."""
    if isinstance(tree, Leaf):
        return [(tree, total, physical)]
    quotient, remainder = divmod(total, len(tree))
    return [
        row
        for i, child in enumerate(tree)
        for row in oracle(child, quotient + (i < remainder), physical / len(tree))
    ]


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize(
    "q,alpha,reverse", [(1, 1, False), (1, 4, True), (0.125, 2, True)]
)
def test_eligible_tree_exact_fields(name, q, alpha, reverse):
    document, trees = deepcopy(CASES[name])
    if reverse:
        document["network"]["nodes"] = dict(
            reversed(list(document["network"]["nodes"].items()))
        )
        document["network"]["links"].reverse()
    scenario = replace(
        Scenario.from_yaml(yaml.safe_dump(document, sort_keys=False)),
        units=UnitsSettings(q),
    )
    result = prepare(scenario, demand_sets=("d",))
    ds = result.demand_sets["d"]
    assert resolve_demands(result, scenario.demand_sets["d"]) == ds
    amounts, accounting = scaled_expansion(ds, alpha, q)
    volume = document["demands"]["d"][0]["volume"]
    exact = Fraction(float(volume)) * Fraction(alpha) / Fraction(q)
    total = (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)
    expected_rows, expected_accounts, nominal = [], [], {}
    for i, tree in enumerate(trees):
        base = f"d|0|{i}" if len(trees) > 1 else "d|0"
        expected = oracle(tree, total, Fraction(float(volume)))
        nominal_exact = Fraction(float(volume)) / Fraction(q)
        nominal_total = (2 * nominal_exact.numerator + nominal_exact.denominator) // (
            2 * nominal_exact.denominator
        )
        nominal.update(
            {
                f"{base}|{j}": units
                for j, (leaf, units, _) in enumerate(
                    oracle(tree, nominal_total, Fraction(float(volume)))
                )
                if leaf.reason is None
            }
        )
        physical = leaf_amounts(ds.expansion_template[i].root, volume)
        assert physical == {f"{base}|{j}": row[2] for j, row in enumerate(expected)}
        discards = []
        for j, (leaf, units, _) in enumerate(expected):
            identity = f"{base}|{j}"
            if leaf.reason:
                discards.append((identity, units, leaf.reason))
            else:
                expected_rows.append(
                    (identity, base, leaf.sources, leaf.targets, units)
                )
        expected_accounts.append(
            (
                base,
                total,
                total - sum(x[1] for x in discards),
                sum(x[1] for x in discards),
                discards,
            )
        )
        parent = ds.expansion_template[i]
        assert (
            parent.base_id,
            parent.declaration_ordinal,
            parent.expand_leaf_index,
            parent.physical_volume,
        ) == (base, 0, i if len(trees) > 1 else None, volume)
    assert [
        (d.id, d.base_id, d.endpoints.sources, d.endpoints.destinations, amounts[d.id])
        for d in ds.demands
    ] == expected_rows
    assert dict(amounts) == {row[0]: row[4] for row in expected_rows}
    assert {d.id: d.nominal_units for d in ds.demands} == nominal
    assert all(type(v) is int for v in amounts.values())
    assert [
        (
            a.base_id,
            a.declared_units,
            a.resolved_units,
            a.discarded_units,
            [(d.label, d.units, d.reason) for d in a.discards],
        )
        for a in accounting
    ] == expected_accounts


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("gm", ["flatten", "per_group", "group_pairwise"])
def test_original_overlapping_groups_refuse_before_pruning(mode, gm):
    document, _ = case("^[AB]$", "^[AB]$", [], mode=mode, gm=gm)
    if gm == "group_pairwise":
        document["demands"]["d"][0]["target"] = {"path": "^[AB]$", "group_by": "tg"}
    with pytest.raises(ValueError, match="non-diagonal source/target overlap"):
        prepare(Scenario.from_yaml(yaml.safe_dump(document)), demand_sets=("d",))
    document["demands"]["d"][0].update(source="^(A)$", target="^(C)$")
    prepare(Scenario.from_yaml(yaml.safe_dump(document)), demand_sets=("d",))


def test_oracle_hand_controls():
    ab, ba = pair("A", "B"), pair("B", "A")
    assert [r[1] for r in oracle([ab, ba], 5, Fraction(5))] == [3, 2]
    assert [r[1] for r in oracle([[ab, ba], [ab, ba]], 11, Fraction(11))] == [
        3,
        3,
        3,
        2,
    ]
    assert [r[1] for r in oracle([ab, [ab, ba, ab]], 10, Fraction(10))] == [5, 2, 2, 1]
    assert [r[1] for r in oracle([ab, EMPTY], 5, Fraction(5))] == [3, 2]


@pytest.mark.parametrize(
    "name",
    [
        "combine_flatten_self",
        "pairwise_flatten_self",
        "same_label_distinct_nodes",
        "empty_all",
    ],
)
def test_whole_discard_roots_keep_zero_structure_and_full_scaled_volume(name):
    document, _ = deepcopy(CASES[name])
    document["demands"]["d"][0]["volume"] = 0
    zero = prepare(
        replace(Scenario.from_yaml(yaml.safe_dump(document)), units=UnitsSettings(1)),
        demand_sets=("d",),
    ).demand_sets["d"]
    assert zero.demands == ()
    parent = zero.expansion_template[0]
    assert parent.root.id == "d|0|0" and parent.root.order == 0
    assert parent.root.endpoints is None
    expected_reason = CASES[name][1][0].reason
    assert parent.root.discard_reason == expected_reason
    assert [(s.label, s.units, s.reason) for s in zero.accounting[0].discards] == [
        ("d|0|0", 0, expected_reason)
    ]


@pytest.mark.parametrize(
    "constructor", ["Endpoints", "ExpansionLeaf", "ExpansionSplit", "_Expansion"]
)
def test_expansion_construction_failure_publishes_nothing_and_retry_is_identical(
    monkeypatch, constructor
):
    import ngraph.analysis.demands as module

    document, _ = deepcopy(CASES["odd_matrix2"])
    scenario = Scenario.from_yaml(yaml.safe_dump(document))
    expected = module.expansion_plans(scenario.network, scenario.demand_sets["d"])
    original_nodes = dict(scenario.network.nodes)
    original_links = dict(scenario.network.links)
    original_demands = scenario.demand_sets["d"]
    make = getattr(module, constructor)

    def fail(*args, **kwargs):
        raise MemoryError("injected construction failure")

    with monkeypatch.context() as patch:
        patch.setattr(module, constructor, fail)
        with pytest.raises(MemoryError, match="injected construction failure"):
            module.expansion_plans(scenario.network, scenario.demand_sets["d"])
    assert (
        module.expansion_plans(scenario.network, scenario.demand_sets["d"]) == expected
    )
    assert dict(scenario.network.nodes) == original_nodes
    assert dict(scenario.network.links) == original_links
    assert scenario.demand_sets["d"] == original_demands
    assert getattr(module, constructor) is make


@pytest.mark.parametrize("interaction", ["ordered", "simultaneous"])
@pytest.mark.parametrize("workers", [1, 2])
def test_failure_capacity_and_connectivity_never_reallocate_pair_shares(
    interaction, workers
):
    from ngraph import PlacementQuery, place

    document, _ = deepcopy(CASES["odd_matrix2"])
    document["network"]["links"] = []
    prep = prepare(
        replace(Scenario.from_yaml(yaml.safe_dump(document)), units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    ds = prep.demand_sets["d"]
    result = place(prep, PlacementQuery(ds, interaction=interaction, workers=workers))
    rows = result.cases[0].states["converged"].rows
    assert [(r.id, r.reference_request_units, r.result.delivered) for r in rows] == [
        ("d|0|0", 3, 0),
        ("d|0|1", 2, 0),
    ]
    assert [(d.id, d.nominal_units) for d in ds.demands] == [("d|0|0", 3), ("d|0|1", 2)]


def test_pruned_combined_branch_has_no_ingress_pool_or_budget():
    from ngraph import FlowPolicyPreset, PlacementQuery, place

    document, _ = deepcopy(CASES["per_group_combine_mixed"])
    document["demands"]["d"][0]["preset"] = str(FlowPolicyPreset.TE_ECMP_16_LSP)
    document["workflow"] = [
        {
            "type": "TrafficMatrixPlacement",
            "name": "p",
            "demand_set": "d",
            "interaction": "simultaneous",
            "workers": 1,
        }
    ]
    prep = prepare(
        replace(Scenario.from_yaml(yaml.safe_dump(document)), units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    ds = prep.demand_sets["d"]
    assert tuple(prep.topology.pool_heads) == ("d|0|0",)
    (demand,) = ds.demands
    assert (
        demand.id,
        demand.order,
        demand.nominal_units,
        demand.endpoints.sources,
        demand.endpoints.destinations,
    ) == ("d|0|0", 0, 11, ("B",), ("A",))
    assert demand.pool is not None and demand.pool.offer_limit_units == 11
    assert (demand.pool.head.pool_id, demand.pool.head.physical_sources) == (
        "d|0|0",
        ("B",),
    )
    row = (
        place(prep, PlacementQuery(ds, workers=1)).cases[0].states["converged"].rows[0]
    )
    assert row.reference_request_units == row.result.delivered == 11


def test_mixed_empty_branch_keeps_its_share_without_redistribution():
    from ngraph.analysis.demands import expand_units
    from ngraph.results import Endpoints, ExpansionLeaf, ExpansionSplit

    active = ExpansionLeaf("d|0", 0, Endpoints(("A",), ("B",)), None)
    empty = ExpansionLeaf("d|1", 1, None, "empty_selection")
    root = ExpansionSplit("root", (active, empty))
    assert expand_units(root, 5) == ((active, 3), (empty, 2))
    assert leaf_amounts(root, 5) == {"d|0": Fraction(5, 2), "d|1": Fraction(5, 2)}


def test_many_large_declarations_keep_python_totals_above_uint64():
    document, _ = deepcopy(CASES["odd_matrix2"])
    declaration = document["demands"]["d"][0]
    declaration["volume"] = float(2**61)
    document["demands"]["d"] = [deepcopy(declaration) for _ in range(9)]
    ds = prepare(
        replace(Scenario.from_yaml(yaml.safe_dump(document)), units=UnitsSettings(1)),
        demand_sets=("d",),
    ).demand_sets["d"]
    assert [d.nominal_units for d in ds.demands] == [2**60] * 18
    assert sum(a.declared_units for a in ds.accounting) == 9 * 2**61 > 2**64
    assert sum(d.nominal_units for d in ds.demands) == 9 * 2**61
    assert all(
        type(a.declared_units) is int and a.discarded_units == 0 and a.discards == ()
        for a in ds.accounting
    )


@pytest.mark.parametrize(
    "name",
    ["odd_matrix2", "empty_all", "pairwise_flatten_self", "same_label_distinct_nodes"],
)
def test_accounting_export_has_exact_fields_and_applicable_reasons(name):
    import io
    import json
    from importlib.resources import files

    import jsonschema

    from ngraph import PlacementQuery, place, write_json

    document, trees = deepcopy(CASES[name])
    prep = prepare(
        replace(Scenario.from_yaml(yaml.safe_dump(document)), units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    sink = io.StringIO()
    write_json(place(prep, PlacementQuery(prep.demand_sets["d"], workers=1)), sink)
    wire = json.loads(sink.getvalue())
    total = document["demands"]["d"][0]["volume"]
    expected = oracle(trees[0], total, Fraction(total))
    discards = [
        {"label": f"d|0|{i}", "units": units, "reason": leaf.reason}
        for i, (leaf, units, _) in enumerate(expected)
        if leaf.reason
    ]
    discarded = sum(d["units"] for d in discards)
    assert wire["analysis"]["accounting"] == [
        {
            "base_id": "d|0",
            "declared_units": total,
            "resolved_units": total - discarded,
            "discarded_units": discarded,
            "discards": discards,
        }
    ]
    validator = jsonschema.Draft202012Validator(
        json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
    )
    validator.validate(wire)
    record = wire["analysis"]["accounting"][0]
    for field in record:
        for broken in (
            {k: v for k, v in record.items() if k != field},
            {**record, field: None},
        ):
            altered = deepcopy(wire)
            altered["analysis"]["accounting"][0] = broken
            assert not validator.is_valid(altered), (field, broken)


def test_exclusion_does_not_hide_an_invalid_named_program():
    from ngraph import (
        DemandSet,
        DemandSpec,
        Link,
        Network,
        Node,
        PinnedRoutes,
        RouteSpec,
        Selector,
    )

    network = Network(nodes={n: Node(n) for n in ("A", "B")})
    network.add_link(Link("A", "B", 10, 1))

    def scenario(route):
        spec = DemandSpec(
            Selector("^A$"), Selector("^A$"), 11, PinnedRoutes((route,)), id="self"
        )
        return Scenario(
            network,
            demand_sets={"d": DemandSet("d", (spec,))},
            routes={"good": RouteSpec("A", nodes=("A", "B"))},
            units=UnitsSettings(1),
        )

    with pytest.raises(ValueError, match="missing"):
        prepare(scenario("missing"), demand_sets=("d",))
    result = prepare(scenario("good"), demand_sets=("d",))
    assert result.demand_sets["d"].demands == ()
    assert [
        (s.label, s.units, s.reason)
        for s in result.demand_sets["d"].accounting[0].discards
    ] == [("self|0", 11, "self_pair")]


@pytest.mark.parametrize(
    "flavor", ["plain", "tunnelled", "pooled", "pinned", "controller"]
)
@pytest.mark.parametrize("interaction", ["ordered", "simultaneous"])
def test_adding_only_excluded_candidates_changes_no_failure_result(flavor, interaction):
    import io
    import random
    import re

    from ngraph import (
        FailureMode,
        FailurePolicy,
        FailureRequest,
        FailureRule,
        PlacementQuery,
        place,
        write_json,
    )

    rng = random.Random(731)
    for volume in (0, 1, 5, 11):
        links = [("A", "X"), ("A", "Y"), ("X", "M"), ("Y", "M"), ("M", "T")]
        document = {
            "network": {
                "nodes": {n: {} for n in ("A", "X", "Y", "M", "T")},
                "links": [
                    {
                        "source": s,
                        "target": t,
                        "capacity": rng.randint(3, 20),
                        "cost": rng.randint(1, 4),
                    }
                    for s, t in links
                ],
            },
            "demands": {
                "d": [
                    {
                        "source": "^(A)$",
                        "target": "^(T)$",
                        "volume": volume,
                        "mode": "pairwise",
                        "preset": "SHORTEST_PATHS_ECMP_LOSSY",
                    }
                ]
            },
            "units": {"resolution": 1},
            "seed": 42,
        }
        declaration = document["demands"]["d"][0]
        if flavor in ("pooled", "pinned"):
            declaration.update(mode="combine", group_mode="per_group")
        if flavor == "pooled":
            declaration["preset"] = "TE_ECMP_16_LSP"
        elif flavor == "tunnelled":
            declaration.pop("preset")
            declaration["model"] = {
                "routing": {
                    "type": "centralized_te",
                    "source_allocation": "equal",
                    "tunnel_count": {"per_head": 2},
                },
                "admission": "lossy",
            }
        elif flavor == "pinned":
            declaration.pop("preset")
            declaration["model"] = {
                "routing": {"type": "pinned", "routes": ["walk"]},
                "admission": "lossy",
            }
            document["supports"] = {
                "dag": {
                    "edges": [
                        {"link": f"{s}|{t}|0", "direction": "forward"} for s, t in links
                    ]
                }
            }
            document["routes"] = {"walk": {"head": "A", "support": "dag"}}
        elif flavor == "controller":
            declaration["preset"] = "SHORTEST_PATHS_WCMP"
            document["routing"] = {"igp_domain": "^(X|Y|M)$", "bgp_edge": "^(A|T)$"}
            document["wcmp_controller"] = {"scope": "all_routers"}
        document["workflow"] = [
            {
                "type": "TrafficMatrixPlacement",
                "name": "p",
                "demand_set": "d",
                "interaction": interaction,
                "workers": 1,
            }
        ]
        augmented = deepcopy(document)
        augmented["demands"]["d"][0]["source"] = "^(A|T)$"
        prep = [
            prepare(Scenario.from_yaml(yaml.safe_dump(d)))
            for d in (document, augmented)
        ]
        edge = rng.choice(links)
        failures = FailureRequest(
            FailurePolicy(
                modes=[
                    FailureMode(
                        1,
                        [
                            FailureRule(
                                "link",
                                mode="all",
                                path="^" + re.escape(edge[0] + "|" + edge[1]) + "$",
                            )
                        ],
                    )
                ]
            ),
            1,
            42,
        )
        exported = []
        for p in prep:
            result = place(
                p,
                PlacementQuery(
                    p.demand_sets["d"],
                    failures=failures,
                    states=("converged", "stale", "repair"),
                    interaction=interaction,
                    workers=2,
                ),
            )
            sink = io.StringIO()
            write_json(result, sink)
            exported.append(sink.getvalue())
        # The query echoes the caller's source selector. Account for precisely
        # that input edit; every other byte, including every result row, stays.
        assert exported[0].count('"path":"^(A)$"') == 1
        assert (
            exported[0].replace('"path":"^(A)$"', '"path":"^(A|T)$"', 1) == exported[1]
        ), (flavor, interaction, volume, edge)


@pytest.mark.parametrize("active_only", [None, True, False])
@pytest.mark.parametrize("side", ["source", "target"])
def test_python_selector_context_default_and_explicit_disabled_roster(
    active_only, side
):
    from ngraph import DemandSet, DemandSpec, Network, Node, Selector
    from ngraph.analysis.demands import expand_units, expansion_plans

    network = Network(
        nodes={"A": Node("A"), "B": Node("B", disabled=True), "T": Node("T")}
    )
    population = Selector("^(A|B)$", active_only=active_only)
    fixed = Selector("^(T)$")
    spec = DemandSpec(
        population if side == "source" else fixed,
        fixed if side == "source" else population,
        11,
        mode="pairwise",
    )
    (plan,) = expansion_plans(network, DemandSet("d", (spec,)))
    actual = [
        (leaf.endpoints.sources, leaf.endpoints.destinations, units)
        for leaf, units in expand_units(plan.root, 11)
    ]
    eligible = [("A", 6), ("B", 5)] if active_only is False else [("A", 11)]
    assert actual == [
        ((node,), ("T",), units) if side == "source" else (("T",), (node,), units)
        for node, units in eligible
    ]
