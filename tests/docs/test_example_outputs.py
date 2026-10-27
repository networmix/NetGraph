"""What the pages say their YAML and Python examples produce.

Each test names the page and the statement it checks; the example is read from the page,
so an edit of the example or of its stated result fails here. A fragment that is only
syntax gets the smallest network that makes its stated result observable.
"""

import re
from dataclasses import fields

import netgraph_core as ngc
import pytest
import yaml

from ngraph import (
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Scenario,
    prepare,
    run,
)
from ngraph.analysis.failures import failure_cases
from ngraph.dsl.expansion.brackets import expand_name_patterns
from ngraph.workflow import MaximumSupportedDemand, TrafficMatrixPlacement
from tests.docs.pages import ROOT, fence, fences, names, numbers, saved_files, stated

DSL = "docs/reference/dsl.md"
TUTORIAL = "docs/getting-started/tutorial.md"
CLOS = "docs/examples/clos-fabric.md"
BASIC = "docs/examples/basic.md"
WORDS = {"one": 1, "two": 2, "three": 3}


def converged(analysis, case=0):
    return analysis.cases[case].states["converged"]


def scenario(page, excerpt):
    return Scenario.from_yaml(fence(page, excerpt).text)


def nodes(page, excerpt):
    return list(scenario(page, excerpt).network.nodes)


def nodes_of(text):
    return list(Scenario.from_yaml(text).network.nodes)


def links(page, excerpt):
    return list(scenario(page, excerpt).network.links)


def run_python(page, upto):
    """The namespace after a page's first `upto` Python examples."""
    namespace = {"__name__": "__documented_client__"}
    for block in [f for f in fences(page) if f.lang == "python"][:upto]:
        exec(compile(block.text, f"{page}:{block.line}", "exec"), namespace)
    return namespace


# README.md


def test_the_readme_scenario_is_the_bundled_file():
    """README: "(this is `scenarios/readme_example.yml`)"."""
    shown = fence("README.md", "blueprints:").text
    assert shown == (ROOT / "scenarios/readme_example.yml").read_text()


# Tutorial


def test_the_tutorial_results_are_the_ones_its_text_states():
    """Tutorial, Read results: physical capacity 10, cut at A→B, route cost 3; either
    single-link failure disconnects A from C; at most two patterns plus the baseline,
    occurrences summing to 20; the placement uses the alpha MSD found."""
    text = saved_files()["example.yaml"]
    amount, tail, head, cost = (
        stated(TUTORIAL, r"physical capacity (\d+)")
        + stated(TUTORIAL, r"cut at (\w)→(\w)")
        + stated(TUTORIAL, r"route cost (\d+)")
    )
    (patterns,) = stated(TUTORIAL, r"(\w+) failure patterns")
    (draws,) = stated(TUTORIAL, r"`occurrences` sum to (\d+)")
    prepared = prepare(Scenario.from_yaml(text))
    q = prepared.topology.q
    capacity, msd, placement = (step.result for step in run(prepared).steps)
    row = converged(capacity).rows[0]
    assert row.result.delivered * q == int(amount)
    refs = prepared.topology.edge_refs
    assert [(refs[e].link, refs[e].direction) for e in row.result.min_cut] == [
        (f"{tail}|{head}|0", "forward")
    ]
    assert [piece.marginal_cost for piece in row.cost_distribution.bins] == [int(cost)]
    baseline, *failed = placement.cases
    assert 1 <= len(failed) <= WORDS[patterns]
    assert placement.metadata.sampling.iterations == int(draws)
    assert sum(case.case.occurrences for case in placement.cases) == int(draws)
    for case in failed:
        assert (
            converged(placement, placement.cases.index(case)).totals.delivered_units
            == 0
        )
    assert placement.query.alpha_from_step == "supported_load"
    assert placement.alpha == msd.alpha_feasible
    # "alpha_tolerance, 0.01 by default": the tutorial omits it.
    assert msd.query.alpha_tolerance == 0.01


# Basic Example


def test_the_basic_example_states_wcmp_and_the_cost_objective():
    """Basic Example: capacity-weighted splitting carries the full 3 on the cheap route;
    the minimum-cost objective is 18."""
    from ngraph import CapacityQuery, capacity

    (carried,) = stated(BASIC, r"full (\d+)")
    (objective,) = stated(BASIC, r"objective[^=]+= (\d+)")
    space = run_python(BASIC, 3)
    prepared, source, target = space["prepared"], space["source"], space["target"]
    weighted = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.CAPACITY,
        )
    )
    answer = capacity(prepared, CapacityQuery(source, target, config=weighted))
    assert converged(answer).rows[0].result.delivered == int(carried)
    assert space["row"].result.total_cost == int(objective)


