"""Regression tests for FailureManager review fixes.

Covers:
- Demand-placement Monte Carlo with id-less demand configs (stable demand ids).
- Seed fallback to policy.seed when FailureManager seed is None.
- Context injection gated on the analysis function declaring 'context'.
- Prepared-matches cache identity check (id() address-reuse hazard).
- No forced serial execution for __main__-defined analysis functions.
- Transitive risk-group exclusions across a 3-level hierarchy.
- Risk-group expansion index built once per manager, not per iteration.
"""

from typing import Any

import pytest

from ngraph.analysis.failure_manager import FailureManager
from ngraph.analysis.functions import (
    _reconstruct_traffic_demands,
    build_demand_placement_inputs,
    demand_placement_analysis,
)
from ngraph.model.failure.policy import FailureMode, FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node, RiskGroup


def _chain_network() -> Network:
    """A -> B -> C chain with capacity 10 links."""
    network = Network()
    for name in ("A", "B", "C"):
        network.add_node(Node(name))
    network.add_link(Link("A", "B", capacity=10.0))
    network.add_link(Link("B", "C", capacity=10.0))
    return network


def _manager_with_link_choice_policy(network: Network) -> FailureManager:
    policy = FailurePolicy(
        seed=7,
        modes=[
            FailureMode(
                weight=1.0,
                rules=[FailureRule(scope="link", mode="choice", count=1)],
            )
        ],
    )
    policy_set = FailurePolicySet()
    policy_set.add("p", policy)
    return FailureManager(network, policy_set, "p")


def _manager_without_policy(network: Network) -> FailureManager:
    return FailureManager(network, FailurePolicySet(), None)


class TestIdlessDemandConfigs:
    """Demand configs without 'id' must not crash Monte Carlo analysis."""

    def test_run_demand_placement_mc_idless_combine(self) -> None:
        fm = _manager_with_link_choice_policy(_chain_network())

        result = fm.run_demand_placement_monte_carlo(
            [{"source": "^A$", "target": "^C$", "volume": 5.0, "mode": "combine"}],
            iterations=3,
        )

        assert result["baseline"] is not None
        assert result["baseline"].summary.total_placed == pytest.approx(5.0)
        assert len(result["results"]) >= 1

    def test_run_demand_placement_mc_idless_per_group(self) -> None:
        network = Network()
        for name in ("dc1/a", "dc1/b", "dc2/a", "dc2/b", "hub"):
            network.add_node(Node(name))
        for name in ("dc1/a", "dc1/b", "dc2/a", "dc2/b"):
            network.add_link(Link(name, "hub", capacity=10.0))
        fm = _manager_with_link_choice_policy(network)

        result = fm.run_demand_placement_monte_carlo(
            [
                {
                    "source": "^(dc[0-9]+)/.*",
                    "target": "^hub$",
                    "volume": 4.0,
                    "mode": "combine",
                    "group_mode": "per_group",
                }
            ],
            iterations=2,
        )

        baseline = result["baseline"]
        # One demand per source group (dc1, dc2), each volume 2.0
        assert baseline.summary.num_flows == 2
        assert baseline.summary.total_demand == pytest.approx(4.0)
        assert baseline.summary.total_placed == pytest.approx(4.0)

    def test_reconstructed_ids_are_deterministic(self) -> None:
        config = [
            {"source": "^A$", "target": "^C$", "volume": 5.0, "mode": "combine"},
            {"source": "^B$", "target": "^C$", "volume": 1.0},
        ]
        ids_first = [td.id for td in _reconstruct_traffic_demands(config)]
        ids_second = [td.id for td in _reconstruct_traffic_demands(config)]

        assert ids_first == ids_second
        assert all(ids_first)
        assert len(set(ids_first)) == len(ids_first)

    def test_prebuilt_context_without_expansion_idless_config(self) -> None:
        """Fallback path: context provided but expansion absent must still work."""
        network = _chain_network()
        config = [{"source": "^A$", "target": "^C$", "volume": 5.0, "mode": "combine"}]
        ctx, _, _ = build_demand_placement_inputs(network, config)

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=config,
            context=ctx,
        )

        assert result.summary.total_placed == pytest.approx(5.0)


