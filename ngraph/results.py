"""Owned analysis envelopes, exact reports and normalized questions.

Computational results remain native values with their native lifetime and fields.
"""

from __future__ import annotations

import sys
from collections.abc import Mapping
from dataclasses import MISSING, FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from functools import cache
from reprlib import recursive_repr
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Annotated,
    ClassVar,
    Generic,
    Literal,
    TypeAlias,
    TypeVar,
    dataclass_transform,
)

import netgraph_core as ngc

from ngraph.utils.values import JSONValue, frozen_attrs, physical

if TYPE_CHECKING:
    from ngraph.analysis.capacity import CapacityQuery
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
    return tuple(field.name for field in fields(kind))


def _compile_init(kind: type):
    """Build a record class's constructor, as ``dataclasses`` would write it."""
    names, defaults = [], {}
    for field in fields(kind):
        assert field.default_factory is MISSING and not field.kw_only, field.name
        if field.default is not MISSING:
            defaults[f"_default_{field.name}"] = field.default
            names.append(f"{field.name}=_default_{field.name}")
        else:
            names.append(field.name)
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


@dataclass_transform(frozen_default=True, eq_default=False)
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


# A record field's declaration is also its output schema: an ``Annotated``
# mapping adds JSON Schema keywords to the schema of its type.


@_record
class ExactAlpha(_ResultRecord):
    value: Annotated[float, {"exclusiveMinimum": 0}]
    numerator: int
    denominator: Annotated[int, {"minimum": 1}]


@_record
class Endpoints(_ResultRecord):
    sources: tuple[str, ...]
    destinations: tuple[str, ...]


@_record
class SyntheticIngress(_ResultRecord):
    pool_id: str
    source: str


@_record
class PoolHead(_ResultRecord):
    pool_id: str
    physical_sources: tuple[str, ...]


@_record
class PoolMetadata(_ResultRecord):
    head: PoolHead
    offer_limit_units: ClassVar[Literal[0]] = 0
    synthetic_ingress_cost: ClassVar[Literal[1]] = 1


@_record
class DiscardedShare(_ResultRecord):
    label: str
    units: int
    reason: Literal["self_pair", "filtered", "empty_selection"]


@_record
class ExpansionAccounting(_ResultRecord):
    base_id: str
    declared_units: int
    resolved_units: int
    discarded_units: int
    discards: tuple[DiscardedShare, ...]


@_record
class ResolvedDemand(_ResultRecord):
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
class ResolvedDemandSet(_ResultRecord):
    name: str
    demands: tuple[ResolvedDemand, ...]
    accounting: tuple[ExpansionAccounting, ...]
    expansion_template: tuple[ExpansionParent, ...]


@_record
class FailurePattern(_ResultRecord):
    """Canonical failure mask used as a scheduling and sampling key."""

    excluded_nodes: tuple[str, ...]
    excluded_links: tuple[str, ...]

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
    rule_index: int
    scope: Literal["node", "link", "risk_group"]
    selected: tuple[str, ...]


@_record
class FailureTrace(_ResultRecord):
    draw_index: int
    mode_index: int | None
    mode_attrs: Mapping[str, JSONValue]
    selections: tuple[FailureSelection, ...]
    expanded_nodes: tuple[str, ...]
    expanded_links: tuple[str, ...]


@_record
class FailureCase(_ResultRecord):
    id: str
    kind: Literal["baseline", "failure"]
    pattern: FailurePattern
    occurrences: int
    eligibility: ngc.Eligibility
    trace: FailureTrace | None


@_record
class ReportLocation(_ResultRecord):
    step: str | None
    case_id: str | None
    probe_index: int | None


@_record
class PreparationScope(_ResultRecord):
    workflow_steps: tuple[str, ...]
    workflow_demand_sets: tuple[str, ...]
    library_demand_sets: tuple[str, ...]


@_record
class InputQuantization(_ResultRecord):
    label: str
    kind: Literal["capacity", "demand", "offer", "design", "min_unreserved"]
    binary64_value: float
    binary64_hex: str
    units: int
    error: Fraction
    relative_error: Fraction | None


@_record
class InputConstraint(_ResultRecord):
    kind: ClassVar[Literal["input"]] = "input"
    label: str
    q_upper_bound: Fraction
    met: bool


@_record
class SplitConstraint(_ResultRecord):
    kind: Literal["expansion", "source", "router", "tunnel"]
    label: str
    incoming_physical: Fraction
    basis: Literal["declared", "observed"]
    members: Annotated[int, {"minimum": 2}]
    q_upper_bound: Fraction
    met: bool


