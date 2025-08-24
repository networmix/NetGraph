from __future__ import annotations

from collections import defaultdict

from ngraph.algorithms.base import FlowPlacement
from ngraph.scenario import Scenario


def build_scenario() -> Scenario:
    scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 8
        name_template: t1-{node_num}
      t2:
        node_count: 8
        name_template: t2-{node_num}

    adjacency:
      - source: /t1
        target: /t2
        pattern: mesh
        link_params:
          capacity: 2
          cost: 1

  3tier_clos:
    groups:
      b1:
        use_blueprint: brick_2tier
      b2:
        use_blueprint: brick_2tier
      spine:
        node_count: 64
        name_template: t3-{node_num}

    adjacency:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1

network:
  name: "3tier_clos_network"
  version: 1.0

  groups:
    my_clos1:
      use_blueprint: 3tier_clos

    my_clos2:
      use_blueprint: 3tier_clos

  adjacency:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      link_count: 4
      link_params:
        capacity: 1
        cost: 1
"""
    return Scenario.from_yaml(scenario_yaml)


def make_uneven_parallel_caps(scenario: Scenario) -> None:
    net = scenario.network
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for link in net.links.values():
        s, t = link.source, link.target
        if (s.startswith("my_clos1/spine") and t.startswith("my_clos2/spine")) or (
            s.startswith("my_clos2/spine") and t.startswith("my_clos1/spine")
        ):
            groups[(s, t)].append(link)

    for idx, key in enumerate(sorted(groups.keys())):
        links = sorted(groups[key], key=lambda lk: (lk.source, lk.target, id(lk)))
        # Create heavy imbalance among the four parallel links
        caps = [4.0, 0.25, 0.25, 0.25] if idx % 2 == 0 else [2.0, 1.0, 0.5, 0.25]
        for lk, cap in zip(links, caps, strict=False):
            lk.capacity = cap


def main() -> None:
    scenario = build_scenario()
    network = scenario.network

    base_ecmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )
    base_wcmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.PROPORTIONAL,
    )
    v_base_ecmp = float(next(iter(base_ecmp.values())))
    v_base_wcmp = float(next(iter(base_wcmp.values())))
    print("Baseline ECMP:", v_base_ecmp)
    print("Baseline WCMP:", v_base_wcmp)

    make_uneven_parallel_caps(scenario)

    ecmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.EQUAL_BALANCED,
    )
    wcmp = network.max_flow(
        source_path=r"my_clos1.*(b[0-9]*)/t1",
        sink_path=r"my_clos2.*(b[0-9]*)/t1",
        mode="combine",
        shortest_path=True,
        flow_placement=FlowPlacement.PROPORTIONAL,
    )
    v_ecmp = float(next(iter(ecmp.values())))
    v_wcmp = float(next(iter(wcmp.values())))
    print("Uneven ECMP:", v_ecmp)
    print("Uneven WCMP:", v_wcmp)
    assert v_wcmp >= v_ecmp


if __name__ == "__main__":
    main()
