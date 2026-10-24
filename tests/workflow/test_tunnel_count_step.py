"""The TunnelCountAnalysis step: what preparation learns from it, and its YAML.

Resolutions are derived from the recipe's constraints, each q <= bound: input
atoms q <= 2 * precision * x, and split targets q <= precision * y / (r - 1).
"""

import io
from fractions import Fraction

import jsonschema
import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    TunnelCountQuery,
    UnitsSettings,
    prepare,
    run,
    tunnel_counts,
    write_json,
)
from ngraph.analysis import counts
from ngraph.workflow import TunnelCountAnalysis
from ngraph.workflow.parse import build_workflow_steps
from tests.controller.test_owner_figures import ebb_links

LOSSLESS = ngc.Admission.LOSSLESS
P = Fraction(0.001)


def t2(k=1, up_to=False, headroom=False):
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(k, up_to=up_to),
            prefer_headroom=headroom,
        ),
        admission=LOSSLESS,
    )


def network(links):
    names = sorted({u for u, v, *_ in links} | {v for u, v, *_ in links})
    net = Network(nodes={name: Node(name) for name in names})
    for u, v, capacity, *cost in links:
        net.add_link(Link(u, v, capacity, cost[0] if cost else 1))
    return net


def step(name="c", **fields):
    values = {"demand_set": "d", "counts": (4,), "design_demand": 100, "offer": 100}
    return TunnelCountAnalysis(name, **{**values, **fields})


def active(value):
    """Prepare with the demand set active, as a step naming it makes it."""
    return prepare(value, demand_sets=("d",))


def scenario(links, specs, steps=(), q="auto"):
    return Scenario(
        network(links),
        steps,
        demand_sets={"d": DemandSet("d", tuple(specs))},
        units=UnitsSettings(q),
    )


TWO_HEADS = [("A", "T", 100), ("B", "T", 100)]


def heads(volume=0, count=1):
    return DemandSpec(Selector("^(A|B)$"), Selector("^T$"), volume, t2(count), id="te")


def test_a_count_step_moves_q_by_its_own_splits_only():
    # The declared set (exact count 1, volume 0) binds nothing: capacities give 2^-3.
    assert active(scenario(TWO_HEADS, [heads()])).topology.q == 1 / 8
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(),)))
    # Rows: sources split 0.001 * 100 / 1; each head's 4 tunnels 0.001 * 50 / 3 -> 2^-6.
    assert prep.topology.q == 1 / 64
    labels = {c.label: c for c in prep.units_report.nominal_splits}
    assert labels["workflow.c.demand[te|0].count[4].sources"].q_upper_bound == P * 100
    head = labels["workflow.c.demand[te|0].count[4].head[0]"]
    assert (head.q_upper_bound, head.members, head.basis) == (P * 50 / 3, 4, "declared")
    # The step's offer and design join the input atoms of the recipe.
    bare = active(scenario(TWO_HEADS, [heads()])).units_report.input_count
    assert prep.units_report.input_count == bare + 2
    inputs = {c.label for c in prep.units_report.binding_constraints}
    assert "workflow.c.demand[te|0].count[4].head[0]" in inputs


EBB_S2 = ebb_links("S2")


def ebb_counts(**fields):
    spec = DemandSpec(
        Selector("^DC_A$"), Selector("^DC_B$"), 2400, t2(1, headroom=True), id="te"
    )
    values = {
        "counts": (8, 16, 24, 32, 48, 64, 96, 128),
        "up_to": 256,
        "design_demand": 2400,
        "offer": 2400,
    }
    return prepare(scenario(EBB_S2, [spec], (step(**{**values, **fields}),)))


def test_count_rows_bind_q_through_their_largest_split():
    spec = DemandSpec(
        Selector("^DC_A$"), Selector("^DC_B$"), 2400, t2(1, headroom=True), id="te"
    )
    # The declared exact count 1 has no tunnel split: link capacities give 2^-4.
    assert active(scenario(EBB_S2, [spec])).topology.q == 1 / 16
    prep = ebb_counts()
    # The up-to row's 256 members bind: 0.001 * 2400 / 255 -> 2^-7.
    assert prep.topology.q == 1 / 128
    binding = [c for c in prep.units_report.binding_constraints if "up_to" in c.label]
    head = prep.topology.node_id_by_name["DC_A"]
    assert [c.label for c in binding] == [
        f"workflow.c.demand[te|0].up_to[256].head[{head}]"
    ]
    assert binding[0].q_upper_bound == P * 2400 / 255
    assert {c.basis for c in prep.units_report.nominal_splits if ".c." in c.label} == {
        "declared"
    }
    # Without the up-to row, the k = 128 row binds: 0.001 * 2400 / 127 -> 2^-6.
    assert ebb_counts(up_to=None).topology.q == 1 / 64


