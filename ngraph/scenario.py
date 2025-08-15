"""Scenario class for defining network analysis workflows from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from ngraph.components import ComponentsLibrary
from ngraph.demand.manager.builder import build_traffic_matrix_set
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.failure.policy import (
    FailureCondition,
    FailureMode,
    FailurePolicy,
    FailureRule,
)
from ngraph.failure.policy_set import FailurePolicySet
from ngraph.logging import get_logger
from ngraph.model.network import Network, RiskGroup
from ngraph.results import Results
from ngraph.seed_manager import SeedManager
from ngraph.workflow.base import WORKFLOW_STEP_REGISTRY, WorkflowStep
from ngraph.yaml_utils import normalize_yaml_dict_keys


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
          - vars
          - blueprints
          - network
          - failure_policy_set
          - traffic_matrix_set
          - workflow
          - components
          - risk_groups
          - seed

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
        data = yaml.safe_load(yaml_str)
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ValueError("The provided YAML must map to a dictionary at top-level.")

        # Ensure only recognized top-level keys are present.
        recognized_keys = {
            "vars",
            "blueprints",
            "network",
            "failure_policy_set",
            "traffic_matrix_set",
            "workflow",
            "components",
            "risk_groups",
            "seed",
        }
        extra_keys = set(data.keys()) - recognized_keys
        if extra_keys:
            raise ValueError(
                f"Unrecognized top-level key(s) in scenario: {', '.join(sorted(extra_keys))}. "
                f"Allowed keys are {sorted(recognized_keys)}"
            )

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
            except Exception:
                # Defensive: network object may not be fully initialised in some error paths
                pass

        # 2) Build the failure policy set
        fps_data = data.get("failure_policy_set", {})
        if not isinstance(fps_data, dict):
            raise ValueError(
                "'failure_policy_set' must be a mapping of name -> FailurePolicy definition"
            )

        # Normalize dictionary keys to handle YAML boolean keys
        normalized_fps = normalize_yaml_dict_keys(fps_data)
        failure_policy_set = FailurePolicySet()
        seed_manager = SeedManager(seed)
        for name, fp_data in normalized_fps.items():
            if not isinstance(fp_data, dict):
                raise ValueError(
                    f"Failure policy '{name}' must map to a FailurePolicy definition dict"
                )
            failure_policy = cls._build_failure_policy(fp_data, seed_manager, name)
            failure_policy_set.add(name, failure_policy)

        if failure_policy_set.policies:
            try:
                policy_names = sorted(list(failure_policy_set.policies.keys()))
                Scenario._logger.debug(
                    "Built FailurePolicySet: %d policies (%s)",
                    len(policy_names),
                    ", ".join(policy_names[:5])
                    + ("..." if len(policy_names) > 5 else ""),
                )
            except Exception:
                pass

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
        except Exception:
            pass

        # 4) Build workflow steps
        workflow_data = data.get("workflow", [])
        workflow_steps = cls._build_workflow_steps(workflow_data, seed_manager)
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
        except Exception:
            pass

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
        if rg_data:
            risk_groups = cls._build_risk_groups(rg_data)
            for rg in risk_groups:
                network_obj.risk_groups[rg.name] = rg
                if rg.disabled:
                    network_obj.disable_risk_group(rg.name, recursive=True)
            try:
                Scenario._logger.debug(
                    "Attached risk groups: %d",
                    len(getattr(network_obj, "risk_groups", {})),
                )
            except Exception:
                pass

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
            snapshot_failure_policies: Dict[str, Any] = {}
            for name, policy in failure_policy_set.policies.items():
                modes_list: list[dict[str, Any]] = []
                for mode in getattr(policy, "modes", []) or []:
                    mode_dict = {
                        "weight": float(getattr(mode, "weight", 0.0)),
                        "rules": [],
                        "attrs": dict(getattr(mode, "attrs", {}) or {}),
                    }
                    for rule in getattr(mode, "rules", []) or []:
                        rule_dict = {
                            "entity_scope": getattr(rule, "entity_scope", "node"),
                            "logic": getattr(rule, "logic", "or"),
                            "rule_type": getattr(rule, "rule_type", "all"),
                            "probability": float(getattr(rule, "probability", 1.0)),
                            "count": int(getattr(rule, "count", 1)),
                            "conditions": [
                                {
                                    "attr": c.attr,
                                    "operator": c.operator,
                                    "value": c.value,
                                }
                                for c in getattr(rule, "conditions", []) or []
                            ],
                        }
                        mode_dict["rules"].append(rule_dict)
                    modes_list.append(mode_dict)
                snapshot_failure_policies[name] = {
                    "attrs": dict(getattr(policy, "attrs", {}) or {}),
                    "modes": modes_list,
                }

            snapshot_tms: Dict[str, list[dict[str, Any]]] = {}
            for mname, demands in tms.matrices.items():
                entries: list[dict[str, Any]] = []
                for d in demands:
                    entries.append(
                        {
                            "source_path": getattr(d, "source_path", ""),
                            "sink_path": getattr(d, "sink_path", ""),
                            "demand": float(getattr(d, "demand", 0.0)),
                            "priority": int(getattr(d, "priority", 0)),
                            "mode": getattr(d, "mode", "pairwise"),
                            "flow_policy_config": getattr(
                                d, "flow_policy_config", None
                            ),
                            "attrs": dict(getattr(d, "attrs", {}) or {}),
                        }
                    )
                snapshot_tms[mname] = entries

            scenario_obj.results.set_scenario_snapshot(
                {
                    "seed": seed,
                    "failure_policy_set": snapshot_failure_policies,
                    "traffic_matrices": snapshot_tms,
                }
            )
        except Exception:
            # Snapshot should never block scenario construction
            pass

        try:
            Scenario._logger.debug(
                "Scenario constructed: nodes=%d, links=%d, policies=%d, matrices=%d, steps=%d",
                len(getattr(network_obj, "nodes", {})),
                len(getattr(network_obj, "links", {})),
                len(getattr(failure_policy_set, "policies", {})),
                len(getattr(tms, "matrices", {})),
                len(workflow_steps),
            )
        except Exception:
            pass

        return scenario_obj

    @staticmethod
    def _build_risk_groups(rg_data: List[Dict[str, Any]]) -> List[RiskGroup]:
        """Recursively builds a list of RiskGroup objects from YAML data.

        Each entry may have keys: "name", "children", "disabled", and "attrs" (dict).

        Args:
            rg_data (List[Dict[str, Any]]): The list of risk-group definitions.

        Returns:
            List[RiskGroup]: Possibly nested risk groups.

        Raises:
            ValueError: If any group is missing 'name'.
        """

        def build_one(d: Dict[str, Any]) -> RiskGroup:
            name = d.get("name")
            if not name:
                raise ValueError("RiskGroup entry missing 'name' field.")
            disabled = d.get("disabled", False)
            children_list = d.get("children", [])
            child_objs = [build_one(cd) for cd in children_list]
            attrs = normalize_yaml_dict_keys(d.get("attrs", {}))
            return RiskGroup(
                name=name, disabled=disabled, children=child_objs, attrs=attrs
            )

        return [build_one(entry) for entry in rg_data]

    @staticmethod
    def _build_failure_policy(
        fp_data: Dict[str, Any], seed_manager: SeedManager, policy_name: str
    ) -> FailurePolicy:
        """Constructs a FailurePolicy from data that may specify multiple rules plus
        optional top-level fields like fail_risk_groups, fail_risk_group_children,
        and attrs.

        Example:
            failure_policy_set:
              default:
                fail_risk_groups: true
                fail_risk_group_children: false
                attrs:
                  custom_key: custom_val
                rules:
                  - entity_scope: "node"
                    conditions:
                      - attr: "capacity"
                        operator: ">"
                        value: 100
                  logic: "and"
                  rule_type: "choice"
                  count: 2

        Args:
            fp_data (Dict[str, Any]): Dictionary from the 'failure_policy' section of the YAML.
            seed_manager (SeedManager): Seed manager for reproducible operations.
            policy_name (str): Name of the policy for seed derivation.

        Returns:
            FailurePolicy: The constructed policy. If no rules exist, it's an empty policy.

        Raises:
            ValueError: If 'rules' is present but not a list, or if conditions are not lists.
        """
        fail_srg = fp_data.get("fail_risk_groups", False)
        fail_rg_children = fp_data.get("fail_risk_group_children", False)
        attrs = normalize_yaml_dict_keys(fp_data.get("attrs", {}))

        def build_rules(rule_dicts: List[Dict[str, Any]]) -> List[FailureRule]:
            rules_local: List[FailureRule] = []
            for rule_dict in rule_dicts:
                entity_scope = rule_dict.get("entity_scope", "node")
                conditions_data = rule_dict.get("conditions", [])
                if not isinstance(conditions_data, list):
                    raise ValueError(
                        "Each rule's 'conditions' must be a list if present."
                    )
                conditions: List[FailureCondition] = []
                for cond_dict in conditions_data:
                    conditions.append(
                        FailureCondition(
                            attr=cond_dict["attr"],
                            operator=cond_dict["operator"],
                            value=cond_dict["value"],
                        )
                    )

                rule = FailureRule(
                    entity_scope=entity_scope,
                    conditions=conditions,
                    logic=rule_dict.get("logic", "or"),
                    rule_type=rule_dict.get("rule_type", "all"),
                    probability=rule_dict.get("probability", 1.0),
                    count=rule_dict.get("count", 1),
                    weight_by=rule_dict.get("weight_by"),
                )
                rules_local.append(rule)
            return rules_local

        # Extract weighted modes (required)
        modes: List[FailureMode] = []
        modes_data = fp_data.get("modes", [])
        if not isinstance(modes_data, list) or not modes_data:
            raise ValueError("failure_policy requires non-empty 'modes' list.")
        for _m_idx, m in enumerate(modes_data):
            if not isinstance(m, dict):
                raise ValueError("Each mode must be a mapping.")
            try:
                weight = float(m.get("weight", 0.0))
            except (TypeError, ValueError) as exc:
                raise ValueError("Each mode 'weight' must be a number.") from exc
            mode_rules_data = m.get("rules", [])
            if not isinstance(mode_rules_data, list):
                raise ValueError("Each mode 'rules' must be a list.")
            mode_rules = build_rules(mode_rules_data)
            mode_attrs = normalize_yaml_dict_keys(m.get("attrs", {}))
            modes.append(FailureMode(weight=weight, rules=mode_rules, attrs=mode_attrs))

        # Derive seed for this failure policy
        policy_seed = seed_manager.derive_seed("failure_policy", policy_name)

        return FailurePolicy(
            attrs=attrs,
            fail_risk_groups=fail_srg,
            fail_risk_group_children=fail_rg_children,
            seed=policy_seed,
            modes=modes,
        )

    @staticmethod
    def _build_workflow_steps(
        workflow_data: List[Dict[str, Any]],
        seed_manager: SeedManager,
    ) -> List[WorkflowStep]:
        """Converts workflow step dictionaries into WorkflowStep objects.

        Each step dict must have a "step_type" referencing a registered workflow
        step in WORKFLOW_STEP_REGISTRY. All other keys in the dict are passed
        to that step's constructor as keyword arguments.

        Args:
            workflow_data (List[Dict[str, Any]]): A list of dictionaries describing
                each workflow step, for example:
                [
                  {
                    "step_type": "MyStep",
                    "arg1": "value1",
                    "arg2": "value2",
                  },
                  ...
                ]
            seed_manager (SeedManager): Seed manager for reproducible operations.

        Returns:
            List[WorkflowStep]: A list of instantiated WorkflowStep objects.

        Raises:
            ValueError: If any step lacks "step_type" or references an unknown type.
            TypeError: If step initialization fails due to invalid arguments.
        """
        if not isinstance(workflow_data, list):
            raise ValueError("'workflow' must be a list if present.")

        steps: List[WorkflowStep] = []
        # Track assigned names to enforce uniqueness and avoid result/metadata collisions
        assigned_names: set[str] = set()
        for step_index, step_info in enumerate(workflow_data):
            step_type = step_info.get("step_type")
            if not step_type:
                raise ValueError(
                    "Each workflow entry must have a 'step_type' field "
                    "indicating the WorkflowStep subclass to use."
                )

            step_cls = WORKFLOW_STEP_REGISTRY.get(step_type)
            if not step_cls:
                raise ValueError(f"Unrecognized 'step_type': {step_type}")

            ctor_args = {k: v for k, v in step_info.items() if k != "step_type"}
            # Normalize constructor argument keys to handle YAML boolean keys
            normalized_ctor_args = normalize_yaml_dict_keys(ctor_args)

            # Resolve a concrete step name to prevent collisions in results/metadata
            raw_name = normalized_ctor_args.get("name")
            # Treat blank/whitespace names as missing
            if isinstance(raw_name, str) and raw_name.strip() == "":
                raw_name = None
            step_name = raw_name or f"{step_type}_{step_index}"

            # Enforce uniqueness across the workflow
            if step_name in assigned_names:
                raise ValueError(
                    f"Duplicate workflow step name '{step_name}'. "
                    "Each step must have a unique name."
                )
            assigned_names.add(step_name)

            # Ensure the constructed WorkflowStep receives the resolved unique name
            normalized_ctor_args["name"] = step_name

            # Determine seed provenance and possibly derive a step seed
            seed_source: str = "none"
            if (
                "seed" in normalized_ctor_args
                and normalized_ctor_args["seed"] is not None
            ):
                seed_source = "explicit-step"
            else:
                derived_seed = seed_manager.derive_seed("workflow_step", step_name)
                if derived_seed is not None:
                    normalized_ctor_args["seed"] = derived_seed
                    seed_source = "scenario-derived"

            step_obj = step_cls(**normalized_ctor_args)
            # Attach internal provenance for metadata collection
            try:
                step_obj._seed_source = seed_source
            except Exception:
                pass
            steps.append(step_obj)

        return steps
