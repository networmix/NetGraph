from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.results.store import Results
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


def _mock_scenario_with_matrix() -> MagicMock:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "A"
    td.target = "B"
    td.volume = 10.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy = None
    mock_scenario.demand_set.get_set.return_value = [td]
    return mock_scenario


@patch.object(MaximumSupportedDemand, "_evaluate_alpha")
@patch.object(MaximumSupportedDemand, "_build_cache")
def test_msd_basic_bracket_and_bisect(
    mock_build_cache: MagicMock, mock_eval: MagicMock
) -> None:
    """Test binary search logic with mocked evaluation."""
    mock_build_cache.return_value = MagicMock()

    # Feasible if alpha <= 1.3, infeasible otherwise
    def _eval(cache, alpha):
        feasible = alpha <= 1.3
        return feasible, {
            "placement_ratio": 1.0 if feasible else 0.9,
        }

    mock_eval.side_effect = _eval

    scenario = _mock_scenario_with_matrix()
    step = MaximumSupportedDemand(
        name="msd_step",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        max_bisect_iters=32,
        max_bracket_iters=16,
    )
    scenario.results = Results()
    step.execute(scenario)

    exported = scenario.results.to_dict()
    alpha_star = exported["steps"]["msd_step"]["data"]["alpha_star"]
    assert abs(alpha_star - 1.3) <= 0.02
    ctx = exported["steps"]["msd_step"]["data"].get("context", {})
    assert ctx.get("acceptance_rule") == "hard"
    base = exported["steps"]["msd_step"]["data"].get("base_demands", [])
    assert base and base[0]["source"] == "A"


@patch.object(MaximumSupportedDemand, "_evaluate_alpha")
@patch.object(MaximumSupportedDemand, "_build_cache")
def test_msd_no_feasible_raises(
    mock_build_cache: MagicMock, mock_eval: MagicMock
) -> None:
    """Test that MSD raises when no feasible alpha is found."""
    mock_build_cache.return_value = MagicMock()

    # Always infeasible
    def _eval(cache, alpha):
        return False, {"placement_ratio": 0.0}

    mock_eval.side_effect = _eval

    scenario = _mock_scenario_with_matrix()
    step = MaximumSupportedDemand(
        name="msd_step",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        alpha_min=0.25,
        max_bracket_iters=8,
    )
    scenario.results = Results()
    with pytest.raises(ValueError):
        step.execute(scenario)


def test_msd_end_to_end_single_link() -> None:
    """Test MSD end-to-end with a simple single-link scenario."""
    from ngraph.analysis.functions import demand_placement_analysis
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

    # Build a tiny deterministic scenario: A --(cap=10)--> B, demand base=5
    scenario = (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B"])
        .with_simple_links([("A", "B", 10.0)])
        .with_traffic_demand("A", "B", 5.0, demand_set="default")
        .build_scenario()
    )

    step = MaximumSupportedDemand(
        name="msd_e2e",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
    )
    scenario.results = Results()
    step.execute(scenario)

    # Expected alpha* ~ 2.0 (capacity 10 / base 5)
    exported = scenario.results.to_dict()
    data = exported["steps"]["msd_e2e"]["data"]
    alpha_star = data.get("alpha_star")
    assert alpha_star is not None
    assert abs(float(alpha_star) - 2.0) <= 0.02

    base_demands = data.get("base_demands")
    assert isinstance(base_demands, list) and base_demands

    # Verify feasibility at alpha* using demand_placement_analysis
    scaled_demands = MSD._build_scaled_demands(base_demands, float(alpha_star))
    demands_config = [
        {
            "id": d.id,
            "source": d.source,
            "target": d.target,
            "volume": d.volume,
            "mode": d.mode,
            "priority": d.priority,
            "flow_policy": d.flow_policy,
        }
        for d in scaled_demands
    ]

    result = demand_placement_analysis(
        network=scenario.network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=demands_config,
        placement_rounds=1,
    )

    # At alpha*, all demands should be fully placed
    assert result.summary.overall_ratio >= 1.0 - 1e-9

    # Verify infeasibility just above alpha*
    alpha_above = float(alpha_star) + 0.05
    scaled_demands_above = MSD._build_scaled_demands(base_demands, alpha_above)
    demands_config_above = [
        {
            "id": d.id,
            "source": d.source,
            "target": d.target,
            "volume": d.volume,
            "mode": d.mode,
            "priority": d.priority,
            "flow_policy": d.flow_policy,
        }
        for d in scaled_demands_above
    ]

    result_above = demand_placement_analysis(
        network=scenario.network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=demands_config_above,
        placement_rounds=1,
    )

    # Above alpha*, placement should fail (ratio < 1.0)
    assert result_above.summary.overall_ratio < 1.0 - 1e-9


