"""The answers the pages narrate after their examples, and the figures of the scenario
headers, compared with what the product gives.

Each number is read from the prose a reader sees (`narration`, `stated`), never copied
into the test, and compared with a value the product computes when the page's own
examples run; a changed number in the prose fails here.
"""

import math
import re
from collections import Counter
from fractions import Fraction

import netgraph_core as ngc
import yaml

from ngraph import CapacityQuery, Scenario, capacity, prepare, run
from tests.docs.pages import ROOT, fence, fences, narration, numbers, stated

CONCEPTS = "docs/concepts.md"
BASIC = "docs/examples/basic.md"
CLOS = "docs/examples/clos-fabric.md"
BUNDLED = "docs/examples/bundled-scenarios.md"
WORDS = {"single": 1, "pair": 2, "pairs": 2} | dict(
    zip(
        "zero one two three four five six seven eight nine ten".split(),
        range(11),
        strict=True,
    )
)


def number(text):
    return WORDS[text.lower()] if text.lower() in WORDS else Fraction(text)


def ints(groups):
    return [number(g) for g in groups]


def examples(page, upto_excerpt):
    """The namespace after running a page's Python examples up to the one containing the
    excerpt, in order, as the page's reader does."""
    namespace = {"__name__": "__documented_client__"}
    for block in [f for f in fences(page) if f.lang == "python"]:
        exec(compile(block.text, f"{page}:{block.line}", "exec"), namespace)
        if upto_excerpt in block.text:
            return namespace
    raise AssertionError(f"{page}: no Python example contains {upto_excerpt!r}")


def triple_quoted(page, excerpt):
    """The first triple-quoted YAML text inside a page's Python example."""
    return re.search(r'"""\n(.*?)"""', fence(page, excerpt, "python").text, re.S)[1]


def with_outputs(text, step_name, outputs):
    """A scenario text whose named step also requests the given outputs."""
    pattern = re.compile(r"(\{type: \w+, name: %s,[^}]*?)\}" % re.escape(step_name))
    changed, count = pattern.subn(
        lambda m: m[1] + f", outputs: {outputs}}}", text, count=1
    )
    assert count == 1, step_name
    return changed


def flows(prepared, vector):
    return {
        ref.link: int(units)
        for ref, units in zip(prepared.topology.edge_refs, vector, strict=True)
        if ref is not None and ref.direction == "forward"
    }


def converged(result, step=0, case=0):
    return result.steps[step].result.cases[case].states["converged"]


def test_basic_states_its_unmet_precision_target():
    """Basic Example: q = 1 misses the default target, nothing rounded."""
    report = examples(BASIC, "network.add_link(Link(source")["prepared"].units_report
    assert not report.target_met and report.limited_by == "declared"


def test_the_api_and_tunnel_count_examples_state_their_unmet_precision_target():
    """Python API and TunnelCountAnalysis: their examples fix q = 1, which misses the
    default precision target; nothing is rounded."""
    api = "docs/reference/api.md"
    space = examples(api, 'network.add_link(Link("A", "B"')
    workflow = "docs/reference/workflow.md"
    counts = prepare(
        Scenario.from_yaml(fence(workflow, "TunnelCountAnalysis", "yaml").text)
    )
    for prepared in (space["prepared"], counts):
        report = prepared.units_report
        assert prepared.topology.q == 1 and report.mode == "manual"
        assert not report.target_met


# How NetGraph computes


def test_units_narration():
    space = examples(CONCEPTS, "volume: 2.625")
    text = narration(CONCEPTS, "volume: 2.625")
    units, physical, stats = ints(
        (
            numbers(text, "delivers (\\d+) units")
            + numbers(text, "([\\d.]+) physical")
            + numbers(text, "physical capacity, (\\d+)")
        )
    )
    totals, q = space["totals"], space["prepared"].topology.q
    assert totals.delivered_units == units
    assert totals.delivered_units * q == physical
    assert space["result"].steps[0].result.total_capacity == stats


def test_routing_narration():
    space = examples(CONCEPTS, "SHORTEST_PATHS_ECMP_LOSSY")
    text = narration(CONCEPTS, "SHORTEST_PATHS_ECMP_LOSSY")
    prepared, lossless, lossy = space["prepared"], space["lossless"], space["lossy"]
    most, to_b, to_c, each, tenth = ints(
        (
            numbers(text, "Lossless: (\\d+)")
            + numbers(text, "A gives (\\d+)")
            + numbers(text, "(\\d+) to C")
            + numbers(text, "C gives (\\d+)")
            + numbers(text, "would send (\\d+)")
        )
    )
    found = flows(prepared, lossless.rows[0].result.edge_flows)
    assert lossless.totals.delivered_units == most
    assert (found["A|B|0"], found["A|C|0"]) == (to_b, to_c)
    assert found["C|X|0"] == found["C|Y|0"] == each
    # One more unit than fits: what C then sends toward X, carried plus lost there.
    more = space["paths"].replace(
        "volume: 12, preset: SHORTEST_PATHS_ECMP_LOSSY",
        f"volume: {most + 1}, preset: SHORTEST_PATHS_ECMP_LOSSY",
    )
    tried = prepare(Scenario.from_yaml(more))
    state = converged(run(tried), step=1)
    assert (
        flows(tried, state.rows[0].result.edge_flows)["C|X|0"]
        + state.totals.edge_drop_units
        == tenth
    )
    entered, each_way, to_x, lost = ints(
        (
            numbers(text, "Lossy: all (\\d+)")
            + numbers(text, "A sends (\\d+)")
            + numbers(text, "C sends (\\d+)")
            + numbers(text, "(\\d+) unit is lost")
        )
    )
    found = flows(prepared, lossy.rows[0].result.edge_flows)
    totals = lossy.totals
    assert totals.reference_request_units == entered and totals.unadmitted_units == 0
    assert totals.source_drop_units == 0
    assert found["A|B|0"] == found["A|C|0"] == each_way
    assert found["C|X|0"] + totals.edge_drop_units == to_x
    assert totals.edge_drop_units == lost