def test_count_splits_solve_no_traffic_and_search_once_per_leaf(monkeypatch):
    calls = {"evaluate": 0, "searches": 0, "candidates": 0}
    real_pairs, real_demand = ngc.evaluate_pairs, ngc.evaluate_demand
    real_spf, real_splits = ngc.spf, counts.count_splits

    def pairs(*args, **kwargs):
        calls["evaluate"] += 1
        return real_pairs(*args, **kwargs)

    def demand(*args, **kwargs):
        calls["evaluate"] += 1
        return real_demand(*args, **kwargs)

    def search(*args, **kwargs):
        calls["searches"] += 1
        return real_spf(*args, **kwargs)

    def splits(*args, **kwargs):
        calls["candidates"] += 1
        return real_splits(*args, **kwargs)

    monkeypatch.setattr(ngc, "evaluate_pairs", pairs)
    monkeypatch.setattr(ngc, "evaluate_demand", demand)
    monkeypatch.setattr(ngc, "spf", search)
    monkeypatch.setattr(counts, "count_splits", splits)
    leaves = [heads(), DemandSpec(Selector("^A$"), Selector("^T$"), 0, t2(), id="one")]
    assert active(scenario(TWO_HEADS, leaves)).topology.q == 2**-3
    assert calls == {"evaluate": 0, "searches": 0, "candidates": 0}
    prep = prepare(scenario(TWO_HEADS, leaves, (step(counts=(2, 4), up_to=8),)))
    assert calls["evaluate"] == 0
    # The recipe tries each q from the capacities' 2^-3 down to 2^-8 (te's heads at
    # up to 8: 0.001 * 50 / 7), and at each one reverse search per leaf serves all
    # three of its rows: 2 leaves x 6 candidates.
    assert prep.topology.q == 2**-8
    assert (calls["candidates"], calls["searches"]) == (6, 2 * 6)


def library(prep, offer, count=4, **fields):
    return tunnel_counts(
        prep, TunnelCountQuery(prep.demand_sets["d"], (count,), offer, offer, **fields)
    )


def test_a_library_question_outside_what_preparation_declared_misses():
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(),)))
    assert prep.topology.q == 1 / 64
    assert library(prep, 100).misses == ()

    def unmet(analysis):
        (miss,) = analysis.misses
        assert (
            miss.location.step,
            miss.location.case_id,
            miss.location.probe_index,
        ) == (
            None,
            "baseline",
            None,
        )
        return sorted(c.label for c in miss.constraints)

    # O = D = 10: sources 0.001 * 10 and heads 0.001 * 5 / 3 are below q = 1/64.
    assert unmet(library(prep, 10)) == [
        "tunnel_counts.demand[te|0].count[4].head[0]",
        "tunnel_counts.demand[te|0].count[4].head[1]",
        "tunnel_counts.demand[te|0].count[4].sources",
    ]
    # k = 16: heads 0.001 * 50 / 15 are below q; the sources split still meets it.
    assert unmet(library(prep, 100, count=16)) == [
        "tunnel_counts.demand[te|0].count[16].head[0]",
        "tunnel_counts.demand[te|0].count[16].head[1]",
    ]
    # A removed head only raises the other head's share: no miss.
    mask = prep.topology.graph.eligibility(
        excluded_nodes=[prep.topology.node_id_by_name["B"]]
    )
    assert library(prep, 100, eligibility=mask).misses == ()


