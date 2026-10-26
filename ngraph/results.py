"""Owned analysis envelopes, exact reports and normalized questions.

Computational results remain native values with their native lifetime and fields.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import MISSING, FrozenInstanceError, dataclass, field, fields, replace
from fractions import Fraction
from functools import cache
from reprlib import recursive_repr
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    ClassVar,
    Generic,
    Literal,
    TypeAlias,
    TypeVar,
    dataclass_transform,
)

import netgraph_core as ngc

from ngraph.model.network import DirectedLink
from ngraph.utils.values import JSONValue, frozen_attrs, physical

if TYPE_CHECKING:
    from ngraph.analysis.capacity import CapacityQuery
    from ngraph.analysis.controller import DestinationTable
    from ngraph.analysis.counts import TunnelCountQuery
    from ngraph.analysis.msd import MSDQuery
    from ngraph.analysis.paths import PathQuery
    from ngraph.analysis.placement import PlacementQuery
    from ngraph.analysis.preparation import PreparedScenario
    from ngraph.analysis.sensitivity import SensitivityQuery
    from ngraph.analysis.topology import PreparedTopology
    from ngraph.model.demand import DemandPolicy
    from ngraph.model.selectors import Selector
    from ngraph.workflow.build_graph import BuildGraph
    from ngraph.workflow.cost_power import CostPower
    from ngraph.workflow.network_stats import NetworkStats


@cache
def _record_fields(kind: type) -> tuple[str, ...]:
    return tuple(item.name for item in fields(kind))


def _compile_init(kind: type):
    """Build a record class's constructor, as ``dataclasses`` would write it."""
    names, defaults = [], {}
    for item in fields(kind):
        assert item.default_factory is MISSING and not item.kw_only, item.name
        if item.default is not MISSING:
            defaults[f"_default_{item.name}"] = item.default
            names.append(f"{item.name}=_default_{item.name}")
        else:
            names.append(item.name)
    body = [f"    _set(self, {f.name!r}, {f.name})" for f in fields(kind)]
    if hasattr(kind, "__post_init__"):
        body.append("    self.__post_init__()")
    namespace = {"_set": object.__setattr__, **defaults}
    exec(f"def __init__(self, {', '.join(names)}):\n" + "\n".join(body), namespace)
    init = namespace["__init__"]
    init.__qualname__ = f"{kind.__qualname__}.__init__"
    return init


class _ResultRecord:
    """Share cold value operations instead of compiling them for every record."""

    __slots__ = ()

    def __init__(self, *args, **kwargs):
        # Each record class gets its real constructor when first used, so
        # importing this module generates no code for the classes a run skips.
        kind = next(c for c in type(self).__mro__ if "__dataclass_fields__" in vars(c))
        kind.__init__ = _compile_init(kind)
        kind.__init__(self, *args, **kwargs)

    def __setattr__(self, name, value):
        # Frozen dataclasses reject every edit on the declared record, and
        # field edits on subclasses; a subclass may add its own attributes.
        if "__dataclass_fields__" in vars(type(self)) or name in _record_fields(
            type(self)
        ):
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if "__dataclass_fields__" in vars(type(self)) or name in _record_fields(
            type(self)
        ):
            raise FrozenInstanceError(f"cannot delete field {name!r}")
        object.__delattr__(self, name)

    def __eq__(self, other):
        if self is other:
            return True
        if type(self) is not type(other):
            return NotImplemented
        return all(
            getattr(self, name) == getattr(other, name)
            for name in _record_fields(type(self))
        )

    def __hash__(self):
        return hash(tuple(getattr(self, name) for name in _record_fields(type(self))))

    @recursive_repr()
    def __repr__(self):
        members = ", ".join(
            f"{name}={getattr(self, name)!r}" for name in _record_fields(type(self))
        )
        return f"{type(self).__qualname__}({members})"


_RecordT = TypeVar("_RecordT")


@dataclass_transform(frozen_default=True, eq_default=False, field_specifiers=(field,))
def _record(cls: type[_RecordT]) -> type[_RecordT]:
    # Fields and constructor signatures are documented separately. Supplying a
    # docstring also avoids dataclasses inspecting all signatures at import.
    if not cls.__doc__:
        cls.__doc__ = f"Immutable {cls.__name__} record."
    # Register standard field/replace/match metadata, without generating any
    # methods. Constructors are built on first use; immutable guards are shared.
    result = dataclass(init=False, eq=False, repr=False)(cls)
    params = vars(result)["__dataclass_params__"]
    params.init = True
    params.frozen = True
    params.eq = cls.__name__ == "FailurePattern"
    return result


# A record field's declaration is also its output schema: its field metadata adds
# JSON Schema keywords to the schema of its type, and states when the field is null
# (``null_when``); the results generator reads both. The type stays plain for users.


@_record
class ExactAlpha(_ResultRecord):
    """An alpha (the demand multiplier) as a binary64 value and its exact fraction."""

    value: float = field(metadata={"exclusiveMinimum": 0})
    """Alpha as a binary64 value."""
    numerator: int
    """Alpha's exact numerator."""
    denominator: int = field(metadata={"minimum": 1})
    """Alpha's exact denominator."""


@_record
class Endpoints(_ResultRecord):
    """The source and destination node names of a row, each sorted."""

    sources: tuple[str, ...]
    """Source node names, sorted."""
    destinations: tuple[str, ...]
    """Destination node names, sorted."""


@_record
class SyntheticIngress(_ResultRecord):
    """One attachment of a TE ingress pool: the private link from the pool head to one
    physical source.
    """

    pool_id: str
    """The pool's identifier."""
    source: str
    """The physical source this attachment feeds."""


