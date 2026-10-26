"""Immutable demand declarations and native preset values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, field
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType
from typing import Literal, TypeAlias

import netgraph_core as ngc
import numpy as np

from ngraph.model.network import DirectedLink
from ngraph.model.selectors.schema import Selector
from ngraph.utils.values import (
    JSONValue,
    collection,
    exact_fraction,
    frozen_attrs,
    integer,
    optional_integer,
    optional_text,
    own,
    physical,
    shared_copy,
    text,
)

PhysicalAmount = float
"""A physical amount, such as a capacity or a volume, in whatever unit the scenario
uses (for example Gbit/s), never in units of ``q``.
"""


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
    """A named DAG of directed links that pinned routes can follow (``supports`` in
    YAML).
    """

    edges: tuple[DirectedLink, ...]

    def __post_init__(self) -> None:
        edges = collection(self.edges, "support.edges")
        if not edges:
            raise ValueError(
                f"support.edges: expected at least one edge, got {self.edges!r}"
            )
        if not all(isinstance(edge, DirectedLink) for edge in edges):
            raise TypeError(
                f"support.edges: expected DirectedLink values, got {self.edges!r}"
            )
        object.__setattr__(self, "edges", edges)


@dataclass(frozen=True)
class EdgeWeight:
    """One explicit integer weight on a directed link."""

    edge: DirectedLink
    value: int

    def __post_init__(self) -> None:
        if not isinstance(self.edge, DirectedLink):
            raise TypeError(f"weight.edge: expected DirectedLink, got {self.edge!r}")
        own(self, value=integer(self.value, "weight.value", maximum=1 << 62))


@dataclass(frozen=True)
class WeightSpec:
    """A named vector of explicit edge weights (``weights`` in YAML); unlisted edges
    weigh 0.
    """

    entries: tuple[EdgeWeight, ...]

    def __post_init__(self) -> None:
        entries = collection(self.entries, "weights.entries")
        if not all(isinstance(entry, EdgeWeight) for entry in entries):
            raise TypeError(
                f"weights.entries: expected EdgeWeight values, got {self.entries!r}"
            )
        object.__setattr__(self, "entries", entries)


@dataclass(frozen=True)
class RouteSpec:
    """A named route from its head: a node path, an edge path or a named support, with
    an integer weight.
    """

    head: str
    nodes: tuple[str, ...] | None = None
    edges: tuple[DirectedLink, ...] | None = None
    support: str | None = None
    weight: int = 1

    def __post_init__(self) -> None:
        if sum((v is not None for v in (self.nodes, self.edges, self.support))) != 1:
            raise ValueError("route: specify exactly one of nodes, edges or support")
        nodes = edges = None
        if self.nodes is not None:
            nodes = tuple(
                text(node, "route.nodes")
                for node in collection(self.nodes, "route.nodes")
            )
            if len(nodes) < 2:
                raise ValueError(
                    f"route.nodes: a node route needs at least two nodes, got {nodes!r}"
                )
        if self.edges is not None:
            edges = collection(self.edges, "route.edges")
            if not all(isinstance(edge, DirectedLink) for edge in edges):
                raise TypeError(
                    f"route.edges: expected DirectedLink values, got {self.edges!r}"
                )
            if not edges:
                raise ValueError("route.edges: an edge route needs at least one edge")
        own(
            self,
            head=text(self.head, "route.head"),
            nodes=nodes,
            edges=edges,
            support=optional_text(self.support, "route.support"),
            weight=integer(self.weight, "route.weight", maximum=1 << 62),
        )


@dataclass(frozen=True)
class PinnedRoutes:
    """A pinned model over named routes, in order: its admission and, for a DAG, its
    allocation and weights.
    """

    routes: tuple[str, ...]
    admission: ngc.Admission = ngc.Admission.LOSSLESS
    allocation: ngc.RouteAllocation | None = None
    weight_basis: ngc.WeightBasis | None = None
    edge_weights: str | None = None

    def __post_init__(self) -> None:
        routes = tuple(
            text(name, "pinned.routes")
            for name in collection(self.routes, "pinned.routes")
        )
        if not routes:
            raise ValueError("pinned.routes: expected a nonempty ordered list")
        if not isinstance(self.admission, ngc.Admission):
            raise ValueError(
                f"pinned.admission: expected lossless or lossy, got {self.admission!r}"
            )
        if self.allocation not in (
            None,
            ngc.RouteAllocation.EQUAL,
            ngc.RouteAllocation.WEIGHTED,
        ):
            raise ValueError(
                f"pinned.allocation: expected equal or weighted, got {self.allocation!r}"
            )
        if self.weight_basis not in (
            None,
            ngc.WeightBasis.CAPACITY,
            ngc.WeightBasis.EXPLICIT,
        ):
            raise ValueError(
                "pinned.weight_basis: expected capacity or explicit, "
                f"got {self.weight_basis!r}"
            )
        edge_weights = optional_text(self.edge_weights, "pinned.edge_weights")
        if self.allocation != ngc.RouteAllocation.WEIGHTED and (
            self.weight_basis is not None or edge_weights is not None
        ):
            raise ValueError("pinned: weights require weighted allocation")
        if (self.weight_basis == ngc.WeightBasis.EXPLICIT) != (
            edge_weights is not None
        ):
            raise ValueError(
                "pinned: explicit basis requires named edge_weights and conversely"
            )
        own(self, routes=routes, edge_weights=edge_weights)


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
    """One declared demand: endpoints, physical volume, model, identity, priority and
    expansion modes.
    """

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
            raise TypeError(
                f"demand endpoints require Selector values, got {(self.source, self.target)!r}"
            )
        if not isinstance(self.mode, str) or self.mode not in ("combine", "pairwise"):
            raise ValueError(
                f"demand.mode: expected combine or pairwise, got {self.mode!r}"
            )
        if not isinstance(self.group_mode, str) or self.group_mode not in (
            "flatten",
            "per_group",
            "group_pairwise",
        ):
            raise ValueError(f"demand.group_mode: unknown mode {self.group_mode!r}")
        own(
            self,
            volume=physical(self.volume, "demand.volume"),
            id=optional_text(self.id, "demand.id"),
            priority=integer(self.priority, "demand.priority", minimum=-(1 << 63)),
            mode=str.__str__(self.mode),
            group_mode=str.__str__(self.group_mode),
            yaml_label=optional_text(self.yaml_label, "demand.yaml_label"),
            declaration_ordinal=optional_integer(
                self.declaration_ordinal, "demand.declaration_ordinal"
            ),
            expand_leaf_index=optional_integer(
                self.expand_leaf_index, "demand.expand_leaf_index"
            ),
        )
        if not isinstance(
            self.policy,
            (ngc.FlowPolicyConfig, FlowPolicyPreset, PinnedRoutes, _ParsedModel),
        ):
            raise TypeError(
                f"demand.policy: expected a native configuration, preset or declared routing model, got {self.policy!r}"
            )
        object.__setattr__(self, "attrs", frozen_attrs(self.attrs, "attrs"))


@dataclass(frozen=True)
class DemandSet:
    """A named list of demand declarations."""

    name: str
    demands: tuple[DemandSpec, ...]

    def __post_init__(self) -> None:
        name = text(self.name, "demand set name")
        demands = collection(self.demands, f"demand set {name}.demands")
        if not all(isinstance(demand, DemandSpec) for demand in demands):
            raise TypeError(
                f"demand set {name}.demands: expected DemandSpec values, got {self.demands!r}"
            )
        own(self, name=name, demands=demands)


ExactShare: TypeAlias = int | str | Fraction
"""An exact share: an integer, a ``p/q`` or decimal string, or a Fraction."""


def _share(value: object, label: str) -> Fraction:
    if isinstance(value, (float, np.floating)):
        try:
            share = Fraction(integer(value, label, minimum=None))
        except ValueError as exc:
            raise ValueError(
                f"{label}: expected an exact share (integer, fraction string or Fraction), got {value!r}"
            ) from exc
    else:
        share = exact_fraction(value, label)
    if share < 0:
        raise ValueError(f"{label}: expected a nonnegative share, got {value!r}")
    return share


def _children(values: Sequence[object], label: str) -> tuple[GroupChild, ...]:
    raw_values = values
    values = collection(values, label)
    children = tuple(child for child in values if isinstance(child, GroupChild))
    if len(children) != len(values):
        raise TypeError(f"{label}: expected GroupChild values, got {raw_values!r}")
    if not children:
        raise ValueError(f"{label}: expected at least one child")
    return children


@dataclass(frozen=True, init=False)
class GroupChild:
    """A member edge, or a conditional subtree, with its share within its parent.

    Exactly one of ``edge`` and ``children`` is set, and the share is
    nonnegative, stored as a Fraction; preparation checks the tree against the
    network (edges leaving the router, zero shares, duplicates).
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
        object.__setattr__(self, "share", _share(share, "group_child.share"))
        if edge is not None and not isinstance(edge, DirectedLink):
            raise TypeError(f"group_child.edge: expected DirectedLink, got {edge!r}")
        if (edge is None) == (children is None):
            raise ValueError("group_child: expected exactly one of edge and children")
        object.__setattr__(self, "edge", edge)
        if children is not None:
            children = _children(children, "group_child.children")
        object.__setattr__(self, "children", children)


