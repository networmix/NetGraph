"""Explicit routes use native validation, ordered duplicates and physical labels."""

import netgraph_core as ngc
import pytest

from ngraph import Link, Network, Node
from ngraph.analysis.placement import policy_roster, remove_policies, replace_matrix
from ngraph.analysis.programs import compile_named, pinned_config, support_dag
from ngraph.analysis.topology import compile_topology
from ngraph.model.demand import (
    PRESETS,
    EdgeWeight,
    FlowPolicyPreset,
    PinnedRoutes,
    RouteSpec,
    SupportSpec,
    WeightSpec,
)
from ngraph.model.network import DirectedLink
from ngraph.results import Endpoints, ResolvedDemand


@pytest.mark.parametrize(
    "invalid,valid,message",
    [
        (
            lambda: SupportSpec(("edge",)),
            lambda: SupportSpec((DirectedLink("a|b|0", "forward"),)),
            "support.edges",
        ),
        (lambda: WeightSpec(("entry",)), lambda: WeightSpec(()), "weights.entries"),
        (
            lambda: RouteSpec("a", nodes="abt"),
            lambda: RouteSpec("a", nodes=("a", "b", "t")),
            "route.nodes",
        ),
        (
            lambda: PinnedRoutes("route"),
            lambda: PinnedRoutes(("route",)),
            "pinned.routes",
        ),
        (
            lambda: PinnedRoutes(({},)),
            lambda: PinnedRoutes(("route",)),
            "pinned.routes",
        ),
    ],
)
def test_declaration_members_refuse_wrong_shapes_and_own_legal_sequences(
    invalid, valid, message
):
    with pytest.raises((ValueError, TypeError), match=message):
        invalid()
    assert valid() is not None


def network():
    n = Network()
    for name in ("t", "a", "b"):
        n.add_node(Node(name))
    n.add_link(Link("a", "b", 2, 1))
    n.add_link(Link("a", "b", 3, 4))
    n.add_link(Link("b", "t", 2, 2))
    n.add_link(Link("a", "t", 3, 5))
    return n


def test_node_path_chooses_cheapest_member_explicit_selects_other_and_reverse():
    t = compile_topology(network(), 1)
    routes = compile_named(
        t,
        routes={
            "cheap": RouteSpec("a", nodes=("a", "b", "t")),
            "other": RouteSpec(
                "a",
                edges=(
                    DirectedLink("a|b|1", "forward"),
                    DirectedLink("b|t|0", "forward"),
                ),
            ),
            "back": RouteSpec("b", edges=(DirectedLink("a|b|0", "reverse"),)),
        },
    ).routes
    cheap, other, reverse = routes["cheap"], routes["other"], routes["back"]
    assert cheap.route.cost() == 3
    assert other.route.cost() == 6
    assert reverse.route.source() == t.node_id_by_name["b"]
    assert reverse.route.destination() == t.node_id_by_name["a"]


def test_duplicates_remain_separate_and_invalid_zero_weight_route_is_validated():
    t = compile_topology(network(), 1)
    endpoints = Endpoints(("a",), ("t",))
    route = RouteSpec("a", nodes=("a", "b", "t"))
    config = pinned_config(
        t,
        endpoints,
        PinnedRoutes(("one", "one")),
        compile_named(t, routes={"one": route}),
    )
    assert [entry.entry_id for entry in config.routing.program.tunnels] == [0, 1]
    with pytest.raises(ValueError, match="ends|destination"):
        pinned_config(
            t,
            endpoints,
            PinnedRoutes(("bad",)),
            compile_named(
                t, routes={"bad": RouteSpec("a", nodes=("a", "b"), weight=0)}
            ),
        )
    assert len(config.routing.program.tunnels) == 2


def test_empty_cycle_duplicate_supports_and_explicit_weighted_dag():
    t = compile_topology(network(), 1)
    refs = (DirectedLink("a|b|0", "forward"), DirectedLink("b|t|0", "forward"))
    dag = support_dag(t, SupportSpec(refs), "dag")
    assert set(dag.via_edges()) == {t._edge_id_by_ref[ref] for ref in refs}
    with pytest.raises(ValueError, match="support.edges: expected at least one edge"):
        SupportSpec(())
    with pytest.raises(ValueError, match="duplicate"):
        support_dag(t, SupportSpec(refs + refs), "duplicate")
    with pytest.raises(ValueError, match="cycle|acyclic"):
        support_dag(
            t, SupportSpec((refs[0], DirectedLink("a|b|0", "reverse"))), "cycle"
        )
    weights = WeightSpec(tuple(EdgeWeight(ref, 1) for ref in refs))
    config = pinned_config(
        t,
        Endpoints(("a",), ("t",)),
        PinnedRoutes(
            ("dag",),
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights="w",
        ),
        compile_named(
            t,
            routes={"dag": RouteSpec("a", support="s")},
            supports={"s": SupportSpec(refs)},
            weights={"w": weights},
        ),
    )
    assert isinstance(config.routing, ngc.Pinned)