@_record
class PoolHead(_ResultRecord):
    """The private head of a TE ingress pool and the physical sources it feeds."""

    pool_id: str
    """The pool's identifier."""
    physical_sources: tuple[str, ...]
    """The physical sources behind the pool head."""


@_record
class PoolMetadata(_ResultRecord):
    """A TE ingress pool; ``offer_limit_units`` is its prepared lossy offer budget."""

    head: PoolHead
    """The pool head and its physical sources."""
    offer_limit_units: int = 0
    """The prepared lossy offer budget of the pool (integer units of q)."""
    synthetic_ingress_cost: ClassVar[Literal[1]] = 1
    """The cost of each pool attachment (1)."""


@_record
class DiscardedShare(_ResultRecord):
    """One expansion leaf whose units were discarded, and why."""

    label: str
    """The discarded expansion leaf."""
    units: int
    """Its discarded units."""
    reason: Literal["self_pair", "filtered", "empty_selection"]
    """Why it was discarded: an empty selection, or an entirely excluded declaration (a self pair or identical group labels). If a declaration is excluded for both reasons, the first exclusion in canonical group and node order supplies its reason."""


@_record
class ExpansionAccounting(_ResultRecord):
    """How a declared demand's units were divided: declared, resolved and discarded
    units, with each discarded share.
    """

    base_id: str
    """The declared demand's identifier, before expansion."""
    declared_units: int
    """The declared demand's units: its scaled total, converted to units once."""
    resolved_units: int
    """Units split among eligible leaves, after excluding self and same-label group pairs."""
    discarded_units: int
    """Units of its discarded leaves."""
    discards: tuple[DiscardedShare, ...]
    """Empty-selection shares, or the whole declaration when all pairs are excluded, with their reasons."""


@_record
class ResolvedDemand(_ResultRecord):
    """One demand bound to the prepared graph: its identity, endpoints, priority, units
    at alpha 1 and native configuration.
    """

    id: str
    base_id: str
    endpoints: Endpoints
    priority: int
    order: int
    nominal_units: int
    config: ngc.FlowPolicyConfig
    pool: PoolMetadata | None
    # The YAML declaration that labels this demand's refusals, if any.
    yaml_label: str | None = None


@_record
class MemberWeight(_ResultRecord):
    """One member of a programmed router and its integer weight (0 included)."""

    edge: DirectedLink
    """The member: a directed link leaving the router."""
    weight: int
    """Its integer weight (0 included)."""


@_record
class ProgrammedRouter(_ResultRecord):
    router: str
    """The programmed router."""
    members: tuple[MemberWeight, ...]
    """Its members with their integer weights."""


@_record
class SourceWeight(_ResultRecord):
    """A source's share of declared physical volumes toward the destination and its weight."""

    source: str
    """The source node."""
    nominal_physical: Fraction
    """Its share of declared physical volumes toward the destination (a fraction, before alpha)."""
    weight: int
    """Its integer source weight."""


@_record
class TableReport(_ResultRecord):
    """The WCMP controller's table toward one destination, by name.

    ``programmed`` lists the routers the controller programs; any other router
    splits equally over its members (ECMP).
    """

    destination: str
    """The destination of the table."""
    programmed: tuple[ProgrammedRouter, ...]
    """The routers the controller programs, with their member weights."""
    source_weights: tuple[SourceWeight, ...] | None = field(
        metadata={"null_when": "the scope is not all_routers"}
    )
    """all_routers: each source's share of declared physical volumes and its weight."""


def approximations(demands: ResolvedDemandSet) -> tuple[WeightApproximation, ...]:
    """The weight approximations of a demand set's controller tables."""
    return tuple(
        entry
        for _, table in demands.controller_tables
        for entry in table.approximations
    )


@_record
class ResolvedDemandSet(_ResultRecord):
    """Resolved demands; a set the WCMP controller programs also holds its tables.

    ``controller_tables`` are the internal tables with their destination
    names; ``controller`` is their report (None when the controller programs
    nothing).
    """

    name: str
    demands: tuple[ResolvedDemand, ...]
    accounting: tuple[ExpansionAccounting, ...]
    expansion_template: tuple[ExpansionParent, ...]
    controller_tables: tuple[tuple[str, DestinationTable], ...] = ()
    controller: tuple[TableReport, ...] | None = None

    def controller_table(self, destination: str) -> DestinationTable:
        """The internal table toward one destination router."""
        for name, table in self.controller_tables:
            if name == destination:
                return table
        raise KeyError(
            f"demand set {self.name}: the WCMP controller has no table toward "
            f"{destination}"
        )


@_record
class FailurePattern(_ResultRecord):
    """The nodes and links one draw fails, each sorted; equal patterns are one case."""

    excluded_nodes: tuple[str, ...]
    """Failed nodes, sorted."""
    excluded_links: tuple[str, ...]
    """Failed links (both directions), sorted."""

    def __eq__(self, other):
        if self is other:
            return True
        if type(self) is type(other):
            return (
                self.excluded_nodes == other.excluded_nodes
                and self.excluded_links == other.excluded_links
            )
        return NotImplemented

    def __hash__(self):
        return hash((self.excluded_nodes, self.excluded_links))


@_record
class FailureSelection(_ResultRecord):
    """What one failure rule selected in a draw."""

    rule_index: int
    """The rule's index in its mode."""
    scope: Literal["node", "link", "risk_group"]
    """What the rule selects: node, link or risk_group."""
    selected: tuple[str, ...]
    """The selected entities."""


