def test_max_flow_variants():
    """
    Tests max flow calculations on a graph with parallel edges.

    Graph topology (costs/capacities):

                 [1,1] & [1,2]     [1,1] & [1,2]
          A ──────────────────► B ─────────────► C
          │                                      ▲
          │    [2,3]                             │ [2,3]
          └───────────────────► D ───────────────┘

    Edges:
      - A→B: two parallel edges with (cost=1, capacity=1) and (cost=1, capacity=2)
      - B→C: two parallel edges with (cost=1, capacity=1) and (cost=1, capacity=2)
      - A→D: (cost=2, capacity=3)
      - D→C: (cost=2, capacity=3)

    The test computes:
      - The true maximum flow (expected flow: 6.0)
      - The flow along the shortest paths (expected flow: 3.0)
      - Flow placement using an equal-balanced strategy on the shortest paths (expected flow: 2.0)
    """
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.max_flow import calc_max_flow
    from ngraph.lib.algorithms.base import FlowPlacement

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    # Create parallel edges between A→B and B→C
    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("A", "B", key=1, cost=1, capacity=2)
    g.add_edge("B", "C", key=2, cost=1, capacity=1)
    g.add_edge("B", "C", key=3, cost=1, capacity=2)
    # Create an alternative path A→D→C
    g.add_edge("A", "D", key=4, cost=2, capacity=3)
    g.add_edge("D", "C", key=5, cost=2, capacity=3)

    # 1. The true maximum flow
    max_flow_prop = calc_max_flow(g, "A", "C")
    assert max_flow_prop == 6.0, f"Expected 6.0, got {max_flow_prop}"

    # 2. The flow along the shortest paths
    max_flow_sp = calc_max_flow(g, "A", "C", shortest_path=True)
    assert max_flow_sp == 3.0, f"Expected 3.0, got {max_flow_sp}"

    # 3. Flow placement using an equal-balanced strategy on the shortest paths
    max_flow_eq = calc_max_flow(
        g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
    )
    assert max_flow_eq == 2.0, f"Expected 2.0, got {max_flow_eq}"


def test_traffic_engineering_simulation():
    """
    Demonstrates traffic engineering by placing two bidirectional demands on a network.

    Graph topology (costs/capacities):

              [15]
          A ─────── B
           \      /
        [5] \    / [15]
             \  /
              C

    - Each link is bidirectional:
         A↔B: capacity 15, B↔C: capacity 15, and A↔C: capacity 5.
    - We place a demand of volume 20 from A→C and a second demand of volume 20 from C→A.
    - Each demand uses its own FlowPolicy, so the policy's global flow accounting does not overlap.
    - The test verifies that each demand is fully placed at 20 units.
    """
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.flow_init import init_flow_graph
    from ngraph.lib.flow_policy import FlowPolicyConfig, get_flow_policy
    from ngraph.lib.demand import Demand

    # Build the graph.
    g = StrictMultiDiGraph()
    for node in ("A", "B", "C"):
        g.add_node(node)

    # Create bidirectional edges with distinct labels (for clarity).
    g.add_edge("A", "B", key=0, cost=1, capacity=15, label="1")
    g.add_edge("B", "A", key=1, cost=1, capacity=15, label="1")
    g.add_edge("B", "C", key=2, cost=1, capacity=15, label="2")
    g.add_edge("C", "B", key=3, cost=1, capacity=15, label="2")
    g.add_edge("A", "C", key=4, cost=1, capacity=5, label="3")
    g.add_edge("C", "A", key=5, cost=1, capacity=5, label="3")

    # Initialize flow-related structures (e.g., to track placed flows in the graph).
    flow_graph = init_flow_graph(g)

    # Create flow policies for each demand.
    flow_policy_ac = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
    flow_policy_ca = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)

    # Demand from A→C (volume 20).
    demand_ac = Demand("A", "C", 20, flow_policy=flow_policy_ac)
    demand_ac.place(flow_graph)
    assert demand_ac.placed_demand == 20, (
        f"Demand from {demand_ac.src_node} to {demand_ac.dst_node} "
        f"expected to be fully placed."
    )

    # Demand from C→A (volume 20).
    demand_ca = Demand("C", "A", 20, flow_policy=flow_policy_ca)
    demand_ca.place(flow_graph)
    assert demand_ca.placed_demand == 20, (
        f"Demand from {demand_ca.src_node} to {demand_ca.dst_node} "
        f"expected to be fully placed."
    )
