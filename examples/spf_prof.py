# pylint: disable=protected-access,invalid-name
import networkx as nx

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.spf import spf
from ngraph.algorithms.common import min_cost_edges_fabric

from line_profiler import LineProfiler


lp = LineProfiler()
g = MultiDiGraph()
for node_num in range(100):
    node_id = str(node_num)
    g.add_node(node_id)
    for _node_id in g:
        if _node_id != node_id:
            for _metric in range(100, 0, -1):
                g.add_edge(_node_id, node_id, metric=_metric)
                g.add_edge(node_id, _node_id, metric=_metric)

edge_sel = min_cost_edges_fabric("metric")

lp = LineProfiler()
lp_wrapper = lp(spf)
# lp.add_function(edge_sel)
lp_wrapper(g, "0", edge_sel)
lp.print_stats()

# def test_spf_bench_2():
#     g = nx.MultiDiGraph()
#     for node_num in range(100):
#         node_id = str(node_num)
#         g.add_node(node_id)
#         for _node_id in g:
#             if _node_id != node_id:
#                 for _metric in range(100, 0, -1):
#                     g.add_edge(_node_id, node_id, metric=_metric)
#                     g.add_edge(node_id, _node_id, metric=_metric)

#     nx.dijkstra_predecessor_and_distance(g, "0")
