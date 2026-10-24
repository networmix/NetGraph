"""Execute the same typed client used to check installed public construction."""

import json

from ngraph import Network
from tests.typing.valid_client import controlled_example, example, minimal


def test_minimal_public_construction_and_all_public_functions():
    assert minimal(Network(), ()).steps == ()
    result, placement, supported, text = example()
    assert result.steps[0].result.nodes == 3
    assert placement.cases[0].states["converged"].totals.delivered_units == 10
    assert supported.alpha_feasible is not None
    assert json.loads(text)["analysis"]["kind"] == "placement"


def test_a_typed_controller_client():
    # Shares 1 and 1/2 give weights 2:1; 9 units split 6 and 3.
    assert controlled_example() == (9, [("S|X1|0", 2), ("S|X2|0", 1)])