# ---------------------------------------------------------------------------
# Edge-case tests for _binary_search: all-feasible / bracket-exhaustion bugs
# ---------------------------------------------------------------------------


def _make_step(**kwargs: object) -> MaximumSupportedDemand:
    """Create an MSD step with sensible defaults, overridden by kwargs."""
    defaults: dict[str, object] = dict(
        name="test",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        alpha_min=1e-6,
        alpha_max=1e9,
        resolution=0.01,
        max_bracket_iters=32,
        max_bisect_iters=32,
    )
    defaults.update(kwargs)
    return MaximumSupportedDemand(**defaults)


def _threshold_probe(threshold: float | None):
    """Return a probe function that is feasible for alpha <= threshold (or always)."""

    def probe(alpha: float) -> tuple[bool, dict[str, float]]:
        feasible = True if threshold is None else alpha <= threshold
        return feasible, {"placement_ratio": 1.0 if feasible else 0.5}

    return probe


def test_msd_all_feasible_small_alpha_max() -> None:
    """All alphas feasible with small alpha_max should return alpha_max, not crash."""
    step = _make_step(alpha_max=10.0)
    result = step._binary_search(_threshold_probe(threshold=None))
    assert result == 10.0


def test_msd_all_feasible_alpha_max_equals_alpha_start() -> None:
    """All feasible with alpha_max == alpha_start should return alpha_start."""
    step = _make_step(alpha_max=1.0, alpha_start=1.0)
    result = step._binary_search(_threshold_probe(threshold=None))
    assert result == 1.0


def test_msd_all_feasible_default_alpha_max() -> None:
    """All feasible with default alpha_max=1e9 should return alpha_max, not crash."""
    step = _make_step()  # defaults: alpha_max=1e9, max_bracket_iters=32
    result = step._binary_search(_threshold_probe(threshold=None))
    assert result == 1e9


def test_msd_bracket_exhausted_alpha_max_feasible() -> None:
    """Bracket iters exhaust before alpha_max, but alpha_max IS feasible -> return alpha_max."""
    step = _make_step(alpha_max=1e6, max_bracket_iters=4)
    # With 4 iters: probes 1,2,4,8,16 -> lower=16, upper=None
    # Fix probes alpha_max=1e6 directly -> feasible -> returns 1e6
    result = step._binary_search(_threshold_probe(threshold=None))
    assert result == 1e6


def test_msd_bracket_exhausted_alpha_max_infeasible() -> None:
    """Bracket iters exhaust before alpha_max, alpha_max is infeasible -> bisect to ~threshold."""
    threshold = 500.0
    step = _make_step(alpha_max=1e6, max_bracket_iters=4, resolution=0.01)
    # With 4 iters: probes 1,2,4,8,16 -> lower=16, upper=None
    # Fix probes alpha_max=1e6 -> infeasible -> bracket [16, 1e6] -> bisect to ~500
    result = step._binary_search(_threshold_probe(threshold=threshold))
    assert abs(result - threshold) <= 0.02


def test_msd_threshold_exactly_at_alpha_max() -> None:
    """Threshold exactly at alpha_max should return alpha_max, not crash."""
    step = _make_step(alpha_max=10.0)
    result = step._binary_search(_threshold_probe(threshold=10.0))
    assert result == 10.0


def test_msd_auto_vs_one_equivalence_single_link() -> None:
    """Test that MSD with auto vs 1 placement rounds produces equivalent results."""
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

    # Same single-link scenario; compare auto vs 1 rounds
    scenario = (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B"])
        .with_simple_links([("A", "B", 10.0)])
        .with_traffic_demand("A", "B", 5.0, demand_set="default")
        .build_scenario()
    )

    step_auto = MSD(
        name="msd_auto",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        placement_rounds="auto",
    )
    step_one = MSD(
        name="msd_one",
        demand_set="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        placement_rounds=1,
    )

    scenario.results = Results()
    step_auto.execute(scenario)
    step_one.execute(scenario)

    exported = scenario.results.to_dict()
    alpha_auto = float(exported["steps"]["msd_auto"]["data"]["alpha_star"])
    alpha_one = float(exported["steps"]["msd_one"]["data"]["alpha_star"])
    # Both should find approximately the same alpha* for this simple case
    assert abs(alpha_auto - alpha_one) <= 0.02
