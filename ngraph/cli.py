"""Command-line interface for NetGraph."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from statistics import median
from time import perf_counter
from typing import Any, Dict, Iterator, List, Optional

from ngraph.explorer import NetworkExplorer
from ngraph.logging import get_logger, set_global_log_level, setup_root_logger
from ngraph.profiling.profiler import PerformanceProfiler, PerformanceReporter
from ngraph.scenario import Scenario
from ngraph.utils.output_paths import (
    ensure_parent_dir,
    profiles_dir_for_run,
    results_path_for_run,
)
from ngraph.workflow.base import WorkflowStep

logger = get_logger(__name__)


def _format_table(
    headers: List[str],
    rows: List[List[str]],
    min_width: int = 8,
    max_col_width: Optional[int] = None,
) -> str:
    """Format data as a simple ASCII table.

    Args:
        headers: Column labels, one per column.
        rows: One list of cell values per row, each the same length as
            ``headers``.
        min_width: Floor for every column width, in characters.
        max_col_width: Clip longer cells to this width with a trailing "...".
            None leaves cells unclipped.

    Returns:
        The rendered table, or "" when ``rows`` is empty.
    """
    if not rows:
        return ""

    def clip(val: Any) -> str:
        s = str(val)
        if max_col_width is not None and len(s) > max_col_width:
            return s[: max_col_width - 3] + "..."
        return s

    clipped_headers = [clip(h) for h in headers]
    clipped_rows = [[clip(item) for item in row] for row in rows]

    # Widths come from the clipped content, not the originals.
    all_data = [clipped_headers] + clipped_rows
    col_widths = []
    for col_idx in range(len(clipped_headers)):
        max_width = max(len(str(row[col_idx])) for row in all_data)
        col_widths.append(max(max_width, min_width))

    def format_row(row_data: List[str]) -> str:
        return "   " + " | ".join(
            f"{str(item):<{col_widths[i]}}" for i, item in enumerate(row_data)
        )

    lines = []
    lines.append(format_row(clipped_headers))
    lines.append("   " + "-+-".join("-" * width for width in col_widths))
    for row in clipped_rows:
        lines.append(format_row(row))

    return "\n".join(lines)


def _format_cost(value: float) -> str:
    """Return cost formatted with up to three decimals.

    Uses thousands separators, trims trailing zeros and the decimal point when
    not needed.

    Examples:
        0.1 -> "0.1"; 10.0 -> "10"; 1234.567 -> "1,234.567".
    """
    s = f"{float(value):,.3f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _format_duration(seconds: float) -> str:
    """Format seconds as a short ASCII duration for logs.

    Examples:
        0.123 -> "123.0 ms"; 1.234 -> "1.23 s"; 75.2 -> "1m 15.2s".
    """
    if seconds < 1.0:
        return f"{seconds * 1000.0:.1f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    minutes = int(seconds // 60)
    rem = seconds - minutes * 60
    return f"{minutes}m {rem:.1f}s"


def _collect_step_path_fields(step: Any) -> list[tuple[str, str]]:
    """Return (field, pattern) pairs for a step's node selector fields.

    Fields considered, when their value is a non-empty string:
    - `source` and `target`
    - names ending with "_path" or "_regex"

    Private fields (leading underscore) are skipped.
    """
    fields: list[tuple[str, str]] = []
    for key, value in step.__dict__.items():
        if key.startswith("_"):
            continue
        if not isinstance(value, str):
            continue
        if not value.strip():
            continue
        if (
            key in ("source", "target")
            or key.endswith("_path")
            or key.endswith("_regex")
        ):
            fields.append((key, value))
    return fields


def _summarize_pattern(pattern: str, net: Any) -> Dict[str, Any]:
    """Count the node groups and nodes that a selector pattern matches.

    Returns:
        Dict with ``pattern``, ``groups``, ``nodes``, ``enabled_nodes`` and
        ``labels`` (first five group labels), or ``pattern`` and ``error``
        when selection raises.
    """
    try:
        groups = net.select_node_groups_by_path(pattern)
    except Exception as exc:  # pragma: no cover (defensive)
        return {"pattern": pattern, "error": f"{type(exc).__name__}: {exc}"}

    labels = list(groups.keys())
    total_nodes = sum(len(nodes) for nodes in groups.values())
    enabled_nodes = sum(
        1 for nodes in groups.values() for nd in nodes if not nd.disabled
    )
    return {
        "pattern": pattern,
        "groups": len(labels),
        "nodes": total_nodes,
        "enabled_nodes": enabled_nodes,
        "labels": labels[:5],
    }


def _summarize_node_matches(step: Any, net: Any) -> Dict[str, Dict[str, Any]]:
    """Map each node selector field of a workflow step to its match summary."""
    summary: Dict[str, Dict[str, Any]] = {}
    fields = _collect_step_path_fields(step)
    if not fields:
        return summary
    for name, pattern in fields:
        summary[name] = _summarize_pattern(pattern, net)
    return summary


def _print_network_structure(
    network: Any, components_library: Any, detail: bool
) -> float:
    """Print network structure summary and return total enabled link capacity.

    Args:
        network: Network to summarize.
        components_library: Components library used for hierarchy analysis.
        detail: Print the full hierarchy, every violation, and per-node and
            per-link tables instead of previews.

    Returns:
        Total capacity across enabled links as a float. Returns 0.0 when
        there are no enabled links.
    """
    nodes = network.nodes
    links = network.links

    print(f"   Total Nodes: {len(nodes):,}")
    print(f"   Total Links: {len(links):,}")

    enabled_nodes = [n for n in nodes.values() if not n.disabled]
    disabled_nodes = [n for n in nodes.values() if n.disabled]
    enabled_links = [link for link in links.values() if not link.disabled]
    disabled_links = [link for link in links.values() if link.disabled]

    # Per-node attached capacity and enabled-link counts, computed in a single
    # O(E) pass shared by the detail-mode node table and the statistics block.
    # Self-loops contribute once per link, matching per-node match semantics.
    cap_by_node: Dict[str, float] = {}
    link_count_by_node: Dict[str, int] = {}
    for link in enabled_links:
        endpoints = (
            (link.source,) if link.source == link.target else (link.source, link.target)
        )
        for endpoint in endpoints:
            cap_by_node[endpoint] = cap_by_node.get(endpoint, 0.0) + float(
                link.capacity
            )
            link_count_by_node[endpoint] = link_count_by_node.get(endpoint, 0) + 1

    enabled_nodes_pct = (len(enabled_nodes) / len(nodes) * 100.0) if nodes else 0.0
    print(f"   Enabled Nodes: {len(enabled_nodes):,} ({enabled_nodes_pct:.1f}%)")
    if disabled_nodes:
        print(f"   Disabled Nodes: {len(disabled_nodes):,}")

    enabled_links_pct = (len(enabled_links) / len(links) * 100.0) if links else 0.0
    print(f"   Enabled Links: {len(enabled_links):,} ({enabled_links_pct:.1f}%)")
    if disabled_links:
        print(f"   Disabled Links: {len(disabled_links):,}")

    if nodes:
        pkg_logger = logging.getLogger("ngraph")
        original_level = pkg_logger.level
        pkg_logger.setLevel(logging.WARNING)
        explorer = None
        try:
            # Use non-strict validation so hierarchy is printable even with issues
            explorer = NetworkExplorer.explore_network(
                network, components_library, strict_validation=False
            )
            print("\n   Network Hierarchy:")
            print(
                "   Legend: counts include disabled nodes/links; cost/power are\n"
                "           aggregated from components if defined."
            )
            # Keep the printed tree shallow in non-detailed mode for readability
            explorer.print_tree(
                max_depth=2 if not detail else None,
                skip_leaves=not detail,
                detailed=detail,
                max_external_lines=8 if detail else 4,
                line_prefix="   ",
            )
        except Exception as e:
            print(f"   Network Hierarchy: Unable to analyze ({e})")
        finally:
            pkg_logger.setLevel(original_level)

        # Best effort: a failure here is logged at debug level and skipped.
        try:
            if explorer is not None:
                node_utils = explorer.get_node_utilization()
                link_issues = explorer.get_link_issues()

                cap_viol = [u for u in node_utils if u.capacity_violation]
                port_viol = [u for u in node_utils if u.ports_violation]

                print("\n   Validation & Hardware Utilization:")
                print(
                    f"     nodes with capacity violations: {len(cap_viol):,}; ports violations: {len(port_viol):,}"
                )

                if cap_viol:
                    cap_viol_sorted = sorted(
                        cap_viol,
                        key=lambda u: (u.capacity_utilization, u.node_name),
                        reverse=True,
                    )
                    top = cap_viol_sorted if detail else cap_viol_sorted[:10]
                    rows: list[list[str]] = []
                    for u in top:
                        rows.append(
                            [
                                u.node_name,
                                str(u.component_name or "-"),
                                f"{u.hw_count:g}",
                                f"{u.capacity_supported:,.1f}",
                                f"{u.attached_capacity_active:,.1f}",
                                f"{u.capacity_utilization:,.2f}",
                            ]
                        )
                    print("     Over-capacity nodes:")
                    tbl = _format_table(
                        [
                            "Node",
                            "Component",
                            "HW Cnt",
                            "Supported",
                            "Attached",
                            "Util",
                        ],
                        rows,
                        max_col_width=48,
                    )
                    print("\n".join(f"       {ln}" for ln in tbl.split("\n")))
                    if not detail and len(cap_viol_sorted) > len(top):
                        print(f"       ... and {len(cap_viol_sorted) - len(top)} more")

                if detail and port_viol:
                    port_sorted = sorted(
                        port_viol,
                        key=lambda u: (u.ports_utilization, u.node_name),
                        reverse=True,
                    )
                    rows2: list[list[str]] = []
                    for u in port_sorted:
                        rows2.append(
                            [
                                u.node_name,
                                str(u.component_name or "-"),
                                f"{u.hw_count:g}",
                                f"{u.ports_available:,.1f}",
                                f"{u.ports_used:,.1f}",
                                f"{u.ports_utilization:,.2f}",
                            ]
                        )
                    print("     Port capacity violations:")
                    tbl2 = _format_table(
                        [
                            "Node",
                            "Component",
                            "HW Cnt",
                            "Ports Avail",
                            "Ports Used",
                            "Util",
                        ],
                        rows2,
                        max_col_width=48,
                    )
                    print("\n".join(f"       {ln}" for ln in tbl2.split("\n")))

                if link_issues:
                    issues = link_issues if detail else link_issues[:10]
                    rows3: list[list[str]] = []
                    for iss in issues:
                        rows3.append(
                            [
                                iss.source,
                                iss.target,
                                f"{iss.capacity:,.1f}",
                                f"{iss.limit:,.1f}",
                                iss.reason,
                            ]
                        )
                    print(
                        f"     links exceeding per-end HW capacity: {len(link_issues):,}"
                    )
                    tbl3 = _format_table(
                        ["Source", "Target", "Capacity", "Limit", "Reason"], rows3
                    )
                    print("\n".join(f"       {ln}" for ln in tbl3.split("\n")))
                    if not detail and len(link_issues) > len(issues):
                        print(f"       ... and {len(link_issues) - len(issues)} more")
        except Exception as exc:
            logger.debug("Failed to display hardware utilization: %s", exc)

    if detail:
        if nodes:
            print("\n   Nodes:")
            node_rows = []
            for node_name in sorted(nodes.keys()):
                node = nodes[node_name]
                status = "disabled" if node.disabled else "enabled"

                node_capacity = cap_by_node.get(node_name, 0.0)
                node_link_count = link_count_by_node.get(node_name, 0)

                capacity_str = f"{node_capacity:,.0f}" if node_capacity > 0 else "0"

                node_rows.append(
                    [node_name, status, capacity_str, str(node_link_count)]
                )

            node_table = _format_table(
                ["Node", "Status", "Tot. Capacity", "Links"], node_rows
            )
            print(node_table)

        if links:
            print("\n   Links:")
            link_rows = []
            for _link_id, link in links.items():
                status = "disabled" if link.disabled else "enabled"
                capacity = f"{link.capacity:,.0f}"
                cost = _format_cost(link.cost)

                link_rows.append([link.source, link.target, status, capacity, cost])

            link_table = _format_table(
                ["Source", "Target", "Status", "Capacity", "Cost"], link_rows
            )
            print(link_table)

    total_enabled_link_capacity: float = 0.0
    if links:
        link_caps = [float(link.capacity) for link in enabled_links]
        if link_caps:
            total_enabled_link_capacity = float(sum(link_caps))
            print("\n   Link Capacity Statistics:")
            cap_table = _format_table(
                ["Metric", "Value"],
                [
                    ["Min", f"{min(link_caps):,.1f}"],
                    ["Max", f"{max(link_caps):,.1f}"],
                    ["Mean", f"{sum(link_caps) / len(link_caps):,.1f}"],
                    ["Median", f"{median(link_caps):,.1f}"],
                    ["Total", f"{total_enabled_link_capacity:,.1f}"],
                ],
            )
            print(cap_table)

    if nodes and links:
        print("\n   Node Capacity Statistics:")
        # Only include nodes with enabled links attached
        node_capacities = [cap_by_node[n] for n in nodes if cap_by_node.get(n, 0.0) > 0]

        if node_capacities:
            node_cap_table = _format_table(
                ["Metric", "Value"],
                [
                    ["Min", f"{min(node_capacities):,.1f}"],
                    ["Max", f"{max(node_capacities):,.1f}"],
                    ["Mean", f"{sum(node_capacities) / len(node_capacities):,.1f}"],
                    ["Median", f"{median(node_capacities):,.1f}"],
                    ["Total", f"{sum(node_capacities):,.1f}"],
                ],
            )
            print(node_cap_table)

    return total_enabled_link_capacity


def _print_risk_groups(network: Any, detail: bool) -> None:
    """Print the risk group count and names (first five unless ``detail``).

    Args:
        network: Network instance containing optional ``risk_groups`` mapping.
        detail: When True, list individual group names; otherwise show a preview.
    """
    print("\n3. RISK GROUPS")
    print("-" * 30)
    if network.risk_groups:
        print(f"   Total: {len(network.risk_groups)}")
        if detail:
            for rg_name, rg in network.risk_groups.items():
                status = "disabled" if rg.disabled else "enabled"
                print(f"     {rg_name} ({status})")
        else:
            risk_items = list(network.risk_groups.items())[:5]
            for rg_name, rg in risk_items:
                status = "disabled" if rg.disabled else "enabled"
                print(f"     {rg_name} ({status})")
            if len(network.risk_groups) > 5:
                remaining = len(network.risk_groups) - 5
                print(f"     ... and {remaining} more")
    else:
        print("   Total: 0")


def _print_components_library(components_library: Any, detail: bool) -> None:
    """Print the component count and names (first five unless ``detail``).

    Args:
        components_library: Components library with ``components`` mapping.
        detail: When True, list all component names; otherwise show a preview.
    """
    print("\n4. COMPONENTS LIBRARY")
    print("-" * 30)
    comp_count = len(components_library.components)
    print(f"   Total: {comp_count}")
    if components_library.components:
        if detail:
            for comp_name in components_library.components.keys():
                print(f"     {comp_name}")
        else:
            comp_items = list(components_library.components.keys())[:5]
            for comp_name in comp_items:
                print(f"     {comp_name}")
            if comp_count > 5:
                remaining = comp_count - 5
                print(f"     ... and {remaining} more")


def _print_failure_policies(failure_policy_set: Any, detail: bool) -> None:
    """Print failure policy set overview and optional per-mode details.

    Args:
        failure_policy_set: Collection of failure policies under ``policies``.
        detail: When True, also show the first three modes of each policy
            and the first three rules of each mode.
    """
    print("\n5. FAILURE POLICIES")
    print("-" * 30)
    policy_count = len(failure_policy_set.policies)
    print(f"   Total: {policy_count}")
    if failure_policy_set.policies:
        policy_items = list(failure_policy_set.policies.items())[:5]
        for policy_name, policy in policy_items:
            mode_count = len(policy.modes)
            print(
                f"     {policy_name}: {mode_count} mode{'s' if mode_count != 1 else ''}"
            )
            if detail and mode_count > 0:
                for mi, mode in enumerate(policy.modes[:3]):
                    rule_count = len(mode.rules)
                    print(
                        f"       {mi + 1}. weight={mode.weight:g} | {rule_count} rule{'s' if rule_count != 1 else ''}"
                    )
                    for ri, rule in enumerate(mode.rules[:3]):
                        extra = (
                            f" count={rule.count}"
                            if rule.mode == "choice"
                            else (
                                f" p={rule.probability}"
                                if rule.mode == "random"
                                else ""
                            )
                        )
                        print(f"           - {ri + 1}. {rule.scope} {rule.mode}{extra}")
                    if rule_count > 3:
                        print(f"           ... and {rule_count - 3} more rules")
        if policy_count > 5:
            remaining = policy_count - 5
            print(f"     ... and {remaining} more")


def _print_demand_sets(
    network: Any, ds: Any, detail: bool, total_enabled_link_capacity: float
) -> None:
    """Print demand sets summary and capacity-vs-demand ratio if available.

    Args:
        network: Network instance for node pattern summarization.
        ds: Demand set collection to summarize.
        detail: Whether to print detailed tables.
        total_enabled_link_capacity: Sum of capacities of enabled links.
    """
    print("\n6. DEMAND SETS")
    print("-" * 30)
    set_count = len(ds.sets)
    print(f"   Total: {set_count}")
    if not ds.sets:
        return

    # Totals across all sets print before the per-set breakdown.
    try:
        grand_total_demand = 0.0
        grand_demand_count = 0
        for demands in ds.sets.values():
            grand_demand_count += len(demands)
            for d in demands:
                grand_total_demand += float(d.volume)

        print("\n   Capacity vs Demand:")
        print(f"     enabled link capacity: {total_enabled_link_capacity:,.1f}")
        print(
            f"     total demand (all sets): {grand_total_demand:,.1f} ({grand_demand_count:,} demands)"
        )
        if total_enabled_link_capacity > 0.0 and grand_total_demand > 0.0:
            cap_per_demand = total_enabled_link_capacity / grand_total_demand
            demand_util = grand_total_demand / total_enabled_link_capacity
            print(f"     capacity/demand: {cap_per_demand:,.2f}x")
            print(f"     demand/capacity: {demand_util:,.2%}")
        else:
            print("     ratio: N/A (zero capacity or zero demand)")
    except Exception as exc:  # pragma: no cover (defensive)
        print(f"   Capacity vs Demand: unable to compute ({type(exc).__name__}: {exc})")

    set_items = list(ds.sets.items())[:5]
    for set_name, demands in set_items:
        demand_count = len(demands)
        total_volume = sum(d.volume for d in demands)
        print(
            f"     {set_name}: {demand_count} demand{'s' if demand_count != 1 else ''}"
        )

        src_counts: Dict[str, int] = {}
        tgt_counts: Dict[str, int] = {}
        pair_counts: Dict[tuple[str, str], Dict[str, float | int]] = {}
        for d in demands:
            # Handle both string and dict selectors
            src_key = d.source if isinstance(d.source, str) else str(d.source)
            tgt_key = d.target if isinstance(d.target, str) else str(d.target)
            src_counts[src_key] = src_counts.get(src_key, 0) + 1
            tgt_counts[tgt_key] = tgt_counts.get(tgt_key, 0) + 1
            key = (src_key, tgt_key)
            stats = pair_counts.setdefault(key, {"count": 0, "volume": 0.0})
            stats["count"] = int(stats["count"]) + 1
            stats["volume"] = float(stats["volume"]) + float(d.volume)

        if detail:
            print(f"       total demand: {total_volume:,.0f}")
            print(
                f"       unique source patterns: {len(src_counts)}; unique target patterns: {len(tgt_counts)}"
            )

            rows: list[list[str]] = []
            for (src_pat, tgt_pat), stats in list(pair_counts.items())[:10]:
                src_info = _summarize_pattern(src_pat, network)
                tgt_info = _summarize_pattern(tgt_pat, network)
                src_match = (
                    f"{src_info['groups']}g/{src_info['nodes']}n ({src_info['enabled_nodes']}e)"
                    if "error" not in src_info
                    else f"ERROR {src_info['error']}"
                )
                tgt_match = (
                    f"{tgt_info['groups']}g/{tgt_info['nodes']}n ({tgt_info['enabled_nodes']}e)"
                    if "error" not in tgt_info
                    else f"ERROR {tgt_info['error']}"
                )
                label_preview = ", ".join(src_info.get("labels", [])) or "-"
                rows.append(
                    [
                        src_pat,
                        tgt_pat,
                        str(int(stats["count"])),
                        f"{float(stats['volume']):,.0f}",
                        src_match,
                        tgt_match,
                        label_preview,
                    ]
                )
            if rows:
                print("       Demand patterns:")
                table = _format_table(
                    [
                        "Source Pattern",
                        "Target Pattern",
                        "Demands",
                        "Total",
                        "Src Match",
                        "Tgt Match",
                        "Src Labels",
                    ],
                    rows,
                )
                print("\n".join(f"         {line}" for line in table.split("\n")))

            try:
                top_n = 5
                sorted_demands = sorted(
                    demands,
                    key=lambda d: float(d.volume),
                    reverse=True,
                )[:top_n]
                if sorted_demands:
                    print("       Top demands (by offered volume):")
                    top_rows: list[list[str]] = []
                    for d in sorted_demands:
                        src = d.source if isinstance(d.source, str) else str(d.source)
                        tgt = d.target if isinstance(d.target, str) else str(d.target)
                        top_rows.append(
                            [
                                src,
                                tgt,
                                f"{float(d.volume):,.1f}",
                                str(d.priority),
                            ]
                        )
                    top_table = _format_table(
                        ["Source", "Target", "Offered", "Priority"],
                        top_rows,
                    )
                    print(
                        "\n".join(f"         {line}" for line in top_table.split("\n"))
                    )
            except Exception as exc:
                logger.debug("Failed to display top demands: %s", exc)

            if demands:
                for i, demand in enumerate(demands[:3]):
                    src = (
                        demand.source
                        if isinstance(demand.source, str)
                        else str(demand.source)
                    )
                    tgt = (
                        demand.target
                        if isinstance(demand.target, str)
                        else str(demand.target)
                    )
                    print(f"       {i + 1}. {src} -> {tgt} ({demand.volume})")
                if demand_count > 3:
                    print(f"       ... and {demand_count - 3} more demands")
        else:
            print(f"       total demand: {total_volume:,.0f}")
            print("       Node selection preview:")
            top_src = sorted(src_counts.items(), key=lambda kv: -kv[1])[:2]
            top_tgt = sorted(tgt_counts.items(), key=lambda kv: -kv[1])[:2]
            for name, _ in top_src:
                info = _summarize_pattern(name, network)
                if "error" in info:
                    print(f"         source {name}: ERROR {info['error']}")
                else:
                    print(
                        f"         source {name}: {info['groups']} groups, {info['nodes']} nodes ({info['enabled_nodes']} enabled)"
                    )
            for name, _ in top_tgt:
                info = _summarize_pattern(name, network)
                if "error" in info:
                    print(f"         target {name}: ERROR {info['error']}")
                else:
                    print(
                        f"         target {name}: {info['groups']} groups, {info['nodes']} nodes ({info['enabled_nodes']} enabled)"
                    )

    if set_count > 5:
        remaining = set_count - 5
        print(f"     ... and {remaining} more")


def _print_workflow_steps(scenario: Any, detail: bool, network: Any) -> None:
    """Print workflow steps with optional parameter and match details.

    Args:
        scenario: Scenario object providing the ``workflow`` sequence.
        detail: When True, include step parameters and node match tables.
        network: Network used to summarize node selection field matches.
    """
    print("\n7. WORKFLOW STEPS")
    print("-" * 30)
    step_count = len(scenario.workflow)
    print(f"   Total: {step_count}")
    if not scenario.workflow:
        return
    if not detail:
        workflow_rows = []
        for i, step in enumerate(scenario.workflow):
            step_name = step.name or f"step_{i + 1}"
            step_type = step.__class__.__name__
            determinism = "deterministic" if scenario.seed is not None else "random"
            workflow_rows.append([str(i + 1), step_name, step_type, determinism])

        # Column shows determinism (scenario-level), not the numeric step seed
        workflow_table = _format_table(
            ["#", "Name", "Type", "Determinism"], workflow_rows
        )
        print(workflow_table)

        print("\n   Node selection preview:")
        any_preview = False
        for i, step in enumerate(scenario.workflow):
            match_info = _summarize_node_matches(step, network)
            if not match_info:
                continue
            any_preview = True
            parts: list[str] = []
            for field_name, info in match_info.items():
                if "error" in info:
                    parts.append(f"{field_name}: ERROR {info['error']}")
                else:
                    parts.append(
                        f"{field_name}: {info['groups']} groups, {info['nodes']} nodes ({info['enabled_nodes']} enabled)"
                    )
            label = step.name or step.__class__.__name__
            print(f"     {i + 1}. {label}: " + "; ".join(parts))
        if not any_preview:
            print("     (no node selection fields in workflow steps)")
    else:
        for i, step in enumerate(scenario.workflow):
            step_name = step.name or f"step_{i + 1}"
            step_type = step.__class__.__name__
            determinism = "deterministic" if scenario.seed is not None else "random"
            seed_info = (
                f" (seed: {step.seed}, {determinism})"
                if step.seed is not None
                else f" ({determinism})"
            )
            print(f"     {i + 1}. {step_name} ({step_type}){seed_info}")

            step_dict = step.__dict__
            param_rows = []
            for key, value in step_dict.items():
                if key not in ["name", "seed"] and not key.startswith("_"):
                    shown = value.name if isinstance(value, Enum) else str(value)
                    param_rows.append([key, shown])

            if param_rows:
                param_table = _format_table(["Parameter", "Value"], param_rows)
                indented_table = "\n".join(
                    f"        {line}" for line in param_table.split("\n")
                )
                print(indented_table)

            match_info = _summarize_node_matches(step, network)
            if match_info:
                rows: list[List[str]] = []
                for field_name, info in match_info.items():
                    if "error" in info:
                        rows.append(
                            [
                                field_name,
                                info["pattern"],
                                "ERROR",
                                info["error"],
                            ]
                        )
                    else:
                        label_preview = (
                            ", ".join(info["labels"]) if info["labels"] else "-"
                        )
                        rows.append(
                            [
                                field_name,
                                info["pattern"],
                                f"{info['groups']} groups / {info['nodes']} nodes",
                                f"{info['enabled_nodes']} enabled; labels: {label_preview}",
                            ]
                        )
                if rows:
                    print("        Node matches:")
                    match_table = _format_table(
                        ["Field", "Pattern", "Matches", "Details"], rows
                    )
                    indented = "\n".join(
                        f"        {line}" for line in match_table.split("\n")
                    )
                    print(indented)
                if all(
                    (info.get("nodes", 0) == 0) and ("error" not in info)
                    for info in match_info.values()
                ):
                    print("        WARNING: No nodes matched for the given patterns")


def _inspect_scenario(path: Path, detail: bool = False) -> None:
    """Load and validate a scenario file, then print a sectioned summary.

    Exits with status 1 when the file is missing or fails to load.

    Args:
        path: Scenario YAML file.
        detail: Include full node and link tables, all names, and step
            parameters.
    """
    logger.info(f"Inspecting scenario from: {path}")
    _start_time = perf_counter()

    try:
        yaml_text = path.read_text()
        logger.info("✓ YAML file loaded")

        scenario = Scenario.from_yaml(yaml_text)
        logger.debug(
            "Scenario loaded: nodes=%d, links=%d, steps=%d, policies=%d, demand_sets=%d",
            len(scenario.network.nodes),
            len(scenario.network.links),
            len(scenario.workflow),
            len(scenario.failure_policy_set.policies),
            len(scenario.demand_set.sets),
        )
        logger.info("✓ Scenario validated")

        print("\n" + "=" * 60)
        print("NETGRAPH SCENARIO INSPECTION")
        print("=" * 60)

        try:
            network = scenario.network
            nodes = network.nodes
            links = network.links
            enabled_nodes = [n for n in nodes.values() if not n.disabled]
            enabled_links = [lk for lk in links.values() if not lk.disabled]
            en_nodes_pct = (len(enabled_nodes) / len(nodes) * 100.0) if nodes else 0.0
            en_links_pct = (len(enabled_links) / len(links) * 100.0) if links else 0.0
            total_enabled_capacity = float(
                sum(float(lk.capacity) for lk in enabled_links)
            )

            ds = scenario.demand_set
            set_count = len(ds.sets)
            total_demands = 0
            total_demand_volume = 0.0
            for demands in ds.sets.values():
                total_demands += len(demands)
                for d in demands:
                    total_demand_volume += float(d.volume)

            util = (
                (total_demand_volume / total_enabled_capacity)
                if total_enabled_capacity > 0
                else 0.0
            )

            rg_total = len(network.risk_groups)
            rg_disabled = (
                sum(1 for rg in network.risk_groups.values() if rg.disabled)
                if rg_total
                else 0
            )

            wf_steps = len(scenario.workflow)

            print("\nOVERVIEW")
            print("-" * 30)
            rows: List[List[str]] = [
                ["Nodes", f"{len(nodes):,}"],
                ["Links", f"{len(links):,}"],
                [
                    "Enabled",
                    f"{len(enabled_nodes):,} nodes ({en_nodes_pct:.1f}%), {len(enabled_links):,} links ({en_links_pct:.1f}%)",
                ],
                ["Capacity (enabled)", f"{total_enabled_capacity:,.1f}"],
                [
                    "Demand (all sets)",
                    f"{total_demand_volume:,.1f} ({total_demands:,} demands across {set_count} sets)",
                ],
                ["Utilization", f"{util:,.2%}"],
                ["Risk groups", f"{rg_total} total; {rg_disabled} disabled"],
                ["Workflow steps", f"{wf_steps}"],
            ]
            overview_table = _format_table(["Metric", "Value"], rows, max_col_width=64)
            print(overview_table)
        except Exception as exc:
            # Best effort; the numbered sections below still print.
            logger.debug("Failed to display overview section: %s", exc)

        print("\n1. SCENARIO METADATA")
        print("-" * 30)
        if scenario.seed is not None:
            print(f"   Seed: {scenario.seed} (deterministic)")
            print(
                "   All workflow step seeds are derived deterministically from scenario seed"
            )
        else:
            print("   Seed: None (non-deterministic)")
            print("   Workflow step seeds will be random on each run")

        print("\n2. NETWORK STRUCTURE")
        print("-" * 30)
        network = scenario.network
        total_enabled_link_capacity = _print_network_structure(
            network, scenario.components_library, detail
        )
        _print_risk_groups(network, detail)
        _print_components_library(scenario.components_library, detail)
        _print_failure_policies(scenario.failure_policy_set, detail)
        _print_demand_sets(
            network, scenario.demand_set, detail, total_enabled_link_capacity
        )
        _print_workflow_steps(scenario, detail, network)

        print("\n" + "=" * 60)
        print("INSPECTION COMPLETE")
        print("=" * 60)

        if scenario.workflow:
            print(
                f"\nReady to run with {len(scenario.workflow)} workflow step{'s' if len(scenario.workflow) != 1 else ''}"
            )
            print(f"Usage: python -m ngraph run {path}")
        else:
            print("\nNo workflow steps defined")

        _elapsed = perf_counter() - _start_time
        logger.info(f"Scenario inspection completed in {_format_duration(_elapsed)}")

    except FileNotFoundError:
        print(f"❌ ERROR: Scenario file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to inspect scenario: {e}")
        print("❌ ERROR: Failed to inspect scenario", file=sys.stderr)
        print(f"  {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


def _run_scenario(
    path: Path,
    results_override: Optional[Path],
    no_results: bool,
    stdout: bool,
    keys: Optional[list[str]] = None,
    profile: bool = False,
    profile_memory: bool = False,
    output_dir: Optional[Path] = None,
) -> None:
    """Run a scenario file and export results as JSON by default.

    Exits with status 1 on any failure.

    Args:
        path: Scenario YAML file.
        results_override: Optional explicit path for JSON results. When ``None``,
            the path is derived from the scenario name under ``output_dir``.
        no_results: Skip writing the results file.
        stdout: Print the results JSON to stdout.
        keys: Optional list of workflow step names to include. When ``None`` all steps are
            exported.
        profile: Profile each step with cProfile and print a report to stderr.
        profile_memory: Also record peak memory per step with tracemalloc.
            Only takes effect with ``profile``.
        output_dir: Base directory for derived output paths (results, profiles).
    """
    logger.info(f"Loading scenario from: {path}")
    _start_time = perf_counter()

    try:
        yaml_text = path.read_text()
        scenario = Scenario.from_yaml(yaml_text)
        if keys:
            step_names = [step.name for step in scenario.workflow]
            unknown = sorted(set(keys) - set(step_names))
            if unknown:
                raise ValueError(
                    f"Unknown step name(s) in --keys: {', '.join(unknown)}; "
                    f"workflow steps: {', '.join(step_names)}"
                )

        if profile:
            logger.info("Performance profiling enabled")
            profiler = PerformanceProfiler(track_memory=profile_memory)
            profiler.start_scenario()

            logger.info("Starting scenario execution with profiling")

            # FailureManager worker threads write per-worker .pstats files here.
            child_profile_dir = profiles_dir_for_run(path, output_dir)
            child_profile_dir.mkdir(parents=True, exist_ok=True)
            prev_profile_dir = os.environ.get("NGRAPH_PROFILE_DIR")
            os.environ["NGRAPH_PROFILE_DIR"] = str(child_profile_dir.resolve())
            logger.info(f"Worker profiles will be saved to: {child_profile_dir}")

            @contextmanager
            def _profile_step_hook(step: WorkflowStep) -> Iterator[None]:
                """Wrap step execution with profiling and worker-profile merge.

                Worker profiles are merged only after the profiled block exits
                normally; exceptions raised by the step propagate unchanged and
                skip the merge.
                """
                step_name = step.name or step.__class__.__name__
                with profiler.profile_step(step_name, step.__class__.__name__):
                    yield
                if child_profile_dir.exists():
                    profiler.merge_child_profiles(child_profile_dir, step_name)

            try:
                scenario.run(step_hook=_profile_step_hook)
            finally:
                # Restore the environment so later in-process runs do not
                # inherit profiling into a stale directory.
                if prev_profile_dir is None:
                    os.environ.pop("NGRAPH_PROFILE_DIR", None)
                else:
                    os.environ["NGRAPH_PROFILE_DIR"] = prev_profile_dir

            logger.info("Scenario execution completed")

            profiler.end_scenario()
            profiler.analyze_performance()

            # merge_child_profiles deletes the files it merges; remove leftovers.
            if child_profile_dir.exists():
                remaining_files = list(child_profile_dir.glob("*.pstats"))
                if remaining_files:
                    logger.debug(
                        f"Cleaning up {len(remaining_files)} remaining profile files"
                    )
                    for f in remaining_files:
                        try:
                            f.unlink()
                        except Exception as exc:
                            logger.debug("Failed to remove profile file %s: %s", f, exc)
                # Keep the profiles directory when an explicit output dir is used
                # to make artifact paths consistent and discoverable.
                if output_dir is None:
                    try:
                        child_profile_dir.rmdir()  # Remove dir if empty
                    except Exception as exc:
                        logger.debug("Failed to remove profiles dir: %s", exc)

            # Report goes to stderr so machine-readable stdout (--stdout)
            # stays pure JSON.
            reporter = PerformanceReporter(profiler.results)
            performance_report = reporter.generate_report()
            print("\n" + performance_report, file=sys.stderr)

        else:
            logger.info("Starting scenario execution")
            scenario.run()
            print("✅ Scenario execution completed", file=sys.stderr)

        if not no_results or stdout:
            logger.info("Serializing results to JSON")
            results_dict: Dict[str, Any] = scenario.results.to_dict()

            if keys:
                # Filter only the steps subsection; keep workflow/scenario intact
                steps_map = results_dict.get("steps", {})
                filtered_steps: Dict[str, Any] = {
                    step: steps_map[step] for step in keys
                }
                results_dict["steps"] = filtered_steps

            json_str = json.dumps(results_dict, indent=2)

            if not no_results:
                effective_output = results_path_for_run(
                    scenario_path=path,
                    output_dir=output_dir,
                    results_override=results_override,
                )

                ensure_parent_dir(effective_output)
                effective_output.write_text(json_str)
                print(f"✅ Results written to: {effective_output}", file=sys.stderr)

            if stdout:
                print(json_str)

        _elapsed = perf_counter() - _start_time
        logger.info(f"Scenario run completed in {_format_duration(_elapsed)}")

    except FileNotFoundError:
        logger.error(f"Scenario file not found: {path}")
        print(f"❌ ERROR: Scenario file not found: {path}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to run scenario: {type(e).__name__}: {e}")
        print(
            f"❌ ERROR: Failed to run scenario: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``ngraph`` command.

    Prints help and exits with status 0 when no arguments are given.

    Args:
        argv: Arguments without the program name. If ``None``,
            ``sys.argv[1:]`` is used.
    """
    parser = argparse.ArgumentParser(
        prog="ngraph",
        description="Run and analyze network scenarios.",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Show only warnings and errors in logs"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        title="Available commands",
        metavar="{run,inspect}",
        help="Available commands",
    )

    run_parser = subparsers.add_parser("run", help="Run a scenario")
    run_parser.add_argument("scenario", type=Path, help="Path to scenario YAML")
    run_parser.add_argument(
        "--results",
        "-r",
        type=Path,
        default=None,
        help=(
            "Export results to JSON file (default: <scenario_name>.results.json;"
            " placed under --output when provided)"
        ),
    )
    run_parser.add_argument(
        "--no-results",
        action="store_true",
        help="Disable results file generation",
    )
    run_parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print results to stdout",
    )
    run_parser.add_argument(
        "--keys",
        "-k",
        nargs="+",
        help="Filter output to these workflow step names",
    )
    run_parser.add_argument(
        "--profile",
        action="store_true",
        help="Profile the run and print a per-step CPU report to stderr",
    )
    run_parser.add_argument(
        "--profile-memory",
        action="store_true",
        help="Also track peak memory per step (via tracemalloc)",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Inspect and validate a scenario"
    )
    inspect_parser.add_argument("scenario", type=Path, help="Path to scenario YAML")
    inspect_parser.add_argument(
        "--detail",
        "-d",
        action="store_true",
        help="Show detailed information including complete node/link tables and step parameters",
    )
    run_parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help=(
            "Directory for the results file and, with --profile, the"
            " worker profile directory"
        ),
    )

    effective_args = sys.argv[1:] if argv is None else argv
    if not effective_args:
        parser.print_help()
        raise SystemExit(0)

    args = parser.parse_args(effective_args)
    if args.command == "run" and args.profile_memory and not args.profile:
        parser.error("--profile-memory requires --profile")

    setup_root_logger()
    if args.verbose:
        set_global_log_level(logging.DEBUG)
        logger.debug("Debug logging enabled")
    elif args.quiet:
        set_global_log_level(logging.WARNING)
    else:
        set_global_log_level(logging.INFO)

    if args.command == "run":
        _run_scenario(
            path=args.scenario,
            results_override=args.results,
            no_results=args.no_results,
            stdout=args.stdout,
            keys=args.keys,
            profile=args.profile,
            profile_memory=args.profile_memory,
            output_dir=args.output,
        )
    elif args.command == "inspect":
        _inspect_scenario(args.scenario, args.detail)


if __name__ == "__main__":
    main()