def test_source_roster_narration():
    space = examples(CONCEPTS, "roster % (first, second)")
    text = narration(CONCEPTS, "roster % (first, second)")
    delivered, roster = space["delivered"], space["roster"]
    big, small, first, second, fit = ints(
        (
            numbers(text, "(\\d+) and (\\d+)")
            + numbers(text, "(\\d+) units and S2 (\\d+), so (\\d+)")
        )
    )
    text_with_flows = (roster % (big, small)).replace(
        "alpha: 2.5}", "alpha: 2.5, outputs: {edge_flows: true}}"
    )
    prepared = prepare(Scenario.from_yaml(text_with_flows))
    found = flows(prepared, converged(run(prepared)).rows[0].result.edge_flows)
    assert (found["S1|T|0"], found["S2|T|0"]) == (first, second)
    assert delivered[big, small] == fit
    need, own, fit = ints(numbers(text, "(\\d+) of its (\\d+), so (\\d+)"))
    assert (need, own) == (first, small) and delivered[small, big] == fit
    (after,) = ints(numbers(text, "S1's (\\w+) unit"))
    assert delivered[5, 0] == after and delivered[0, 5] == 0  # "admits nothing"


def test_tunnel_narration():
    space = examples(CONCEPTS, "distributed_te")
    text = narration(CONCEPTS, "distributed_te")
    head, placed = space["head"], space["placed"]
    hold, link, asks, free_a, free_b = ints(
        (
            numbers(text, "holds (\\d+)")
            + numbers(text, "link of (\\d+)")
            + numbers(text, "asks (\\d+)")
            + numbers(text, "(\\d+) and (\\d+)")
        )
    )
    links = head.scenario.network.links
    held = flows(head, placed.edge_reservations)
    assert held == {"S|T|0": hold, "S|T|1": 0} and links["S|T|0"].capacity == link
    assert asks == hold  # the design splits equally over the two tunnels
    assert (link - hold, links["S|T|1"].capacity) == (free_a, free_b) and asks > max(
        free_a, free_b
    )
    (carries,) = ints(numbers(text, "carries (\\d+),"))
    assert placed.delivered == carries
    two, offer = ints(
        (numbers(text, "deliver (\\d+)") + numbers(text, "offer of (\\d+)"))
    )
    rows = space["rows"]
    assert (rows[1].count, rows[1].result.delivered) == (2, two)
    assert space["counts"].steps[0].result.query.offer == offer
    limit, chosen, design = ints(
        (
            numbers(text, "Up to (\\d+)")
            + numbers(text, "chooses (\\w+) tunnel")
            + numbers(text, "design of (\\d+)")
        )
    )
    assert (rows[2].count, rows[2].up_to, rows[2].result.plan.tunnels_per_head) == (
        limit,
        True,
        chosen,
    )
    assert space["counts"].steps[0].result.query.design_demand == design


def test_wcmp_narration():
    space = examples(CONCEPTS, "SHORTEST_PATHS_WCMP}]\n  ecmp")
    text = narration(CONCEPTS, "SHORTEST_PATHS_WCMP}]\n  ecmp")
    x1, x2, grow_a, grow_b, w1, w2, total = ints(
        (
            numbers(text, "X1 carries (\\d+)")
            + numbers(text, "X2 (\\d+)")
            + numbers(text, "grow (\\d+) to (\\d+)")
            + numbers(text, "are (\\d+) and (\\d+)")
            + numbers(text, "all (\\d+) arrive")
        )
    )
    prepared = space["prepared"]
    links = prepared.scenario.network.links
    assert (links["X1|T|0"].capacity, links["X2|T|0"].capacity) == (x1, x2)
    assert Fraction(x1, x2) == Fraction(grow_a, grow_b)
    [table] = prepared.demand_sets["wcmp"].controller
    assert [m.weight for m in table.programmed[0].members] == [w1, w2]
    result = run(prepared)
    assert converged(result, step=0).totals.delivered_units == total
    first, admitted, via_x1, via_x2 = ints(
        (numbers(text, "X2's (\\d+)") + numbers(text, "(\\d+) \\((\\d+) and (\\d+)\\)"))
    )
    assert first == x2 and converged(result, step=1).totals.delivered_units == admitted
    shown = prepare(
        Scenario.from_yaml(with_outputs(space["domain"], "ecmp", "{edge_flows: true}"))
    )
    found = flows(shown, converged(run(shown), step=1).rows[0].result.edge_flows)
    assert (found["S|X1|0"], found["S|X2|0"]) == (via_x1, via_x2)


