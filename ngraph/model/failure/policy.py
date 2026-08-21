"""Failure policy primitives.

Defines `FailureRule` and `FailurePolicy` for expressing how nodes, links,
and risk groups fail in analyses. Conditions match on top-level attributes
with simple operators; rules select matches using "all", probabilistic
"random" (with `probability`), or fixed-size "choice" (with `count`).
Policies can optionally expand failures by shared risk groups. Failed risk
groups always cascade to their children downstream (the hierarchy is
inherent), so no policy flag controls that behavior.
"""

from __future__ import annotations

import heapq
import math
import random as _random
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, Sequence, Set, Tuple, get_args

from ngraph.model.selectors import (
    Condition,
    EntityScope,
    link_path_key,
    match_entity_ids,
)


@dataclass
class FailureRule:
    """Defines how to match and then select entities for failure.

    Attributes:
        scope: The type of entities this rule applies to: "node", "link",
            or "risk_group".
        conditions: A list of conditions to filter matching entities.
        logic: "and" (all must be true) or "or" (any must be true, default).
        mode: The selection strategy among the matched set:
            - "random": each matched entity fails independently with
              `probability`.
            - "choice": pick exactly `count` items (random sample).
            - "all": select every matched entity.
        probability: Probability in [0,1], used if mode="random".
        count: Number of entities to pick if mode="choice".
        weight_by: Optional attribute for weighted sampling in choice mode.
        path: Optional regex pattern applied after condition matching. For
            node and risk_group scope it is matched against the entity ID;
            for link scope it is matched against the "source|target" key,
            not the link ID.
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
        if self.scope not in get_args(EntityScope):
            raise ValueError(
                f"Invalid rule scope '{self.scope}'. "
                f"Valid scopes: {', '.join(get_args(EntityScope))}"
            )
        if self.mode not in ("random", "choice", "all"):
            raise ValueError(
                f"Invalid rule mode '{self.mode}'. Valid modes: random, choice, all"
            )
        if self.logic not in ("and", "or"):
            raise ValueError(
                f"Invalid rule logic '{self.logic}'. Must be 'and' or 'or'."
            )
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

    The main entry point is `apply_failures_typed`, which:
      1) Builds a single RNG for the entire call (from `seed` or `self.seed`).
      2) Selects a mode based on weights (one RNG draw).
      3) Gathers the relevant entities for each rule in that mode.
      4) Matches them against the rule conditions using 'and' or 'or' logic.
      5) Applies the selection strategy (all, random, or choice), drawing
         from the same RNG, which keeps rules statistically independent.
      6) Collects the union of all failed entities across all rules.
      7) Optionally expands failures by shared-risk groups.

    Attributes:
        attrs: Arbitrary metadata about this policy.
        expand_groups: If True, expand failures among entities sharing
            risk groups with failed entities.
        seed: Default seed for reproducible random operations. Overridden
            by the ``seed`` parameter on ``apply_failures_typed`` when
            provided.
        modes: List of weighted failure modes.
    """

    attrs: Dict[str, Any] = field(default_factory=dict)
    expand_groups: bool = False
    seed: Optional[int] = None
    modes: List[FailureMode] = field(default_factory=list)

    def apply_failures_typed(
        self,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
        *,
        seed: Optional[int] = None,
        failure_trace: Optional[Dict[str, Any]] = None,
        prepared_matches: Optional[Dict[int, tuple[str, ...]]] = None,
        prepared_weights: Optional[
            Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]
        ] = None,
        prepared_rg_index: Optional[Dict[str, Set[str]]] = None,
        prepared_rg_members: Optional[Dict[str, Tuple[frozenset, frozenset]]] = None,
    ) -> Tuple[Set[str], Set[str], Set[str]]:
        """Identify which entities fail for this iteration, typed by scope.

        A single ``random.Random`` instance is created from the effective seed
        (``seed`` if given, else ``self.seed``).  All random draws -- mode
        selection followed by per-rule entity selection -- are sequential from
        this one stream, ensuring that rules are statistically independent.
        When no seed is available, an unseeded ``Random()`` instance is used so
        that results are isolated from the global ``random`` module state.

        Args:
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            network_risk_groups: Mapping of risk_group_name -> flattened attribute dict.
            seed: Optional deterministic seed for selection.  Overrides
                ``self.seed`` when provided.
            failure_trace: Optional dict to populate with trace data (mode selection,
                rule selections, expansion). If provided, will be mutated in-place.
            prepared_matches: Optional mapping from ``id(rule)`` to already-sorted
                candidate IDs. Used by FailureManager to avoid repeated matching.
            prepared_weights: Optional per-rule weight splits from
                ``prepare_weights``. Only consulted for rules that also appear
                in ``prepared_matches``.
            prepared_rg_index: Optional precomputed risk-group -> entity-ID index
                (see ``build_risk_group_index``). Used by callers that invoke
                ``apply_failures_typed`` repeatedly on a static network to avoid
                rebuilding the index on every call. Only consulted when
                ``expand_groups`` is True; built on demand when omitted.
            prepared_rg_members: Optional transitive risk-group -> (nodes,
                links) member index. Seeds expansion for rule-failed risk
                groups, including nested children that are not registered
                top-level; without it, seeding falls back to the flattened
                risk-group map and reaches only registered groups.

        Returns:
            Tuple of (failed_nodes, failed_links, failed_risk_groups). Typed
            sets let callers classify entities without name probing, which
            matters when a risk group shares its name with a node or link.
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

        # Build a single RNG for this entire apply_failures call.
        # All random draws (mode selection, entity selection across rules)
        # come from this one stream, ensuring statistical independence.
        effective_seed = seed if seed is not None else self.seed
        rng = (
            _random.Random(effective_seed)
            if effective_seed is not None
            else _random.Random()
        )

        # Determine rules from a selected mode (or none if no modes / no mode
        # has positive weight)
        rules_to_apply: Sequence[FailureRule] = []
        if self.modes:
            mode_index = self._select_mode_index(self.modes, rng)
            if mode_index is not None:
                rules_to_apply = self.modes[mode_index].rules
                if failure_trace is not None:
                    failure_trace["mode_index"] = mode_index
                    failure_trace["mode_attrs"] = dict(self.modes[mode_index].attrs)

        # Collect matched from each rule, then select
        for idx, rule in enumerate(rules_to_apply):
            matched_ids: Sequence[str] | Set[str]
            if prepared_matches is not None and id(rule) in prepared_matches:
                matched_ids = prepared_matches[id(rule)]
            else:
                matched_ids = self._match_scope(
                    rule,
                    network_nodes,
                    network_links,
                    network_risk_groups,
                )
            weight_split = None
            if (
                prepared_weights is not None
                and prepared_matches is not None
                and id(rule) in prepared_matches
            ):
                weight_split = prepared_weights.get(id(rule))
            selected = self._select_entities(
                matched_ids,
                rule,
                rng,
                network_nodes
                if rule.scope == "node"
                else (network_links if rule.scope == "link" else network_risk_groups),
                weight_split=weight_split,
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

            if rule.scope == "node":
                failed_nodes |= set(selected)
            elif rule.scope == "link":
                failed_links |= set(selected)
            elif rule.scope == "risk_group":
                failed_risk_groups |= set(selected)

        # Snapshot before expansion for trace
        pre_nodes: Set[str] = set()
        pre_links: Set[str] = set()
        if failure_trace is not None:
            pre_nodes = set(failed_nodes)
            pre_links = set(failed_links)

        # Optionally expand by risk groups. Members of rule-failed risk
        # groups seed the expansion so the same physical failure state
        # expands identically regardless of which rule scope produced it.
        if self.expand_groups:
            self._expand_risk_groups(
                failed_nodes,
                failed_links,
                network_nodes,
                network_links,
                rg_to_entities=prepared_rg_index,
                failed_risk_groups=failed_risk_groups,
                network_risk_groups=network_risk_groups,
                rg_members=prepared_rg_members,
            )

        # Capture expansion in trace
        if failure_trace is not None:
            failure_trace["expansion"] = {
                "nodes": sorted(failed_nodes - pre_nodes),
                "links": sorted(failed_links - pre_links),
                # Expansion adds member nodes/links; the group set never grows.
                "risk_groups": [],
            }

        return failed_nodes, failed_links, failed_risk_groups

    def apply_failures(
        self,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
        *,
        seed: Optional[int] = None,
        failure_trace: Optional[Dict[str, Any]] = None,
        prepared_matches: Optional[Dict[int, tuple[str, ...]]] = None,
        prepared_weights: Optional[
            Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]
        ] = None,
        prepared_rg_index: Optional[Dict[str, Set[str]]] = None,
        prepared_rg_members: Optional[Dict[str, Tuple[frozenset, frozenset]]] = None,
    ) -> List[str]:
        """Identify which entities fail for this iteration.

        Convenience wrapper over ``apply_failures_typed`` returning a single
        merged, sorted ID list. Use the typed variant when entity kinds must
        be distinguished (IDs are not guaranteed unique across kinds).

        Returns:
            Sorted list of failed entity IDs (nodes, links, and/or risk group names).
        """
        failed_nodes, failed_links, failed_risk_groups = self.apply_failures_typed(
            network_nodes,
            network_links,
            network_risk_groups,
            seed=seed,
            failure_trace=failure_trace,
            prepared_matches=prepared_matches,
            prepared_weights=prepared_weights,
            prepared_rg_index=prepared_rg_index,
            prepared_rg_members=prepared_rg_members,
        )
        return sorted(failed_nodes | failed_links | failed_risk_groups)

    def prepare_matches(
        self,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
    ) -> Dict[int, tuple[str, ...]]:
        """Prepare stable ordered candidate pools for all rules in this policy.

        Pre-computes the set of matching entity IDs for each rule so that
        ``apply_failures`` can skip per-iteration condition evaluation.

        Args:
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            network_risk_groups: Mapping of risk_group_name -> flattened attribute dict.

        Returns:
            Mapping from ``id(rule)`` to a sorted tuple of matching entity IDs.
        """
        if network_risk_groups is None:
            network_risk_groups = {}

        prepared: Dict[int, tuple[str, ...]] = {}
        for mode in self.modes:
            for rule in mode.rules:
                rule_key = id(rule)
                if rule_key in prepared:
                    continue
                prepared[rule_key] = tuple(
                    sorted(
                        self._match_scope(
                            rule,
                            network_nodes,
                            network_links,
                            network_risk_groups,
                        )
                    )
                )
        return prepared

    def prepare_weights(
        self,
        prepared_matches: Dict[int, tuple[str, ...]],
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any] | None = None,
    ) -> Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]]:
        """Precompute per-rule weight splits for weighted-choice rules.

        Weights depend only on the static entity attributes, so callers that
        invoke ``apply_failures_typed`` repeatedly (Monte Carlo) should compute
        them once. For each ``mode="choice"`` rule with ``weight_by``, maps
        ``id(rule)`` to ``(positives, zeros)``: entities with positive weight
        (insertion-ordered by sorted entity id) and zero/missing-weight
        entities (same order). Only valid together with ``prepared_matches``
        from the same policy and entity maps.

        Args:
            prepared_matches: Result of ``prepare_matches`` for this policy.
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            network_risk_groups: Mapping of risk_group_name -> flattened
                attribute dict.

        Returns:
            Mapping from ``id(rule)`` to its precomputed weight split.
        """
        if network_risk_groups is None:
            network_risk_groups = {}

        prepared: Dict[int, Tuple[Dict[str, float], Tuple[str, ...]]] = {}
        for mode in self.modes:
            for rule in mode.rules:
                rule_key = id(rule)
                if rule_key in prepared or rule_key not in prepared_matches:
                    continue
                if rule.mode != "choice" or not rule.weight_by:
                    continue
                entity_map = (
                    network_nodes
                    if rule.scope == "node"
                    else (
                        network_links if rule.scope == "link" else network_risk_groups
                    )
                )
                positives: Dict[str, float] = {}
                zeros: list[str] = []
                for eid in prepared_matches[rule_key]:
                    w = FailurePolicy._extract_weight(
                        entity_map.get(eid), rule.weight_by
                    )
                    w = float(w) if isinstance(w, (int, float)) else 0.0
                    if w <= 0.0:
                        zeros.append(eid)
                    else:
                        positives[eid] = w
                prepared[rule_key] = (positives, tuple(zeros))
        return prepared

    def _match_scope(
        self,
        rule: FailureRule,
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        network_risk_groups: Dict[str, Any],
    ) -> Set[str]:
        """Get the set of IDs matched by the given rule.

        Evaluates the rule's conditions via ``match_entity_ids``, then applies
        the optional ``path`` regex. For link scope the regex is matched
        against the "source|target" key, otherwise against the entity ID.
        """
        if rule.scope == "node":
            candidates = match_entity_ids(network_nodes, rule.conditions, rule.logic)
        elif rule.scope == "link":
            candidates = match_entity_ids(network_links, rule.conditions, rule.logic)
        else:  # risk_group
            candidates = match_entity_ids(
                network_risk_groups, rule.conditions, rule.logic
            )

        if rule.path:
            pattern = re.compile(rule.path)
            if rule.scope == "link":
                candidates = {
                    eid
                    for eid in candidates
                    if pattern.match(link_path_key(network_links[eid]))
                }
            else:
                candidates = {eid for eid in candidates if pattern.match(eid)}

        return candidates

    @staticmethod
    def _select_entities(
        entity_ids: Sequence[str] | Set[str],
        rule: FailureRule,
        rng: _random.Random,
        entity_map: Dict[str, Any],
        weight_split: Optional[Tuple[Dict[str, float], Tuple[str, ...]]] = None,
    ) -> Set[str]:
        """Select entities for failure per rule.

        For mode="choice" and rule.weight_by set, perform weighted sampling
        without replacement according to the specified attribute. If all weights
        are non-positive or missing, fallback to uniform sampling.

        Args:
            entity_ids: Candidate entity IDs. Accepts a pre-sorted sequence
                (from ``prepare_matches``) or a set (sorted internally).
            rule: The failure rule specifying selection strategy.
            rng: Random instance shared across the entire apply_failures call.
            entity_map: Mapping of entity_id -> attribute dict, consulted only
                to read ``weight_by`` values.
            weight_split: Precomputed ``(positives, zeros)`` split from
                ``prepare_weights``; computed here when omitted.
        """
        if not entity_ids:
            return set()

        # Ensure deterministic mapping from RNG draws to entity IDs. Prepared
        # matches are already ordered (used as-is, no copy); sets must still
        # be sorted here.
        ordered_ids: Sequence[str] = (
            entity_ids if isinstance(entity_ids, (tuple, list)) else sorted(entity_ids)
        )

        if rule.mode == "random":
            # Draw the failure count from Binomial(n, p) and sample uniformly:
            # distributionally identical to per-entity Bernoulli trials but
            # O(failures) instead of O(matched). binomialvariate requires
            # Python 3.12+; fall back to the per-entity loop on 3.11.
            binomialvariate = getattr(rng, "binomialvariate", None)
            if binomialvariate is not None:
                k = binomialvariate(len(ordered_ids), rule.probability)
                return set(rng.sample(ordered_ids, k=k))
            return {eid for eid in ordered_ids if rng.random() < rule.probability}
        elif rule.mode == "choice":
            count = min(rule.count, len(ordered_ids))
            if count <= 0:
                return set()

            # Weighted without replacement if weight_by provided. The
            # positive/zero split is static per rule; use the precomputed one
            # (see prepare_weights) when the caller supplies it.
            if rule.weight_by:
                if weight_split is not None:
                    positives, zeros = weight_split
                else:
                    positives = {}
                    zeros_list: list[str] = []
                    for eid in ordered_ids:
                        w = FailurePolicy._extract_weight(
                            entity_map.get(eid), rule.weight_by
                        )
                        w = float(w) if isinstance(w, (int, float)) else 0.0
                        if w <= 0.0:
                            zeros_list.append(eid)
                        else:
                            positives[eid] = w
                    zeros = tuple(zeros_list)

                selected: set[str] = set()
                if positives:
                    k = min(count, len(positives))
                    selected |= FailurePolicy._weighted_sample_without_replacement(
                        positives, k, rng
                    )
                # If we still need more picks, fill uniformly from zero-weight items
                remaining = count - len(selected)
                if remaining > 0 and zeros:
                    # zeros already follow ordered_ids order; preserve that
                    pool = [z for z in zeros if z not in selected]
                    if pool:
                        selected |= set(rng.sample(pool, k=min(remaining, len(pool))))
                return selected

            # Uniform sampling when no weighting is requested
            return set(rng.sample(ordered_ids, k=count))

        # mode == "all" (validated in FailureRule.__post_init__)
        return set(ordered_ids)

    @staticmethod
    def _extract_weight(entity: Optional[Dict[str, Any]], attr_name: str) -> float:
        """Extract a numeric weight from a flattened attribute dict.

        Returns 0.0 on missing entities, missing attributes, or non-numeric values.
        """
        if entity is None:
            return 0.0
        value = entity.get(attr_name)
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _weighted_sample_without_replacement(
        weights: Dict[str, float], count: int, rng: _random.Random
    ) -> Set[str]:
        """Sample `count` keys without replacement proportionally to `weights`.

        Implements Efraimidis-Spirakis algorithm (2006) using keys k_i = U_i^(1/w_i)
        for w_i > 0, where U_i is uniform(0,1). Picks items with largest keys.

        Args:
            weights: Mapping from item id -> non-negative weight.
            count: Number of items to sample (<= len(weights)).
            rng: Random instance shared across the entire apply_failures call.

        Returns:
            Set of selected item ids.
        """
        # Sort by item id to ensure a stable order of RNG draws per item
        positive_items: List[Tuple[str, float]] = sorted(
            [(k, w) for k, w in weights.items() if w > 0.0], key=lambda x: x[0]
        )
        if not positive_items:
            return set()

        # Efraimidis-Spirakis keys computed in the log domain: ln(u) / w is a
        # monotone transform of u ** (1/w), so the ranking is identical where
        # the linear form is exact, but the log form neither underflows to 0.0
        # for tiny weights (~1e-5, e.g. per-hour failure rates) nor saturates
        # to 1.0 for huge ones -- both of which silently degenerated selection
        # into descending-id order regardless of weights.
        scored: List[Tuple[float, str]] = []
        for item_id, w in positive_items:
            u = rng.random()
            # Guard against u=0.0 -> use minimal positive number
            if u <= 0.0:
                u = 1e-12
            scored.append((math.log(u) / w, item_id))
        # Largest keys win; nlargest avoids sorting the full candidate list.
        return {item_id for _, item_id in heapq.nlargest(count, scored)}

    @staticmethod
    def _select_mode_index(
        modes: Sequence["FailureMode"], rng: _random.Random
    ) -> Optional[int]:
        """Select a mode index based on normalized weights.

        Modes with non-positive weights are ignored. Returns None when no mode
        has positive weight, in which case no rules should be applied.

        Args:
            modes: Sequence of FailureMode objects to select from.
            rng: Random instance shared across the entire apply_failures call.
        """
        # Weights need not sum to 1; normalize against the positive ones only.
        effective: List[Tuple[int, float]] = [
            (idx, float(m.weight))
            for idx, m in enumerate(modes)
            if float(m.weight) > 0.0
        ]
        if not effective:
            # Degenerate: no positive weights -> no mode is selected
            return None
        total = sum(w for _, w in effective)
        r = rng.random() * total
        cumulative = 0.0
        for idx, w in effective:
            cumulative += w
            if r < cumulative:
                return idx
        # Fallback due to FP rounding
        return effective[-1][0]

    @staticmethod
    def build_risk_group_index(
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
    ) -> Dict[str, Set[str]]:
        """Build a risk-group -> entity-ID index for risk-group expansion.

        The index depends only on the network, so callers that invoke
        ``apply_failures_typed`` repeatedly (e.g., Monte Carlo iterations) should
        build it once and pass it via ``prepared_rg_index``.

        Args:
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.

        Returns:
            Mapping of risk-group name -> set of node and link IDs in the group.
        """
        rg_to_entities: Dict[str, Set[str]] = defaultdict(set)
        for n_id, nd in network_nodes.items():
            if "risk_groups" in nd and nd["risk_groups"]:
                for rg in nd["risk_groups"]:
                    rg_to_entities[rg].add(n_id)
        for l_id, lk in network_links.items():
            if "risk_groups" in lk and lk["risk_groups"]:
                for rg in lk["risk_groups"]:
                    rg_to_entities[rg].add(l_id)
        return rg_to_entities

    def _expand_risk_groups(
        self,
        failed_nodes: Set[str],
        failed_links: Set[str],
        network_nodes: Dict[str, Any],
        network_links: Dict[str, Any],
        rg_to_entities: Optional[Dict[str, Set[str]]] = None,
        failed_risk_groups: Optional[Set[str]] = None,
        network_risk_groups: Optional[Dict[str, Any]] = None,
        rg_members: Optional[Dict[str, Tuple[frozenset, frozenset]]] = None,
    ) -> None:
        """Expand failures among any node/link that shares a risk group
        with a failed entity. BFS until no new failures.

        When ``failed_risk_groups`` is given, the members of those groups
        (transitively through child groups) seed the expansion as well, so a
        rule-failed risk group expands exactly like the equivalent set of
        rule-failed member entities.

        Args:
            failed_nodes: Set of failed node IDs; mutated in place.
            failed_links: Set of failed link IDs; mutated in place.
            network_nodes: Mapping of node_id -> flattened attribute dict.
            network_links: Mapping of link_id -> flattened attribute dict.
            rg_to_entities: Optional precomputed risk-group -> entity-ID index
                (see ``build_risk_group_index``); built here when omitted.
            failed_risk_groups: Risk groups failed by risk_group-scoped rules.
            network_risk_groups: Mapping of risk_group_name -> flattened
                attribute dict (provides ``children`` for transitive members).
            rg_members: Optional transitive risk-group -> (node IDs, link IDs)
                index. Preferred over ``network_risk_groups`` for seeding,
                since it also covers nested groups that are not registered
                top-level.
        """
        # Expansion only ever adds nodes and links; the failed risk-group set
        # is never grown here.
        if rg_to_entities is None:
            rg_to_entities = self.build_risk_group_index(network_nodes, network_links)

        # Seed with members of failed risk groups so a rule-failed group
        # expands like the equivalent set of rule-failed member entities.
        if failed_risk_groups:
            if rg_members is not None:
                # Transitive member index (covers nested child groups even
                # when they are not registered top-level; FailureManager
                # passes its recursive index here).
                for rg_name in failed_risk_groups:
                    member_nodes, member_links = rg_members.get(
                        rg_name, (frozenset(), frozenset())
                    )
                    failed_nodes.update(member_nodes)
                    failed_links.update(member_links)
            else:
                # Best-effort fallback: walk children via the flattened
                # risk-group map. Nested groups that are absent from the map
                # (only top-level groups are registered in
                # network.risk_groups) cannot be traversed here, so direct
                # callers wanting full-depth seeding should pass rg_members.
                network_risk_groups = network_risk_groups or {}
                rg_queue = deque(failed_risk_groups)
                seen_rgs = set(failed_risk_groups)
                while rg_queue:
                    rg_name = rg_queue.popleft()
                    for member_id in rg_to_entities.get(rg_name, ()):
                        if member_id in network_nodes:
                            failed_nodes.add(member_id)
                        elif member_id in network_links:
                            failed_links.add(member_id)
                    for child in network_risk_groups.get(rg_name, {}).get(
                        "children", []
                    ):
                        if child not in seen_rgs:
                            seen_rgs.add(child)
                            rg_queue.append(child)

        queue = deque(failed_nodes | failed_links)
        visited = set(queue)

        while queue:
            current_id = queue.popleft()
            # An ID can name either a node or a link; look it up in both maps.
            current_rgs = []
            if current_id in network_nodes:
                nd = network_nodes[current_id]
                current_rgs = nd.get("risk_groups", [])
            elif current_id in network_links:
                lk = network_links[current_id]
                current_rgs = lk.get("risk_groups", [])

            for rg in current_rgs:
                for other_id in rg_to_entities.get(rg, ()):
                    if other_id not in visited:
                        visited.add(other_id)
                        queue.append(other_id)
                        if other_id in network_nodes:
                            failed_nodes.add(other_id)
                        elif other_id in network_links:
                            failed_links.add(other_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        The output matches the scenario YAML failure-policy format: rule
        conditions and logic are nested under a ``match`` key, so the result
        round-trips through ``build_failure_policy``. The policy ``seed`` is
        derived at scenario load time and is not part of the format, so it is
        not serialized.

        Returns:
            Dictionary representation with all fields as JSON-serializable primitives.
        """
        data: Dict[str, Any] = {
            "attrs": dict(self.attrs),
            "expand_groups": self.expand_groups,
        }
        if self.modes:
            data["modes"] = [
                {
                    "weight": mode.weight,
                    "rules": [
                        {
                            "scope": rule.scope,
                            "match": {
                                "logic": rule.logic,
                                "conditions": [
                                    {
                                        "attr": cond.attr,
                                        "op": cond.op,
                                        "value": cond.value,
                                    }
                                    for cond in rule.conditions
                                ],
                            },
                            "mode": rule.mode,
                            "probability": rule.probability,
                            "count": rule.count,
                            **({"weight_by": rule.weight_by} if rule.weight_by else {}),
                            **({"path": rule.path} if rule.path else {}),
                        }
                        for rule in mode.rules
                    ],
                    "attrs": dict(mode.attrs),
                }
                for mode in self.modes
            ]
        return data
