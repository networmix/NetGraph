"""NGRAPH_PROFILE_DIR must be restored even when serial analysis raises."""

import os

import pytest

from ngraph.analysis.failure_manager import FailureManager
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node


def _failing_analysis(network, excluded_nodes, excluded_links, **kwargs):
    raise RuntimeError("analysis blew up")


def test_run_serial_restores_profile_dir_on_exception(tmp_path, monkeypatch):
    profile_dir = str(tmp_path / "profiles")
    monkeypatch.setenv("NGRAPH_PROFILE_DIR", profile_dir)

    network = Network()
    network.add_node(Node("A"))
    network.add_node(Node("B"))
    network.add_link(Link("A", "B", capacity=1.0, cost=1.0))
    fm = FailureManager(network, FailurePolicySet(), policy_name=None)

    with pytest.raises(RuntimeError, match="analysis blew up"):
        fm.run_monte_carlo_analysis(
            analysis_func=_failing_analysis, iterations=1, parallelism=1
        )

    assert os.environ.get("NGRAPH_PROFILE_DIR") == profile_dir
