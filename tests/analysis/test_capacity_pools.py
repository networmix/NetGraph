"""Capacity questions pool combined sources under TE presets, as placement does."""

import io
import json

import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
    run,
    write_json,
)
from ngraph.model.demand import PRESETS
from ngraph.workflow.max_flow_step import MaxFlow

TE16 = FlowPolicyPreset.TE_ECMP_16_LSP


def network():
    # a1 -> t (10) and a2 -> t (6): 16 equal tunnels from one private head.
    value = Network(nodes={name: Node(name) for name in ("a1", "a2", "t")})
    value.add_link(Link("a1", "t", 10, 1))
    value.add_link(Link("a2", "t", 6, 1))
    return value


def ask(preset=TE16, **fields):
    return MaxFlow(
        name="m",
        source=Selector("^a"),
        target=Selector("^t$"),
        preset=preset,
        workers=1,
        **fields,
    )


def test_a_te_preset_over_combined_sources_asks_its_private_pool():
    prepared = prepare(Scenario(network(), (ask(),), units=UnitsSettings(1)))
    row = run(prepared).steps[0].result.cases[0].states["converged"].rows[0]
    # Ten tunnels of one unit through a1 and six through a2: 16 units; any
    # other split of 16 equal tunnels carries less (e.g. 8 + 8 gives 12).
    assert row.result.delivered == 16
    assert row.pool.head.pool_id == "workflow.m.pair[0]"
    assert row.pool.head.physical_sources == ("a1", "a2")
    # Preparation observes one head (node 3, after a1, a2 and t) splitting
    # the delivered 16 units over its 16 tunnels; no source split.
    assert prepared.topology.pool_heads == {"workflow.m.pair[0]": 3}


def test_a_pooled_capacity_row_exports_its_pool_and_cost_domain():
    step = ask(export_cost_distribution=True)
    result = run(prepare(Scenario(network(), (step,), units=UnitsSettings(1))))
    output = io.StringIO()
    write_json(result, output)
    row = json.loads(output.getvalue())["steps"][0]["result"]["cases"][0]["states"][
        "converged"
    ]["rows"][0]
    assert row["pool"] == {
        "head": {"pool_id": "workflow.m.pair[0]", "physical_sources": ["a1", "a2"]},
        "offer_limit_units": 0,
        "synthetic_ingress_cost": 1,
    }
    report = row["cost_distribution"]
    assert report["cost_domain"] == "analysis_graph"
    # Every unit pays the cost-1 ingress and one cost-1 link.
    assert report["bins"] == [
        {"cost": 2, "physical_path_cost": 1, "delivered_units": 16}
    ]


def test_a_single_source_is_a_pool_too_and_other_presets_are_not():
    single = network()
    single.replace_link("a1|t|0", capacity=32)
    prepared = prepare(
        Scenario(
            single,
            (
                MaxFlow(
                    name="one",
                    source=Selector("^a1$"),
                    target=Selector("^t$"),
                    preset=TE16,
                    workers=1,
                ),
                ask(FlowPolicyPreset.TE_MAXFLOW_UNLIM),
            ),
            units=UnitsSettings(1),
        )
    )
    first, second = (
        step.result.cases[0].states["converged"].rows[0] for step in run(prepared).steps
    )
    # 16 tunnels of 2 units through a1; the maximum flow takes 32 + 6.
    assert first.pool.head.pool_id == "workflow.one.pair[0]"
    assert first.result.delivered == 32
    assert second.pool is None and second.result.delivered == 38


def query(source="^a", **fields):
    return CapacityQuery(
        Selector(source),
        Selector("^t$"),
        PRESETS[TE16],
        declaration=TE16,
        workers=1,
        **fields,
    )


def test_a_library_question_uses_a_prepared_pool_of_its_sources():
    load = DemandSet("d", (DemandSpec(Selector("^a"), Selector("^t$"), 4, TE16),))
    prepared = prepare(
        Scenario(network(), demand_sets={"d": load}, units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    row = capacity(prepared, query()).cases[0].states["converged"].rows[0]
    assert row.pool.head.pool_id == "d|0|0" and row.result.delivered == 16
    # The step asking the same sources shares that pool instead of a new one.
    with_step = prepare(
        Scenario(network(), (ask(),), demand_sets={"d": load}, units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    assert set(with_step.topology.pool_heads) == {"d|0|0"}


def test_a_library_question_without_a_prepared_pool_is_refused():
    prepared = prepare(Scenario(network(), units=UnitsSettings(1)))
    with pytest.raises(
        ValueError,
        match=r"^capacity\.pair\[0\]: TE_ECMP_16_LSP over combined sources needs a "
        "pool prepared for them; ask it as a MaxFlow step and prepare again$",
    ):
        capacity(prepared, query())
    # Pairwise questions and a supplied configuration name no pool.
    pairwise = capacity(prepared, query("^(a[12])$", mode="pairwise")).cases[0]
    assert [row.pool for row in pairwise.states["converged"].rows] == [None, None]


def test_a_step_shares_a_pool_only_with_exactly_its_sources():
    # A demand pool over {a1} overlaps the step's {a1, a2} but is not its
    # ingress: the step gets its own pool and its 16 units (10 + 6 tunnels).
    load = DemandSet("d", (DemandSpec(Selector("^a1$"), Selector("^t$"), 1, TE16),))
    prepared = prepare(
        Scenario(network(), (ask(),), demand_sets={"d": load}, units=UnitsSettings(1)),
        demand_sets=("d",),
    )
    assert set(prepared.topology.pool_heads) == {"d|0|0", "workflow.m.pair[0]"}
    row = run(prepared).steps[0].result.cases[0].states["converged"].rows[0]
    assert row.pool.head.pool_id == "workflow.m.pair[0]"
    assert row.result.delivered == 16
