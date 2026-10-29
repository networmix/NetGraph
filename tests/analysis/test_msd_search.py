"""Terminal causes, exact best probes, and cleanup before every observation."""

import math

import pytest

from ngraph.analysis import msd
from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.units import UnitRangeError
from tests.analysis.test_persistent_msd import prepared


@pytest.mark.parametrize(
    "volume,controls,status,reason,alphas,outcomes,best",
    [
        (
            4,
            {"alpha_tolerance": 1},
            "feasible",
            "tolerance",
            [1, 2],
            ["feasible", "infeasible"],
            0,
        ),
        (4, {"max_bracket_iters": 1}, "limit", "bracket_limit", [1], ["feasible"], 0),
        (
            4,
            {"alpha_start": 2, "max_bracket_iters": 1},
            "none_feasible",
            "bracket_limit",
            [2],
            ["infeasible"],
            None,
        ),
        (
            4,
            {"alpha_start": 2, "alpha_min": 2},
            "none_feasible",
            "alpha_bound",
            [2],
            ["infeasible"],
            None,
        ),
        (
            4,
            {"max_bracket_iters": 2, "max_bisect_iters": 1},
            "limit",
            "bisect_limit",
            [1, 2, 1.5],
            ["feasible", "infeasible", "infeasible"],
            0,
        ),
        (
            1,
            {"alpha_max": 2},
            "limit",
            "alpha_bound",
            [1, 2],
            ["feasible", "feasible"],
            1,
        ),
        (0, {"alpha_max": 4}, "trivial", "nothing_offered", [4], ["feasible"], 0),
        (
            1,
            {
                "alpha_start": math.ulp(0.0),
                "alpha_min": math.ulp(0.0),
                "alpha_max": 2 * math.ulp(0.0),
                "growth_factor": math.nextafter(1.0, 2.0),
            },
            "stagnation",
            "representable_limit",
            [math.ulp(0.0)],
            ["below_resolution"],
            None,
        ),
        (
            1,
            {"alpha_start": float(2**63), "alpha_max": float(2**63)},
            "range",
            "offer_range",
            [float(2**63)],
            ["range"],
            None,
        ),
    ],
)
def test_status_history_and_best_are_actual_native_observations(
    volume, controls, status, reason, alphas, outcomes, best
):
    context, demands = prepared(volume)
    result = maximum_supported_demand(context, MSDQuery(demands, **controls))
    assert result.search_status == status and result.stop_reason == reason
    assert [probe.alpha.value for probe in result.history] == alphas
    assert [probe.outcome for probe in result.history] == outcomes
    assert [probe.index for probe in result.history] == list(range(len(alphas)))
    assert result.best_probe_index == best
    assert result.probe_rows is None
    if best is None:
        assert (
            result.alpha_feasible is result.best_rows is result.best_accounting is None
        )
        assert result.upper_certificate is None
    else:
        assert result.alpha_feasible == result.history[best].alpha
        assert result.alpha_feasible.value == max(
            probe.alpha.value for probe in result.history if probe.outcome == "feasible"
        )
        assert (
            result.best_rows[0].reference_request_units
            == result.history[best].totals.reference_request_units
        )
    for probe in result.history:
        assert probe.alpha.value.as_integer_ratio() == (
            probe.alpha.numerator,
            probe.alpha.denominator,
        )
        if probe.outcome == "range":
            assert probe.totals is None and probe.range_refusal is not None
            assert probe.range_refusal.reason == "native_units_range"
        else:
            assert probe.range_refusal is None and probe.totals is not None
            if probe.outcome == "below_resolution":
                assert volume > 0 and probe.totals.reference_request_units == 0
                assert probe.totals.feasible
            else:
                assert probe.totals.feasible == (probe.outcome == "feasible")


def test_remove_all_owners_precedes_scaling_even_for_range_probe(monkeypatch):
    context, demands = prepared(1)
    original_roster, original_scaling = msd.policy_roster, msd.scaled_expansion
    rosters, observations = [], []

    def roster(*args):
        ledger, policies = original_roster(*args)
        rosters.append((ledger, policies))
        return ledger, policies

    def scaling(*args):
        ledger, policies = rosters[0]
        assert all(value == 0 for value in ledger.carried())
        assert all(value == 0 for value in ledger.reserved())
        assert all(
            policy.program is None and policy.records() == [] for policy in policies
        )
        observations.append(args[1])
        return original_scaling(*args)

    monkeypatch.setattr(msd, "policy_roster", roster)
    monkeypatch.setattr(msd, "scaled_expansion", scaling)
    result = maximum_supported_demand(
        context, MSDQuery(demands, growth_factor=2**63, alpha_max=2**63)
    )
    assert len(rosters) == 1 and observations == [1, float(2**63)]
    assert result.search_status == "range" and result.alpha_feasible.value == 1
    assert all(value == 0 for value in rosters[0][0].carried())


def test_range_terminal_cause_wins_without_a_feasible_probe(monkeypatch):
    context, demands = prepared(8)
    original = msd.scaled_expansion

    def refuse_second(values, alpha, q):
        if alpha == 0.5:
            # Inject the typed numerical refusal at the preparation boundary;
            # this tests status precedence, not a native arithmetic witness.
            raise UnitRangeError(
                "load|0",
                "native_units_range",
                "injected range refusal",
                float(alpha).hex(),
            )
        return original(values, alpha, q)

    monkeypatch.setattr(msd, "scaled_expansion", refuse_second)
    result = maximum_supported_demand(context, MSDQuery(demands))
    assert [probe.outcome for probe in result.history] == ["infeasible", "range"]
    assert result.search_status == "range" and result.stop_reason == "offer_range"
    assert (
        result.alpha_feasible
        is result.best_probe_index
        is result.upper_certificate
        is None
    )
    assert result.best_rows is result.best_accounting is None


@pytest.mark.parametrize("boundary", ["MSDProbe", "analysis_metadata"])
def test_python_result_failure_releases_every_policy_and_retry_succeeds(
    monkeypatch, boundary
):
    context, demands = prepared()
    original_roster, original_boundary = msd.policy_roster, getattr(msd, boundary)
    rosters = []

    def roster(*args):
        ledger, owners = original_roster(*args)
        rosters.append((ledger, owners))
        return ledger, owners

    def fail(*args, **kwargs):
        raise MemoryError("forced Python result publication failure")

    monkeypatch.setattr(msd, "policy_roster", roster)
    monkeypatch.setattr(msd, boundary, fail)
    with pytest.raises(MemoryError, match="forced Python result publication"):
        maximum_supported_demand(context, MSDQuery(demands, alpha_tolerance=1))
    ledger, owners = rosters[0]
    assert all(value == 0 for value in ledger.carried())
    assert all(value == 0 for value in ledger.reserved())
    assert all(owner.program is None and owner.records() == [] for owner in owners)
    monkeypatch.setattr(msd, boundary, original_boundary)
    retry = maximum_supported_demand(context, MSDQuery(demands, alpha_tolerance=1))
    assert retry.alpha_feasible.value == 1
    assert [probe.outcome for probe in retry.history] == ["feasible", "infeasible"]
