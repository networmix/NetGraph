"""Capacity workflows ask explicit native questions and retain failed cases."""

import json
from io import StringIO

import netgraph_core as ngc
import pytest

from ngraph.analysis.units import UnitsSettings
from ngraph.export import write_json
from ngraph.model.demand import FlowPolicyPreset
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.max_flow_step import MaxFlow
from tests.question import asked


def _run(**controls):
    step = MaxFlow(
        name="capacity",
        source=Selector("^A$"),
        target=Selector("^C$"),
        **({"preset": FlowPolicyPreset.SHORTEST_PATHS_ECMP} | controls),
    )
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    network.add_link(Link("A", "B", 2, 1))
    network.add_link(Link("B", "C", 2, 2))
    network.add_link(Link("A", "C", 3, 5))
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("node", path="^B$")], {"label": "down"})]
    )
    prepared = prepare(
        Scenario(
            network, (step,), failure_policies={"down": policy}, units=UnitsSettings(1)
        )
    )
    return prepared, run(prepared)


class TestMaxFlowStep:
    def test_initialization_defaults(self):
        step = MaxFlow(source=Selector("^A$"), target=Selector("^C$"))
        assert step.source.path == "^A$" and step.target.path == "^C$"
        assert step.mode == "combine" and step.failure_policy is None
        assert step.iterations == 1 and step.workers == "auto"
        assert step.seed is None and step.failure_trace is False
        assert step.declaration == FlowPolicyPreset.TE_MAXFLOW_UNLIM
        assert not step.export_cost_distribution and not step.outputs.edge_flows

    def test_initialization_custom_values(self):
        step = MaxFlow(
            source=Selector("^src$"),
            target=Selector("^dst$"),
            mode="pairwise",
            failure_policy="down",
            iterations=100,
            workers=4,
            preset=FlowPolicyPreset.TE_MAXFLOW_UNLIM,
            seed=42,
            failure_trace=True,
            outputs=ngc.OutputOptions(edge_flows=True),
            export_cost_distribution=True,
        )
        assert step.mode == "pairwise" and step.failure_policy == "down"
        assert step.iterations == 100 and step.workers == 4 and step.seed == 42
        assert (
            step.failure_trace
            and step.outputs.edge_flows
            and step.export_cost_distribution
        )
        assert step.declaration == FlowPolicyPreset.TE_MAXFLOW_UNLIM

    @pytest.mark.parametrize(
        "controls",
        [
            {"iterations": -1},
            {"workers": 0},
            {"workers": 2.5},
            {"workers": True},
            {"workers": "4"},
            {"mode": "invalid"},
        ],
    )
    def test_validation_errors(self, controls):
        with pytest.raises(ValueError):
            MaxFlow(source=Selector("^A$"), target=Selector("^C$"), **controls)
        assert (
            _run(workers=1)[1]
            .steps[0]
            .result.cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 2
        )

    def test_run_records_native_question_and_result(self):
        _, result = _run(workers=1)
        (step,) = result.steps
        assert step.name == "capacity" and step.step_type == "MaxFlow"
        assert step.question.source.path == "^A$" and step.question.target.path == "^C$"
        assert step.question.mode == "combine"
        assert asked(step)["model"]["routing"] == "shortest_paths"
        assert asked(step)["model"]["allocation"] == "equal"
        assert asked(step)["model"]["source_allocation"] == "equal"
        assert asked(step)["model"]["admission"] == "lossless"
        assert step.result.kind == "capacity"
        (baseline,) = step.result.cases
        assert baseline.case.id == "baseline" and baseline.case.occurrences == 1
        assert baseline.states["converged"].rows[0].result.delivered == 2

    def test_run_with_failure_patterns(self):
        _, result = _run(failure_policy="down", iterations=2, workers=2)
        baseline, failed = result.steps[0].result.cases
        assert baseline.case.pattern.excluded_nodes == ()
        assert failed.case.pattern.excluded_nodes == ("B",)
        assert failed.case.occurrences == 2
        # Each failure derives its own shortest support: direct A-C now carries3.
        assert [
            case.states["converged"].rows[0].result.delivered
            for case in (baseline, failed)
        ] == [2, 3]

    def test_capacity_workflow_exports_question_and_cases(self):
        _, result = _run(failure_policy="down", iterations=2, workers=1)
        output = StringIO()
        write_json(result, output)
        step = json.loads(output.getvalue())["steps"][0]
        assert step["name"] == "capacity" and step["execution_order"] == 0
        assert step["question"]["kind"] == step["result"]["kind"] == "capacity"
        assert [case["case"]["occurrences"] for case in step["result"]["cases"]] == [
            0,
            2,
        ]

    def test_requested_native_details_and_opt_in_cost_distribution(self):
        prepared, result = _run(
            preset=FlowPolicyPreset.TE_MAXFLOW_UNLIM,
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=True, min_cut=True),
            export_cost_distribution=True,
        )
        (row,) = result.steps[0].result.cases[0].states["converged"].rows
        actual = {
            (ref.link, ref.direction): int(value)
            for ref, value in zip(
                prepared.topology.edge_refs, row.result.edge_flows, strict=True
            )
        }
        assert actual == {
            ("A|B|0", "forward"): 2,
            ("A|B|0", "reverse"): 0,
            ("B|C|0", "forward"): 2,
            ("B|C|0", "reverse"): 0,
            ("A|C|0", "forward"): 3,
            ("A|C|0", "reverse"): 0,
        }
        assert row.result.delivered == 5 and row.result.min_cut is not None
        assert row.cost_distribution.kind == "marginal_curve"
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(3, 2), (5, 3)]
        default_row = (
            _run(workers=1)[1].steps[0].result.cases[0].states["converged"].rows[0]
        )
        assert (
            default_row.cost_distribution
            is default_row.result.edge_flows
            is default_row.result.min_cut
            is None
        )

    def test_failure_trace_persisted_on_results(self):
        _, result = _run(
            failure_policy="down", iterations=2, workers=2, seed=42, failure_trace=True
        )
        step = result.steps[0]
        assert step.step_seed == 42 and step.question.failures.policy_name == "down"
        trace = step.result.cases[1].case.trace
        assert trace.mode_index == 0 and dict(trace.mode_attrs) == {"label": "down"}
        assert trace.selections[0].selected == ("B",)
        output = StringIO()
        write_json(result, output)
        wire = json.loads(output.getvalue())["steps"][0]["result"]["cases"][1]["case"][
            "trace"
        ]
        assert wire["mode_index"] == 0 and wire["selections"][0]["selected"] == ["B"]

    def test_no_failure_trace_when_disabled(self):
        _, result = _run(failure_policy="down", iterations=2, workers=1)
        assert all(case.case.trace is None for case in result.steps[0].result.cases)
        output = StringIO()
        write_json(result, output)
        assert all(
            "trace" not in case["case"]
            for case in json.loads(output.getvalue())["steps"][0]["result"]["cases"]
        )
