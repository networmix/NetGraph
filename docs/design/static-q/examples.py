"""Executable examples for the static-q rule and its proof boundaries.

Usage (from this directory, with NetGraph's environment for the native mode):
    python -B examples.py reference   expected values (derived by hand, written below) against reference.py
    python -B examples.py plants      plant wrong values into every expected value: each must fail
    python -B examples.py mutants     break one rule of the reference at a time: some example must disagree
    python -B examples.py ngraph      expected values against the current NetGraph checkout

One line per checked value, plant or example, then a SUMMARY line. Exit status 1 on any failure. The expected values
below are literals derived by hand (README.md and PROOFS.md give the derivations); the reference never imports
NetGraph. Keys starting with `reading_` are the numbers a plausible wrong reading of a rule gives; they must differ.
"""

from __future__ import annotations

import gzip
import sys
from fractions import Fraction as F
from pathlib import Path
from typing import Any

import boundaries
import reference as ref

HERE = Path(__file__).resolve().parent
SC = HERE / "scenarios"
DCBB_YAML = SC / "dcbb12.yml.gz"
DCBB_YAML_SHA256 = "33bd5af6058e05d0d3b4572612a60467f9a4cf2159f7ed981cad55c7293bc9be"
DCBB_GRAPH = HERE / "fixtures" / "dcbb12.graph.json.gz"
DCBB_GRAPH_SHA256 = "7634843751ef4cbce69bb35e6b424a13c88554186bfe157fa74382ee7b702c08"
P = F(1, 1000)


def scenario_bytes(path: Path) -> bytes:
    payload = path.read_bytes()
    return gzip.decompress(payload) if path.suffix == ".gz" else payload


# ---------------------------------------------------------------- expected values, derived by hand

