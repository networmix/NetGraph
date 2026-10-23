"""Directed-edge sensitivity of one native model at a fixed question."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import netgraph_core as ngc

from ngraph.analysis.capacity import (
    evaluation_options,
    question_kind,
    validate_capacity_inputs,
)
from ngraph.analysis.demands import selected_pairs
from ngraph.analysis.failures import Workers, resolve_workers
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.precision import query_inputs, query_miss
from ngraph.model.selectors import Selector
from ngraph.results import OutputSelection, ReportLocation, SensitivityAnalysis
from ngraph.utils.values import physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class SensitivityQuery:
    source: Selector
    target: Selector
    config: ngc.FlowPolicyConfig
    offer: float | None = None
    design_demand: float | None = None
    eligibility: ngc.Eligibility | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)

    export_details: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.export_details, bool):
            raise ValueError("export_details: expected bool")
        validate_capacity_inputs(
            self.source,
            self.target,
            self.config,
            self.offer,
            self.design_demand,
            self.outputs,
        )
        if self.offer is not None:
            object.__setattr__(self, "offer", physical(self.offer, "sensitivity.offer"))
        if self.design_demand is not None:
            object.__setattr__(
                self,
                "design_demand",
                physical(self.design_demand, "sensitivity.design_demand"),
            )
        if self.eligibility is not None and not isinstance(
            self.eligibility, ngc.Eligibility
        ):
            raise TypeError("sensitivity.eligibility: expected native Eligibility")
        if self.workers != "auto":
            resolve_workers(self.workers)


def edge_sensitivity(
    prepared: PreparedScenario, query: SensitivityQuery
) -> SensitivityAnalysis:
    topology = prepared.topology
    (pair,) = selected_pairs(
        prepared.scenario.network, query.source, query.target, "combine", "sensitivity"
    )
    if pair.sources == pair.destinations:
        raise ValueError("sensitivity: source and target must be disjoint")
    question, source = question_kind(query.config, query.offer, query.design_demand)
    if question == "first_hop_experiment" or (
        query.config.admission == ngc.Admission.LOSSY and source == "unlimited"
    ):
        raise ValueError("sensitivity: LOSSY requires a fixed finite offer")
    if query.config.admission == ngc.Admission.LOSSLESS and query.offer is not None:
        raise ValueError(
            "sensitivity: LOSSLESS requires the uncapped capacity question"
        )
    assert source != "first_hop"
    mask = (
        topology.disabled
        if query.eligibility is None
        else ngc.Eligibility.intersect(topology.disabled, query.eligibility)
    )
    workers = resolve_workers(query.workers)
    options = evaluation_options(
        topology, query.config, query.offer, query.design_demand, mask, query.outputs
    )
    result = ngc.evaluate_edge_failures(
        topology.graph,
        [topology.node_id_by_name[name] for name in pair.sources],
        [topology.node_id_by_name[name] for name in pair.destinations],
        options,
        workers=workers,
    )
    baseline = result.baseline
    entries = result.entries
    observations = [(pair, baseline.delivered, mask, "sensitivity.baseline", None)]
    observations.extend(
        (
            pair,
            baseline.delivered - entry.delivery_reduction,
            ngc.Eligibility.intersect(
                mask, topology.graph.eligibility(excluded_edges=[entry.edge])
            ),
            f"sensitivity.edge[{entry.edge}]",
            None,
        )
        for entry in entries
    )
    miss = query_miss(
        prepared,
        query,
        observations,
        ReportLocation(None, "baseline", None),
        query_inputs(prepared, query, "sensitivity"),
    )
    return SensitivityAnalysis(
        prepared,
        () if miss is None else (miss,),
        analysis_metadata(workers),
        OutputSelection(query.outputs, False, query.export_details),
        pair,
        question,
        source,
        result,
        query,
    )