def test_forwarding_groups_narration():
    space = examples(
        CONCEPTS,
        "forwarding_groups:\n  edge:\n    router: S\n    groups:\n      - share: 1",
    )
    text = narration(
        CONCEPTS,
        "forwarding_groups:\n  edge:\n    router: S\n    groups:\n      - share: 1",
    )
    live = ints(numbers(text, "live,.*?weights (\\d+), (\\d+), (\\d+)"))
    dead = ints(numbers(text, "dead,.*?weights (\\d+), (\\d+), (\\d+)"))
    (total,) = ints(numbers(text, "all (\\d+) still arrive"))
    for capacity_x3, weights in ((100, live), (0, dead)):
        prepared = prepare(Scenario.from_yaml(space["groups"] % capacity_x3))
        [table] = prepared.demand_sets["d"].controller
        assert [m.weight for m in table.programmed[0].members] == weights
        assert converged(run(prepared)).totals.delivered_units == total


def test_failure_states_narration():
    excerpt = "failure_states: [converged, stale, repair]"
    space = examples(CONCEPTS, excerpt)
    text = narration(CONCEPTS, excerpt)
    draws, patterns = ints(
        (numbers(text, "(\\w+) draws") + numbers(text, "(\\w+) patterns"))
    )
    analysis = space["failures"]
    result = run(analysis).steps[0].result
    assert (
        result.metadata.sampling.iterations == draws
        and len(result.cases) - 1 == patterns
    )
    (each,) = ints(numbers(text, "routes, (\\d+) each"))
    (moved,) = ints(numbers(text, "moves (\\d+)"))
    (lost,) = ints(numbers(text, "sends (\\d+)"))
    carried, refused = ints(
        (numbers(text, "carries (\\d+)") + numbers(text, "other (\\d+)"))
    )
    yaml_text = triple_quoted(CONCEPTS, excerpt)
    shown = prepare(
        Scenario.from_yaml(
            yaml_text.replace(
                "failure_states: [converged, stale, repair]}",
                "failure_states: [converged, stale, repair], outputs: {edge_flows: true}}",
            )
        )
    )
    cases = run(shown).steps[0].result.cases
    base = flows(shown, cases[0].states["converged"].rows[0].result.edge_flows)
    assert base["S|A|0"] == base["S|B|0"] == each and base["S|C|0"] == 0
    for case in cases[1:]:
        assert (
            flows(shown, case.states["converged"].rows[0].result.edge_flows)["S|C|0"]
            == moved
        )
        assert case.states["stale"].totals.edge_drop_units == lost
        repair = case.states["repair"].totals
        assert (repair.delivered_units, repair.unadmitted_units) == (carried, refused)


def test_dead_cap_narration():
    space = examples(CONCEPTS, "x2_exit")
    text = narration(CONCEPTS, "x2_exit")
    (taken,) = ints(numbers(text, "(\\w+) unit"))
    each, lost = ints((numbers(text, "sends (\\d+)") + numbers(text, "X2's (\\d+)")))
    assert space["converged_state"].totals.delivered_units == taken
    stale = space["stale_state"].totals
    assert stale.delivered_units == each and stale.edge_drop_units == lost == each


def test_simultaneous_narration():
    space = examples(CONCEPTS, "interaction: simultaneous")
    text = narration(CONCEPTS, "interaction: simultaneous")
    sent, carried, loses = ints(
        (
            numbers(text, "send (\\d+)")
            + numbers(text, "carries (\\d+)")
            + numbers(text, "loses (\\d+)")
        )
    )
    rows = space["simultaneous"]
    assert all(row.result.requested == sent for row in rows)
    assert sum(row.result.delivered for row in rows) == carried
    assert [row.result.requested - row.result.delivered for row in rows] == [
        loses,
        loses,
    ]
    small_a, small_b, after_first, after_second, final = ints(
        (
            numbers(text, "(\\d+) and (\\d+)")
            + numbers(text, "after each \\((\\d+), then (\\d+)\\)")
            + numbers(text, "final (\\d+)")
        )
    )
    assert (
        f"two % ({small_a}, {small_b})"
        in fence(CONCEPTS, "interaction: simultaneous", "python").text
    )
    assert space["left"] == [[after_first, after_second], [final, final]]


def test_msd_narration():
    space = examples(CONCEPTS, "below_resolution")
    text = narration(CONCEPTS, "below_resolution")
    num, den, up_num, up_den = numbers(text, "finds (\\d+)/(\\d+)") + numbers(
        text, "below (\\d+)/(\\d+)"
    )
    search = space["search"]
    assert search.alpha_feasible.value == Fraction(int(num), int(den))
    assert search.upper_certificate.upper.value == Fraction(int(up_num), int(up_den))
    probes = [
        numbers(text, rf"(\d+) × 1/({divisor}) = ([\d.]+) rounds to (\d+)")
        for divisor in (8, 4)
    ]
    for probe, (volume, divisor, product, units) in zip(
        space["coarse"].history[:2], probes, strict=True
    ):
        assert probe.alpha.value == Fraction(1, int(divisor))
        assert Fraction(volume) / int(divisor) == Fraction(product)
        assert probe.totals.reference_request_units == int(units)


def test_results_narration():
    excerpt = "te.total_cost == 240"
    space = examples(CONCEPTS, excerpt)
    text = narration(CONCEPTS, excerpt)
    physical, units, divisor, per_unit, cost, times, total, scaled = ints(
        (
            numbers(text, "(\\d+) delivered")
            + numbers(text, "(\\d+) units of 1/(\\d+)")
            + numbers(text, "costs (\\d+)")
            + numbers(text, "`total_cost` is (\\d+) × (\\d+) = (\\d+)")
            + numbers(text, "(\\d+) after × `q`")
        )
    )
    te, q = space["te"], space["prepared"].topology.q
    assert q == Fraction(1, int(divisor)) and te.delivered == units == times
    assert te.delivered * q == physical
    links = space["prepared"].scenario.network.links
    assert links["A|B|0"].cost + links["B|C|0"].cost == per_unit == cost
    assert te.total_cost == total and te.total_cost * q == scaled


