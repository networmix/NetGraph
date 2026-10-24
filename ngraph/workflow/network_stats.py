"""Statistics of the named physical network, with temporary exclusions."""

from dataclasses import dataclass
from statistics import mean, median
from typing import ClassVar

from ngraph.results import (
    NetworkStatsResult,
    StepContext,
    StepOutput,
)
from ngraph.utils.values import own_scalars, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step, step_name


def _names(values, label):
    if isinstance(values, str):
        raise ValueError(f"{label}: expected a sequence of names")
    values = tuple(values)
    if not all(isinstance(name, str) and name for name in values):
        raise ValueError(f"{label}: expected nonempty string names")
    return tuple(sorted({str.__str__(name) for name in values}))


@register_workflow_step("NetworkStats")
@dataclass
class NetworkStats(WorkflowStep):
    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    # The recorded question is the step itself: this kind and its own fields.
    question_kind: ClassVar[str] = "network_stats"
    include_disabled: bool = False
    excluded_nodes: tuple[str, ...] = ()
    excluded_links: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.include_disabled, bool):
            raise ValueError("NetworkStats.include_disabled: expected bool")
        for name in ("excluded_nodes", "excluded_links"):
            object.__setattr__(
                self, name, _names(getattr(self, name), f"NetworkStats.{name}")
            )
        own_scalars(self, f"workflow step {step_name(self)}", ("include_disabled",))

    def run(self, context: StepContext) -> StepOutput:
        network = context.prepared.scenario.network
        excluded_nodes, excluded_links = (
            set(self.excluded_nodes),
            set(self.excluded_links),
        )
        nodes = {
            name
            for name, node in network.nodes.items()
            if name not in excluded_nodes
            and (self.include_disabled or not node.disabled)
        }
        links = [
            link
            for name, link in network.links.items()
            if name not in excluded_links
            and link.source in nodes
            and link.target in nodes
            and (self.include_disabled or not link.disabled)
        ]
        capacities = [float(link.capacity) for link in links]
        costs = [float(link.cost) for link in links]
        degrees = {name: 0 for name in nodes}
        for link in links:
            degrees[link.source] += 1
            degrees[link.target] += 1
        degree_values = list(degrees.values())
        result = NetworkStatsResult(
            len(nodes),
            len(links),
            sum(capacities),
            float(mean(capacities)) if capacities else 0.0,
            float(median(capacities)) if capacities else 0.0,
            min(capacities, default=0.0),
            max(capacities, default=0.0),
            float(mean(costs)) if costs else 0.0,
            float(median(costs)) if costs else 0.0,
            min(costs, default=0.0),
            max(costs, default=0.0),
            float(mean(degree_values)) if degree_values else 0.0,
            float(median(degree_values)) if degree_values else 0.0,
            float(min(degree_values, default=0)),
            float(max(degree_values, default=0)),
        )
        return StepOutput(self, result)
