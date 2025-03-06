from collections import defaultdict
from dataclasses import dataclass, field
import statistics
from typing import Dict, List, Optional, Tuple, Union, NamedTuple

from ngraph.lib.algorithms import base
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.demand import Demand
from ngraph.lib.flow_policy import FlowPolicyConfig, FlowPolicy, get_flow_policy
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.network import Network, Node
from ngraph.traffic_demand import TrafficDemand


class TrafficResult(NamedTuple):
    """
    A container for traffic demand result data.

    Attributes:
        priority (int): Demand priority class (lower=more critical).
        total_volume (float): Total traffic volume for this entry.
        placed_volume (float): The volume actually placed in the flow graph.
        unplaced_volume (float): The volume not placed (total_volume - placed_volume).
        src (str): Source node/path.
        dst (str): Destination node/path.
    """

    priority: int
    total_volume: float
    placed_volume: float
    unplaced_volume: float
    src: str
    dst: str


@dataclass
class TrafficManager:
    """
    Manages the expansion and placement of traffic demands on a Network.

    This class:

      1) Builds (or rebuilds) a StrictMultiDiGraph from the given Network.
      2) Expands each TrafficDemand into one or more Demand objects based
         on a configurable 'mode' (e.g., 'combine' or 'full_mesh').
      3) Each Demand is associated with a FlowPolicy, which handles how flows
         are placed (split across paths, balancing, etc.).
      4) Provides methods to place all demands incrementally with optional
         re-optimization, reset usage, and retrieve flow/usage summaries.

    In particular:
      - 'combine' mode:
        * Combine all matched sources into a single pseudo-source node, and all
          matched sinks into a single pseudo-sink node (named using the traffic
          demand's `source_path` and `sink_path`). A single Demand is created
          from the pseudo-source to the pseudo-sink, with the full volume.

      - 'full_mesh' mode:
        * All matched sources form one group, all matched sinks form another group.
          A separate Demand is created for each (src_node, dst_node) pair,
          skipping self-pairs. The total volume is split evenly across the pairs.

    The sum of volumes of all expanded Demands for a given TrafficDemand matches
    that TrafficDemand's `demand` value (unless no valid node pairs exist, in which
    case no demands are created).

    Attributes:
        network (Network): The underlying network object.
        traffic_demands (List[TrafficDemand]): The scenario-level demands.
        default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
            a TrafficDemand does not specify one.
        graph (StrictMultiDiGraph): Active graph built from the network.
        demands (List[Demand]): All expanded demands from traffic_demands.
        _td_to_demands (Dict[str, List[Demand]]): Internal mapping from
            TrafficDemand.id to its expanded Demand objects.
    """

    network: Network
    traffic_demands: List[TrafficDemand] = field(default_factory=list)
    default_flow_policy_config: FlowPolicyConfig = FlowPolicyConfig.SHORTEST_PATHS_ECMP

    graph: Optional[StrictMultiDiGraph] = None
    demands: List[Demand] = field(default_factory=list)
    _td_to_demands: Dict[str, List[Demand]] = field(default_factory=dict)

    def build_graph(self, add_reverse: bool = True) -> None:
        """
        Builds or rebuilds the internal StrictMultiDiGraph from self.network.

        This also initializes flow-related edge attributes (e.g., flow=0).

        Args:
            add_reverse (bool): If True, for every link A->B, add a mirrored
                link B->A with the same capacity/cost.
        """
        self.graph = self.network.to_strict_multidigraph(add_reverse=add_reverse)
        init_flow_graph(self.graph)  # Initialize flow-related attributes

    def expand_demands(self) -> None:
        """
        Converts each TrafficDemand in self.traffic_demands into one or more
        Demand objects based on the demand's 'mode'.

        The expanded demands are stored in self.demands, sorted by ascending
        demand_class (priority). Also populates _td_to_demands[td.id] for each
        TrafficDemand.

        Raises:
            ValueError: If an unknown mode is encountered.
        """
        self._td_to_demands.clear()
        expanded: List[Demand] = []

        for td in self.traffic_demands:
            # Gather node groups for source and sink
            src_groups = self.network.select_node_groups_by_path(td.source_path)
            snk_groups = self.network.select_node_groups_by_path(td.sink_path)

            if not src_groups or not snk_groups:
                # No matching nodes; skip
                self._td_to_demands[td.id] = []
                continue

            # Expand demands according to the specified mode
            if td.mode == "combine":
                demands_of_td: List[Demand] = []
                self._expand_combine(demands_of_td, td, src_groups, snk_groups)
                expanded.extend(demands_of_td)
                self._td_to_demands[td.id] = demands_of_td
            elif td.mode == "full_mesh":
                demands_of_td: List[Demand] = []
                self._expand_full_mesh(demands_of_td, td, src_groups, snk_groups)
                expanded.extend(demands_of_td)
                self._td_to_demands[td.id] = demands_of_td
            else:
                raise ValueError(f"Unknown mode: {td.mode}")

        # Sort final demands by ascending demand_class (i.e., priority)
        expanded.sort(key=lambda d: d.demand_class)
        self.demands = expanded

    def place_all_demands(
        self,
        placement_rounds: Union[int, str] = "auto",
        reoptimize_after_each_round: bool = False,
    ) -> float:
        """
        Places all expanded demands in ascending priority order using multiple
        incremental rounds per priority.

        In each priority class:
          - We determine the number of rounds (user-supplied or estimated).
          - We iterate placement_rounds times.
          - In each round, we allocate (leftover / rounds_left) for each demand
            and attempt to place that volume in the flow graph.
          - If no progress was made during a round, we stop early.
          - If reoptimize_after_each_round is True, we remove and re-place
            each demand's flow after the round to better share capacity.

        Args:
            placement_rounds (Union[int, str]): Number of incremental passes per
                priority class. If "auto", a heuristic is used to choose a reasonable
                number based on total demand and total capacity.
            reoptimize_after_each_round (bool): Whether to remove and re-place
                all demands in the same priority after each round for better
                capacity sharing.

        Returns:
            float: Total volume successfully placed across all demands.

        Raises:
            RuntimeError: If the graph has not been built yet.
        """
        if self.graph is None:
            raise RuntimeError("Graph not built yet. Call build_graph() first.")

        if isinstance(placement_rounds, str) and placement_rounds.lower() == "auto":
            placement_rounds = self._estimate_rounds()

        # Group demands by priority class
        prio_map: Dict[int, List[Demand]] = defaultdict(list)
        for dmd in self.demands:
            prio_map[dmd.demand_class].append(dmd)

        total_placed = 0.0
        sorted_priorities = sorted(prio_map.keys())

        for priority_class in sorted_priorities:
            demands_in_class = prio_map[priority_class]

            for round_idx in range(placement_rounds):
                placed_in_this_round = 0.0
                rounds_left = placement_rounds - round_idx

                for demand in demands_in_class:
                    leftover = demand.volume - demand.placed_demand
                    if leftover < base.MIN_FLOW:
                        continue

                    step_to_place = leftover / float(rounds_left)
                    placed_now, _remain = demand.place(
                        flow_graph=self.graph,
                        max_placement=step_to_place,
                    )
                    total_placed += placed_now
                    placed_in_this_round += placed_now

                # Optionally reoptimize flows in this class
                if reoptimize_after_each_round and placed_in_this_round > 0.0:
                    self._reoptimize_priority_demands(demands_in_class)

                # If no progress was made, no need to continue extra rounds
                if placed_in_this_round < base.MIN_FLOW:
                    break

        # Update each TrafficDemand's placed volume
        for td in self.traffic_demands:
            dlist = self._td_to_demands.get(td.id, [])
            td.demand_placed = sum(d.placed_demand for d in dlist)

        return total_placed

    def reset_all_flow_usages(self) -> None:
        """
        Removes flow usage from the graph for each Demand's FlowPolicy
        and resets placed_demand to 0 for all demands.

        Also sets TrafficDemand.demand_placed to 0 for each top-level demand.
        """
        if self.graph is None:
            return

        for dmd in self.demands:
            if dmd.flow_policy:
                dmd.flow_policy.remove_demand(self.graph)
            dmd.placed_demand = 0.0

        for td in self.traffic_demands:
            td.demand_placed = 0.0

    def get_flow_details(self) -> Dict[Tuple[int, int], Dict[str, object]]:
        """
        Summarizes flows from each Demand's FlowPolicy.

        Returns:
            Dict[Tuple[int, int], Dict[str, object]]:
                A dictionary keyed by (demand_index, flow_index). Each value
                includes:
                {
                    "placed_flow": <float>,
                    "src_node": <str>,
                    "dst_node": <str>,
                    "edges": <List[tuple]>
                }
        """
        details: Dict[Tuple[int, int], Dict[str, object]] = {}
        for i, dmd in enumerate(self.demands):
            if not dmd.flow_policy:
                continue
            for f_idx, flow_obj in dmd.flow_policy.flows.items():
                details[(i, f_idx)] = {
                    "placed_flow": flow_obj.placed_flow,
                    "src_node": flow_obj.src_node,
                    "dst_node": flow_obj.dst_node,
                    "edges": list(flow_obj.path_bundle.edges),
                }
        return details

    def summarize_link_usage(self) -> Dict[str, float]:
        """
        Returns the total flow usage per edge in the graph.

        Returns:
            Dict[str, float]: A mapping from edge_key -> current flow on that edge.
        """
        usage: Dict[str, float] = {}
        if self.graph is None:
            return usage

        for edge_key, edge_tuple in self.graph.get_edges().items():
            attr_dict = edge_tuple[3]
            usage[edge_key] = attr_dict.get("flow", 0.0)

        return usage

    def get_traffic_results(self, detailed: bool = False) -> List[TrafficResult]:
        """
        Returns traffic demand summaries.

        If detailed=False, each top-level TrafficDemand is returned as a single entry.
        If detailed=True, each expanded Demand is returned separately.

        Args:
            detailed (bool): Whether to return per-expanded-demand data
                instead of top-level aggregated data.

        Returns:
            List[TrafficResult]: A list of traffic result tuples, each containing:
                (priority, total_volume, placed_volume, unplaced_volume, src, dst).
        """
        results: List[TrafficResult] = []

        if not detailed:
            # Summaries for top-level TrafficDemands
            for td in self.traffic_demands:
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
                        src=dmd.src_node,
                        dst=dmd.dst_node,
                    )
                )

        return results

    def _reoptimize_priority_demands(self, demands_in_prio: List[Demand]) -> None:
        """
        Re-run flow-policy placement for each Demand in the same priority class.

        Removing and re-placing each flow allows the flow policy to adjust if
        capacity constraints have changed due to other demands.

        Args:
            demands_in_prio (List[Demand]): All demands of the same priority class.
        """
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

    def _expand_combine(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'combine' mode expansion.

        Attaches a single pseudo-source and a single pseudo-sink node for the
        matched source and sink nodes, similar to the approach in network.py.
        A single Demand is created with the total volume from the pseudo-source
        to the pseudo-sink. Infinite-capacity edges are added from the pseudo-source
        to each real source node, and from each real sink node to the pseudo-sink.

        Args:
            expanded (List[Demand]): Accumulates newly created Demand objects.
            td (TrafficDemand): The original TrafficDemand (total volume, etc.).
            src_groups (Dict[str, List[Node]]): Matched source nodes by label.
            snk_groups (Dict[str, List[Node]]): Matched sink nodes by label.
        """
        # Flatten the source and sink node lists
        src_nodes = [
            node for group_nodes in src_groups.values() for node in group_nodes
        ]
        dst_nodes = [
            node for group_nodes in snk_groups.values() for node in group_nodes
        ]

        if not src_nodes or not dst_nodes or self.graph is None:
            # If no valid nodes or no graph, skip
            return

        # Create pseudo-source / pseudo-sink names
        pseudo_source_name = f"combine_src::{td.id}"
        pseudo_sink_name = f"combine_snk::{td.id}"

        # Add pseudo nodes to the graph (no-op if they already exist)
        self.graph.add_node(pseudo_source_name)
        self.graph.add_node(pseudo_sink_name)

        # Link pseudo-source to real sources, and real sinks to pseudo-sink
        for s_node in src_nodes:
            self.graph.add_edge(
                pseudo_source_name,
                s_node.name,
                capacity=float("inf"),
                cost=0,
            )
        for t_node in dst_nodes:
            self.graph.add_edge(
                t_node.name,
                pseudo_sink_name,
                capacity=float("inf"),
                cost=0,
            )

        init_flow_graph(self.graph)  # Re-initialize flow-related attributes

        # Create a single Demand with the full volume
        if td.flow_policy:
            flow_policy = td.flow_policy.deep_copy()
        else:
            fp_config = td.flow_policy_config or self.default_flow_policy_config
            flow_policy = get_flow_policy(fp_config)

        expanded.append(
            Demand(
                src_node=pseudo_source_name,
                dst_node=pseudo_sink_name,
                volume=td.demand,
                demand_class=td.priority,
                flow_policy=flow_policy,
            )
        )

    def _expand_full_mesh(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'full_mesh' mode expansion.

        Combines all matched source nodes into one group and all matched sink
        nodes into another group. Creates a Demand for each (src_node, dst_node)
        pair (skipping self pairs), splitting td.demand evenly among them.

        Args:
            expanded (List[Demand]): Accumulates newly created Demand objects.
            td (TrafficDemand): The original TrafficDemand (total volume, etc.).
            src_groups (Dict[str, List[Node]]): Matched source nodes by label.
            snk_groups (Dict[str, List[Node]]): Matched sink nodes by label.
        """
        # Flatten the source and sink node lists
        src_nodes = [
            node for group_nodes in src_groups.values() for node in group_nodes
        ]
        dst_nodes = [
            node for group_nodes in snk_groups.values() for node in group_nodes
        ]

        # Generate all valid (src, dst) pairs
        valid_pairs = [
            (s_node, t_node)
            for s_node in src_nodes
            for t_node in dst_nodes
            if s_node.name != t_node.name
        ]
        pair_count = len(valid_pairs)
        if pair_count == 0:
            return

        demand_per_pair = td.demand / float(pair_count)

        for s_node, t_node in valid_pairs:
            if td.flow_policy:
                # Already a FlowPolicy instance, so deep copy it
                flow_policy = td.flow_policy.deep_copy()
            else:
                # Build from enum-based factory
                fp_config = td.flow_policy_config or self.default_flow_policy_config
                flow_policy = get_flow_policy(fp_config)

            expanded.append(
                Demand(
                    src_node=s_node.name,
                    dst_node=t_node.name,
                    volume=demand_per_pair,
                    demand_class=td.priority,
                    flow_policy=flow_policy,
                )
            )

    def _estimate_rounds(self) -> int:
        """
        Estimates a suitable number of placement rounds by comparing
        the median demand volume and the median edge capacity. Returns
        a default of 5 rounds if there is insufficient data for a
        meaningful calculation.

        Returns:
            int: Estimated number of rounds to use for traffic placement.
        """
        if not self.demands:
            return 5

        demand_volumes = [demand.volume for demand in self.demands if demand.volume > 0]
        if not demand_volumes:
            return 5

        median_demand = statistics.median(demand_volumes)

        if not self.graph:
            return 5

        edges = self.graph.get_edges().values()
        capacities = [
            edge_data[3].get("capacity", 0)
            for edge_data in edges
            if edge_data[3].get("capacity", 0) > 0
        ]
        if not capacities:
            return 5

        median_capacity = statistics.median(capacities)
        ratio = median_demand / median_capacity
        guessed_rounds = int(5 + 5 * ratio)
        return max(5, min(guessed_rounds, 100))