@_record
class FailureTrace(_ResultRecord):
    """The first draw that produced a failure pattern: its mode and what each rule
    selected.
    """

    draw_index: int
    """The draw that first produced the pattern."""
    mode_index: int | None = field(metadata={"null_when": "the policy has no modes"})
    """The mode drawn."""
    mode_attrs: Mapping[str, JSONValue]
    """The drawn mode's attributes."""
    selections: tuple[FailureSelection, ...]
    """What each rule selected."""
    expanded_nodes: tuple[str, ...]
    """Nodes the selections expand to."""
    expanded_links: tuple[str, ...]
    """Links the selections expand to."""


@_record
class FailureCase(_ResultRecord):
    """One failure case: the baseline or one distinct failure pattern, how many draws
    produced it, and its eligibility (the engine's mask of what the case can use).
    """

    id: str
    kind: Literal["baseline", "failure"]
    pattern: FailurePattern
    occurrences: int
    eligibility: ngc.Eligibility
    trace: FailureTrace | None


@_record
class ReportLocation(_ResultRecord):
    """Where a precision miss happened: the step, the failure case and the MSD probe,
    where they apply.
    """

    step: str | None = field(metadata={"null_when": "the report is outside a workflow"})
    """The step."""
    case_id: str | None = field(
        metadata={"null_when": "the report is outside failure cases"}
    )
    """The case."""
    probe_index: int | None = field(metadata={"null_when": "the report is outside MSD"})
    """The MSD probe."""


@_record
class PreparationScope(_ResultRecord):
    """What a preparation covered: its workflow steps, and the demand sets bound for the
    workflow and for library callers.
    """

    workflow_steps: tuple[str, ...]
    """The workflow steps prepared."""
    workflow_demand_sets: tuple[str, ...]
    """The demand sets the workflow names."""
    library_demand_sets: tuple[str, ...]
    """The demand sets the library caller named."""


@_record
class InputQuantization(_ResultRecord):
    """One physical input converted to units: its binary64 value, its units and the
    rounding error.
    """

    label: str
    """The input or constraint label: where the value is declared."""
    kind: Literal["capacity", "demand", "offer", "design", "min_unreserved"]
    """What the input is: a capacity, demand, offer, design or minimum unreserved bandwidth."""
    binary64_value: float
    """The physical input as given."""
    binary64_hex: str
    """The physical input in hexadecimal."""
    units: int
    """Its value in units (integer units of q)."""
    error: Fraction
    """The signed rounding error, units times q minus the input (physical, a fraction): positive when rounded up."""
    relative_error: Fraction | None = field(metadata={"null_when": "the input is zero"})
    """The signed relative error, the error divided by the input."""


@_record
class InputConstraint(_ResultRecord):
    """The input bound of one positive input v at precision p (q at most 2pv), and
    whether q meets it.
    """

    kind: ClassVar[Literal["input"]] = "input"
    """The record kind, a fixed tag."""
    label: str
    """The input or constraint label: where the value is declared."""
    q_upper_bound: Fraction
    """The largest q at which rounding this input is guaranteed within the precision: 2 times the precision times the input (rounding moves it half a unit at most)."""
    met: bool
    """Whether the chosen q meets it."""


@_record
class SplitConstraint(_ResultRecord):
    """The split bound of a positive amount v over m members at precision p (q at most
    pv/(m - 1)), and whether q meets it.
    """

    kind: Literal["expansion", "source", "router", "tunnel"]
    """Where the split is: expansion, sources, a router or tunnels."""
    label: str
    """The input or constraint label: where the value is declared."""
    incoming_physical: Fraction
    """The physical amount split (a fraction)."""
    basis: Literal["declared", "observed"]
    """declared (from the demands) or observed (from an analysis)."""
    members: int = field(metadata={"minimum": 2})
    """The members the amount is split over."""
    q_upper_bound: Fraction
    """The q bound this split records: the precision times the incoming amount divided by (members - 1). It bounds q, not the split's own error."""
    met: bool
    """Whether the chosen q meets it."""


@_record
class RangeConstraint(_ResultRecord):
    """A range limit: a value in units against its exclusive limit 2^62 at the tested q."""

    kind: Literal["capacity_sum", "cost_sum", "amount"]
    """What is bounded: a capacity sum, a cost sum, or one amount."""
    label: str
    """The input or constraint label: where the value is declared."""
    tested_q: float
    """The q tested."""
    units_value: int
    """The value at that q (integer units of q)."""
    exclusive_limit: int
    """The exclusive native limit (2^62)."""
    met: bool
    """Whether the value is below the limit."""


@_record
class UnverifiedConstraint(_ResultRecord):
    """A supplied program whose splits cannot be checked against the precision target."""

    kind: ClassVar[Literal["unverified"]] = "unverified"
    """The record kind, a fixed tag."""
    label: str
    """The input or constraint label: where the value is declared."""
    reason: ClassVar[Literal["opaque_program"]] = "opaque_program"
    """The split is inside a supplied native program NetGraph cannot inspect."""


UnitConstraint: TypeAlias = (
    InputConstraint | SplitConstraint | RangeConstraint | UnverifiedConstraint
)
"""One precision or range constraint of a units report."""


@_record
class PrecisionMiss(_ResultRecord):
    """One place an analysis missed the precision target: its location, the constraints
    it missed and its input rounding.
    """

    location: ReportLocation
    """Where the miss was observed: step, case and probe."""
    constraints: tuple[InputConstraint | SplitConstraint | UnverifiedConstraint, ...]
    """The constraints the chosen q does not meet there."""
    inexact_inputs: int
    """Inputs not exact at q there."""
    zeroed_inputs: int
    """Positive inputs that round to zero units there."""
    examples: tuple[InputQuantization, ...]
    """Example inputs that miss."""