# Basic Example


def test_basic_capacity_narration():
    space = examples(BASIC, "ideal = capacity(")
    text = narration(BASIC, "ideal = capacity(")
    (each,) = ints(numbers(text, "(\\d+) units on each"))
    (cheap,) = ints(numbers(text, "sum to (\\d+)"))
    (equal,) = ints(numbers(text, "admits (\\d+)"))
    prepared, source, target = space["prepared"], space["source"], space["target"]
    shown = capacity(
        prepared,
        CapacityQuery(source, target, outputs=ngc.OutputOptions(edge_flows=True)),
    )
    found = flows(
        prepared, shown.cases[0].states["converged"].rows[0].result.edge_flows
    )
    assert found["A|B|0"] + found["A|B|1"] == found["A|D|0"] == each
    links = prepared.scenario.network.links
    assert links["A|B|0"].capacity + links["A|B|1"].capacity == cheap
    assert (
        space["shortest"].cases[0].states["converged"].rows[0].result.delivered == cheap
    )
    assert space["equal"].cases[0].states["converged"].rows[0].result.delivered == equal


def test_basic_cost_and_cut_narration():
    space = examples(BASIC, "reported = capacity(")
    text = narration(BASIC, "reported = capacity(")
    u1, c1, u2, c2, objective = ints(
        numbers(text, "objective is (\\d+)×(\\d+) \\+ (\\d+)×(\\d+) = (\\d+)")
    )
    row = space["row"]
    assert [(p.units, p.marginal_cost) for p in row.cost_distribution.bins] == [
        (u1, c1),
        (u2, c2),
    ]
    assert u1 * c1 + u2 * c2 == objective == row.result.total_cost
    *parts, total = ints(
        numbers(text, "capacity (\\d+) \\+ (\\d+) \\+ (\\d+) = (\\d+)")
    )
    prepared = space["prepared"]
    links = prepared.scenario.network.links
    cut = [prepared.topology.edge_refs[e].link for e in row.result.min_cut]
    assert [links[link].capacity for link in cut] == parts
    assert sum(parts) == total == row.result.delivered


def test_basic_failures_and_placement_narration():
    space = examples(BASIC, "from ngraph import FailureMode")
    text = narration(BASIC, "from ngraph import FailureMode")
    draws, all_draws, patterns = ints(
        (
            numbers(text, "(\\w+) times")
            + numbers(text, "(\\w+) draws")
            + numbers(text, "(\\w+) physical pattern")
        )
    )
    result = space["result"]
    assert result.metadata.sampling.iterations == draws
    assert [c.case.occurrences for c in result.cases[1:]] == [all_draws] * patterns
    space = examples(BASIC, "from ngraph import DemandSet")
    (unadmitted,) = ints(
        numbers(narration(BASIC, "from ngraph import DemandSet"), "remaining (\\d+)")
    )
    assert space["state"].totals.unadmitted_units == unadmitted


# Clos Fabric


def clos():
    text = fence(CLOS, "blueprints:").text
    prepared = prepare(Scenario.from_yaml(text))
    return prepared, run(prepared)


def test_clos_introduction_and_failed_capacity():
    """Clos Fabric: the opening paragraph's figures; losing either inter-site link
    leaves the stated capacity."""
    (expected,) = stated(CLOS, "leaves (\\d+)")
    leaves, spines, local, inter, total = (
        stated(CLOS, "have (\\w+)")
        + stated(CLOS, "and (\\w+) spines")
        + stated(CLOS, "capacity-(\\d+) link")
        + stated(CLOS, "capacity-(\\d+) inter-site")
        + stated(CLOS, "delivery to (\\d+)")
    )
    prepared, result = clos()
    network = prepared.scenario.network
    for site in ("site1", "site2"):
        assert sum(n.startswith(f"{site}/leaf/") for n in network.nodes) == number(
            leaves
        )
        assert sum(n.startswith(f"{site}/spine/") for n in network.nodes) == number(
            spines
        )
    kinds = Counter(
        ("inter" if link.attrs.get("role") == "inter_site" else "local", link.capacity)
        for link in network.links.values()
    )
    assert (
        set(kinds) == {("local", int(local)), ("inter", int(inter))}
        and kinds["inter", int(inter)] == 2
    )
    analysis = result.steps[1].result
    q = prepared.topology.q
    assert converged(result, step=1).rows[0].result.delivered * q == int(total)
    assert analysis.cases[1:]
    for case in analysis.cases[1:]:
        assert case.states["converged"].rows[0].result.delivered * q == int(expected)


def test_clos_expansion_and_route_cost():
    text = (ROOT / CLOS).read_text()
    nodes, links, edges = ints(
        (
            numbers(text, "(\\d+) nodes")
            + numbers(text, "(\\d+) physical links")
            + numbers(text, "(\\d+) directed export edges")
        )
    )
    up, across, down, cost = ints(
        numbers(text, "cost (\\d+) \\+ (\\d+) \\+ (\\d+) = (\\d+)")
    )
    prepared, result = clos()
    built = result.steps[0].result
    assert (
        built.node_count,
        len(prepared.scenario.network.links),
        built.edge_count,
    ) == (nodes, links, edges)
    network = prepared.scenario.network
    assert (
        {
            link.cost
            for link in network.links.values()
            if link.attrs.get("role") != "inter_site"
        }
        == {up}
        == {down}
    )
    assert {
        link.cost
        for link in network.links.values()
        if link.attrs.get("role") == "inter_site"
    } == {across}
    row = converged(result, step=1).rows[0]
    assert up + across + down == cost and [
        b.cost for b in row.cost_distribution.bins
    ] == [cost]


