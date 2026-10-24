"""The destination DAG of a routing domain: exits, one reverse search, uplinks, no transit."""

import netgraph_core as ngc
import pytest

from tests.controller.helpers import dag_edges, delivered, demand, prepared, row

# Nearest exit: S (BGP) - U - X1 | X2 (exits) - T (BGP). U->X1 costs 1 and U->X2 costs 2, but X1's
# exit link costs 10 and has capacity 4: the nearest exit by IGP distance is X1.
NEAREST_EXIT = [
    ("S", "U", 10),
    ("U", "X1", 10),
    ("U", "X2", 10, 2),
    ("X1", "T", 4, 10),
    ("X2", "T", 10),
]
DOMAIN, EDGE = "^(U|X1|X2)$", "^(S|T|B2)$"


def test_one_reverse_search_from_all_exits_picks_the_nearest_igp_exit():
    prep = prepared(NEAREST_EXIT, DOMAIN, EDGE, [demand("^S$", "^T$", 10)])
    # Exit-link cost does not select the exit; per-exit DAGs are not unioned.
    assert dag_edges(prep, "T") == ["S->U", "U->X1", "X1->T", "X2->T"]
    assert delivered(prep)[0] == {"d|0|0": 4}


def test_other_bgp_edge_routers_supply_uplinks_but_never_carry_transit():
    links = [*NEAREST_EXIT, ("U", "B2", 10), ("B2", "T", 10)]
    prep = prepared(
        links,
        DOMAIN,
        EDGE,
        [demand("^S$", "^T$", 10), demand("^B2$", "^T$", 1, id="b2")],
    )
    edges = dag_edges(prep, "T")
    assert edges == ["B2->U", "S->U", "U->X1", "X1->T", "X2->T"]
    # Nothing enters a BGP-edge router but the destination.
    assert not [e for e in edges if e.split("->")[1] in ("S", "B2")]
    rows, _ = delivered(prep)
    assert rows["d|0|0"] == 4
    assert row(prep, "T", "B2") == [("U|B2|0", "reverse", 1)]


def test_no_exit_gives_an_empty_dag_and_a_native_no_route():
    links = [("S", "U", 10), ("U", "B2", 10), ("B2", "T", 10)]
    prep = prepared(links, "^U$", EDGE, [demand("^S$", "^T$", 7)])
    assert dag_edges(prep, "T") == []
    assert prep.demand_sets["d"].controller[0].programmed == ()
    rows, analysis = delivered(prep)
    result = analysis.cases[0].states["converged"].rows[0].result
    # Consumers are lossless: the request is refused before entering.
    assert (rows["d|0|0"], result.unadmitted, result.source_drops) == (0, 7, 0)
    assert result.termination == ngc.Termination.NO_ROUTE


def test_native_endpoints_stay_nonempty_with_an_empty_dag():
    # The leaf's own endpoints go to native construction; Core refuses empty ones.
    g = ngc.Graph(2, [], [], [], [], 1.0)
    empty = ngc.PredecessorDAG.from_csr(g, [0, 0, 0], [], [])
    program = ngc.ForwardingProgram.from_dag(g, [0], [1], empty)
    for admission, offer, expected in (
        (ngc.Admission.LOSSY, 7, (0, 7, 0)),
        (ngc.Admission.LOSSLESS, 6, (0, 0, 6)),
    ):
        r = ngc.evaluate_demand(
            g,
            [0],
            [1],
            ngc.EvaluationOptions(
                ngc.FlowPolicyConfig(routing=ngc.Pinned(program), admission=admission),
                offer=offer,
            ),
        )
        assert (r.delivered, r.source_drops, r.unadmitted) == expected
        assert r.termination == ngc.Termination.NO_ROUTE
    with pytest.raises(ValueError, match="sources: the node set is empty"):
        ngc.ForwardingProgram.from_dag(g, [], [1], empty)


