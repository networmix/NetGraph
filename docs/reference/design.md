# Architecture

NetGraph is two layers. This page says what each owns, what crosses between them, and what holds across them; [How NetGraph computes](../concepts.md) explains the rules.

## Two layers

NetGraph owns network meaning: physical topology, selectors, grouped demands, risk groups, scenarios and workflow questions. NetGraph-Core owns graph searches, allocation, forwarding, reservations and numerical results. A query declares which native model to run.

## The pipeline

- **Prepare:** NetGraph resolves selectors and demands on a read-only view of the editable network, chooses the bandwidth unit `q` and builds one immutable native graph.
- **Run:** numerical analysis steps ask the Core their questions on the prepared graph. `BuildGraph`, `NetworkStats` and `CostPower` read the prepared domain records; custom steps run their own code. Numerical analysis results retain native objects through export.
- **Export:** `write_json` writes the native results and NetGraph's records as JSON.

## Guarantees

- Any exception cleans all owners and publishes no partial analysis or run.
- Returned results and record snapshots remain valid after every owner is explicitly removed.
- Independent cases can run on worker threads. Drawing and output order do not depend on worker completion, and results are the same for any number of workers.
