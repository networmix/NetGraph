"""Parsers for FailurePolicySet and related failure modeling structures."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ngraph.logging import get_logger
from ngraph.model.failure.policy import (
    FailureMode,
    FailurePolicy,
    FailureRule,
)
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import RiskGroup
from ngraph.model.selectors import parse_match_spec
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys

_logger = get_logger(__name__)


def build_risk_groups(
    rg_data: List[Any],
) -> tuple[List[RiskGroup], List[Dict[str, Any]]]:
    """Build RiskGroup objects from raw config data.

    Supports:
    - String shorthand: "GroupName" is equivalent to {name: "GroupName"}
    - Bracket expansion: {name: "DC[1-3]_Power"} creates DC1_Power, DC2_Power, DC3_Power
    - Children are also expanded recursively
    - Generate blocks: {generate: {...}} for dynamic group creation

    'membership', 'disabled', and 'generate' are only honored on top-level
    entries: only top-level groups are registered in network.risk_groups, so
    these keys would be silently inert on nested children. Child entries
    carrying them are rejected with ValueError.

    Args:
        rg_data: List of risk group definitions (strings or dicts).

    Returns:
        Tuple of (explicit_risk_groups, generate_specs_raw):
        - explicit_risk_groups: List of RiskGroup objects with names expanded.
        - generate_specs_raw: List of raw generate block dicts for deferred processing.
    """
    from ngraph.dsl.expansion import expand_name_patterns

    def normalize_entry(entry: Any) -> Dict[str, Any]:
        """Normalize entry to dict format, handling string shorthand."""
        if isinstance(entry, str):
            return {"name": entry}
        if isinstance(entry, dict):
            return entry
        raise ValueError(
            f"RiskGroup entry must be a string or dict, got {type(entry).__name__}"
        )

    def build_one(d: Dict[str, Any]) -> RiskGroup:
        """Build a single RiskGroup (name already expanded)."""
        name = d.get("name")
        if not name:
            raise ValueError("RiskGroup entry missing 'name' field.")
        disabled = d.get("disabled", False)
        # Recursively expand and build children
        children_list = d.get("children", [])
        child_objs = expand_and_build(children_list, in_children=True)
        attrs = normalize_yaml_dict_keys(d.get("attrs", {}))
        # Extract membership rule for deferred resolution
        membership_raw = d.get("membership")
        return RiskGroup(
            name=name,
            disabled=disabled,
            children=child_objs,
            attrs=attrs,
            _membership_raw=membership_raw,
        )

    def expand_and_build(
        entries: List[Any], *, in_children: bool = False
    ) -> List[RiskGroup]:
        """Expand names and build RiskGroups for a list of entries."""
        result: List[RiskGroup] = []
        for entry in entries:
            normalized = normalize_entry(entry)
            # Reject generate blocks in children (not supported)
            if "generate" in normalized:
                raise ValueError("'generate' blocks not allowed in children")
            if in_children:
                # Only top-level groups are registered in network.risk_groups,
                # so membership rules and disabled flags on nested children
                # would be silently ignored. Reject them instead.
                if "membership" in normalized:
                    raise ValueError(
                        "'membership' rules not allowed in children; define "
                        "the group at top level and reference it as a child"
                    )
                if "disabled" in normalized:
                    raise ValueError(
                        "'disabled' not allowed in children; define the group "
                        "at top level and reference it as a child"
                    )
            name = normalized.get("name", "")
            if not name:
                raise ValueError("RiskGroup entry missing 'name' field.")
            expanded_names = expand_name_patterns(name)
            for exp_name in expanded_names:
                modified = dict(normalized)
                modified["name"] = exp_name
                result.append(build_one(modified))
        return result

    # Separate generate blocks from explicit risk groups
    explicit_entries: List[Any] = []
    generate_specs: List[Dict[str, Any]] = []

    for entry in rg_data:
        if isinstance(entry, dict) and "generate" in entry:
            generate_specs.append(entry["generate"])
        else:
            explicit_entries.append(entry)

    return expand_and_build(explicit_entries), generate_specs


def build_failure_policy(
    fp_data: Dict[str, Any],
    *,
    policy_name: str,
    derive_seed: Callable[[str], Optional[int]],
) -> FailurePolicy:
    """Build a FailurePolicy from a raw configuration dictionary.

    Args:
        fp_data: Policy definition dict with keys: modes (required), attrs,
            expand_groups. Each mode contains weight and rules.
        policy_name: Name identifier for this policy (used for seed derivation).
        derive_seed: Callable to derive deterministic seeds from component names.

    Returns:
        FailurePolicy: Configured policy with parsed modes and rules.

    Raises:
        ValueError: If modes is empty or malformed, if rules are invalid, or
            if no mode has positive weight.
    """

    def build_rules(rule_dicts: List[Dict[str, Any]]) -> List[FailureRule]:
        out: List[FailureRule] = []
        for rule_dict in rule_dicts:
            scope = rule_dict.get("scope")
            if not scope:
                raise ValueError(
                    "failure rule requires 'scope' field (node, link, or risk_group)"
                )

            # Parse the match block with the unified parser
            match_spec = parse_match_spec(
                rule_dict.get("match", {}), context="failure rule"
            )
            out.append(
                FailureRule(
                    scope=scope,
                    conditions=match_spec.conditions,
                    logic=match_spec.logic,
                    mode=rule_dict.get("mode", "all"),
                    probability=rule_dict.get("probability", 1.0),
                    count=rule_dict.get("count", 1),
                    weight_by=rule_dict.get("weight_by"),
                    path=rule_dict.get("path"),
                )
            )
        return out

    expand_groups = fp_data.get("expand_groups", False)
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

    if not any(mode.weight > 0.0 for mode in modes):
        raise ValueError(
            f"failure policy '{policy_name}' has no mode with positive weight; "
            "at least one mode must have weight > 0"
        )

    policy_seed = derive_seed(policy_name)

    return FailurePolicy(
        attrs=attrs,
        expand_groups=expand_groups,
        seed=policy_seed,
        modes=modes,
    )


def build_failure_policy_set(
    raw: Dict[str, Any],
    *,
    derive_seed: Callable[[str], Optional[int]],
) -> FailurePolicySet:
    """Build a FailurePolicySet from raw config data.

    Args:
        raw: Mapping of policy name -> policy definition dict.
        derive_seed: Callable to derive deterministic seeds from component names.

    Returns:
        Configured FailurePolicySet.

    Raises:
        ValueError: If raw is not a dict or contains invalid policy definitions.
    """
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
            derive_seed=lambda n, _fn=derive_seed: _fn(f"failure_policy:{n}"),
        )
        fps.add(name, policy)
    return fps