class TestSeedFallback:
    """FailureManager seed=None must fall back to the policy's own seed."""

    def test_policy_seed_produces_varied_iterations(self) -> None:
        network = Network()
        names = [f"n{i}" for i in range(7)]
        for name in names:
            network.add_node(Node(name))
        for left, right in zip(names, names[1:], strict=False):
            network.add_link(Link(left, right, capacity=1.0))

        policy = FailurePolicy(
            seed=42,
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="link", mode="choice", count=1)],
                )
            ],
        )
        policy_set = FailurePolicySet()
        policy_set.add("p", policy)
        fm = FailureManager(network, policy_set, "p")

        def fake_analysis(
            network: Network, excluded_nodes: set, excluded_links: set
        ) -> dict[str, Any]:
            return {"excluded": len(excluded_links)}

        result = fm.run_monte_carlo_analysis(analysis_func=fake_analysis, iterations=10)

        # Without the fallback, every iteration reuses the same policy RNG
        # and collapses to a single failure pattern.
        assert result["metadata"]["unique_patterns"] > 1

    def test_policy_seed_fallback_is_reproducible(self) -> None:
        def run_once() -> list[tuple]:
            network = Network()
            for name in ("a", "b", "c", "d"):
                network.add_node(Node(name))
            policy = FailurePolicy(
                seed=13,
                modes=[
                    FailureMode(
                        weight=1.0,
                        rules=[FailureRule(scope="node", mode="choice", count=1)],
                    )
                ],
            )
            policy_set = FailurePolicySet()
            policy_set.add("p", policy)
            fm = FailureManager(network, policy_set, "p")
            patterns = []
            for i in range(5):
                excluded_nodes, excluded_links = fm.compute_exclusions(
                    seed_offset=13 + i
                )
                patterns.append((tuple(sorted(excluded_nodes))))
            return patterns

        assert run_once() == run_once()


class TestContextInjectionGating:
    """Context pre-building requires an explicit prepare_inputs hook."""

    def test_custom_function_with_source_target_params(self) -> None:
        fm = _manager_with_link_choice_policy(_chain_network())

        def custom(
            network: Network,
            excluded_nodes: set,
            excluded_links: set,
            source: str,
            target: str,
        ) -> dict[str, Any]:
            return {"src": source, "dst": target}

        result = fm.run_monte_carlo_analysis(
            analysis_func=custom, iterations=2, source="^A$", target="^C$"
        )

        assert result["baseline"] == {"src": "^A$", "dst": "^C$"}

    def test_var_keyword_function_does_not_opt_in(self) -> None:
        fm = _manager_without_policy(_chain_network())
        captured: list[dict[str, Any]] = []

        def custom(
            network: Network, excluded_nodes: set, excluded_links: set, **kwargs: Any
        ) -> dict[str, Any]:
            captured.append(dict(kwargs))
            return {}

        # 'source' is not a valid selector regex; injection would crash here.
        fm.run_monte_carlo_analysis(
            analysis_func=custom, iterations=1, source="dc(", target="x"
        )

        assert captured
        assert all("context" not in kwargs for kwargs in captured)

    def test_declared_context_without_hook_gets_no_injection(self) -> None:
        # Declaring a `context` parameter is no longer enough on its own;
        # only a prepare_inputs hook opts a function into pre-building.
        fm = _manager_without_policy(_chain_network())

        def custom(
            network: Network,
            excluded_nodes: set,
            excluded_links: set,
            demands_config: list,
            context: Any = None,
        ) -> dict[str, bool]:
            return {"has_context": context is not None}

        result = fm.run_monte_carlo_analysis(
            analysis_func=custom,
            iterations=1,
            demands_config=[
                {"source": "^A$", "target": "^C$", "volume": 1.0, "mode": "combine"}
            ],
        )

        assert result["baseline"] == {"has_context": False}

    def test_prepare_inputs_hook_receives_prebuilt_inputs(self) -> None:
        fm = _manager_without_policy(_chain_network())

        def custom(
            network: Network,
            excluded_nodes: set,
            excluded_links: set,
            demands_config: list,
            context: Any = None,
            expansion: Any = None,
            resolved_ids: Any = None,
        ) -> dict[str, bool]:
            return {
                "has_context": context is not None,
                "has_expansion": expansion is not None,
                "has_resolved_ids": resolved_ids is not None,
            }

        def prepare(network: Network, kwargs: dict) -> dict:
            ctx, expansion, resolved_ids = build_demand_placement_inputs(
                network, kwargs["demands_config"]
            )
            return {
                "context": ctx,
                "expansion": expansion,
                "resolved_ids": resolved_ids,
            }

        custom.prepare_inputs = prepare

        result = fm.run_monte_carlo_analysis(
            analysis_func=custom,
            iterations=1,
            demands_config=[
                {"source": "^A$", "target": "^C$", "volume": 1.0, "mode": "combine"}
            ],
        )

        assert result["baseline"] == {
            "has_context": True,
            "has_expansion": True,
            "has_resolved_ids": True,
        }

    def test_builtin_analysis_functions_carry_hook(self) -> None:
        from ngraph.analysis.functions import (
            demand_placement_analysis,
            max_flow_analysis,
            sensitivity_analysis,
        )

        for func in (
            demand_placement_analysis,
            max_flow_analysis,
            sensitivity_analysis,
        ):
            assert callable(getattr(func, "prepare_inputs", None))


