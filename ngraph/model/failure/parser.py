"""Parsers for FailurePolicySet and related failure modeling structures."""

from __future__ import annotations

from typing import Any, Dict, List

from ngraph.logging import get_logger
from ngraph.model.failure.policy import FailureCondition, FailureMode, FailurePolicy
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import RiskGroup
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys

_logger = get_logger(__name__)


def build_risk_groups(rg_data: List[Dict[str, Any]]) -> List[RiskGroup]:
    def build_one(d: Dict[str, Any]) -> RiskGroup:
        name = d.get("name")
        if not name:
            raise ValueError("RiskGroup entry missing 'name' field.")
        disabled = d.get("disabled", False)
        children_list = d.get("children", [])
        child_objs = [build_one(cd) for cd in children_list]
        attrs = normalize_yaml_dict_keys(d.get("attrs", {}))
        return RiskGroup(name=name, disabled=disabled, children=child_objs, attrs=attrs)

    return [build_one(entry) for entry in rg_data]


def build_failure_policy(
    fp_data: Dict[str, Any], *, policy_name: str, derive_seed
) -> FailurePolicy:
    def build_rules(rule_dicts: List[Dict[str, Any]]):
        out: List[Any] = []
        for rule_dict in rule_dicts:
            entity_scope = rule_dict.get("entity_scope", "node")
            conditions_data = rule_dict.get("conditions", [])
            if not isinstance(conditions_data, list):
                raise ValueError("Each rule's 'conditions' must be a list if present.")
            conditions: List[FailureCondition] = []
            for cond_dict in conditions_data:
                conditions.append(
                    FailureCondition(
                        attr=cond_dict["attr"],
                        operator=cond_dict["operator"],
                        value=cond_dict["value"],
                    )
                )
            out.append(
                type(
                    "_Rule",
                    (),
                    {
                        "entity_scope": entity_scope,
                        "conditions": conditions,
                        "logic": rule_dict.get("logic", "or"),
                        "rule_type": rule_dict.get("rule_type", "all"),
                        "probability": rule_dict.get("probability", 1.0),
                        "count": rule_dict.get("count", 1),
                        "weight_by": rule_dict.get("weight_by"),
                    },
                )
            )
        return out

    fail_srg = fp_data.get("fail_risk_groups", False)
    fail_rg_children = fp_data.get("fail_risk_group_children", False)
    attrs = normalize_yaml_dict_keys(fp_data.get("attrs", {}))

    modes: List[FailureMode] = []
    modes_data = fp_data.get("modes", [])
    if not isinstance(modes_data, list) or not modes_data:
        raise ValueError("failure_policy requires non-empty 'modes' list.")
    for m in modes_data:
        if not isinstance(m, dict):
            raise ValueError("Each mode must be a mapping.")
        weight = float(m.get("weight", 0.0))
        mode_rules_data = m.get("rules", [])
        if not isinstance(mode_rules_data, list):
            raise ValueError("Each mode 'rules' must be a list.")
        mode_rules = build_rules(mode_rules_data)
        mode_attrs = normalize_yaml_dict_keys(m.get("attrs", {}))
        modes.append(FailureMode(weight=weight, rules=mode_rules, attrs=mode_attrs))

    policy_seed = derive_seed(policy_name)

    return FailurePolicy(
        attrs=attrs,
        fail_risk_groups=fail_srg,
        fail_risk_group_children=fail_rg_children,
        seed=policy_seed,
        modes=modes,
    )


def build_failure_policy_set(raw: Dict[str, Any], *, derive_seed) -> FailurePolicySet:
    if not isinstance(raw, dict):
        raise ValueError(
            "'failure_policy_set' must be a mapping of name -> FailurePolicy definition"
        )

    normalized_fps = normalize_yaml_dict_keys(raw)
    fps = FailurePolicySet()
    for name, fp_data in normalized_fps.items():
        if not isinstance(fp_data, dict):
            raise ValueError(
                f"Failure policy '{name}' must map to a FailurePolicy definition dict"
            )
        policy = build_failure_policy(
            fp_data,
            policy_name=name,
            derive_seed=lambda n: derive_seed(f"failure_policy:{n}"),
        )
        fps.add(name, policy)
    return fps
