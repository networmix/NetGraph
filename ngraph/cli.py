from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from ngraph.logging import get_logger, set_global_log_level
from ngraph.scenario import Scenario

logger = get_logger(__name__)


def _run_scenario(path: Path, output: Optional[Path]) -> None:
    """Run a scenario file and store results as JSON."""
    logger.info(f"Loading scenario from: {path}")

    try:
        yaml_text = path.read_text()
        scenario = Scenario.from_yaml(yaml_text)

        logger.info("Starting scenario execution")
        scenario.run()
        logger.info("Scenario execution completed successfully")

        logger.info("Serializing results to JSON")
        results_dict: Dict[str, Dict[str, Any]] = scenario.results.to_dict()
        json_str = json.dumps(results_dict, indent=2, default=str)

        if output:
            logger.info(f"Writing results to: {output}")
            output.write_text(json_str)
            logger.info("Results written successfully")
        else:
            print(json_str)

    except FileNotFoundError:
        logger.error(f"Scenario file not found: {path}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to run scenario: {type(e).__name__}: {e}")
        sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the ``ngraph`` command.

    Args:
        argv: Optional list of command-line arguments. If ``None``, ``sys.argv``
            is used.
    """
    parser = argparse.ArgumentParser(prog="ngraph")

    # Global options
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose (DEBUG) logging"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true", help="Enable quiet mode (WARNING+ only)"
    )

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

    # Configure logging based on arguments
    if args.verbose:
        set_global_log_level(logging.DEBUG)
        logger.debug("Debug logging enabled")
    elif args.quiet:
        set_global_log_level(logging.WARNING)
    else:
        set_global_log_level(logging.INFO)

    if args.command == "run":
        _run_scenario(args.scenario, args.results)


if __name__ == "__main__":
    main()
