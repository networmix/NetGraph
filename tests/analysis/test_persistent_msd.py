"""Persistent alpha probes, exact totals, compact history and native cleanup."""

from fractions import Fraction

import pytest

from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from tests.prepared import prepare_network


def prepared(volume=4, preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP):
    network = Network()
    network.add_node(Node("s"))
    network.add_node(Node("t"))
    network.add_link(Link("s", "t", 4, 3))
    context = prepare_network(network)
    demands = resolve_demands(
        context,
        DemandSet(
            "load", (DemandSpec(Selector("^s$"), Selector("^t$"), volume, preset),)
        ),
    )
    return context, demands


def test_fixed_path_bracket_is_tested_and_not_a_global_rounded_float_optimum(
    monkeypatch,
):
    from ngraph.analysis import msd

    context, demands = prepared()
    original = msd._apply_matrix
    rosters = []
    ledgers = []
    observations = []

    def observe(ledger, policies, requests):
        assert list(ledger.carried()) == [0, 0]
        assert list(ledger.reserved()) == [0, 0]
        ledgers.append(ledger)
        rosters.append(tuple(policies))
        results = original(ledger, policies, requests)
        observations.append(results)
        return results

    monkeypatch.setattr(msd, "_apply_matrix", observe)
    result = maximum_supported_demand(context, MSDQuery(demands, alpha_tolerance=1))
    assert len(result.history) == 2
    assert [row.alpha.value for row in result.history] == [1, 2]
    assert [row.outcome for row in result.history] == ["feasible", "infeasible"]
    assert [row.totals.reference_request_units for row in result.history] == [4, 8]
    assert [row.totals.delivered_units for row in result.history] == [4, 4]
    assert [row.totals.unadmitted_units for row in result.history] == [0, 4]
    assert result.alpha_feasible.value == 1 and result.best_probe_index == 0
    assert result.proof == "fixed_program" and result.monotone_proven
    assert result.search_status == "feasible" and result.stop_reason == "tolerance"
    certificate = result.upper_certificate
    assert certificate.lower.value == 1 and certificate.upper.value == 2
    assert certificate.lower_probe_index == 0 and certificate.upper_probe_index == 1
    assert result.best_rows[0].reference_request_units == 4
    assert result.best_rows[0].result.delivered == 4
    assert result.best_rows[0].result.by_source[0].delivered == 4
    assert result.best_rows[0].result.plan is None
    assert result.best_rows[0].result.min_cut is None
    assert result.best_rows[0].result.edge_flows is None
    assert result.best_rows[0].result.total_cost is None
    assert result.best_accounting[0].declared_units == 4
    assert result.probe_rows is None
    assert all(ledger is ledgers[0] for ledger in ledgers)
    assert all(roster[0] is rosters[0][0] for roster in rosters)
    assert list(ledgers[0].carried()) == [0, 0]
    assert list(ledgers[0].reserved()) == [0, 0]
    assert observations[0][0].delivered == 4  # snapshot survives final remove


def test_zero_declared_and_zero_rounded_are_distinct_and_probe_rows_are_opt_in():
    context, demands = prepared(0)
    trivial = maximum_supported_demand(context, MSDQuery(demands, alpha_max=4))
    assert (
        trivial.search_status == "trivial" and trivial.stop_reason == "nothing_offered"
    )
    assert trivial.proof == "nothing_offered" and trivial.monotone_proven
    assert trivial.alpha_feasible.value == 4
    assert len(trivial.history) == 1 and trivial.history[
        0
    ].totals.delivery_ratio == Fraction(1)
    assert trivial.history[0].totals.reference_request_units == 0
    assert trivial.upper_certificate is None
    context, demands = prepared(0.25)
    assert demands.demands[0].nominal_units == 0
    scaled = maximum_supported_demand(
        context, MSDQuery(demands, alpha_max=4, export_probe_rows=True)
    )
    assert scaled.search_status == "limit" and scaled.stop_reason == "alpha_bound"
    assert scaled.proof == "fixed_program"
    assert scaled.alpha_feasible.value == 4
    assert scaled.best_rows[0].reference_request_units == 1
    assert scaled.best_rows[0].result.delivered == 1
    assert set(scaled.probe_rows) == set(range(len(scaled.history)))
    assert [row.index for row in scaled.history] == list(range(len(scaled.history)))


