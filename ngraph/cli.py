from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ngraph.scenario import Scenario


def _run_scenario(path: Path, output: Optional[Path]) -> None:
    """Run a scenario file and store results as JSON."""

    yaml_text = path.read_text()
    scenario = Scenario.from_yaml(yaml_text)
    scenario.run()

    results_dict: Dict[str, Dict[str, Any]] = scenario.results.to_dict()
    json_str = json.dumps(results_dict, indent=2, default=str)
    if output:
        output.write_text(json_str)
    else:
        print(json_str)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``ngraph`` command.

    Args:
        argv: Optional list of command-line arguments. If ``None``, ``sys.argv``
            is used.
    """
    parser = argparse.ArgumentParser(prog="ngraph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a scenario")
    run_parser.add_argument("scenario", type=Path, help="Path to scenario YAML")
    run_parser.add_argument(
        "--results",
        "-r",
        type=Path,
        default=None,
        help="Write JSON results to this file instead of stdout",
    )

    args = parser.parse_args(argv)

    if args.command == "run":
        _run_scenario(args.scenario, args.results)


if __name__ == "__main__":
    main()
