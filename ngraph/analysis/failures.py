"""Canonical failure draws, graph-owned cases and independent-case scheduling."""

from __future__ import annotations

import heapq
import math
import os
import random
import re
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, TypeVar

from ngraph.analysis.topology import eligibility
from ngraph.model.failure import FailurePolicy
from ngraph.model.network import Network
from ngraph.model.risk import MembershipIndex
from ngraph.model.selectors import (
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    link_path_key,
    match_entity_ids,
)
from ngraph.results import (
    FailureCase,
    FailurePattern,
    FailureSelection,
    FailureTrace,
    SamplingMetadata,
)
from ngraph.utils.values import JSONValue, integer, physical

if TYPE_CHECKING:
    from ngraph.scenario import PreparedScenario

Workers = int | Literal["auto"]


@dataclass(frozen=True)
class FailureRequest:
    """One failure sampling question.

    ``policy_name`` names a scenario's policy in the recorded question (an
    unnamed policy is recorded inline); ``seed_source`` records where a given
    ``seed`` came from.
    """

    policy: FailurePolicy | None
    iterations: int = 1
    seed: int | None = None
    failure_trace: bool = False
    policy_name: str | None = None
    seed_source: Literal["query", "step", "scenario"] = "query"

    def __post_init__(self) -> None:
        integer(self.iterations, "failure iterations", minimum=0)
        if self.seed is not None:
            if isinstance(self.seed, bool) or not isinstance(self.seed, int):
                raise ValueError("failure seed: expected an integer")
        if not isinstance(self.failure_trace, bool):
            raise ValueError("failure_trace: expected bool")
        if self.policy is not None and not isinstance(self.policy, FailurePolicy):
            raise TypeError("failure policy: expected FailurePolicy or None")
        if self.policy_name is not None and (
            not isinstance(self.policy_name, str) or self.policy is None
        ):
            raise ValueError("failure policy_name: expected a name with its policy")
        if self.seed_source not in ("query", "step", "scenario"):
            raise ValueError("failure seed_source: expected query, step or scenario")


@dataclass(frozen=True)
class _Rule:
    index: int
    scope: Literal["node", "link", "risk_group"]
    candidates: tuple[str, ...]
    mode: Literal["all", "random", "choice"]
    probability: float
    count: int
    log_weights: tuple[tuple[str, float], ...] | None
    zeros: tuple[str, ...]


@dataclass(frozen=True)
class _Mode:
    weight: float
    attrs: Mapping[str, JSONValue]
    rules: tuple[_Rule, ...]


@dataclass(frozen=True)
class _Policy:
    modes: tuple[_Mode, ...]
    membership: MembershipIndex
    expand_groups: bool
    mode_intervals: tuple[tuple[int, int], ...] = ()
    mode_total: int = 0


def resolve_workers(workers: Workers) -> int:
    if workers == "auto":
        return os.cpu_count() or 1
    return integer(workers, "workers", minimum=1)


def sampling_metadata(request: FailureRequest | None) -> SamplingMetadata | None:
    if request is None:
        return None
    seed = request.seed
    source: Literal["query", "step", "scenario", "policy", "unseeded"]
    source = request.seed_source
    if seed is None:
        seed = request.policy.seed if request.policy is not None else None
        source = "policy" if seed is not None else "unseeded"
    return SamplingMetadata(seed, source, request.iterations)


