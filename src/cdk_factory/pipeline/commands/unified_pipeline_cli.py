"""Unified Pipeline CLI — Centralized build/deploy orchestrator.

Auto-detects project configuration and executes build/deploy steps in a
fixed order: run-tests → deploy-images → publish-code-artifact.

Usage:
    python3 -m cdk_factory.pipeline.commands.unified_pipeline_cli \
        --run-tests \
        --deploy-images \
        --publish-code-artifact \
        --project-root <path>

Ported from aplos_saas_devops_cdk.commands.unified_pipeline_cli with import paths
updated to cdk_factory.pipeline.*.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional

from cdk_factory.pipeline.versioning.pyproject_version import _load_toml
from cdk_factory.utilities.version_builder import VersionBuilder, VersionSource
from cdk_factory.pipeline.versioning.pyproject_version import (
    read_project_version_from_pyproject,
)


def get_project_root(override_path: Optional[str] = None) -> str:
    """Get project root directory.

    Resolution order:
      1. Explicit override path (--project-root flag)
      2. CODEBUILD_SRC_DIR environment variable
      3. Current working directory

    Args:
        override_path: Optional explicit path to the project root.

    Returns:
        Resolved absolute path to the project root directory.
    """
    if override_path:
        return str(Path(override_path).resolve())

    codebuild_src = os.environ.get("CODEBUILD_SRC_DIR")
    if codebuild_src:
        return codebuild_src

    return str(Path.cwd().resolve())


def read_package_name(project_root: str) -> str:
    """Read the package name from pyproject.toml at the given project root.

    Reads the ``[project].name`` field from pyproject.toml.

    Args:
        project_root: Path to the project root directory containing pyproject.toml.

    Returns:
        The package name string.

    Raises:
        SystemExit: If pyproject.toml does not exist or is missing the name field.
    """
    pyproject_path = Path(project_root) / "pyproject.toml"

    if not pyproject_path.exists():
        print(
            f"❌ Error: pyproject.toml not found at: {pyproject_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = _load_toml(pyproject_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(
            f"❌ Error: Failed to parse pyproject.toml at {pyproject_path}: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    project = data.get("project")
    if not isinstance(project, dict):
        print(
            "❌ Error: Missing [project] section in pyproject.toml",
            file=sys.stderr,
        )
        sys.exit(1)

    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        print(
            "❌ Error: Missing or empty project.name in pyproject.toml",
            file=sys.stderr,
        )
        sys.exit(1)

    return name.strip()


def derive_app_name(package_name: str) -> str:
    """Derive the application name from the package name.

    Replaces underscores with hyphens. This is the ONLY transformation applied.
    No prefix stripping, no case normalization, no truncation.

    Args:
        package_name: The Python package name (e.g., ``asset_workbench_workload``).

    Returns:
        The derived app name (e.g., ``asset-workbench-workload``).
    """
    return package_name.replace("_", "-")


def get_docker_config_path(project_root: str) -> str:
    """Get the path to the Docker images configuration file.

    Args:
        project_root: Path to the project root directory.

    Returns:
        Absolute path to docker-images.json.
    """
    return str(Path(project_root) / "docker-images.json")


def get_image_app_names(config_path: str) -> List[str]:
    """Get the list of image app names from the Docker config.

    Args:
        config_path: Path to docker-images.json.

    Returns:
        List of repo_name values from the images array.
    """
    if not os.path.exists(config_path):
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    images = config.get("images", [])
    if not isinstance(images, list):
        return []

    return [img.get("repo_name", "") for img in images if img.get("repo_name")]


def compute_version(project_root: str, package_name: str) -> str:
    """Compute the version string using VersionBuilder and pyproject.toml.

    Reads the base version from pyproject.toml, computes the git-based
    build number, and returns the full version string (major.minor.patch).

    Args:
        project_root: Path to the project root directory.
        package_name: The package name (used for version.py updates).

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


def invoke_cli(module_main: Callable, argv: List[str]) -> None:
    """Invoke a CLI module's main function with the given arguments.

    Handles both modules that accept an ``argv`` parameter and those that
    read from ``sys.argv`` directly. Tries passing ``argv`` first; if the
    function doesn't accept it, patches ``sys.argv`` temporarily.

    Args:
        module_main: The main() function of the CLI module to invoke.
        argv: Command-line arguments to pass to the module.

    Raises:
        Exception: Re-raises any exception from the invoked module.
    """
    import inspect

    sig = inspect.signature(module_main)
    params = list(sig.parameters.values())

    # If the function accepts at least one positional-or-keyword parameter,
    # pass argv directly. Otherwise, patch sys.argv.
    if params and params[0].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    ):
        module_main(argv)
    else:
        original_argv = sys.argv
        try:
            sys.argv = ["unified_pipeline_cli"] + argv
            module_main()
        finally:
            sys.argv = original_argv


