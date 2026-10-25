"""Python allocation/publication failures release every native owner before retry."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, get_ident

import netgraph_core as ngc
import pytest

from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare
from tests.placement_fixture import network_of

BOUNDARIES = (
    ("netgraph_core", "FlowPolicy", 3, False),
    ("netgraph_core", "Replace", 3, False),
    ("netgraph_core", "apply_actions", 1, True),
    ("policy", "records", 3, False),
    ("ngraph.analysis.placement", "PlacementRow", 3, False),
    ("ngraph.analysis.costs", "cost_distribution", 3, False),
    ("ngraph.analysis.placement", "placement_miss", 1, False),
    ("ngraph.analysis.placement", "placement_inputs", 1, False),
    ("ngraph.analysis.placement", "placement_inputs", 1, True),
    ("ngraph.analysis.placement", "placement_totals", 1, False),
    ("ngraph.analysis.placement", "CaseState", 1, False),
    ("ngraph.analysis.placement", "CaseResult", 1, False),
    ("ngraph.analysis.placement", "analysis_metadata", 1, False),
    ("ngraph.analysis.placement", "PlacementAnalysis", 1, False),
    ("ngraph.analysis.placement", "schedule_cases", 1, True),
)


def _prepared():
    network = network_of(
        [("S", "R", 12, 1), ("R", "T", 12, 2)], nodes=tuple(f"N{i}" for i in range(6))
    )
    shortest = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    tunnels = ngc.FlowPolicyConfig(routing=ngc.DistributedTE(ngc.TunnelCount(1)))
    specs = tuple(
        DemandSpec(
            Selector("^S$"),
            Selector("^T$"),
            2,
            shortest if index < 8 else tunnels,
            id=f"owner-{index:02}",
        )
        for index in range(16)
    )
    return prepare(
        Scenario(
            network,
            demand_sets={"load": DemandSet("load", specs)},
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )


def _assert_answer(value):
    assert len(value.cases) >= 3
    assert sum(case.case.occurrences for case in value.cases) == 64
    for case in value.cases:
        state = case.states["converged"]
        assert [row.id for row in state.rows] == [
            f"owner-{index:02}|0" for index in range(16)
        ]
        assert [row.result.delivered for row in state.rows] == [2] * 6 + [0] * 10
        assert state.totals.reference_request_units == 32
        assert state.totals.delivered_units == 12
        assert state.totals.reference_shortfall_units == 20
        assert state.totals.source_drop_units == state.totals.edge_drop_units == 0
        assert not state.totals.feasible


@pytest.mark.parametrize("boundary", BOUNDARIES, ids=lambda row: row[0] + "." + row[1])
@pytest.mark.parametrize("warm", [False, True], ids=["cold", "grown"])
@pytest.mark.parametrize("workers", [1, 2])
def test_publication_fault_cleanup_and_retry(boundary, warm, workers, monkeypatch):
    prepared = _prepared()
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("node", mode="choice", path="^N")])]
    )
    query = PlacementQuery(
        prepared.demand_sets["load"],
        failures=FailureRequest(policy, 64, 42),
        workers=workers,
        outputs=ngc.OutputOptions(edge_flows=True, edge_reservations=True),
        export_cost_distribution=True,
    )
    original_ledger, original_policy, original_apply = (
        ngc.FlowLedger,
        ngc.FlowPolicy,
        ngc.apply_actions,
    )
    ledgers, owners, snapshots, published, threads = [], [], [], [], []
    lock = Lock()

    def ledger(*args, **kwargs):
        value = original_ledger(*args, **kwargs)
        ledgers.append(value)
        return value

    def owner(*args, **kwargs):
        value = original_policy(*args, **kwargs)
        owners.append(value)
        return value

    def apply(*args, **kwargs):
        value = original_apply(*args, **kwargs)
        snapshots.extend(value)
        return value

    monkeypatch.setattr(ngc, "FlowLedger", ledger)
    monkeypatch.setattr(ngc, "FlowPolicy", owner)
    monkeypatch.setattr(ngc, "apply_actions", apply)

    def invoke():
        threads.append(get_ident())
        value = place(prepared, query)
        published.append(value)
        return value

    module_name, name, ordinal, after = boundary
    target = (
        original_policy
        if module_name == "policy"
        else importlib.import_module(module_name)
    )
    original = getattr(target, name)
    calls, fired = 0, False

    def fail(*args, **kwargs):
        nonlocal calls, fired
        with lock:
            calls += 1
            inject = calls == ordinal
            if inject:
                fired = True
        if inject and not after:
            raise MemoryError("publication:" + name)
        value = original(*args, **kwargs)
        if inject:
            raise MemoryError("publication:" + name)
        return value

    # One outer thread survives warm-up, failure and retry. With workers1 the
    # native caller/scratch thread is identical throughout. With workers2 each
    # public call additionally exercises cleanup across independent case workers.
    with ThreadPoolExecutor(max_workers=1) as executor:
        if warm:
            _assert_answer(executor.submit(invoke).result(timeout=30))
        count_before = len(published)
        with monkeypatch.context() as patch:
            patch.setattr(target, name, fail)
            with pytest.raises(MemoryError, match="publication:" + name):
                executor.submit(invoke).result(timeout=30)
        assert fired and calls >= ordinal
        assert len(published) == count_before
        assert all(
            not any(value.carried()) and not any(value.reserved()) for value in ledgers
        )
        assert all(value.program is None and value.records() == [] for value in owners)
        _assert_answer(executor.submit(invoke).result(timeout=30))
    assert len(set(threads)) == 1
    assert ledgers and owners and snapshots
    assert all(
        not any(value.carried()) and not any(value.reserved()) for value in ledgers
    )
    assert all(value.program is None and value.records() == [] for value in owners)
    # Captured native result arrays remain valid after every owner is removed.
    assert any(value.delivered == 2 for value in snapshots)
    for value in snapshots:
        assert value.edge_flows is not None and value.edge_reservations is not None
        assert sum(int(amount) for amount in value.edge_flows) == 2 * value.delivered


def test_each_case_places_on_its_own_ledger_with_workers_equal_to_one(monkeypatch):
    # Cases are independent questions: one private ledger per case and state, never one
    # ledger reused across the cases a worker runs (results would not show it: every
    # owner is removed after its case).
    from ngraph.analysis import placement

    network = network_of([("S", "T", 4, 1), ("S", "R", 4, 1), ("R", "T", 4, 1)])
    prepared = prepare(
        Scenario(
            network,
            demand_sets={
                "load": DemandSet(
                    "load", (DemandSpec(Selector("^S$"), Selector("^T$"), 6),)
                )
            },
            units=UnitsSettings(1),
        ),
        demand_sets=("load",),
    )
    failures = FailureRequest(
        FailurePolicy(
            modes=[FailureMode(1, [FailureRule("link", mode="choice", count=1)])]
        ),
        30,
        7,
    )
    real = ngc.FlowLedger
    created = []
    lock = Lock()

    def ledger(graph):
        value = real(graph)
        with lock:
            created.append((get_ident(), value))
        return value

    monkeypatch.setattr(placement.ngc, "FlowLedger", ledger)

    def answers(workers):
        created.clear()
        result = place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["load"], failures=failures, workers=workers
            ),
        )
        return result, [
            (c.case.id, [r.result.delivered for r in c.states["converged"].rows])
            for c in result.cases
        ]

    serial, serial_rows = answers(1)
    assert len(serial.cases) == 4  # baseline and each of the three single-link failures
    assert len(created) == 4 and len({id(v) for _, v in created}) == 4
    parallel, parallel_rows = answers(3)
    assert len(created) == 4 and len({id(v) for _, v in created}) == 4
    assert parallel_rows == serial_rows
