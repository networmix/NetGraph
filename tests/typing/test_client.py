"""Execute the same typed client used to check installed public construction."""

import json

from ngraph import Network
from tests.typing.valid_client import (
    controlled_example,
    counts_example,
    example,
    minimal,
    populated_example,
)


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


def test_a_typed_count_client():
    # Equal heads behind 2 and 10: two tunnels per head; up to 2 chooses 1 (U = 2 and 1
    # carry 4 each, short of the design 12, so the smallest count wins).
    assert counts_example() == [(2, False, 2), (2, True, 1)]


def test_the_populated_client_runs_every_constructor_field():
    # The controller splits 9 by the group caps 1 : 1/2 (6 and 3 within capacity 10);
    # the pinned demand sends 1 unit on each named route.
    assert populated_example() == [("controlled", 9.0), ("pinned", 2.0)]
