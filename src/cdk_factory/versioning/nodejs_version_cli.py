"""
CLI for auto-incrementing package.json version using git commit count.

The base ``major.minor`` is read from ``package.json`` and the patch component
is derived from the git commit count (via :class:`VersionBuilder`), producing a
final ``major.minor.<build_number>`` version that is written back to both
``package.json`` and ``version.txt``.

Usage:
    python -m cdk_factory.versioning.nodejs_version_cli --project-root .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cdk_factory.utilities.version_builder import VersionBuilder, VersionSource
from cdk_factory.versioning.package_json_version import (
    read_version_from_package_json,
)
from cdk_factory.versioning.package_json_version_writer import (
    update_version_in_package_json,
)


def compute_version(project_root: str) -> str:
    """
    Read base version from package.json, compute patch from git, write back.

    Returns:
        Computed version string (e.g. "3.0.47")
    """
    base_version = read_version_from_package_json(project_root)
    print(f"💬 Base version (package.json): {base_version}")

    builder = VersionBuilder(version_source=VersionSource.FILE, strict=False)
    major, minor, _ = builder.parse_version(base_version)
    major_minor = f"{major}.{minor}"

    build_number = builder.get_git_build_number(major_minor, project_root)
    version = f"{major_minor}.{build_number}"
    print(f"💬 Version: {base_version} → {version}")

    # Write computed version back to package.json
    update_version_in_package_json(project_root, version)

    # Write version.txt to project root
    write_version_txt(project_root, version)

    return version


def write_version_txt(project_root: str, version: str) -> None:
    """Write version.txt to project root."""
    version_txt_path = Path(project_root) / "version.txt"
    version_txt_path.write_text(f"{version}\n", encoding="utf-8")
    print(f"✓ Wrote version.txt: {version_txt_path}")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Auto-increment package.json version using git commit count"
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Path to the project root containing package.json",
    )
    args = parser.parse_args()

    try:
        version = compute_version(args.project_root)
        # Print just the version to stdout as the LAST line for capture by
        # shell scripts (e.g. VERSION=$(python -m ... --project-root .)).
        print(version)
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
