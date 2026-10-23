"""Producer identity captured once from the actual imported extension."""

import sys
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import _netgraph_core as extension
import netgraph_core as ngc

from ngraph.analysis.failures import FailureRequest, sampling_metadata
from ngraph.results import AnalysisMetadata, RunMetadata


@lru_cache(maxsize=1)
def _producer_identity() -> tuple[str, str, str, str]:
    return (
        version("ngraph"),
        ngc.__version__,
        sha256(Path(extension.__file__).read_bytes()).hexdigest(),
        sys.version.split()[0],
    )


def run_metadata(seed: int | None = None) -> RunMetadata:
    netgraph, core, extension_hash, runtime = _producer_identity()
    return RunMetadata(netgraph, core, extension_hash, runtime, seed)


def analysis_metadata(
    workers: int, failures: FailureRequest | None = None
) -> AnalysisMetadata:
    return AnalysisMetadata(workers, sampling_metadata(failures))