# Workflow Steps


def test_tunnel_count_narration():
    page = "docs/reference/workflow.md"
    text = (
        (ROOT / page)
        .read_text()
        .split("## TunnelCountAnalysis", 1)[1]
        .split("\n## ", 1)[0]
    )
    narrow, wide, offer, tunnels, chosen, head_a, head_b, per_head, head_chosen = ints(
        (
            numbers(text, "delivers (\\d+) \\+ (\\d+)")
            + numbers(text, "offer of (\\d+)")
            + numbers(text, "with (\\w+) tunnels \\(")
            + numbers(text, "chooses (\\w+) tunnel")
            + numbers(text, "heads deliver (\\d+) \\+ (\\d+)")
            + numbers(text, "with (\\w+) tunnels each")
            + numbers(text, "choose (\\w+)")
        )
    )
    physical = ints(numbers(text, "\\((\\d+) and (\\d+)"))
    block = re.search(r"```yaml\n(.*?)```", text, re.S)[1]
    prepared = prepare(Scenario.from_yaml(block))
    rows = run(prepared).steps[0].result.rows
    links = prepared.scenario.network.links
    assert sorted((links["S|T|0"].capacity, links["S|T|1"].capacity)) == [narrow, wide]
    assert (links["a|T|0"].capacity, links["b|T|0"].capacity) == (head_a, head_b)
    pooled = [r for r in rows if r.base_id == "pooled"]
    heads = [r for r in rows if r.base_id == "heads"]
    assert (
        pooled[0].result.delivered == narrow + wide
        and pooled[0].result.plan.tunnels_per_head == tunnels
    )
    assert prepared.scenario.workflow[0].offer == offer
    assert pooled[1].up_to and pooled[1].result.plan.tunnels_per_head == chosen
    assert (
        heads[0].result.delivered == head_a + head_b
        and heads[0].result.plan.tunnels_per_head == per_head
    )
    assert heads[1].result.plan.tunnels_per_head == head_chosen
    assert [r.physical_tunnel_cost for r in pooled] == physical


# Bundled scenarios: the figures of each opening comment


class Header:
    """A scenario and the result figures in its opening comment."""

    def __init__(self, name):
        self.text = (ROOT / "scenarios" / name).read_text()
        comment = self.text.split("\nseed:", 1)[0].splitlines()
        self.words = " ".join(line.removeprefix("#").strip() for line in comment)
        self.scenario = Scenario.from_yaml(self.text)

    def read(self, pattern):
        return numbers(self.words, pattern)


def one_rule(policy):
    [mode] = policy.modes
    [rule] = mode.rules
    return rule


def test_square_mesh_header():
    head = Header("square_mesh.yaml")
    network, workflow = head.scenario.network, head.scenario.workflow
    (nodes,) = head.read("(\\w+)-node")
    pairs = Counter(
        tuple(sorted((link.source, link.target))) for link in network.links.values()
    )
    assert len(network.nodes) == number(nodes)
    assert len(pairs) == number(nodes) * (number(nodes) - 1) // 2 and set(
        pairs.values()
    ) == {1}
    a, b, narrow, wide = (
        head.read("(N\\d-N\\d) and (N\\d-N\\d)")
        + head.read("capacity (\\d+)")
        + head.read("others (\\d+)")
    )
    capacities = {k: v.capacity for k, v in network.links.items()}
    thin = {pair.replace("-", "|") + "|0" for pair in (a, b)}
    assert {k for k, v in capacities.items() if v == int(narrow)} == thin
    assert {v for k, v in capacities.items() if k not in thin} == {int(wide)}
    draws, failed = head.read("(\\d+) draws") + head.read("(\\w+) link failure")
    assert [s.iterations for s in workflow[1:]] == [int(draws), int(draws)]
    assert (
        workflow[1].failure_policy == workflow[2].failure_policy
    )  # "the same failures"
    rule = one_rule(head.scenario.failure_policies[workflow[1].failure_policy])
    assert (rule.scope, rule.mode, rule.count) == ("link", "choice", number(failed))


def test_readme_example_header():
    head = Header("readme_example.yml")
    network, workflow = head.scenario.network, head.scenario.workflow
    sites, blueprints = head.read("(\\w+) Clos sites") + head.read("(\\w+) blueprint")
    assert len({name.split("/")[0] for name in network.nodes}) == number(sites)
    assert len(yaml.safe_load(head.text)["blueprints"]) == number(blueprints)
    ends = {
        (link.source.split("/")[1], link.target.split("/")[1])
        for link in network.links.values()
        if link.source.split("/")[0] != link.target.split("/")[0]
    }
    assert ends == {("spine", "spine")}
    draws, failed = head.read("(\\d+) draws") + head.read("(\\w+) random link failure")
    assert workflow[1].iterations == int(draws)
    rule = one_rule(head.scenario.failure_policies[workflow[1].failure_policy])
    assert (rule.scope, rule.mode, rule.count) == ("link", "choice", number(failed))


