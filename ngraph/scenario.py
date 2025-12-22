"""Scenario class for defining network analysis workflows from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.logging import get_logger
from ngraph.model.components import ComponentsLibrary
from ngraph.model.demand.builder import build_traffic_matrix_set
from ngraph.model.demand.matrix import TrafficMatrixSet
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
from ngraph.workflow.base import WorkflowStep
from ngraph.workflow.parse import build_workflow_steps


@dataclass
class Scenario:
    """Represents a complete scenario for building and executing network workflows.

    This scenario includes:
      - A network (nodes/links), constructed via blueprint expansion.
      - A failure policy set (one or more named failure policies).
      - A traffic matrix set containing one or more named traffic matrices.
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
    traffic_matrix_set: TrafficMatrixSet = field(default_factory=TrafficMatrixSet)
    results: Results = field(default_factory=Results)
    components_library: ComponentsLibrary = field(default_factory=ComponentsLibrary)
    seed: Optional[int] = None
    # Per-instance execution counter for thread-safe step ordering
    _execution_counter: int = field(default=0, init=False, repr=False)

    # Module-level logger
    _logger = get_logger(__name__)

    @property
    def seed_manager(self) -> SeedManager:
        """Get the seed manager for this scenario.

        Returns:
            SeedManager instance configured with this scenario's seed.
        """
        return SeedManager(self.seed)

    def run(self) -> None:
        """Executes the scenario's workflow steps in order.

        Each step may modify scenario data or store outputs
        in scenario.results.
        """
        # Reset instance execution counter for this run
        self._execution_counter = 0
        for step in self.workflow:
            step.execute(self)

    @classmethod
    def from_yaml(
        cls,
        yaml_str: str,
        default_components: Optional[ComponentsLibrary] = None,
    ) -> Scenario:
        """Constructs a Scenario from a YAML string, optionally merging
        with a default ComponentsLibrary if provided.

        Top-level YAML keys can include:
          - vars: YAML anchors for value reuse
          - blueprints: Reusable topology templates
          - network: Nodes, links, groups, adjacency
          - risk_groups: Failure correlation groups (direct, membership rules, generate blocks)
          - failure_policy_set: Failure simulation policies
          - traffic_matrix_set: Traffic demand definitions
          - workflow: Analysis execution steps
          - components: Hardware component library
          - seed: Master seed for reproducible randomness

        Risk group processing:
        1. Direct definitions and membership rules are registered
        2. Generate blocks create groups from unique attribute values
        3. Membership rules auto-assign entities to groups
        4. References are validated (undefined groups and circular hierarchies detected)

        If no 'workflow' key is provided, the scenario has no steps to run.
        If 'failure_policy_set' is omitted, scenario.failure_policy_set is empty.
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
            try:
                Scenario._logger.debug(
                    "Expanded network: nodes=%d, links=%d",
                    len(getattr(network_obj, "nodes", {})),
                    len(getattr(network_obj, "links", {})),
                )
            except Exception as exc:
                # Defensive: network object may not be fully initialised in some error paths
                Scenario._logger.debug("Failed to log network stats: %s", exc)

        # 2) Build the failure policy set
        seed_manager = SeedManager(seed)
        failure_policy_set = build_failure_policy_set(
            data.get("failure_policy_set", {}),
            derive_seed=lambda n: seed_manager.derive_seed("failure_policy", n),
        )

        if failure_policy_set.policies:
            try:
                policy_names = sorted(list(failure_policy_set.policies.keys()))
                Scenario._logger.debug(
                    "Built FailurePolicySet: %d policies (%s)",
                    len(policy_names),
                    ", ".join(policy_names[:5])
                    + ("..." if len(policy_names) > 5 else ""),
                )
            except Exception as exc:
                Scenario._logger.debug("Failed to log policy set stats: %s", exc)

        # 3) Build traffic matrix set
        raw = data.get("traffic_matrix_set", {})
        tms = build_traffic_matrix_set(raw)
        try:
            matrix_names = sorted(list(getattr(tms, "matrices", {}).keys()))
            total_demands = 0
            for _mname, demands in getattr(tms, "matrices", {}).items():
                total_demands += len(demands)
            Scenario._logger.debug(
                "Constructed TrafficMatrixSet: matrices=%d, total_demands=%d%s",
                len(matrix_names),
                total_demands,
                (
                    f" ({', '.join(matrix_names[:5])}{'...' if len(matrix_names) > 5 else ''})"
                    if matrix_names
                    else ""
                ),
            )
        except Exception as exc:
            Scenario._logger.debug("Failed to log traffic matrix stats: %s", exc)

        # 4) Build workflow steps
        workflow_data = data.get("workflow", [])
        workflow_steps = build_workflow_steps(
            workflow_data,
            derive_seed=lambda name: seed_manager.derive_seed("workflow_step", name),
        )
        try:
            labels: list[str] = []
            for idx, step in enumerate(workflow_steps):
                label = (step.name or step.__class__.__name__) or f"step_{idx}"
                labels.append(label)
            Scenario._logger.debug(
                "Built workflow: steps=%d%s",
                len(workflow_steps),
                (
                    f" ({', '.join(labels[:8])}{'...' if len(labels) > 8 else ''})"
                    if labels
                    else ""
                ),
            )
        except Exception as exc:
            Scenario._logger.debug("Failed to log workflow stats: %s", exc)

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
                if rg.disabled:
                    network_obj.disable_risk_group(rg.name, recursive=True)
            try:
                Scenario._logger.debug(
                    "Attached risk groups: %d",
                    len(getattr(network_obj, "risk_groups", {})),
                )
            except Exception as exc:
                Scenario._logger.debug("Failed to log risk group stats: %s", exc)

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
                            f"and name_template='{spec.name_template}' produced a name that "
                            f"already exists. Either rename the existing group or adjust "
                            f"the name_template to avoid collisions."
                        )
                    network_obj.risk_groups[rg.name] = rg
            except ValueError as e:
                raise ValueError(f"Invalid generate block: {e}") from e

        try:
            if generate_specs_raw:
                Scenario._logger.debug(
                    "Generated risk groups: total now %d",
                    len(getattr(network_obj, "risk_groups", {})),
                )
        except Exception as exc:
            Scenario._logger.debug("Failed to log generate stats: %s", exc)

        # 10) Validate risk group references
        # Ensures all risk group names referenced by nodes/links are defined
        validate_risk_group_references(network_obj)

        scenario_obj = Scenario(
            network=network_obj,
            failure_policy_set=failure_policy_set,
            workflow=workflow_steps,
            traffic_matrix_set=tms,
            components_library=final_components,
            seed=seed,
        )

        # Attach minimal scenario snapshot to results for export
        try:
            scenario_obj.results.set_scenario_snapshot(
                build_scenario_snapshot(
                    seed=seed,
                    failure_policy_set=failure_policy_set,
                    traffic_matrix_set=tms,
                )
            )
        except Exception as exc:
            # Snapshot should never block scenario construction
            Scenario._logger.debug("Failed to attach scenario snapshot: %s", exc)

        try:
            Scenario._logger.debug(
                "Scenario constructed: nodes=%d, links=%d, policies=%d, matrices=%d, steps=%d",
                len(getattr(network_obj, "nodes", {})),
                len(getattr(network_obj, "links", {})),
                len(getattr(failure_policy_set, "policies", {})),
                len(getattr(tms, "matrices", {})),
                len(workflow_steps),
            )
        except Exception as exc:
            Scenario._logger.debug("Failed to log scenario construction stats: %s", exc)

        return scenario_obj