@_record
class WeightApproximation(_ResultRecord):
    """Controller weights whose exact values reached 2^62 and were apportioned.

    The label names a router (``controller.<set>.<t>.router.<r>``) or, for an
    ``all_routers`` source vector, its source with the largest error
    (``controller.<set>.<t>.source.<s>``). ``max_relative_error`` is the
    largest relative error of the normalized shares over the positive members
    or sources.
    """

    kind: ClassVar[Literal["weight_approximation"]] = "weight_approximation"
    """The record kind, a fixed tag."""
    label: str
    """The router (controller.<set>.<t>.router.<r>) or all_routers source (controller.<set>.<t>.source.<s>) whose weights were apportioned."""
    max_relative_error: Fraction
    """The largest relative error of the apportioned weights (a fraction)."""


@_record
class UnitsReport(_ResultRecord):
    """How preparation chose q: the mode and target, the bounds that set q, input
    rounding, the range sums and every precision miss.
    """

    q: float
    """The bandwidth unit: one unit is q in physical terms."""
    exponent: int
    """q as a power of two: q = 2^exponent."""
    mode: Literal["auto", "manual"]
    """auto (chosen by the recipe) or manual (declared)."""
    precision: float
    """The relative precision target."""
    target_met: bool
    """Whether every declared input and split meets the precision at q."""
    input_convention: ClassVar[Literal["promoted_binary64_half_up"]] = (
        "promoted_binary64_half_up"
    )
    """Physical inputs round half-up from their binary64 value."""
    display_convention: ClassVar[Literal["units_authoritative_binary64_display"]] = (
        "units_authoritative_binary64_display"
    )
    """Units are authoritative; physical values are binary64 displays."""
    scope: PreparationScope
    """What the preparation covered."""
    binding_constraints: tuple[UnitConstraint, ...]
    """The constraints that limited q."""
    input_count: int
    """Physical inputs converted to units."""
    inexact_inputs: int
    """Inputs not exact at q."""
    zeroed_inputs: int
    """Positive inputs that round to zero units."""
    inexact_examples: tuple[InputQuantization, ...]
    """Example inexact inputs."""
    zeroed_examples: tuple[InputQuantization, ...]
    """Example zeroed inputs."""
    max_absolute_input_error: Fraction
    """The largest absolute input error (physical, a fraction)."""
    max_relative_input_error: Fraction
    """The largest absolute relative input error (a fraction)."""
    augmented_capacity_sum_units: int
    """The graph's capacity sum with pool attachments (integer units of q)."""
    augmented_cost_sum: int
    """The graph's cost sum with pool attachments."""
    nominal_split_count: int
    """Splits of the demands at alpha 1 without failures."""
    nominal_splits: tuple[SplitConstraint, ...]
    """Those splits with their bounds on q."""
    misses: tuple[PrecisionMiss, ...]
    """Precision misses observed in analyses."""
    weight_approximations: tuple[WeightApproximation, ...] = ()
    """Controller weights apportioned because they reached 2^62."""

    def with_misses(self, misses: tuple[PrecisionMiss, ...]) -> UnitsReport:
        """This report with further precision misses appended."""
        if not misses:
            return self
        return replace(self, target_met=False, misses=(*self.misses, *misses))

    def with_approximations(
        self, entries: tuple[WeightApproximation, ...]
    ) -> UnitsReport:
        """This report with the controller's weight approximations, each once.

        They change neither ``target_met`` nor the binding constraints.
        """
        known = {entry.label for entry in self.weight_approximations}
        new = tuple(entry for entry in entries if entry.label not in known)
        if not new:
            return self
        return replace(self, weight_approximations=(*self.weight_approximations, *new))


@_record
class OutputSelection(_ResultRecord):
    """The optional outputs an analysis was asked for: native flags, cost reports and
    details.
    """

    native: ngc.OutputOptions
    """The native output flags."""
    cost_distribution: bool
    """Whether cost reports are exported."""
    details: bool = False
    """Whether native per-source, per-tunnel, plan and call fields are exported."""


@_record
class SamplingMetadata(_ResultRecord):
    """How failures were drawn: the seed and its source, the number of draws and the
    fixed drawing rules.
    """

    random_rule_algorithm: ClassVar[Literal["per_entity_bernoulli"]] = (
        "per_entity_bernoulli"
    )
    """The random-rule algorithm: one Bernoulli trial per entity."""
    rng: ClassVar[Literal["random.Random"]] = "random.Random"
    """The random number generator."""
    python_version: ClassVar[str] = sys.version.split()[0]
    """The Python version that drew."""
    seed: int | None = field(metadata={"null_when": "the draws are unseeded"})
    """The base seed."""
    seed_source: Literal["query", "step", "scenario", "policy", "unseeded"]
    """Where the base seed comes from."""
    draw_seed_rule: ClassVar[Literal["base_plus_draw_index"]] = "base_plus_draw_index"
    """Draw i uses the base seed plus i."""
    entity_order: ClassVar[Literal["sorted_identifier"]] = "sorted_identifier"
    """Entities are drawn in sorted identifier order."""
    rule_order: ClassVar[Literal["declaration"]] = "declaration"
    """Rules are applied in declaration order."""
    iterations: int
    """The number of draws."""


@_record
class AnalysisMetadata(_ResultRecord):
    """How an analysis ran: its effective number of workers and its failure sampling."""

    workers: int
    """The effective number of workers."""
    sampling: SamplingMetadata | None = field(
        metadata={"null_when": "the analysis draws no failures"}
    )
    """The failure sampling metadata."""