def _prepare(
    network: Network, membership: MembershipIndex, request: FailureRequest
) -> _Policy:
    policy = request.policy
    if policy is None:
        return _Policy((), membership, False)
    if not isinstance(policy.expand_groups, bool):
        raise ValueError("failure policy expand_groups: expected bool")
    maps = {
        "node": {
            name: flatten_node_attrs(node) for name, node in network.nodes.items()
        },
        "link": {
            name: flatten_link_attrs(link, name) for name, link in network.links.items()
        },
        "risk_group": {
            name: flatten_risk_group_attrs(group)
            for name, group in membership.groups.items()
        },
    }
    modes: list[_Mode] = []
    for mode_index, mode in enumerate(policy.modes):
        label = f"failure mode {mode_index}"
        weight = physical(mode.weight, label + " weight")
        rules: list[_Rule] = []
        for rule_index, rule in enumerate(mode.rules):
            label = f"failure mode {mode_index} rule {rule_index}"
            if rule.scope not in maps:
                raise ValueError(f"{label}: unknown scope {rule.scope}")
            if rule.mode not in ("all", "random", "choice"):
                raise ValueError(f"{label}: unknown selection mode {rule.mode}")
            count = integer(rule.count, label + " count", minimum=0)
            probability = physical(rule.probability, label + " probability")
            if probability > 1:
                raise ValueError(f"{label}: probability must be in [0,1]")
            attrs = maps[rule.scope]
            matched = match_entity_ids(attrs, rule.conditions, rule.logic)
            if rule.path is not None:
                try:
                    pattern = re.compile(rule.path)
                except (re.error, TypeError) as exc:
                    raise ValueError(f"{label}: invalid path: {exc}") from exc
                matched = {
                    name
                    for name in matched
                    if pattern.match(
                        link_path_key(attrs[name]) if rule.scope == "link" else name
                    )
                }
            candidates = tuple(sorted(matched))
            weights = None
            zeros: list[str] = []
            if rule.mode == "choice" and rule.weight_by:
                weighted: list[tuple[str, float]] = []
                for name in candidates:
                    value = attrs[name].get(rule.weight_by)
                    try:
                        value = float(value) if value is not None else 0.0
                    except (ValueError, TypeError):
                        value = 0.0
                    if not math.isfinite(value):
                        raise ValueError(f"{label}: nonfinite weight for {name}")
                    if value > 0:
                        weighted.append((name, math.log(value)))
                    else:
                        zeros.append(name)
                weights = tuple(weighted)
            rules.append(
                _Rule(
                    rule_index,
                    rule.scope,
                    candidates,
                    rule.mode,
                    probability,
                    count,
                    weights,
                    tuple(zeros),
                )
            )
        modes.append(_Mode(weight, mode.attrs, tuple(rules)))
    positive = [
        (index, mode.weight.as_integer_ratio())
        for index, mode in enumerate(modes)
        if mode.weight > 0
    ]
    denominator = max((ratio[1] for _, ratio in positive), default=1)
    cumulative = 0
    intervals = []
    for index, (numerator, divisor) in positive:
        cumulative += numerator * (denominator // divisor)
        intervals.append((index, cumulative))
    return _Policy(
        tuple(modes), membership, policy.expand_groups, tuple(intervals), cumulative
    )


def _choose(rule: _Rule, rng: random.Random) -> tuple[str, ...]:
    if rule.mode == "all":
        return rule.candidates
    if rule.mode == "random":
        return tuple(
            name for name in rule.candidates if rng.random() < rule.probability
        )
    count = min(rule.count, len(rule.candidates))
    if rule.log_weights is None:
        return tuple(sorted(rng.sample(rule.candidates, count)))
    scores = []
    for name, log_weight in rule.log_weights:
        draw = rng.random()
        scores.append(
            (
                math.log(-math.log(draw)) - log_weight if draw > 0 else math.inf,
                name,
            )
        )
    selected = {name for _, name in heapq.nsmallest(min(count, len(scores)), scores)}
    if count > len(selected):
        selected.update(rng.sample(rule.zeros, count - len(selected)))
    return tuple(sorted(selected))


def _draw(
    policy: _Policy, draw_index: int, seed: int | None, traced: bool = True
) -> tuple[FailurePattern, FailureTrace | None]:
    rng = random.Random(None if seed is None else seed + draw_index)
    mode_index = None
    if policy.mode_intervals:
        numerator, denominator = rng.random().as_integer_ratio()
        mode_index = next(
            index
            for index, cumulative in policy.mode_intervals
            if numerator * policy.mode_total < cumulative * denominator
        )
    nodes: set[str] = set()
    links: set[str] = set()
    groups: set[str] = set()
    selections: list[FailureSelection] = []
    attrs: Mapping[str, JSONValue] = MappingProxyType({})
    if mode_index is not None:
        mode = policy.modes[mode_index]
        attrs = mode.attrs
        for rule in mode.rules:
            selected = _choose(rule, rng)
            if traced:
                selections.append(FailureSelection(rule.index, rule.scope, selected))
            {"node": nodes, "link": links, "risk_group": groups}[rule.scope].update(
                selected
            )
    members = policy.membership.expand(
        nodes, links, groups, shared=policy.expand_groups
    )
    pattern = FailurePattern(tuple(sorted(members.nodes)), tuple(sorted(members.links)))
    if not traced:
        return pattern, None
    trace = FailureTrace(
        draw_index,
        mode_index,
        attrs,
        tuple(selections),
        tuple(sorted(members.nodes.difference(nodes))),
        tuple(sorted(members.links.difference(links))),
    )
    return pattern, trace


def failure_cases(
    prepared: PreparedScenario, request: FailureRequest | None
) -> tuple[FailureCase, ...]:
    """The baseline, then each distinct drawn pattern with its draw count."""
    topology = prepared.topology
    baseline = FailurePattern((), ())
    counts = {baseline: 0}
    traces: dict[FailurePattern, FailureTrace] = {}
    if request is not None:
        policy = _prepare(prepared.scenario.network, prepared._membership, request)
        metadata = sampling_metadata(request)
        assert metadata is not None
        seed = metadata.seed
        for draw_index in range(request.iterations):
            pattern, trace = _draw(policy, draw_index, seed, request.failure_trace)
            counts[pattern] = counts.get(pattern, 0) + 1
            if trace is not None and pattern not in traces:
                traces[pattern] = trace
    return tuple(
        FailureCase(
            "baseline" if index == 0 else f"failure-{index:06d}",
            "baseline" if index == 0 else "failure",
            pattern,
            count,
            eligibility(
                topology,
                excluded_nodes=pattern.excluded_nodes,
                excluded_links=pattern.excluded_links,
            ),
            traces.get(pattern),
        )
        for index, (pattern, count) in enumerate(counts.items())
    )


_Result = TypeVar("_Result")
_Job = TypeVar("_Job")


def schedule_cases(
    cases: tuple[_Job, ...],
    solve: Callable[[_Job], _Result],
    workers: int,
) -> tuple[_Result, ...]:
    """Publish in case order; all worker cleanup completes before an error leaves."""
    if workers == 1 or len(cases) < 2:
        return tuple(solve(case) for case in cases)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(solve, case) for case in cases]
        return tuple(future.result() for future in futures)