def test_design_splits_bind_when_the_design_is_below_the_offer():
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(design_demand=10, offer=100),)))
    # Design 10 over heads A, B and 4 tunnels each: 0.001 * 5 / 3 -> 2^-10 (the
    # offer's 0.001 * 50 / 3 alone gives 2^-6).
    assert prep.topology.q == 2**-10
    assert sorted(c.label for c in prep.units_report.binding_constraints) == [
        "workflow.c.demand[te|0].count[4].design.head[0]",
        "workflow.c.demand[te|0].count[4].design.head[1]",
    ]
    # Prepared for D = O = 100 (q = 2^-6), a library D = 10 misses its design splits:
    # heads 0.001 * 5 / 3 and sources 0.001 * 10; the atoms 2 * 0.001 * 10 are met.
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(),)))
    analysis = tunnel_counts(
        prep, TunnelCountQuery(prep.demand_sets["d"], (4,), 10, 100)
    )
    (miss,) = analysis.misses
    assert sorted(c.label for c in miss.constraints if not c.met) == [
        "tunnel_counts.demand[te|0].count[4].design.head[0]",
        "tunnel_counts.demand[te|0].count[4].design.head[1]",
        "tunnel_counts.demand[te|0].count[4].design.sources",
    ]


@pytest.mark.parametrize(
    ("design", "offer", "atom"),
    [(0.001, 1000, "design_demand"), (1000, 0.001, "offer")],
)
def test_the_smaller_amount_binds_its_own_input_atom(design, offer, atom):
    counted = step(counts=(1,), design_demand=design, offer=offer)
    prep = prepare(scenario([("A", "T", 100)], [heads()], (counted,)))
    # One head at count 1 has no split; q <= 2 * 0.001 * 0.001 -> 2^-19.
    assert prep.topology.q == 2**-19
    assert [c.label for c in prep.units_report.binding_constraints] == [
        f"workflow.c.{atom}"
    ]


def test_a_pooled_leaf_splits_at_its_pool_head():
    pooled = DemandSpec(
        Selector("^S[12]$"), Selector("^T$"), 0, FlowPolicyPreset.TE_ECMP_16_LSP, id="p"
    )
    links = [("S1", "X", 100), ("S2", "X", 100), ("X", "T", 200)]
    prep = prepare(scenario(links, [pooled], (step(),)))
    # The pool's private head (node 4, after S1, S2, T, X) is the leaf's one head: its
    # 4 tunnels split 100 at 0.001 * 100 / 3 -> 2^-5, and one head has no sources split.
    assert prep.topology.q == 2**-5
    assert [c.label for c in prep.units_report.binding_constraints] == [
        "workflow.c.demand[p|0].count[4].head[4]"
    ]
    assert {
        c.label: c.q_upper_bound
        for c in prep.units_report.nominal_splits
        if ".c." in c.label
    } == {"workflow.c.demand[p|0].count[4].head[4]": P * 100 / 3}


def test_each_leaf_searches_its_own_heads():
    leaves = [
        DemandSpec(Selector("^A$"), Selector("^T$"), 0, t2(), id="one"),
        DemandSpec(Selector("^(A|B)$"), Selector("^T$"), 0, t2(), id="two"),
    ]
    prep = prepare(scenario(TWO_HEADS, leaves, (step(),)))
    # two's heads A and B: 50 each over 4 tunnels, 0.001 * 50 / 3 -> 2^-6 (one's
    # single head alone: 0.001 * 100 / 3 -> 2^-5).
    assert prep.topology.q == 2**-6
    assert sorted(c.label for c in prep.units_report.binding_constraints) == [
        "workflow.c.demand[two|0].count[4].head[0]",
        "workflow.c.demand[two|0].count[4].head[1]",
    ]
    assert {
        c.label: c.q_upper_bound
        for c in prep.units_report.nominal_splits
        if "[two|" in c.label
    } == {
        "workflow.c.demand[two|0].count[4].head[0]": P * 50 / 3,
        "workflow.c.demand[two|0].count[4].head[1]": P * 50 / 3,
        "workflow.c.demand[two|0].count[4].sources": P * 100,
    }


def test_a_library_miss_keeps_the_query_input_atoms():
    counted = step(counts=(1,), design_demand=10, offer=10)
    prep = prepare(scenario([("A", "T", 100)], [heads()], (counted,)))
    # One head at count 1 has no split; design 10 is met, offer 0.01 needs
    # q <= 2 * 0.001 * 0.01.
    assert prep.topology.q > 2 * 0.001 * 0.01
    analysis = tunnel_counts(
        prep, TunnelCountQuery(prep.demand_sets["d"], (1,), 10, 0.01)
    )
    (miss,) = analysis.misses
    assert [c.label for c in miss.constraints if not c.met] == ["tunnel_counts.offer"]


def test_the_step_is_a_numerical_step_of_the_units_report():
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(),)))
    assert prep.units_report.scope.workflow_steps == ("c",)