def test_uplinks_whatever_their_igp_distance_and_every_parallel_exit_link():
    links = [("S", "U1", 10), ("S", "U2", 10), ("U2", "U1", 10), ("U1", "T", 20)]
    prep = prepared(links, "^U[12]$", "^(S|T)$", [demand("^S$", "^T$", 20)])
    assert dag_edges(prep, "T") == ["S->U1", "S->U2", "U1->T", "U2->U1"]
    assert row(prep, "T", "S") == [("S|U1|0", "forward", 1), ("S|U2|0", "forward", 1)]
    assert delivered(prep)[0] == {"d|0|0": 20}
    parallel = [("S", "X", 10), ("X", "T", 5), ("X", "T", 5)]
    prep = prepared(parallel, "^X$", "^(S|T)$", [demand("^S$", "^T$", 10)])
    assert dag_edges(prep, "T") == ["S->X", "X->T", "X->T"]
    assert delivered(prep)[0] == {"d|0|0": 10}


@pytest.mark.parametrize(
    "disabled", [{"disabled_links": ("U|X1|0",)}, {"disabled_nodes": ("X1",)}]
)
def test_the_nominal_mask_removes_disabled_links_and_nodes(disabled):
    prep = prepared(NEAREST_EXIT, DOMAIN, EDGE, [demand("^S$", "^T$", 10)], **disabled)
    # A disabled link leaves X1 an exit (its own link to T stays); a disabled node does not.
    expected = ["S->U", "U->X2", "X2->T"]
    if "disabled_links" in disabled:
        expected = ["S->U", "U->X2", "X1->T", "X2->T"]
    assert dag_edges(prep, "T") == expected
    assert delivered(prep)[0] == {"d|0|0": 10}


def test_an_exit_needs_an_eligible_link_to_the_destination():
    prep = prepared(
        NEAREST_EXIT,
        DOMAIN,
        EDGE,
        [demand("^S$", "^T$", 10)],
        disabled_links=("X1|T|0",),
    )
    # X1 is no exit now; as a domain node it reaches X2 through U.
    assert dag_edges(prep, "T") == ["S->U", "U->X2", "X1->U", "X2->T"]
    assert delivered(prep)[0] == {"d|0|0": 10}


def test_zero_capacity_links_stay_in_the_dag():
    links = [
        ("S", "U", 10),
        ("U", "X1", 0),
        ("U", "X2", 10),
        ("X1", "T", 10),
        ("X2", "T", 10),
    ]
    prep = prepared(links, DOMAIN, EDGE, [demand("^S$", "^T$", 10)])
    assert "U->X1" in dag_edges(prep, "T")


def test_an_uplink_into_a_domain_node_that_reaches_no_exit_is_left_out():
    # B's only uplink enters V, which has no route to an exit inside the domain.
    links = [("S", "U", 10), ("U", "X", 10), ("X", "T", 10), ("B", "V", 10)]
    prep = prepared(
        links,
        "^(U|X|V)$",
        "^(S|B|T)$",
        [demand("^S$", "^T$", 5), demand("^B$", "^T$", 1, id="b", priority=1)],
    )
    assert dag_edges(prep, "T") == ["S->U", "U->X", "X->T"]
    assert [r.router for r in prep.demand_sets["d"].controller[0].programmed] == ["S"]
    rows, analysis = delivered(prep)
    assert rows == {"d|0|0": 5, "b|0": 0}
    (b,) = [
        r.result for r in analysis.cases[0].states["converged"].rows if r.id == "b|0"
    ]
    assert (b.termination, b.unadmitted) == (ngc.Termination.NO_ROUTE, 1)


def test_a_deep_domain_is_walked_without_recursion():
    n = 600
    links = [
        ("S", "N0000", 10),
        *[(f"N{i:04}", f"N{i + 1:04}", 10) for i in range(n - 1)],
        (f"N{n - 1:04}", "T", 10),
    ]
    prep = prepared(links, "^N", "^(S|T)$", [demand("^S$", "^T$", 1)], q=1)
    assert delivered(prep)[0] == {"d|0|0": 1}
