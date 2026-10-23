"""Bounded MSD workflows report actual native probes and tested feasibility."""

from fractions import Fraction

from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


def msd_scenario(capacity=13, volume=10, **controls):
    network = Network()
    network.add_node(Node("A"))
    network.add_node(Node("B"))
    network.add_link(Link("A", "B", capacity, 3))
    demands = DemandSet("load", (DemandSpec(Selector("^A$"), Selector("^B$"), volume),))
    step = MaximumSupportedDemand(name="msd", demand_set="load", **controls)
    return prepare(
        Scenario(
            network,
            (step,),
            demand_sets={"load": demands},
            units=UnitsSettings(1 / 1024),
        )
    )


def checked_msd(prepared):
    result = run(prepared).steps[0].result
    capacity = int(prepared.scenario.network.links["A|B|0"].capacity * 1024)
    volume = prepared.scenario.demand_sets["load"].demands[0].volume
    feasible = []
    for index, probe in enumerate(result.history):
        assert probe.index == index
        assert Fraction(
            probe.alpha.numerator, probe.alpha.denominator
        ) == Fraction.from_float(probe.alpha.value)
        amount = Fraction.from_float(volume * probe.alpha.value) * 1024
        requested = (2 * amount.numerator + amount.denominator) // (
            2 * amount.denominator
        )
        assert probe.outcome == ("feasible" if requested <= capacity else "infeasible")
        assert probe.totals.reference_request_units == requested
        assert probe.totals.delivered_units == min(requested, capacity)
        assert probe.totals.unadmitted_units == max(0, requested - capacity)
        if requested <= capacity:
            feasible.append(probe)
    if feasible:
        best = max(feasible, key=lambda probe: (probe.alpha.value, -probe.index))
        assert (
            result.alpha_feasible == best.alpha
            and result.best_probe_index == best.index
        )
        assert result.best_rows[0].result.delivered == best.totals.delivered_units
    else:
        assert result.alpha_feasible is result.best_probe_index is None
        assert result.best_rows is result.best_accounting is None
    assert result.proof == "fixed_program" and result.monotone_proven
    assert result.probe_rows is None
    return result


def test_msd_basic_bracket_and_bisect():
    result = checked_msd(msd_scenario(alpha_tolerance=0.001))
    assert 1.299 <= result.alpha_feasible.value <= 1.301
    assert result.search_status == "feasible" and result.stop_reason == "tolerance"
    certificate = result.upper_certificate
    assert certificate.lower == result.alpha_feasible
    assert certificate.upper.value - certificate.lower.value <= 0.001
    assert result.history[certificate.upper_probe_index].outcome == "infeasible"


def test_msd_no_feasible_reports_status():
    result = checked_msd(msd_scenario(0, 1, alpha_min=0.25))
    assert (
        result.search_status == "none_feasible" and result.stop_reason == "alpha_bound"
    )
    assert result.upper_certificate is None
    assert [probe.alpha.value for probe in result.history] == [1, 0.5, 0.25]


def test_msd_end_to_end_single_link():
    prepared = msd_scenario(10, 5, alpha_tolerance=0.001)
    result = checked_msd(prepared)
    assert 2 <= result.alpha_feasible.value < 2.001
    feasible = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"], result.alpha_feasible.value, workers=1
        ),
    )
    assert feasible.cases[0].states["converged"].totals.feasible
    above = place(
        prepared,
        PlacementQuery(
            prepared.demand_sets["load"],
            result.upper_certificate.upper.value,
            workers=1,
        ),
    )
    assert not above.cases[0].states["converged"].totals.feasible


def test_msd_all_feasible_small_alpha_max():
    result = checked_msd(msd_scenario(100, 1, alpha_max=10))
    assert result.alpha_feasible.value == 10
    assert result.search_status == "limit" and result.stop_reason == "alpha_bound"


def test_msd_all_feasible_alpha_max_equals_alpha_start():
    result = checked_msd(msd_scenario(100, 1, alpha_max=1))
    assert [probe.alpha.value for probe in result.history] == [1]
    assert result.alpha_feasible.value == 1


def test_msd_all_feasible_default_alpha_max():
    result = checked_msd(msd_scenario(2**40, 1))
    assert result.alpha_feasible.value == 1e9
    assert result.stop_reason == "alpha_bound"


def test_msd_bracket_limit_preserves_largest_tested_feasible():
    result = checked_msd(msd_scenario(2**40, 1, alpha_max=1e6, max_bracket_iters=4))
    assert [probe.alpha.value for probe in result.history] == [1, 2, 4, 8]
    assert result.alpha_feasible.value == 8
    assert result.search_status == "limit" and result.stop_reason == "bracket_limit"


def test_msd_bracket_limit_does_not_invent_untested_upper():
    result = checked_msd(msd_scenario(500, 1, alpha_max=1e6, max_bracket_iters=4))
    assert result.alpha_feasible.value == 8
    assert result.upper_certificate is None
    assert result.stop_reason == "bracket_limit"


def test_msd_threshold_exactly_at_alpha_max():
    result = checked_msd(msd_scenario(10, 1, alpha_max=10))
    assert result.alpha_feasible.value == 10
    assert result.history[-1].alpha.value == 10
    assert result.stop_reason == "alpha_bound"
