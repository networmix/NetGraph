"""Closed query mode literals refuse aliases and unknown controls."""

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.units import UnitsSettings
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


def _prepared():
    network = Network(nodes={name: Node(name) for name in ("A", "B")})
    network.add_link(Link("A", "B", 1, 3))
    return prepare(Scenario(network, units=UnitsSettings(1)))


@pytest.mark.parametrize(
    "mode", ["aggregate", "Combined", "pair", "all", "", "COMBINE", "Pairwise"]
)
def test_capacity_invalid_mode_raises(mode):
    with pytest.raises(ValueError, match="capacity.mode"):
        CapacityQuery(Selector("^A$"), Selector("^B$"), mode=mode)
    assert (
        capacity(
            _prepared(), CapacityQuery(Selector("^A$"), Selector("^B$"), workers=1)
        )
        .cases[0]
        .states["converged"]
        .rows[0]
        .result.delivered
        == 1
    )


def test_sensitivity_unknown_mode_refuses():
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    with pytest.raises(TypeError, match="unexpected keyword argument 'mode'"):
        SensitivityQuery(Selector("^A$"), Selector("^B$"), config, mode="aggregate")
    assert (
        edge_sensitivity(
            _prepared(),
            SensitivityQuery(Selector("^A$"), Selector("^B$"), config, workers=1),
        ).result.baseline.delivered
        == 1
    )


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
def test_valid_modes_accepted(mode):
    result = capacity(
        _prepared(),
        CapacityQuery(Selector("^A$"), Selector("^B$"), mode=mode, workers=1),
    )
    assert len(result.cases[0].states["converged"].rows) == 1
    assert result.cases[0].states["converged"].rows[0].result.delivered == 1
