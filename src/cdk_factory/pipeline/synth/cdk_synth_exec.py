"""CDK synth execution CLI module.

Resolves the project root and CDK directory, then executes ``npx cdk synth``
as a subprocess.

Ported from aplos_saas_devops_cdk.synth.cdk_synth_exec with import paths
updated to cdk_factory.pipeline.*.

CLI Interface:
    python -m cdk_factory.pipeline.synth.cdk_synth_exec \
        --project-root <path> \
        --cdk-dir <relative-path> \
        --operation synth
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def _resolve_project_root(project_root: Optional[str] = None) -> Path:
    """Resolve the project root directory.

    Resolution order:
      1. Explicit ``project_root`` argument (if provided)
      2. ``CODEBUILD_SRC_DIR`` environment variable (if set)
      3. Current working directory

    Args:
        project_root: Optional explicit path to the project root.

    Returns:
        Resolved absolute path to the project root directory.
    """
    if project_root:
        return Path(project_root).resolve()

    codebuild_src = os.environ.get("CODEBUILD_SRC_DIR")
    if codebuild_src:
        return Path(codebuild_src).resolve()

    return Path.cwd().resolve()


def main() -> None:
    """Parse arguments, validate CDK directory, and run npx cdk synth."""
    parser = argparse.ArgumentParser(
        description="Execute CDK synth in the resolved CDK directory."
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Path to the project root directory. "
        "Falls back to CODEBUILD_SRC_DIR env var, then cwd.",
    )
    parser.add_argument(
        "--cdk-dir",
        type=str,
        default="devops/cdk-iac",
        help="Relative path from project root to the CDK app directory. "
        "Defaults to 'devops/cdk-iac'.",
    )
    parser.add_argument(
        "--operation",
        type=str,
        default="synth",
        help="CDK operation to perform. Defaults to 'synth'.",
    )

    args = parser.parse_args()

    # Resolve project root
    project_root = _resolve_project_root(args.project_root)

    # Resolve CDK directory relative to project root
    cdk_dir = (project_root / args.cdk_dir).resolve()

    # Validate CDK directory exists
    if not cdk_dir.exists():
        raise FileNotFoundError(f"CDK directory does not exist: {cdk_dir}")

    # Verify npx is available on PATH
    if shutil.which("npx") is None:
        raise EnvironmentError(
            "npx is not available on the system PATH. "
            "Please install Node.js and npm."
        )

    # Execute npx cdk synth
    print(f"Running 'npx cdk {args.operation}' in: {cdk_dir}")
    result = subprocess.run(
        ["npx", "cdk", args.operation],
        cwd=str(cdk_dir),
    )

    # Propagate non-zero exit code
    if result.returncode != 0:
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