@_record
class PathCostBin(_ResultRecord):
    """Delivered units at one path cost, in a cost report."""

    cost: int
    """The path cost (analysis graph for a pool)."""
    physical_path_cost: int
    """The path cost without the pool attachment."""
    delivered_units: int
    """The units delivered over paths of this cost."""


@_record
class MarginalCostBin(_ResultRecord):
    """One piece of a marginal cost curve: its marginal cost and its units."""

    marginal_cost: int
    """The increase of the minimum total cost per additional unit."""
    units: int
    """The units delivered at that marginal cost."""


@_record
class DeliveredByPathCost(_ResultRecord):
    """A cost report: delivered units per path cost, cheapest first."""

    kind: ClassVar[Literal["delivered_by_path_cost"]] = "delivered_by_path_cost"
    """The record kind, a fixed tag."""
    cost_domain: Literal["physical_network", "analysis_graph"]
    """physical_network, or analysis_graph when costs include the pool attachment's 1."""
    bins: tuple[PathCostBin, ...]
    """Delivered units per path cost, in ascending cost."""


@_record
class MarginalCurve(_ResultRecord):
    """A cost report: the native marginal cost curve of an optimized flow."""

    kind: ClassVar[Literal["marginal_curve"]] = "marginal_curve"
    """The record kind, a fixed tag."""
    cost_domain: Literal["physical_network", "analysis_graph"]
    """physical_network, or analysis_graph when costs include the pool attachment's 1."""
    bins: tuple[MarginalCostBin, ...]
    """The native marginal cost curve: each piece's marginal cost and units, in ascending cost."""


CostReport: TypeAlias = DeliveredByPathCost | MarginalCurve
"""A cost report: delivered units per path cost, or a marginal cost curve."""

CostUnavailableReason: TypeAlias = Literal[
    "mixed_cost_dag", "unsupported_model", "controller_table"
]
"""Why a requested cost report is unavailable: ``controller_table`` (the demand forwards
on a WCMP controller table, which does not attribute delivery to path costs),
``mixed_cost_dag`` (a pinned DAG whose routes differ in cost) or
``unsupported_model`` (the model's delivery cannot be attributed to path costs).
"""


@_record
class PlacementRow(_ResultRecord):
    """One placed demand: its identity, endpoints, reference request, native result and
    optional reports.
    """

    id: str
    base_id: str
    endpoints: Endpoints
    reference_request_units: int
    result: ngc.PlacementResult
    pool: PoolMetadata | None
    cost_distribution: CostReport | None
    unavailable_outputs: Mapping[Literal["cost_distribution"], CostUnavailableReason]


@_record
class CapacityRow(_ResultRecord):
    """One capacity answer between a source and a destination group: its native result
    and optional reports.
    """

    id: str
    endpoints: Endpoints
    result: ngc.PlacementResult
    pool: PoolMetadata | None
    cost_distribution: CostReport | None
    unavailable_outputs: Mapping[Literal["cost_distribution"], CostUnavailableReason]


@_record
class SelfPair(_ResultRecord):
    """A node paired with itself in a capacity question; its capacity is 0."""

    kind: ClassVar[Literal["self"]] = "self"
    """The record kind, a fixed tag."""
    id: str
    """The row's stable identifier within its analysis."""
    node: str
    """The node that is both source and target."""
    capacity_units: ClassVar[Literal[0]] = 0
    """Always 0: a node's capacity to itself is not a question."""


@_record
class PlacementTotals(_ResultRecord):
    """A state's totals in units: the reference request, the delivery, the losses by
    kind, the shortfall, the delivery ratio and whether every row was placed in full.
    """

    reference_request_units: int
    """The scaled declared requests over the rows (integer units of q)."""
    delivered_units: int
    """Units delivered over the rows."""
    unadmitted_units: int
    """Lossless units not admitted over the rows."""
    source_drop_units: int
    """Lossy units lost at sources over the rows."""
    edge_drop_units: int
    """Lossy units dropped on physical links and TE ingress pool attachments over the rows."""
    reference_shortfall_units: int
    """The reference request minus the delivery (integer units of q)."""
    delivery_ratio: Fraction
    """Delivered over the reference request (a fraction; 1 for no request)."""
    feasible: bool
    """Whether every row delivered its whole reference request, without loss."""


RowT = TypeVar("RowT")

StateName: TypeAlias = Literal["converged", "stale", "repair"]
# The order in which a case computes and reports its states.
STATE_ORDER: tuple[StateName, ...] = ("converged", "stale", "repair")


@_record
class DeadCap(_ResultRecord):
    """A declared root group with no live member in a case, and its fixed cap.

    Its traffic is dropped at its router; ``group`` is its index in the tree.
    """

    destination: str
    """The destination node name."""
    router: str
    """The router node name."""
    forwarding_group: str
    """The forwarding group (tree) name."""
    group: int
    """The root group's index in the tree."""
    cap: Fraction
    """The group's fixed cap: its share of the router's traffic (a fraction)."""


@_record
class ForwardingFailure(_ResultRecord):
    """The case and state's bounded lossy forwarding cycled or reached its round limit.

    This does not prove that no stable answer exists.
    """

    kind: ClassVar[Literal["loss_iteration"]] = "loss_iteration"
    """The record kind, a fixed tag."""
    message: str
    """The native error text."""


