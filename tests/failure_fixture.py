"""Small owned topologies and typed single-draw observations for failure tests."""

from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.analysis.units import UnitsSettings
from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario, prepare


def policy_network():
    network = Network()
    for name, vendor, location in (
        ("N1", "cisco", "dallas"),
        ("N2", "juniper", "houston"),
        ("N3", "cisco", "austin"),
    ):
        network.add_node(Node(name, attrs={"vendor": vendor, "location": location}))
    for target, kind in (("N2", "fiber"), ("N3", "radio")):
        network.add_link(Link("N1", target, 10, 3, attrs={"kind": kind}))
    return prepare(Scenario(network, units=UnitsSettings(1)))


def draw(prepared, policy, seed=42, *, trace=False):
    cases = failure_cases(prepared, FailureRequest(policy, 1, seed, trace))
    sampled = [case for case in cases if case.occurrences]
    assert len(sampled) == 1 and sampled[0].occurrences == 1
    return sampled[0]