def test_a_run_reports_its_count_step_misses_under_the_step():
    prep = prepare(scenario(TWO_HEADS, [heads()], (step(),), q=1 / 8))
    (result,) = run(prep).steps
    (miss,) = result.result.misses
    assert miss.location.case_id == "baseline"
    report_misses = run(prep).units_report.misses
    assert [m.location.step for m in report_misses] == ["c"]


def test_the_declared_set_still_takes_part_in_choosing_q():
    for volume, count, bare, stepped in (
        (1, 16, 2**-15, 2**-15),
        (100, 2, 2**-5, 2**-6),
        (0, 16, 2**-3, 2**-6),
    ):
        assert active(scenario(TWO_HEADS, [heads(volume, count)])).topology.q == bare
        prep = prepare(scenario(TWO_HEADS, [heads(volume, count)], (step(),)))
        assert prep.topology.q == stepped


def test_every_leaf_uses_the_query_design_and_offer():
    specs = [
        DemandSpec(Selector("^A$"), Selector("^T$"), 10, t2(2), id="small"),
        DemandSpec(Selector("^B$"), Selector("^T$"), 1000, t2(2), id="large"),
    ]
    prep = prepare(scenario(TWO_HEADS, specs, (step(counts=(2,)),), q=1))
    rows = run(prep).steps[0].result.rows
    assert [
        (
            r.base_id,
            r.result.requested,
            r.result.plan.design_demand,
            r.result.plan.planned_bandwidth_per_tunnel,
            r.result.delivered,
        )
        for r in rows
    ] == [("small", 100, 100, 50, 100), ("large", 100, 100, 50, 100)]


def test_discarded_shares_have_no_rows():
    spec = DemandSpec(
        Selector("^(A|B)$"), Selector("^(A|B)$"), 10, t2(2), id="pw", mode="pairwise"
    )
    prep = prepare(
        scenario(TWO_HEADS, [spec], (step(counts=(2,), offer=1, design_demand=1),), q=1)
    )
    rows = run(prep).steps[0].result.rows
    assert [(r.endpoints.sources, r.endpoints.destinations) for r in rows] == [
        (("A",), ("B",)),
        (("B",), ("A",)),
    ]
    (accounting,) = prep.demand_sets["d"].accounting
    assert [(d.label, d.units, d.reason) for d in accounting.discards] == [
        ("pw|0", 3, "self_pair"),
        ("pw|3", 2, "self_pair"),
    ]


def test_a_non_tunnelled_set_is_refused_at_preparation():
    spec = DemandSpec(
        Selector("^A$"),
        Selector("^T$"),
        1,
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        id="x",
    )
    with pytest.raises(
        ValueError,
        match=r"^workflow\.c\.demands: demand x\|0: TunnelCountAnalysis needs a "
        r"CentralizedTE model with a tunnel count$",
    ):
        prepare(scenario(TWO_HEADS, [spec], (step(),)))


def test_a_pool_offer_at_the_units_bound_makes_q_coarser_or_is_refused():
    specs = [
        DemandSpec(
            Selector(f"^{s}$"),
            Selector("^T$"),
            0,
            FlowPolicyPreset.TE_ECMP_16_LSP,
            id=i,
        )
        for s, i in (("A", "p"), ("B", "r"))
    ]
    huge = 3.0 * 2**60
    counted = (step(offer=huge, design_demand=1),)
    # Two attachments of 3 * 2^60 units break the 2^62 capacity sum at q = 1; the finest
    # legal resolution is 2, which misses the precision target.
    prep = prepare(scenario(TWO_HEADS, specs, counted))
    report = prep.units_report
    assert (report.q, report.target_met) == (2.0, False)
    assert [d.pool.offer_limit_units for d in prep.demand_sets["d"].demands] == [
        3 * 2**59
    ] * 2
    assert report.augmented_capacity_sum_units < 2**62
    with pytest.raises(
        ValueError, match="^topology.augmented_capacity_sum: no legal resolution"
    ):
        prepare(scenario(TWO_HEADS, specs, counted, q=1))


YAML = """
network:
  nodes: {{A: {{}}, T: {{}}}}
  links:
    - {{source: A, target: T, capacity: 100, cost: 1}}
demands:
  d:
    - {{id: te, source: '^A$', target: '^T$', volume: 0,
       model: {{routing: {{type: centralized_te, source_allocation: equal, tunnel_count: {{per_head: 1}}}},
                admission: lossless}}}}
workflow:
  - type: TunnelCountAnalysis
    name: counts
    demand_set: d
{extra}
"""


