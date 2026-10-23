"""Failure declarations and one YAML construction path."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ngraph.model.selectors import Condition, EntityScope, parse_match_spec
from ngraph.utils.seed_manager import SeedManager
from ngraph.utils.values import frozen_attrs, integer, own_scalars, physical
from ngraph.utils.yaml_utils import check_no_extra_keys, normalize_yaml_dict_keys


@dataclass(frozen=True)
class FailureRule:
    scope: EntityScope
    conditions: Sequence[Condition] = ()
    logic: Literal["and", "or"] = "or"
    mode: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1
    weight_by: str | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        own_scalars(
            self, "failure rule", ("scope", "logic", "mode", "weight_by", "path")
        )
        if self.scope not in ("node", "link", "risk_group"):
            raise ValueError(f"failure rule: invalid scope {self.scope!r}")
        if self.logic not in ("and", "or"):
            raise ValueError("failure rule logic: expected and or or")
        if self.mode not in ("all", "random", "choice"):
            raise ValueError("failure rule mode: expected all, random or choice")
        probability = physical(self.probability, "failure rule probability")
        if probability > 1:
            raise ValueError("failure rule probability: expected [0,1]")
        object.__setattr__(self, "probability", probability)
        integer(self.count, "failure rule count", minimum=0)
        object.__setattr__(self, "count", int.__int__(self.count))
        for name in ("weight_by", "path"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"failure rule {name}: expected string or None")
        object.__setattr__(self, "conditions", tuple(self.conditions))
        if not all(isinstance(condition, Condition) for condition in self.conditions):
            raise TypeError("failure rule conditions: expected Condition values")


@dataclass(frozen=True)
class FailureMode:
    weight: float
    rules: Sequence[FailureRule] = ()
    attrs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "weight", physical(self.weight, "failure mode weight"))
        object.__setattr__(self, "rules", tuple(self.rules))
        if not all(isinstance(rule, FailureRule) for rule in self.rules):
            raise TypeError("failure mode rules: expected FailureRule values")
        object.__setattr__(
            self, "attrs", frozen_attrs(self.attrs, "failure mode attrs")
        )


@dataclass(frozen=True)
class FailurePolicy:
    attrs: dict[str, Any] = field(default_factory=dict)
    expand_groups: bool = False
    seed: int | None = None
    modes: Sequence[FailureMode] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.expand_groups, bool):
            raise ValueError("failure policy expand_groups: expected bool")
        if self.seed is not None and (
            isinstance(self.seed, bool) or not isinstance(self.seed, int)
        ):
            raise ValueError("failure policy seed: expected integer or None")
        own_scalars(self, "failure policy", ("seed",))
        object.__setattr__(self, "modes", tuple(self.modes))
        if not all(isinstance(mode, FailureMode) for mode in self.modes):
            raise TypeError("failure policy modes: expected FailureMode values")
        object.__setattr__(
            self, "attrs", frozen_attrs(self.attrs, "failure policy attrs")
        )


def build_failure_policies(
    raw: dict[str, Any], master_seed: int | None
) -> dict[str, FailurePolicy]:
    """Construct named policies; seeded YAML keeps the established composed hash.

    Policy name ``n`` uses SHA256("<master>:failure_policy:failure_policy:<n>"),
    first four bytes big-endian masked to31 bits. Step seeds use their own
    workflow_step component and never pass through this policy derivation.
    """
    if not isinstance(raw, dict):
        raise ValueError("failures: expected mapping of names to policies")
    policies = {}
    manager = SeedManager(master_seed)
    for name, value in normalize_yaml_dict_keys(raw).items():
        if not isinstance(name, str) or not name or not isinstance(value, dict):
            raise ValueError("failures: expected nonempty names and policy mappings")
        check_no_extra_keys(
            value, {"modes", "attrs", "expand_groups"}, f"failure policy {name}"
        )
        modes = []
        raw_modes = value.get("modes")
        if not isinstance(raw_modes, list) or not raw_modes:
            raise ValueError(f"failure policy {name}: modes must be a nonempty list")
        for mode_index, raw_mode in enumerate(raw_modes):
            if not isinstance(raw_mode, dict):
                raise ValueError(
                    f"failure policy {name} mode {mode_index}: expected mapping"
                )
            check_no_extra_keys(
                raw_mode,
                {"weight", "rules", "attrs"},
                f"failure policy {name} mode {mode_index}",
            )
            raw_rules = raw_mode.get("rules", [])
            if not isinstance(raw_rules, list):
                raise ValueError(
                    f"failure policy {name} mode {mode_index}: rules must be a list"
                )
            rules = []
            for rule_index, raw_rule in enumerate(raw_rules):
                if not isinstance(raw_rule, dict):
                    raise ValueError(
                        f"failure policy {name} rule {rule_index}: expected mapping"
                    )
                check_no_extra_keys(
                    raw_rule,
                    {
                        "scope",
                        "match",
                        "mode",
                        "probability",
                        "count",
                        "weight_by",
                        "path",
                    },
                    f"failure policy {name} rule {rule_index}",
                )
                match = parse_match_spec(
                    raw_rule.get("match", {}),
                    context=f"failure policy {name} rule {rule_index}",
                )
                rules.append(
                    FailureRule(
                        scope=cast(EntityScope, raw_rule.get("scope")),
                        conditions=match.conditions,
                        logic=match.logic,
                        mode=raw_rule.get("mode", "all"),
                        probability=raw_rule.get("probability", 1.0),
                        count=raw_rule.get("count", 1),
                        weight_by=raw_rule.get("weight_by"),
                        path=raw_rule.get("path"),
                    )
                )
            modes.append(
                FailureMode(
                    raw_mode.get("weight", 0),
                    rules,
                    normalize_yaml_dict_keys(raw_mode.get("attrs", {})),
                )
            )
        if not any(mode.weight > 0 for mode in modes):
            raise ValueError(
                f"failure policy {name}: at least one mode must have positive weight"
            )
        policies[name] = FailurePolicy(
            attrs=normalize_yaml_dict_keys(value.get("attrs", {})),
            expand_groups=value.get("expand_groups", False),
            seed=manager.derive_seed("failure_policy", "failure_policy", name),
            modes=modes,
        )
    return policies
