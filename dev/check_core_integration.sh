#!/usr/bin/env bash
# Build the explicitly selected Core and test it in a separate NetGraph environment.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
unset PYTHONPATH PYTHONHOME
if [[ -z "${1:-}" || ! -f "$1/pyproject.toml" || ! -f "$1/CMakeLists.txt" ]]; then
    echo 'Usage: bash dev/check_core_integration.sh /absolute/path/to/NetGraph-Core-worktree' >&2
    exit 2
fi
core_path=$(cd "$1" && pwd -P)
[[ -x venv/bin/python ]] || { echo 'Run workspace setup first.' >&2; exit 1; }
mkdir -p build/core-integration
run_dir=$(mktemp -d "$PWD/build/core-integration/run.XXXXXX")
echo "Integration artifacts: $run_dir"
# Keep the wheel and test evidence, not a full environment per run.
trap 'rm -rf "$run_dir/venv" "$run_dir/core-build"' EXIT
venv/bin/python -m venv "$run_dir/venv"
export VIRTUAL_ENV="$run_dir/venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
export CMAKE_BUILD_PARALLEL_LEVEL="${CMAKE_BUILD_PARALLEL_LEVEL:-4}"
if [[ "$(uname -s)" == Darwin ]]; then
    export CC="$(xcrun --find clang)"
    export CXX="$(xcrun --find clang++)"
    export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-15.0}"
fi
python -m pip install --upgrade pip
python -m pip install cmake ninja
python -m pip wheel --no-deps --wheel-dir "$run_dir/wheels" \
    --config-settings="build-dir=$run_dir/core-build" "$core_path"
wheels=("$run_dir"/wheels/netgraph_core-*.whl)
[[ ${#wheels[@]} -eq 1 && -f "${wheels[0]}" ]] || { echo 'Expected one Core wheel.' >&2; exit 1; }
python -m pip install -e '.[dev]' "${wheels[0]}"
python -m pip check
{
    echo "NetGraph: $(git rev-parse HEAD)"
    git status --short
    echo "Core: $(git -C "$core_path" rev-parse HEAD)"
    git -C "$core_path" status --short
    python - "${wheels[0]}" <<'PY'
import hashlib
import importlib.metadata
import pathlib
import sys
import _netgraph_core
import netgraph_core
wheel = pathlib.Path(sys.argv[1])
print('Python:', sys.version)
print('Core version:', importlib.metadata.version('netgraph-core'))
print('Core wrapper:', netgraph_core.__file__)
print('Core extension:', _netgraph_core.__file__)
print('Wheel SHA256:', hashlib.sha256(wheel.read_bytes()).hexdigest())
assert pathlib.Path(_netgraph_core.__file__).is_relative_to(sys.prefix)
PY
} | tee "$run_dir/provenance.txt"
python -m pytest --junitxml="$run_dir/pytest.xml" 2>&1 | tee "$run_dir/pytest.log"