# Clos Fabric


def test_the_clos_fabric_has_its_stated_links_and_cut_for_every_named_preset():
    """Clos Fabric: 18 physical links; with SHORTEST_PATHS_WCMP, SHORTEST_PATHS_MAXFLOW or
    TE_MAXFLOW_UNLIM the symmetric baseline is bounded by the same inter-site cut, 100."""
    text = saved_files()["clos.yaml"]
    (count,) = stated(CLOS, r"(\d+) physical links")
    (cut,) = stated(CLOS, r"delivery to (\d+)")
    assert len(Scenario.from_yaml(text).network.links) == int(count)
    step = "    preset: SHORTEST_PATHS_ECMP\n    failure_policy"
    assert text.count(step) == 1
    for preset in ("SHORTEST_PATHS_WCMP", "SHORTEST_PATHS_MAXFLOW", "TE_MAXFLOW_UNLIM"):
        changed = text.replace(step, f"    preset: {preset}\n    failure_policy")
        prepared = prepare(Scenario.from_yaml(changed))
        analysis = run(prepared).steps[1].result
        assert analysis.query.declaration.name == preset
        delivered = converged(analysis).rows[0].result.delivered
        assert delivered == ngc.to_units(int(cut), prepared.topology.q), preset


# Bundled scenarios


@pytest.mark.parametrize(
    ("path", "steps", "policies", "demand_sets"),
    [
        (
            "square_mesh.yaml",
            ["msd_baseline", "tm_placement", "node_to_node_capacity_matrix"],
            ["single_link_failure"],
            ["baseline_traffic_matrix"],
        ),
        (
            "readme_example.yml",
            ["max_demand", "placement_at_max"],
            ["random_link"],
            ["global_traffic"],
        ),
        (
            "backbone_clos.yml",
            ["network_statistics", "msd_baseline", "tm_placement", "cost_power"],
            ["weighted_modes"],
            ["baseline_traffic_matrix"],
        ),
        (
            "nsfnet.yaml",
            [
                "node_to_node_capacity_matrix_1",
                "node_to_node_capacity_matrix_2",
                "node_to_node_capacity_matrix_3",
            ],
            [
                "assumed_random_failures",
                "single_connection_failure",
                "single_link_failure",
            ],
            [],
        ),
    ],
)
def test_each_bundled_scenario_has_the_parts_its_page_lists(
    path, steps, policies, demand_sets
):
    """Bundled Scenarios: each section's step names, failure policies and demand sets,
    and an opening comment in each file."""
    text = (ROOT / "scenarios" / path).read_text()
    value = Scenario.from_yaml(text)
    assert [step.name for step in value.workflow] == steps
    assert sorted(value.failure_policies) == policies
    assert sorted(value.demand_sets) == demand_sets


def test_square_mesh_is_the_smallest_bundled_scenario():
    sizes = {
        path.name: len(Scenario.from_yaml(path.read_text()).network.nodes)
        for path in sorted((ROOT / "scenarios").iterdir())
    }
    assert min(sizes, key=sizes.get) == "square_mesh.yaml"
    assert sorted(sizes.values()).count(sizes["square_mesh.yaml"]) == 1


