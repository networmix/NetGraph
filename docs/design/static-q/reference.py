"""Independent reference for the examples of README.md.

Written from the design's rule text and from the documented routing rules; standard library only. It never imports
NetGraph or NetGraph-Core. Every amount is an exact Fraction; binary64 inputs are read exactly.

- `rule`: the choice of q from counts (README.md).
- `Net`, `Program`: a network of physical links (two directions each), shortest-path DAGs toward a destination set,
  fluid fractions of equal splitting (each router equally over its members, each roster source an equal share).
- `whole_units_lossless`: the largest whole-unit total whose round-robin forwarding fits (sources and members in a
  given order).
- `msd_outputs`: the alphas the MSD search can return when the unit-fit cutoff lies anywhere in a band.
"""

from __future__ import annotations

import heapq
import json
from fractions import Fraction as F

P_DEFAULT = F(1, 1000)


def exact(value) -> F:
    """The exact value of a binary64 input."""
    return F(float(value))


def largest_power(limit: F | None) -> int:
    """The exponent of the largest power of two in [2^-32, 2^32] at most `limit` (2^32 when unbounded); -33 when
    even 2^-32 exceeds it."""
    if limit is None:
        return 32
    e = 32
    while e >= -32 and F(2) ** e > limit:
        e -= 1
    return e


def split_count(L: int, k: int, tunnels: int) -> F:
    """Gamma for one group placed together: max(k, 1) (L/4 + 2) plus its tunnels."""
    return max(k, 1) * (F(L, 4) + 2) + tunnels


def rule(
    L: int,
    groups: list[tuple[int, int]],
    c_min,
    v_min,
    p=P_DEFAULT,
    range_ok=lambda e: True,
):
    """The static automatic q. groups: (k in-scope demands, tunnels) per group; the floor group (1, 0) is implied.

    Tunnel totals count all selected source endpoints, before runtime reachability filtering; a pool is one head.
    Returns (exponent, Gamma, limited_by, achieved precision, target_met)."""
    p = exact(p)
    gamma = max([split_count(L, 0, 0)] + [split_count(L, k, t) for k, t in groups])
    c_min = exact(c_min) if c_min is not None else None
    v_min = exact(v_min) if v_min is not None else None
    bounds = {}
    if v_min is not None:
        bounds["input"] = 2 * p * v_min
    if c_min is not None:
        bounds["split_count"] = p * c_min / gamma
    limit = min(bounds.values()) if bounds else None
    e = largest_power(limit)
    if not bounds:
        limited = "unbounded"
    elif e < -32:
        e, limited = -32, "resolution_floor"
    else:
        limited = min(bounds, key=lambda name: (bounds[name], name != "input"))
    while not range_ok(e):
        e += 1
        limited = "range"
        if e > 32:
            raise ValueError("no legal resolution is in range")
    return (
        e,
        gamma,
        limited,
        achieved(e, gamma, c_min, v_min),
        achieved_ok(e, gamma, c_min, v_min, p),
    )


def achieved(e, gamma, c_min, v_min):
    """max(q / (2 v_min), q Gamma / c_min), None without a positive input."""
    q = F(2) ** e
    terms = []
    if v_min is not None:
        terms.append(q / (2 * exact(v_min)))
    if c_min is not None:
        terms.append(q * gamma / exact(c_min))
    return max(terms) if terms else None


def achieved_ok(e, gamma, c_min, v_min, p=P_DEFAULT):
    a = achieved(e, gamma, c_min, v_min)
    return a is None or a <= exact(p)


