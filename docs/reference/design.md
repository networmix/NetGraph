# Architecture

NetGraph is two layers. This page says what each does, what crosses between them, and what holds across them; [How NetGraph computes](../concepts.md) explains the rules.

## Two layers

NetGraph handles what the network means: physical topology, selectors, grouped demands, risk groups, scenarios and workflow questions. NetGraph-Core computes: graph searches, allocation, forwarding, tunnel holds and numerical results. A query names the engine model to run.

## The pipeline

- **Prepare:** NetGraph resolves selectors and demands on a read-only view of the editable network, chooses the bandwidth unit `q` and builds one immutable native graph.
- **Run:** numerical analysis steps ask the Core their questions on the prepared graph. `BuildGraph`, `NetworkStats` and `CostPower` read the prepared domain records; custom steps run their own code. Numerical results hold the engine's result objects, which the export writes out.
- **Export:** `write_json` writes the native results and NetGraph's records as JSON.

## Guarantees

- A call that fails publishes nothing: no partial analysis and no partial run.
- Returned results stay readable after the scenario, its network and the prepared scenario are deleted.
- Independent cases can run on worker threads. Drawing and output order do not depend on worker completion, and results are the same for any number of workers.
