"""Failure policy primitives.

Defines `FailureCondition`, `FailureRule`, and `FailurePolicy` for expressing
how nodes, links, and risk groups fail in analyses. Conditions match on
top-level attributes with simple operators; rules select matches using
"all", probabilistic "random" (with `probability`), or fixed-size "choice"
(with `count`). Policies can optionally expand failures by shared risk groups
or by risk-group children.
"""

from __future__ import annotations

import random as _random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

from .conditions import FailureCondition as EvalCondition
from .conditions import evaluate_condition as _shared_evaluate_condition
from .conditions import evaluate_conditions as _shared_evaluate_conditions


@dataclass
class FailureCondition(EvalCondition):
    """Alias to the shared condition dataclass.

    This maintains a consistent import path within the failure policy module.
    """


# Supported entity scopes for a rule
EntityScope = Literal["node", "link", "risk_group"]


@dataclass
class FailureRule:
    """Defines how to match and then select entities for failure.

    Attributes:
        entity_scope (EntityScope):
            The type of entities this rule applies to: "node", "link", or "risk_group".
        conditions (List[FailureCondition]):
            A list of conditions to filter matching entities.
        logic (Literal["and", "or"]):
            "and": All conditions must be true for a match.
            "or": At least one condition is true for a match (default).
        rule_type (Literal["random", "choice", "all"]):
            The selection strategy among the matched set:
              - "random": each matched entity is chosen with probability = `probability`.
              - "choice": pick exactly `count` items from the matched set (random sample).
              - "all": select every matched entity in the matched set.
        probability (float):
            Probability in [0,1], used if `rule_type="random"`.
        count (int):
            Number of entities to pick if `rule_type="choice"`.
    """

    entity_scope: EntityScope
    conditions: List[FailureCondition] = field(default_factory=list)
    logic: Literal["and", "or"] = "or"
    rule_type: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1
    # Optional attribute for weighted sampling in choice mode
    # When set and rule_type=="choice", items are sampled without replacement
    # with probability proportional to the non-negative numeric value of this attribute.
    # If all weights are non-positive or missing, fallback to uniform sampling.
    weight_by: Optional[str] = None

    def __post_init__(self) -> None:
        if self.rule_type == "random":
            if not (0.0 <= self.probability <= 1.0):
                raise ValueError(
                    f"probability={self.probability} must be within [0,1] "
                    f"for rule_type='random'."
                )


