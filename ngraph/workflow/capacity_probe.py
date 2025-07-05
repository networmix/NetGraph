"""Capacity probing workflow component."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, Iterable, Tuple

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.network_view import NetworkView
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario


@dataclass
class CapacityProbe(WorkflowStep):
    """A workflow step that probes capacity (max flow) between selected groups of nodes.

    Supports optional exclusion simulation using NetworkView without modifying the base network.

    YAML Configuration:
        ```yaml
        workflow:
          - step_type: CapacityProbe
            name: "capacity_probe_analysis"  # Optional: Custom name for this step
            source_path: "^datacenter/.*"    # Regex pattern to select source node groups
            sink_path: "^edge/.*"            # Regex pattern to select sink node groups
            mode: "combine"                  # "combine" or "pairwise" flow analysis
            probe_reverse: false             # Also compute flow in reverse direction
            shortest_path: false             # Use shortest paths only
            flow_placement: "PROPORTIONAL"   # "PROPORTIONAL" or "EQUAL_BALANCED"
            excluded_nodes: ["node1", "node2"] # Optional: Nodes to exclude for analysis
            excluded_links: ["link1"]          # Optional: Links to exclude for analysis
        ```

    Attributes:
        source_path: A regex pattern to select source node groups.
        sink_path: A regex pattern to select sink node groups.
        mode: "combine" or "pairwise" (defaults to "combine").
            - "combine": All matched sources form one super-source; all matched sinks form one super-sink.
            - "pairwise": Compute flow for each (source_group, sink_group).
        probe_reverse: If True, also compute flow in the reverse direction (sink→source).
        shortest_path: If True, only use shortest paths when computing flow.
        flow_placement: Handling strategy for parallel equal cost paths (default PROPORTIONAL).
        excluded_nodes: Optional list of node names to exclude (temporary exclusion).
        excluded_links: Optional list of link IDs to exclude (temporary exclusion).
    """

    source_path: str = ""
    sink_path: str = ""
    mode: str = "combine"
    probe_reverse: bool = False
    shortest_path: bool = False
    flow_placement: FlowPlacement = FlowPlacement.PROPORTIONAL
    excluded_nodes: Iterable[str] = ()
    excluded_links: Iterable[str] = ()

    def __post_init__(self):
        if isinstance(self.flow_placement, str):
            try:
                self.flow_placement = FlowPlacement[self.flow_placement.upper()]
            except KeyError:
                valid_values = ", ".join([e.name for e in FlowPlacement])
                raise ValueError(
                    f"Invalid flow_placement '{self.flow_placement}'. "
                    f"Valid values are: {valid_values}"
                ) from None

    def run(self, scenario: Scenario) -> None:
        """Executes the capacity probe by computing max flow between node groups
        matched by source_path and sink_path. Results are stored in scenario.results.

        If excluded_nodes or excluded_links are specified, uses NetworkView to simulate
        exclusions without modifying the base network.

        Depending on 'mode', the returned flow is either a single combined dict entry
        or multiple pairwise entries. If 'probe_reverse' is True, flow is computed
        in both directions (forward and reverse).

        Args:
            scenario (Scenario): The scenario object containing the network and results.
        """
        # Create view if we have exclusions, otherwise use base network
        if self.excluded_nodes or self.excluded_links:
            network_or_view = NetworkView.from_excluded_sets(
                scenario.network,
                excluded_nodes=self.excluded_nodes,
                excluded_links=self.excluded_links,
            )
        else:
            network_or_view = scenario.network

        # 1) Forward direction (source_path -> sink_path)
        fwd_flow_dict = network_or_view.max_flow(
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
            rev_flow_dict = network_or_view.max_flow(
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
        """Stores the flow dictionary in the scenario's results container, labeling
        each entry consistently. For each (src_label, snk_label) in the flow_dict,
        we store: "max_flow:[src_label -> snk_label]".

        Args:
            scenario (Scenario): The scenario that holds the results.
            flow_dict (Dict[Tuple[str, str], float]): Mapping of (src_label, snk_label) to flow.
        """
        for (src_label, snk_label), flow_value in flow_dict.items():
            result_label = f"max_flow:[{src_label} -> {snk_label}]"
            scenario.results.put(self.name, result_label, flow_value)


# Register the class after definition to avoid decorator ordering issues
register_workflow_step("CapacityProbe")(CapacityProbe)
