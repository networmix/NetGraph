"""Tests for CapacityEnvelope flow summary aggregation.

Validates aggregation of cost distributions and min-cut frequencies from
provided FlowSummary-like objects.
"""

from __future__ import annotations

import json
from collections import namedtuple

from ngraph.results.artifacts import CapacityEnvelope


def test_aggregate_flow_summaries_cost_and_min_cut() -> None:
    """Aggregate multiple summaries and validate computed statistics."""
    Summary = namedtuple("Summary", ["cost_distribution", "min_cut"])

    # Two summaries with overlapping costs and min-cut edges
    s1 = Summary(cost_distribution={1.0: 5.0, 2.0: 3.0}, min_cut=[("u", "v", "e1")])
    s2 = Summary(
        cost_distribution={1.0: 7.0, 3.0: 2.0},
        min_cut=[("u", "v", "e1"), ("x", "y", "e2")],
    )

    env = CapacityEnvelope.from_values(
        source_pattern="S",
        sink_pattern="T",
        mode="combine",
        values=[10.0, 20.0],  # arbitrary values, not used by aggregation
        flow_summaries=[s1, s2],
    )

    stats = env.flow_summary_stats
    assert "cost_distribution_stats" in stats
    cds = stats["cost_distribution_stats"]

    # Validate means over volumes
    # cost 1.0 has [5.0, 7.0] -> mean 6.0, min 5.0, max 7.0, total_samples 2
    assert 1.0 in cds
    assert cds[1.0]["mean"] == 6.0
    assert cds[1.0]["min"] == 5.0
    assert cds[1.0]["max"] == 7.0
    assert cds[1.0]["total_samples"] == 2
    # frequencies should count occurrences
    assert cds[1.0]["frequencies"][5.0] == 1
    assert cds[1.0]["frequencies"][7.0] == 1

    # cost 2.0 only appears once
    assert cds[2.0]["mean"] == 3.0
    assert cds[2.0]["min"] == 3.0
    assert cds[2.0]["max"] == 3.0
    assert cds[2.0]["total_samples"] == 1

    # Validate min-cut edge frequency counting
    mcf = stats["min_cut_frequencies"]
    assert mcf[str(("u", "v", "e1"))] == 2  # appears in both summaries
    assert mcf[str(("x", "y", "e2"))] == 1

    # Ensure the whole envelope dict is JSON-serializable with stats included
    d = env.to_dict()
    assert "flow_summary_stats" in d
    json.dumps(d)
