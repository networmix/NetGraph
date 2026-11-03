"""Native result selection across analyses, independent of JSON detail selection."""

import gc
from dataclasses import replace
from fractions import Fraction

import netgraph_core as ngc
import numpy as np
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    Link,
    MSDQuery,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    SensitivityQuery,
    TunnelCountQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    maximum_supported_demand,
    place,
    prepare,
    tunnel_counts,
)
from tests.results.test_analysis_wire import project


def prepared(model=None, *, volume=4, capacity_=10):
    network = Network(nodes={n: Node(n) for n in ("s", "t")})
    network.add_link(Link("s", "t", capacity_, 3))
    return prepare(
        Scenario(
            network,
            demand_sets={
                "d": DemandSet(
                    "d",
                    (
                        DemandSpec(
                            Selector("^s$"),
                            Selector("^t$"),
                            volume,
                            ngc.FlowPolicyConfig(routing=model or ngc.ShortestPaths()),
                        ),
                    ),
                )
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )


def values(value):
    """Fold every property of native records, including nested tunnel plans."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Fraction):
        return (value.numerator, value.denominator)
    if hasattr(value, "name"):
        return value.name
    properties = [k for k, v in vars(type(value)).items() if isinstance(v, property)]
    if properties:
        return {k: values(getattr(value, k)) for k in properties}
    return tuple(values(v) for v in value)


def run_query(kind, selected, details):
    model = (
        ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.OPTIMIZED,
            tunnel_count=ngc.TunnelCount(1),
        )
        if kind == "counts"
        else ngc.ShortestPaths()
    )
    prep = prepared(model)
    demands = prep.demand_sets["d"]
    if kind == "capacity_pinned":
        ledger = ngc.FlowLedger(prep.topology.graph)
        owner = ngc.FlowPolicy(
            ledger,
            [prep.topology.node_id_by_name["s"]],
            [prep.topology.node_id_by_name["t"]],
            ngc.FlowPolicyConfig(routing=model),
        )
        owner.replace(4)
        program = owner.program
        assert program is not None
        owner.remove()
        model = ngc.Pinned(program)
    if kind.startswith("placement"):
        analysis = place(
            prep,
            PlacementQuery(
                demands,
                outputs=selected,
                export_details=details,
                workers=1,
                interaction="simultaneous"
                if kind.endswith("simultaneous")
                else "ordered",
            ),
        )
        results = [analysis.cases[0].states["converged"].rows[0].result]
        expected = [4]
    elif kind.startswith("capacity"):
        analysis = capacity(
            prep,
            CapacityQuery(
                Selector("^s$"),
                Selector("^t$"),
                ngc.FlowPolicyConfig(routing=model),
                offer=4,
                mode="pairwise" if kind == "capacity_pairs" else "combine",
                outputs=selected,
                export_details=details,
                workers=1,
            ),
        )
        results = [analysis.cases[0].states["converged"].rows[0].result]
        expected = [4]
    elif kind == "msd":
        analysis = maximum_supported_demand(
            prep,
            MSDQuery(
                demands,
                alpha_max=4,
                alpha_tolerance=0.01,
                export_probe_rows=True,
                outputs=selected,
                export_details=details,
            ),
        )
        assert analysis.best_rows is not None and analysis.probe_rows is not None
        results = [analysis.best_rows[0].result] + [
            row.result for rows in analysis.probe_rows.values() for row in rows
        ]
        assert analysis.best_rows[0].result.delivered == 10
        expected = [10] + [
            min(10, probe.totals.reference_request_units) for probe in analysis.history
        ]
    elif kind == "sensitivity":
        analysis = edge_sensitivity(
            prep,
            SensitivityQuery(
                Selector("^s$"),
                Selector("^t$"),
                ngc.FlowPolicyConfig(routing=model),
                outputs=selected,
                export_details=details,
                workers=2,
            ),
        )
        results = [analysis.result.baseline]
        expected = [10]
    else:
        analysis = tunnel_counts(
            prep,
            TunnelCountQuery(
                demands,
                (1, 2),
                design_demand=4,
                offer=4,
                up_to=2,
                outputs=selected,
                export_details=details,
                workers=2,
            ),
        )
        results = [r.result for r in analysis.rows]
        expected = [4, 4, 4]
        assert all(r.plan is not None and r.by_tunnel for r in results)
    assert [r.delivered for r in results] == expected
    return analysis, results


@pytest.mark.parametrize(
    "kind",
    [
        "placement",
        "placement_simultaneous",
        "capacity",
        "capacity_pairs",
        "capacity_pinned",
        "msd",
        "sensitivity",
        "counts",
    ],
)
@pytest.mark.parametrize("details", [False, True])
@pytest.mark.parametrize(
    "edge_flag",
    [
        None,
        "edge_flows",
        "residual",
        "edge_reservations",
        "saturated_boundary_edges",
        "min_cut",
        "all",
    ],
)
def test_all_four_native_requests_and_details(kind, details, edge_flag):
    common = None
    held = []
    for program, by_source in (
        (False, False),
        (True, False),
        (False, True),
        (True, True),
    ):
        selected = ngc.OutputOptions(
            program=program,
            by_source=by_source,
            edge_flows=edge_flag in ("edge_flows", "all"),
            residual=edge_flag in ("residual", "all"),
            edge_reservations=edge_flag in ("edge_reservations", "all"),
            saturated_boundary_edges=edge_flag in ("saturated_boundary_edges", "all"),
            min_cut=edge_flag in ("min_cut", "all"),
        )
        analysis, results = run_query(kind, selected, details)
        assert analysis.outputs.native is selected
        wire = project(analysis)["analysis"]["outputs"]["native"]
        assert wire == {
            name: getattr(selected, name)
            for name in (
                "program",
                "by_source",
                "edge_flows",
                "residual",
                "edge_reservations",
                "saturated_boundary_edges",
                "min_cut",
            )
        }
        snapshots = []
        for result in results:
            assert (result.program is not None) == program
            assert (result.by_source is not None) == (by_source or details)
            full = values(result)
            if by_source or details:
                (source,) = result.by_source
                assert source.delivered == result.delivered
            snapshots.append(
                {k: v for k, v in full.items() if k not in ("program", "by_source")}
            )
            held.append((result, full))
        if common is None:
            common = snapshots
        else:
            assert snapshots == common
    gc.collect()
    assert all(values(result) == snapshot for result, snapshot in held)


@pytest.mark.parametrize(
    "model,program,source",
    [
        (ngc.ShortestPaths(), False, True),
        (ngc.DistributedTE(ngc.TunnelCount(1)), True, False),
        (ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.EQUAL), True, False),
        (
            ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
            False,
            False,
        ),
        (
            ngc.CentralizedTE(
                source_allocation=ngc.SourceAllocation.OPTIMIZED,
                tunnel_count=ngc.TunnelCount(1),
            ),
            True,
            False,
        ),
    ],
)
def test_cost_reports_request_only_the_fields_they_read(model, program, source):
    prep = prepared(model)
    config = prep.demand_sets["d"].demands[0].config
    for function, query in (
        (
            place,
            PlacementQuery(
                prep.demand_sets["d"], workers=1, export_cost_distribution=True
            ),
        ),
        (
            capacity,
            CapacityQuery(
                Selector("^s$"),
                Selector("^t$"),
                config,
                offer=4,
                design_demand=4
                if program
                and not (
                    isinstance(model, ngc.CentralizedTE) and model.tunnel_count is None
                )
                else None,
                workers=1,
                export_cost_distribution=True,
            ),
        ),
    ):
        analysis = function(prep, query)
        row = analysis.cases[0].states["converged"].rows[0]
        assert row.result.delivered == 4
        assert row.cost_distribution is not None
        assert not row.unavailable_outputs
        assert (row.result.by_source is not None) == source
        assert (row.result.program is not None) == (program and function is capacity)
        assert (
            not analysis.outputs.native.program
            and not analysis.outputs.native.by_source
        )
        bins = row.cost_distribution.bins
        assert (
            sum(getattr(b, "delivered_units", getattr(b, "units", 0)) for b in bins)
            == 4
        )
        project(analysis)


def test_msd_outputs_validation_and_python_workflow():
    from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand

    prep = prepared()
    selected = ngc.OutputOptions(program=True, by_source=True)
    step = MaximumSupportedDemand(name="msd", demand_set="d", outputs=selected)
    assert step.query(prep.demand_sets["d"]).outputs is selected
    for value in (None, {}, True):
        with pytest.raises(
            TypeError, match="msd.outputs: expected native OutputOptions"
        ):
            MSDQuery(prep.demand_sets["d"], outputs=value)
    original = MSDQuery(prep.demand_sets["d"])
    assert replace(original, outputs=selected).outputs is selected


@pytest.mark.parametrize("interaction", ["ordered", "simultaneous"])
@pytest.mark.parametrize(
    "states", [("converged", "stale", "repair"), ("stale", "repair")]
)
@pytest.mark.parametrize(
    "program,by_source", [(False, False), (True, False), (False, True), (True, True)]
)
def test_replay_baseline_uses_live_programs(interaction, states, program, by_source):
    from tests.analysis.test_failure_states import (
        BY,
        demand,
        links_failing,
    )
    from tests.analysis.test_failure_states import (
        prepared as failure_prepared,
    )

    prep = failure_prepared(BY, [demand("^S$", "^T$", 10)])
    result = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"],
            workers=2,
            interaction=interaction,
            states=states,
            failures=links_failing(r"^S\|T$"),
            outputs=ngc.OutputOptions(program=program, by_source=by_source),
        ),
    )
    for case in result.cases:
        for state, value in case.states.items():
            native = value.rows[0].result
            expected = 10 if case.case.kind == "baseline" or state == "converged" else 0
            assert native.delivered == value.totals.delivered_units == expected
            assert (native.program is not None) is program
            assert (native.by_source is not None) is by_source
            if by_source:
                assert sum(s.delivered for s in native.by_source) == expected
    project(result)


def test_shortest_report_never_materializes_records(monkeypatch):
    def forbidden(*args):
        raise AssertionError("cost report materialized records")

    monkeypatch.setattr(ngc.FlowPolicy, "records", forbidden)
    prep = prepared()
    result = place(
        prep,
        PlacementQuery(
            prep.demand_sets["d"],
            workers=1,
            export_cost_distribution=True,
        ),
    )
    native = result.cases[0].states["converged"].rows[0]
    assert [(b.cost, b.delivered_units) for b in native.cost_distribution.bins] == [
        (3, 4)
    ]
    assert native.result.program is None


def test_baseline_capture_failure_releases_live_owners(monkeypatch):
    from ngraph.analysis.states import Baseline

    prep = prepared()
    real_policy = ngc.FlowPolicy
    owners = []

    def policy(*args):
        owner = real_policy(*args)
        owners.append(owner)
        return owner

    def fail(cls, state, demands, policies):
        assert all(p.program is not None for p in policies)
        raise MemoryError("baseline capture")

    monkeypatch.setattr(ngc, "FlowPolicy", policy)
    monkeypatch.setattr(Baseline, "of", classmethod(fail))
    with pytest.raises(MemoryError, match="baseline capture"):
        place(prep, PlacementQuery(prep.demand_sets["d"], states=("stale",)))
    assert owners and all(p.program is None and p.records() == [] for p in owners)
    monkeypatch.undo()
    valid = place(prep, PlacementQuery(prep.demand_sets["d"], states=("stale",)))
    assert valid.cases[0].states["stale"].rows[0].result.delivered == 4


@pytest.mark.parametrize("kind", ["placement", "capacity"])
def test_unequal_source_amounts_use_static_costs_not_hop_counts(kind):
    network = Network(nodes={n: Node(n) for n in ("s0", "s1", "x", "t")})
    for a, b, cost in (("s0", "t", 1), ("s1", "x", 1), ("x", "t", 2)):
        network.add_link(Link(a, b, 30, cost))
    prep = prepare(
        Scenario(
            network,
            units=UnitsSettings(1),
            demand_sets={
                "d": DemandSet(
                    "d", (DemandSpec(Selector("^s[01]$"), Selector("^t$"), 21),)
                )
            },
        ),
        demand_sets=("d",),
    )
    if kind == "placement":
        result = place(
            prep, PlacementQuery(prep.demand_sets["d"], export_cost_distribution=True)
        )
    else:
        result = capacity(
            prep,
            CapacityQuery(
                Selector("^s[01]$"),
                Selector("^t$"),
                ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
                offer=21,
                export_cost_distribution=True,
            ),
        )
    row = result.cases[0].states["converged"].rows[0]
    assert [(b.cost, b.delivered_units) for b in row.cost_distribution.bins] == [
        (1, 11),
        (3, 10),
    ]
    assert row.result.program is None
    assert [s.delivered for s in row.result.by_source] == [11, 10]


@pytest.mark.parametrize(
    "selected", [ngc.OutputOptions(), ngc.OutputOptions(by_source=True, program=True)]
)
def test_wide_totals_keep_exact_requested_and_unadmitted_units(selected):
    network = Network(nodes={n: Node(n) for n in ("s", "t")})
    network.add_link(Link("s", "t", 2**60, 1))
    prep = prepare(
        Scenario(
            network,
            units=UnitsSettings(1),
            demand_sets={
                "d": DemandSet(
                    "d",
                    tuple(
                        DemandSpec(Selector("^s$"), Selector("^t$"), 2**61, id=f"d{i}")
                        for i in range(9)
                    ),
                )
            },
        ),
        demand_sets=("d",),
    )
    result = place(prep, PlacementQuery(prep.demand_sets["d"], outputs=selected))
    state = result.cases[0].states["converged"]
    assert state.totals.reference_request_units == 9 * 2**61
    assert state.totals.delivered_units == 2**60
    assert state.totals.unadmitted_units == 17 * 2**60
    assert [r.result.delivered for r in state.rows] == [2**60] + [0] * 8
    assert result.units_report.q == 1
    project(result)


def test_missing_source_rows_refuse_inconsistent_report_and_export_requests():
    from ngraph.analysis.costs import cost_distribution

    prep = prepared()
    query = PlacementQuery(prep.demand_sets["d"], workers=1)
    compact = place(prep, query)
    native = compact.cases[0].states["converged"].rows[0].result
    assert native.by_source is None
    project(compact)
    inconsistent = replace(compact, outputs=replace(compact.outputs, details=True))
    with pytest.raises(ValueError, match="^details: source rows were not requested$"):
        project(inconsistent)
    with pytest.raises(
        ValueError,
        match="^cost_distribution: shortest-path source rows were not requested$",
    ):
        cost_distribution(
            prep.topology,
            prep.demand_sets["d"].demands[0].config,
            native,
            [prep.topology.node_id_by_name["t"]],
            prep.topology.disabled,
        )
    valid = place(
        prep, replace(query, export_details=True, export_cost_distribution=True)
    )
    row = valid.cases[0].states["converged"].rows[0]
    assert row.result.by_source[0].delivered == 4
    assert [(b.cost, b.delivered_units) for b in row.cost_distribution.bins] == [(3, 4)]
    project(valid)
