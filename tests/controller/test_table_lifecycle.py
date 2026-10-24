"""Controller tables are built only where a state recomputes them.

One failure case (link PA1-PB1), one destination: converged builds that case's
table; stale replays the baseline programs; repair prunes the nominal table
(next hop) or rebuilds the group table on the surviving routes; the baseline
case uses the nominal tables built at preparation.
"""

import pytest

from ngraph import (
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    PlacementQuery,
    place,
)
from ngraph.analysis import controller
from tests.controller.helpers import demand, prepared
from tests.controller.test_tables import WCMP_SCOPE, wcmp_scope_tree

FAILURES = FailureRequest(
    FailurePolicy(
        modes=[FailureMode(1, [FailureRule("link", mode="all", path="^PA1\\|PB1$")])]
    ),
    1,
    1,
)


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (
            "next_hop",
            {
                ("converged",): [False],
                ("stale",): [],
                ("repair",): [],
                ("converged", "stale", "repair"): [False],
            },
        ),
        (
            "group",
            {
                ("converged",): [False],
                ("stale",): [],
                ("repair",): [True],
                ("converged", "stale", "repair"): [False, True],
            },
        ),
    ],
)
def test_tables_are_built_per_recomputing_state_only(scope, expected, monkeypatch):
    trees = {"g": wcmp_scope_tree()} if scope == "group" else {}
    prep = prepared(
        WCMP_SCOPE,
        "^(P|Q)(A|B)[12]$",
        "^DC",
        [demand("^DC$", "^DCB$", 100)],
        scope=scope,
        q=1,
        trees=trees,
    )
    built = []
    real = controller.destination_table

    def counting(*args, **kwargs):
        built.append(kwargs.get("repair", False))
        return real(*args, **kwargs)

    monkeypatch.setattr(controller, "destination_table", counting)
    for states, repairs in expected.items():
        built.clear()
        analysis = place(
            prep,
            PlacementQuery(
                prep.demand_sets["d"], states=states, failures=FAILURES, workers=1
            ),
        )
        assert [case.case.kind for case in analysis.cases] == ["baseline", "failure"]
        # Each built table is the failure case's, one per state that recomputes it.
        assert built == repairs, states
