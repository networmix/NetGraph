"""Controller declarations: YAML and Python forms, and every refusal before native work."""

import re
from fractions import Fraction

import jsonschema
import netgraph_core as ngc
import pytest
import yaml

from ngraph import (
    CapacityQuery,
    ControllerGroup,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    RoutingDomain,
    Scenario,
    Selector,
    WCMPController,
    capacity,
    prepare,
)
from ngraph.model.demand import PRESETS
from tests.controller.helpers import (
    WCMP,
    delivered,
    demand,
    network,
    prepared,
    row,
    scenario,
    tree,
)

FIXTURE = """
units: {resolution: 0.015625, precision: 0.001}
network:
  nodes: {DC_A: {}, A1: {}, A2: {}, B1: {}, B2: {}, DC_B: {}}
  links:
    - {source: DC_A, target: A1, capacity: 100, cost: 1}
    - {source: DC_A, target: A2, capacity: 50, cost: 1}
    - {source: A1, target: B1, capacity: 100, cost: 1}
    - {source: A2, target: B2, capacity: 50, cost: 1}
    - {source: B1, target: DC_B, capacity: 100, cost: 1}
    - {source: B2, target: DC_B, capacity: 50, cost: 1}
routing: {igp_domain: {path: '^(A|B)[12]$'}, bgp_edge: {path: '^DC_'}}
wcmp_controller: {scope: group}
forwarding_groups:
  ingress:
    router: DC_A
    groups:
      - children:
          - {edge: {link: 'DC_A|A1|0', direction: forward}, share: 1}
      - children:
          - {edge: {link: 'DC_A|A2|0', direction: forward}, share: 1}
demands:
  ebb:
    - {id: dc, source: '^DC_A$', target: '^DC_B$', volume: 100, preset: SHORTEST_PATHS_WCMP}
workflow:
  - {type: TrafficMatrixPlacement, name: baseline, demand_set: ebb, workers: 1}
"""

LINE = [("S", "U", 10), ("U", "T", 10)]


def fixture(**changes):
    data = yaml.safe_load(FIXTURE)
    for path, value in changes.items():
        target = data
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[int(key)] if isinstance(target, list) else target[key]
        if value is None:
            del target[keys[-1]]
        else:
            target[keys[-1]] = value
    return yaml.safe_dump(data)


def test_yaml_declarations_parse_into_records_with_exact_shares():
    value = Scenario.from_yaml(
        fixture(**{"forwarding_groups.ingress.groups.1.share": "3/2"})
    )
    assert value.routing.igp_domain.path == "^(A|B)[12]$"
    assert value.wcmp_controller == WCMPController("group")
    groups = value.forwarding_groups["ingress"].groups
    assert groups[1].share == Fraction(3, 2) and groups[0].share == 1
    assert type(groups[0].children[0].share) is Fraction
    assert Scenario.from_yaml(
        fixture(**{"wcmp_controller": {}})
    ).wcmp_controller == WCMPController("next_hop")


@pytest.mark.parametrize(
    ("value", "stored"),
    [
        (2, Fraction(2)),
        ("3/2", Fraction(3, 2)),
        ("0.5", Fraction(1, 2)),
        (Fraction(3, 2), Fraction(3, 2)),
    ],
)
def test_exact_shares_from_python(value, stored):
    assert GroupChild(value).share == stored


@pytest.mark.parametrize("value", [0.5, True, "x", "1/0"])
def test_inexact_shares_are_refused_at_construction(value):
    with pytest.raises(ValueError, match="group_child.share"):
        GroupChild(value)


@pytest.mark.parametrize(
    "path",
    [
        "routing.extra",
        "wcmp_controller.extra",
        "forwarding_groups.ingress.extra",
        "forwarding_groups.ingress.groups.0.extra",
        "forwarding_groups.ingress.groups.0.children.0.extra",
    ],
)
def test_unknown_keys_refuse_in_every_new_object(path):
    with pytest.raises(jsonschema.ValidationError, match="extra"):
        Scenario.from_yaml(fixture(**{path: 1}))


@pytest.mark.parametrize("share", [0.5, True])
def test_yaml_floats_and_booleans_are_not_exact_shares(share):
    with pytest.raises(jsonschema.ValidationError):
        Scenario.from_yaml(
            fixture(**{"forwarding_groups.ingress.groups.0.share": share})
        )


