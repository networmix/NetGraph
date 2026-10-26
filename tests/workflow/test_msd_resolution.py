"""Small finite tunnel demands and unreachable demand outcomes at fixed q."""

from fractions import Fraction

from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


def _fabric(leaves, spines):
    network = Network()
    for index in range(leaves):
        network.add_node(Node(f"leaf{index:02d}"))
    for index in range(spines):
        network.add_node(Node(f"spine{index:02d}"))
    for leaf in range(leaves):
        for spine in range(spines):
            network.add_link(Link(f"leaf{leaf:02d}", f"spine{spine:02d}", 100, 1))
    return network


def test_many_lsps_over_small_pairwise_volumes_find_tested_feasible_alpha():
    network = _fabric(4, 2)
    demands = DemandSet(
        "load",
        tuple(
            DemandSpec(
                Selector(f"^leaf{index:02d}$"),
                Selector("^leaf", group_by="name"),
                1,
                FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP,
                id=f"d{index}",
                mode="pairwise",
            )
            for index in range(4)
        ),
    )
    step = MaximumSupportedDemand(
        name="msd",
        demand_set="load",
        alpha_tolerance=0.5,
        max_bracket_iters=12,
        max_bisect_iters=4,
    )
    prepared = prepare(Scenario(network, (step,), demand_sets={"load": demands}))
    result = run(prepared).steps[0].result
    # Each parent of 1 splits among three off-diagonal pairs: p*1/(3-1)
    # is .0005, whose coarsest power of two is 2^-11. Each pair's small
    # design fits one tunnel, so the up-to limit adds no tunnel constraint.
    assert prepared.topology.q == 1 / 2048
    assert all(
        c.kind == "expansion" and c.members == 3
        for c in prepared.units_report.binding_constraints
    )
    assert 64 <= result.alpha_feasible.value <= 512
    assert result.history[0].outcome == "feasible"
    assert result.proof == "unproved" and result.upper_certificate is None
    assert result.best_rows is not None and len(result.best_rows) == 12
    assert all(row.result.requested == row.result.delivered for row in result.best_rows)


def test_unreachable_target_reports_exact_ratio_and_no_feasible_status():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    network.add_link(Link("A", "B", 10, 3))
    demands = DemandSet(
        "load",
        (
            DemandSpec(Selector("^A$"), Selector("^B$"), 1, id="ok"),
            DemandSpec(Selector("^A$"), Selector("^C$"), 1, id="isolated"),
        ),
    )
    step = MaximumSupportedDemand(
        name="msd",
        demand_set="load",
        alpha_min=1,
        max_bracket_iters=3,
        max_bisect_iters=2,
    )
    result = (
        run(
            prepare(
                Scenario(
                    network,
                    (step,),
                    demand_sets={"load": demands},
                    units=UnitsSettings(1 / 4096),
                )
            )
        )
        .steps[0]
        .result
    )
    assert (
        result.search_status == "none_feasible" and result.stop_reason == "alpha_bound"
    )
    assert result.alpha_feasible is result.best_probe_index is None
    assert len(result.history) == 1
    assert result.history[0].totals.delivery_ratio == Fraction(1, 2)
    assert result.history[0].totals.reference_request_units == 8192
    assert result.history[0].totals.delivered_units == 4096