EXPECTED: dict[str, dict[str, Any]] = {
    "readme": {  # 12 nodes, 18 links: L = 48; one combine ECMP demand: Gamma = 48/4 + 2 = 14
        "L": 48,
        "split_count": F(14),
        "q_exponent": -9,
        "limited_by": "split_count",
        "achieved_precision": F(7, 12800),
        "target_met": True,
        "reading_links_once_q_exponent": -8,
        "baseline_delivered_units": 51200,
        "msd_alpha": F(1),
        "fluid_msd_alpha": F(1),
    },
    "square_mesh": {  # 4 nodes, 6 links: L = 16; 12 pair leaves: Gamma = 12 (16/4 + 2) = 72
        "L": 16,
        "split_count": F(72),
        "q_exponent": -17,
        "limited_by": "split_count",
        "achieved_precision": F(9, 16384),
        "target_met": True,
        "reading_declarations_q_exponent": -13,
        "msd_alpha": F(1),
        "fluid_msd_alpha": F(1),
    },
    "fanin50": {  # 54 nodes, 153 links: L = 360; Gamma = 92; c_min = 1
        "L": 360,
        "split_count": F(92),
        "q_exponent": -17,
        "limited_by": "split_count",
        "achieved_precision": F(23, 32768),
        "target_met": True,
        "delivered_units": 393172,
        "fluid_delivered": F(3),
        "reading_local_split_bound_delivered_units": 3024,  # 0.25's q = 2^-10
        "msd_alpha": F(491, 16384),
        "fluid_msd_alpha": F(3, 100),
    },
    "docs_paths": {  # 6 nodes, 7 links: L = 20; lossless set k = 1, lossy set not counted: Gamma = 7
        "L": 20,
        "split_count": F(7),
        "q_exponent": -12,
        "limited_by": "split_count",
        "achieved_precision": F(7, 8192),
        "target_met": True,
        "delivered_units": 32769,
        "fluid_delivered": F(8),
        "reading_local_split_bound_delivered_units": 2049,  # 0.25's q = 2^-8
    },
    "docs_paths_q1": {  # declared q = 1
        "q_exponent": 0,
        "mode": "manual",
        "limited_by": "declared",
        "achieved_precision": F(7, 2),
        "target_met": False,
        "delivered_units": 9,
        "fluid_delivered": F(8),
    },
    "tunnel_threshold": {  # L = 6; no in-scope demand (floor 3.5) plus 2 tunnels: Gamma = 5.5
        "L": 6,
        "split_count": F(11, 2),
        "q_exponent": -11,
        "limited_by": "split_count",
        "achieved_precision": F(11, 16384),
        "target_met": True,
        "delivered_units": 16385,
        "exact_delivered": F(6),
        "reading_tunnels_not_counted_q_exponent": -10,
        "reading_tunnels_not_counted_delivered_units": 8192,
    },
    "ordered_residual": {  # L = 4; two demands: Gamma = 6; c_min = 10
        "L": 4,
        "split_count": F(6),
        "q_exponent": -10,
        "limited_by": "split_count",
        "achieved_precision": F(3, 5120),
        "target_met": True,
        "first_delivered_units": 10240,
        "second_delivered_units": 0,
        "fluid_second_delivered": F(10) - F(9.9999),
    },
    "range": {  # input bound 2^-19 is out of range (four directed edges of 2^60 units sum to 2^62)
        "L": 6,
        "split_count": F(7, 2),
        "q_exponent": -18,
        "limited_by": "range",
        "achieved_precision": F(2) ** -19 / F(0.001),
        "target_met": False,
        "delivered_units": 262,
        "reading_count_only_precision": F(7, 2**60),
    },
    "te_link": {  # L = 4; a TE question only: floor Gamma = 3; 1.00015 x 4096 = 4096.61 rounds up to 4097
        "L": 4,
        "split_count": F(3),
        "q_exponent": -12,
        "limited_by": "split_count",
        "achieved_precision": 3 * F(2) ** -12 / F(1.00015),
        "target_met": True,
        "max_flow_units": 4097,
        "physical_max_flow": F(1.00015),
    },
    "input_rounding": {  # L = 4, Gamma = 3, count bound 2^-5; input bound 2 x 0.001 x 1.0156 -> 2^-9
        "L": 4,
        "split_count": F(3),
        "q_exponent": -9,
        "limited_by": "input",
        "achieved_precision": F(2) ** -10 / F(1.0156),
        "target_met": True,
        "delivered_units": 520,
        "reading_capacities_only_q_exponent": -5,
        "reading_capacities_only_delivered_units": 32,
    },
    "tunnels_p01": {  # p = 0.1; 14 nodes, 13 links: L = 40; 12 heads x 16 tunnels: Gamma = 12 + 192 = 204
        "L": 40,
        "split_count": F(204),
        "q_exponent": -8,
        "limited_by": "split_count",
        "achieved_precision": F(51, 640),
        "target_met": True,
        "delivered_units": 2560,
        "reading_tunnels_not_counted_q_exponent": -4,
    },
    "zero_member": {  # L = 6, Gamma = 3.5, c_min = 5 (the positive capacity)
        "L": 6,
        "split_count": F(7, 2),
        "q_exponent": -10,
        "limited_by": "split_count",
        "achieved_precision": F(7, 10240),
        "target_met": True,
        "delivered_units": 1,
        "fluid_delivered": F(0),
    },
    "dcbb12": {  # 3077 nodes, 20992 links: L = 45061; two combine ECMP demands: Gamma = 45069/2
        "L": 45061,
        "split_count": F(45069, 2),
        "q_exponent": -16,
        "limited_by": "split_count",
        "achieved_precision": F(45069, 52428800),
        "target_met": True,
        "reading_links_once_q_exponent": -15,
        "fluid_msd_alpha": F(1152, 125),
        "msd_alpha_in": frozenset({F(1179, 128), F(295, 32), F(589, 64)}),
    },
}

EXPECTED.update(boundaries.EXPECTED)

# ---------------------------------------------------------------- the reference's values


def readme_net():
    sites = ("site1", "site2")
    nodes = [f"{s}/spine/spine{i}" for s in sites for i in (1, 2)] + [
        f"{s}/leaf/leaf{i}" for s in sites for i in range(1, 5)
    ]
    links = [
        (f"{s}/leaf/leaf{i}", f"{s}/spine/spine{j}", 100, 1)
        for s in sites
        for i in range(1, 5)
        for j in (1, 2)
    ]
    links += [(f"site1/spine/spine{j}", f"site2/spine/spine{j}", 50, 1) for j in (1, 2)]
    return ref.Net(nodes, links)


