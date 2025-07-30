#!/usr/bin/env python3
"""CLI entry-point for NetGraph performance benchmarking and analysis."""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

from .analysis import PerformanceAnalyzer
from .core import BenchmarkResult
from .profiles import BENCHMARK_PROFILES, get_profile_by_name
from .runner import BenchmarkRunner
from .topology import ALL_TOPOLOGIES
from .visualization import PerformanceVisualizer

PERF_RESULTS_DIR = Path("dev/perf_results")
PERF_PLOTS_DIR = Path("dev/perf_plots")


def cmd_run(args: argparse.Namespace) -> int:
    """Run command implementation."""
    try:
        print("Initializing performance analysis...\n")
        PERF_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        # Get profiles to run
        if args.profile:
            try:
                profile = get_profile_by_name(args.profile)
                profiles = [profile]
            except KeyError:
                print(f"Unknown profile: {args.profile}")
                print(
                    f"Available profiles: {', '.join(p.name for p in BENCHMARK_PROFILES)}"
                )
                return 1
        else:
            profiles = BENCHMARK_PROFILES

        print(f"Selected {len(profiles)} profile(s) for benchmarking")

        # Run benchmarks
        print("\n[ BENCHMARKING ]")
        print("-" * 60)
        runner = BenchmarkRunner()
        results: list[tuple[str, BenchmarkResult]] = []

        for i, profile in enumerate(profiles, 1):
            print(f"\n({i}/{len(profiles)}) Running profile: {profile.name}")
            print(f"    Task: {profile.tasks[0].name}")
            print(f"    Cases: {len(profile.cases)}")
            print(f"    Iterations per case: {profile.iterations}")

            result = runner.run_profile(profile)
            results.append((profile.name, result))
            print(f"    ✓ Completed in {result.total_execution_time():.2f}s")

        # Analyze results
        print("\n\n[ ANALYSIS ]")
        print("-" * 60)
        analyzer = PerformanceAnalyzer(results_dir=PERF_RESULTS_DIR)
        analyzer.add_runs([result for _, result in results])
        analyzer.print_analysis_report()

        # Save results to disk
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        results_file = PERF_RESULTS_DIR / f"benchmark_results_{timestamp}.json"

        # Generate plots and export data
        print("\n[ RESULTS & ARTIFACTS ]")
        print("-" * 60)
        if any(result.profile.analysis.generates_plots() for _, result in results):
            PERF_PLOTS_DIR.mkdir(parents=True, exist_ok=True)
            viz = PerformanceVisualizer(plots_dir=PERF_PLOTS_DIR)
            print("Generated:")
            viz.create_summary_report(analyzer, timestamp)
            viz.export_results_json(analyzer, results, results_file)
        else:
            # Even if no plots are generated, still export the raw data
            viz = PerformanceVisualizer(plots_dir=PERF_PLOTS_DIR)
            print("Generated:")
            viz.export_results_json(analyzer, results, results_file)

        print("\n✓ Performance analysis complete")
        return 0

    except Exception as e:
        print(f"\n✗ Error running benchmarks: {e}")
        return 1


def cmd_show_profile(args: argparse.Namespace) -> int:
    """Show profile configuration."""
    try:
        # If no profile name provided, list available profiles
        if not args.profile_name:
            print("Available benchmark profiles:")
            print("-" * 60)
            for i, profile in enumerate(BENCHMARK_PROFILES, 1):
                print(f"{i:2d}. {profile.name}")
                print(f"    Task: {profile.tasks[0].name}")
                print(f"    Cases: {len(profile.cases)}")
                print(
                    f"    Expected complexity: {profile.analysis.expected.display_name}"
                )
            return 0

        profile = get_profile_by_name(args.profile_name)

        print(f"Profile: {profile.name}")
        print("-" * 60)
        print(f"Iterations: {profile.iterations}")
        print(f"Task: {profile.tasks[0].name}")
        print(f"Expected complexity: {profile.analysis.expected.display_name}")
        print(f"Fit tolerance: {profile.analysis.fit_tol_pct}%")
        print(f"Regression tolerance: {profile.analysis.regression_tol_pct}%")
        print(f"Generate plots: {profile.analysis.plots}")

        print(f"\nBenchmark cases ({len(profile.cases)}):")
        for i, case in enumerate(profile.cases, 1):
            print(f"  {i}. {case.name}")
            print(f"     Problem size: {case.problem_size}")

            # Show topology information generically
            topology = case.inputs.get("topology")
            if topology:
                print(f"     Topology: {topology.__class__.__name__}")
                # Show all topology parameters except computed fields
                for field, value in topology.__dict__.items():
                    if not field.startswith("_") and field not in [
                        "name",
                        "expected_nodes",
                        "expected_links",
                    ]:
                        print(f"       {field}: {value}")
                print(f"     Expected nodes: {topology.expected_nodes}")
                print(f"     Expected links: {topology.expected_links}")

        return 0

    except KeyError:
        print(f"Unknown profile: {args.profile_name}")
        print(f"Available profiles: {', '.join(p.name for p in BENCHMARK_PROFILES)}")
        return 1
    except Exception as e:
        print(f"Error showing profile: {e}")
        return 1


