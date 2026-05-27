"""Parameter Store CLI — Publish version to AWS SSM Parameter Store.

Computes the project version using VersionBuilder and publishes it to
the SSM parameter path ``/<app-name>/version``.

Usage:
    python -m cdk_factory.pipeline.commands.parameter_store_cli \
        --app-name <name> \
        --project-root <path>

Ported from aplos_saas_devops_cdk.commands.parameter_store_cli with import paths updated.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

import boto3

from cdk_factory.utilities.version_builder import VersionBuilder, VersionSource
from cdk_factory.pipeline.versioning.pyproject_version import (
    read_project_version_from_pyproject,
)
from cdk_factory.pipeline.ssm.version_publisher import publish_version_to_ssm


def _resolve_project_root(project_root: Optional[str] = None) -> str:
    """Resolve the project root directory.

    Priority: explicit flag → CODEBUILD_SRC_DIR → cwd.
    """
    if project_root:
        return str(Path(project_root).resolve())
    codebuild_src = os.environ.get("CODEBUILD_SRC_DIR")
    if codebuild_src:
        return codebuild_src
    return str(Path.cwd())


def _compute_version(project_root: str) -> str:
    """Compute the version string using VersionBuilder and pyproject.toml.

    Reads the base version from pyproject.toml, computes the git-based
    build number, and returns the full version string (major.minor.patch).

    Args:
        project_root: Path to the project root directory.

    Returns:
        The computed version string.
    """
    base_version = read_project_version_from_pyproject(project_root)
    vb = VersionBuilder(version_source=VersionSource.GIT_TAG)
    major, minor, _patch = vb.parse_version(base_version)
    major_minor = f"{major}.{minor}"

    build_number = vb.get_git_build_number(major_minor, project_root)
    version = f"{major_minor}.{build_number}"
    return version


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the Parameter Store CLI."""
    parser = argparse.ArgumentParser(
        description="Publish version to AWS SSM Parameter Store."
    )
    parser.add_argument(
        "--app-name",
        required=True,
        help="Application name used to derive the SSM parameter path (e.g., 'my-app').",
    )
    parser.add_argument(
        "--project-root",
        required=False,
        default=None,
        help="Project root directory. Defaults to CODEBUILD_SRC_DIR or cwd.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the Parameter Store CLI."""
    args = _parse_args(argv)

    app_name = args.app_name
    if not app_name:
        print(
            "Error: --app-name is required.",
            file=sys.stderr,
        )
        sys.exit(1)

    project_root = _resolve_project_root(args.project_root)

    print(f"{'=' * 60}")
    print("Parameter Store CLI")
    print(f"{'=' * 60}")
    print(f"  App Name: {app_name}")
    print(f"  Project Root: {project_root}")

    # Compute version
    version = _compute_version(project_root)
    print(f"  Version: {version}")

    # Publish to SSM
    parameter_name_template = "/{{APP_NAME}}/version"
    template_values = {"APP_NAME": app_name}

    ssm_client = boto3.client("ssm")

    try:
        resolved_name = publish_version_to_ssm(
            ssm_client=ssm_client,
            version=version,
            parameter_name_template=parameter_name_template,
            template_values=template_values,
        )
        print(f"  Published: {resolved_name} = {version}")
    except Exception as e:
        print(f"Error: Failed to publish version to SSM: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{'=' * 60}")
    print("Parameter Store CLI — complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
