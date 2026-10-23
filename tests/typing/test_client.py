"""Execute the same typed client used to check installed public construction."""

import json

from ngraph import Network
from tests.typing.valid_client import example, minimal


def test_minimal_public_construction_and_all_public_functions():
    assert minimal(Network(), ()).steps == ()
    result, placement, supported, text = example()
    assert result.steps[0].result.nodes == 3
    assert placement.cases[0].states["converged"].totals.delivered_units == 10
    assert supported.alpha_feasible is not None
    assert json.loads(text)["analysis"]["kind"] == "placement"