def from_yaml(extra):
    return Scenario.from_yaml(YAML.format(extra=extra))


def test_the_yaml_step():
    value = from_yaml(
        "    counts: [4, 2]\n    up_to: 8\n    design_demand: 10\n    offer: 12\n"
        "    workers: 1\n    outputs: {edge_flows: true, details: true}"
    )
    (counted,) = value.workflow
    assert (counted.counts, counted.up_to, counted.design_demand, counted.offer) == (
        (4, 2),
        8,
        10.0,
        12.0,
    )
    assert counted.outputs.edge_flows and counted.export_details
    rows = run(prepare(value)).steps[0].result.rows
    assert [(r.count, r.up_to) for r in rows] == [(4, False), (2, False), (8, True)]


def test_a_yaml_step_without_outputs_exports_no_details():
    value = from_yaml("    counts: [1]\n    design_demand: 1\n    offer: 1")
    (counted,) = value.workflow
    assert counted.export_details is False
    text = io.StringIO()
    write_json(run(prepare(value)), text)
    assert '"by_tunnel"' not in text.getvalue()


def test_yaml_workers_reach_the_native_call(monkeypatch):
    value = Scenario.from_yaml(
        """
network:
  nodes: {A: {}, B: {}, T: {}}
  links:
    - {source: A, target: T, capacity: 100, cost: 1}
    - {source: B, target: T, capacity: 100, cost: 1}
demands:
  d:
    - {id: te, source: '^(A|B)$', target: '^T$', volume: 0, mode: pairwise,
       model: {routing: {type: centralized_te, source_allocation: equal,
                         tunnel_count: {per_head: 1}}}}
workflow:
  - {type: TunnelCountAnalysis, name: counts, demand_set: d, counts: [1],
     design_demand: 1, offer: 1, workers: 4}
"""
    )
    assert value.workflow[0].workers == 4
    prep = prepare(value)
    real = ngc.evaluate_pairs
    calls = []

    def recording(graph, pairs, options, workers=1):
        calls.append((len(pairs), workers))
        return real(graph, pairs, options, workers=workers)

    monkeypatch.setattr(ngc, "evaluate_pairs", recording)
    run(prep)
    # Both leaves share one model: one call of two pairs with the declared workers.
    assert calls == [(2, 4)]


@pytest.mark.parametrize(
    ("fields", "kind", "message"),
    [
        (
            {"counts": (1.5,)},
            ValueError,
            r"tunnel_counts\.counts\[0\]: expected an integer in \[1, 10000\]",
        ),
        (
            {"up_to": True},
            ValueError,
            r"tunnel_counts\.up_to: expected an integer in \[1, 10000\]",
        ),
        (
            {"up_to": 2.0},
            ValueError,
            r"tunnel_counts\.up_to: expected an integer in \[1, 10000\]",
        ),
        (
            {"counts": ()},
            ValueError,
            r"tunnel_counts\.counts: give at least one count or up_to",
        ),
        (
            {"outputs": {}},
            TypeError,
            r"tunnel_counts\.outputs: expected native OutputOptions",
        ),
    ],
)
def test_construction_refusals_name_the_step(fields, kind, message):
    with pytest.raises(kind, match=f"^workflow step c: {message}$") as caught:
        step(**fields)
    assert type(caught.value) is kind
    assert type(caught.value.__cause__) is kind
    assert str(caught.value) == f"workflow step c: {caught.value.__cause__}"


