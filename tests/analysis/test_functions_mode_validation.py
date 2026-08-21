"""Mode string validation in analysis functions.

Invalid mode strings must raise ValueError instead of silently falling back
to PAIRWISE.
"""

import pytest

from ngraph.analysis.functions import (
    build_maxflow_context,
    max_flow_analysis,
    sensitivity_analysis,
)
from ngraph.model.network import Link, Network, Node


def _simple_network() -> Network:
    network = Network()
    for name in ("A", "B"):
        network.add_node(Node(name))
    network.add_link(Link("A", "B", capacity=1.0))
    return network


@pytest.mark.parametrize("bad_mode", ["aggregate", "Combined", "pair", "all", ""])
def test_max_flow_analysis_invalid_mode_raises(bad_mode: str) -> None:
    with pytest.raises(ValueError, match="Invalid mode"):
        max_flow_analysis(
            _simple_network(),
            set(),
            set(),
            source="^A$",
            target="^B$",
            mode=bad_mode,
        )


def test_sensitivity_analysis_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="Invalid mode"):
        sensitivity_analysis(
            _simple_network(),
            set(),
            set(),
            source="^A$",
            target="^B$",
            mode="aggregate",
        )


def test_build_maxflow_context_invalid_mode_raises() -> None:
    with pytest.raises(ValueError, match="Invalid mode"):
        build_maxflow_context(_simple_network(), "^A$", "^B$", mode="bogus")


@pytest.mark.parametrize("mode", ["combine", "pairwise", "COMBINE", "Pairwise"])
def test_valid_modes_accepted(mode: str) -> None:
    result = max_flow_analysis(
        _simple_network(),
        set(),
        set(),
        source="^A$",
        target="^B$",
        mode=mode,
    )
    assert result.summary.num_flows >= 1