@_record
class CaseState(_ResultRecord, Generic[RowT]):
    """One state of a case: its rows and totals, or its forwarding failure.

    ``dead_caps`` lists the dead root groups of a group-scope demand set in the
    converged and repair states; it is None elsewhere.
    """

    rows: tuple[RowT, ...]
    totals: PlacementTotals | None
    failure: ForwardingFailure | None = None
    dead_caps: tuple[DeadCap, ...] | None = None


@_record
class CaseResult(_ResultRecord, Generic[RowT]):
    """One failure case and its states, by name."""

    case: FailureCase
    states: Mapping[StateName, CaseState[RowT]]


class _PreparedResult(_ResultRecord):
    """An analysis of one prepared scenario, with its own precision misses.

    Each analysis record declares ``prepared`` and ``misses`` first;
    ``units_report`` is the preparation's report with these misses appended.
    """

    __slots__ = ()
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]

    @property
    def topology(self) -> PreparedTopology:
        return self.prepared.topology

    @property
    def units_report(self) -> UnitsReport:
        report = self.prepared.units_report.with_misses(self.misses)
        # A demand set bound after preparation brings its own approximations.
        demands = getattr(getattr(self, "query", None), "demands", None)
        if demands is None:
            return report
        return report.with_approximations(approximations(demands))


@_record
class CapacityAnalysis(_PreparedResult):
    """The answer of ``capacity``: the question asked and one result per failure case."""

    kind: ClassVar[Literal["capacity"]] = "capacity"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    outputs: OutputSelection
    question: Literal["lossless_bound", "fixed_offer_delivery", "first_hop_experiment"]
    offer_source: Literal["unlimited", "explicit", "design", "first_hop"]
    cases: tuple[CaseResult[CapacityRow | SelfPair], ...]
    query: CapacityQuery


@_record
class PlacementAnalysis(_PreparedResult):
    """The answer of ``place``: alpha, one result per failure case and the expansion
    accounting.
    """

    kind: ClassVar[Literal["placement"]] = "placement"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    outputs: OutputSelection
    alpha: ExactAlpha
    cases: tuple[CaseResult[PlacementRow], ...]
    accounting: tuple[ExpansionAccounting, ...]
    query: PlacementQuery


@_record
class SensitivityAnalysis(_PreparedResult):
    """The answer of ``edge_sensitivity``: the native baseline and the reduction each
    directed edge's removal causes.
    """

    kind: ClassVar[Literal["sensitivity"]] = "sensitivity"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    outputs: OutputSelection
    endpoints: Endpoints
    question: Literal["lossless_bound", "fixed_offer_delivery"]
    offer_source: Literal["unlimited", "explicit", "design"]
    result: ngc.SensitivityResult
    query: SensitivityQuery


@_record
class PathRow(_ResultRecord):
    """The paths between one source and destination group: their cost and native paths."""

    id: str
    endpoints: Endpoints
    kind: Literal["paths", "self"]
    cost: int | None
    paths: tuple[ngc.Path, ...] | None


@_record
class PathAnalysis(_PreparedResult):
    """The answer of ``paths``: one row per endpoint pair."""

    kind: ClassVar[Literal["paths"]] = "paths"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    algorithm: Literal["spf", "ksp"]
    mode: Literal["combine", "pairwise"]
    costs_only: bool
    rows: tuple[PathRow, ...]
    query: PathQuery


MSDStatus: TypeAlias = Literal[
    "feasible", "none_feasible", "range", "stagnation", "limit", "trivial"
]
"""How an MSD search ended; each value is explained under ``MSDAnalysisJSON`` in the
results reference.
"""
MSDStopReason: TypeAlias = Literal[
    "tolerance",
    "alpha_bound",
    "bracket_limit",
    "bisect_limit",
    "offer_range",
    "representable_limit",
    "nothing_offered",
    "unit_resolution",
]
"""Why an MSD search stopped; each value is explained under ``MSDAnalysisJSON`` in the
results reference.
"""
MSDProof: TypeAlias = Literal[
    "fixed_program", "single_controller", "nothing_offered", "unproved"
]
"""What makes feasibility downward closed in alpha for an MSD question; each value is
explained under ``MSDAnalysisJSON`` in the results reference.
"""


@_record
class RangeRefusal(_ResultRecord):
    """Why an MSD probe was out of range."""

    label: str
    """The input or constraint label: where the value is declared."""
    reason: Literal["scaled_nonfinite", "native_units_range"]
    """scaled_nonfinite or native_units_range."""
    message: str
    """The refusal text."""
    binary64_hex: str | None = field(
        metadata={"null_when": "the refused amount is not a binary64 value"}
    )
    """The refused binary64 value in hexadecimal."""


@_record
class MSDProbe(_ResultRecord):
    """One MSD probe: its alpha, outcome and totals."""

    index: int
    """The probe's position in the search history (0 first)."""
    alpha: ExactAlpha
    """The probe's exact alpha."""
    outcome: Literal["feasible", "infeasible", "below_resolution", "range"]
    """feasible, infeasible, below_resolution (rounds to zero) or range (out of native range)."""
    totals: PlacementTotals | None = field(
        metadata={"null_when": "the probe was out of range"}
    )
    """The probe's totals."""
    range_refusal: RangeRefusal | None = field(
        metadata={"null_when": "the probe was in range"}
    )
    """Why the probe was out of range."""


@_record
class UpperCertificate(_ResultRecord):
    """A proved bracket around the largest feasible alpha: a feasible probe and the
    smallest infeasible probe above it.
    """

    proof: Literal["fixed_program", "single_controller"]
    """What proves the bracket."""
    lower: ExactAlpha
    """The feasible lower alpha."""
    upper: ExactAlpha
    """The infeasible upper alpha."""
    lower_probe_index: int
    """The history index of the lower probe."""
    upper_probe_index: int
    """The history index of the upper probe."""