def test_pairing_is_refused_at_construction():
    net = network(LINE)
    routing = RoutingDomain(Selector("^U$"), Selector("^(S|T)$"))
    with pytest.raises(ValueError, match="wcmp_controller: requires routing"):
        Scenario(net, wcmp_controller=WCMPController())
    with pytest.raises(
        ValueError, match="routing: constrains the WCMP controller only"
    ):
        Scenario(net, routing=routing)
    with pytest.raises(ValueError, match="forwarding_groups: require wcmp_controller"):
        Scenario(net, forwarding_groups={"g": tree("S", (1, [(1, "S|U|0")]))})
    # Control: with a controller the same tree is accepted and validated.
    value = Scenario(
        net,
        routing=routing,
        wcmp_controller=WCMPController(),
        forwarding_groups={"g": tree("S", (1, [(1, "S|U|0")]))},
        demand_sets=scenario(
            LINE, "^U$", "^(S|T)$", [demand("^S$", "^T$", 1)]
        ).demand_sets,
    )
    assert prepare(value, demand_sets=("d",)).demand_sets["d"].controller is not None
    with pytest.raises(TypeError, match="Scenario.routing: expected RoutingDomain"):
        Scenario(net, routing="^U$", wcmp_controller=WCMPController())


def test_a_controller_needs_a_consumer():
    value = scenario(
        LINE,
        "^U$",
        "^(S|T)$",
        [demand("^S$", "^T$", 1, FlowPolicyPreset.SHORTEST_PATHS_ECMP)],
    )
    with pytest.raises(
        ValueError, match="wcmp_controller: no SHORTEST_PATHS_WCMP demand"
    ):
        prepare(value, demand_sets=("d",))


def test_only_the_wcmp_preset_is_programmed():
    ecmp = demand("^S$", "^T$", 1, FlowPolicyPreset.SHORTEST_PATHS_ECMP, id="ecmp")
    native = demand(
        "^S$",
        "^T$",
        1,
        PRESETS[WCMP],
        id="native",
    )
    prep = prepared(
        LINE, "^U$", "^(S|T)$", [demand("^S$", "^T$", 1, id="w"), ecmp, native]
    )
    configs = {d.id: d.config.routing for d in prep.demand_sets["d"].demands}
    assert isinstance(configs["w|0"], ngc.Pinned)
    # A native weighted model, even the preset's own configuration, stays native.
    assert isinstance(configs["ecmp|0"], ngc.ShortestPaths)
    assert isinstance(configs["native|0"], ngc.ShortestPaths)


def test_a_wcmp_capacity_question_under_the_controller_is_refused():
    prep = prepared(LINE, "^U$", "^(S|T)$", [demand("^S$", "^T$", 1)])
    query = CapacityQuery(
        Selector("^S$"), Selector("^T$"), PRESETS[WCMP], declaration=WCMP, workers=1
    )
    with pytest.raises(ValueError, match="capacity: SHORTEST_PATHS_WCMP is programmed"):
        capacity(prep, query)
    text = (
        FIXTURE
        + "  - {type: MaxFlow, name: wcmp, source: '^DC_A$', target: '^DC_B$', preset: SHORTEST_PATHS_WCMP}\n"
    )
    with pytest.raises(
        ValueError, match="workflow.wcmp: SHORTEST_PATHS_WCMP is programmed"
    ):
        prepare(Scenario.from_yaml(text))
    # Control: without the controller the same question is native capacity WCMP.
    plain = prepare(Scenario(network(LINE)))
    result = capacity(plain, query).cases[0].states["converged"].rows[0].result
    assert result.delivered * plain.topology.q == 10


@pytest.mark.parametrize(
    ("args", "match"),
    [
        (("^Z$", "^(S|T)$"), "routing.igp_domain: empty selection"),
        (("^(S|U)$", "^(S|T)$"), r"routing: nodes \['S'\] are in both"),
    ],
)
def test_populations_are_nonempty_and_disjoint(args, match):
    with pytest.raises(ValueError, match=match):
        prepared(LINE, *args, [demand("^S$", "^T$", 1)])