class TestParallelismNotForcedSerial:
    """__main__-defined functions run with the requested thread parallelism."""

    def test_main_module_function_keeps_parallelism(self) -> None:
        fm = _manager_with_link_choice_policy(_chain_network())

        def main_func(
            network: Network, excluded_nodes: set, excluded_links: set
        ) -> dict[str, Any]:
            return {"ok": True}

        main_func.__module__ = "__main__"

        result = fm.run_monte_carlo_analysis(
            analysis_func=main_func, iterations=4, parallelism=2
        )

        assert result["metadata"]["parallelism"] == 2
        assert result["baseline"] == {"ok": True}


class TestPreparedMatchesCacheIdentity:
    """Cache entries must be ignored when the stored policy is a different object."""

    def test_stale_entry_with_reused_id_is_not_used(self) -> None:
        network = Network()
        network.add_node(Node("node1"))
        network.add_node(Node("node2"))
        fm = _manager_without_policy(network)

        policy_a = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="all", path="^node1$")],
                )
            ]
        )
        excluded_nodes, _ = fm.compute_exclusions(policy=policy_a)
        assert excluded_nodes == {"node1"}

        policy_b = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="all", path="^node2$")],
                )
            ]
        )
        rule_b = policy_b.modes[0].rules[0]
        # Simulate CPython address reuse: a stale entry stored under
        # id(policy_b) that belongs to policy_a and maps policy_b's rule
        # to the wrong candidate pool.
        fm._prepared_policy_matches[id(policy_b)] = (
            policy_a,
            {id(rule_b): ("node1",)},
        )

        excluded_nodes_b, _ = fm.compute_exclusions(policy=policy_b)
        assert excluded_nodes_b == {"node2"}

    def test_same_policy_object_uses_cache(self) -> None:
        network = Network()
        network.add_node(Node("node1"))
        fm = _manager_without_policy(network)
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="all")],
                )
            ]
        )

        first, _ = fm.compute_exclusions(policy=policy)
        cached_policy, cached_prepared = fm._prepared_policy_matches[id(policy)]
        second, _ = fm.compute_exclusions(policy=policy)

        assert first == second == {"node1"}
        assert cached_policy is policy
        assert fm._prepared_policy_matches[id(policy)][1] is cached_prepared


