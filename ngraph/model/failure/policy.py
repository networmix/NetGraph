"""Failure policy primitives.

Defines `FailureRule` and `FailurePolicy` for expressing how nodes, links,
and risk groups fail in analyses. Conditions match on top-level attributes
with simple operators; rules select matches using "all", probabilistic
"random" (with `probability`), or fixed-size "choice" (with `count`).
Policies can optionally expand failures by shared risk groups or by
risk-group children.
"""

from __future__ import annotations

import random as _random
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple

from ngraph.dsl.selectors import Condition, EntityScope, match_entity_ids


@dataclass
class FailureRule:
    """Defines how to match and then select entities for failure.

    Attributes:
        scope: The type of entities this rule applies to: "node", "link",
            or "risk_group".
        conditions: A list of conditions to filter matching entities.
        logic: "and" (all must be true) or "or" (any must be true, default).
        mode: The selection strategy among the matched set:
            - "random": each matched entity is chosen with probability.
            - "choice": pick exactly `count` items (random sample).
            - "all": select every matched entity.
        probability: Probability in [0,1], used if mode="random".
        count: Number of entities to pick if mode="choice".
        weight_by: Optional attribute for weighted sampling in choice mode.
        path: Optional regex pattern to filter entities by name.
    """

    scope: EntityScope
    conditions: List[Condition] = field(default_factory=list)
    logic: Literal["and", "or"] = "or"
    mode: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1
    weight_by: Optional[str] = None
    path: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mode == "random":
            if not (0.0 <= self.probability <= 1.0):
                raise ValueError(
                    f"probability={self.probability} must be within [0,1] "
                    f"for mode='random'."
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
    """A container for failure modes plus optional metadata in `attrs`.

    The main entry point is `apply_failures`, which:
      1) Select a mode based on weights.
      2) For each rule in the mode, gather relevant entities.
      3) Match based on rule conditions using 'and' or 'or' logic.
      4) Apply the selection strategy (all, random, or choice).
      5) Collect the union of all failed entities across all rules.
      6) Optionally expand failures by shared-risk groups or sub-risks.

    Attributes:
        attrs: Arbitrary metadata about this policy.
        expand_groups: If True, expand failures among entities sharing
            risk groups with failed entities.
        expand_children: If True, expand failed risk groups to include
            their children recursively.
        seed: Seed for reproducible random operations.
        modes: List of weighted failure modes.
    """

    attrs: Dict[str, Any] = field(default_factory=dict)
    expand_groups: bool = False
    expand_children: bool = False
    seed: Optional[int] = None
    modes: List[FailureMode] = field(default_factory=list)

    def apply_failures(
        self,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
        *,
        seed: Optional[int] = None,
        failure_trace: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """Identify which entities fail for this iteration.

        Select exactly one mode using configured weights and apply its rules.
        If no modes are configured, no failures are applied.

        Args:
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            network_risk_groups: Mapping of risk_group_name -> RiskGroup or dict.
            seed: Optional deterministic seed for selection.
            failure_trace: Optional dict to populate with trace data (mode selection,
                rule selections, expansion). If provided, will be mutated in-place.

        Returns:
            Sorted list of failed entity IDs (nodes, links, and/or risk group names).
        """
        if network_risk_groups is None:
            network_risk_groups = {}

        failed_nodes: Set[str] = set()
        failed_links: Set[str] = set()
        failed_risk_groups: Set[str] = set()

        # Initialize trace structure if requested
        if failure_trace is not None:
            failure_trace.update(
                {
                    "mode_index": None,
                    "mode_attrs": {},
                    "selections": [],
                    "expansion": {"nodes": [], "links": [], "risk_groups": []},
                }
            )

        # Determine rules from a selected mode (or none if no modes)
        rules_to_apply: Sequence[FailureRule] = []
        if self.modes:
            effective_seed = seed if seed is not None else self.seed
            mode_index = self._select_mode_index(self.modes, effective_seed)
            rules_to_apply = self.modes[mode_index].rules
            if failure_trace is not None:
                failure_trace["mode_index"] = mode_index
                failure_trace["mode_attrs"] = dict(self.modes[mode_index].attrs)

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
                if rule.scope == "node"
                else (network_links if rule.scope == "link" else network_risk_groups),
            )

            # Record selection in trace if non-empty
            if failure_trace is not None and selected:
                failure_trace["selections"].append(
                    {
                        "rule_index": idx,
                        "scope": rule.scope,
                        "mode": rule.mode,
                        "matched_count": len(matched_ids),
                        "selected_ids": sorted(selected),
                    }
                )

            # Add them to the respective fail sets
            if rule.scope == "node":
                failed_nodes |= set(selected)
            elif rule.scope == "link":
                failed_links |= set(selected)
            elif rule.scope == "risk_group":
                failed_risk_groups |= set(selected)

        # Snapshot before expansion for trace
        pre_nodes: Set[str] = set()
        pre_links: Set[str] = set()
        pre_rgs: Set[str] = set()
        if failure_trace is not None:
            pre_nodes = set(failed_nodes)
            pre_links = set(failed_links)
            pre_rgs = set(failed_risk_groups)

        # Optionally expand by risk groups
        if self.expand_groups:
            self._expand_risk_groups(
                failed_nodes, failed_links, network_nodes, network_links
            )

        # Optionally expand failed risk-group children
        if self.expand_children and failed_risk_groups:
            self._expand_failed_risk_group_children(
                failed_risk_groups, network_risk_groups
            )

        # Capture expansion in trace
        if failure_trace is not None:
            failure_trace["expansion"] = {
                "nodes": sorted(failed_nodes - pre_nodes),
                "links": sorted(failed_links - pre_links),
                "risk_groups": sorted(failed_risk_groups - pre_rgs),
            }

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
        """Get the set of IDs matched by the given rule.

        Uses the shared match_entity_ids() function from selectors.
        Applies optional path filter if specified.
        """
        import re

        # Decide which mapping to iterate
        if rule.scope == "node":
            candidates = match_entity_ids(network_nodes, rule.conditions, rule.logic)
        elif rule.scope == "link":
            candidates = match_entity_ids(network_links, rule.conditions, rule.logic)
        else:  # risk_group
            candidates = match_entity_ids(
                network_risk_groups, rule.conditions, rule.logic
            )

        # Apply path filter if specified
        if rule.path:
            pattern = re.compile(rule.path)
            candidates = {eid for eid in candidates if pattern.match(eid)}

        return candidates

    @staticmethod
    def _select_entities(
        entity_ids: Set[str],
        rule: FailureRule,
        seed: Optional[int],
        entity_map: Dict[str, Any],
    ) -> Set[str]:
        """Select entities for failure per rule.

        For mode="choice" and rule.weight_by set, perform weighted sampling
        without replacement according to the specified attribute. If all weights
        are non-positive or missing, fallback to uniform sampling.
        """
        if not entity_ids:
            return set()

        # Ensure deterministic mapping from RNG draws to entity IDs by
        # iterating entities in a stable order. Set iteration order is
        # intentionally non-deterministic across processes (hash randomization).
        ordered_ids = sorted(entity_ids)

        if rule.mode == "random":
            rng = _random.Random(seed) if seed is not None else _random
            return {eid for eid in ordered_ids if rng.random() < rule.probability}
        elif rule.mode == "choice":
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
        elif rule.mode == "all":
            return entity_ids
        else:
            raise ValueError(f"Unsupported mode: {rule.mode}")

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
            "expand_groups": self.expand_groups,
            "expand_children": self.expand_children,
            "seed": self.seed,
        }
        if self.modes:
            data["modes"] = [
                {
                    "weight": mode.weight,
                    "rules": [
                        {
                            "scope": rule.scope,
                            "conditions": [
                                {
                                    "attr": cond.attr,
                                    "op": cond.op,
                                    "value": cond.value,
                                }
                                for cond in rule.conditions
                            ],
                            "logic": rule.logic,
                            "mode": rule.mode,
                            "probability": rule.probability,
                            "count": rule.count,
                            **({"weight_by": rule.weight_by} if rule.weight_by else {}),
                            **({"path": rule.path} if rule.path else {}),
                        }
                        for rule in mode.rules
                    ],
                    "attrs": mode.attrs,
                }
                for mode in self.modes
            ]
        return data
