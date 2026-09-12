"""MaximumSupportedDemand feasibility at the engine's numeric resolution."""

from __future__ import annotations

import pytest

from ngraph.model.demand.matrix import DemandSet
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.results import Results
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


class _Scenario:
    def __init__(self, network: Network, demand_set: DemandSet) -> None:
        self.network = network
        self.demand_set = demand_set
        self.results = Results()


def _fabric(leaves: int, spines: int) -> Network:
    net = Network()
    for i in range(leaves):
        net.add_node(Node(f"leaf{i:02d}"))
    for j in range(spines):
        net.add_node(Node(f"spine{j:02d}"))
    for i in range(leaves):
        for j in range(spines):
            net.add_link(Link(f"leaf{i:02d}", f"spine{j:02d}", capacity=100.0, cost=1))
    return net


def _run_msd(net: Network, demands: list[TrafficDemand], **params) -> dict:
    ds = DemandSet()
    ds.add("default", demands)
    scenario = _Scenario(net, ds)
    step = MaximumSupportedDemand(demand_set="default", **params)
    step.name = "msd"
    scenario.results.enter_step("msd")
    try:
        step.run(scenario)  # type: ignore[arg-type]
    finally:
        scenario.results.exit_step()
    return scenario.results.get_step("msd")["data"]


def test_many_lsps_over_small_pairwise_volumes_find_alpha_star():
    """256 LSPs per pair on 0.03-unit demands quantize at 1/4096; that is not infeasibility."""
    net = _fabric(8, 4)
    demands = [
        TrafficDemand(
            source=f"^leaf{i:02d}$",
            target="^leaf",
            volume=1.0,
            mode="pairwise",
            flow_policy=FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP,
            id=f"d{i}",
        )
        for i in range(8)
    ]
    data = _run_msd(
        net,
        demands,
        alpha_start=1.0,
        resolution=0.5,
        max_bracket_iters=6,
        max_bisect_iters=4,
    )
    # Each leaf sends 1.0 over 4 uplinks of 100: alpha_star sits between 64 and 512.
    assert 64.0 <= data["alpha_star"] <= 512.0
    assert data["probes"][0]["feasible"] is True


def test_unreachable_target_reports_ratio_in_error():
    net = Network()
    for n in ("A", "B", "C"):
        net.add_node(Node(n))
    net.add_link(Link("A", "B", capacity=10, cost=1))
    demands = [
        TrafficDemand(source="^A$", target="^B$", volume=1.0, mode="pairwise", id="ok"),
        TrafficDemand(
            source="^A$", target="^C$", volume=1.0, mode="pairwise", id="isolated"
        ),
    ]
    with pytest.raises(ValueError, match=r"best placement ratio over probes 0\.5000"):
        _run_msd(net, demands, alpha_start=1.0, max_bracket_iters=3, max_bisect_iters=2)
