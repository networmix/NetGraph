"""Prepared networks for tests that ask library questions directly."""

from ngraph.analysis.units import UnitsSettings
from ngraph.scenario import Scenario, prepare


def prepare_network(network, q=1, **declared):
    """Prepare one network, with no workflow, at one fixed resolution."""
    return prepare(Scenario(network, units=UnitsSettings(q), **declared))