def run_step(step_name: str, step_number: int, fn: Callable) -> None:
    """Execute a pipeline step with header/footer formatting.

    Args:
        step_name: Human-readable name of the step.
        step_number: Step number for display.
        fn: Callable that executes the step logic.

    Raises:
        SystemExit: If the step fails.
    """
    print(f"\n{'=' * 60}")
    print(f"  Step {step_number}: {step_name}")
    print(f"{'=' * 60}")

    try:
        fn()
        print(f"  ✓ Step {step_number}: {step_name} — complete")
    except SystemExit as e:
        if e.code and e.code != 0:
            print(
                f"❌ Step {step_number} failed: {step_name}",
                file=sys.stderr,
            )
            raise
    except Exception as e:
        print(
            f"❌ Step {step_number} failed: {step_name} — {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the Unified Pipeline CLI.

    Accepts deprecated arguments without error, logging a deprecation
    warning to stderr.
    """
    parser = argparse.ArgumentParser(
        description="Unified Pipeline CLI — Orchestrate build and deploy steps.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Action flags
    parser.add_argument(
        "--run-tests",
        action="store_true",
        default=False,
        help="Run unit tests.",
    )
    parser.add_argument(
        "--deploy-images",
        action="store_true",
        default=False,
        help="Build, tag, push Docker images and update Lambda functions.",
    )
    parser.add_argument(
        "--publish-code-artifact",
        action="store_true",
        default=False,
        help="Build and publish package to AWS CodeArtifact.",
    )

    # Configuration flags
    parser.add_argument(
        "--project-root",
        type=str,
        default=None,
        help="Project root directory. Defaults to CODEBUILD_SRC_DIR or cwd.",
    )

    # Deprecated arguments — accepted without error for backward compatibility
    parser.add_argument(
        "--app-name",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--package-name",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--skip-login",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the Unified Pipeline CLI.

    Orchestrates pipeline steps in fixed order:
      1. run-tests
      2. deploy-images (build → tag → push → SSM publish → Lambda update)
      3. publish-code-artifact
    """
    args = _parse_args(argv)

    # Log deprecation warnings for deprecated args
    if args.app_name:
        print(
            "⚠️  Warning: --app-name is deprecated and will be ignored. "
            "App name is now derived from pyproject.toml.",
            file=sys.stderr,
        )
    if args.package_name:
        print(
            "⚠️  Warning: --package-name is deprecated and will be ignored. "
            "Package name is now read from pyproject.toml.",
            file=sys.stderr,
        )
    if args.skip_login:
        print(
            "⚠️  Warning: --skip-login is deprecated and will be ignored.",
            file=sys.stderr,
        )

    # Check that at least one action flag is provided
    if not args.run_tests and not args.deploy_images and not args.publish_code_artifact:
        print(
            "Error: No action flags provided. Specify at least one of:\n"
            "  --run-tests\n"
            "  --deploy-images\n"
            "  --publish-code-artifact\n",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve project root
    project_root = get_project_root(args.project_root)

    # Read package name from pyproject.toml
    package_name = read_package_name(project_root)

    # Derive app name
    app_name = derive_app_name(package_name)

    print(f"{'=' * 60}")
    print("  Unified Pipeline CLI")
    print(f"{'=' * 60}")
    print(f"  Project Root: {project_root}")
    print(f"  Package Name: {package_name}")
    print(f"  App Name: {app_name}")
    print(f"  Run Tests: {args.run_tests}")
    print(f"  Deploy Images: {args.deploy_images}")
    print(f"  Publish CodeArtifact: {args.publish_code_artifact}")
    print(f"{'=' * 60}")

    step_number = 0

    # Step: Run Tests
    if args.run_tests:
        step_number += 1
        from cdk_factory.pipeline.commands.unit_tests_cli import (
            main as unit_tests_main,
        )

        def _run_tests():
            invoke_cli(unit_tests_main, ["--project-root", project_root])

        run_step("Run Tests", step_number, _run_tests)

    # Step: Deploy Images
    if args.deploy_images:
        docker_config_path = get_docker_config_path(project_root)

        if not os.path.exists(docker_config_path):
            print(
                f"⚠️  Warning: docker-images.json not found at {docker_config_path}. "
                "Skipping deploy-images step.",
                file=sys.stderr,
            )
        else:
            # Sub-step: Docker Build
            step_number += 1
            from cdk_factory.pipeline.commands.docker_build_cli import (
                main as docker_build_main,
            )

            def _docker_build():
                invoke_cli(
                    docker_build_main,
                    [
                        "--package-name",
                        package_name,
                        "--config",
                        docker_config_path,
                        "--action",
                        "build",
                    ],
                )

            run_step("Docker Build", step_number, _docker_build)

            # Sub-step: Docker Tag
            step_number += 1

            def _docker_tag():
                invoke_cli(
                    docker_build_main,
                    [
                        "--package-name",
                        package_name,
                        "--config",
                        docker_config_path,
                        "--action",
                        "tag",
                        "--tag-version",
                    ],
                )

            run_step("Docker Tag", step_number, _docker_tag)

            # Sub-step: Docker Push
            step_number += 1

            def _docker_push():
                invoke_cli(
                    docker_build_main,
                    [
                        "--package-name",
                        package_name,
                        "--config",
                        docker_config_path,
                        "--action",
                        "push",
                        "--tag-version",
                    ],
                )

            run_step("Docker Push", step_number, _docker_push)

            # Sub-step: SSM Publish
            step_number += 1
            from cdk_factory.pipeline.commands.parameter_store_cli import (
                main as parameter_store_main,
            )

            def _ssm_publish():
                invoke_cli(
                    parameter_store_main,
                    ["--app-name", app_name, "--project-root", project_root],
                )

            run_step("SSM Version Publish", step_number, _ssm_publish)

            # Sub-step: Lambda Image Update
            step_number += 1
            from cdk_factory.pipeline.commands.lambda_image_updater import (
                main as lambda_updater_main,
            )

            def _lambda_update():
                invoke_cli(lambda_updater_main, ["--config", docker_config_path])

            run_step("Lambda Image Update", step_number, _lambda_update)

    # Step: Publish CodeArtifact
    if args.publish_code_artifact:
        step_number += 1
        from cdk_factory.pipeline.publishing.codeartifact_publish import (
            main as codeartifact_main,
        )

        def _publish_codeartifact():
            invoke_cli(codeartifact_main, ["--project-root", project_root])

        run_step("Publish to CodeArtifact", step_number, _publish_codeartifact)

    # Success
    print(f"\n{'=' * 60}")
    print("  ✓ Unified Pipeline CLI — all steps complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