class Net:
    """Physical links (both directions, each with the full capacity); nodes in the given order."""

    def __init__(self, nodes, links, ids=None):
        self.nodes = list(nodes)
        self.index = {n: i for i, n in enumerate(self.nodes)}
        if (
            ids is None
        ):  # the documented link id: source|target|n, n counting links of that ordered pair from 0
            seen, ids = {}, []
            for s, t, _, _ in links:
                ids.append(f"{s}|{t}|{seen.get((s, t), 0)}")
                seen[(s, t)] = seen.get((s, t), 0) + 1
        self.edges = []  # (u, v, capacity Fraction, cost, link id, input position)
        for lid, (s, t, cap, cost) in zip(ids, links, strict=False):
            for u, v in ((s, t), (t, s)):
                self.edges.append((u, v, exact(cap), int(cost), lid, len(self.edges)))
        self.links = list(links)

    @classmethod
    def from_json(cls, data):
        nodes = [n["name"] for n in data["nodes"]]
        links = [
            (lk["source"], lk["target"], float.fromhex(lk["capacity"]), lk["cost"])
            for lk in data["links"]
        ]
        return cls(nodes, links, [lk["id"] for lk in data["links"]])

    @property
    def L(self) -> int:
        return len(self.nodes) + 2 * len(self.links)

    def c_min(self):
        positive = [e[2] for e in self.edges if e[2] > 0]
        return min(positive) if positive else None


class Program:
    """One combine demand with equal splits: roster, members per router (EdgeId-like order), fluid fractions."""

    def __init__(self, net: Net, sources, targets, failed_links=(), failed_nodes=()):
        dead_nodes, dead_links = set(failed_nodes), set(failed_links)
        live = [
            e
            for e in net.edges
            if e[0] not in dead_nodes
            and e[1] not in dead_nodes
            and e[4] not in dead_links
        ]
        self.targets = {t for t in targets if t not in dead_nodes}
        inc = {}
        for e in live:
            inc.setdefault(e[1], []).append(e)
        dist = {t: 0 for t in self.targets}
        heap = [(0, net.index[t], t) for t in self.targets]
        heapq.heapify(heap)
        while heap:
            d, _, v = heapq.heappop(heap)
            if d > dist[v]:
                continue
            for u, _, _, cost, _, _ in inc.get(v, ()):
                if d + cost < dist.get(u, d + cost + 1):
                    dist[u] = d + cost
                    heapq.heappush(heap, (d + cost, net.index[u], u))
        self.roster = sorted(
            (
                s
                for s in sources
                if s not in dead_nodes and s in dist and s not in self.targets
            ),
            key=lambda node: net.index[node],
        )
        members = {}
        for e in live:
            u, v, _, cost, _, _ = e
            if u in self.targets or u not in dist or v not in dist:
                continue
            if dist[u] == cost + dist[v]:
                members.setdefault(u, []).append(e)
        reach, stack = set(self.roster), list(self.roster)
        while stack:
            for e in members.get(stack.pop(), ()):
                if e[1] not in reach:
                    reach.add(e[1])
                    stack.append(e[1])
        # Core's member order: by (source, cost, destination), then input order.
        self.members = {
            u: sorted(m, key=lambda e: (e[3], net.index[e[1]], e[5]))
            for u, m in members.items()
            if u in reach
        }
        self.order = sorted(reach, key=lambda n: (-dist[n], net.index[n]))
        self.f = {}
        phi = dict.fromkeys(self.order, F(0))
        for s in self.roster:
            phi[s] += F(1, len(self.roster))
        for u in self.order:
            if u in self.targets or not phi[u]:
                continue
            m = self.members.get(u, ())
            for e in m:
                self.f[e[5]] = self.f.get(e[5], F(0)) + phi[u] / len(m)
                phi[e[1]] += phi[u] / len(m)
        self.net = net

    def x_c(self, available=None):
        """min over carrying members of available capacity / f (0 when one has none)."""
        cap = (
            available if available is not None else {e[5]: e[2] for e in self.net.edges}
        )
        return min((cap[i] / fe for i, fe in self.f.items() if fe > 0), default=None)

    def fits(self, total: int, units: dict[int, int]) -> bool:
        """Round-robin forwarding of `total` whole units overloads no member."""
        inflow = dict.fromkeys(self.order, 0)
        q, r = divmod(total, len(self.roster))
        for i, s in enumerate(self.roster):
            inflow[s] += q + (i < r)
        for u in self.order:
            if u in self.targets or not inflow[u]:
                continue
            m = self.members[u]
            qq, rr = divmod(inflow[u], len(m))
            for i, e in enumerate(m):
                x = qq + (i < rr)
                if x > units[e[5]]:
                    return False
                inflow[e[1]] += x
        return True