@dataclass(frozen=True, init=False)
class ControllerGroup:
    """A root group of one router: its share is a fixed cap, normalized once."""

    children: tuple[GroupChild, ...]
    share: Fraction

    def __init__(self, children: Sequence[GroupChild], share: ExactShare = 1) -> None:
        object.__setattr__(self, "share", _share(share, "controller_group.share"))
        object.__setattr__(
            self, "children", _children(children, "controller_group.children")
        )


@dataclass(frozen=True)
class ForwardingGroup:
    """The declared root groups of one router."""

    router: str
    groups: tuple[ControllerGroup, ...]

    def __post_init__(self) -> None:
        router = text(self.router, "forwarding_group.router")
        groups = collection(self.groups, "forwarding_group.groups")
        if not all(isinstance(group, ControllerGroup) for group in groups):
            raise TypeError(
                f"forwarding_group.groups: expected ControllerGroup values, got {self.groups!r}"
            )
        if not groups:
            raise ValueError("forwarding_group.groups: expected at least one group")
        own(self, router=router, groups=groups)


@dataclass(frozen=True)
class RoutingDomain:
    """One IGP domain and the BGP-edge routers around it."""

    igp_domain: Selector
    bgp_edge: Selector

    def __post_init__(self) -> None:
        if not isinstance(self.igp_domain, Selector) or not isinstance(
            self.bgp_edge, Selector
        ):
            raise TypeError(
                f"routing: expected Selector populations, got {(self.igp_domain, self.bgp_edge)!r}"
            )


@dataclass(frozen=True)
class WCMPController:
    """Which routers the controller programs for SHORTEST_PATHS_WCMP demands."""

    scope: Literal["next_hop", "group", "all_routers"] = "next_hop"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, str) or self.scope not in (
            "next_hop",
            "group",
            "all_routers",
        ):
            raise ValueError(
                "wcmp_controller.scope: expected next_hop, group or all_routers, "
                f"got {self.scope!r}"
            )
        own(self, scope=str.__str__(self.scope))
