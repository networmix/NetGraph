"""Editable scenarios, read-only shared preparation and typed workflow execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from dataclasses import KW_ONLY, dataclass, field, replace

from ngraph.analysis.metadata import run_metadata
from ngraph.analysis.preparation import PreparedScenario, prepare_scenario
from ngraph.analysis.units import UnitsSettings
from ngraph.model.components import ComponentsLibrary
from ngraph.model.demand import (
    DemandSet,
    ForwardingGroup,
    RouteSpec,
    RoutingDomain,
    SupportSpec,
    WCMPController,
    WeightSpec,
)
from ngraph.model.failure import FailurePolicy
from ngraph.model.network import Network
from ngraph.results import (
    CapacityAnalysis,
    MSDAnalysis,
    PathAnalysis,
    PlacementAnalysis,
    RunResult,
    SensitivityAnalysis,
    StepContext,
    TunnelCountAnalysis,
)
from ngraph.utils.values import frozen_dict, own_scalars
from ngraph.workflow.base import WorkflowStep, validate_unique_step_names


def _named(values, kind, label):
    if values is None:
        return frozen_dict()
    if not isinstance(values, Mapping):
        raise TypeError(f"{label}: expected mapping")
    owned = {}
    for name, value in values.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{label}: expected nonempty string names")
        if not isinstance(value, kind):
            raise TypeError(f"{label}.{name}: expected {kind.__name__}")
        owned[str.__str__(name)] = value
    return frozen_dict(owned)


@dataclass(frozen=True, eq=False)
class Scenario:
    """Named domain inputs, fixed at construction.

    The network and the components library keep editable dicts of immutable
    records; ``prepare`` takes a read-only view of them, so later edits do not
    reach a prepared scenario. ``dataclasses.replace`` builds an edited copy.
    """

    network: Network
    workflow: Sequence[WorkflowStep] = ()
    _: KW_ONLY
    demand_sets: Mapping[str, DemandSet] = field(default_factory=frozen_dict)
    failure_policies: Mapping[str, FailurePolicy] = field(default_factory=frozen_dict)
    components_library: ComponentsLibrary = field(default_factory=ComponentsLibrary)
    seed: int | None = None
    units: UnitsSettings = field(default_factory=UnitsSettings)
    routes: Mapping[str, RouteSpec] = field(default_factory=frozen_dict)
    supports: Mapping[str, SupportSpec] = field(default_factory=frozen_dict)
    weights: Mapping[str, WeightSpec] = field(default_factory=frozen_dict)
    forwarding_groups: Mapping[str, ForwardingGroup] = field(
        default_factory=frozen_dict
    )
    routing: RoutingDomain | None = None
    wcmp_controller: WCMPController | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.network, Network):
            raise TypeError("Scenario.network: expected Network")
        seed = self.seed
        if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
            raise ValueError("Scenario.seed: expected integer or None")
        if self.units is None:
            object.__setattr__(self, "units", UnitsSettings())
        if not isinstance(self.units, UnitsSettings):
            raise TypeError("Scenario.units: expected UnitsSettings")
        if self.components_library is None:
            object.__setattr__(self, "components_library", ComponentsLibrary())
        if not isinstance(self.components_library, ComponentsLibrary):
            raise TypeError("Scenario.components_library: expected ComponentsLibrary")
        own_scalars(self, "Scenario", ("seed",))
        object.__setattr__(self, "workflow", tuple(self.workflow))
        if not all(isinstance(step, WorkflowStep) for step in self.workflow):
            raise TypeError("Scenario.workflow: expected WorkflowStep values")
        for name, kind in (
            ("demand_sets", DemandSet),
            ("failure_policies", FailurePolicy),
            ("routes", RouteSpec),
            ("supports", SupportSpec),
            ("weights", WeightSpec),
            ("forwarding_groups", ForwardingGroup),
        ):
            object.__setattr__(self, name, _named(getattr(self, name), kind, name))
        if self.routing is not None and not isinstance(self.routing, RoutingDomain):
            raise TypeError("Scenario.routing: expected RoutingDomain or None")
        if self.wcmp_controller is not None and not isinstance(
            self.wcmp_controller, WCMPController
        ):
            raise TypeError("Scenario.wcmp_controller: expected WCMPController or None")
        # The routing domain and the forwarding groups serve the controller only.
        if self.wcmp_controller is not None and self.routing is None:
            raise ValueError("wcmp_controller: requires routing")
        if self.wcmp_controller is None and self.routing is not None:
            raise ValueError(
                "routing: constrains the WCMP controller only; declare wcmp_controller"
            )
        if self.wcmp_controller is None and self.forwarding_groups:
            raise ValueError("forwarding_groups: require wcmp_controller")
        for name, value in self.demand_sets.items():
            if name != value.name:
                raise ValueError(
                    f"demand_sets.{name}: name/key disagreement {value.name}"
                )

    @classmethod
    def from_yaml(
        cls, yaml_str: str, default_components: ComponentsLibrary | None = None
    ) -> Scenario:
        """Parse one closed scenario declaration and retain editable domain inputs."""
        from ngraph.dsl.blueprints.expand import expand_network_dsl
        from ngraph.dsl.inputs import (
            closed,
            controller_declarations,
            demand_sets,
            named_declarations,
        )
        from ngraph.dsl.loader import load_scenario_yaml
        from ngraph.model.failure import build_failure_policies
        from ngraph.model.risk import (
            MembershipIndex,
            build_risk_groups,
            generate_risk_groups,
            parse_generate_spec,
            resolve_membership_rules,
        )
        from ngraph.utils.seed_manager import SeedManager
        from ngraph.workflow.parse import build_workflow_steps

        data = load_scenario_yaml(yaml_str)
        master = data.get("seed")
        if master is not None and (
            isinstance(master, bool) or not isinstance(master, int)
        ):
            raise ValueError("seed: expected integer")
        network = expand_network_dsl(data)
        groups, generate = build_risk_groups(data.get("risk_groups", []))
        for group in groups:
            if group.name in network.risk_groups:
                raise ValueError(f"Duplicate risk group name {group.name!r}")
            network.risk_groups[group.name] = group
        resolve_membership_rules(network)
        if generate:
            # Generation reads the resolved memberships; refuse a broken
            # declaration with its own message before generating from it.
            MembershipIndex.build(network)
        for raw in generate:
            for group in generate_risk_groups(network, parse_generate_spec(raw)):
                if group.name in network.risk_groups:
                    raise ValueError(
                        f"Generated risk group {group.name!r} conflicts with existing group"
                    )
                network.risk_groups[group.name] = group
        index = MembershipIndex.build(network)
        for group in network.risk_groups.values():
            if group.disabled:
                members = index.members(group.name, recursive=True)
                for node_name in sorted(members.nodes):
                    network.disable_node(node_name)
                for link_id in sorted(members.links):
                    network.disable_link(link_id)
        components = (
            default_components.clone()
            if default_components is not None
            else ComponentsLibrary()
        )
        if data.get("components"):
            components.merge(ComponentsLibrary.from_dict(data["components"]))
        unit_values = closed(
            data.get("units", {}), ("resolution", "precision"), "units"
        )
        routes, supports, weights = named_declarations(data)
        routing, controller, forwarding_groups = controller_declarations(data)
        seeds = SeedManager(master)
        return cls(
            network,
            build_workflow_steps(
                data.get("workflow", []),
                lambda name: seeds.derive_seed("workflow_step", name),
            ),
            demand_sets=demand_sets(data.get("demands", {})),
            failure_policies=build_failure_policies(data.get("failures", {}), master),
            components_library=components,
            seed=master,
            units=UnitsSettings(**unit_values),
            routes=routes,
            supports=supports,
            weights=weights,
            forwarding_groups=forwarding_groups,
            routing=routing,
            wcmp_controller=controller,
        )


def prepare(
    scenario: Scenario,
    *,
    units: UnitsSettings | None = None,
    demand_sets: Sequence[str] = (),
) -> PreparedScenario:
    """Choose one graph/unit over a read-only view of the scenario.

    The input is not changed. The prepared scenario shares its immutable
    records and keeps read-only copies of the network and component dicts,
    so later edits of the caller's collections do not reach it.
    """
    if not isinstance(scenario, Scenario):
        raise TypeError("prepare: expected Scenario")
    if units is not None and not isinstance(units, UnitsSettings):
        raise TypeError("prepare.units: expected UnitsSettings")
    if isinstance(demand_sets, str):
        raise ValueError("prepare.demand_sets: expected a sequence of names")
    requested = tuple(dict.fromkeys(demand_sets))
    for name in requested:
        if not isinstance(name, str) or name not in scenario.demand_sets:
            raise ValueError(f"prepare.demand_sets: unknown demand set {name!r}")
    requested = tuple(str.__str__(name) for name in requested)
    validate_unique_step_names(scenario.workflow)
    snapshot = replace(
        scenario,
        network=scenario.network.snapshot(),
        components_library=scenario.components_library.snapshot(),
    )
    return prepare_scenario(
        snapshot, units if units is not None else snapshot.units, requested
    )


def run(
    prepared: PreparedScenario,
    *,
    step_hook: Callable[[WorkflowStep], AbstractContextManager[None]] | None = None,
) -> RunResult:
    """Execute once in declaration order; publish a run only after every step succeeds."""
    if not isinstance(prepared, PreparedScenario):
        raise TypeError("run: expected PreparedScenario")
    scenario = prepared.scenario
    completed = {}
    results, misses = [], []
    for order, (step, (name, seed, seed_source)) in enumerate(
        zip(scenario.workflow, prepared._steps, strict=True)
    ):
        context = StepContext(prepared, completed, name, order, seed, seed_source)
        with nullcontext() if step_hook is None else step_hook(step):
            result = step.execute(context)
        value = result.result
        if isinstance(
            value,
            (
                CapacityAnalysis,
                PlacementAnalysis,
                SensitivityAnalysis,
                PathAnalysis,
                MSDAnalysis,
                TunnelCountAnalysis,
            ),
        ):
            # An analysis belongs to a preparation of the same graph and report.
            if (
                value.prepared.topology.graph.uid() != prepared.topology.graph.uid()
                or value.prepared.units_report != prepared.units_report
            ):
                raise ValueError(
                    f"step {name}: analysis units/topology do not belong to this preparation"
                )
            misses.extend(
                replace(miss, location=replace(miss.location, step=name))
                for miss in value.misses
            )
        completed[name] = result
        results.append(result)
    return RunResult(
        run_metadata(scenario.seed),
        prepared.units_report.with_misses(tuple(misses)),
        tuple(results),
        prepared,
    )
