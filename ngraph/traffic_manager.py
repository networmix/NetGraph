from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ngraph.lib.algorithms import base
from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.demand import Demand
from ngraph.lib.flow_policy import FlowPolicy, FlowPolicyConfig, get_flow_policy
from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.network import Network, Node
from ngraph.traffic_demand import TrafficDemand


@dataclass
class TrafficManager:
    """
    Manages the expansion and placement of traffic demands on a Network.

    This class:
      1) Builds (or rebuilds) a StrictMultiDiGraph from the given Network.
      2) Expands each TrafficDemand into one or more Demand objects, according
         to a configurable "mode" (e.g., combine, pairwise, node_to_node,
         one_to_one).
      3) Each Demand is associated with a FlowPolicy, which handles how flows
         are placed (split across paths, balancing, etc.).
      4) Provides methods to place all demands incrementally with optional
         re-optimization, reset usage, and retrieve flow/usage summaries.

    The sum of volumes of the expanded Demands for a given TrafficDemand
    matches that TrafficDemand's `demand` value.

    Attributes:
        network (Network): The underlying network object.
        traffic_demands (List[TrafficDemand]): The scenario-level demands.
        default_flow_policy_config (FlowPolicyConfig): Default FlowPolicy if
            a TrafficDemand does not specify one.
        graph (StrictMultiDiGraph): Active graph built from the network.
        demands (List[Demand]): The expanded demands from traffic_demands.
        _td_to_demands (Dict[str, List[Demand]]): Internal mapping from TrafficDemand.id
            to its expanded Demand objects.
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

        This also initializes flow-related edge attributes (like flow=0).

        Args:
            add_reverse (bool): If True, for every link A->B, add a mirrored link
                B->A with the same capacity/cost. Default True.
        """
        self.graph = self.network.to_strict_multidigraph(add_reverse=add_reverse)
        init_flow_graph(self.graph)  # Initialize flow-related attributes

    def expand_demands(self) -> None:
        """
        Converts each TrafficDemand into one or more Demand objects according
        to the demand's 'mode'. The sum of volumes for all expanded Demands of
        a TrafficDemand equals that TrafficDemand's `demand`.

        Supported modes:
            - 'node_to_node'
            - 'combine'
            - 'pairwise'
            - 'one_to_one'

        Each Demand is assigned a FlowPolicy (from the demand or default).
        The expanded demands are stored in self.demands, sorted by ascending
        priority (lower demand_class -> earlier).

        Also populates _td_to_demands[td.id] with the corresponding Demand list.
        """
        self._td_to_demands.clear()
        expanded: List[Demand] = []

        for td in self.traffic_demands:
            # Collect node groups for src and dst
            src_groups = self.network.select_node_groups_by_path(td.source_path)
            snk_groups = self.network.select_node_groups_by_path(td.sink_path)

            # If no node matches, store empty and skip
            if not src_groups or not snk_groups:
                self._td_to_demands[td.id] = []
                continue

            # Sort labels for deterministic expansion
            src_labels = sorted(src_groups.keys())
            snk_labels = sorted(snk_groups.keys())
            mode = td.mode

            local_demands: List[Demand] = []
            if mode == "combine":
                self._expand_combine(local_demands, td, src_groups, snk_groups)
            elif mode == "pairwise":
                self._expand_pairwise(
                    local_demands,
                    td,
                    src_labels,
                    snk_labels,
                    src_groups,
                    snk_groups,
                )
            elif mode == "one_to_one":
                self._expand_one_to_one(
                    local_demands,
                    td,
                    src_labels,
                    snk_labels,
                    src_groups,
                    snk_groups,
                )
            else:
                # Default to "node_to_node"
                self._expand_node_to_node(local_demands, td, src_groups, snk_groups)

            expanded.extend(local_demands)
            self._td_to_demands[td.id] = local_demands

        # Sort final demands by ascending priority
        expanded.sort()
        self.demands = expanded

    def place_all_demands(
        self,
        placement_rounds: int = 5,
        reoptimize_after_each_round: bool = False,
    ) -> float:
        """
        Places all expanded demands in ascending priority order, using a
        multi-round approach for demands of the same priority.

        Each priority class is processed with `placement_rounds` passes, distributing
        demand incrementally. Optionally re-optimizes flows after each round.

        Finally, updates each TrafficDemand's `demand_placed` with the sum of
        its expanded demands' placed volumes.

        Args:
            placement_rounds (int): Number of incremental passes per priority.
            reoptimize_after_each_round (bool): Whether to re-run an optimization
                pass after each round of placement.

        Returns:
            float: Total volume successfully placed across all demands.

        Raises:
            RuntimeError: If the graph has not been built.
        """
        if self.graph is None:
            raise RuntimeError("Graph not built yet. Call build_graph() first.")

        # Group demands by priority
        prio_map: Dict[int, List[Demand]] = defaultdict(list)
        for d in self.demands:
            prio_map[d.demand_class].append(d)

        total_placed = 0.0
        sorted_priorities = sorted(prio_map.keys())

        for priority in sorted_priorities:
            demands_in_prio = prio_map[priority]

            # Multi-round fractional placement
            for round_idx in range(placement_rounds):
                placement_this_round = 0.0

                for demand in demands_in_prio:
                    leftover = demand.volume - demand.placed_demand
                    if leftover < base.MIN_FLOW:
                        # Already fully placed (or negligible leftover)
                        continue

                    # Distribute in fractional increments
                    rounds_left = placement_rounds - round_idx
                    step_to_place = leftover / float(rounds_left)

                    placed_now, _remain = demand.place(
                        flow_graph=self.graph,
                        max_placement=step_to_place,
                    )
                    total_placed += placed_now
                    placement_this_round += placed_now

                # Re-optimize if requested
                if reoptimize_after_each_round and placement_this_round > 0.0:
                    self._reoptimize_priority_demands(demands_in_prio)

                # No progress -> break
                if placement_this_round < base.MIN_FLOW:
                    break

        # Update each TrafficDemand with the sum of its expanded demands
        for td in self.traffic_demands:
            demand_list = self._td_to_demands.get(td.id, [])
            td.demand_placed = sum(d.placed_demand for d in demand_list)

        return total_placed

    def reset_all_flow_usages(self) -> None:
        """
        Removes flow usage from the graph for each Demand's FlowPolicy,
        resets placed_demand=0 for each Demand, and sets
        TrafficDemand.demand_placed=0.
        """
        if self.graph is None:
            return

        # Clear usage from each Demand's FlowPolicy
        for d in self.demands:
            if d.flow_policy:
                d.flow_policy.remove_demand(self.graph)
            d.placed_demand = 0.0

        # Reset top-level traffic demands
        for td in self.traffic_demands:
            td.demand_placed = 0.0

    def get_flow_details(self) -> Dict[Tuple[int, int], Dict[str, object]]:
        """
        Summarizes flows from each Demand's FlowPolicy.

        Returns:
            Dict[Tuple[int, int], Dict[str, object]]:
                Keyed by (demand_index, flow_index), with info on placed_flow,
                src_node, dst_node, and the path edges.
        """
        details: Dict[Tuple[int, int], Dict[str, object]] = {}
        for i, d in enumerate(self.demands):
            if not d.flow_policy:
                continue
            for f_idx, flow_obj in d.flow_policy.flows.items():
                details[(i, f_idx)] = {
                    "placed_flow": flow_obj.placed_flow,
                    "src_node": flow_obj.src_node,
                    "dst_node": flow_obj.dst_node,
                    "edges": list(flow_obj.path_bundle.edges),
                }
        return details

    def summarize_link_usage(self) -> Dict[str, float]:
        """
        Returns flow usage per edge in the graph.

        Returns:
            Dict[str, float]: edge_key -> used capacity (flow).
        """
        usage: Dict[str, float] = {}
        if self.graph is None:
            return usage

        for edge_key, edge_tuple in self.graph.get_edges().items():
            attr_dict = edge_tuple[3]
            usage[edge_key] = attr_dict.get("flow", 0.0)
        return usage

    def _reoptimize_priority_demands(self, demands_in_prio: List[Demand]) -> None:
        """
        Optionally re-run flow-policy optimization for each Demand in
        the same priority class.

        Args:
            demands_in_prio (List[Demand]): Demands of the same priority.
        """
        if self.graph is None:
            return

        for d in demands_in_prio:
            if not d.flow_policy:
                continue
            placed_volume = d.placed_demand
            d.flow_policy.remove_demand(self.graph)
            d.flow_policy.place_demand(
                self.graph,
                d.src_node,
                d.dst_node,
                d.demand_class,
                placed_volume,
            )
            d.placed_demand = d.flow_policy.placed_demand

    def _expand_node_to_node(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'node_to_node' mode: Each matched (src_node, dst_node) pair
        gets an equal fraction of td.demand (skips self-pairs).
        """
        # Determine the flow policy configuration
        fp_config = td.flow_policy_config or self.default_flow_policy_config

        src_nodes: List[Node] = []
        for group_nodes in src_groups.values():
            src_nodes.extend(group_nodes)

        dst_nodes: List[Node] = []
        for group_nodes in snk_groups.values():
            dst_nodes.extend(group_nodes)

        valid_pairs = []
        for s_node in src_nodes:
            for t_node in dst_nodes:
                if s_node.name != t_node.name:
                    valid_pairs.append((s_node, t_node))

        if not valid_pairs:
            return

        demand_per_pair = td.demand / float(len(valid_pairs))
        for s_node, t_node in valid_pairs:
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

    def _expand_combine(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'combine' mode: Combine all matched sources into one set, all sinks into another,
        then distribute td.demand among all valid pairs.
        """
        # Determine the flow policy configuration
        fp_config = td.flow_policy_config or self.default_flow_policy_config

        combined_src_nodes: List[Node] = []
        combined_snk_nodes: List[Node] = []

        for nodes in src_groups.values():
            combined_src_nodes.extend(nodes)
        for nodes in snk_groups.values():
            combined_snk_nodes.extend(nodes)

        valid_pairs = []
        for s_node in combined_src_nodes:
            for t_node in combined_snk_nodes:
                if s_node.name != t_node.name:
                    valid_pairs.append((s_node, t_node))

        if not valid_pairs:
            return

        demand_per_pair = td.demand / float(len(valid_pairs))
        for s_node, t_node in valid_pairs:
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

    def _expand_pairwise(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_labels: List[str],
        snk_labels: List[str],
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'pairwise' mode: For each (src_label, snk_label) pair, allocate a fraction
        of td.demand, then split among valid node pairs (excluding self-pairs).
        """
        # Determine the flow policy configuration
        fp_config = td.flow_policy_config or self.default_flow_policy_config

        label_pairs_count = len(src_labels) * len(snk_labels)
        if label_pairs_count == 0:
            return

        label_share = td.demand / float(label_pairs_count)

        for s_label in src_labels:
            s_nodes = src_groups[s_label]
            if not s_nodes:
                continue

            for t_label in snk_labels:
                t_nodes = snk_groups[t_label]
                if not t_nodes:
                    continue

                valid_pairs = []
                for s_node in s_nodes:
                    for t_node in t_nodes:
                        if s_node.name != t_node.name:
                            valid_pairs.append((s_node, t_node))

                if not valid_pairs:
                    continue

                demand_per_pair = label_share / float(len(valid_pairs))
                for s_node, t_node in valid_pairs:
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

    def _expand_one_to_one(
        self,
        expanded: List[Demand],
        td: TrafficDemand,
        src_labels: List[str],
        snk_labels: List[str],
        src_groups: Dict[str, List[Node]],
        snk_groups: Dict[str, List[Node]],
    ) -> None:
        """
        'one_to_one' mode: Match src_labels[i] to snk_labels[i], splitting td.demand
        evenly among label pairs, then distributing that share among valid node pairs.

        Raises:
            ValueError: If the number of src_labels != number of snk_labels.
        """
        # Determine the flow policy configuration
        fp_config = td.flow_policy_config or self.default_flow_policy_config
        if len(src_labels) != len(snk_labels):
            raise ValueError(
                "one_to_one mode requires equal counts of src and sink labels. "
                f"Got {len(src_labels)} vs {len(snk_labels)}."
            )

        label_count = len(src_labels)
        if label_count == 0:
            return

        pair_share = td.demand / float(label_count)

        for i, s_label in enumerate(src_labels):
            t_label = snk_labels[i]
            s_nodes = src_groups[s_label]
            t_nodes = snk_groups[t_label]
            if not s_nodes or not t_nodes:
                continue

            valid_pairs = []
            for s_node in s_nodes:
                for t_node in t_nodes:
                    if s_node.name != t_node.name:
                        valid_pairs.append((s_node, t_node))

            if not valid_pairs:
                continue

            demand_per_pair = pair_share / float(len(valid_pairs))
            for s_node, t_node in valid_pairs:
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