def test_the_bundled_scenario_headers_state_their_structure():
    """The opening comments' structure (their figures: test_narrated_answers.py): nsfnet's
    core sites on circuit pairs, each pair one risk group, end sites on single circuits;
    backbone_clos's risk group per adjacency and its CostPower rows per metro and per PoP."""
    nsf = Scenario.from_yaml((ROOT / "scenarios/nsfnet.yaml").read_text()).network
    kinds = {name: node.attrs["site_type"] for name, node in nsf.nodes.items()}
    pairs = {}
    for link in nsf.links.values():
        ends = tuple(sorted((link.source, link.target)))
        pairs.setdefault(ends, []).append(tuple(link.risk_groups))
    for ends, groups in pairs.items():
        if all(kinds[end] == "core" for end in ends):
            assert len(groups) == 2 and groups[0] == groups[1] and len(groups[0]) == 1
        else:
            assert groups == [()], ends
    assert len(nsf.risk_groups) == sum(
        all(kinds[e] == "core" for e in ends) for ends in pairs
    )
    backbone = Scenario.from_yaml((ROOT / "scenarios/backbone_clos.yml").read_text())
    network = backbone.network
    adjacency = {
        link.attrs["adjacency_id"]
        for link in network.links.values()
        if "adjacency_id" in link.attrs
    }
    assert set(network.risk_groups) == {f"corridor_risk_{a}" for a in adjacency}
    assert {a.split(":")[0] for a in adjacency} == {
        "inter_metro",
        "intra_metro",
        "dc_to_pop",
    }
    rows = run(prepare(backbone)).steps[3].result
    metros = sorted({name.split("/")[0] for name in network.nodes})
    pops = sorted({"/".join(n.split("/")[:2]) for n in network.nodes if "/pop" in n})
    assert list(rows.levels) == [0, 1, 2]
    assert [row.path for row in rows.levels[1]] == metros
    assert [row.path for row in rows.levels[2]] == pops


def test_the_vscode_settings_name_the_packaged_schema_and_the_scenarios():
    """Schemas, IDE Integration: the settings parse, and their paths exist here."""
    import json

    settings = json.loads(
        fence("docs/reference/schemas.md", "yaml.schemas", lang="json").text
    )
    [(schema, globs)] = settings["yaml.schemas"].items()
    assert (ROOT / schema).is_file()
    assert all(list(ROOT.glob(pattern)) for pattern in globs)


# Workflow Steps


def test_the_msd_example_shows_the_defaults():
    """Workflow Steps, MaximumSupportedDemand: "the example shows the defaults"."""
    shown = yaml.safe_load(fence("docs/reference/workflow.md", "alpha_start").text)
    step = shown["workflow"][0]
    defaults = {f.name: f.default for f in fields(MaximumSupportedDemand)}
    keys = set(step) - {"type", "name", "demand_set"}
    assert len(keys) == 7
    assert {key: step[key] for key in keys} == {key: defaults[key] for key in keys}


def test_the_placement_example_keys_have_their_stated_defaults():
    defaults = {f.name: f.default for f in fields(TrafficMatrixPlacement)}
    assert (defaults["interaction"], defaults["workers"]) == ("ordered", "auto")


# Scenario YAML


def test_capturing_groups_create_the_stated_labels():
    """DSL, Capturing groups: the text example's labels for one and three groups."""
    text = fence(DSL, "Creates groups", lang="text").text
    one, three = numbers(
        text, r'Single group:[^\n]*\n# Creates groups: ("[^"]+"(?:, "[^"]+")*)'
    ) + numbers(
        text, r'Multiple groups:[^\n]*\n# Creates groups: ("[^"]+"(?:, "[^"]+")*)'
    )
    network = Scenario.from_yaml(
        "network:\n  nodes: {dc1/spine/switch-1: {}, dc1/leaf/switch-2: {}, dc2/leaf/switch-1: {}}\n"
    ).network
    by_one = list(network.select_node_groups_by_path(r"(dc\d+)"))
    by_three = list(
        network.select_node_groups_by_path(r"(dc\d+)/(spine|leaf)/switch-(\d+)")
    )
    assert re.findall(r'"([^"]+)"', one) == by_one[:2]
    assert re.findall(r'"([^"]+)"', three) == by_three[:2]


def creates(excerpt):
    """The names on the `Creates:` line after the DSL fence that contains the excerpt."""
    block = fence(DSL, excerpt)
    after = (
        (ROOT / DSL).read_text().splitlines()[block.line + block.text.count("\n") + 1 :]
    )
    line = next(x for x in after if x.strip())
    assert line.startswith("Creates: "), line
    return names(line), "..." in line


def test_node_groups_create_the_stated_names():
    shown, elided = creates('template: "leaf-{n}"\n      attrs:\n        role: "leaf"')
    assert not elided
    assert (
        nodes(DSL, 'template: "leaf-{n}"\n      attrs:\n        role: "leaf"') == shown
    )
    shown, elided = creates('template: "tor-{n}"')
    found = nodes(DSL, 'template: "tor-{n}"')
    assert elided and found[:2] == shown[:2] and found[-2:] == shown[-2:]
    group, *made = names(stated(DSL, r"(`leaf: \{count: 2\}`[^)]*)")[0])
    assert nodes_of("network:\n  nodes: {%s}\n" % group) == made


