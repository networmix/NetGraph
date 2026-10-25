"""Direct capacity batching and signed sensitivity, with independent flow/cut checks."""

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.topology import eligibility
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.results import SelfPair
from tests.flow_oracle import EDGES, closest_source_cut, enumerate_optimum
from tests.prepared import prepare_network


def prepared():
    network = Network()
    for name in ("a", "b", "t"):
        network.add_node(Node(name))
    for source, target, bandwidth, cost in (
        ("a", "b", 2, 1),
        ("b", "t", 2, 2),
        ("a", "t", 3, 5),
    ):
        network.add_link(Link(source, target, bandwidth, cost))
    return prepare_network(network)


def test_capacity_cases_match_independent_optima_costs_and_closest_cut():
    context = prepared()
    policy = FailurePolicy(
        modes=[
            FailureMode(1, [FailureRule("node", path="^b$")]),
            FailureMode(1, [FailureRule("link", path=r"^a\|t$")]),
        ]
    )
    result = capacity(
        context,
        CapacityQuery(
            Selector("^a$"),
            Selector("^t$"),
            failures=FailureRequest(policy, 24, seed=17),
            workers=2,
            outputs=ngc.OutputOptions(edge_flows=True, min_cut=True),
            export_cost_distribution=True,
        ),
    )
    assert result.question == "lossless_bound" and result.offer_source == "unlimited"
    assert len(result.cases) == 3
    for case_result in result.cases:
        case = case_result.case
        (row,) = case_result.states["converged"].rows
        assert case_result.states["converged"].totals is None
        optimum, cost, vector = enumerate_optimum(
            99,
            [e[4] for e in EDGES],
            case.pattern.excluded_nodes,
            case.pattern.excluded_links,
            False,
        )
        native = row.result
        assert native.delivered == optimum and native.total_cost == cost
        actual = {
            (ref.link, ref.direction): int(units)
            for ref, units in zip(
                context.topology.edge_refs, native.edge_flows, strict=True
            )
        }
        assert (
            tuple(actual[(link, direction)] for link, direction, *_ in EDGES) == vector
        )
        cut = {
            (
                context.topology.edge_refs[edge].link,
                context.topology.edge_refs[edge].direction,
            )
            for edge in native.min_cut
        }
        assert cut == closest_source_cut(
            vector, case.pattern.excluded_nodes, case.pattern.excluded_links
        )
        assert (
            sum(
                capacity
                for link, direction, _, _, capacity, _ in EDGES
                if (link, direction) in cut
            )
            == optimum
        )
        assert row.cost_distribution.kind == "marginal_curve"
        assert sum(bin.units for bin in row.cost_distribution.bins) == optimum
        assert (
            sum(bin.units * bin.marginal_cost for bin in row.cost_distribution.bins)
            == cost
        )
    finite = capacity(
        context,
        CapacityQuery(
            Selector("^a$"),
            Selector("^t$"),
            offer=1,
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=True, min_cut=True),
        ),
    )
    (row,) = finite.cases[0].states["converged"].rows
    assert row.result.delivered == 1 and row.result.total_cost == 3
    assert row.result.min_cut is None
    assert (
        finite.question == "fixed_offer_delivery" and finite.offer_source == "explicit"
    )
    assert row.cost_distribution is None and not row.unavailable_outputs


def test_matrix_one_native_batch_per_case_and_diagonal_rows_are_domain_values(
    monkeypatch,
):
    context = prepared()
    calls = []
    original = ngc.evaluate_pairs

    def batch(graph, pairs, options, **kwargs):
        calls.append(tuple(pairs))
        return original(graph, pairs, options, **kwargs)

    monkeypatch.setattr(ngc, "evaluate_pairs", batch)
    monkeypatch.setattr(
        ngc,
        "evaluate_demand",
        lambda *args, **kwargs: pytest.fail("matrix used a scalar Python loop"),
    )
    result = capacity(
        context,
        CapacityQuery(
            Selector(".*", group_by="name"),
            Selector(".*", group_by="name"),
            mode="pairwise",
            workers=2,
        ),
    )
    rows = result.cases[0].states["converged"].rows
    assert len(calls) == 1 and len(calls[0]) == 6
    assert len(rows) == 9
    assert [row.id for row in rows] == [f"pair-{i:06d}" for i in range(9)]
    assert [row.node for row in rows if isinstance(row, SelfPair)] == ["a", "b", "t"]
    assert all(row.capacity_units == 0 for row in rows if isinstance(row, SelfPair))
    assert [
        row.capacity_units if isinstance(row, SelfPair) else row.result.delivered
        for row in rows
    ] == [0, 4, 5, 4, 0, 4, 5, 4, 0]


