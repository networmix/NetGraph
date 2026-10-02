"""Verify the committed API reference without modifying it."""

import difflib
import sys
from pathlib import Path

from generate_api_docs import generate_api_documentation

expected = Path("docs/reference/api-full.md").read_text(encoding="utf-8")
generated = generate_api_documentation(output_to_file=False)
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