def comment_number(excerpt, pattern):
    (value,) = numbers(fence(DSL, excerpt).text, pattern)
    return int(value)


def test_link_definitions_create_the_stated_links():
    """DSL: every leaf to every spine; every spine to every other spine, with the stated
    parallel links per pair; the attribute-filtered and the OR examples."""
    shown = nodes(DSL, "capacity: 3200")
    leaves = [n for n in shown if n.startswith("leaf/")]
    spines = [n for n in shown if n.startswith("spine/")]
    parallel = comment_number("capacity: 3200", r"(\d+) parallel")
    assert links(DSL, "capacity: 3200") == [
        *(f"{a}|{b}|0" for a in leaves for b in spines),
        *(f"{spines[0]}|{spines[1]}|{i}" for i in range(parallel)),
    ]
    assert links(DSL, 'path: "/leaf"') == [
        f"leaf/leaf-{a}|spine/spine-{b}|0" for a in (1, 2) for b in (1, 2)
    ]
    assert links(DSL, 'path: "/metro1/dc[1-1]"') == [
        "metro1/dc1|metro1/pop1|0",
        "metro1/dc1|metro1/pop2|0",
    ]


def test_bracket_expansion_creates_the_stated_names():
    text = fence(DSL, "dc[1-3]/rack[a,b]:").text
    (shown,) = numbers(text, r"# Creates (\w+/\w+(?:, \w+/\w+)*)")
    groups = sorted(
        {name.rsplit("/", 1)[0] for name in nodes(DSL, "dc[1-3]/rack[a,b]:")}
    )
    assert groups == [f"dc{d}/rack{r}" for d in (1, 2, 3) for r in "ab"]
    assert groups[: len(shown.split(", "))] == shown.split(", ")
    fragment = fence(DSL, "dc[1-2]/rack[a,b]: {}").text  # a fragment of network.nodes
    (shown,) = numbers(fragment, r"# Creates: ([^\n]+)")
    wrapped = "network:\n  nodes:\n" + "".join(
        f"    {line}\n" for line in fragment.splitlines()
    )
    assert nodes_of(wrapped) == shown.split(", ")
    single, *made = names(stated(DSL, r"(`SEA\[1-2\]: \{\}`[^)]*)")[0])
    assert nodes_of("network: {nodes: {'%s': {}}}" % single.split(":")[0]) == made
    expansion = scenario(DSL, "DC[1-3]_Power")
    assert list(expansion.network.risk_groups) == [
        "DC1_Power",
        "DC2_Power",
        "DC3_Power",
        "RG1",
        "RG2",
        "RG3",
    ]
    assert expansion.network.nodes["Server"].risk_groups == {"RG1", "RG2", "RG3"}
    # The limitations table: pattern -> what it produces.
    assert expand_name_patterns("n[01-03]") == ["n1", "n2", "n3"]
    assert expand_name_patterns("n[01,02,03]") == ["n01", "n02", "n03"]
    assert expand_name_patterns("n[1-10]") == [f"n{i}" for i in range(1, 11)]
    assert expand_name_patterns("n[A,B,C]") == ["nA", "nB", "nC"]
    with pytest.raises(ValueError):
        Scenario.from_yaml("network: {nodes: {'n[A-C]': {}}}")


def test_variable_expansion_creates_the_stated_link_definitions():
    """DSL, Example in links: the stated cartesian and zip counts; and the attrs example:
    `${dc}` substituted in nested attrs."""
    excerpt = 'source: "plane${p}/rack${r}"'
    cartesian = comment_number(excerpt, r"(\d+) link definitions")
    zipped = comment_number(excerpt, r"# (\d+) paired link definitions")
    fragment = fence(DSL, excerpt).text
    ends = [f"plane{p}/rack{r}" for p in (1, 2) for r in "ab"]
    ends += [f"spine{s}" for s in (1, 2, 3)]
    ends += [f"{kind}{i}" for kind in ("server", "switch") for i in (1, 2, 3, 4)]
    found = links_of(
        "network:\n  nodes: {%s}\n%s"
        % (", ".join(f"{name}: {{}}" for name in ends), indent(fragment))
    )
    assert len(found) == cartesian + zipped
    assert found[-zipped:] == [f"server{i}|switch{i}|0" for i in (1, 2, 3, 4)]
    fragment = fence(DSL, 'datacenter: "${dc}"').text
    ends = [f"dc{d}/{kind}" for d in (1, 2) for kind in ("leaf", "spine")]
    network = Scenario.from_yaml(
        "network:\n  nodes: {%s}\n%s"
        % (", ".join(f"{name}: {{}}" for name in ends), indent(fragment))
    ).network
    assert {k: dict(v.attrs) for k, v in network.links.items()} == {
        f"dc{d}/leaf|dc{d}/spine|0": {
            "datacenter": f"dc{d}",
            "corridor": f"dc{d}_internal",
        }
        for d in (1, 2)
    }