def nsfnet_structure(network):
    """The NSFNET scenario's circuits grouped by connection, and each site's role."""
    roles = {name: node.attrs["site_type"] for name, node in network.nodes.items()}
    circuits = {}
    for link in network.links.values():
        circuits.setdefault(frozenset((link.source, link.target)), []).append(link)
    core = {e: c for e, c in circuits.items() if {roles[s] for s in e} == {"core"}}
    end = {e: c for e, c in circuits.items() if e not in core}
    return roles, core, end


def test_nsfnet_header():
    head = Header("nsfnet.yaml")
    scenario, network, workflow = (
        head.scenario,
        head.scenario.network,
        head.scenario.workflow,
    )
    roles, core, end = nsfnet_structure(network)
    n_core, n_connections, n_end, single = (
        head.read("(\\d+) core sites")
        + head.read("(\\d+) connections")
        + head.read("(\\d+) end sites")
        + head.read("on a (\\w+) circuit")
    )
    assert Counter(roles.values()) == {"core": int(n_core), "end": int(n_end)}
    assert all(name.startswith(role + "/") for name, role in roles.items())
    assert len(core) == int(n_connections)
    assert {len(c) for c in end.values()} == {number(single)}
    assert sorted(s for e in end for s in e if roles[s] == "end") == sorted(
        s for s, role in roles.items() if role == "end"
    )  # every end site has exactly one circuit, to a core site
    ds3, cost = head.read(r"DS-\d \((\d+) kbit/s") + head.read(r"cost (\d+)")
    assert {link.capacity for c in end.values() for link in c} == {int(ds3)}
    assert {sum(link.capacity for link in c) for c in core.values()} == {int(ds3)}
    assert {link.cost for link in network.links.values()} == {int(cost)}
    (pair,) = head.read(r"connection is a (\w+)")
    groups = []
    for links in core.values():
        assert len(links) == number(pair) and {link.capacity for link in links} == {
            int(ds3) / number(pair)
        }
        [[group]] = {tuple(link.risk_groups) for link in links}
        groups.append(group)
    assert {tuple(link.risk_groups) for c in end.values() for link in c} == {()}
    assert len(set(groups)) == len(groups) == len(network.risk_groups)
    circuit, connection = head.read(r"(\w+) random circuit per draw") + head.read(
        r"(\w+) random core connection"
    )
    assert len(scenario.failure_policies) == len(workflow)
    assert {step.failure_policy for step in workflow} == set(scenario.failure_policies)
    for step in workflow:  # every ordered pair of sites, one row each
        assert (
            step.mode == "pairwise" and step.source.path == step.target.path == "^(.+)$"
        )
    rule = one_rule(scenario.failure_policies["single_link_failure"])
    assert (rule.scope, rule.mode, rule.count) == ("link", "choice", number(circuit))
    rule = one_rule(scenario.failure_policies["single_connection_failure"])
    assert (rule.scope, rule.mode, rule.count) == (
        "risk_group",
        "choice",
        number(connection),
    )
    assert {
        (r.scope, r.mode) for r in one_policy_rules(head, "assumed_random_failures")
    } == {
        ("link", "random"),
        ("node", "random"),
    }
    (sites,) = stated(BUNDLED, "(\\d+) sites")
    assert len(network.nodes) == int(sites)


def test_nsfnet_page_section():
    """The section's topology, capacity, cost and workflow results match its scenario."""
    page = (ROOT / BUNDLED).read_text()
    start = page.index("## `scenarios/nsfnet.yaml`")
    section = page[start : page.index("\n## ", start + 1)]
    scenario = Scenario.from_yaml((ROOT / "scenarios/nsfnet.yaml").read_text())
    network, workflow = scenario.network, scenario.workflow
    roles, core, end = nsfnet_structure(network)

    def one(pattern):
        return numbers(section, pattern)

    n_core, n_connections = one("(\\d+) core sites") + one("(\\d+) connections")
    (n_end,) = one("(\\d+) end sites")
    assert Counter(roles.values()) == {"core": int(n_core), "end": int(n_end)}
    assert len(core) == int(n_connections) and {len(c) for c in end.values()} == {1}
    (ds3,) = one("DS-3 of (\\d+)")
    (half,) = one(r"circuits of (\d+) kbit/s")
    assert {sum(link.capacity for link in c) for c in core.values()} == {int(ds3)}
    assert {link.capacity for c in end.values() for link in c} == {int(ds3)}
    assert {link.capacity for c in core.values() for link in c} == {int(half)}
    assert {len(c) for c in core.values()} == {2} and 2 * int(half) == int(ds3)
    cost, metric = one("Cost (\\d+)") + one("metric (\\d+)")
    assert cost == metric
    assert {link.cost for link in network.links.values()} == {int(cost)}
    listed = re.findall(r"`failures\.(\w+)`", one(r"Failure policies: ([^\n]+)")[0])
    steps = re.findall(
        r"`(node_to_node_capacity_matrix_\d)`", one(r"Workflow steps: ([^\n]+)")[0]
    )
    assert [step.name for step in workflow] == steps
    assert [step.failure_policy for step in workflow] == listed


def one_policy_rules(head, name):
    [mode] = head.scenario.failure_policies[name].modes
    return mode.rules