def test_ordered_full_replace_one_persistent_ledger_and_cleanup():
    t = compile_topology(network(), 1)
    config = PRESETS[FlowPolicyPreset.TE_MAXFLOW_UNLIM]
    demands = tuple(
        ResolvedDemand(
            str(i), str(i), Endpoints(("a",), ("t",)), 0, i, volume, config, None
        )
        for i, volume in enumerate((4, 3))
    )
    ledger, policies = policy_roster(t, demands, t.disabled)
    outputs = ngc.OutputOptions(edge_flows=True, min_cut=True)
    try:
        first = replace_matrix(ledger, policies, (4, 3), outputs)
        assert [r.delivered for r in first] == [4, 1]
        assert [r.total_cost for r in first] == [16, 5]
        assert sum(ledger.carried()) == 7
        middle = replace_matrix(ledger, policies, (1, 1), outputs)
        assert [r.delivered for r in middle] == [1, 1]
        again = replace_matrix(ledger, policies, (4, 3), outputs)
        assert [r.delivered for r in again] == [4, 1]
        assert [r.edge_flows.tolist() for r in again] == [
            r.edge_flows.tolist() for r in first
        ]
    finally:
        remove_policies(policies)
    assert not ledger.carried().any()
    assert first[0].delivered == 4 and first[0].total_cost == 16


def test_named_program_values_compile_once_per_graph_and_unused_references_validate(
    monkeypatch,
):
    import ngraph.analysis.programs as programs
    from ngraph.analysis.units import UnitsSettings
    from ngraph.model.demand import DemandSet, DemandSpec
    from ngraph.model.selectors import Selector
    from ngraph.scenario import Scenario, prepare

    counts = {"support": 0, "weights": 0}
    original_dag, original_weights = programs.support_dag, programs.explicit_weights

    def dag(*args):
        counts["support"] += 1
        return original_dag(*args)

    def vector(*args):
        counts["weights"] += 1
        return original_weights(*args)

    monkeypatch.setattr(programs, "support_dag", dag)
    monkeypatch.setattr(programs, "explicit_weights", vector)
    model = network()
    refs = (DirectedLink("a|b|0", "forward"), DirectedLink("b|t|0", "forward"))
    kwargs = dict(
        units=UnitsSettings(1),
        supports={"dag": SupportSpec(refs)},
        routes={"route": RouteSpec("a", support="dag")},
        weights={"w": WeightSpec(tuple(EdgeWeight(ref, 1) for ref in refs))},
        demand_sets={
            "x": DemandSet(
                "x",
                tuple(
                    DemandSpec(
                        Selector("^a$"),
                        Selector("^t$"),
                        1,
                        PinnedRoutes(
                            ("route",),
                            allocation=ngc.RouteAllocation.WEIGHTED,
                            weight_basis=ngc.WeightBasis.EXPLICIT,
                            edge_weights="w",
                        ),
                    )
                    for _ in range(3)
                ),
            )
        },
    )
    prepared = prepare(Scenario(model, **kwargs), demand_sets=("x",))
    assert counts == {"support": 1, "weights": 1}
    assert len(prepared.demand_sets["x"].demands) == 3
    bad = dict(
        kwargs,
        supports={"unused": SupportSpec((DirectedLink("missing", "forward"),))},
        routes={},
    )
    with pytest.raises(ValueError, match="support.unused.*unknown"):
        prepare(Scenario(model, **bad))
    assert (
        prepare(Scenario(model, **kwargs))._named.supports["dag"].graph_uid()
        != prepared.topology.graph.uid()
    )


def test_fully_discarded_named_pinned_demand_validates_without_fake_endpoints():
    from ngraph.analysis.units import UnitsSettings
    from ngraph.model.demand import DemandSet, DemandSpec
    from ngraph.model.selectors import Selector
    from ngraph.scenario import Scenario, prepare

    prepared = prepare(
        Scenario(
            network(),
            demand_sets={
                "x": DemandSet(
                    "x",
                    (
                        DemandSpec(
                            Selector("^a$"),
                            Selector("^a$"),
                            7,
                            PinnedRoutes(("route",)),
                        ),
                    ),
                )
            },
            routes={"route": RouteSpec("a", nodes=("a", "b", "t"))},
            units=UnitsSettings(1),
        ),
        demand_sets=("x",),
    )
    resolved = prepared.demand_sets["x"]
    assert resolved.demands == ()
    assert (
        resolved.accounting[0].declared_units
        == resolved.accounting[0].discarded_units
        == 7
    )
    assert resolved.accounting[0].resolved_units == 0
    assert resolved.expansion_template[0].policy.routes == ("route",)


def test_node_routes_share_one_hop_index_of_cheapest_enabled_hops(monkeypatch):
    from ngraph.analysis import programs

    calls = []
    original = programs.hop_index

    def counted(topology):
        calls.append(topology)
        return original(topology)

    monkeypatch.setattr(programs, "hop_index", counted)
    model = network()
    model.add_link(Link("a", "b", 5, 1))
    t = compile_topology(model, 1)
    routes = compile_named(
        t,
        routes={
            name: RouteSpec(head, nodes=nodes)
            for name, head, nodes in (
                ("one", "a", ("a", "b", "t")),
                ("two", "b", ("b", "t")),
                ("three", "a", ("a", "t")),
            )
        },
    ).routes
    assert calls == [t]
    # Of the two cost-1 parallel links a->b, the lower link id is the hop.
    (first, second) = routes["one"].route.hops()
    assert [t.edge_refs[edge] for edge in (*first, *second)] == [
        DirectedLink("a|b|0", "forward"),
        DirectedLink("b|t|0", "forward"),
    ]
    edges_only = {"e": RouteSpec("a", edges=(DirectedLink("a|t|0", "forward"),))}
    assert compile_named(t, routes=edges_only).routes["e"].route.cost() == 5
    assert calls == [t]