def square_net():
    caps = {
        ("N1", "N2"): 2,
        ("N1", "N3"): 1,
        ("N1", "N4"): 2,
        ("N2", "N3"): 2,
        ("N2", "N4"): 1,
        ("N3", "N4"): 2,
    }
    return ref.Net(
        ["N1", "N2", "N3", "N4"], [(a, b, c, 1) for (a, b), c in caps.items()]
    )


def fanin_net():
    s = [f"S{i:02d}" for i in range(50)]
    links = [(x, f"X{j}", 1000, 1) for x in s for j in (1, 2, 3)] + [
        (f"X{j}", "T", 1, 1) for j in (1, 2, 3)
    ]
    return ref.Net(s + ["X1", "X2", "X3", "T"], links), s


def paths_net():
    links = [
        ("A", "B", 100, 1),
        ("B", "D", 100, 2),
        ("A", "C", 100, 1),
        ("C", "X", 2, 1),
        ("C", "Y", 100, 1),
        ("X", "D", 100, 1),
        ("Y", "D", 100, 1),
    ]
    return ref.Net(["A", "B", "C", "X", "Y", "D"], links)


def msd_search(feasible, tolerance, start=F(1), growth=F(2)):
    """NetGraph's documented search driven by an exact feasibility function (bracket, then exact midpoints)."""
    a = start
    if feasible(a):
        lo = a
        while feasible(a * growth):
            a *= growth
            lo = a
        hi = a * growth
    else:
        hi = a
        while not feasible(a / growth):
            a /= growth
            hi = a
        lo = a / growth
    while hi - lo > tolerance:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if feasible(mid) else (lo, mid)
    return lo


def units(x: F, q: F) -> int:
    return (x / q + F(1, 2)).__floor__()