def test_backbone_header():
    head = Header("backbone_clos.yml")
    network, workflow = head.scenario.network, head.scenario.workflow
    metros, pops, leaves, spines, clos_metros, routers_per_pop, others = (
        head.read("backbone of (\\w+)")
        + head.read("(\\w+) PoPs each")
        + head.read("(\\d+) leaves")
        + head.read("(\\d+) spines")
        + head.read("in (\\w+) metros")
        + head.read("(\\w+) core router")
        + head.read("other (\\w+)")
    )
    by_metro = Counter(name.split("/")[0] for name in network.nodes)
    assert len(by_metro) == number(metros)
    pop_names = {"/".join(n.split("/")[:2]) for n in network.nodes if "/pop" in n}
    assert Counter(p.split("/")[0] for p in pop_names) == {
        m: number(pops) for m in by_metro
    }
    clos_pops = {
        p for p in pop_names if any(n.startswith(p + "/leaf/") for n in network.nodes)
    }
    for pop in clos_pops:
        assert sum(n.startswith(pop + "/leaf/") for n in network.nodes) == int(leaves)
        assert sum(n.startswith(pop + "/spine/") for n in network.nodes) == int(spines)
    clos_metro_names = {p.split("/")[0] for p in clos_pops}
    assert len(clos_metro_names) == number(clos_metros)
    routers = pop_names - clos_pops
    for pop in routers:
        inside = [n for n in network.nodes if n.startswith(pop + "/")]
        assert len(inside) == number(routers_per_pop)
        assert all(network.nodes[n].attrs["role"] == "core" for n in inside)
    assert len({p.split("/")[0] for p in routers}) == number(others)
    dcs = [n for n in network.nodes if "/dc" in n]
    assert sorted(n.split("/")[0] for n in dcs) == sorted(
        clos_metro_names
    )  # a DC region in each
    (per,) = head.read("(\\w+) risk group")
    adjacency = {link.attrs.get("adjacency_id") for link in network.links.values()} - {
        None
    }
    assert len(network.risk_groups) == number(per) * len(adjacency)
    (draws,) = head.read("(\\d+) draws")
    placement = next(s for s in workflow if s.name == "tm_placement")
    assert placement.iterations == int(draws)
    modes = head.scenario.failure_policies[placement.failure_policy].modes
    assert len(modes) > 1 and len({m.weight for m in modes}) > 1


# Worked examples written inline in the rules


def placed_flows(text, step=0):
    prepared = prepare(Scenario.from_yaml(text))
    state = converged(run(prepared), step=step)
    vector = state.rows[0].result.edge_flows
    return (flows(prepared, vector) if vector is not None else None), state


def fan_out(capacities, volume, preset):
    links = "\n".join(
        f"    - {{source: S, target: X{i}, capacity: {c}}}\n    - {{source: X{i}, target: T, capacity: {c}}}"
        for i, c in enumerate(capacities, 1)
    )
    nodes = ", ".join(f"X{i}: {{}}" for i in range(1, len(capacities) + 1))
    return f"""
units: {{resolution: 1}}
network:
  nodes: {{S: {{}}, T: {{}}, {nodes}}}
  links:
{links}
demands:
  d: [{{source: ^S$, target: ^T$, volume: {volume}, preset: {preset}}}]
workflow:
  - {{type: TrafficMatrixPlacement, name: p, demand_set: d, outputs: {{edge_flows: true}}}}
"""


def test_the_splitting_rules_worked_examples():
    """Units: "10 over 3 members gives 4, 3, 3"; "5 over weights 2 and 1 gives 4 and 1";
    "an amount of 10.5 units becomes 11"."""
    total, members, *equal = ints(
        numbers(
            (ROOT / CONCEPTS).read_text(),
            "(\\d+) over (\\d+) members gives (\\d+), (\\d+), (\\d+)",
        )
    )
    found, _ = placed_flows(fan_out([100] * int(members), total, "SHORTEST_PATHS_ECMP"))
    assert [found[f"S|X{i}|0"] for i in range(1, int(members) + 1)] == equal
    total, w1, w2, *weighted = ints(
        numbers(
            (ROOT / CONCEPTS).read_text(),
            "(\\d+) over weights (\\d+) and (\\d+) gives (\\d+) and (\\d+)",
        )
    )
    # SHORTEST_PATHS_WCMP weighs each next hop by its link's capacity.
    found, _ = placed_flows(fan_out([100 * w1, 100 * w2], total, "SHORTEST_PATHS_WCMP"))
    assert [found["S|X1|0"], found["S|X2|0"]] == weighted
    amount, rounded = ints(
        numbers((ROOT / CONCEPTS).read_text(), "([\\d.]+) units becomes (\\d+)")
    )
    assert ngc.to_units(float(amount), 1.0) == rounded


