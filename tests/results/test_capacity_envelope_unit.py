"""Unit tests for CapacityEnvelope.from_dict frequency-key handling."""

from __future__ import annotations

import pytest

from ngraph.results.artifacts import CapacityEnvelope


def test_from_dict_rejects_non_numeric_frequency_key() -> None:
    with pytest.raises(ValueError):
        CapacityEnvelope.from_dict(
            {
                "source": "S",
                "sink": "T",
                "mode": "combine",
                "frequencies": {"not-a-number": 1},
            }
        )


def test_from_dict_normalizes_string_keys() -> None:
    env = CapacityEnvelope.from_dict(
        {
            "source": "S",
            "sink": "T",
            "mode": "combine",
            "frequencies": {"10.0": 2, "20": 1},
            "min": 10.0,
            "max": 20.0,
            "mean": 13.33,
            "stdev": 4.71,
            "total_samples": 3,
        }
    )
    assert env.frequencies == {10.0: 2, 20.0: 1}
