"""Native projection fields are checked by the independent finite-flow witness."""

from copy import deepcopy

import jsonschema
import pytest

import ngraph.export as exporting
from tests.results.test_analysis_wire import (
    test_capacity_native_wire_all_amounts_arrays_cuts_and_requested_curve as capacity_oracle,
)
from tests.results.test_report_field_plants import change, field_paths


def at(value, path):
    for key in path:
        value = value[key]
    return value


def test_native_projection_helper_field_plants_are_all_caught(monkeypatch):
    original = exporting._native
    observed = []

    def capture(*args, **kwargs):
        value = original(*args, **kwargs)
        observed.append(deepcopy(value))
        return value

    with monkeypatch.context() as patch:
        patch.setattr(exporting, "_native", capture)
        capacity_oracle()
    (baseline,) = observed
    paths = tuple(field_paths(baseline))
    caught, equivalent = 0, 0
    for path in paths:
        for mode in ("missing", "null", "wrong"):
            if mode == "null" and at(baseline, path) is None:
                # The uncapped result intentionally emits these nulls; the
                # finite-offer, plan and default-output tests distinguish their
                # other applicability states. Null->null is an equivalent plant.
                equivalent += 1
                continue

            def planted(*args, path=path, mode=mode, **kwargs):
                value = original(*args, **kwargs)
                change(value, path, mode)
                return value

            with monkeypatch.context() as patch:
                patch.setattr(exporting, "_native", planted)
                with pytest.raises((AssertionError, jsonschema.ValidationError)):
                    capacity_oracle()
            caught += 1
    capacity_oracle()
    assert caught + equivalent == 3 * len(paths)
    assert equivalent == 6
    print(
        f"NATIVE FIELD PLANTS: {len(paths)} field paths; {caught} caught; {equivalent} equivalent null->null with applicability controls"
    )


def test_wrong_carried_distribution_with_same_total_is_caught(monkeypatch):
    original = exporting._native

    def planted(*args, **kwargs):
        value = original(*args, **kwargs)
        flows = value["edge_flows"]
        positive = [row for row in flows if row["units"] > 0]
        assert len(positive) == 3
        before = sum(row["units"] for row in flows)
        positive[0]["units"] -= 1
        positive[1]["units"] += 1
        assert sum(row["units"] for row in flows) == before
        return value

    with monkeypatch.context() as patch:
        patch.setattr(exporting, "_native", planted)
        with pytest.raises(AssertionError):
            capacity_oracle()
    capacity_oracle()