@pytest.mark.parametrize(
    ("source", "target", "match"),
    [
        ("^S$", "^U$", "destination U is not in routing.bgp_edge"),
        ("^S$", "^(T|R)$", "the WCMP controller needs one destination router"),
        ("^Z$", "^T$", r"sources \['Z'\] are in neither"),
    ],
)
def test_a_programmed_demand_the_domain_cannot_place_is_refused(source, target, match):
    links = [*LINE, ("Z", "U", 10), ("U", "R", 10)]
    with pytest.raises(ValueError, match=r"demands.d\[0\]\(d\|0\): " + match):
        prepared(links, "^U$", "^(S|T|R)$", [demand(source, target, 1)])


def test_a_cut_off_source_is_a_native_no_route():
    links = [*LINE, ("B", "U", 10)]
    prep = prepared(
        links,
        "^U$",
        "^(S|T|B)$",
        [demand("^B$", "^T$", 6, id="b"), demand("^(S|B)$", "^T$", 6, id="sb")],
        disabled_links=("B|U|0",),
    )
    rows, analysis = delivered(prep)
    cut = analysis.cases[0].states["converged"].rows[0].result
    assert (cut.delivered, cut.source_drops, cut.unadmitted) == (0, 0, 6)
    assert cut.termination == ngc.Termination.NO_ROUTE
    # In a multi-source demand the cut-off source's share moves to S.
    assert rows["sb|0"] == 6


GROUPS = [("S", "A", 10), ("S", "C", 10), ("A", "T", 10), ("C", "T", 10)]
SCOPES = ["group", "next_hop", "all_routers"]


def group_prepared(*trees, scope="group", links=GROUPS, demands=None):
    return prepared(
        links,
        "^(A|C)$",
        "^(S|T|R)$",
        demands or [demand("^S$", "^T$", 4)],
        scope=scope,
        trees={f"g{i}": t for i, t in enumerate(trees)},
    )


@pytest.mark.parametrize(
    ("value", "match"),
    [
        (
            tree("Q", (1, [(1, "S|A|0")])),
            r"forwarding_groups.g0.router: unknown node 'Q'",
        ),
        (tree("S"), "forwarding_groups.g0.groups: expected at least one group"),
        (
            tree("S", (1, [])),
            r"forwarding_groups.g0.groups\[0\].children: expected at least one child",
        ),
        (
            tree("S", (-1, [(1, "S|A|0")]), (1, [(1, "S|C|0")])),
            r"groups\[0\].share: expected a nonnegative share",
        ),
        (
            tree("S", (1, [(1, "S|A|0"), (-1, "S|C|0")])),
            r"groups\[0\].children\[1\].share: expected a nonnegative share, got -1",
        ),
        (
            tree("S", (1, [(1, [(1, "S|A|0"), (-1, "S|C|0")])])),
            r"groups\[0\].children\[0\].children\[1\].share: expected a nonnegative",
        ),
        (
            tree("S", (1, [(1, "S|A|0")]), (0, [(0, [(-1, "S|C|0")])])),
            r"groups\[1\].children\[0\].children\[0\].share: expected a nonnegative",
        ),
        (
            tree("S", (1, [(1, "S|A|0"), (1, "S|A|0")]), (1, [(1, "S|C|0")])),
            r"children\[1\].edge: S\|A\|0 forward is also declared",
        ),
        (
            tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|A|0")])),
            r"groups\[1\].children\[0\].edge: S\|A\|0 forward is also declared",
        ),
        (
            tree("S", (1, [(1, "A|T|0")]), (1, [(1, "S|C|0")])),
            "does not leave router S",
        ),
        (tree("S", (1, [(1, "S|Q|0")])), "unknown directed physical link"),
        (
            tree("S", (0, [(1, "S|A|0")]), (0, [(1, "S|C|0")])),
            "root group shares of router S sum to zero",
        ),
    ],
)
@pytest.mark.parametrize("scope", SCOPES)
def test_tree_declarations_refuse_what_the_input_contract_forbids(scope, value, match):
    with pytest.raises(ValueError, match=match):
        group_prepared(value, scope=scope)


def test_a_child_has_exactly_one_of_edge_and_children():
    both = GroupChild(
        1,
        edge=tree("S", (1, [(1, "S|A|0")])).groups[0].children[0].edge,
        children=(GroupChild(1),),
    )
    for child in (both, GroupChild(1)):
        bad = ForwardingGroup(
            "S",
            (
                ControllerGroup((child,)),
                ControllerGroup(
                    (
                        GroupChild(
                            1, tree("S", (1, [(1, "S|C|0")])).groups[0].children[0].edge
                        ),
                    )
                ),
            ),
        )
        with pytest.raises(
            ValueError, match="expected exactly one of edge and children"
        ):
            group_prepared(bad)