@_record
class RangeConstraint(_ResultRecord):
    kind: Literal["capacity_sum", "cost_sum", "amount"]
    label: str
    tested_q: float
    units_value: int
    exclusive_limit: int
    met: bool


@_record
class UnverifiedConstraint(_ResultRecord):
    kind: ClassVar[Literal["unverified"]] = "unverified"
    label: str
    reason: ClassVar[Literal["opaque_program"]] = "opaque_program"


UnitConstraint: TypeAlias = (
    InputConstraint | SplitConstraint | RangeConstraint | UnverifiedConstraint
)


@_record
class PrecisionMiss(_ResultRecord):
    location: ReportLocation
    constraints: tuple[InputConstraint | SplitConstraint | UnverifiedConstraint, ...]
    inexact_inputs: int
    zeroed_inputs: int
    examples: tuple[InputQuantization, ...]


@_record
class UnitsReport(_ResultRecord):
    q: float
    exponent: int
    mode: Literal["auto", "manual"]
    precision: float
    target_met: bool
    input_convention: ClassVar[Literal["promoted_binary64_half_up"]] = (
        "promoted_binary64_half_up"
    )
    display_convention: ClassVar[Literal["units_authoritative_binary64_display"]] = (
        "units_authoritative_binary64_display"
    )
    scope: PreparationScope
    binding_constraints: tuple[UnitConstraint, ...]
    input_count: int
    inexact_inputs: int
    zeroed_inputs: int
    inexact_examples: tuple[InputQuantization, ...]
    zeroed_examples: tuple[InputQuantization, ...]
    max_absolute_input_error: Fraction
    max_relative_input_error: Fraction
    augmented_capacity_sum_units: int
    augmented_cost_sum: int
    nominal_split_count: int
    nominal_splits: tuple[SplitConstraint, ...]
    misses: tuple[PrecisionMiss, ...]

    def with_misses(self, misses: tuple[PrecisionMiss, ...]) -> UnitsReport:
        """This report with further precision misses appended."""
        if not misses:
            return self
        return replace(self, target_met=False, misses=(*self.misses, *misses))


@_record
class OutputSelection(_ResultRecord):
    native: ngc.OutputOptions
    cost_distribution: bool
    details: bool = False


@_record
class SamplingMetadata(_ResultRecord):
    random_rule_algorithm: ClassVar[Literal["per_entity_bernoulli"]] = (
        "per_entity_bernoulli"
    )
    rng: ClassVar[Literal["random.Random"]] = "random.Random"
    python_version: ClassVar[str] = sys.version.split()[0]
    seed: int | None
    seed_source: Literal["query", "step", "scenario", "policy", "unseeded"]
    draw_seed_rule: ClassVar[Literal["base_plus_draw_index"]] = "base_plus_draw_index"
    entity_order: ClassVar[Literal["sorted_identifier"]] = "sorted_identifier"
    rule_order: ClassVar[Literal["declaration"]] = "declaration"
    iterations: int


@_record
class AnalysisMetadata(_ResultRecord):
    workers: int
    sampling: SamplingMetadata | None


@_record
class PathCostBin(_ResultRecord):
    cost: int
    physical_path_cost: int
    delivered_units: int


@_record
class MarginalCostBin(_ResultRecord):
    marginal_cost: int
    units: int


@_record
class DeliveredByPathCost(_ResultRecord):
    kind: ClassVar[Literal["delivered_by_path_cost"]] = "delivered_by_path_cost"
    cost_domain: Literal["physical_network", "analysis_graph"]
    bins: tuple[PathCostBin, ...]


@_record
class MarginalCurve(_ResultRecord):
    kind: ClassVar[Literal["marginal_curve"]] = "marginal_curve"
    cost_domain: Literal["physical_network", "analysis_graph"]
    bins: tuple[MarginalCostBin, ...]


CostReport: TypeAlias = DeliveredByPathCost | MarginalCurve
CostUnavailableReason: TypeAlias = Literal["mixed_cost_dag", "unsupported_model"]


@_record
class PlacementRow(_ResultRecord):
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
    id: str
    endpoints: Endpoints
    result: ngc.PlacementResult
    pool: PoolMetadata | None
    cost_distribution: CostReport | None
    unavailable_outputs: Mapping[Literal["cost_distribution"], CostUnavailableReason]


@_record
class SelfPair(_ResultRecord):
    kind: ClassVar[Literal["self"]] = "self"
    id: str
    node: str
    capacity_units: ClassVar[Literal[0]] = 0