def units_of(net: Net, q: F) -> dict[int, int]:
    """Every directed edge's capacity in whole units, half up."""
    return {e[5]: (e[2] / q + F(1, 2)).__floor__() for e in net.edges}


def whole_units_lossless(prog: Program, q: F, request_units: int | None = None) -> int:
    units = units_of(prog.net, q)
    hi = sum(units.values()) + 1 if request_units is None else request_units + 1
    lo = 0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if prog.fits(mid, units):
            lo = mid
        else:
            hi = mid
    return lo


def fluid_msd(net: Net, demands, failed_links=()):
    """alpha* = min_e c_e / sum_d V_d f_d,e. demands: [(sources, targets, V)]."""
    load = {}
    for sources, targets, volume in demands:
        prog = Program(net, sources, targets, failed_links)
        for i, fe in prog.f.items():
            load[i] = load.get(i, F(0)) + exact(volume) * fe
    return min(net.edges[i][2] / amount for i, amount in load.items() if amount > 0)


def fluid_ordered(net: Net, demands, alpha, failed_links=(), failed_nodes=()):
    """Fluid ordered lossless placement; returns each demand's delivery."""
    residual = {e[5]: e[2] for e in net.edges}
    out = []
    for sources, targets, volume in demands:
        prog = Program(net, sources, targets, failed_links, failed_nodes)
        request = F(alpha) * exact(volume)
        x = prog.x_c(residual) if prog.f else F(0)
        x = request if x is None else min(request, x)
        for i, fe in prog.f.items():
            residual[i] -= x * fe
        out.append(x)
    return out


def msd_band(p):
    """The conditional normal-product MSD relative allowance, for 0 < p <= 1/2."""
    return p + F(2) ** -52


def msd_outputs(
    alpha_star: F,
    band: F,
    tolerance: F,
    start=F(1),
    growth=F(2),
    alpha_min=F(1, 10**6),
    alpha_max=F(10**9),
):
    """Every alpha the MSD search (bracket by `growth` from `start`, then exact-midpoint bisection until the gap is
    at most `tolerance`; the answer is the largest tested feasible alpha) can return when the unit-fit cutoff c lies
    anywhere in [alpha*(1 - band), alpha*(1 + band)] and a probe is feasible iff alpha <= c."""
    lo_c, hi_c = alpha_star * (1 - band), alpha_star * (1 + band)

    def search(c):
        tested = []

        def feasible(a):
            tested.append(a)
            return a <= c

        a = start
        if feasible(a):
            lo = a
            while True:
                a = a * growth
                if a > alpha_max:
                    return lo, tested
                if not feasible(a):
                    hi = a
                    break
                lo = a
        else:
            hi = a
            while True:
                a = a / growth
                if a < alpha_min:
                    return None, tested
                if feasible(a):
                    lo = a
                    break
                hi = a
        while hi - lo > tolerance:
            mid = (lo + hi) / 2
            if feasible(mid):
                lo = mid
            else:
                hi = mid
        return lo, tested

    # The answer changes only when c crosses a tested alpha: probe c at the band ends and just around every tested
    # value inside the band, repeating until no new tested value appears.
    candidates, seen, outputs = {lo_c, hi_c}, set(), set()
    while candidates - seen:
        c = (candidates - seen).pop()
        seen.add(c)
        out, tested = search(c)
        outputs.add(out)
        for a in tested:
            if lo_c <= a <= hi_c:
                candidates.update(
                    {a, min(hi_c, a + F(1, 2**80)), max(lo_c, a - F(1, 2**80))}
                )
    return outputs


def load_json_gz(path):
    import gzip

    with gzip.open(path, "rt") as fh:
        return json.load(fh)