@_record
class MSDAnalysis(_PreparedResult):
    """The answer of ``maximum_supported_demand``: the largest tested feasible alpha,
    how the search ended, its proof and every probe.

    The values of ``search_status``, ``stop_reason`` and ``proof`` are explained
    under ``MSDAnalysisJSON`` in the results reference.
    """

    kind: ClassVar[Literal["msd"]] = "msd"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    outputs: OutputSelection
    alpha_feasible: ExactAlpha | None
    best_probe_index: int | None
    monotone_proven: bool
    proof: MSDProof
    upper_certificate: UpperCertificate | None
    search_status: MSDStatus
    stop_reason: MSDStopReason
    history: tuple[MSDProbe, ...]
    query: MSDQuery
    best_rows: tuple[PlacementRow, ...] | None
    best_accounting: tuple[ExpansionAccounting, ...] | None
    probe_rows: Mapping[int, tuple[PlacementRow, ...]] | None


@_record
class TunnelCountRow(_ResultRecord):
    """One demand's evaluation at one tunnel count.

    ``count`` is the requested count per head, or the limit of an ``up_to``
    row; the chosen count is ``result.plan.tunnels_per_head``. The plan's
    tunnel cost is on the analysis graph: a pool row adds one cost-1 ingress
    hop per tunnel, which ``physical_tunnel_cost`` leaves out.
    ``lossless_at_design_units`` is min(design, the plan's largest lossless
    offer).
    """

    id: str
    base_id: str
    endpoints: Endpoints
    count: int
    up_to: bool
    result: ngc.PlacementResult
    pool: PoolMetadata | None
    lossless_at_design_units: int
    physical_tunnel_cost: int


@_record
class TunnelCountAnalysis(_PreparedResult):
    """The answer of ``tunnel_counts``: one row per demand and count."""

    kind: ClassVar[Literal["tunnel_counts"]] = "tunnel_counts"
    prepared: PreparedScenario
    misses: tuple[PrecisionMiss, ...]
    metadata: AnalysisMetadata
    outputs: OutputSelection
    rows: tuple[TunnelCountRow, ...]
    query: TunnelCountQuery


AnalysisResult: TypeAlias = (
    CapacityAnalysis
    | PlacementAnalysis
    | SensitivityAnalysis
    | PathAnalysis
    | MSDAnalysis
    | TunnelCountAnalysis
)
"""The result of any analysis: capacity, placement, sensitivity, paths, MSD or tunnel
counts.
"""


@_record
class BuildGraphResult(_ResultRecord):
    """The BuildGraph step's result: the network in NetworkX node-link form."""

    kind: ClassVar[Literal["build_graph"]] = "build_graph"
    """The record kind, a fixed tag."""
    add_reverse: bool
    """Whether the exported graph has a reverse edge per link."""
    node_count: int
    """Nodes in the exported graph."""
    edge_count: int
    """Edges in the exported graph (two per link with add_reverse)."""
    graph: Mapping[str, JSONValue]
    """The node-link JSON of the network."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph", frozen_attrs(self.graph, "BuildGraph.graph"))


@_record
class NetworkStatsResult(_ResultRecord):
    """The NetworkStats step's result: counts, and capacity, cost and degree statistics;
    capacities are physical amounts.
    """

    kind: ClassVar[Literal["network_stats"]] = "network_stats"
    """The record kind, a fixed tag."""
    node_count: int
    """Nodes counted."""
    link_count: int
    """Links counted."""
    total_capacity: float
    """The sum of link capacities."""
    mean_capacity: float
    """The mean link capacity."""
    median_capacity: float
    """The median link capacity."""
    min_capacity: float
    """The smallest link capacity."""
    max_capacity: float
    """The largest link capacity."""
    mean_cost: float
    """The mean link cost."""
    median_cost: float
    """The median link cost."""
    min_cost: int
    """The smallest link cost."""
    max_cost: int
    """The largest link cost."""
    mean_degree: float
    """The mean node degree."""
    median_degree: float
    """The median node degree."""
    min_degree: float
    """The smallest node degree."""
    max_degree: float
    """The largest node degree."""


@_record
class HardwareRow(_ResultRecord):
    """Hardware cost and power of one hierarchy path."""

    path: str
    """The hierarchy path of the row (empty for the root level)."""
    platform_capex: float
    """Platform cost of the path's nodes."""
    platform_power_watts: float
    """Platform power of the path's nodes, in watts."""
    optics_capex: float
    """Optic cost of the path's link ends."""
    optics_power_watts: float
    """Optic power of the path's link ends, in watts."""
    capex_total: float
    """Platform and optic cost."""
    power_total_watts: float
    """Platform and optic power, in watts."""


@_record
class _CostPowerLevels(_ResultRecord, Mapping[int, tuple[HardwareRow, ...]]):
    """Requested levels sharing the final aggregate beyond the deepest name."""

    rows: tuple[tuple[HardwareRow, ...], ...]
    requested: int

    def __eq__(self, other):
        if self is other:
            return True
        if not isinstance(other, Mapping):
            return NotImplemented
        if len(self) != len(other):
            return False
        return all(key in other and rows == other[key] for key, rows in self.items())

    __hash__ = None  # type: ignore[assignment]

    def __getitem__(self, level: int) -> tuple[HardwareRow, ...]:
        key = level
        try:
            hashed = hash(key)
        except TypeError:
            # Let dict produce its interpreter-specific unhashable-key refusal.
            return {}[key]
        candidate = int(key) if type(key) in (int, bool) else None
        if candidate is not None and candidate == key and hash(candidate) == hashed:
            if 0 <= candidate <= self.requested:
                return self.rows[min(candidate, len(self.rows) - 1)]
            raise KeyError(key)
        # Nonnegative integer keys hash to their value modulo this modulus.
        # Inspect exactly that bucket, retaining dict's equality semantics for
        # float, complex, Fraction and user-defined keys, without materializing it.
        if hashed >= 0:
            for candidate in range(hashed, self.requested + 1, sys.hash_info.modulus):
                if candidate == key:
                    return self.rows[min(candidate, len(self.rows) - 1)]
        raise KeyError(key)

    def __iter__(self):
        return iter(range(self.requested + 1))

    def __len__(self) -> int:
        return self.requested + 1