def test_one_tree_per_router():
    a = tree("S", (2, [(1, "S|A|0")]), (1, [(1, "S|C|0")]))
    b = tree("S", (1, [(1, "S|A|0")]), (2, [(1, "S|C|0")]))
    with pytest.raises(
        ValueError,
        match="forwarding_groups.g1: router S already has the tree forwarding_groups.g0",
    ):
        group_prepared(a, b)
    # Control: trees at two routers.
    links = [*GROUPS, ("R", "A", 10), ("R", "C", 10)]
    two = group_prepared(
        a,
        tree("R", (1, [(1, "R|A|0")]), (1, [(1, "R|C|0")])),
        links=links,
        demands=[demand("^S$", "^T$", 4), demand("^R$", "^T$", 4, id="r")],
    )
    assert two.demand_sets["d"].controller is not None


@pytest.mark.parametrize("scope", SCOPES)
def test_a_positive_share_with_only_zero_children_is_refused_in_every_scope(
    scope,
):
    bad = tree("S", (1, [(1, "S|A|0")]), (1, [(0, "S|C|0")]))
    with pytest.raises(
        ValueError,
        match=r"forwarding_groups.g0.groups\[1\]: a positive share at router S has only zero child shares",
    ):
        group_prepared(bad, scope=scope)
    nested = tree("S", (1, [(1, [(0, "S|A|0"), (0, "S|C|0")])]))
    with pytest.raises(
        ValueError, match=r"groups\[0\].children\[0\]: a positive share"
    ):
        group_prepared(nested, scope=scope)


@pytest.mark.parametrize("scope", SCOPES)
def test_zero_children_beside_positive_ones_and_zero_share_subtrees_are_valid(scope):
    # A zero child beside a positive sibling is valid; it carries nothing.
    zero_child = group_prepared(
        tree("S", (1, [(1, "S|A|0"), (0, "S|C|0")])), scope=scope
    )
    assert zero_child.demand_sets["d"].controller is not None
    # A zero-share subtree is validated but not normalized: its all-zero children are fine.
    zero_parent = group_prepared(
        tree("S", (1, [(1, "S|A|0")]), (0, [(0, "S|C|0")])), scope=scope
    )
    assert zero_parent.demand_sets["d"].controller is not None
    # ... while a bad reference below a zero share is still refused.
    with pytest.raises(ValueError, match="unknown directed physical link"):
        group_prepared(tree("S", (1, [(1, "S|A|0")]), (0, [(0, "S|Q|0")])), scope=scope)


def test_a_zero_share_subtree_under_a_positive_root_is_valid():
    links = [("S", "X2", 10), ("S", "X3", 10), ("S", "X4", 10)] + [
        (f"X{i}", "T", 10) for i in (2, 3, 4)
    ]
    value = tree("S", (1, [(1, "S|X2|0"), (0, [(0, "S|X3|0")])]), (1, [(1, "S|X4|0")]))
    prep = prepared(
        links,
        "^X[2-4]$",
        "^(S|T)$",
        [demand("^S$", "^T$", 4)],
        scope="group",
        trees={"g": value},
    )
    assert [w for _, _, w in row(prep, "T", "S")] == [1, 0, 1]


def test_coverage_of_the_programmed_router_members():
    with pytest.raises(
        ValueError, match=r"members missing from the tree \['S\|C\|0 forward'\]"
    ):
        group_prepared(tree("S", (1, [(1, "S|A|0")])))
    links = [*GROUPS, ("S", "X", 10)]
    with pytest.raises(
        ValueError, match=r"leaves that are not members \['S\|X\|0 forward'\]"
    ):
        group_prepared(
            tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|C|0"), (1, "S|X|0")])),
            links=links,
        )
    with pytest.raises(
        ValueError, match="router S is programmed toward T but declares no tree"
    ):
        group_prepared(tree("A", (1, [(1, "A|T|0")])))
    # A leaf on a disabled link is no member either.
    with pytest.raises(
        ValueError, match=r"leaves that are not members \['S\|X\|0 forward'\]"
    ):
        prepared(
            [*links, ("X", "T", 10)],
            "^(A|C|X)$",
            "^(S|T)$",
            [demand("^S$", "^T$", 4)],
            scope="group",
            trees={
                "g": tree("S", (1, [(1, "S|A|0")]), (1, [(1, "S|C|0"), (1, "S|X|0")]))
            },
            disabled_links=("S|X|0",),
        )