def test_cartesian_expansion_over_symmetric_lists_creates_both_orientations():
    """DSL, Cartesian expansion and reversed pairs: `a: [1, 2], b: [1, 2]` creates both
    orientations as parallel links; one mesh over a regex deduplicates them."""
    base = "network:\n  nodes: {dc1/gw: {}, dc2/gw: {}}\n  links:\n"
    both = links_of(
        base
        + '    - {source: "dc${a}/gw", target: "dc${b}/gw", pattern: mesh,\n'
        + "       expand: {vars: {a: [1, 2], b: [1, 2]}}}\n"
    )
    assert both == ["dc1/gw|dc2/gw|0", "dc2/gw|dc1/gw|0"]
    once = links_of(
        base + '    - {source: "dc[0-9]+/gw", target: "dc[0-9]+/gw", pattern: mesh}\n'
    )
    assert once == ["dc1/gw|dc2/gw|0"]


def test_blueprint_parameters_give_the_stated_names_and_counts():
    """DSL, blueprints: the stated instance names and override; the nested override of
    the spine count; the dotted form is refused."""
    shown = names(stated(DSL, r"group name: ([^\n]+)")[0])
    text = fence(DSL, "leaf.count: 6").text
    declared = yaml.safe_load(text)
    blueprint = declared["blueprints"]["leaf_spine"]["nodes"]
    found = nodes_of(text)
    assert set(shown) <= set(found)
    override = declared["network"]["nodes"]["pod2"]["params"]["leaf.count"]
    assert sum(name.startswith("pod2/leaf/") for name in found) == override
    assert (
        sum(name.startswith("pod1/leaf/") for name in found)
        == blueprint["leaf"]["count"]
    )
    text = fence(DSL, "pod1.params:").text
    declared = yaml.safe_load(text)
    spines = declared["blueprints"]["leaf_spine"]["nodes"]["spine"]["count"]
    override = declared["network"]["nodes"]["dc1"]["params"]["pod1.params"][
        "spine.count"
    ]
    found = nodes_of(text)
    assert sum(name.startswith("dc1/pod1/spine/") for name in found) == override
    assert (
        sum(name.startswith("dc1/pod2/spine/") for name in found) == spines != override
    )
    (dotted_key,) = names(stated(DSL, r"dotted form (`[^`]+`)")[0])
    params = yaml.safe_load(text)["network"]["nodes"]["dc1"]["params"]
    [(outer, inner)] = params.items()
    assert dotted_key == f"{outer}.{next(iter(inner))}"  # the same override, dotted
    dotted = re.sub(
        r"pod1\.params:.*\n\s+spine\.count: (\d+)", rf"{dotted_key}: \1", text
    )
    assert dotted != text
    with pytest.raises(ValueError):
        Scenario.from_yaml(dotted)


def test_a_failed_risk_group_fails_the_stated_members():
    """DSL, Entity references: what failing each named group fails."""
    seattle = stated(DSL, r"(`Site_Seattle`[^;]+)")[0]
    region = stated(DSL, r"(`Region_West`[^\n]+)")[0]
    prepared = prepare(scenario(DSL, "Router_PDX: {risk_groups"))

    def failed(group):
        policy = FailurePolicy(
            modes=[FailureMode(1, [FailureRule("risk_group", path=f"^{group}$")])]
        )
        _, case = failure_cases(prepared, FailureRequest(policy, iterations=1, seed=1))
        return sorted((*case.pattern.excluded_nodes, *case.pattern.excluded_links))

    for part in (seattle, region):
        group, *members = names(part)
        assert failed(group) == sorted(members), part


def test_yaml_anchors_merge_with_explicit_keys_winning():
    found = scenario(DSL, "default_cap: &cap").network.nodes
    assert dict(found["spine-1"].attrs) == {
        "cost": 100,
        "region": "dc1",
        "power_budget": 2500,
        "capacity": 10000,
        "hardware": {"component": "SpineRouter", "count": 1},
    }
    assert found["spine-2"].attrs["region"] == "dc2"


