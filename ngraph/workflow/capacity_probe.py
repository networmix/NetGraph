from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Tuple, Pattern
from ngraph.workflow.base import WorkflowStep, register_workflow_step
from ngraph.lib.algorithms.base import FlowPlacement

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@register_workflow_step("CapacityProbe")
@dataclass
class CapacityProbe(WorkflowStep):
    """
    A workflow step that probes capacity (max flow) between selected groups of nodes.

    Attributes:
        source_path (str): A regex pattern to select source node groups.
        sink_path (str): A regex pattern to select sink node groups.
        mode (str): "combine" or "pairwise" (defaults to "combine").
            - "combine": All matched sources form one super-source; all matched sinks form one super-sink.
            - "pairwise": Compute flow for each (source_group, sink_group).
        probe_reverse (bool): If True, also compute flow in the reverse direction (sink→source).
        shortest_path (bool): If True, only use shortest paths when computing flow.
        flow_placement (FlowPlacement): Handling strategy for parallel equal cost paths (default PROPORTIONAL).
    """

    source_path: Pattern[str] = ""
    sink_path: Pattern[str] = ""
    mode: str = "combine"
    probe_reverse: bool = False
    shortest_path: bool = False
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL

    def __post_init__(self):
        if isinstance(self.flow_placement, str):
            try:
                self.flow_placement = FlowPlacement[self.flow_placement.upper()]
            except KeyError:
                valid_values = ", ".join([e.name for e in FlowPlacement])
                raise ValueError(
                    f"Invalid flow_placement '{self.flow_placement}'. "
                    f"Valid values are: {valid_values}"
                )

    def run(self, scenario: Scenario) -> None:
        """
        Executes the capacity probe by computing max flow between node groups
        matched by source_path and sink_path. Results are stored in scenario.results.

        Depending on 'mode', the returned flow is either a single combined dict entry
        or multiple pairwise entries. If 'probe_reverse' is True, flow is computed
        in both directions (forward and reverse).

        Args:
            scenario (Scenario): The scenario object containing the network and results.
        """
        # 1) Forward direction (source_path -> sink_path)
        fwd_flow_dict = scenario.network.max_flow(
            source_path=self.source_path,
            sink_path=self.sink_path,
            mode=self.mode,
            shortest_path=self.shortest_path,
            flow_placement=self.flow_placement,
        )
        self._store_flow_dict(
            scenario=scenario,
            flow_dict=fwd_flow_dict,
        )

        # 2) Reverse direction (if enabled)
        if self.probe_reverse:
            rev_flow_dict = scenario.network.max_flow(
                source_path=self.sink_path,
                sink_path=self.source_path,
                mode=self.mode,
                shortest_path=self.shortest_path,
                flow_placement=self.flow_placement,
            )
            self._store_flow_dict(
                scenario=scenario,
                flow_dict=rev_flow_dict,
            )

    def _store_flow_dict(
        self,
        scenario: Scenario,
        flow_dict: Dict[Tuple[str, str], float],
    ) -> None:
        """
        Stores the flow dictionary in the scenario's results container, labeling
        each entry consistently. For each (src_label, snk_label) in the flow_dict,
        we store: "max_flow:[src_label -> snk_label]".

        Args:
            scenario (Scenario): The scenario that holds the results.
            flow_dict (Dict[Tuple[str, str], float]): Mapping of (src_label, snk_label) to flow.
        """
        for (src_label, snk_label), flow_value in flow_dict.items():
            result_label = f"max_flow:[{src_label} -> {snk_label}]"
            scenario.results.put(self.name, result_label, flow_value)
