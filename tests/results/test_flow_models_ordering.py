from __future__ import annotations

from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary


def test_flow_iteration_result_preserves_flow_order_and_counts() -> None:
    e1 = FlowEntry("S1", "D1", 0, 1.0, 1.0, 0.0)
    e2 = FlowEntry("S2", "D2", 1, 2.0, 1.5, 0.5)
    s = FlowSummary(3.0, 2.5, 2.5 / 3.0, 1, 2)
    it = FlowIterationResult(failure_id="f0", flows=[e1, e2], summary=s)
    d = it.to_dict()
    flows = d["flows"]
    assert flows[0]["source"] == "S1" and flows[1]["source"] == "S2"
    assert d["summary"]["num_flows"] == 2