def compute(name):
    """The reference's value for every key of EXPECTED[name]."""
    if name in boundaries.EXPECTED:
        return boundaries.compute(name, ref)
    out: dict[str, Any] = {}
    if name == "readme":
        net = readme_net()
        src = [n for n in net.nodes if n.startswith("site1/leaf")]
        dst = [n for n in net.nodes if n.startswith("site2/leaf")]
        e, g, lim, ach, ok = ref.rule(net.L, [(1, 0)], net.c_min(), 50)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        out["reading_links_once_q_exponent"] = ref.rule(
            len(net.nodes) + len(net.links), [(1, 0)], net.c_min(), 50
        )[0]
        q = F(2) ** e
        prog = ref.Program(net, src, dst)
        cap = ref.units_of(net, q)
        out["baseline_delivered_units"] = ref.whole_units_lossless(
            prog, q, units(F(100), q)
        )
        out["msd_alpha"] = msd_search(
            lambda a: prog.fits(units(a * 100, q), cap), F(1, 100)
        )
        out["fluid_msd_alpha"] = ref.fluid_msd(net, [(src, dst, 100)])
    elif name == "square_mesh":
        net = square_net()
        pairs = [([a], [b], F(1)) for a in net.nodes for b in net.nodes if a != b]
        e, g, lim, ach, ok = ref.rule(net.L, [(len(pairs), 0)], net.c_min(), 1)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        out["reading_declarations_q_exponent"] = ref.rule(
            net.L, [(1, 0)], net.c_min(), 1
        )[0]
        q = F(2) ** e
        cap = ref.units_of(net, q)
        progs = [ref.Program(net, s, t) for s, t, _ in pairs]

        def fits(a):  # every pair delivers its request: loads add (Theorem B's lemma)
            load = dict.fromkeys(cap, 0)
            for prog, (_, _, v) in zip(progs, pairs, strict=False):
                r = units(a * v, q)
                inflow = dict.fromkeys(prog.order, 0)
                inflow[prog.roster[0]] = r
                for u in prog.order:
                    if u in prog.targets or not inflow[u]:
                        continue
                    m = prog.members[u]
                    qq, rr = divmod(inflow[u], len(m))
                    for i, edge in enumerate(m):
                        load[edge[5]] += qq + (i < rr)
                        inflow[edge[1]] += qq + (i < rr)
            return all(load[i] <= cap[i] for i in cap)

        out["msd_alpha"] = msd_search(fits, F(5, 100))
        out["fluid_msd_alpha"] = ref.fluid_msd(net, pairs)
    elif name == "fanin50":
        net, src = fanin_net()
        e, g, lim, ach, ok = ref.rule(net.L, [(1, 0)], net.c_min(), 1)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        q = F(2) ** e
        prog = ref.Program(net, src, ["T"])
        cap = ref.units_of(net, q)
        out["delivered_units"] = ref.whole_units_lossless(prog, q, units(F(100), q))
        out["fluid_delivered"] = prog.x_c()
        out["reading_local_split_bound_delivered_units"] = ref.whole_units_lossless(
            prog, F(2) ** -10, 100 * 1024
        )
        out["msd_alpha"] = msd_search(
            lambda a: prog.fits(units(a * 100, q), cap), F(1, 10**4)
        )
        out["fluid_msd_alpha"] = ref.fluid_msd(net, [(src, ["T"], 100)])
    elif name in ("docs_paths", "docs_paths_q1"):
        net = paths_net()
        prog = ref.Program(net, ["A"], ["D"])
        if name == "docs_paths":
            e, g, lim, ach, ok = ref.rule(net.L, [(1, 0), (0, 0)], net.c_min(), 2)
            out.update(
                L=net.L,
                split_count=g,
                q_exponent=e,
                limited_by=lim,
                achieved_precision=ach,
                target_met=ok,
            )
            out["reading_local_split_bound_delivered_units"] = ref.whole_units_lossless(
                prog, F(2) ** -8, 12 * 256
            )
        else:
            g = ref.split_count(net.L, 1, 0)
            e = 0
            out.update(
                q_exponent=0,
                mode="manual",
                limited_by="declared",
                achieved_precision=ref.achieved(0, g, 2, 2),
                target_met=ref.achieved_ok(0, g, 2, 2),
            )
        q = F(2) ** e
        out["delivered_units"] = ref.whole_units_lossless(prog, q, units(F(12), q))
        out["fluid_delivered"] = prog.x_c()
    elif name == "tunnel_threshold":
        L = 2 + 4
        e, g, lim, ach, ok = ref.rule(L, [(0, 2)], 4, 4)
        out.update(
            L=L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        volume = F(8.000244140625)

        def t1(q):
            """Two tunnels set up in order on the first link with enough unreserved bandwidth; each asks its round-
            robin share of the rounded volume; then the largest round-robin total that fits on the up tunnels."""
            caps = [units(F(6), q), units(F(4), q)]
            request = units(volume, q)
            asks = [request // 2 + (i < request % 2) for i in range(2)]
            free, up = list(caps), []
            for ask in asks:
                link = next((j for j in range(2) if free[j] >= ask), None)
                if link is not None:
                    free[link] -= ask
                    up.append(link)
            best = 0
            for total in range(request + 1):
                loads = [0, 0]
                for i, link in enumerate(up):
                    loads[link] += total // len(up) + (i < total % len(up))
                if all(loads[j] <= caps[j] for j in range(2)):
                    best = total
            return best

        out["delivered_units"] = t1(F(2) ** e)
        # Exact amounts: each tunnel asks volume/2 > 4; the second does not fit; the first carries the link of 6.
        out["exact_delivered"] = min(volume, F(6)) if volume / 2 > 4 else volume
        e2 = ref.rule(L, [(0, 0)], 4, 4)[0]
        out["reading_tunnels_not_counted_q_exponent"] = e2
        out["reading_tunnels_not_counted_delivered_units"] = t1(F(2) ** e2)
    elif name == "ordered_residual":
        net = ref.Net(["A", "B"], [("A", "B", 10, 1)])
        e, g, lim, ach, ok = ref.rule(net.L, [(2, 0)], 10, 9.9999)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        q = F(2) ** e
        cap = units(F(10), q)
        first = min(units(F(9.9999), q), cap)
        out["first_delivered_units"] = first
        out["second_delivered_units"] = min(units(F(10), q), cap - first)
        out["fluid_second_delivered"] = ref.fluid_ordered(
            net, [(["A"], ["B"], 9.9999), (["A"], ["B"], 10)], 1
        )[1]
    elif name == "range":
        net = ref.Net(["A", "B"], [("A", "B", 2**41, 1), ("A", "B", 2**41, 1)])

        def range_ok(e):
            q = F(2) ** e
            return (
                sum(units(edge[2], q) for edge in net.edges) < 2**62
                and units(F(0.001), q) < 2**62
            )

        e, g, lim, ach, ok = ref.rule(net.L, [(1, 0)], 2**41, 0.001, range_ok=range_ok)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        out["delivered_units"] = units(F(0.001), F(2) ** e)
        out["reading_count_only_precision"] = F(2) ** e * g / F(2**41)
    elif name == "te_link":
        net = ref.Net(["A", "B"], [("A", "B", 1.00015, 1)])
        e, g, lim, ach, ok = ref.rule(net.L, [(0, 0)], net.c_min(), 1.00015)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        cap = ref.units_of(net, F(2) ** e)
        out["max_flow_units"] = cap[
            0
        ]  # one link: the maximum flow is its rounded capacity (edge A->B)
        out["physical_max_flow"] = net.c_min()
    elif name == "input_rounding":
        L = 2 + 2
        e, g, lim, ach, ok = ref.rule(L, [(1, 0)], 100, 1.0156)
        out.update(
            L=L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        out["delivered_units"] = units(F(1.0156), F(2) ** e)
        e2 = ref.rule(L, [(1, 0)], 100, 100)[0]
        out["reading_capacities_only_q_exponent"] = e2
        out["reading_capacities_only_delivered_units"] = units(F(1.0156), F(2) ** e2)
    elif name == "tunnels_p01":
        L = 14 + 2 * 13
        e, g, lim, ach, ok = ref.rule(L, [(0, 12 * 16)], 10, 10, p=F(1, 10))
        out.update(
            L=L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        q = F(2) ** e
        size = units(F(10), q) // (
            12 * 16
        )  # every tunnel crosses H-T: the capacity-limited common size
        out["delivered_units"] = (
            min(units(F(10), q), units(F(1000), q)) if size >= 1 else 0
        )
        out["reading_tunnels_not_counted_q_exponent"] = ref.rule(
            L, [(0, 0)], 10, 10, p=F(1, 10)
        )[0]
    elif name == "zero_member":
        net = ref.Net(["A", "B"], [("A", "B", 5, 1), ("A", "B", 0, 1)])
        e, g, lim, ach, ok = ref.rule(net.L, [(1, 0)], net.c_min(), 5)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        prog = ref.Program(net, ["A"], ["B"])
        q = F(2) ** e
        out["delivered_units"] = ref.whole_units_lossless(prog, q, units(F(5), q))
        out["fluid_delivered"] = prog.x_c()
    elif name == "dcbb12":
        net = dcbb_net()
        demands = dcbb_demands(net)
        e, g, lim, ach, ok = ref.rule(net.L, [(2, 0)], net.c_min(), 400)
        out.update(
            L=net.L,
            split_count=g,
            q_exponent=e,
            limited_by=lim,
            achieved_precision=ach,
            target_met=ok,
        )
        out["reading_links_once_q_exponent"] = ref.rule(
            len(net.nodes) + len(net.links), [(2, 0)], net.c_min(), 400
        )[0]
        a = ref.fluid_msd(net, demands)
        out["fluid_msd_alpha"] = a
        out["msd_alpha_in"] = frozenset(ref.msd_outputs(a, ref.msd_band(P), F(1, 100)))
    return out


_DCBB: dict[str, Any] = {}


def dcbb_net():
    import hashlib

    if "net" not in _DCBB:
        digest = hashlib.sha256(DCBB_GRAPH.read_bytes()).hexdigest()
        if digest != DCBB_GRAPH_SHA256:
            raise SystemExit(f"fixture {DCBB_GRAPH} changed: {digest}")
        _DCBB["net"] = ref.Net.from_json(ref.load_json_gz(DCBB_GRAPH))
    return _DCBB["net"]


def dcbb_demands(net):
    import re

    pods = [n for n in net.nodes if re.match(r"^abc1/pod.*/rsw$", n)]
    hub = [n for n in net.nodes if re.match(r"^xyz1/mp1/rsw$", n)]
    return [(pods, hub, 100000.0), (hub, pods, 100000.0)]


# ---------------------------------------------------------------- comparison, plants, NetGraph


def matches(key, expected, actual):
    if key.endswith("_in"):
        return isinstance(actual, frozenset) and actual == expected
    return type(expected) is type(actual) and expected == actual


def check_reference():
    bad = n = 0
    for name, values in EXPECTED.items():
        actual = compute(name)
        for key, value in values.items():
            n += 1
            ok = key in actual and matches(key, value, actual[key])
            bad += not ok
            print(
                f"{'ok  ' if ok else 'FAIL'} {name}.{key}: expected {show(value)} reference {show(actual.get(key))}"
            )
        for key in values:
            if key.startswith("reading_") and key.endswith("q_exponent"):
                differs = values[key] != values["q_exponent"]
                n += 1
                bad += not differs
                print(
                    f"{'ok  ' if differs else 'FAIL'} {name}.{key} differs from q_exponent: {values[key]} vs {values['q_exponent']}"
                )
    print(f"SUMMARY examples reference: {n - bad}/{n} values agree")
    return bad


def plants_for(value):
    if isinstance(value, bool):
        return [not value, None, str(value)]
    if isinstance(value, int):
        return [value + 1, value - 1, None, float(value), str(value)]
    if isinstance(value, F):
        return [value + F(1, 2**70), value + 1, None, float(value), str(value)]
    if isinstance(value, frozenset):
        return [frozenset(sorted(value)[1:]), value | {F(0)}, frozenset(), None]
    if isinstance(value, tuple):
        return [value[:-1], value + (0,), None, list(value)]
    return [value + "_", None, 0]


def check_plants():
    caught = total = bad = 0
    for name, values in EXPECTED.items():
        actual = compute(name)
        for key, value in values.items():
            if not matches(key, value, actual[key]):
                bad += 1
                print(f"FAIL {name}.{key}: the clean value already fails")
                continue
            for plant in plants_for(value):
                total += 1
                hit = not matches(key, plant, actual[key])
                caught += hit
                print(
                    f"{'caught' if hit else 'MISSED'} {name}.{key} planted {show(plant)}"
                )
    print(f"SUMMARY examples plants: {caught}/{total} plants caught")
    return total - caught + bad


def check_mutants():
    """Break one rule of the reference at a time; some example must then disagree with the hand values."""
    original = {
        name: getattr(ref, name)
        for name in ("split_count", "achieved", "rule", "units_of", "msd_band")
    }
    orig_fits = ref.Program.fits

    def links_once(self):
        return len(self.nodes) + len(self.links)

    def rr_last(self, total, units):
        inflow = dict.fromkeys(self.order, 0)
        q, r = divmod(total, len(self.roster))
        for i, s in enumerate(self.roster):
            inflow[s] += q + (i >= len(self.roster) - r)
        for u in self.order:
            if u in self.targets or not inflow[u]:
                continue
            m = self.members[u]
            qq, rr = divmod(inflow[u], len(m))
            for i, e in enumerate(m):
                x = qq + (i >= len(m) - rr)
                if x > units[e[5]]:
                    return False
                inflow[e[1]] += x
        return True

    mutants = [
        (
            "L counts each link once",
            lambda: setattr(ref.Net, "L", property(links_once)),
            lambda: setattr(
                ref.Net,
                "L",
                property(lambda self: len(self.nodes) + 2 * len(self.links)),
            ),
        ),
        (
            "no floor of one question",
            lambda: setattr(ref, "split_count", lambda L, k, t: k * (F(L, 4) + 2) + t),
            lambda: setattr(ref, "split_count", original["split_count"]),
        ),
        (
            "tunnels not counted",
            lambda: setattr(
                ref, "split_count", lambda L, k, t: max(k, 1) * (F(L, 4) + 2)
            ),
            lambda: setattr(ref, "split_count", original["split_count"]),
        ),
        (
            "+1 instead of +2 per demand",
            lambda: setattr(
                ref, "split_count", lambda L, k, t: max(k, 1) * (F(L, 4) + 1) + t
            ),
            lambda: setattr(ref, "split_count", original["split_count"]),
        ),
        (
            "achieved precision without input rounding",
            lambda: setattr(
                ref,
                "achieved",
                lambda e, g, c, v: F(2) ** e * g / ref.exact(c)
                if c is not None
                else None,
            ),
            lambda: setattr(ref, "achieved", original["achieved"]),
        ),
        (
            "units rounded down",
            lambda: setattr(
                ref,
                "units_of",
                lambda net, q: {e[5]: (e[2] / q).__floor__() for e in net.edges},
            ),
            lambda: setattr(ref, "units_of", original["units_of"]),
        ),
        (
            "remainder to the last member",
            lambda: setattr(ref.Program, "fits", rr_last),
            lambda: setattr(ref.Program, "fits", orig_fits),
        ),
        (
            "MSD band without the binary64 term",
            lambda: setattr(
                ref, "msd_band", lambda p: original["msd_band"](p) - F(2) ** -52
            ),
            lambda: setattr(ref, "msd_band", original["msd_band"]),
        ),
    ]
    killed = 0
    for name, on, off in mutants:
        on()
        try:
            killers = []
            for example, values in EXPECTED.items():
                try:
                    actual = compute(example)
                except Exception as exc:  # a crash also kills the mutant
                    killers.append(f"{example} ({type(exc).__name__})")
                    continue
                if any(
                    key not in actual or not matches(key, v, actual[key])
                    for key, v in values.items()
                ):
                    killers.append(example)
        finally:
            off()
        killed += bool(killers)
        print(
            f"{'killed' if killers else 'SURVIVED'} mutant '{name}' by {', '.join(killers) if killers else 'nothing'}"
        )
    print(f"SUMMARY examples mutants: {killed}/{len(mutants)} reference mutants killed")
    return len(mutants) - killed


def show(v):
    if isinstance(v, frozenset):
        return "{" + ", ".join(str(x) for x in sorted(v)) + "}"
    return str(v)


def check_ngraph():
    """Compare hand-derived expectations with this checkout and its native engine."""
    import hashlib
    import importlib.metadata
    import signal

    import _netgraph_core
    import netgraph_core
    import yaml

    import ngraph
    from ngraph import prepare, run
    from ngraph.scenario import Scenario

    checkout = HERE.parents[2]
    assert Path(ngraph.__file__).resolve() == checkout / "ngraph" / "__init__.py"
    for module in (ngraph, netgraph_core, _netgraph_core):
        assert module.__file__ is not None
        origin = Path(module.__file__).resolve()
        if module is not ngraph:
            assert origin.is_relative_to(Path(sys.prefix).resolve()), origin
        digest = hashlib.sha256(origin.read_bytes()).hexdigest()
        print(f"IDENTITY {module.__name__}: {origin} sha256={digest}")
    assert importlib.metadata.version("ngraph") == "0.26.0"
    assert importlib.metadata.version("netgraph-core") == "0.12.0"
    print("IDENTITY versions: ngraph=0.26.0 netgraph-core=0.12.0")

    def load(path) -> Any:
        signal.alarm(180)
        doc = yaml.safe_load(scenario_bytes(Path(path)))
        return prepare(Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False)))

    def report_values(prepared) -> dict[str, Any]:
        r = prepared.units_report
        out: dict[str, Any] = {
            "q_exponent": r.exponent,
            "target_met": r.target_met,
            "limited_by": r.limited_by,
            "achieved_precision": r.achieved_precision,
            "mode": r.mode,
        }
        split = r.split_bound
        if split is not None:
            out["split_count"] = split.count
            out["L"] = split.directed_links + split.nodes
        return out

    def rows(result, step=0, case=0):
        return result.steps[step].result.cases[case].states["converged"].rows

    files = {
        "readme": "readme_example.yml",
        "square_mesh": "square_mesh.yml",
        "fanin50": "fanin50.yml",
        "docs_paths": "docs_paths.yml",
        "docs_paths_q1": "docs_paths_q1.yml",
        "tunnel_threshold": "tunnel_threshold.yml",
        "ordered_residual": "ordered_residual.yml",
        "range": "range.yml",
        "te_link": "te_link.yml",
        "input_rounding": "input_rounding.yml",
        "tunnels_p01": "tunnels_p01.yml",
        "zero_member": "zero_member.yml",
    }
    bad = n = 0

    def record(name, key, expected, actual):
        nonlocal bad, n
        n += 1
        ok = actual is not None and matches(key, expected, actual)
        bad += not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {name}.{key}: expected {show(expected)} ngraph {show(actual)}"
        )

    def bound(name, label, answer, fluid, q):
        nonlocal bad, n
        n += 1
        ok = abs(answer - fluid) <= P * fluid + q / 2
        bad += not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {name}.{label}: ngraph {float(answer):.9g} fluid {float(fluid):.9g} "
            f"observed comparison threshold p*X + q/2 (no general ordered/scaled guarantee)"
        )

    for name, file in files.items():
        prepared = load(SC / file)
        result: Any = run(prepared)
        got = report_values(prepared)
        q = F(prepared.topology.q)
        if name == "readme":
            got["msd_alpha"] = F(result.steps[0].result.alpha_feasible.value)
            place = result.steps[1].result
            got["baseline_delivered_units"] = (
                place.cases[0].states["converged"].totals.delivered_units
            )
            net = readme_net()
            src = [x for x in net.nodes if x.startswith("site1/leaf")]
            dst = [x for x in net.nodes if x.startswith("site2/leaf")]
            for case in place.cases:
                fluid = ref.fluid_ordered(
                    net, [(src, dst, 100)], 1, case.case.pattern.excluded_links
                )[0]
                answer = F(case.states["converged"].totals.delivered_units) * q
                bound(name, f"case {case.case.id}", answer, fluid, q)
        elif name == "square_mesh":
            got["msd_alpha"] = F(result.steps[0].result.alpha_feasible.value)
        elif name == "fanin50":
            got["msd_alpha"] = F(result.steps[0].result.alpha_feasible.value)
            got["delivered_units"] = rows(result, 1)[0].result.delivered
        elif name in (
            "docs_paths",
            "docs_paths_q1",
            "input_rounding",
            "zero_member",
            "tunnel_threshold",
            "tunnels_p01",
            "range",
        ):
            got["delivered_units"] = rows(result)[0].result.delivered
        elif name == "ordered_residual":
            r = rows(result)
            got["first_delivered_units"], got["second_delivered_units"] = (
                r[0].result.delivered,
                r[1].result.delivered,
            )
        elif name == "te_link":
            got["max_flow_units"] = rows(result)[0].result.delivered
        for key, value in EXPECTED[name].items():
            if key in got:
                record(name, key, value, got[key])
            elif not key.startswith(("reading_", "fluid_", "exact_", "physical_")):
                record(name, key, value, None)
    # DC-BB: the q and MSD alpha, and every failure case against the fluid reference, per demand.
    digest = hashlib.sha256(scenario_bytes(DCBB_YAML)).hexdigest()
    if digest != DCBB_YAML_SHA256:
        raise SystemExit(f"{DCBB_YAML} changed: {digest}")
    prepared = load(DCBB_YAML)
    result: Any = run(prepared)
    got = report_values(prepared)
    got["msd_alpha_in"] = frozenset({F(result.steps[0].result.alpha_feasible.value)})
    exp = EXPECTED["dcbb12"]
    for key, value in exp.items():
        if key == "msd_alpha_in":
            n += 1
            ok = next(iter(got[key])) in value
            bad += not ok
            print(
                f"{'ok  ' if ok else 'FAIL'} dcbb12.msd_alpha: ngraph {show(got[key])} in {show(value)}"
            )
        elif key in got:
            record("dcbb12", key, value, got[key])
        elif not key.startswith(("reading_", "fluid_")):
            record("dcbb12", key, value, None)
    net = dcbb_net()
    demands = dcbb_demands(net)
    q = F(prepared.topology.q)
    place = result.steps[1].result
    alpha = F(place.alpha.value)
    for case in place.cases:
        links, nodes = (
            case.case.pattern.excluded_links,
            case.case.pattern.excluded_nodes,
        )
        fluid = ref.fluid_ordered(net, demands, alpha, links, nodes)
        for row, x in zip(case.states["converged"].rows, fluid, strict=False):
            bound(
                "dcbb12",
                f"case {case.case.id} {row.id}",
                F(row.result.delivered) * q,
                x,
                q,
            )
    for name, values in boundaries.EXPECTED.items():
        signal.alarm(60)
        actual = boundaries.native_values(name)
        for key, value in actual.items():
            record(name, key, values[key], value)
    signal.alarm(0)
    print(f"SUMMARY examples ngraph: {n - bad}/{n} checks pass")
    return bad


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "reference"
    failures = {
        "reference": check_reference,
        "plants": check_plants,
        "mutants": check_mutants,
        "ngraph": check_ngraph,
    }[mode]()
    sys.exit(1 if failures else 0)