def test_the_alpha_and_expansion_worked_examples():
    """Demands: "1.05 at alpha 2.5 is 2.625, 11 units at q = 0.25, not 2.5 × 4 units";
    "At q = 1, a parent of 10 split into two groups and the second into three gives 5
    and (2, 2, 1)"."""
    text = (ROOT / CONCEPTS).read_text()
    volume, alpha, scaled, units, q, alpha_again, per_unit = (
        numbers(text, "([\\d.]+) at alpha ([\\d.]+) is")
        + numbers(text, "is ([\\d.]+), (\\d+) units")
        + numbers(text, "units at `q` = ([\\d.]+)")
        + numbers(text, "([\\d.]+) × (\\d+) units")
    )
    assert float(volume) * float(alpha) == float(scaled) and alpha == alpha_again
    assert ngc.to_units(float(volume), float(q)) == int(per_unit)
    scenario_text = f"""
units: {{resolution: {q}}}
network:
  nodes: {{A: {{}}, B: {{}}}}
  links: [{{source: A, target: B, capacity: 100}}]
demands:
  d: [{{source: ^A$, target: ^B$, volume: {volume}}}]
workflow:
  - {{type: TrafficMatrixPlacement, name: p, demand_set: d, alpha: {alpha}}}
"""
    _, state = placed_flows(scenario_text)
    assert (
        state.totals.reference_request_units
        == int(units)
        != float(alpha) * int(per_unit)
    )
    q, parent, groups, members, first, *second = (
        numbers(text, "`q` = (\\d+), a parent")
        + numbers(text, "parent of (\\d+)")
        + numbers(text, "into (\\w+) groups")
        + numbers(text, "second into (\\w+)")
        + numbers(text, "(\\d+) and \\((\\d+), (\\d+), (\\d+)\\)")
    )
    assert (number(groups), number(members)) == (2, len(second))
    nodes = ["g1/a", *(f"g2/{n}" for n in "abc"[: number(members)])]
    expansion = f"""
units: {{resolution: {q}}}
network:
  nodes: {{{", ".join(f"{n}: {{}}" for n in nodes)}, T: {{}}}}
  links: [{", ".join(f"{{source: {n}, target: T}}" for n in nodes)}]
demands:
  d: [{{source: '^(g1|g2)/', target: '^T$', volume: {parent}, mode: pairwise, group_mode: group_pairwise}}]
"""
    prepared = prepare(Scenario.from_yaml(expansion), demand_sets=("d",))
    shares = [d.nominal_units for d in prepared.demand_sets["d"].demands]
    assert shares == [int(first), *map(int, second)]


def test_the_failure_coverage_figure():
    """Failures: "`n` × ln(`n`/ε) draws, rounded up, miss some link with chance at most ε:
    32 draws for 5 links at ε = 1 %"; and the stated draws do cover the five links of a
    seeded ring, while `n` draws there miss one."""
    draws, links, percent = map(
        int,
        (
            stated(CONCEPTS, "(\\d+) draws")
            + stated(CONCEPTS, "(\\d+) links at")
            + stated(CONCEPTS, "ε = (\\d+) %")
        ),
    )
    epsilon = percent / 100
    assert draws == math.ceil(links * math.log(links / epsilon))
    missed = sum(
        (-1) ** (k + 1) * math.comb(links, k) * (1 - k / links) ** draws
        for k in range(1, links)
    )
    assert missed <= epsilon
    names = [f"N{i}" for i in range(links)]
    ring = "\n".join(
        f"    - {{source: {a}, target: {b}, capacity: 1}}"
        for a, b in zip(names, names[1:] + names[:1], strict=True)
    )

    def failure_cases(iterations):
        text = f"""
seed: 1
network:
  nodes: {{{", ".join(f"{n}: {{}}" for n in names)}}}
  links:
{ring}
failures:
  one: {{modes: [{{weight: 1, rules: [{{scope: link, mode: choice, count: 1}}]}}]}}
workflow:
  - {{type: MaxFlow, name: m, source: ^N0$, target: ^N2$, failure_policy: one,
     iterations: {iterations}}}
"""
        cases = run(prepare(Scenario.from_yaml(text))).steps[0].result.cases
        return len(cases) - 1

    assert failure_cases(draws) == links > failure_cases(links)


def test_the_seed_and_weight_approximation_figures():
    """DSL: scenario seed 42 and policy random_link yield 2099469712; volumes 1000 and 0.1
    are apportioned and reported, 1000000 and 1 stay exact."""
    page = "docs/reference/dsl.md"
    seed, name, derived = (
        stated(page, "scenario seed `(\\d+)`")
        + stated(page, "policy `(\\w+)` yield")
        + stated(page, "yield `(\\d+)`")
    )
    value = Scenario.from_yaml(
        f"seed: {seed}\nfailures:\n  {name}:\n    modes: [{{weight: 1, rules: [{{scope: link, mode: choice}}]}}]\n"
    )
    assert value.failure_policies[name].seed == int(derived)
    a, b, power, c, d = (
        stated(page, "volumes ([\\d.]+) and ([\\d.]+)")
        + stated(page, "2\\^(\\d+) denominator")
        + stated(page, "while (\\d+) and (\\d+)")
    )
    assert Fraction(float(b)).denominator == 2 ** int(power)

    def approximations(first, second):
        text = f"""
units: {{resolution: 1}}
network:
  nodes: {{A: {{}}, B: {{}}, M: {{}}, t: {{}}}}
  links:
    - {{source: A, target: M, capacity: 1000000000}}
    - {{source: B, target: M, capacity: 1000000000}}
    - {{source: M, target: t, capacity: 1000000000}}
routing:
  igp_domain: {{path: '^M$'}}
  bgp_edge: {{path: '^(A|B|t)$'}}
wcmp_controller: {{scope: all_routers}}
demands:
  d:
    - {{source: ^A$, target: ^t$, volume: {first}, preset: SHORTEST_PATHS_WCMP}}
    - {{source: ^B$, target: ^t$, volume: {second}, preset: SHORTEST_PATHS_WCMP}}
"""
        prepared = prepare(Scenario.from_yaml(text), demand_sets=("d",))
        return [w.label for w in prepared.units_report.weight_approximations]

    assert approximations(a, b) == ["controller.d.t.source.B"]
    assert approximations(c, d) == []
