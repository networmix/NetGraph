"""Regression tests for BuildGraph with reserved-key collisions in attrs.

BuildGraph previously crashed with TypeError ("got multiple values for
keyword argument") when node attrs contained "disabled" or link attrs
contained "id", "capacity", "cost", or "disabled". Reserved keys must win
over user attrs, matching the precedence documented for flatten_node_attrs
and flatten_link_attrs.
"""

from unittest.mock import MagicMock

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.results.store import Results
from ngraph.workflow.build_graph import BuildGraph


@pytest.fixture
def scenario_with_reserved_attrs():
    """Scenario whose node/link attrs collide with reserved graph keys."""
    scenario = MagicMock()
    scenario.seed = None
    scenario._execution_counter = 0
    scenario.network = Network()
    scenario.results = Results()

    scenario.network.add_node(Node("A", attrs={"disabled": "user-value", "site": "X"}))
    scenario.network.add_node(Node("B"))
    scenario.network.add_link(
        Link(
            "A",
            "B",
            capacity=10.0,
            cost=2.0,
            attrs={
                "id": "circuit-123",
                "capacity": "10G",
                "cost": "external",
                "disabled": "maybe",
                "vendor": "acme",
            },
        )
    )
    return scenario


def _step_data(scenario, step_name: str) -> dict:
    return scenario.results.to_dict()["steps"][step_name]["data"]


def test_build_graph_runs_with_reserved_attr_keys(scenario_with_reserved_attrs):
    """Step completes instead of raising TypeError on reserved attr keys."""
    step = BuildGraph(name="build_graph")

    step.execute(scenario_with_reserved_attrs)

    data = _step_data(scenario_with_reserved_attrs, "build_graph")
    assert data["graph"] is not None


def test_reserved_node_keys_win_over_user_attrs(scenario_with_reserved_attrs):
    """Node 'disabled' reflects model state, not the user attr value."""
    step = BuildGraph(name="build_graph")
    step.execute(scenario_with_reserved_attrs)

    graph_dict = _step_data(scenario_with_reserved_attrs, "build_graph")["graph"]
    nodes = {n["id"]: n for n in graph_dict["nodes"]}

    assert nodes["A"]["disabled"] is False
    # Non-reserved user attrs are preserved
    assert nodes["A"]["site"] == "X"


def test_reserved_link_keys_win_over_user_attrs(scenario_with_reserved_attrs):
    """Edge id/capacity/cost/disabled reflect model state, not user attrs."""
    network = scenario_with_reserved_attrs.network
    link_id = next(iter(network.links))

    step = BuildGraph(name="build_graph")
    step.execute(scenario_with_reserved_attrs)

    graph_dict = _step_data(scenario_with_reserved_attrs, "build_graph")["graph"]
    edges = {e["id"]: e for e in graph_dict["edges"]}

    forward = edges[link_id]
    assert forward["source"] == "A"
    assert forward["target"] == "B"
    assert forward["capacity"] == 10.0
    assert forward["cost"] == 2.0
    assert forward["disabled"] is False
    # Non-reserved user attrs are preserved
    assert forward["vendor"] == "acme"

    reverse = edges[f"{link_id}_reverse"]
    assert reverse["source"] == "B"
    assert reverse["target"] == "A"
    assert reverse["capacity"] == 10.0
    assert reverse["cost"] == 2.0
    assert reverse["disabled"] is False
    assert reverse["vendor"] == "acme"


def test_build_graph_without_reserved_keys_unchanged():
    """Plain attrs still pass through unchanged."""
    scenario = MagicMock()
    scenario.seed = None
    scenario._execution_counter = 0
    scenario.network = Network()
    scenario.results = Results()
    scenario.network.add_node(Node("A", attrs={"role": "leaf"}))
    scenario.network.add_node(Node("B", disabled=True))
    scenario.network.add_link(Link("A", "B", capacity=5.0, cost=1.0))

    step = BuildGraph(name="build_graph")
    step.execute(scenario)

    graph_dict = _step_data(scenario, "build_graph")["graph"]
    nodes = {n["id"]: n for n in graph_dict["nodes"]}
    assert nodes["A"]["role"] == "leaf"
    assert nodes["A"]["disabled"] is False
    assert nodes["B"]["disabled"] is True
    assert len(graph_dict["edges"]) == 2  # forward + reverse
