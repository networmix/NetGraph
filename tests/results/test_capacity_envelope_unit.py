"""Unit tests for CapacityEnvelope aggregation and deserialization edge cases."""

from __future__ import annotations

from collections import namedtuple

import pytest

from ngraph.results.artifacts import CapacityEnvelope


def test_aggregate_frequencies_count_duplicates() -> None:
    """Frequency counting (Counter-based) matches duplicate volumes exactly."""
    Summary = namedtuple("Summary", ["cost_distribution", "min_cut"])
    summaries = [
        Summary(cost_distribution={1.0: 5.0}, min_cut=[]),
        Summary(cost_distribution={1.0: 5.0}, min_cut=[]),
        Summary(cost_distribution={1.0: 7.0}, min_cut=[]),
    ]

    env = CapacityEnvelope.from_values(
        source_pattern="S",
        sink_pattern="T",
        mode="combine",
        values=[1.0, 2.0, 3.0],
        flow_summaries=summaries,
    )

    freqs = env.flow_summary_stats["cost_distribution_stats"][1.0]["frequencies"]
    assert freqs == {5.0: 2, 7.0: 1}


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
