"""Immutable demand declarations and native preset values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, field
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType
from typing import Literal, TypeAlias

import netgraph_core as ngc

from ngraph.model.network import DirectedLink
from ngraph.model.selectors.schema import Selector
from ngraph.utils.values import (
    JSONValue,
    exact_fraction,
    frozen_attrs,
    integer,
    own_scalars,
    physical,
    scalar,
    shared_copy,
)

PhysicalAmount = float


class FlowPolicyPreset(StrEnum):
    """Named questions with one immutable native configuration each."""

    SHORTEST_PATHS_ECMP = "SHORTEST_PATHS_ECMP"
    SHORTEST_PATHS_ECMP_LOSSY = "SHORTEST_PATHS_ECMP_LOSSY"
    SHORTEST_PATHS_WCMP = "SHORTEST_PATHS_WCMP"
    SHORTEST_PATHS_MAXFLOW = "SHORTEST_PATHS_MAXFLOW"
    TE_MAXFLOW_UNLIM = "TE_MAXFLOW_UNLIM"
    TE_ECMP_16_LSP = "TE_ECMP_16_LSP"
    TE_ECMP_UP_TO_256_LSP = "TE_ECMP_UP_TO_256_LSP"


PRESETS = MappingProxyType(
    {
        FlowPolicyPreset.SHORTEST_PATHS_ECMP: ngc.FlowPolicyConfig(
            routing=ngc.ShortestPaths()
        ),
        FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY: ngc.FlowPolicyConfig(
            routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
        ),
        FlowPolicyPreset.SHORTEST_PATHS_WCMP: ngc.FlowPolicyConfig(
            routing=ngc.ShortestPaths(
                allocation=ngc.RouteAllocation.WEIGHTED,
                weight_basis=ngc.WeightBasis.CAPACITY,
            )
        ),
        FlowPolicyPreset.SHORTEST_PATHS_MAXFLOW: ngc.FlowPolicyConfig(
            routing=ngc.ShortestPaths(
                allocation=ngc.RouteAllocation.OPTIMIZED,
                source_allocation=ngc.SourceAllocation.OPTIMIZED,
            )
        ),
        FlowPolicyPreset.TE_MAXFLOW_UNLIM: ngc.FlowPolicyConfig(
            routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
        ),
        FlowPolicyPreset.TE_ECMP_16_LSP: ngc.FlowPolicyConfig(
            routing=ngc.CentralizedTE(
                source_allocation=ngc.SourceAllocation.OPTIMIZED,
                tunnel_count=ngc.TunnelCount(16),
                prefer_headroom=True,
            )
        ),
        FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP: ngc.FlowPolicyConfig(
            routing=ngc.CentralizedTE(
                source_allocation=ngc.SourceAllocation.OPTIMIZED,
                tunnel_count=ngc.TunnelCount(256, up_to=True),
                prefer_headroom=True,
            )
        ),
    }
)


@dataclass(frozen=True)
class SupportSpec:
    edges: tuple[DirectedLink, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "edges", tuple(self.edges))
        if not all(isinstance(edge, DirectedLink) for edge in self.edges):
            raise TypeError("support.edges: expected DirectedLink values")


@dataclass(frozen=True)
class EdgeWeight:
    edge: DirectedLink
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.edge, DirectedLink):
            raise TypeError("weight.edge: expected DirectedLink")
        integer(self.value, "weight.value", maximum=1 << 62)
        own_scalars(self, "weight", ("value",))


@dataclass(frozen=True)
class WeightSpec:
    entries: tuple[EdgeWeight, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "entries", tuple(self.entries))
        if not all(isinstance(entry, EdgeWeight) for entry in self.entries):
            raise TypeError("weights.entries: expected EdgeWeight values")


@dataclass(frozen=True)
class RouteSpec:
    head: str
    nodes: tuple[str, ...] | None = None
    edges: tuple[DirectedLink, ...] | None = None
    support: str | None = None
    weight: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.head, str) or not self.head:
            raise ValueError("route.head: expected a nonempty physical node name")
        if sum((v is not None for v in (self.nodes, self.edges, self.support))) != 1:
            raise ValueError("route: specify exactly one of nodes, edges or support")
        integer(self.weight, "route.weight", maximum=1 << 62)
        own_scalars(self, "route", ("head", "support", "weight"))
        if self.nodes is not None:
            if isinstance(self.nodes, str):
                raise TypeError("route.nodes: expected a sequence of node names")
            if not all(isinstance(node, str) and node for node in self.nodes):
                raise ValueError("route.nodes: expected nonempty physical node names")
            object.__setattr__(
                self, "nodes", tuple(scalar(node, "route.nodes") for node in self.nodes)
            )
        if self.edges is not None:
            object.__setattr__(self, "edges", tuple(self.edges))
            if not all(isinstance(edge, DirectedLink) for edge in self.edges):
                raise TypeError("route.edges: expected DirectedLink values")
        if self.support is not None and (
            not isinstance(self.support, str) or not self.support
        ):
            raise ValueError("route.support: expected a nonempty support name")


@dataclass(frozen=True)
class PinnedRoutes:
    routes: tuple[str, ...]
    admission: ngc.Admission = ngc.Admission.LOSSLESS
    allocation: ngc.RouteAllocation | None = None
    weight_basis: ngc.WeightBasis | None = None
    edge_weights: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.routes, str):
            raise TypeError("pinned.routes: expected a sequence of route names")
        if not all(isinstance(name, str) and name for name in self.routes):
            raise ValueError("pinned.routes: expected nonempty route names")
        object.__setattr__(
            self, "routes", tuple(scalar(name, "pinned.routes") for name in self.routes)
        )
        own_scalars(self, "pinned", ("edge_weights",))


@dataclass(frozen=True)
class _ShortestPathsInput:
    allocation: ngc.RouteAllocation = ngc.RouteAllocation.EQUAL
    source_allocation: ngc.SourceAllocation | None = None
    weight_basis: ngc.WeightBasis | None = None
    edge_weights: str | None = None
    tie_break: ngc.RouteTieBreak = ngc.RouteTieBreak.FEWER_HOPS
    multipath: bool = True
    parallel_edges: bool = True


@dataclass(frozen=True)
class _DistributedTEInput:
    tunnel_count: ngc.TunnelCount
    cost_ceiling: ngc.AbsoluteCost | ngc.CostStretch | None = None
    min_unreserved_bandwidth: PhysicalAmount = 0
    tie_break: ngc.RouteTieBreak = ngc.RouteTieBreak.FEWER_HOPS
    parallel_edges: bool = True


@dataclass(frozen=True)
class _CentralizedTEInput:
    source_allocation: ngc.SourceAllocation
    tunnel_count: ngc.TunnelCount | None = None
    prefer_headroom: bool = False


@dataclass(frozen=True)
class _ParsedModel:
    routing: _ShortestPathsInput | _DistributedTEInput | _CentralizedTEInput
    admission: ngc.Admission = ngc.Admission.LOSSLESS


DemandPolicy: TypeAlias = (
    ngc.FlowPolicyConfig | FlowPolicyPreset | PinnedRoutes | _ParsedModel
)
"""A demand's declared model: a native config, a preset, named pinned routes
or a parsed YAML model."""


@dataclass(frozen=True)
class DemandSpec:
    source: Selector
    target: Selector
    volume: PhysicalAmount
    policy: DemandPolicy = FlowPolicyPreset.SHORTEST_PATHS_ECMP
    id: str | None = None
    priority: int = 0
    mode: Literal["combine", "pairwise"] = "combine"
    group_mode: Literal["flatten", "per_group", "group_pairwise"] = "flatten"
    attrs: Mapping[str, JSONValue] = field(default_factory=dict)
    _: KW_ONLY
    # Its YAML declaration, kept by dataclasses.replace: refusal label,
    # position in the declared list and row of an expand block.
    yaml_label: str | None = field(default=None, compare=False, repr=False)
    declaration_ordinal: int | None = field(default=None, compare=False, repr=False)
    expand_leaf_index: int | None = field(default=None, compare=False, repr=False)
    __copy__ = __deepcopy__ = shared_copy

    def __post_init__(self) -> None:
        if not isinstance(self.source, Selector) or not isinstance(
            self.target, Selector
        ):
            raise TypeError("demand endpoints require Selector values")
        if self.yaml_label is not None and (
            not isinstance(self.yaml_label, str) or not self.yaml_label
        ):
            raise ValueError("demand.yaml_label: expected a nonempty string")
        for name in ("declaration_ordinal", "expand_leaf_index"):
            if getattr(self, name) is not None:
                integer(getattr(self, name), f"demand.{name}")
        object.__setattr__(self, "volume", physical(self.volume, "demand.volume"))
        if self.id is not None and (not isinstance(self.id, str) or not self.id):
            raise ValueError("demand.id: expected a nonempty string")
        integer(self.priority, "demand.priority", minimum=-(1 << 63))
        own_scalars(
            self,
            "demand",
            (
                "id",
                "priority",
                "mode",
                "group_mode",
                "yaml_label",
                "declaration_ordinal",
                "expand_leaf_index",
            ),
        )
        if self.mode not in ("combine", "pairwise"):
            raise ValueError("demand.mode: expected combine or pairwise")
        if self.group_mode not in ("flatten", "per_group", "group_pairwise"):
            raise ValueError("demand.group_mode: unknown mode")
        if not isinstance(
            self.policy,
            (ngc.FlowPolicyConfig, FlowPolicyPreset, PinnedRoutes, _ParsedModel),
        ):
            raise TypeError(
                "demand.policy: expected a native configuration, preset or declared routing model"
            )
        object.__setattr__(self, "attrs", frozen_attrs(self.attrs, "attrs"))


@dataclass(frozen=True)
class DemandSet:
    name: str
    demands: tuple[DemandSpec, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("demand set name: expected a nonempty string")
        object.__setattr__(self, "demands", tuple(self.demands))
        if not all(isinstance(demand, DemandSpec) for demand in self.demands):
            raise TypeError(f"demand set {self.name}: expected DemandSpec values")
        own_scalars(self, "demand set", ("name",))


ExactShare: TypeAlias = int | str | Fraction
"""An exact share: an integer, a ``p/q`` or decimal string, or a Fraction."""


@dataclass(frozen=True, init=False)
class GroupChild:
    """A member edge, or a conditional subtree, with its share within its parent.

    Exactly one of ``edge`` and ``children`` is set; preparation checks the
    structure and the share's range. The share is stored as a Fraction.
    """

    share: Fraction
    edge: DirectedLink | None
    children: tuple[GroupChild, ...] | None

    def __init__(
        self,
        share: ExactShare = 1,
        edge: DirectedLink | None = None,
        children: Sequence[GroupChild] | None = None,
    ) -> None:
        object.__setattr__(self, "share", exact_fraction(share, "group_child.share"))
        if edge is not None and not isinstance(edge, DirectedLink):
            raise TypeError("group_child.edge: expected DirectedLink")
        object.__setattr__(self, "edge", edge)
        if children is not None:
            children = tuple(children)
            if not all(isinstance(child, GroupChild) for child in children):
                raise TypeError("group_child.children: expected GroupChild values")
        object.__setattr__(self, "children", children)


@dataclass(frozen=True, init=False)
class ControllerGroup:
    """A root group of one router: its share is a fixed cap, normalized once."""

    children: tuple[GroupChild, ...]
    share: Fraction

    def __init__(self, children: Sequence[GroupChild], share: ExactShare = 1) -> None:
        object.__setattr__(
            self, "share", exact_fraction(share, "controller_group.share")
        )
        children = tuple(children)
        if not all(isinstance(child, GroupChild) for child in children):
            raise TypeError("controller_group.children: expected GroupChild values")
        object.__setattr__(self, "children", children)


@dataclass(frozen=True)
class ForwardingGroup:
    """The declared root groups of one router."""

    router: str
    groups: tuple[ControllerGroup, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.router, str) or not self.router:
            raise ValueError("forwarding_group.router: expected a nonempty node name")
        own_scalars(self, "forwarding_group", ("router",))
        object.__setattr__(self, "groups", tuple(self.groups))
        if not all(isinstance(group, ControllerGroup) for group in self.groups):
            raise TypeError("forwarding_group.groups: expected ControllerGroup values")


@dataclass(frozen=True)
class RoutingDomain:
    """One IGP domain and the BGP-edge routers around it."""

    igp_domain: Selector
    bgp_edge: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.igp_domain, Selector) or not isinstance(
            self.bgp_edge, Selector
        ):
            raise TypeError("routing: expected Selector populations")


@dataclass(frozen=True)
class WCMPController:
    """Which routers the controller programs for SHORTEST_PATHS_WCMP demands."""

    scope: Literal["next_hop", "group", "all_routers"] = "next_hop"

    def __post_init__(self) -> None:
        own_scalars(self, "wcmp_controller", ("scope",))
        if self.scope not in ("next_hop", "group", "all_routers"):
            raise ValueError(
                "wcmp_controller.scope: expected next_hop, group or all_routers"
            )
