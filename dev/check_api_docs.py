"""Verify the committed API reference without modifying it."""

import difflib
import re
import sys
from pathlib import Path

from generate_api_docs import generate_api_documentation

expected = Path("docs/reference/api-full.md").read_text(encoding="utf-8")
generated = generate_api_documentation(output_to_file=False)
# The generator includes wall-clock time; ignore only that metadata line.
timestamp = r"(?m)^Generated from source code on: .*$"
expected = re.sub(timestamp, "Generated from source code on: <timestamp>", expected)
generated = re.sub(timestamp, "Generated from source code on: <timestamp>", generated)
if generated != expected:
    sys.stdout.writelines(
        difflib.unified_diff(
            expected.splitlines(keepends=True),
            generated.splitlines(keepends=True),
            fromfile="docs/reference/api-full.md",
            tofile="generated API reference",
        )
    )
    sys.exit("API reference differs. Run make docs and review the generated changes.")
print("API reference matches source.")
