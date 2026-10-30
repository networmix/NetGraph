// Diagnostic probes for NetGraph 0.26.0 on NetGraph-Core 0.12.0, built against
// the Core v0.12.0 headers and Core's pybind11 release (README.md,
// "Reproducing"): discard_programs drops the forwarding program a completed
// PlacementResult owns (a counterfactual); census sizes the programs, source
// DAGs and plans that results own. measure compares recalculated admission and
// per-source delivery with the result; its aggregate and attributed edge
// vectors are compared with the recalculated lossless step, not
// PlacementResult::edge_flows.
#include "netgraph/core/detail/program_data.hpp"
#include "netgraph/core/detail/route_builders.hpp"
#include "netgraph/core/flow_policy.hpp"
#include <chrono>
#include <cstdint>
#include <pybind11/pybind11.h>
#include <stdexcept>
#include <unordered_set>
#if defined(__APPLE__)
#include <malloc/malloc.h>
#define NGPROBE_USABLE(p) malloc_size(p)
#else
#include <malloc.h>
#define NGPROBE_USABLE(p) malloc_usable_size(const_cast<void *>(p))
#endif

namespace py = pybind11;
using namespace netgraph::core;
using namespace netgraph::core::detail;
using Clock = std::chrono::steady_clock;

PYBIND11_MODULE(ngprobe, m) {
  m.def("discard_programs", [](py::iterable results) {
    for (auto result : results)
      result.cast<PlacementResult &>().program.reset();
  });
  m.def("census", [](py::iterable values) {
    std::unordered_set<const void *> dags, programs, plans;
    std::uint64_t rows = 0, dag_edges = 0, dag_nodes = 0, dag_payload = 0,
                  dag_malloc = 0;
    std::uint64_t plan_payload = 0, plan_malloc = 0, program_malloc = 0,
                  source_malloc = 0;
    auto usable = [](const auto &a) -> std::size_t {
      return a.data() == nullptr
                 ? 0
                 : NGPROBE_USABLE(static_cast<const void *>(a.data()));
    };
    for (auto value : values) {
      const auto &r = value.cast<const PlacementResult &>();
      ++rows;
      source_malloc += usable(r.by_source);
      if (!r.program || !programs.insert(r.program.get()).second)
        continue;
      const auto &p = ProgramAccess::data(*r.program);
      program_malloc +=
          usable(p.block()) + usable(p.entries) + usable(p.split_contexts);
      for (const auto &e : p.entries) {
        if (!e.route || !dags.insert(e.route.get()).second)
          continue;
        const auto &d = *e.route;
        const auto nodes = PredecessorDAGBuilder::member_nodes(d);
        const auto offsets = PredecessorDAGBuilder::member_offsets(d);
        const auto edges = PredecessorDAGBuilder::ascending(d);
        dag_nodes += nodes.size();
        dag_edges += edges.size();
        dag_payload += 8 * nodes.size() + 4 + 12 * edges.size();
        dag_malloc += usable(nodes) + usable(offsets) + usable(d.parents()) +
                      usable(d.via_edges()) + usable(edges);
      }
      for (const auto &c : p.split_contexts) {
        if (!c.prepared_route || !plans.insert(c.prepared_route.get()).second)
          continue;
        const auto &q = *c.prepared_route;
        plan_payload +=
            4 * (q.support_edges.size() + q.forwarding_edges.size()) +
            8 * q.weights.size() +
            4 * (2 * q.sources.size() + q.destinations.size() +
                 3 * q.topological_order.size() + q.forwarding_edges.size()) +
            4 * ((q.is_destination.size() + 3) / 4);
        // sources starts at the base of PreparedRoute::store_, whose other
        // fields are spans.
        plan_malloc += usable(q.support_edges) + usable(q.forwarding_edges) +
                       usable(q.weights) + usable(q.sources);
      }
    }
    py::dict d;
    d["rows"] = rows;
    d["programs"] = programs.size();
    d["dags"] = dags.size();
    d["plans"] = plans.size();
    d["dag_edges"] = dag_edges;
    d["dag_nodes"] = dag_nodes;
    d["dag_payload"] = dag_payload;
    d["dag_malloc"] = dag_malloc;
    d["plan_payload"] = plan_payload;
    d["plan_malloc"] = plan_malloc;
    d["program_malloc"] = program_malloc;
    d["source_malloc"] = source_malloc;
    d["object_model"] = rows * sizeof(PlacementResult) +
                        programs.size() * (sizeof(ProgramBlock) + 32) +
                        plans.size() * (sizeof(PreparedRoute) + 32) +
                        dags.size() * (sizeof(PredecessorDAG) + 32);
    d["sizeof_dag"] = sizeof(PredecessorDAG);
    d["sizeof_plan"] = sizeof(PreparedRoute);
    d["sizeof_program_block"] = sizeof(ProgramBlock);
    d["sizeof_result"] = sizeof(PlacementResult);
    d["sizeof_source_flow"] = sizeof(SourceFlow);
    return d;
  });
  m.def("measure", [](const Graph &g, const PlacementResult &r, Amount offer) {
    if (!r.program)
      throw std::runtime_error("program required");
    const auto &data = ProgramAccess::data(*r.program);
    const auto &plan = *data.split_contexts.front().prepared_route;
    std::vector<Amount> view, zero(plan.forwarding_edges.size(), 0);
    for (auto edge : plan.forwarding_edges)
      view.push_back(g.edge_capacity_units()[edge]);
    auto start = Clock::now();
    auto step = lossless_step(plan, 0, view, zero, offer);
    const double lossless =
        std::chrono::duration<double>(Clock::now() - start).count();
    if (step.admitted != r.delivered)
      throw std::runtime_error("lossless result differs from actual case");
    std::vector<Amount> inject(plan.sources.size(), 0);
    round_robin(step.admitted, inject);
    start = Clock::now();
    auto aggregate = forward(plan, Injection{inject, false}, {}, nullptr);
    const double aggregate_s =
        std::chrono::duration<double>(Clock::now() - start).count();
    Attribution attr;
    start = Clock::now();
    auto attributed = forward(plan, Injection{inject, false}, {}, &attr);
    const double attributed_s =
        std::chrono::duration<double>(Clock::now() - start).count();
    if (aggregate.edge_flows != step.edge_flows ||
        attributed.edge_flows != step.edge_flows)
      throw std::runtime_error("kernel edge allocations differ");
    for (std::size_t i = 0; i < data.reachable_sources.size(); ++i) {
      bool found = false;
      for (const auto &s : r.by_source) {
        if (s.source == data.reachable_sources[i]) {
          if (s.delivered != attr.delivered[i])
            throw std::runtime_error("source delivery differs");
          found = true;
        }
      }
      if (!found)
        throw std::runtime_error("source row absent");
    }
    py::dict out;
    out["lossless_s"] = lossless;
    out["search_probes"] = step.probes;
    out["aggregate_forward_s"] = aggregate_s;
    out["attributed_forward_s"] = attributed_s;
    out["sources"] = plan.sources.size();
    out["edges"] = plan.forwarding_edges.size();
    std::uint64_t entries = 0;
    for (const auto &list : attr.entries)
      entries += list.size();
    out["attribution_entries"] = entries;
    out["admitted"] = step.admitted;
    return out;
  });
}