def test_sensitivity_keeps_signed_improvements_and_one_native_baseline(monkeypatch):
    network = Network()
    for name in ("a", "b", "t"):
        network.add_node(Node(name))
    network.add_link(Link("a", "t", 1, 1))
    network.add_link(Link("b", "t", 10, 3))
    context = prepare_network(network)
    topology = context.topology
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.EQUAL)
    )
    original = ngc.evaluate_edge_failures
    calls = []

    def evaluate(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(ngc, "evaluate_edge_failures", evaluate)
    monkeypatch.setattr(
        ngc,
        "evaluate_demand",
        lambda *args, **kwargs: pytest.fail("sensitivity solved a second baseline"),
    )
    result = edge_sensitivity(
        context,
        SensitivityQuery(
            Selector("^[ab]$"),
            Selector("^t$"),
            config,
            workers=2,
            outputs=ngc.OutputOptions(edge_flows=True),
        ),
    )
    assert len(calls) == 1
    assert result.result.baseline.delivered == 2
    assert result.result.baseline.total_cost == 4
    assert (
        result.result.baseline.by_source[0].delivered
        == result.result.baseline.by_source[1].delivered
        == 1
    )
    signed = {
        (
            topology.edge_refs[entry.edge].link,
            topology.edge_refs[entry.edge].direction,
        ): entry.delivery_reduction
        for entry in result.result.entries
    }
    assert signed == {
        ("a|t|0", "forward"): -8,
        ("b|t|0", "forward"): 1,
        ("a|t|0", "reverse"): 0,
        ("b|t|0", "reverse"): 0,
    }
    assert {edge: value for edge, value in signed.items() if value} == {
        ("a|t|0", "forward"): -8,
        ("b|t|0", "forward"): 1,
    }
    assert result.query.offer is None and result.question == "lossless_bound"


def test_sensitivity_node_and_directed_masks_have_independent_expected_values():
    context = prepared()
    topology = context.topology
    config = CapacityQuery(Selector("^a$"), Selector("^t$")).config
    forward, reverse = topology.edges_by_link["a|t|0"]
    for mask, expected in (
        (eligibility(topology, excluded_nodes=["b"]), 3),
        (topology.graph.eligibility(excluded_edges=[forward]), 2),
    ):
        result = edge_sensitivity(
            context,
            SensitivityQuery(
                Selector("^a$"), Selector("^t$"), config, eligibility=mask, workers=1
            ),
        )
        assert result.result.baseline.delivered == expected
        assert result.result.baseline.total_cost == (15 if expected == 3 else 6)
    assert topology.graph.eligibility(excluded_edges=[forward]).edge_allowed()[reverse]


def test_deleting_a_zero_capacity_member_improves_a_fixed_offer():
    # s->t over parallel cost-1 links of capacity 0 and 10; ECMP LOSSY at the fixed offer
    # 10, q = 1. Baseline: 5 offered to each link, the zero link drops its 5, 5 delivered.
    # Deleting the zero link puts all 10 on the other: reduction 5 - 10 = -5. Deleting the
    # 10 link leaves nothing: reduction 5. Reverse edges carry nothing: reduction 0.
    import io
    import json

    from ngraph.export import write_json

    network = Network()
    for name in ("s", "t"):
        network.add_node(Node(name))
    network.add_link(Link("s", "t", 0, 1))
    network.add_link(Link("s", "t", 10, 1))
    context = prepare_network(network)
    config = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(allocation=ngc.RouteAllocation.EQUAL),
        admission=ngc.Admission.LOSSY,
    )
    analysis = edge_sensitivity(
        context,
        SensitivityQuery(Selector("^s$"), Selector("^t$"), config, offer=10, workers=1),
    )
    refs = context.topology.edge_refs
    assert analysis.result.baseline.delivered == 5
    assert {
        (refs[e.edge].link, refs[e.edge].direction): e.delivery_reduction
        for e in analysis.result.entries
    } == {
        ("s|t|0", "forward"): -5,
        ("s|t|1", "forward"): 5,
        ("s|t|0", "reverse"): 0,
        ("s|t|1", "reverse"): 0,
    }
    output = io.StringIO()
    write_json(analysis, output)
    entries = json.loads(output.getvalue())["analysis"]["entries"]
    assert [(e["edge"]["link"], e["delivery_reduction_units"]) for e in entries] == [
        ("s|t|0", -5),
        ("s|t|1", 5),
    ]


def test_an_exact_native_total_above_2_53_reaches_rows_and_json_as_integers():
    # At q = 1/2: A->T twice (capacities 2^52 and 0.5, 2^53 and 1 units) and B->T 1 (2
    # units). The unrestricted maximum flow from both sources saturates every link: A
    # delivers 2^53 + 1, B 2, in all 2^53 + 3. Neither 2^53 + 1 nor 2^53 + 3 is a binary64
    # value, so a per-source or total amount passed through a float would differ.
    import io
    import json

    from ngraph.export import write_json

    network = Network()
    for name in ("A", "B", "T"):
        network.add_node(Node(name))
    network.add_link(Link("A", "T", 2**52, 1))
    network.add_link(Link("A", "T", 0.5, 1))
    network.add_link(Link("B", "T", 1, 1))
    context = prepare_network(network, q=0.5)
    analysis = capacity(
        context,
        CapacityQuery(
            Selector("^[AB]$"), Selector("^T$"), workers=1, export_details=True
        ),
    )
    (row,) = analysis.cases[0].states["converged"].rows
    assert row.result.delivered == 2**53 + 3 and type(row.result.delivered) is int
    names = context.topology.node_names
    assert [(names[s.source], s.delivered) for s in row.result.by_source] == [
        ("A", 2**53 + 1),
        ("B", 2),
    ]
    output = io.StringIO()
    write_json(analysis, output)
    (wire,) = json.loads(output.getvalue())["analysis"]["cases"][0]["states"][
        "converged"
    ]["rows"]
    assert wire["result"]["delivered_units"] == 2**53 + 3
    assert [s["delivered_units"] for s in wire["result"]["by_source"]] == [2**53 + 1, 2]
