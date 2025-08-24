"""Utilities for building CLI artifact output paths.

This module centralizes logic for composing file and directory paths for
artifacts produced by the NetGraph CLI. Paths are built from an optional
output directory, a prefix (usually derived from the scenario file or
results file), and a per-artifact suffix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def scenario_prefix_from_path(scenario_path: Path) -> str:
    """Return a safe prefix derived from a scenario file path.

    Args:
        scenario_path: The scenario YAML file path.

    Returns:
        The scenario filename stem, trimmed of extensions.
    """
    return scenario_path.stem


def ensure_parent_dir(path: Path) -> None:
    """Ensure the parent directory exists for a file path."""
    path.parent.mkdir(parents=True, exist_ok=True)


def build_artifact_path(output_dir: Optional[Path], prefix: str, suffix: str) -> Path:
    """Compose an artifact path as output_dir / (prefix + suffix).

    If ``output_dir`` is None, the path is created relative to the current
    working directory.

    Args:
        output_dir: Base directory for outputs; if None, use CWD.
        prefix: Filename prefix; usually derived from scenario or results stem.
        suffix: Per-artifact suffix including the dot (e.g. ".results.json").

    Returns:
        The composed path.
    """
    base = output_dir if output_dir is not None else Path.cwd()
    return base / f"{prefix}{suffix}"


def resolve_override_path(
    override: Optional[Path], output_dir: Optional[Path]
) -> Optional[Path]:
    """Resolve an override path with respect to an optional output directory.

    - Absolute override paths are returned as-is.
    - Relative override paths are interpreted as relative to ``output_dir``
      when provided; otherwise relative to the current working directory.

    Args:
        override: Path provided by the user to override the default.
        output_dir: Optional base directory for relative overrides.

    Returns:
        The resolved path or None if no override was provided.
    """
    if override is None:
        return None
    if override.is_absolute():
        return override
    # Compose relative to the output directory if available
    if output_dir is not None:
        return (output_dir / override).resolve()
    # Otherwise, leave as relative to CWD
    return override


def results_path_for_run(
    scenario_path: Path,
    output_dir: Optional[Path],
    results_override: Optional[Path],
) -> Path:
    """Determine the results JSON path for the ``run`` command.

    Behavior:
    - If ``results_override`` is provided, return it (resolved relative to
      ``output_dir`` when that is specified, otherwise as-is).
    - Else if ``output_dir`` is provided, return ``output_dir/<prefix>.results.json``.
    - Else, return ``<scenario_stem>.results.json`` in the current working directory.

    Args:
        scenario_path: The scenario YAML file path.
        output_dir: Optional base output directory.
        results_override: Optional explicit results file path.

    Returns:
        The path where results should be written.
    """
    resolved_override = resolve_override_path(results_override, output_dir)
    if resolved_override is not None:
        return resolved_override

    prefix = scenario_prefix_from_path(scenario_path)
    if output_dir is not None:
        return build_artifact_path(output_dir, prefix, ".results.json")
    return Path(f"{prefix}.results.json")


def profiles_dir_for_run(scenario_path: Path, output_dir: Optional[Path]) -> Path:
    """Return the directory for child worker profiles for ``run --profile``.

    Args:
        scenario_path: The scenario YAML path.
        output_dir: Optional base output directory.

    Returns:
        Directory path where worker profiles should be stored.
    """
    prefix = scenario_prefix_from_path(scenario_path)
    if output_dir is None:
        return Path("worker_profiles")
    return build_artifact_path(output_dir, prefix, ".profiles")
