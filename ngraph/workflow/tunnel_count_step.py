"""Evaluate each tunnelled TE demand of a set at fixed tunnel counts, design and offer."""

from dataclasses import dataclass, field

import netgraph_core as ngc

from ngraph import results
from ngraph.analysis.counts import TunnelCountQuery, tunnel_counts
from ngraph.analysis.failures import Workers
from ngraph.analysis.preparation import PreparedScenario, StepNeeds
from ngraph.analysis.units import question_inputs
from ngraph.utils.values import _located_error, flag, own, shared_copy, text
from ngraph.workflow.base import (
    WorkflowStep,
    _query_error,
    register_workflow_step,
    step_name,
)


@dataclass
class TunnelCountAnalysis(WorkflowStep):
    """Workflow step: one evaluation per demand and tunnel count (or ``up_to`` limit).

    Every demand uses the same ``design_demand`` and ``offer``; the set's
    declared volumes are not read by the rows, though they still take part in
    choosing the resolution, as every demand set a step names does.
    """

    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    demand_set: str = ""
    counts: tuple[int, ...] = ()
    up_to: int | None = None
    design_demand: float | None = None
    offer: float | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_details: bool = False

    def __post_init__(self):
        super().__post_init__()
        own(self, demand_set=text(self.demand_set, "TunnelCountAnalysis.demand_set"))
        for name in ("design_demand", "offer"):
            if getattr(self, name) is None:
                raise _located_error(
                    ValueError(f"TunnelCountAnalysis.{name}: required"),
                    f"TunnelCountAnalysis.{name}",
                    None,
                )
        # The query validates and normalizes every field it shares with the step.
        try:
            query = self.query_for(
                results.ResolvedDemandSet(self.demand_set, (), (), ())
            )
        except (TypeError, ValueError) as exc:
            raise _query_error(
                exc,
                f"workflow step {step_name(self)}: {exc}",
                "tunnel_counts",
                "TunnelCountAnalysis",
            ) from exc
        for name in ("counts", "up_to", "design_demand", "offer"):
            object.__setattr__(self, name, getattr(query, name))
        own(self, workers=query.workers, export_details=query.export_details)

    def query_for(self, demands) -> TunnelCountQuery:
        assert self.design_demand is not None and self.offer is not None
        return TunnelCountQuery(
            demands,
            self.counts,
            self.design_demand,
            self.offer,
            self.up_to,
            None,
            self.workers,
            self.outputs,
            self.export_details,
        )

    def query(self, prepared: PreparedScenario) -> TunnelCountQuery:
        try:
            return self.query_for(prepared.demand_sets[self.demand_set])
        except (TypeError, ValueError) as exc:
            if type(exc) not in (TypeError, ValueError):
                raise
            raise _query_error(
                exc, str(exc), "tunnel_counts", "TunnelCountAnalysis"
            ) from exc

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        from ngraph.dsl.inputs import OUTPUT_FLAGS, closed

        label = f"workflow step {name}"
        if "export_details" in arguments:
            raise _located_error(
                ValueError(f"{label}: unknown key export_details; use outputs.details"),
                label + ".export_details",
                arguments["export_details"],
            )
        selected = closed(
            arguments.pop("outputs", {}), (*OUTPUT_FLAGS, "details"), f"{label}.outputs"
        )
        flags = {
            key: flag(value, f"{label}.outputs.{key}")
            for key, value in selected.items()
        }
        arguments["export_details"] = flags.pop("details", False)
        arguments["outputs"] = ngc.OutputOptions(**flags)
        if "counts" in arguments:
            if not isinstance(arguments["counts"], list):
                raise _located_error(
                    ValueError(f"{label}.counts: expected a list of integers"),
                    label + ".counts",
                    arguments["counts"],
                )
            arguments["counts"] = tuple(arguments["counts"])
        return arguments

    def needs(self) -> StepNeeds:
        return StepNeeds(
            numerical=True,
            demand_set=self.demand_set,
            inputs=question_inputs(self.offer, self.design_demand, None),
            offer_budget=self.offer,
            counts=self.query,
        )

    def run(self, context: results.StepContext) -> results.StepOutput:
        value = tunnel_counts(context.prepared, self.query(context.prepared))
        return results.StepOutput(value.query, value)


register_workflow_step("TunnelCountAnalysis")(TunnelCountAnalysis)
