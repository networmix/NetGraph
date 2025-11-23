#!/usr/bin/env python3
"""Benchmark serialization and startup overhead for threading vs multiprocessing.

ARCHIVED ANALYSIS - Historical Documentation
============================================
This script was used to analyze the performance trade-offs between threading and
multiprocessing for parallel failure analysis in NetGraph. The analysis showed
that threading provides significant benefits:
  - Eliminates serialization overhead (50ms+ for large networks)
  - Reduces memory footprint (5-6 MB saved per run with 8 workers)
  - Zero-copy network sharing across workers

OUTCOME: Threading has been implemented in ngraph.exec.failure.manager.FailureManager
using ThreadPoolExecutor with shared network references.

This script is kept for documentation purposes to explain the architectural
decision and can be re-run if the trade-offs need to be re-evaluated in the
future (e.g., for different workload patterns or Python versions).
"""

import pickle
import time
from concurrent.futures import ThreadPoolExecutor

from ngraph.model.network import Link, Network, Node


def create_test_network(num_nodes=1000, num_links=5000):
    """Create a realistic test network."""
    network = Network()

    for i in range(num_nodes):
        network.add_node(
            Node(
                name=f"node_{i}",
                attrs={
                    "region": f"region_{i % 10}",
                    "type": "router",
                    "coords": (i, i * 2),
                },
            )
        )

    for i in range(num_links):
        src = f"node_{i % num_nodes}"
        dst = f"node_{(i + 15) % num_nodes}"
        network.add_link(
            Link(
                source=src,
                target=dst,
                capacity=100.0 + i % 100,
                cost=1.0 + i % 10,
                attrs={"fiber": True, "distance": i % 1000},
            )
        )

    return network


def measure_serialization(network, num_workers=8):
    """Measure pickle serialization overhead."""
    # Serialize once (main process)
    start = time.time()
    pickled = pickle.dumps(network)
    serialize_time = time.time() - start

    # Deserialize for each worker
    start = time.time()
    for _ in range(num_workers):
        _ = pickle.loads(pickled)
    deserialize_time = time.time() - start

    return serialize_time, deserialize_time, len(pickled)


def measure_thread_startup(num_workers=8):
    """Measure thread pool startup time."""

    def dummy_work():
        return 42

    start = time.time()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(dummy_work) for _ in range(num_workers)]
        _ = [f.result() for f in futures]
    thread_time = time.time() - start

    return thread_time


def main():
    print("=" * 70)
    print("NetGraph Concurrency Benchmark")
    print("=" * 70)

    # Create test network
    print("\nCreating test network (1000 nodes, 5000 links)...")
    network = create_test_network(1000, 5000)
    print(f"✓ Network: {len(network.nodes)} nodes, {len(network.links)} links")

    workers = 8

    # Measure serialization overhead
    print("\n" + "=" * 70)
    print("MULTIPROCESSING OVERHEAD (Current Implementation)")
    print("=" * 70)

    serialize_time, deserialize_time, size_bytes = measure_serialization(
        network, workers
    )
    total_serialization = serialize_time + deserialize_time

    print(f"Serialize once (main process):     {serialize_time * 1000:6.1f}ms")
    print(f"Serialized size:                   {size_bytes / 1024 / 1024:6.2f} MB")
    print(f"Deserialize {workers}× (one per worker): {deserialize_time * 1000:6.1f}ms")
    print(f"Total startup overhead:            {total_serialization * 1000:6.1f}ms")
    print(
        f"Memory footprint ({workers} workers):      {size_bytes * workers / 1024 / 1024:6.2f} MB"
    )

    # Measure threading
    print("\n" + "=" * 70)
    print("THREADING (Proposed Implementation)")
    print("=" * 70)

    thread_time = measure_thread_startup(workers)

    print(f"Serialize:                         {0:6.1f}ms (eliminated)")
    print(f"Deserialize:                       {0:6.1f}ms (eliminated)")
    print(f"Thread pool startup:               {thread_time * 1000:6.1f}ms")
    print(
        f"Memory footprint ({workers} workers):      {size_bytes / 1024 / 1024:6.2f} MB (shared)"
    )

    # Calculate savings
    print("\n" + "=" * 70)
    print("SAVINGS")
    print("=" * 70)

    memory_saved = size_bytes * (workers - 1) / 1024 / 1024
    time_saved = total_serialization - thread_time
    speedup = total_serialization / thread_time

    print(f"Startup time saved:                {time_saved * 1000:6.1f}ms")
    print(f"Memory saved:                      {memory_saved:6.2f} MB")
    print(f"Speedup ratio (startup):           {speedup:6.1f}×")

    # Project impact for real workloads
    print("\n" + "=" * 70)
    print("PROJECTED IMPACT FOR 1000 ITERATIONS")
    print("=" * 70)

    iterations = 1000
    work_per_iter_ms = 100  # Assume 100ms per iteration
    work_per_iter = work_per_iter_ms / 1000

    # Multiprocessing total time
    mp_total = total_serialization + (iterations * work_per_iter / workers)
    # Threading total time
    th_total = thread_time + (iterations * work_per_iter / workers)

    # Per-iteration IPC overhead (estimate)
    ipc_overhead_per_iter = 0.001  # 1ms per iteration for IPC
    mp_total += iterations * ipc_overhead_per_iter / workers

    print(f"Work per iteration (assumed):      {work_per_iter_ms:6.1f}ms")
    print(f"Total iterations:                  {iterations}")
    print(f"Workers:                           {workers}")
    print()
    print(f"Multiprocessing total time:        {mp_total:6.2f}s")
    print(f"  Startup overhead:                {total_serialization:6.2f}s")
    print(
        f"  Work time:                       {iterations * work_per_iter / workers:6.2f}s"
    )
    print(
        f"  IPC overhead:                    {iterations * ipc_overhead_per_iter / workers:6.2f}s"
    )
    print()
    print(f"Threading total time:              {th_total:6.2f}s")
    print(f"  Startup overhead:                {thread_time:6.2f}s")
    print(
        f"  Work time:                       {iterations * work_per_iter / workers:6.2f}s"
    )
    print(f"  IPC overhead:                    {0:6.2f}s (eliminated)")
    print()
    print(f"Time saved:                        {mp_total - th_total:6.2f}s")
    print(
        f"Percentage improvement:            {(mp_total - th_total) / mp_total * 100:6.1f}%"
    )

    # Test with different network sizes
    print("\n" + "=" * 70)
    print("SCALABILITY TEST (Different Network Sizes)")
    print("=" * 70)
    print(
        f"{'Nodes':<10} {'Links':<10} {'Size (MB)':<12} {'Serialize (ms)':<15} {'Memory (8w)':<12}"
    )
    print("-" * 70)

    for nodes in [100, 500, 1000, 2000]:
        links = nodes * 5
        net = create_test_network(nodes, links)
        ser_time, deser_time, size = measure_serialization(net, workers)
        print(
            f"{nodes:<10} {links:<10} {size / 1024 / 1024:<12.2f} {(ser_time + deser_time) * 1000:<15.1f} {size * workers / 1024 / 1024:<12.2f}"
        )

    print("\n" + "=" * 70)
    print("CONCLUSION")
    print("=" * 70)
    print("✓ Threading eliminates ALL serialization overhead")
    print(f"✓ Saves {memory_saved:.1f} MB memory per analysis run")
    print(f"✓ {speedup:.1f}× faster startup")
    print(
        f"✓ {(mp_total - th_total) / mp_total * 100:.1f}% overall improvement for typical workloads"
    )
    print()
    print("Recommendation: Switch to threading immediately")


if __name__ == "__main__":
    main()
