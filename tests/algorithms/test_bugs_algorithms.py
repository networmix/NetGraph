import pytest

from ngraph.algorithms.max_flow import calc_max_flow
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def test_min_cut_should_not_include_edge_from_source_side_with_only_reverse_reachability():
    """Repro: reverse-residual reachability is ignored in reachable/min_cut.

    Topology (costs in brackets, capacities all 1):
        S -> A [0]
        A -> B [1]
        B -> T [1]
        S -> B [2]

    Max-flow augmentation picks S->A->B->T (cost=2), saturating S->A, A->B, B->T.
    In the true residual graph, S can reach B (forward residual on S->B), and then reach A via
    the reverse residual edge B->A (from the flow on A->B). Therefore A is reachable from S
    in the residual graph, so edge S->A must NOT be in the s-t min-cut. The min-cut should be
    only {B->T}.

    Current implementation computes reachable via forward residual edges only
    (ngraph/algorithms/max_flow.py:_build_flow_summary), incorrectly including S->A in min-cut.
    """

    g = StrictMultiDiGraph()
    for n in ("S", "A", "B", "T"):
        g.add_node(n)

    # Record keys for explicit assertions
    sa_k = g.add_edge("S", "A", capacity=1.0, flow=0.0, flows={}, cost=0)
    ab_k = g.add_edge("A", "B", capacity=1.0, flow=0.0, flows={}, cost=1)
    bt_k = g.add_edge("B", "T", capacity=1.0, flow=0.0, flows={}, cost=1)
    sb_k = g.add_edge("S", "B", capacity=1.0, flow=0.0, flows={}, cost=2)

    # Sanity: avoid flake8/ruff unused warnings
    assert all(k is not None for k in (sa_k, ab_k, bt_k, sb_k))

    flow, summary = calc_max_flow(g, "S", "T", return_summary=True)

    assert flow == 1.0

    # Expected correct min-cut: only B->T
    expected_bt = ("B", "T", bt_k)
    unexpected_sa = ("S", "A", sa_k)

    # Now correct behavior: only B->T is in the cut, S->A is not.
    assert expected_bt in summary.min_cut
    assert unexpected_sa not in summary.min_cut


@pytest.mark.xfail(
    strict=True,
    reason="SPF fast path hardcodes 'capacity'/'flow' ignoring calc_max_flow capacity_attr/flow_attr; see ngraph/algorithms/spf.py:_spf_fast_all_min_cost_with_cap_remaining_dijkstra",
)
def test_calc_max_flow_respects_custom_attribute_names():
    """Repro: passing custom capacity/flow attribute names breaks SPF fast path.

    The public API allows custom attribute names via capacity_attr/flow_attr.
    The SPF fast-path still reads 'capacity' and 'flow' directly, raising KeyError.
    """

    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    # Use non-default attribute names: 'cap' and 'flowX'
    g.add_edge("A", "B", cap=5.0, flowX=0.0, flows={}, cost=1)

    # Should compute 5.0 using the provided attribute names without error.
    max_flow = calc_max_flow(
        g,
        "A",
        "B",
        capacity_attr="cap",
        flow_attr="flowX",
    )

    assert max_flow == 5.0