def test_an_unused_tree_under_group_scope_is_refused():
    # wcmp_scope: the DC tree splits equally over the planes; a tree at Q-A1 would
    # program Q-A1 5:1 (480 instead of 160), but Q-A1 is no programmed router.
    from tests.controller.test_tables import WCMP_SCOPE, wcmp_scope_tree

    extra = tree("QA1", (1, [(5, "QA1|QB1|0")]), (1, [(1, "QA1|QB2|0")]))
    with pytest.raises(
        ValueError,
        match="forwarding_groups.g1: router QA1 is programmed toward no destination",
    ):
        prepared(
            WCMP_SCOPE,
            "^(P|Q)(A|B)[12]$",
            "^DC",
            [demand("^DC$", "^DCB$", 1)],
            scope="group",
            trees={"g0": wcmp_scope_tree(), "g1": extra},
        )
    # Under next_hop the same tree is validated and unused.
    prep = prepared(
        WCMP_SCOPE,
        "^(P|Q)(A|B)[12]$",
        "^DC",
        [demand("^DC$", "^DCB$", 640)],
        trees={"g0": wcmp_scope_tree(), "g1": extra},
    )
    assert delivered(prep)[0] == {"d|0|0": 640}


@pytest.mark.parametrize(
    ("make", "error", "match"),
    [
        (lambda: GroupChild(1, edge="S|A|0"), TypeError, "group_child.edge"),
        (lambda: GroupChild(1, children=("x",)), TypeError, "group_child.children"),
        (lambda: ControllerGroup(("x",)), TypeError, "controller_group.children"),
        (lambda: ForwardingGroup("", ()), ValueError, "forwarding_group.router"),
        (lambda: ForwardingGroup("S", ("x",)), TypeError, "forwarding_group.groups"),
        (
            lambda: RoutingDomain("^A$", Selector("^B$")),
            TypeError,
            "routing: expected Selector populations",
        ),
        (
            lambda: WCMPController("everything"),
            ValueError,
            "wcmp_controller.scope: expected next_hop, group or all_routers",
        ),
        (
            lambda: Scenario(
                network(GROUPS), routing="x", wcmp_controller=WCMPController()
            ),
            TypeError,
            "Scenario.routing: expected RoutingDomain",
        ),
        (
            lambda: Scenario(
                network(GROUPS),
                routing=RoutingDomain(Selector("^A$"), Selector("^S$")),
                wcmp_controller="next_hop",
            ),
            TypeError,
            "Scenario.wcmp_controller: expected WCMPController",
        ),
    ],
)
def test_constructors_refuse_wrong_types_and_an_unknown_scope(make, error, match):
    with pytest.raises(error, match=match):
        make()


@pytest.mark.parametrize("scope", SCOPES)
def test_a_positive_root_whose_children_are_zero_and_zero_is_refused(scope):
    with pytest.raises(
        ValueError,
        match=r"forwarding_groups.g0.groups\[0\]: a positive share at router S has only zero child shares",
    ):
        group_prepared(tree("S", (1, [(0, "S|A|0"), (0, "S|C|0")])), scope=scope)
    # Control: the same members with one positive child.
    assert (
        group_prepared(tree("S", (1, [(1, "S|A|0"), (0, "S|C|0")])), scope=scope)
        .demand_sets["d"]
        .controller
    )


@pytest.mark.parametrize(
    ("share", "message"),
    [("x", "invalid exact fraction"), (-1, "expected a nonnegative share, got -1")],
)
def test_child_shares_are_checked_below_a_zero_share_too(share, message):
    zero_parent = {"forwarding_groups.ingress.groups.1.share": 0}
    assert prepare(Scenario.from_yaml(fixture(**zero_parent)))
    bad = {**zero_parent, "forwarding_groups.ingress.groups.1.children.0.share": share}
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"forwarding_groups.ingress.groups[1].children[0].share: {message}"
        ),
    ):
        prepare(Scenario.from_yaml(fixture(**bad)))
