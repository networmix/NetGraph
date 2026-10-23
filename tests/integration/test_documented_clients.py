"""The public Python examples execute against the installed native engine."""

import re
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "relative",
    [
        "README.md",
        "docs/reference/api.md",
        "docs/examples/basic.md",
        "docs/examples/clos-fabric.md",
        "docs/getting-started/tutorial.md",
    ],
)
def test_documented_python_client(relative, tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[2]
    text = (root / relative).read_text()
    if relative.endswith("tutorial.md"):
        (tmp_path / "example.yaml").write_text(
            re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)[0]
        )
    if relative.endswith("clos-fabric.md"):
        (tmp_path / "clos.yaml").write_text(
            re.findall(r"```yaml\n(.*?)```", text, re.DOTALL)[0]
        )
    monkeypatch.chdir(tmp_path)
    namespace = {"__name__": "__documented_client__"}
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    assert blocks
    for index, block in enumerate(blocks):
        exec(compile(block, f"{relative}:python-block-{index}", "exec"), namespace)
