from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from heapq import heappush, heappop

from ngraph.lib import common
from ngraph.lib.flow import FlowPolicy, FlowPolicyConfig, get_flow_policy
from ngraph.lib.graph import EdgeID, MultiDiGraph, NodeID
from ngraph.lib.demand import Demand
from ngraph.net import Net, Link, Node


class EntityType(IntEnum):
    """
    EntityType represents the type of entity.
    """

    NODE = 1
    LINK = 2


class ConstraintType(IntEnum):
    """
    ConstraintType represents the type of constraint.
    """

    NON_TRANSIT = 1


@dataclass
class Constraint:
    """
    Constraint is a tag attached to an edge or node.
    """

    entity_type: EntityType
    entity_id: Union[EdgeID, NodeID]
    constraint_type: ConstraintType
    constraint_value: Optional[Any] = None


@dataclass
class Failure:
    """
    Failure is a tag attached to an edge or node.
    """

    entity_type: EntityType
    entity_id: Union[EdgeID, NodeID]
    failure_probability: float
    failure_value: Optional[Any] = None


@dataclass
class SolverParams:
    """
    Parameters for the solver.
    """

    demand_placement_policy: Dict[int, FlowPolicyConfig] = field(
        default_factory=lambda: {
            1: FlowPolicyConfig.TE_ECMP_16_LSP,
            2: FlowPolicyConfig.TE_ECMP_16_LSP,
            3: FlowPolicyConfig.TE_ECMP_16_LSP,
        }
    )
    max_demand_placement_fraction: float = 0.005
    max_demand_placement_volume: float = 10.0


@dataclass
class Problem:
    """
    Problem represents a problem to be solved.
    """

    net: Net
    demands: List[Demand]
    constraints: List[Constraint] = field(default_factory=list)
    failures: List[Failure] = field(default_factory=list)
    solver_params: SolverParams = field(default_factory=SolverParams)


class Solver:
    def solve(self, problem: Problem):
        self.params = problem.solver_params
        demand_policy_map = self._place_demands(
            problem.solver_params,
            problem.net,
            problem.demands,
            problem.constraints,
            problem.failures,
        )
        return problem.net.graph, demand_policy_map

    def _place_demands(
        self,
        params: SolverParams,
        net: Net,
        demands: List[Demand],
        constraints: List[Constraint],
        failures: List[Failure],
    ) -> Dict[Demand, FlowPolicy]:
        graph = net.graph
        demand_policy_map: Dict[Demand, FlowPolicy] = {}

        # Create a demand queue.
        demand_queue: List[Tuple[int, Demand]] = []
        for demand in demands:
            flow_policy = get_flow_policy(
                params.demand_placement_policy[demand.demand_class]
            )
            demand_policy_map[demand] = flow_policy
            heappush(demand_queue, (demand.demand_class, demand))

        while demand_queue:
            _, demand = heappop(demand_queue)
            flow_policy = demand_policy_map[demand]
            placed, remaining = demand.place(
                graph,
                flow_policy,
                params.max_demand_placement_fraction,
                params.max_demand_placement_volume,
            )
            if placed:
                heappush(demand_queue, (demand.demand_class, demand))

        return demand_policy_map