@_record
class CostPowerResult(_ResultRecord):
    """The CostPower step's result: hardware rows per aggregation level."""

    kind: ClassVar[Literal["cost_power"]] = "cost_power"
    include_disabled: bool
    aggregation_level: int
    levels: Mapping[int, tuple[HardwareRow, ...]]

    def __post_init__(self) -> None:
        if isinstance(self.levels, _CostPowerLevels):
            return

        object.__setattr__(
            self,
            "levels",
            MappingProxyType(
                {
                    level: tuple(sorted(rows, key=lambda row: row.path))
                    for level, rows in sorted(self.levels.items())
                }
            ),
        )


DomainResult: TypeAlias = BuildGraphResult | NetworkStatsResult | CostPowerResult
"""The result of a built-in domain step: BuildGraph, NetworkStats or CostPower."""


@_record
class StepResult(_ResultRecord):
    """One workflow step's published result: its name, type, order, seeds, question and
    result.
    """

    name: str
    step_type: str
    execution_order: int
    scenario_seed: int | None
    step_seed: int | None
    seed_source: Literal["explicit-step", "scenario-derived", "none"]
    result: object
    question: StepQuestion


@_record
class RunMetadata(_ResultRecord):
    """What produced a run: package versions, the native extension's hash, the Python
    version and the seed.
    """

    schema_version: ClassVar[Literal["1.0"]] = "1.0"
    """The results schema version."""
    netgraph_version: str
    """The installed ngraph package version."""
    core_version: str
    """The netgraph-core version."""
    core_extension_sha256: str
    """The SHA-256 of the loaded native extension."""
    python_version: str
    """The Python version."""
    seed: int | None = field(metadata={"null_when": "the scenario sets no seed"})
    """The scenario seed."""


@_record
class RunResult(_ResultRecord):
    """One run; ``units_report`` adds every step's precision misses, by step."""

    metadata: RunMetadata
    units_report: UnitsReport
    steps: tuple[StepResult, ...]
    prepared: PreparedScenario

    @property
    def topology(self) -> PreparedTopology:
        return self.prepared.topology


@_record
class ExpansionLeaf(_ResultRecord):
    """A leaf of a demand's expansion tree: one resolved demand, or a discarded share
    with its reason.
    """

    id: str
    order: int
    endpoints: Endpoints | None
    discard_reason: Literal["self_pair", "filtered", "empty_selection"] | None


@_record
class ExpansionSplit(_ResultRecord):
    """A node of a demand's expansion tree whose units split over its children."""

    label: str
    children: tuple[ExpansionSplit | ExpansionLeaf, ...]


@_record
class ExpansionParent(_ResultRecord):
    """One declared demand: its declaration and its expansion tree.

    ``config`` is the native configuration of its first resolved leaf (None
    when every leaf of a named pinned declaration was discarded).
    """

    source: Selector
    target: Selector
    priority: int
    policy: DemandPolicy
    config: ngc.FlowPolicyConfig | None
    base_id: str
    declaration_ordinal: int
    expand_leaf_index: int | None
    physical_volume: float
    mode: Literal["combine", "pairwise"]
    group_mode: Literal["flatten", "per_group", "group_pairwise"]
    root: ExpansionSplit | ExpansionLeaf


if TYPE_CHECKING:
    StepQuestion: TypeAlias = (
        CapacityQuery
        | PlacementQuery
        | SensitivityQuery
        | PathQuery
        | MSDQuery
        | TunnelCountQuery
        | BuildGraph
        | NetworkStats
        | CostPower
        | Mapping[str, JSONValue]
    )
    """A step's recorded question: an analysis's own query, a built-in domain step's
    configuration, or a custom step's finite JSON parameters.
    """
else:
    StepQuestion = object


@_record
class StepContext(_ResultRecord):
    """What a custom step's ``run`` receives: the prepared scenario, earlier steps'
    results, its name, order and seed.
    """

    prepared: PreparedScenario
    prior_results: Mapping[str, StepResult]
    step_name: str
    execution_order: int
    seed: int | None
    seed_source: Literal["explicit-step", "scenario-derived", "none"]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "prior_results", MappingProxyType(dict(self.prior_results))
        )


@_record
class StepOutput(_ResultRecord):
    """What a custom step's ``run`` returns: its question and its result."""

    question: StepQuestion
    result: object


@_record
class ExportContext(_ResultRecord):
    """What a result encoder receives: the prepared scenario and the run's units report."""

    prepared: PreparedScenario
    units_report: UnitsReport

    @property
    def topology(self) -> PreparedTopology:
        return self.prepared.topology


def exact_alpha(value: float) -> ExactAlpha:
    """The exact binary64 ratio of a positive physical multiplier."""
    alpha = physical(value, "alpha", positive=True)
    numerator, denominator = alpha.as_integer_ratio()
    return ExactAlpha(alpha, numerator, denominator)
