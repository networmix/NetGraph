"""all_routers: one native flow whose sources send in proportion to the demands."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

import ngraph.analysis.controller as controller
from ngraph import MSDQuery, maximum_supported_demand
from ngraph.results import WeightApproximation
from tests.controller.helpers import delivered, demand, prepared, row, table

# A and B share M; every path costs 3; the cut into t is 2.
MERGE_AT_M = [
    ("A", "M", 2),
    ("B", "M", 1),
    ("B", "X", 1, 2),
    ("M", "X", 1),
    ("M", "Y", 1),
    ("X", "t", 1),
    ("Y", "t", 1),
]
DOMAIN, EDGE = "^(M|X|Y)$", "^(A|B|Bp|C|t)$"
L = 1 << 62


def merge_at_m(*demands, q=1 / 8, links=MERGE_AT_M, **kwargs):
    return prepared(
        links, DOMAIN, EDGE, list(demands), scope="all_routers", q=q, **kwargs
    )


A2 = demand("^A$", "^t$", 2, id="a")
B1 = demand("^B$", "^t$", 1, id="b", priority=1)


def weights(prep, router, set_name="d"):
    return {link: w for link, _, w in row(prep, "t", router, set_name)}


def source_weights(prep, set_name="d"):
    (report,) = prep.demand_sets[set_name].controller
    return {s.source: (s.nominal_physical, s.weight) for s in report.source_weights}


def test_one_weighted_solve_programs_every_router_on_the_walks():
    prep = merge_at_m(A2, B1)
    assert source_weights(prep) == {"A": (2, 2), "B": (1, 1)}
    # H(16, [2, 1]) = [11, 5]: B's 5 over B->X, A's 3 over M->X and 8 over M->Y.
    assert weights(prep, "M") == {"M|X|0": 3, "M|Y|0": 8}
    assert weights(prep, "B") == {"B|M|0": 0, "B|X|0": 5}
    assert weights(prep, "A") == {"A|M|0": 11}
    assert delivered(prep)[0] == {"a|0": 11, "b|0": 5}


def test_each_matrix_is_its_own_table():
    prep = merge_at_m(
        A2,
        B1,
        sets={
            "equal": [
                demand("^A$", "^t$", 1, id="a2"),
                demand("^B$", "^t$", 1, id="b2", priority=1),
            ]
        },
    )
    assert weights(prep, "M") == {"M|X|0": 3, "M|Y|0": 8}
    # Equal weights: A and B each 8 units, B over X, A over Y.
    assert weights(prep, "M", "equal") == {"M|X|0": 0, "M|Y|0": 8}
    assert delivered(prep, "equal")[0] == {"a2|0": 8, "b2|0": 8}


def test_the_vector_is_aggregated_before_rounding():
    prep = merge_at_m(
        demand("^A$", "^t$", 0.25, id="a"), demand("^B$", "^t$", 0.5, id="b"), q=1
    )
    # At q=1 the units would be 0 and 1; the exact amounts give 1:2.
    assert source_weights(prep) == {"A": (Fraction(1, 4), 1), "B": (Fraction(1, 2), 2)}


def test_a_multi_source_leaf_divides_over_its_sources_that_reach_t():
    links = [*MERGE_AT_M, ("Bp", "M", 1)]
    prep = merge_at_m(
        demand("^(A|Bp)$", "^t$", 2, id="ab"),
        B1,
        links=links,
        disabled_links=("Bp|M|0",),
    )
    # Bp has no eligible uplink: A carries the leaf's whole 2 (not 1 and 1).
    assert source_weights(prep) == {"A": (2, 2), "B": (1, 1), "Bp": (0, 0)}
    assert delivered(prep)[0] == {"ab|0": 11, "b|0": 5}
    repeated = merge_at_m(
        demand("^A$", "^t$", 0.5, id="a1"),
        demand("^A$", "^t$", 0.5, id="a2"),
        demand("^B$", "^t$", 1, id="b", priority=1),
    )
    assert source_weights(repeated) == {"A": (1, 1), "B": (1, 1)}


def test_discarded_self_shares_are_excluded():
    prep = merge_at_m(demand("^(A|t)$", "^t$", 4, id="at", mode="pairwise"), B1)
    # Leaves A->t (2) and t->t (2, a discarded self pair).
    assert source_weights(prep) == {"A": (2, 2), "B": (1, 1)}
    accounting = prep.demand_sets["d"].accounting[0]
    assert [d.reason for d in accounting.discards] == ["self_pair"]


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_coprime_proportions_in_either_declaration_order(reverse):
    links = [(f"{p}{i}", "M", 10) for p, n in (("P", 3), ("Q", 7)) for i in range(n)]
    links += [("M", "X", 100), ("X", "t", 100)]
    three = demand("^P[0-2]$", "^t$", 1, id="three")
    seven = demand("^Q[0-6]$", "^t$", 1, id="seven", priority=1)
    prep = prepared(
        links,
        "^(M|X)$",
        "^(P\\d|Q\\d|t)$",
        [seven, three] if reverse else [three, seven],
        scope="all_routers",
    )
    found = source_weights(prep)
    assert {found[f"P{i}"][1] for i in range(3)} == {7}
    assert {found[f"Q{i}"][1] for i in range(7)} == {3}
    assert found["P0"][0] == Fraction(1, 3) and found["Q0"][0] == Fraction(1, 7)


def test_a_zero_volume_source_keeps_weight_zero_and_changes_nothing():
    links = [*MERGE_AT_M, ("C", "M", 1)]
    base = merge_at_m(A2, B1, links=links)
    zero = merge_at_m(A2, B1, demand("^C$", "^t$", 0, id="c", priority=2), links=links)
    # C's own uplink is listed with weight 0; every other router's row is unchanged.
    for router in ("A", "B", "M", "X", "Y"):
        assert weights(base, router) == weights(zero, router)
    assert row(base, "t", "C") is None and weights(zero, "C") == {"C|M|0": 0}
    assert source_weights(zero)["C"] == (0, 0)
    assert delivered(zero)[0] == {"a|0": 11, "b|0": 5, "c|0": 0}


def test_the_table_is_fixed_for_alpha_and_the_msd_series():
    prep = merge_at_m(
        demand("^A$", "^t$", 0.25, id="a"), demand("^B$", "^t$", 0.5, id="b"), q=1
    )
    t = table(prep, "t")
    _, scaled = delivered(prep, alpha=2.0)
    assert scaled.query.demands.controller_table("t") is t
    search = maximum_supported_demand(prep, MSDQuery(prep.demand_sets["d"]))
    assert search.query.demands.controller_table("t") is t
    # Proportions from rounded probe units would give [0, 1] at alpha 1.
    assert source_weights(prep) == {"A": (Fraction(1, 4), 1), "B": (Fraction(1, 2), 2)}


def test_source_weights_at_the_native_bound_are_apportioned_and_reported():
    prep = merge_at_m(
        demand("^A$", "^t$", 1000, id="a"), demand("^B$", "^t$", 0.1, id="b")
    )
    # 0.1 is 3602879701896397 / 2^55, so the exact weights are [125 * 2^58,
    # 3602879701896397]; over 2^62 - 1 units the floors are 4611224895937794123
    # and 461122489593779, and the one unit left goes to A's larger quotient.
    assert source_weights(prep) == {
        "A": (1000, 4611224895937794124),
        "B": (Fraction(0.1), 461122489593779),
    }
    error = Fraction(404628740251494852, 426034614033626905898254159925269)
    entry = WeightApproximation("controller.d.t.source.B", error)
    assert prep.units_report.weight_approximations == (entry,)
    _, analysis = delivered(prep)
    assert analysis.units_report.weight_approximations == (entry,)
    exact = merge_at_m(
        demand("^A$", "^t$", 1e6, id="a"), demand("^B$", "^t$", 1.0, id="b")
    )
    assert source_weights(exact) == {"A": (10**6, 10**6), "B": (1, 1)}
    assert exact.units_report.weight_approximations == ()


def test_the_source_entry_names_the_earlier_source_on_equal_errors():
    tiny = 2.0**-70
    prep = merge_at_m(
        demand("^A$", "^t$", 1.0, id="a"),
        demand("^B$", "^t$", tiny, id="b"),
        demand("^C$", "^t$", tiny, id="c", priority=2),
        links=[*MERGE_AT_M, ("C", "M", 1)],
    )
    # Exact [2^70, 1, 1]: B and C keep their reserved unit and share one error.
    assert {s: w for s, (_, w) in source_weights(prep).items()} == {
        "A": L - 3,
        "B": 1,
        "C": 1,
    }
    error = Fraction((1 << 70) - L + 3, L - 1)
    assert prep.units_report.weight_approximations == (
        WeightApproximation("controller.d.t.source.B", error),
    )


def test_an_all_zero_matrix_and_an_empty_support_are_distinct_outcomes():
    zero = merge_at_m(demand("^A$", "^t$", 0, id="a"), demand("^B$", "^t$", 0, id="b"))
    assert set(weights(zero, "M").values()) == {0}
    assert search_status(zero) == "trivial"
    links = [("A", "M", 2), ("M", "C", 2), ("C", "t", 2)]
    empty = prepared(links, "^M$", EDGE, [A2], scope="all_routers")
    assert empty.demand_sets["d"].controller[0].programmed == ()
    rows, analysis = delivered(empty)
    result = analysis.cases[0].states["converged"].rows[0].result
    assert rows == {"a|0": 0}
    assert result.termination == ngc.Termination.NO_ROUTE


def search_status(prep):
    return maximum_supported_demand(prep, MSDQuery(prep.demand_sets["d"])).search_status


def test_a_coarse_quantum_is_a_different_answer():
    prep = merge_at_m(A2, B1, q=1)
    # H(2, [2, 1]) = [2, 0]: B's row carries nothing and B's demand finds no route.
    assert weights(prep, "B") == {"B|M|0": 0, "B|X|0": 0}
    assert delivered(prep)[0] == {"a|0": 2, "b|0": 0}


def test_only_routers_on_the_sources_walks_are_listed():
    links = [*MERGE_AT_M, ("C", "M", 1)]
    prep = merge_at_m(A2, B1, links=links)
    listed = [r.router for r in prep.demand_sets["d"].controller[0].programmed]
    # C is a BGP-edge router with an uplink but no demand.
    assert listed == ["A", "B", "M", "X", "Y"]


def test_a_native_refusal_of_the_weighted_solve_names_the_destination(monkeypatch):
    def refuse(*args, **kwargs):
        raise ValueError("planted")

    monkeypatch.setattr(controller.ngc, "evaluate_demand", refuse)
    with pytest.raises(ValueError, match=r"^controller\.t: planted$"):
        merge_at_m(A2, B1)
