"""Export the named domain network in NetworkX node-link form."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import ClassVar

from ngraph.results import (
    BuildGraphResult,
    StepContext,
    StepOutput,
)
from ngraph.utils.values import flag, own, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step


@register_workflow_step("BuildGraph")
@dataclass
class BuildGraph(WorkflowStep):
    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    # The recorded question is the step itself: this kind and its own fields.
    question_kind: ClassVar[str] = "build_graph"
    add_reverse: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        own(self, add_reverse=flag(self.add_reverse, "BuildGraph.add_reverse"))

    def run(self, context: StepContext) -> StepOutput:
        import networkx as nx

        network = context.prepared.scenario.network
        graph = nx.MultiDiGraph()
        for name, node in sorted(network.nodes.items()):
            graph.add_node(name, **{**node.attrs, "disabled": node.disabled})
        for identity, link in sorted(network.links.items()):
            attrs = {
                **link.attrs,
                "id": identity,
                "capacity": float(link.capacity),
                "cost": link.cost,
                "disabled": link.disabled,
            }
            graph.add_edge(link.source, link.target, **attrs)
            if self.add_reverse:
                graph.add_edge(
                    link.target, link.source, **{**attrs, "id": f"{identity}_reverse"}
                )
        data = nx.node_link_data(graph, edges="edges")
        result = BuildGraphResult(
            self.add_reverse,
            graph.number_of_nodes(),
            graph.number_of_edges(),
            MappingProxyType(data),
        )
        return StepOutput(self, result)
