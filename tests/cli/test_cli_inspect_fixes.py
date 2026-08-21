"""Regression tests for `ngraph inspect` output fixes.

Covers:
- Single-pass per-node capacity/link-count aggregation in
  ``_print_network_structure`` (previously O(V*E) nested scans), including
  self-loop semantics.
- "Top demands (by offered volume)" sorting by the ``volume`` attribute
  (previously keyed on a nonexistent ``demand`` attribute).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

from ngraph import cli
from ngraph.model.components import ComponentsLibrary
from ngraph.model.network import Link, Network, Node


def _capture_print(func, *args, **kwargs) -> str:
    """Run func with print patched and return the joined printed output."""
    with patch("sys.stdout", new=io.StringIO()), patch("builtins.print") as mprint:
        func(*args, **kwargs)
    return "\n".join(str(c.args[0]) for c in mprint.call_args_list if c.args)


def _table_rows(output: str, heading: str) -> list[list[str]]:
    """Extract table rows (split on '|') printed after a heading line."""
    lines = output.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.strip() == heading)
    rows: list[list[str]] = []
    in_table = False
    for ln in lines[start + 1 :]:
        stripped = ln.strip()
        if not stripped or set(stripped) <= {"-", "+"}:
            if in_table and not stripped:
                break
            continue  # blank before table or separator row
        if "|" in ln:
            in_table = True
            rows.append([cell.strip() for cell in ln.split("|")])
        elif in_table:
            break
    return rows


def _build_network_with_self_loop() -> Network:
    net = Network()
    for name in ("A", "B", "C"):
        net.add_node(Node(name=name))
    net.add_link(Link(source="A", target="B", capacity=10.0))
    net.add_link(Link(source="B", target="C", capacity=20.0))
    # Self-loop must contribute its capacity and link count exactly once
    net.add_link(Link(source="A", target="A", capacity=5.0))
    # Disabled links are excluded from capacity/link-count aggregation
    net.add_link(Link(source="A", target="C", capacity=100.0, disabled=True))
    return net


def test_node_table_capacity_and_link_counts_single_pass() -> None:
    net = _build_network_with_self_loop()
    out = _capture_print(
        cli._print_network_structure, net, ComponentsLibrary(), detail=True
    )

    rows = _table_rows(out, "Nodes:")
    # Drop header row
    data = {r[0]: r for r in rows if r[0] in ("A", "B", "C")}
    # A: 10 (A-B) + 5 (self-loop counted once); 2 enabled links
    assert data["A"][2] == "15"
    assert data["A"][3] == "2"
    # B: 10 (A-B) + 20 (B-C); 2 enabled links
    assert data["B"][2] == "30"
    assert data["B"][3] == "2"
    # C: 20 (B-C); the disabled A-C link must not count
    assert data["C"][2] == "20"
    assert data["C"][3] == "1"


def test_node_capacity_statistics_match_naive_aggregation() -> None:
    net = _build_network_with_self_loop()
    out = _capture_print(
        cli._print_network_structure, net, ComponentsLibrary(), detail=False
    )

    rows = _table_rows(out, "Node Capacity Statistics:")
    stats = {r[0]: r[1] for r in rows if len(r) >= 2}
    # Per-node capacities: A=15, B=30, C=20
    assert stats["Min"] == "15.0"
    assert stats["Max"] == "30.0"
    assert stats["Mean"] == "21.7"
    assert stats["Median"] == "20.0"
    assert stats["Total"] == "65.0"


def test_node_capacity_statistics_exclude_isolated_nodes() -> None:
    net = Network()
    for name in ("A", "B", "ISOLATED"):
        net.add_node(Node(name=name))
    net.add_link(Link(source="A", target="B", capacity=8.0))

    out = _capture_print(
        cli._print_network_structure, net, ComponentsLibrary(), detail=False
    )

    rows = _table_rows(out, "Node Capacity Statistics:")
    stats = {r[0]: r[1] for r in rows if len(r) >= 2}
    # Only A and B have enabled links; ISOLATED must not drag Min to 0
    assert stats["Min"] == "8.0"
    assert stats["Total"] == "16.0"


def test_inspect_top_demands_sorted_by_volume(tmp_path: Path) -> None:
    scenario_file = tmp_path / "top_demands.yaml"
    scenario_file.write_text(
        """
seed: 1
network:
  nodes:
    A: {}
    B: {}
    C: {}
  links:
    - source: A
      target: B
      capacity: 1000
    - source: B
      target: C
      capacity: 1000
demands:
  default:
    - source: "^A$"
      target: "^B$"
      volume: 10
    - source: "^B$"
      target: "^C$"
      volume: 300
    - source: "^A$"
      target: "^C$"
      volume: 50
workflow:
  - type: BuildGraph
"""
    )

    with patch("sys.stdout", new=io.StringIO()), patch("builtins.print") as mprint:
        cli.main(["inspect", str(scenario_file), "--detail"])

    out = "\n".join(str(c.args[0]) for c in mprint.call_args_list if c.args)
    assert "Top demands (by offered volume):" in out

    rows = _table_rows(out, "Top demands (by offered volume):")
    offered = [
        float(r[2].replace(",", "")) for r in rows if r[2] not in ("Offered", "")
    ]
    assert offered == [300.0, 50.0, 10.0]