def test_range_is_not_congestion_and_preserves_earlier_feasible_probe():
    context, demands = prepared(1)
    result = maximum_supported_demand(
        context, MSDQuery(demands, growth_factor=2**63, alpha_max=2**63)
    )
    assert result.search_status == "range" and result.stop_reason == "offer_range"
    assert result.alpha_feasible.value == 1
    assert result.best_probe_index == 0 and result.upper_certificate is None
    refused = result.history[-1]
    assert refused.outcome == "range" and refused.totals is None
    assert refused.range_refusal.reason == "native_units_range"
    assert "load|0" in refused.range_refusal.label
    assert refused.range_refusal.binary64_hex == float(2**63).hex()
    assert result.best_rows[0].result.delivered == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"growth_factor": 1},
        {"alpha_start": True},
        {"max_bracket_iters": 0},
        {"alpha_tolerance": 0},
        {"alpha_max": float("inf")},
        {"export_probe_rows": 1},
    ],
)
def test_invalid_controls_refuse_and_legal_control_succeeds(kwargs):
    context, demands = prepared()
    with pytest.raises(ValueError, match="msd"):
        MSDQuery(demands, **kwargs)
    assert (
        maximum_supported_demand(
            context, MSDQuery(demands, alpha_tolerance=1)
        ).alpha_feasible.value
        == 1
    )


@pytest.mark.parametrize("retained", [False, True])
def test_rows_are_built_only_for_retained_probes_and_new_best_probes(
    monkeypatch, retained
):
    from ngraph.analysis import msd

    built = []
    original = msd.PlacementRow

    def row(*args):
        value = original(*args)
        built.append(value)
        return value

    monkeypatch.setattr(msd, "PlacementRow", row)
    context, demands = prepared(volume=1)
    result = maximum_supported_demand(
        context, MSDQuery(demands, alpha_start=1, export_probe_rows=retained)
    )
    best, improving = None, []
    for probe in result.history:
        if probe.outcome == "feasible" and (
            best is None or probe.alpha.value > best.alpha.value
        ):
            best = probe
            improving.append(probe.index)
    assert len(improving) >= 2 and len(result.history) > len(improving)
    measured = [probe.index for probe in result.history if probe.totals is not None]
    assert len(built) == (len(measured) if retained else len(improving))
    assert result.best_probe_index == improving[-1]
    assert result.best_rows[0].result.delivered == 4
    if retained:
        assert sorted(result.probe_rows) == measured
        assert result.probe_rows[result.best_probe_index] == result.best_rows
    else:
        assert result.probe_rows is None and result.best_rows == (built[-1],)


def test_every_probe_is_quantized_at_the_prepared_q():
    # Automatic resolution: q is chosen once at preparation and never again for a probe.
    # Each probe's request is then alpha x volume / q units: growing with alpha. A q
    # chosen again from the probe's scaled volume would grow with alpha instead and keep
    # the request near the first probe's units.
    from ngraph.analysis.units import UnitsSettings
    from ngraph.scenario import Scenario, prepare

    network = Network()
    network.add_node(Node("s"))
    network.add_node(Node("t"))
    network.add_link(Link("s", "t", 64, 1))
    context = prepare(Scenario(network, units=UnitsSettings()))
    q = context.topology.q
    assert context.units_report.mode == "auto" and context.units_report.q == q
    demands = resolve_demands(
        context,
        DemandSet(
            "load",
            (
                DemandSpec(
                    Selector("^s$"),
                    Selector("^t$"),
                    1,
                    FlowPolicyPreset.TE_MAXFLOW_UNLIM,
                ),
            ),
        ),
    )
    result = maximum_supported_demand(context, MSDQuery(demands))
    probed = [p for p in result.history if p.totals is not None]
    assert [p.alpha.value for p in probed][:7] == [1, 2, 4, 8, 16, 32, 64]
    for probe in probed:
        # Half-up of the exact scaled request at the prepared q (q = 1/8 here: alpha
        # 64.0625 asks 512.5 -> 513 units).
        exact = Fraction(probe.alpha.numerator, probe.alpha.denominator) / Fraction(q)
        assert probe.totals.reference_request_units == int(exact + Fraction(1, 2))
    # The capacity is 64 / q = 512 units: the best probe asks exactly those.
    best = result.history[result.best_probe_index]
    assert best.totals.reference_request_units == 512 == best.totals.delivered_units
