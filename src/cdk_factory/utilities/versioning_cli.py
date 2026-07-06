"""
Versioning CLI Utility

Reads version information from a Node.js project's package.json, computes
a build number using git commit history via the existing VersionBuilder class,
and writes a version.txt file. Optionally updates package.json with the
computed version.

Usage as a CLI (called from pipeline steps):

    python -m cdk_factory.utilities.versioning_cli \
        --project-root "./my-node-project" \
        --output-dir "./my-node-project/dist"

Usage for shell variable capture:

    export VERSION=$(python -m cdk_factory.utilities.versioning_cli \
        --project-root ".")

Usage with package.json update:

    python -m cdk_factory.utilities.versioning_cli \
        --project-root "." \
        --update-package-json

Usage with git-tag version source:

    python -m cdk_factory.utilities.versioning_cli \
        --project-root "." \
        --version-source git-tag

Usage as a library:

    from cdk_factory.utilities.versioning_cli import VersioningCli
    cli = VersioningCli(project_root=".", output_dir="./dist")
    version = cli.read_package_json_version()
    computed = cli.compute_version()
    cli.write_version_file(computed)
"""

import sys
import os
import re
import json
import logging
import argparse
from typing import Optional

from cdk_factory.utilities.version_builder import VersionBuilder, VersionSource

logger = logging.getLogger(__name__)


class VersioningCli:
    """Reads version from package.json, computes build number, writes version.txt."""

    def __init__(self, project_root: str, output_dir: Optional[str] = None):
        """
        Initialize VersioningCli.

        Args:
            project_root: Path to the Node.js project root containing package.json.
            output_dir: Directory to write version.txt. Defaults to project_root.
        """
        self.project_root = project_root
        self.output_dir = output_dir if output_dir is not None else project_root

    def read_package_json_version(self) -> str:
        """Read and validate the version field from package.json.

        Returns:
            The raw version string (e.g., "1.2.0").

        Raises:
            SystemExit: If package.json is missing, invalid JSON, missing version,
                       or version is not valid semver.
        """
        package_json_path = os.path.join(self.project_root, "package.json")

        # Check file exists
        if not os.path.isfile(package_json_path):
            print(
                f"ERROR: package.json not found at {package_json_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Read and parse JSON
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(
                f"ERROR: Failed to read package.json: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(
                f"ERROR: Failed to parse package.json: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Validate version field exists
        if "version" not in data:
            print(
                'ERROR: package.json does not contain a "version" field',
                file=sys.stderr,
            )
            sys.exit(1)

        version = data["version"]

        # Validate version format: MAJOR.MINOR.PATCH (non-negative integers)
        if not re.match(r"^\d+\.\d+\.\d+$", str(version)):
            print(
                f'ERROR: Invalid version "{version}" in package.json. '
                f"Expected MAJOR.MINOR.PATCH",
                file=sys.stderr,
            )
            sys.exit(1)

        return version

    def compute_version(self, version_source: str = "package-json") -> str:
        """Compute the final version string.

        Delegates git commit counting and tag-based build number computation
        to the existing VersionBuilder class.

        Args:
            version_source: Either "package-json" or "git-tag".

        Returns:
            Computed version string (e.g., "1.2.42").
        """
        if version_source == "package-json":
            raw_version = self.read_package_json_version()
            parts = raw_version.split(".")
            major = parts[0]
            minor = parts[1]
            major_minor = f"{major}.{minor}"

            vb = VersionBuilder(VersionSource.PACKAGE_JSON)
            build_number = vb.get_git_build_number(major_minor, self.project_root)
            return f"{major}.{minor}.{build_number}"
        else:
            # git-tag source: delegate everything to VersionBuilder
            vb = VersionBuilder(VersionSource.GIT_TAG)
            return vb.build_version_with_patch()

    def write_version_file(self, version: str) -> None:
        """Write version string to version.txt in output_dir.

        Creates output_dir and parent directories if they don't exist.
        Overwrites existing version.txt without prompting.

        Args:
            version: The computed version string to write.

        Raises:
            SystemExit: If write fails due to filesystem error.
        """
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            version_file_path = os.path.join(self.output_dir, "version.txt")
            with open(version_file_path, "w", encoding="utf-8") as f:
                f.write(version)
        except OSError as e:
            print(
                f"ERROR: Failed to write version.txt: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

    def update_package_json(self, version: str) -> None:
        """Update the version field in package.json, preserving formatting.

        Preserves all other JSON fields, key ordering, and indentation style.

        Args:
            version: The computed version string to set.

        Raises:
            SystemExit: If package.json doesn't exist or write fails.
        """
        package_json_path = os.path.join(self.project_root, "package.json")

        # Check file exists
        if not os.path.isfile(package_json_path):
            print(
                f"ERROR: package.json not found at {package_json_path}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Read existing content
        try:
            with open(package_json_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(
                f"ERROR: Failed to read package.json: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Detect indentation by examining the first indented line
        indent: str | int = 2  # default to 2 spaces
        for line in content.splitlines():
            if line and line[0] in (" ", "\t"):
                if line[0] == "\t":
                    indent = "\t"
                else:
                    # Count leading spaces
                    stripped = line.lstrip(" ")
                    indent = len(line) - len(stripped)
                break

        # Parse JSON (Python 3.7+ dicts preserve insertion order)
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            print(
                f"ERROR: Failed to parse package.json: {e}",
                file=sys.stderr,
            )
            sys.exit(1)

        # Update only the version field
        data["version"] = version

        # Serialize back with detected indentation, preserving key order
        updated_content = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"

        # Write back to file
        try:
            with open(package_json_path, "w", encoding="utf-8") as f:
                f.write(updated_content)
        except OSError as e:
            print(
                f"ERROR: Failed to write package.json: {e}",
                file=sys.stderr,
            )
            sys.exit(1)


def main() -> None:
    """CLI entry point. Parses args, computes version, writes output."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    parser = argparse.ArgumentParser(
        description="Compute version from package.json and git history, write version.txt"
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Path to the Node.js project root containing package.json (default: current directory)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write version.txt (default: same as --project-root)",
    )
    parser.add_argument(
        "--update-package-json",
        action="store_true",
        help="Update the version field in package.json with the computed version",
    )
    parser.add_argument(
        "--version-source",
        default="package-json",
        choices=["package-json", "git-tag"],
        help="Source for base version: 'package-json' reads from package.json, "
        "'git-tag' uses the latest git tag (default: package-json)",
    )

    args = parser.parse_args()

    # Validate --project-root path exists and is a directory
    resolved_project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(resolved_project_root):
        print(
            f"ERROR: --project-root path does not exist or is not a directory: {args.project_root}",
            file=sys.stderr,
        )
        sys.exit(1)

    cli = VersioningCli(
        project_root=resolved_project_root,
        output_dir=args.output_dir,
    )
    version = cli.compute_version(version_source=args.version_source)
    cli.write_version_file(version)

    if args.update_package_json:
        cli.update_package_json(version)

    print(version)


if __name__ == "__main__":
    main()
