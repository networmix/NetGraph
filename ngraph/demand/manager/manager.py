"""Traffic demand management and placement.

`TrafficManager` expands `TrafficDemand` specs into concrete `Demand` objects,
builds a working `StrictMultiDiGraph` from a `Network`, and places flows via
per-demand `FlowPolicy` instances.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Tuple, Union

from ngraph.algorithms.flow_init import init_flow_graph
from ngraph.demand import Demand
from ngraph.demand.manager.expand import expand_demands as expand_demands_helper
from ngraph.demand.manager.schedule import place_demands_round_robin
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph
from ngraph.model.network import Network

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from ngraph.demand.matrix import TrafficMatrixSet  # pragma: no cover
    from ngraph.model.view import NetworkView  # pragma: no cover


def _new_td_map() -> Dict[str, List[Demand]]:
    """Return a new mapping from TrafficDemand id to expanded demands.

    Returns:
        Empty mapping with the correct type for ``_td_to_demands``.
    """
    return {}


class TrafficResult(NamedTuple):
    """Traffic demand result entry.

    Attributes:
        priority: Demand priority class (lower value is more critical).
        total_volume: Total traffic volume for this entry.
        placed_volume: Volume actually placed in the flow graph.
        unplaced_volume: Volume not placed (``total_volume - placed_volume``).
        src: Source node or path.
        dst: Destination node or path.
    """

    priority: int
    total_volume: float
    placed_volume: float
    unplaced_volume: float
    src: str
    dst: str


@dataclass
class TrafficManager:
    """Manage expansion and placement of traffic demands on a `Network`.

     This class:

      1) Builds (or rebuilds) a StrictMultiDiGraph from the given Network.
       2) Expands each TrafficDemand into one or more Demand objects based
          on a configurable 'mode' ("combine" or "pairwise").
      3) Each Demand is associated with a FlowPolicy, which handles how flows
         are placed (split across paths, balancing, etc.).
         4) Provides methods to place all demands incrementally with optional
          re-optimization, reset usage, and retrieve flow/usage summaries.

     Auto rounds semantics:
       - placement_rounds="auto" performs up to a small number of fairness passes
         (at most 3), with early stop when diminishing returns are detected. Each
         pass asks the scheduler to place full leftovers without step splitting.

    In particular:
      - 'combine' mode:
        * Combine all matched sources into a single pseudo-source node, and all
          matched sinks into a single pseudo-sink node (named using the traffic
          demand's `source_path` and `sink_path`). A single Demand is created
          from the pseudo-source to the pseudo-sink, with the full volume.

       - 'pairwise' mode:
        * All matched sources form one group, all matched sinks form another group.
          A separate Demand is created for each (src_node, dst_node) pair,
          skipping self-pairs. The total volume is split evenly across the pairs.

    The sum of volumes of all expanded Demands for a given TrafficDemand matches
    that TrafficDemand's `demand` value (unless no valid node pairs exist, in which
    case no demands are created).

    Attributes:
        network (Union[Network, NetworkView]): The underlying network or view object.
        traffic_matrix_set (TrafficMatrixSet): Traffic matrices containing demands.
        matrix_name (Optional[str]): Name of specific matrix to use, or None for default.
        default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
            a TrafficDemand does not specify one.
        graph (StrictMultiDiGraph): Active graph built from the network.
        demands (List[Demand]): All expanded demands from the active matrix.
        _td_to_demands (Dict[str, List[Demand]]): Internal mapping from
            TrafficDemand.id to its expanded Demand objects.
    """

    network: Union[Network, "NetworkView"]
    traffic_matrix_set: "TrafficMatrixSet"
    matrix_name: Optional[str] = None
    default_flow_policy_config: FlowPolicyConfig = FlowPolicyConfig.SHORTEST_PATHS_ECMP

    graph: Optional[StrictMultiDiGraph] = None
    demands: List[Demand] = field(default_factory=list)
    _td_to_demands: Dict[str, List[Demand]] = field(default_factory=_new_td_map)

    def _get_traffic_demands(self) -> List[TrafficDemand]:
        """Return traffic demands from the matrix set.

        Returns:
            Traffic demands from the specified matrix or the default matrix.
        """
        if self.matrix_name:
            return self.traffic_matrix_set.get_matrix(self.matrix_name)
        else:
            return self.traffic_matrix_set.get_default_matrix()

    def build_graph(self, add_reverse: bool = True) -> None:
        """Build or rebuild the internal `StrictMultiDiGraph` from ``network``.

        Also initializes flow-related edge attributes (for example, ``flow=0``).

        Args:
            add_reverse: If True, for every link A->B, add a mirrored link B->A
                with the same capacity and cost.
        """
        self.graph = self.network.to_strict_multidigraph(
            add_reverse=add_reverse, compact=True
        )
        init_flow_graph(self.graph)  # Initialize flow-related attributes

    def expand_demands(self) -> None:
        """Expand each `TrafficDemand` into one or more `Demand` objects.

        The expanded demands are stored in ``demands``, sorted by ascending
        ``demand_class`` (priority). Also populates ``_td_to_demands[td.id]``.

        Raises:
            ValueError: If an unknown mode is encountered.
        """
        expanded, td_map = expand_demands_helper(
            network=self.network,
            graph=self.graph,
            traffic_demands=self._get_traffic_demands(),
            default_flow_policy_config=self.default_flow_policy_config,
        )
        self._td_to_demands = td_map
        self.demands = expanded

    def place_all_demands(
        self,
        placement_rounds: Union[int, str] = "auto",
        reoptimize_after_each_round: bool = False,
    ) -> float:
        """Place all expanded demands in ascending priority order.

        Uses multiple incremental rounds per priority class. Optionally
        re-optimizes after each round.

        Args:
            placement_rounds: Number of passes per priority class. If ``"auto"``,
                choose using a heuristic based on total demand and capacity.
            reoptimize_after_each_round: Remove and re-place each demand after
                the round to better share capacity.

        Returns:
            Total volume successfully placed across all demands.

        Raises:
            RuntimeError: If the graph has not been built yet.
        """
        if self.graph is None:
            raise RuntimeError("Graph not built yet. Call build_graph() first.")

        if isinstance(placement_rounds, str) and placement_rounds.lower() == "auto":
            # Simple, reliable auto: up to 3 passes with early stop.
            from ngraph.algorithms.base import MIN_FLOW

            total_placed = 0.0
            max_auto_rounds = 3
            for _ in range(max_auto_rounds):
                placed_now = place_demands_round_robin(
                    graph=self.graph,
                    demands=self.demands,
                    placement_rounds=1,
                    reoptimize_after_each_round=False,
                )
                total_placed += placed_now

                # Early stops: no progress or negligible leftover
                if placed_now < MIN_FLOW:
                    break

                leftover_total = sum(
                    max(0.0, d.volume - d.placed_demand) for d in self.demands
                )
                if leftover_total < 0.05 * placed_now:
                    break

                # Fairness check: if served ratios are already close, stop
                served = [
                    (d.placed_demand / d.volume)
                    for d in self.demands
                    if d.volume > 0.0 and (d.volume - d.placed_demand) >= MIN_FLOW
                ]
                if served:
                    s_min, s_max = min(served), max(served)
                    if s_max <= 0.0 or s_min >= 0.8 * s_max:
                        break
        else:
            # Ensure placement_rounds is an int for range() and arithmetic operations
            placement_rounds_int = (
                int(placement_rounds)
                if isinstance(placement_rounds, str)
                else placement_rounds
            )

            if placement_rounds_int <= 0:
                raise ValueError("placement_rounds must be positive")

            total_placed = place_demands_round_robin(
                graph=self.graph,
                demands=self.demands,
                placement_rounds=placement_rounds_int,
                reoptimize_after_each_round=reoptimize_after_each_round,
            )

        # Update each TrafficDemand's placed volume
        for td in self._get_traffic_demands():
            dlist = self._td_to_demands.get(td.id, [])
            td.demand_placed = sum(d.placed_demand for d in dlist)

        return total_placed

    def reset_all_flow_usages(self) -> None:
        """Remove flow usage for each demand and reset placements to 0.

        Also sets ``TrafficDemand.demand_placed`` to 0 for each top-level demand.
        """
        if self.graph is None:
            return

        # First, remove flows for currently tracked demands to reset internal
        # policy state (placed_flow counters) without destroying flow objects.
        for dmd in self.demands:
            if dmd.flow_policy:
                dmd.flow_policy.remove_demand(self.graph)
            dmd.placed_demand = 0.0

        # Then, ensure the graph itself is clean of any stray flows that may have
        # been created by previously expanded demands (no longer referenced).
        # This guarantees a full graph-level reset regardless of demand set churn.
        from ngraph.algorithms.flow_init import init_flow_graph

        init_flow_graph(self.graph, reset_flow_graph=True)

        for td in self._get_traffic_demands():
            td.demand_placed = 0.0

    def get_flow_details(self) -> Dict[Tuple[int, int], Dict[str, object]]:
        """Summarize flows from each demand's policy.

        Returns:
            Mapping keyed by ``(demand_index, flow_index)``; each value includes
            ``placed_flow``, ``src_node``, ``dst_node``, and ``edges``.
        """
        details: Dict[Tuple[int, int], Dict[str, object]] = {}
        for i, dmd in enumerate(self.demands):
            if not dmd.flow_policy:
                continue
            for j, (_f_idx, flow_obj) in enumerate(dmd.flow_policy.flows.items()):
                details[(i, j)] = {
                    "placed_flow": flow_obj.placed_flow,
                    "src_node": flow_obj.src_node,
                    "dst_node": flow_obj.dst_node,
                    "edges": list(flow_obj.path_bundle.edges),
                }
        return details

    def summarize_link_usage(self) -> Dict[str, float]:
        """Return total flow usage per edge in the graph.

        Returns:
            Mapping from ``edge_key`` to current flow on that edge.
        """
        usage: Dict[str, float] = {}
        if self.graph is None:
            return usage

        for edge_key, edge_tuple in self.graph.get_edges().items():
            attr_dict = edge_tuple[3]
            usage[str(edge_key)] = attr_dict.get("flow", 0.0)

        return usage

    def get_traffic_results(self, detailed: bool = False) -> List[TrafficResult]:
        """Return traffic demand summaries.

        If ``detailed`` is False, return one entry per top-level `TrafficDemand`.
        If True, return one entry per expanded `Demand`.

        Args:
            detailed: Whether to return per-expanded-demand data instead of
                top-level aggregated data.

        Returns:
            List of ``TrafficResult`` entries.
        """
        results: List[TrafficResult] = []

        if not detailed:
            # Summaries for top-level TrafficDemands
            for td in self._get_traffic_demands():
                total_volume = td.demand
                placed_volume = td.demand_placed
                unplaced_volume = total_volume - placed_volume

                # For aggregated results, we return the original src/dst "paths."
                results.append(
                    TrafficResult(
                        priority=td.priority,
                        total_volume=total_volume,
                        placed_volume=placed_volume,
                        unplaced_volume=unplaced_volume,
                        src=td.source_path,
                        dst=td.sink_path,
                    )
                )
        else:
            # Summaries for each expanded Demand
            for dmd in self.demands:
                total_volume = dmd.volume
                placed_volume = dmd.placed_demand
                unplaced_volume = total_volume - placed_volume

                results.append(
                    TrafficResult(
                        priority=dmd.demand_class,
                        total_volume=total_volume,
                        placed_volume=placed_volume,
                        unplaced_volume=unplaced_volume,
                        src=str(dmd.src_node),
                        dst=str(dmd.dst_node),
                    )
                )

        return results

    def _reoptimize_priority_demands(self, demands_in_prio: List[Demand]) -> None:
        # Retained for backward-compat within this class; internal only. The
        # scheduling module provides its own implementation.
        if self.graph is None:
            return
        for dmd in demands_in_prio:
            if not dmd.flow_policy:
                continue
            placed_volume = dmd.placed_demand
            dmd.flow_policy.remove_demand(self.graph)
            dmd.flow_policy.place_demand(
                self.graph,
                dmd.src_node,
                dmd.dst_node,
                dmd.demand_class,
                placed_volume,
            )
            dmd.placed_demand = dmd.flow_policy.placed_demand

    def _estimate_rounds(self) -> int:
        """Estimate a suitable number of placement rounds.

        Compares median demand volume with median edge capacity. Falls back to
        a default when data is insufficient.

        Returns:
            Estimated number of rounds to use for traffic placement.
        """
        from ngraph.config import TRAFFIC_CONFIG

        if not self.demands:
            return TRAFFIC_CONFIG.default_rounds

        demand_volumes = [demand.volume for demand in self.demands if demand.volume > 0]
        if not demand_volumes:
            return TRAFFIC_CONFIG.default_rounds

        median_demand = statistics.median(demand_volumes)

        if not self.graph:
            return TRAFFIC_CONFIG.default_rounds

        edges = self.graph.get_edges().values()
        capacities = [
            edge_data[3].get("capacity", 0)
            for edge_data in edges
            if edge_data[3].get("capacity", 0) > 0
        ]
        if not capacities:
            return TRAFFIC_CONFIG.default_rounds

        median_capacity = statistics.median(capacities)
        ratio = median_demand / median_capacity
        return TRAFFIC_CONFIG.estimate_rounds(ratio)