@_record
class PlacementTotals(_ResultRecord):
    reference_request_units: int
    delivered_units: int
    unadmitted_units: int
    source_drop_units: int
    edge_drop_units: int
    reference_shortfall_units: int
    delivery_ratio: Fraction
    feasible: bool


RowT = TypeVar("RowT")


@_record
class CaseState(_ResultRecord, Generic[RowT]):
    rows: tuple[RowT, ...]
    totals: PlacementTotals | None


@_record
class CaseResult(_ResultRecord, Generic[RowT]):
    case: FailureCase
    states: Mapping[Literal["converged"], CaseState[RowT]]


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
        return self.prepared.units_report.with_misses(self.misses)


@_record
class CapacityAnalysis(_PreparedResult):
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
    id: str
    endpoints: Endpoints
    kind: Literal["paths", "self"]
    cost: int | None
    paths: tuple[ngc.Path, ...] | None


@_record
class PathAnalysis(_PreparedResult):
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
MSDStopReason: TypeAlias = Literal[
    "tolerance",
    "alpha_bound",
    "bracket_limit",
    "bisect_limit",
    "offer_range",
    "representable_limit",
    "declared_zero",
    "unit_resolution",
]
MSDProof: TypeAlias = Literal[
    "fixed_program", "single_controller", "declared_zero", "unproved"
]


@_record
class RangeRefusal(_ResultRecord):
    label: str
    reason: Literal["scaled_nonfinite", "native_units_range"]
    message: str
    binary64_hex: str | None


@_record
class MSDProbe(_ResultRecord):
    index: int
    alpha: ExactAlpha
    outcome: Literal["feasible", "infeasible", "below_resolution", "range"]
    totals: PlacementTotals | None
    range_refusal: RangeRefusal | None


@_record
class UpperCertificate(_ResultRecord):
    proof: Literal["fixed_program", "single_controller"]
    lower: ExactAlpha
    upper: ExactAlpha
    lower_probe_index: int
    upper_probe_index: int


@_record
class MSDAnalysis(_PreparedResult):
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


AnalysisResult: TypeAlias = (
    CapacityAnalysis
    | PlacementAnalysis
    | SensitivityAnalysis
    | PathAnalysis
    | MSDAnalysis
)


@_record
class BuildGraphResult(_ResultRecord):
    kind: ClassVar[Literal["build_graph"]] = "build_graph"
    add_reverse: bool
    node_count: int
    link_count: int
    graph: Mapping[str, JSONValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "graph", frozen_attrs(self.graph, "BuildGraph.graph"))


@_record
class NetworkStatsResult(_ResultRecord):
    kind: ClassVar[Literal["network_stats"]] = "network_stats"
    node_count: int
    link_count: int
    total_capacity: float
    mean_capacity: float
    median_capacity: float
    min_capacity: float
    max_capacity: float
    mean_cost: float
    median_cost: float
    min_cost: float
    max_cost: float
    mean_degree: float
    median_degree: float
    min_degree: float
    max_degree: float


@_record
class HardwareRow(_ResultRecord):
    path: str
    platform_capex: float
    platform_power_watts: float
    optics_capex: float
    optics_power_watts: float
    capex_total: float
    power_total_watts: float


@_record
class CostPowerResult(_ResultRecord):
    kind: ClassVar[Literal["cost_power"]] = "cost_power"
    include_disabled: bool
    aggregation_level: int
    levels: Mapping[int, tuple[HardwareRow, ...]]

    def __post_init__(self) -> None:
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


@_record
class StepResult(_ResultRecord):
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
    schema_version: ClassVar[Literal["1.0"]] = "1.0"
    netgraph_version: str
    core_version: str
    core_extension_sha256: str
    python_version: str
    seed: int | None


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
    id: str
    order: int
    endpoints: Endpoints | None
    discard_reason: Literal["self_pair", "filtered", "empty_selection"] | None


@_record
class ExpansionSplit(_ResultRecord):
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
    # A step's recorded question: an analysis's own query, a built-in domain
    # step's configuration, or a custom step's finite JSON parameters.
    StepQuestion: TypeAlias = (
        CapacityQuery
        | PlacementQuery
        | SensitivityQuery
        | PathQuery
        | MSDQuery
        | BuildGraph
        | NetworkStats
        | CostPower
        | Mapping[str, JSONValue]
    )
else:
    StepQuestion = object


@_record
class StepContext(_ResultRecord):
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
    question: StepQuestion
    result: object


@_record
class ExportContext(_ResultRecord):
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
