"""Preparation avoids repeated work while retaining input checks and ownership."""

import netgraph_core as ngc
import pytest

import ngraph.analysis.precision as precision
import ngraph.analysis.units as units
from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
)


def network():
    value = Network(
        nodes={name: Node(name, attrs={"owned": [1]}) for name in ("a", "t")}
    )
    value.add_link(Link("a", "t", 1, 3))
    return value


def test_preparation_shares_the_input_records_without_copying_them():
    source = network()
    prepared = prepare(Scenario(source, units=UnitsSettings(1)))
    view = prepared.scenario.network
    assert view is not source and view.nodes is not source.nodes
    assert all(view.nodes[name] is node for name, node in source.nodes.items())
    assert all(view.links[name] is link for name, link in source.links.items())
    with pytest.raises(TypeError, match="read-only"):
        source.nodes["a"].attrs["owned"].append(2)
    source.replace_node("a", attrs={"owned": [1, 2]})
    assert prepared.scenario.network.nodes["a"].attrs["owned"] == [1]
    again = prepare(Scenario(source, units=UnitsSettings(1)))
    assert again.scenario.network.nodes["a"].attrs["owned"] == [1, 2]


def test_complete_input_observations_are_built_once_for_a_manual_candidate(monkeypatch):
    calls = []
    original = units.input_samples

    def observed(inputs, q):
        calls.append(tuple(inputs))
        return original(inputs, q)

    monkeypatch.setattr(units, "input_samples", observed)
    prepared = prepare(Scenario(network(), units=UnitsSettings(1)))
    assert calls == [("link.a|t|0.capacity",)]
    assert prepared.units_report.input_count == 1
    assert prepared.units_report.augmented_capacity_sum_units == 2


def test_input_quantization_skips_coarse_candidates_excluded_by_precision(monkeypatch):
    converted = []
    original = units.quantize

    def observed(value, q, label):
        converted.append(q)
        return original(value, q, label)

    monkeypatch.setattr(units, "quantize", observed)
    load = DemandSet("load", (DemandSpec(Selector("a"), Selector("t"), 0.25),))
    value = prepare(
        Scenario(network(), demand_sets={"load": load}), demand_sets=("load",)
    )
    # Input target: q <= 2*0.001*0.25, so the coarsest legal power is2^-11.
    assert value.topology.q == 2**-11
    assert converted and all(q <= 2**-11 for q in converted)


def test_empty_optimized_split_branch_is_not_visited_but_input_misses_remain(
    monkeypatch,
):
    value = prepare(Scenario(network(), units=UnitsSettings(1)))

    def forbidden(*args, **kwargs):
        raise AssertionError("empty per-pair split check")

    with monkeypatch.context() as patch:
        patch.setattr(precision, "query_splits", forbidden)
        result = capacity(
            value, CapacityQuery(Selector("a"), Selector("t"), offer=0.125, workers=1)
        )
        assert result.cases[0].states["converged"].rows[0].result.delivered == 0
        assert not result.units_report.target_met
        assert any(
            c.label == "capacity.offer"
            for miss in result.units_report.misses
            for c in miss.constraints
        )
        with pytest.raises(AssertionError, match="per-pair"):
            capacity(
                value,
                CapacityQuery(
                    Selector("a"),
                    Selector("t"),
                    config=ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
                    workers=1,
                ),
            )


def test_precision_range_conflict_selects_finest_range_valid_quantum():
    value = network()
    value.replace_link("a|t|0", capacity=float(2**61))
    value.add_link(Link("a", "t", 0.25, 1))
    p = prepare(Scenario(value))
    report = p.units_report
    # The tiny input requires q<=0.0005. At q=1 the two directions of the
    # large link sum to2^62, which is illegal; q=2 sums to2^61 and is legal.
    # No precision-compatible q fits; the finest range-valid fallback is2.
    assert p.topology.q == 2
    assert not report.target_met and report.zeroed_inputs == 1
    assert report.augmented_capacity_sum_units == 2**61
    ranges = [c for c in report.binding_constraints if c.kind == "capacity_sum"]
    assert len(ranges) == 1
    assert (ranges[0].tested_q, ranges[0].units_value, ranges[0].exclusive_limit) == (
        1,
        2**62,
        2**62,
    )
    assert any(
        c.kind == "input" and c.label == "link.a|t|1.capacity" and not c.met
        for c in report.binding_constraints
    )
    value.replace_link("a|t|0", capacity=1e100)
    with pytest.raises(
        ValueError, match="no legal resolution.*complete prepared input"
    ):
        prepare(Scenario(value))
    assert prepare(Scenario(network())).topology.graph.num_edges() == 2


@pytest.mark.parametrize(
    "preset,mode,solves",
    [
        ("TE_MAXFLOW_UNLIM", "pairwise", False),
        ("SHORTEST_PATHS_MAXFLOW", "combine", False),
        ("SHORTEST_PATHS_ECMP", "pairwise", True),
    ],
)
def test_prepare_solves_a_capacity_question_only_for_its_split_checks(
    monkeypatch, preset, mode, solves
):
    from ngraph import FlowPolicyPreset
    from ngraph.workflow.max_flow_step import MaxFlow

    value = Network(nodes={name: Node(name) for name in ("a1", "a2", "t1", "t2")})
    for s in ("a1", "a2"):
        for t in ("t1", "t2"):
            value.add_link(Link(s, t, 3, 1))
    calls = []
    for name in ("evaluate_demand", "evaluate_pairs"):
        original = getattr(ngc, name)

        def observed(graph, *args, original=original, name=name, **kwargs):
            options = args[-1] if name == "evaluate_demand" else args[1]
            pairs = 1 if name == "evaluate_demand" else len(args[0])
            calls.append((pairs, sum(options.eligibility.node_allowed())))
            return original(graph, *args, **kwargs)

        monkeypatch.setattr(ngc, name, observed)
    step = MaxFlow(
        name="cap",
        source=Selector("^(a.)"),
        target=Selector("^(t.)"),
        mode=mode,
        preset=FlowPolicyPreset[preset],
        workers=1,
    )
    prepare(Scenario(value, (step,), units=UnitsSettings(1)))
    if solves:
        assert calls and all(open_nodes == 4 for _, open_nodes in calls)
        assert sum(pairs for pairs, _ in calls) == 4
    else:
        # One native check per candidate quantum, with no eligible node.
        assert calls and all(call == (1, 0) for call in calls)
