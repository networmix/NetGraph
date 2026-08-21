"""Scenario class for defining network analysis workflows from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, ContextManager, List, Optional

from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.logging import get_logger
from ngraph.model.components import ComponentsLibrary
from ngraph.model.demand.builder import build_demand_set
from ngraph.model.demand.matrix import DemandSet
from ngraph.model.failure.generate import generate_risk_groups, parse_generate_spec
from ngraph.model.failure.membership import resolve_membership_rules
from ngraph.model.failure.parser import build_failure_policy_set, build_risk_groups
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.failure.validation import (
    validate_risk_group_hierarchy,
    validate_risk_group_references,
)
from ngraph.model.network import Network
from ngraph.results import Results
from ngraph.results.snapshot import build_scenario_snapshot
from ngraph.utils.seed_manager import SeedManager
from ngraph.workflow.base import WorkflowStep, validate_unique_step_names
from ngraph.workflow.parse import build_workflow_steps


@dataclass
class Scenario:
    """A complete scenario for building and executing network workflows.

    Holds:
      - A network (nodes/links), constructed via blueprint expansion.
      - A failure policy set (one or more named failure policies).
      - A demand set containing one or more named demand collections.
      - A list of workflow steps to execute.
      - A results container for storing outputs.
      - A components_library for hardware/optics definitions.
      - A seed for reproducible random operations (optional).

    Typical usage example:

        scenario = Scenario.from_yaml(yaml_str, default_components=default_lib)
        scenario.run()
        # Inspect scenario.results
    """

    network: Network
    workflow: List[WorkflowStep]
    failure_policy_set: FailurePolicySet = field(default_factory=FailurePolicySet)
    demand_set: DemandSet = field(default_factory=DemandSet)
    results: Results = field(default_factory=Results)
    components_library: ComponentsLibrary = field(default_factory=ComponentsLibrary)
    seed: Optional[int] = None
    # Per-instance execution counter for thread-safe step ordering
    _execution_counter: int = field(default=0, init=False, repr=False)

    # Module-level logger
    _logger = get_logger(__name__)

    def run(
        self,
        step_hook: Optional[Callable[[WorkflowStep], ContextManager[None]]] = None,
    ) -> None:
        """Execute the scenario's workflow steps in order.

        A step may modify scenario data or store outputs in scenario.results.

        Args:
            step_hook: Optional callable invoked once per step with the step
                about to run. It must return a context manager, which is
                entered before ``step.execute`` and exited after it returns
                (e.g., for per-step profiling). Exceptions raised by a step
                propagate through the context manager.
        """
        # Reject duplicate effective step names before executing anything.
        validate_unique_step_names(self.workflow)
        # Reset instance execution counter for this run
        self._execution_counter = 0
        for step in self.workflow:
            if step_hook is None:
                step.execute(self)
            else:
                with step_hook(step):
                    step.execute(self)

    @classmethod
    def from_yaml(
        cls,
        yaml_str: str,
        default_components: Optional[ComponentsLibrary] = None,
    ) -> Scenario:
        """Construct a Scenario from a YAML string, merging in a default
        ComponentsLibrary when one is given.

        Top-level YAML keys can include:
          - vars: YAML anchors for value reuse
          - blueprints: Reusable topology templates
          - components: Hardware component library
          - network: Nodes, links, node_rules, link_rules
          - risk_groups: Failure correlation groups (direct, membership rules, generate blocks)
          - demands: Traffic demand definitions (named sets)
          - failures: Failure simulation policies
          - workflow: Analysis execution steps
          - seed: Master seed for reproducible randomness

        Risk group processing:
        1. Direct risk-group definitions are registered
        2. Membership rules auto-assign entities to groups
        3. The risk-group hierarchy is validated (cycle detection)
        4. Generate blocks create groups from unique attribute values
           (membership rules cannot match generated groups, since generation
           runs after membership resolution)
        5. Members of groups declared disabled are disabled (recursive
           cascade; runs after membership and generate processing so rule-
           and generate-assigned entities are covered)
        6. Risk-group references on nodes/links are validated (undefined
           groups detected)

        If no 'workflow' key is provided, the scenario has no steps to run.
        If 'failures' is omitted, scenario.failure_policy_set is empty.
        If 'components' is provided, it is merged with default_components.
        If 'seed' is provided, it enables reproducible random operations.
        If 'vars' is provided, it can contain YAML anchors and aliases for reuse.
        If any unrecognized top-level key is found, a ValueError is raised.

        Args:
            yaml_str (str): The YAML string that defines the scenario.
            default_components (ComponentsLibrary, optional):
                A default library to merge with scenario-specific components.

        Returns:
            Scenario: An initialized Scenario with expanded network.

        Raises:
            ValueError: If the YAML is malformed or missing required sections,
                or if there are any unrecognized top-level keys.
            TypeError: If a workflow step's arguments are invalid for the step class.
        """
        data = load_scenario_yaml(yaml_str)

        # Extract seed first as it may be used by other components
        seed = data.get("seed")
        if seed is not None and not isinstance(seed, int):
            raise ValueError("'seed' must be an integer if provided.")

        # 1) Build the network using blueprint expansion logic
        network_obj = expand_network_dsl(data)
        if network_obj is None:
            network_obj = Network()
        else:
            Scenario._logger.debug(
                "Expanded network: nodes=%d, links=%d",
                len(network_obj.nodes),
                len(network_obj.links),
            )

        # 2) Build the failure policy set
        seed_manager = SeedManager(seed)
        failure_policy_set = build_failure_policy_set(
            data.get("failures", {}),
            derive_seed=lambda n: seed_manager.derive_seed("failure_policy", n),
        )

        if failure_policy_set.policies:
            policy_names = sorted(failure_policy_set.policies.keys())
            Scenario._logger.debug(
                "Built FailurePolicySet: %d policies (%s)",
                len(policy_names),
                ", ".join(policy_names[:5]) + ("..." if len(policy_names) > 5 else ""),
            )

        # 3) Build demand sets
        raw = data.get("demands", {})
        ds = build_demand_set(raw)
        set_names = sorted(ds.sets.keys())
        Scenario._logger.debug(
            "Constructed DemandSet: sets=%d, total_demands=%d%s",
            len(set_names),
            sum(len(demands) for demands in ds.sets.values()),
            (
                f" ({', '.join(set_names[:5])}{'...' if len(set_names) > 5 else ''})"
                if set_names
                else ""
            ),
        )

        # 4) Build workflow steps
        workflow_data = data.get("workflow", [])
        workflow_steps = build_workflow_steps(
            workflow_data,
            derive_seed=lambda name: seed_manager.derive_seed("workflow_step", name),
        )
        labels = [step.name or step.__class__.__name__ for step in workflow_steps]
        Scenario._logger.debug(
            "Built workflow: steps=%d%s",
            len(workflow_steps),
            (
                f" ({', '.join(labels[:8])}{'...' if len(labels) > 8 else ''})"
                if labels
                else ""
            ),
        )

        # 5) Build/merge components library
        scenario_comps_data = data.get("components", {})
        scenario_comps_lib = (
            ComponentsLibrary.from_dict(scenario_comps_data)
            if scenario_comps_data
            else None
        )
        final_components = (
            default_components.clone() if default_components else ComponentsLibrary()
        )
        if scenario_comps_lib:
            final_components.merge(scenario_comps_lib)

        # 6) Parse optional risk_groups, then attach them to the network
        rg_data = data.get("risk_groups", [])
        generate_specs_raw: list = []
        if rg_data:
            risk_groups, generate_specs_raw = build_risk_groups(rg_data)
            for rg in risk_groups:
                network_obj.risk_groups[rg.name] = rg
            Scenario._logger.debug(
                "Attached risk groups: %d", len(network_obj.risk_groups)
            )

        # 7) Resolve membership rules (adds entities to risk groups based on conditions)
        resolve_membership_rules(network_obj)

        # 8) Validate risk group hierarchy (detect cycles from membership rules)
        validate_risk_group_hierarchy(network_obj)

        # 9) Process generate blocks (creates risk groups from entity attributes)
        for gen_raw in generate_specs_raw:
            try:
                spec = parse_generate_spec(gen_raw)
                generated_rgs = generate_risk_groups(network_obj, spec)
                for rg in generated_rgs:
                    if rg.name in network_obj.risk_groups:
                        raise ValueError(
                            f"Generated risk group '{rg.name}' conflicts with existing "
                            f"risk group. The generate block with group_by='{spec.group_by}' "
                            f"and name='{spec.name}' produced a name that "
                            f"already exists. Either rename the existing group or adjust "
                            f"the name to avoid collisions."
                        )
                    network_obj.risk_groups[rg.name] = rg
            except ValueError as e:
                raise ValueError(f"Invalid generate block: {e}") from e

        if generate_specs_raw:
            Scenario._logger.debug(
                "Generated risk groups: total now %d", len(network_obj.risk_groups)
            )

        # Disable members of risk groups declared disabled. This runs after
        # membership rules and generate blocks so entities assigned to groups
        # by those mechanisms are covered by the cascade.
        for rg in network_obj.risk_groups.values():
            if rg.disabled:
                network_obj.disable_risk_group(rg.name, recursive=True)

        # 10) Validate risk group references
        # Ensures all risk group names referenced by nodes/links are defined
        validate_risk_group_references(network_obj)

        scenario_obj = Scenario(
            network=network_obj,
            failure_policy_set=failure_policy_set,
            workflow=workflow_steps,
            demand_set=ds,
            components_library=final_components,
            seed=seed,
        )

        # Attach minimal scenario snapshot to results for export
        try:
            scenario_obj.results.set_scenario_snapshot(
                build_scenario_snapshot(
                    seed=seed,
                    failure_policy_set=failure_policy_set,
                    demand_set=ds,
                )
            )
        except Exception as exc:
            # Snapshot should never block scenario construction
            Scenario._logger.debug("Failed to attach scenario snapshot: %s", exc)

        Scenario._logger.debug(
            "Scenario constructed: nodes=%d, links=%d, policies=%d, demand_sets=%d, steps=%d",
            len(network_obj.nodes),
            len(network_obj.links),
            len(failure_policy_set.policies),
            len(ds.sets),
            len(workflow_steps),
        )

        return scenario_obj
