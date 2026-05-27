"""CodeArtifact Publisher CLI — Build and publish Python packages to AWS CodeArtifact.

Ported from aplos_saas_devops_cdk.publishing.codeartifact_publish with import paths
updated to cdk_factory.pipeline.*.

Usage:
    python -m cdk_factory.pipeline.publishing.codeartifact_publish \
        --project-root <path> \
        --skip-login \
        --skip-build \
        --skip-upload
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def _resolve_project_root(project_root: Optional[str] = None) -> str:
    """Resolve the project root directory.

    Resolution order:
      1. Explicit ``project_root`` argument (if provided)
      2. ``CODEBUILD_SRC_DIR`` environment variable (if set)
      3. Current working directory

    Args:
        project_root: Optional explicit path to the project root.

    Returns:
        Resolved absolute path to the project root directory as a string.
    """
    if project_root:
        return str(Path(project_root).resolve())

    codebuild_src = os.environ.get("CODEBUILD_SRC_DIR")
    if codebuild_src:
        return codebuild_src

    return str(Path.cwd().resolve())


def _run_command(
    cmd: List[str], cwd: Optional[str] = None, description: str = ""
) -> subprocess.CompletedProcess:
    """Run a subprocess command and return the result.

    Args:
        cmd: Command and arguments to execute.
        cwd: Working directory for the command.
        description: Human-readable description of the command for error messages.

    Returns:
        CompletedProcess instance.
    """
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def _authenticate_codeartifact(project_root: str) -> None:
    """Authenticate with AWS CodeArtifact using the AWS CLI.

    Uses ``aws codeartifact login`` with pip as the tool. Configuration
    is read from environment variables:
      - CODE_ARTIFACT_DOMAIN: The CodeArtifact domain name
      - CODE_ARTIFACT_DOMAIN_OWNER: The AWS account ID that owns the domain
      - CODE_ARTIFACT_REPOSITORY: The repository name
      - AWS_REGION or AWS_DEFAULT_REGION: The AWS region

    Args:
        project_root: Path to the project root directory.

    Raises:
        SystemExit: If authentication fails.
    """
    domain = os.environ.get("CODE_ARTIFACT_DOMAIN", "")
    domain_owner = os.environ.get("CODE_ARTIFACT_DOMAIN_OWNER", "")
    repository = os.environ.get("CODE_ARTIFACT_REPOSITORY", "")
    region = os.environ.get("AWS_REGION") or os.environ.get(
        "AWS_DEFAULT_REGION", "us-east-1"
    )

    if not domain or not domain_owner or not repository:
        print(
            "❌ CodeArtifact authentication failed: "
            "Missing required environment variables. "
            "Set CODE_ARTIFACT_DOMAIN, CODE_ARTIFACT_DOMAIN_OWNER, "
            "and CODE_ARTIFACT_REPOSITORY.",
            file=sys.stderr,
        )
        sys.exit(1)

    cmd = [
        "aws",
        "codeartifact",
        "login",
        "--tool",
        "pip",
        "--domain",
        domain,
        "--domain-owner",
        domain_owner,
        "--repository",
        repository,
        "--region",
        region,
    ]

    # Add profile if set
    aws_profile = os.environ.get("AWS_PROFILE")
    if aws_profile:
        cmd.extend(["--profile", aws_profile])

    print("🔐 Authenticating with CodeArtifact...")
    result = _run_command(cmd, cwd=project_root, description="CodeArtifact login")

    if result.returncode != 0:
        print(
            "❌ CodeArtifact authentication failed. "
            "Check your AWS credentials and environment variables.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("✓ CodeArtifact authentication successful")


def _build_package(project_root: str) -> None:
    """Build the Python package distribution.

    Runs ``python -m build`` to create sdist and wheel distributions
    in the ``dist/`` directory.

    Args:
        project_root: Path to the project root directory.

    Raises:
        SystemExit: If the build fails.
    """
    print("📦 Building Python package distribution...")

    # Clean previous dist artifacts
    dist_dir = Path(project_root) / "dist"
    if dist_dir.exists():
        import shutil

        shutil.rmtree(dist_dir)
        print("  Cleaned previous dist/ directory")

    cmd = [sys.executable, "-m", "build"]
    result = _run_command(cmd, cwd=project_root, description="Package build")

    if result.returncode != 0:
        print(
            "❌ Package build failed. Check your pyproject.toml and build configuration.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("✓ Package build successful")


def _upload_package(project_root: str) -> None:
    """Upload the built package to CodeArtifact.

    Uses ``twine upload`` to upload all distributions in the ``dist/``
    directory to the CodeArtifact repository configured via pip.

    Args:
        project_root: Path to the project root directory.

    Raises:
        SystemExit: If the upload fails.
    """
    print("🚀 Uploading package to CodeArtifact...")

    dist_dir = Path(project_root) / "dist"
    if not dist_dir.exists() or not any(dist_dir.iterdir()):
        print(
            "❌ Upload failed: No distribution files found in dist/. "
            "Run build first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Use twine to upload — it respects pip's configured repository
    cmd = [
        sys.executable,
        "-m",
        "twine",
        "upload",
        "--repository",
        "codeartifact",
        str(dist_dir / "*"),
    ]

    result = _run_command(cmd, cwd=project_root, description="Package upload")

    if result.returncode != 0:
        print(
            "❌ Package upload to CodeArtifact failed. "
            "Check your authentication and repository configuration.",
            file=sys.stderr,
        )
        sys.exit(1)

    print("✓ Package uploaded to CodeArtifact successfully")


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the CodeArtifact Publisher CLI."""
    parser = argparse.ArgumentParser(
        description="Build and publish Python packages to AWS CodeArtifact."
    )
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory. "
        "Defaults to CODEBUILD_SRC_DIR env var, then cwd.",
    )
    parser.add_argument(
        "--skip-login",
        action="store_true",
        default=False,
        help="Skip CodeArtifact authentication (use existing credentials).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        default=False,
        help="Skip building the package distribution.",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        default=False,
        help="Skip uploading the package to CodeArtifact.",
    )

    args = parser.parse_args(argv)

    # Resolve project root
    project_root = _resolve_project_root(args.project_root)

    print(f"{'=' * 60}")
    print("CodeArtifact Publisher")
    print(f"{'=' * 60}")
    print(f"  Project Root: {project_root}")
    print(f"  Skip Login: {args.skip_login}")
    print(f"  Skip Build: {args.skip_build}")
    print(f"  Skip Upload: {args.skip_upload}")
    print(f"{'=' * 60}")

    # Step 1: Authenticate with CodeArtifact
    if not args.skip_login:
        _authenticate_codeartifact(project_root)
    else:
        print("⏭️  Skipping CodeArtifact authentication (--skip-login)")

    # Step 2: Build the package
    if not args.skip_build:
        _build_package(project_root)
    else:
        print("⏭️  Skipping package build (--skip-build)")

    # Step 3: Upload to CodeArtifact
    if not args.skip_upload:
        _upload_package(project_root)
    else:
        print("⏭️  Skipping package upload (--skip-upload)")

    print(f"\n{'=' * 60}")
    print("CodeArtifact Publisher — complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
