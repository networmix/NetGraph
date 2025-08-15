"""Load JSON results for notebook analysis with a status wrapper.

The loader returns a small dictionary that includes success status and basic
metadata about the results file. It keeps errors non-fatal for notebook usage.
"""

import json
from pathlib import Path
from typing import Any, Union


class DataLoader:
    """Load and validate analysis results from a JSON file."""

    @staticmethod
    def load_results(json_path: Union[str, Path]) -> dict[str, Any]:
        json_path = Path(json_path)
        out: dict[str, Any] = {
            "file_path": str(json_path),
            "success": False,
            "results": {},
            "message": "",
        }
        try:
            if not json_path.exists():
                out["message"] = f"Results file not found: {json_path}"
                return out
            with open(json_path, "r", encoding="utf-8") as f:
                results = json.load(f)
            if not isinstance(results, dict):
                out["message"] = "Invalid results format - expected dictionary"
                return out
            steps = results.get("steps", {}) if isinstance(results, dict) else {}
            out.update(
                dict(
                    success=True,
                    results=results,
                    message=f"Loaded {len(steps):,} analysis steps from {json_path.name}",
                    step_count=len(steps),
                    step_names=list(steps.keys()),
                )
            )
        except json.JSONDecodeError as e:
            out["message"] = f"Invalid JSON format: {e}"
        except Exception as e:
            out["message"] = f"Error loading results: {e}"
        return out