@dataclass
class FailureMode:
    """A weighted mode that encapsulates a set of rules applied together.

    Exactly one mode is selected per failure iteration according to the
    mode weights. Within a mode, all contained rules are applied and their
    selections are unioned into the failure set.

    Attributes:
        weight: Non-negative weight used for mode selection. All weights are
            normalized internally. Modes with zero weight are never selected.
        rules: A list of `FailureRule` applied together when this mode is chosen.
        attrs: Optional metadata.
    """

    weight: float
    rules: List[FailureRule] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FailurePolicy:
    """A container for multiple FailureRules plus optional metadata in `attrs`.

    The main entry point is `apply_failures`, which:
      1) For each rule, gather the relevant entities (node, link, or risk_group).
              2) Match them based on rule conditions using 'and' or 'or' logic.
      3) Apply the selection strategy (all, random, or choice).
      4) Collect the union of all failed entities across all rules.
      5) Optionally expand failures by shared-risk groups or sub-risks.

    Example YAML configuration:
        ```yaml
        failure_policy:
          attrs:
            description: "Regional power grid failure affecting telecom infrastructure"
          fail_risk_groups: true
          rules:
            # Fail all nodes in Texas electrical grid
            - entity_scope: "node"
              conditions:
                - attr: "electric_grid"
                  operator: "=="
                  value: "texas"
              logic: "and"
              rule_type: "all"

            # Randomly fail 40% of underground fiber links in affected region
            - entity_scope: "link"
              conditions:
                - attr: "region"
                  operator: "=="
                  value: "southwest"
                - attr: "installation"
                  operator: "=="
                  value: "underground"
              logic: "and"
              rule_type: "random"
              probability: 0.4

            # Choose exactly 2 risk groups to fail (e.g., data centers)
            # Note: logic defaults to "or" when not specified
            - entity_scope: "risk_group"
              rule_type: "choice"
              count: 2
        ```

    Attributes:
        rules (List[FailureRule]):
            A list of FailureRules to apply.
        attrs (Dict[str, Any]):
            Arbitrary metadata about this policy (e.g. "name", "description").
        fail_risk_groups (bool):
            If True, after initial selection, expand failures among any
            node/link that shares a risk group with a failed entity.
        fail_risk_group_children (bool):
            If True, and if a risk_group is marked as failed, expand to
            children risk_groups recursively.
        seed (Optional[int]):
            Seed for reproducible random operations. If None, operations
            will be non-deterministic.

    """

    attrs: Dict[str, Any] = field(default_factory=dict)
    fail_risk_groups: bool = False
    fail_risk_group_children: bool = False
    seed: Optional[int] = None
    modes: List[FailureMode] = field(default_factory=list)

    def apply_failures(
        self,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
        *,
        seed: Optional[int] = None,
    ) -> List[str]:
        """Identify which entities fail for this iteration.

        Select exactly one mode using configured weights and apply its rules.
        If no modes are configured, no failures are applied.

        Args:
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            network_risk_groups: Mapping of risk_group_name -> RiskGroup or dict.
            seed: Optional deterministic seed for selection.

        Returns:
            Sorted list of failed entity IDs (nodes, links, and/or risk group names).
        """
        if network_risk_groups is None:
            network_risk_groups = {}

        failed_nodes: Set[str] = set()
        failed_links: Set[str] = set()
        failed_risk_groups: Set[str] = set()

        # Determine rules from a selected mode (or none if no modes)
        rules_to_apply: Sequence[FailureRule] = []
        if self.modes:
            effective_seed = seed if seed is not None else self.seed
            mode_index = self._select_mode_index(self.modes, effective_seed)
            rules_to_apply = self.modes[mode_index].rules

        # Collect matched from each rule, then select
        for idx, rule in enumerate(rules_to_apply):
            matched_ids = self._match_scope(
                idx,
                rule,
                network_nodes,
                network_links,
                network_risk_groups,
            )
            effective_seed = seed if seed is not None else self.seed
            selected = self._select_entities(
                matched_ids,
                rule,
                effective_seed,
                network_nodes
                if rule.entity_scope == "node"
                else (
                    network_links
                    if rule.entity_scope == "link"
                    else network_risk_groups
                ),
            )

            # Add them to the respective fail sets
            if rule.entity_scope == "node":
                failed_nodes |= set(selected)
            elif rule.entity_scope == "link":
                failed_links |= set(selected)
            elif rule.entity_scope == "risk_group":
                failed_risk_groups |= set(selected)

        # Optionally expand by risk groups
        if self.fail_risk_groups:
            self._expand_risk_groups(
                failed_nodes, failed_links, network_nodes, network_links
            )

        # Optionally expand failed risk-group children
        if self.fail_risk_group_children and failed_risk_groups:
            self._expand_failed_risk_group_children(
                failed_risk_groups, network_risk_groups
            )

        all_failed = set(failed_nodes) | set(failed_links) | set(failed_risk_groups)
        return sorted(all_failed)

    def _match_scope(
        self,
        rule_idx: int,
        rule: FailureRule,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any],
    ) -> Set[str]:
        """Get the set of IDs matched by the given rule, either from cache
        or by performing a fresh match over the relevant entity type.
        """
        # Decide which mapping to iterate
        if rule.entity_scope == "node":
            matched = self._match_entities(network_nodes, rule.conditions, rule.logic)
        elif rule.entity_scope == "link":
            matched = self._match_entities(network_links, rule.conditions, rule.logic)
        else:  # risk_group
            matched = self._match_entities(
                network_risk_groups, rule.conditions, rule.logic
            )
        return matched

    def _match_entities(
        self,
        entity_map: Dict[str, Any],
        conditions: List[FailureCondition],
        logic: str,
    ) -> Set[str]:
        """Return all entity IDs that match the given conditions based on 'and'/'or' logic.

        entity_map is either nodes, links, or risk_groups:
          {entity_id -> {top_level_attr: value, ...}}

        If no conditions, return everything (no restrictions means all match).

        Returns:
            A set of matching entity IDs.
        """
        if not conditions:
            # No conditions means match all entities regardless of logic
            return set(entity_map.keys())

        matched = set()
        for entity_id, attrs in entity_map.items():
            if self._evaluate_conditions(attrs, conditions, logic):
                matched.add(entity_id)

        return matched

    @staticmethod
    def _evaluate_conditions(
        attrs: Dict[str, Any],
        conditions: List[FailureCondition],
        logic: str,
    ) -> bool:
        """Evaluate multiple conditions on a single entity. All or any condition(s)
        must pass, depending on 'logic'.
        """
        return _shared_evaluate_conditions(attrs, conditions, logic)

    @staticmethod
    def _select_entities(
        entity_ids: Set[str],
        rule: FailureRule,
        seed: Optional[int],
        entity_map: Dict[str, Any],
    ) -> Set[str]:
        """Select entities for failure per rule.

        For rule_type="choice" and rule.weight_by set, perform weighted sampling
        without replacement according to the specified attribute. If all weights
        are non-positive or missing, fallback to uniform sampling.
        """
        if not entity_ids:
            return set()

        # Ensure deterministic mapping from RNG draws to entity IDs by
        # iterating entities in a stable order. Set iteration order is
        # intentionally non-deterministic across processes (hash randomization).
        ordered_ids = sorted(entity_ids)

        if rule.rule_type == "random":
            rng = _random.Random(seed) if seed is not None else _random
            return {eid for eid in ordered_ids if rng.random() < rule.probability}
        elif rule.rule_type == "choice":
            count = min(rule.count, len(entity_ids))
            if count <= 0:
                return set()

            # Weighted without replacement if weight_by provided
            if rule.weight_by:
                weights: Dict[str, float] = {}
                positives: Dict[str, float] = {}
                zeros: list[str] = []
                for eid in ordered_ids:
                    w = FailurePolicy._extract_weight(
                        entity_map.get(eid), rule.weight_by
                    )
                    w = float(w) if isinstance(w, (int, float)) else 0.0
                    if w <= 0.0:
                        zeros.append(eid)
                        weights[eid] = 0.0
                    else:
                        positives[eid] = w
                        weights[eid] = w

                selected: set[str] = set()
                if positives:
                    k = min(count, len(positives))
                    selected |= FailurePolicy._weighted_sample_without_replacement(
                        positives, k, seed
                    )
                # If we still need more picks, fill uniformly from zero-weight items
                remaining = count - len(selected)
                if remaining > 0 and zeros:
                    # zeros already follow ordered_ids order; preserve that
                    pool = [z for z in zeros if z not in selected]
                    if pool:
                        rng = _random.Random(seed) if seed is not None else _random
                        selected |= set(rng.sample(pool, k=min(remaining, len(pool))))
                if selected:
                    return selected

            # Fallback to uniform sampling
            entity_list = ordered_ids
            rng = _random.Random(seed) if seed is not None else _random
            return set(rng.sample(entity_list, k=count))
        elif rule.rule_type == "all":
            return entity_ids
        else:
            raise ValueError(f"Unsupported rule_type: {rule.rule_type}")

    @staticmethod
    def _extract_weight(entity: Any, attr_name: str) -> float:
        """Extract weight attribute from entity which can be dict-like or object.

        Returns 0.0 on missing attributes or non-numeric values.
        """
        if entity is None:
            return 0.0
        # Dict mapping from merged attributes
        if isinstance(entity, dict):
            value = entity.get(attr_name)
        else:
            # RiskGroup object or similar with .attrs
            value = getattr(entity, "attrs", {}).get(attr_name)
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _weighted_sample_without_replacement(
        weights: Dict[str, float], count: int, seed: Optional[int]
    ) -> Set[str]:
        """Sample `count` keys without replacement proportionally to `weights`.

        Implements Efraimidis-Spirakis algorithm (2006) using keys k_i = U_i^(1/w_i)
        for w_i > 0, where U_i is uniform(0,1). Picks items with largest keys.

        Args:
            weights: Mapping from item id -> non-negative weight.
            count: Number of items to sample (<= len(weights)).
            seed: Optional deterministic seed.

        Returns:
            Set of selected item ids.
        """
        # Sort by item id to ensure a stable order of RNG draws per item
        positive_items: List[Tuple[str, float]] = sorted(
            [(k, w) for k, w in weights.items() if w > 0.0], key=lambda x: x[0]
        )
        if not positive_items:
            return set()

        rng = _random.Random(seed) if seed is not None else _random
        # Compute keys and select top `count`
        scored: List[Tuple[float, str]] = []
        for item_id, w in positive_items:
            u = rng.random()
            # Guard against u=0.0 -> use minimal positive number
            if u <= 0.0:
                u = 1e-12
            key = u ** (1.0 / w)
            scored.append((key, item_id))
        # Largest keys first
        scored.sort(reverse=True)
        selected_ids = {item_id for _, item_id in scored[:count]}
        return selected_ids

    @staticmethod
    def _select_mode_index(modes: Sequence["FailureMode"], seed: Optional[int]) -> int:
        """Select a mode index based on normalized weights.

        Modes with non-positive weights are ignored.
        """
        # Build cumulative weights
        effective: List[Tuple[int, float]] = [
            (idx, float(m.weight))
            for idx, m in enumerate(modes)
            if float(m.weight) > 0.0
        ]
        if not effective:
            # Degenerate: no positive weights -> fall back to first mode if exists
            return 0
        total = sum(w for _, w in effective)
        rng = _random.Random(seed) if seed is not None else _random
        r = rng.random() * total
        cumulative = 0.0
        for idx, w in effective:
            cumulative += w
            if r < cumulative:
                return idx
        # Fallback due to FP rounding
        return effective[-1][0]

    def _expand_risk_groups(
        self,
        failed_nodes: Set[str],
        failed_links: Set[str],
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
    ) -> None:
        """Expand failures among any node/link that shares a risk group
        with a failed entity. BFS until no new failures.
        """
        # We'll handle node + link expansions only. (Risk group expansions are separate.)
        # Build a map risk_group -> set of node or link IDs
        rg_to_entities: Dict[str, Set[str]] = defaultdict(set)

        # Gather risk_groups from nodes
        for n_id, nd in network_nodes.items():
            if "risk_groups" in nd and nd["risk_groups"]:
                for rg in nd["risk_groups"]:
                    rg_to_entities[rg].add(n_id)

        # Gather risk_groups from links
        for l_id, lk in network_links.items():
            if "risk_groups" in lk and lk["risk_groups"]:
                for rg in lk["risk_groups"]:
                    rg_to_entities[rg].add(l_id)

        # Combined set of failed node/link IDs
        queue = deque(failed_nodes | failed_links)
        visited = set(queue)  # track which entity IDs we've processed

        while queue:
            current_id = queue.popleft()
            # figure out if current_id is a node or a link by seeing where it appears
            current_rgs = []
            if current_id in network_nodes:
                # node
                nd = network_nodes[current_id]
                current_rgs = nd.get("risk_groups", [])
            elif current_id in network_links:
                # link
                lk = network_links[current_id]
                current_rgs = lk.get("risk_groups", [])

            for rg in current_rgs:
                # all entity IDs in rg_to_entities[rg] should be failed
                for other_id in rg_to_entities[rg]:
                    if other_id not in visited:
                        visited.add(other_id)
                        queue.append(other_id)
                        if other_id in network_nodes:
                            failed_nodes.add(other_id)
                        elif other_id in network_links:
                            failed_links.add(other_id)
                        # if other_id in risk_groups => not handled here

    def _expand_failed_risk_group_children(
        self,
        failed_rgs: Set[str],
        all_risk_groups: Dict[str, Any],
    ) -> None:
        """If we fail a risk_group, also fail its descendants recursively.

        We assume each entry in all_risk_groups is something like:
            rg_name -> RiskGroup object or { 'name': .., 'children': [...] }

        BFS or DFS any children to mark them as failed as well.
        """
        queue = deque(failed_rgs)
        while queue:
            rg_name = queue.popleft()
            rg_data = all_risk_groups.get(rg_name)
            if not rg_data:
                continue
            # Suppose the children are in rg_data["children"]
            # or if it's an actual RiskGroup object => rg_data.children
            child_list = []
            if isinstance(rg_data, dict):
                child_list = rg_data.get("children", [])
            else:
                # assume it's a RiskGroup object with a .children
                child_list = rg_data.children

            for child_obj in child_list:
                # child_obj might be a dict or RiskGroup with name
                child_name = (
                    child_obj["name"] if isinstance(child_obj, dict) else child_obj.name
                )
                if child_name not in failed_rgs:
                    failed_rgs.add(child_name)
                    queue.append(child_name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation with all fields as JSON-serializable primitives.
        """
        data: Dict[str, Any] = {
            "attrs": self.attrs,
            "fail_risk_groups": self.fail_risk_groups,
            "fail_risk_group_children": self.fail_risk_group_children,
            "seed": self.seed,
        }
        if self.modes:
            data["modes"] = [
                {
                    "weight": mode.weight,
                    "rules": [
                        {
                            "entity_scope": rule.entity_scope,
                            "conditions": [
                                {
                                    "attr": cond.attr,
                                    "operator": cond.operator,
                                    "value": cond.value,
                                }
                                for cond in rule.conditions
                            ],
                            "logic": rule.logic,
                            "rule_type": rule.rule_type,
                            "probability": rule.probability,
                            "count": rule.count,
                            **({"weight_by": rule.weight_by} if rule.weight_by else {}),
                        }
                        for rule in mode.rules
                    ],
                    "attrs": mode.attrs,
                }
                for mode in self.modes
            ]
        return data


def _evaluate_condition(entity_attrs: Dict[str, Any], cond: FailureCondition) -> bool:
    """Wrapper using the shared evaluator."""
    return _shared_evaluate_condition(entity_attrs, cond)