def test_an_unnamed_step_names_itself_by_its_class():
    with pytest.raises(
        ValueError,
        match=r"^workflow step TunnelCountAnalysis: tunnel_counts\.counts: give at "
        r"least one count or up_to$",
    ):
        TunnelCountAnalysis(demand_set="d", counts=(), design_demand=1, offer=1)


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            "    counts: [1]\n    design_demand: 1\n    offer: 1\n    outputs: {cost_distribution: true}",
            "'cost_distribution' was unexpected",
        ),
        (
            "    counts: [1]\n    design_demand: 1\n    offer: 1\n    failure_policy: f",
            "'failure_policy' was unexpected",
        ),
        ("    counts: [1]\n    offer: 1", "'design_demand' is a required property"),
        (
            "    counts: [1, 1]\n    design_demand: 1\n    offer: 1",
            "non-unique elements",
        ),
    ],
)
def test_the_scenario_schema_refuses_what_the_step_does_not_take(extra, message):
    with pytest.raises(jsonschema.ValidationError, match=message):
        from_yaml(extra)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            {"outputs": {"cost_distribution": True}},
            "Unrecognized key\\(s\\) in workflow step counts\\.outputs: cost_distribution",
        ),
        (
            {"failure_policy": "f"},
            "Unrecognized key\\(s\\) in workflow step 'counts': failure_policy",
        ),
        ({"export_details": True}, "unknown key export_details; use outputs.details"),
        ({"counts": 4}, "counts: expected a list of integers"),
        ({"design_demand": None}, "TunnelCountAnalysis.design_demand: required"),
        ({"offer": None}, "TunnelCountAnalysis.offer: required"),
        (
            {"counts": [1, 1]},
            r"^workflow step counts: tunnel_counts\.counts: duplicate count 1$",
        ),
    ],
)
def test_the_step_parser_refusals(fields, message):
    entry = {
        "type": "TunnelCountAnalysis",
        "name": "counts",
        "demand_set": "d",
        "counts": [1],
        "design_demand": 1,
        "offer": 1,
        **fields,
    }
    entry = {key: value for key, value in entry.items() if value is not None}
    with pytest.raises(ValueError, match=message):
        build_workflow_steps([entry], lambda name: None)


def test_a_pool_budget_is_the_largest_known_lossy_offer():
    from ngraph.workflow import TrafficMatrixPlacement

    spec = DemandSpec(
        Selector("^A$"), Selector("^T$"), 300, FlowPolicyPreset.TE_ECMP_16_LSP, id="p"
    )

    def budget(*steps):
        prep = prepare(scenario(TWO_HEADS, [spec], steps, q=1))
        return prep.demand_sets["d"].demands[0].pool.offer_limit_units

    # Count steps: the larger offer, whichever comes first.
    assert budget(step(offer=1000), step("c2", offer=10)) == 1000
    assert budget(step(offer=10), step("c2", offer=1000)) == 1000
    # A simultaneous step's known request (300) against a smaller count offer.
    simultaneous = TrafficMatrixPlacement(
        name="sim", demand_set="d", interaction="simultaneous", alpha=1
    )
    assert budget(simultaneous, step(offer=10)) == 300
    assert budget(simultaneous, step(offer=1000)) == 1000
    # Offer 2.5 at q = 1 rounds half up to 3 units, as the rows' offer does, so the
    # step's own run fits its budget.
    assert budget(step(offer=2.5, design_demand=2)) == 3
    run(prepare(scenario(TWO_HEADS, [spec], (step(offer=2.5, design_demand=2),), q=1)))


def test_the_documented_example_runs_with_its_stated_rows():
    import re
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "docs/reference/workflow.md"
    ).read_text()
    section = text.split("## TunnelCountAnalysis", 1)[1]
    (block,) = re.findall(r"```yaml\n(.*?)```", section.split("\n## ", 1)[0], re.DOTALL)
    rows = run(prepare(Scenario.from_yaml(block))).steps[0].result.rows
    # Pooled S: two tunnels (narrow link, wide link) carry 1 + 100 of 1000; F = 2; cost
    # (1 + 1) + (1 + 2) = 5 on the analysis graph, 3 physical. Up to 3 chooses one
    # tunnel planned at u = 2, which only the wide link fits: 100, cost 1 + 2.
    # Heads a and b (links 2 and 10): two tunnels each, U = 1, F = 4, 2 + 10 delivered;
    # up to 3 chooses one per head (F'(1) = 4 already covers the design 2).
    assert [
        (
            r.base_id,
            r.count,
            r.up_to,
            r.result.plan.tunnels_per_head,
            r.result.delivered,
            r.lossless_at_design_units,
            r.result.plan.total_tunnel_cost,
            r.physical_tunnel_cost,
        )
        for r in rows
    ] == [
        ("pooled", 2, False, 2, 101, 2, 5, 3),
        ("pooled", 3, True, 1, 100, 2, 3, 2),
        ("heads", 2, False, 2, 12, 2, 4, 4),
        ("heads", 3, True, 1, 12, 2, 2, 2),
    ]