def test_demand_expansion_creates_the_stated_demands():
    """DSL, Variable Expansion in Demands: the stated cartesian and zip counts."""
    combinations = comment_number("src_dc:", r"(\d+) combinations")
    zipped = comment_number("src_dc:", r"(\d+) demands")
    found = scenario(DSL, "src_dc:").demand_sets["inter_dc"].demands
    pairs = [(d.source.path, d.target.path) for d in found]
    assert len(pairs) == combinations + zipped == len(set(pairs))
    assert pairs == [
        *((f"^dc{s}/.*", f"^dc{t}/.*") for t in (3, 4) for s in (1, 2)),
        *((f"^dc{i}/leaf/.*", f"^dc{i}/spine/.*") for i in (1, 2, 3)),
    ]
    assert all(source != target for source, target in pairs)


def test_group_pairwise_creates_one_demand_per_ordered_pair_of_labels():
    """DSL, Example with group_mode: the stated label pairs, and every other ordered one."""
    fragment = fence(DSL, "inter_dc_traffic:").text
    (shown,) = numbers(fragment, r"# Creates (\w+->\w+(?:, \w+->\w+)*)")
    text = "network:\n  nodes: {%s}\n%s" % (
        ", ".join(f"dc{i}/r: {{attrs: {{dc: dc{i}}}}}" for i in (1, 2, 3)),
        fragment,
    )
    prepared = prepare(Scenario.from_yaml(text), demand_sets=("inter_dc_traffic",))
    pairs = [
        (
            d.endpoints.sources[0].split("/")[0],
            d.endpoints.destinations[0].split("/")[0],
        )
        for d in prepared.demand_sets["inter_dc_traffic"].demands
    ]
    assert sorted(pairs) == [
        (a, b) for a in ("dc1", "dc2", "dc3") for b in ("dc1", "dc2", "dc3") if a != b
    ]
    assert {tuple(pair.split("->")) for pair in shown.split(", ")} <= set(pairs)


def test_the_overview_grouped_pairwise_demand_pairs_nodes_of_different_datacenters():
    """DSL, `demands` overview: "Node pairs between different datacenters", on a network
    with two nodes in one datacenter (pairwise within one datacenter would overlap)."""
    fragment = fence(DSL, "production:").text
    names = {"dc1/a": "dc1", "dc1/b": "dc1", "dc2/a": "dc2"}
    text = "network:\n  nodes: {%s}\n%s" % (
        ", ".join(f"{n}: {{attrs: {{dc: {dc}}}}}" for n, dc in names.items()),
        fragment,
    )
    prepared = prepare(Scenario.from_yaml(text), demand_sets=("production",))
    pairs = [
        (d.endpoints.sources, d.endpoints.destinations)
        for d in prepared.demand_sets["production"].demands
        if d.base_id == "production|1"
    ]
    assert sorted(pairs) == sorted(
        ((a,), (b,)) for a in names for b in names if names[a] != names[b]
    )


def test_the_all_pairs_matrix_has_its_stated_pairs_and_shares():
    """DSL, Traffic Modes: "12 ordered pairs of distinct sites, 48 / 12 = 4 each"."""
    block = fence(DSL, '"^(A|B|C|D)$"').text
    pairs, total, over, each = (
        int(g)
        for g in (
            numbers(block, r"(\d+) ordered pairs")
            + numbers(block, r", (\d+) / (\d+) = (\d+)")
        )
    )
    [declared] = yaml.safe_load(block)["demands"]["matrix"]
    assert declared["volume"] == total and over == pairs and total / over == each
    prepared = prepare(Scenario.from_yaml(block))
    rows = converged(run(prepared).steps[0].result).rows
    sites = list(yaml.safe_load(block)["network"]["nodes"])
    assert sorted((r.endpoints.sources, r.endpoints.destinations) for r in rows) == [
        ((a,), (b,)) for a in sites for b in sites if a != b
    ]
    assert len(rows) == pairs
    q = prepared.topology.q
    assert {r.reference_request_units * q for r in rows} == {each}


def indent(fragment):
    return "".join(f"  {line}\n" for line in fragment.splitlines())


def links_of(text):
    return list(Scenario.from_yaml(text).network.links)