def cmd_show_topology(args: argparse.Namespace) -> int:
    """Show topology configuration and expected dimensions."""
    try:
        # If no topology type provided, list available topologies
        if not args.topology_type:
            print("Available topology types:")
            print("-" * 60)

            for i, topology_class in enumerate(ALL_TOPOLOGIES, 1):
                print(f"{i}. {topology_class.__name__}")

                # Get parameter information from dataclass fields
                if dataclasses.is_dataclass(topology_class):
                    fields = dataclasses.fields(topology_class)
                    param_fields = [
                        f.name
                        for f in fields
                        if f.name not in ["name", "expected_nodes", "expected_links"]
                    ]
                    print(f"   Parameters: {', '.join(param_fields)}")

                print()
            return 0

        # Parse topology type and parameters
        topology_type = args.topology_type

        # Find the topology class by name
        topology_class = None
        for topo_class in ALL_TOPOLOGIES:
            if topo_class.__name__ == topology_type:
                topology_class = topo_class
                break

        if topology_class is None:
            print(f"Unknown topology type: {topology_type}")
            available_types = [topo.__name__ for topo in ALL_TOPOLOGIES]
            print(f"Available types: {', '.join(available_types)}")
            return 1

        # Parse parameter key=value pairs
        params = {}
        for param in args.parameters:
            if "=" not in param:
                print(f"Invalid parameter format: {param}")
                print("Use format: key=value")
                return 1

            key, value = param.split("=", 1)

            # Try to parse value as appropriate type
            if value.lower() in ("true", "false"):
                params[key] = value.lower() == "true"
            elif value.isdigit():
                params[key] = int(value)
            else:
                try:
                    params[key] = float(value)
                except ValueError:
                    params[key] = value

        # Create topology by direct instantiation
        topology = topology_class(**params)

        print(f"Topology: {topology.__class__.__name__}")
        print("-" * 60)
        print(f"Name: {topology.name}")
        print(f"Expected nodes: {topology.expected_nodes}")
        print(f"Expected links: {topology.expected_links}")

        print("\nParameters:")
        for field, value in topology.__dict__.items():
            if not field.startswith("_") and field not in [
                "name",
                "expected_nodes",
                "expected_links",
            ]:
                print(f"  {field}: {value}")

        return 0

    except TypeError as e:
        print(f"Error creating topology: {e}")
        print("Check parameter names and types")
        return 1
    except Exception as e:
        print(f"Error showing topology: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="perf",
        description="NetGraph performance benchmarking & analysis",
    )
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="Run benchmarks then analyze")
    run_p.add_argument("--profile", help="Run a single profile")

    # Add show command with subcommands
    show_p = sub.add_parser("show", help="Show configuration details")
    show_sub = show_p.add_subparsers(dest="show_command")

    # Show profile subcommand
    profile_p = show_sub.add_parser("profile", help="Show profile configuration")
    profile_p.add_argument(
        "profile_name", nargs="?", help="Name of the profile to show"
    )

    # Show topology subcommand
    topology_p = show_sub.add_parser("topology", help="Show topology dimensions")
    topology_p.add_argument(
        "topology_type", nargs="?", help="Type of topology (e.g., Grid2DTopology)"
    )
    topology_p.add_argument(
        "parameters", nargs="*", help="Parameters as key=value pairs"
    )

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    if args.command == "show":
        if args.show_command == "profile":
            return cmd_show_profile(args)
        if args.show_command == "topology":
            return cmd_show_topology(args)
        show_p.print_help()
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