class TestRiskGroupIndexCache:
    """Risk-group expansion index is built once per manager, not per call."""

    @staticmethod
    def _network_with_shared_risk_group() -> Network:
        network = Network()
        network.add_node(Node("A", risk_groups={"rg1"}))
        network.add_node(Node("B", risk_groups={"rg1"}))
        network.add_node(Node("C"))
        network.add_link(Link("A", "C", capacity=1.0))
        return network

    @staticmethod
    def _expanding_policy_manager(network: Network) -> FailureManager:
        policy = FailurePolicy(
            expand_groups=True,
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="all", path="^A$")],
                )
            ],
        )
        policy_set = FailurePolicySet()
        policy_set.add("p", policy)
        return FailureManager(network, policy_set, "p")

    def test_index_built_once_across_many_exclusion_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fm = self._expanding_policy_manager(self._network_with_shared_risk_group())

        calls = {"count": 0}
        original = FailurePolicy.build_risk_group_index

        def counting(
            network_nodes: dict[str, Any], network_links: dict[str, Any]
        ) -> dict[str, set[str]]:
            calls["count"] += 1
            return original(network_nodes, network_links)

        monkeypatch.setattr(
            FailurePolicy, "build_risk_group_index", staticmethod(counting)
        )

        for i in range(10):
            excluded_nodes, _excluded_links = fm.compute_exclusions(seed_offset=i)
            # Expansion via the shared risk group must still take effect:
            # B shares rg1 with the failed node A.
            assert {"A", "B"} <= excluded_nodes

        assert calls["count"] == 1

    def test_index_not_built_when_policy_does_not_expand(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        network = self._network_with_shared_risk_group()
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="node", mode="all", path="^A$")],
                )
            ],
        )
        policy_set = FailurePolicySet()
        policy_set.add("p", policy)
        fm = FailureManager(network, policy_set, "p")

        def boom(*args: Any, **kwargs: Any) -> None:
            raise AssertionError(
                "build_risk_group_index must not run when expand_groups is False"
            )

        monkeypatch.setattr(FailurePolicy, "build_risk_group_index", staticmethod(boom))

        excluded_nodes, _excluded_links = fm.compute_exclusions()
        assert excluded_nodes == {"A"}


class TestRiskGroupHierarchyExclusions:
    """Nested (3-level) risk-group members must all be excluded."""

    def test_grandchild_members_excluded_when_top_fails(self) -> None:
        network = Network()
        network.add_node(Node("n_top", risk_groups={"top"}))
        network.add_node(Node("n_mid", risk_groups={"mid"}))
        network.add_node(Node("n_leaf", risk_groups={"leaf"}))
        network.add_node(Node("other"))
        leaf_link = Link("n_leaf", "other", risk_groups={"leaf"})
        network.add_link(leaf_link)

        # Only the top-level group is registered in network.risk_groups;
        # 'mid' and 'leaf' exist solely as nested children.
        network.risk_groups["top"] = RiskGroup(
            name="top",
            children=[RiskGroup(name="mid", children=[RiskGroup(name="leaf")])],
        )

        policy = FailurePolicy(
            modes=[
                FailureMode(
                    weight=1.0,
                    rules=[FailureRule(scope="risk_group", mode="all")],
                )
            ]
        )
        policy_set = FailurePolicySet()
        policy_set.add("p", policy)
        fm = FailureManager(network, policy_set, "p")

        excluded_nodes, excluded_links = fm.compute_exclusions()

        assert {"n_top", "n_mid", "n_leaf"} <= excluded_nodes
        assert "other" not in excluded_nodes
        assert leaf_link.id in excluded_links


class TestExpandGroupsScopeSymmetry:
    """expand_groups must produce identical exclusions whether a failure came
    from an entity rule or a risk_group rule, including depth>=3 hierarchies
    whose nested groups are not registered top-level."""

    def test_deep_hierarchy_rg_rule_matches_node_rule(self) -> None:
        from ngraph.model.network import Network, Node, RiskGroup

        def build() -> Network:
            net = Network()
            for n in ("n_leaf", "n_mid", "n_lat"):
                net.add_node(Node(n))
            leaf = RiskGroup(name="leaf")
            mid = RiskGroup(name="mid", children=[leaf])
            net.risk_groups["top"] = RiskGroup(name="top", children=[mid])
            net.nodes["n_leaf"].risk_groups |= {"leaf", "SHARED"}
            net.nodes["n_mid"].risk_groups |= {"mid"}
            net.nodes["n_lat"].risk_groups |= {"SHARED"}
            return net

        def exclusions(rule: FailureRule) -> list[str]:
            net = build()
            pol = FailurePolicy(
                expand_groups=True, modes=[FailureMode(weight=1.0, rules=[rule])]
            )
            fps = FailurePolicySet()
            fps.add("p", pol)
            fm = FailureManager(network=net, failure_policy_set=fps, policy_name="p")
            nodes, _ = fm.compute_exclusions(pol, 1)
            return sorted(nodes)

        via_rg = exclusions(FailureRule(scope="risk_group", mode="all", path="^top$"))
        via_nodes = exclusions(
            FailureRule(scope="node", mode="all", path="^(n_leaf|n_mid)$")
        )
        assert via_rg == via_nodes == ["n_lat", "n_leaf", "n_mid"]
