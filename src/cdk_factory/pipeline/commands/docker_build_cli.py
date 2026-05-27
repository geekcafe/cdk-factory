"""Docker Build CLI — Build, tag, and push Docker images.

Ported from aplos_saas_devops_cdk.commands.docker_build_cli with import paths
updated to cdk_factory.pipeline.*.

Usage:
    python -m cdk_factory.pipeline.commands.docker_build_cli \
        --package-name <name> \
        --action build|tag|push \
        --config <path> \
        --tag <name> --tag-version
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from cdk_factory.utilities.docker_utilities import DockerUtilities
from cdk_factory.utilities.version_builder import VersionBuilder, VersionSource
from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags
from cdk_factory.pipeline.versioning.pyproject_version import (
    read_project_version_from_pyproject,
)
from cdk_factory.pipeline.versioning.pyproject_version_writer import (
    update_version_in_pyproject,
)
from cdk_factory.pipeline.versioning.version_file_writer import (
    update_version_in_version_py,
)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the Docker build CLI."""
    parser = argparse.ArgumentParser(
        description="Docker Build CLI — Build, tag, and push Docker images."
    )
    parser.add_argument(
        "--package-name",
        required=True,
        help="The package name (e.g., 'my_package').",
    )
    parser.add_argument(
        "--config",
        required=False,
        default=None,
        help="Path to docker-images.json configuration file.",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["build", "tag", "push"],
        help="Docker action to perform: build, tag, or push.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="One or more tags to apply (used with 'tag' action). Can be repeated.",
    )
    parser.add_argument(
        "--tag-version",
        action="store_true",
        default=False,
        help="Include the computed version as an additional tag.",
    )
    parser.add_argument(
        "--project-root",
        required=False,
        default=None,
        help="Project root directory. Defaults to CODEBUILD_SRC_DIR or cwd.",
    )

    return parser.parse_args(argv)


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


def _load_config(config_path: str) -> Dict[str, Any]:
    """Load and validate the Docker images configuration file.

    Args:
        config_path: Path to the docker-images.json file.

    Returns:
        Parsed configuration dictionary.

    Raises:
        SystemExit: If the file does not exist or is not valid JSON.
    """
    if not os.path.exists(config_path):
        print(
            f"Error: Config file not found: {config_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(
            f"Error: Invalid JSON in config file '{config_path}': {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    return config


def _compute_version(project_root: str, package_name: str) -> str:
    """Compute the version string using VersionBuilder and pyproject.toml.

    Reads the base version from pyproject.toml, computes the git-based
    build number, and returns the full version string (major.minor.patch).

    Also updates pyproject.toml and version.py with the computed version.

    Args:
        project_root: Path to the project root directory.
        package_name: The package name for version.py updates.

    Returns:
        The computed version string.
    """
    base_version = read_project_version_from_pyproject(project_root)
    vb = VersionBuilder(version_source=VersionSource.GIT_TAG)
    major, minor, _patch = vb.parse_version(base_version)
    major_minor = f"{major}.{minor}"

    build_number = vb.get_git_build_number(major_minor, project_root)
    version = f"{major_minor}.{build_number}"

    # Update version in pyproject.toml and version.py
    update_version_in_pyproject(project_root, version)
    try:
        update_version_in_version_py(project_root, package_name, version)
    except FileNotFoundError:
        # version.py may not exist for all packages; this is non-fatal
        pass

    return version


def _get_images_from_config(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract the images array from the configuration.

    Args:
        config: Parsed configuration dictionary.

    Returns:
        List of image configuration dictionaries.
    """
    images = config.get("images", [])
    if not isinstance(images, list):
        print("Error: 'images' field in config must be an array.", file=sys.stderr)
        sys.exit(1)
    return images


def _do_build(
    docker: DockerUtilities,
    image_config: Dict[str, Any],
    project_root: str,
    version: str,
    package_name: str,
) -> None:
    """Execute the Docker build action for a single image config.

    Args:
        docker: DockerUtilities instance.
        image_config: Image configuration dictionary.
        project_root: Project root directory.
        version: Computed version string.
        package_name: Package name.
    """
    repo_name = image_config.get("repo_name", package_name)
    dockerfile = image_config.get("dockerfile", "Dockerfile")

    # Resolve dockerfile path relative to project root
    dockerfile_path = os.path.join(project_root, dockerfile)
    context_path = project_root

    # Build tag is the repo_name:version
    build_tag = f"{repo_name}:{version}"

    print(f"  Building image: {build_tag}")
    print(f"  Dockerfile: {dockerfile_path}")
    print(f"  Context: {context_path}")

    build_args = image_config.get("build_args", [])
    docker.execute_build(
        docker_file=dockerfile_path,
        context_path=context_path,
        tag=build_tag,
        build_args=build_args,
    )
    docker.build_tag = build_tag


def _do_tag(
    docker: DockerUtilities,
    image_config: Dict[str, Any],
    version: str,
    package_name: str,
    tags: List[str],
    tag_version: bool,
    environment: Optional[str] = None,
) -> None:
    """Execute the Docker tag action for a single image config.

    Args:
        docker: DockerUtilities instance.
        image_config: Image configuration dictionary.
        version: Computed version string.
        package_name: Package name.
        tags: Explicit tags from CLI arguments.
        tag_version: Whether to include the version as an additional tag.
        environment: Optional environment name for tag resolution.
    """
    repo_name = image_config.get("repo_name", package_name)
    source_tag = docker.build_tag or f"{repo_name}:{version}"

    all_tags: List[str] = list(tags)

    if tag_version:
        all_tags.append(version)

    # If environment is available, resolve environment-specific tags
    if environment:
        env_tags = resolve_docker_tags(environment=environment, version=version)
        for t in env_tags:
            if t not in all_tags:
                all_tags.append(t)

    for tag in all_tags:
        new_tag = f"{repo_name}:{tag}"
        print(f"  Tagging: {source_tag} → {new_tag}")
        docker.execute_tag_command(source_tag, new_tag)


def _do_push(
    docker: DockerUtilities,
    image_config: Dict[str, Any],
    version: str,
    package_name: str,
    tags: List[str],
    tag_version: bool,
    environment: Optional[str] = None,
) -> None:
    """Execute the Docker push action for a single image config.

    Args:
        docker: DockerUtilities instance.
        image_config: Image configuration dictionary.
        version: Computed version string.
        package_name: Package name.
        tags: Explicit tags from CLI arguments.
        tag_version: Whether to include the version as an additional tag.
        environment: Optional environment name for tag resolution.
    """
    repo_name = image_config.get("repo_name", package_name)

    # Determine ECR details from image config or environment
    deployments = image_config.get("lambda_deployments", [])
    if not deployments:
        print(
            f"  Warning: No lambda_deployments found for {repo_name}. "
            "Cannot determine ECR URI for push.",
            file=sys.stderr,
        )
        return

    for deployment in deployments:
        enabled = deployment.get("enabled", True)
        if not enabled:
            continue

        account = deployment.get("account") or deployment.get("ecr_account", "")
        region = deployment.get("region", "us-east-1")
        ecr_account = deployment.get("ecr_account", account)

        if not ecr_account:
            print(
                f"  Warning: No account specified for deployment of {repo_name}. Skipping.",
                file=sys.stderr,
            )
            continue

        ecr_uri = f"{ecr_account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"

        # Resolve tags to push
        all_tags: List[str] = list(tags)
        if tag_version:
            all_tags.append(version)

        if environment:
            env_tags = resolve_docker_tags(environment=environment, version=version)
            for t in env_tags:
                if t not in all_tags:
                    all_tags.append(t)

        # If no explicit tags, use version
        if not all_tags:
            all_tags = [version]

        # Build fully qualified tag list
        qualified_tags = [f"{ecr_uri}:{t}" for t in all_tags]

        print(f"  Pushing to ECR: {ecr_uri}")
        print(f"  Tags: {all_tags}")

        aws_profile = os.environ.get("AWS_PROFILE")
        docker.execute_push_to_aws(
            aws_region=region,
            aws_ecr_uri=f"{ecr_account}.dkr.ecr.{region}.amazonaws.com",
            tags=qualified_tags,
            aws_profile=aws_profile,
        )


def main(argv: Optional[List[str]] = None) -> None:
    """Main entry point for the Docker Build CLI."""
    args = _parse_args(argv)

    project_root = _resolve_project_root(args.project_root)
    package_name = args.package_name
    action = args.action

    print(f"{'=' * 60}")
    print(f"Docker Build CLI")
    print(f"{'=' * 60}")
    print(f"  Package: {package_name}")
    print(f"  Action: {action}")
    print(f"  Project Root: {project_root}")

    # Compute version
    version = _compute_version(project_root, package_name)
    print(f"  Version: {version}")

    # Get environment from env var (used for tag resolution)
    environment = os.environ.get("ENVIRONMENT") or os.environ.get("ENV")

    # Initialize Docker utilities
    docker = DockerUtilities()

    # Load config if provided
    if args.config:
        config = _load_config(args.config)
        images = _get_images_from_config(config)
        print(f"  Config: {args.config}")
        print(f"  Images: {len(images)}")
    else:
        # No config — use a single default image entry based on package name
        images = [{"repo_name": package_name, "dockerfile": "Dockerfile"}]

    print(f"{'=' * 60}")

    # Execute the requested action for each image
    for image_config in images:
        repo_name = image_config.get("repo_name", package_name)
        print(f"\n  Processing image: {repo_name}")

        if action == "build":
            _do_build(docker, image_config, project_root, version, package_name)
        elif action == "tag":
            _do_tag(
                docker,
                image_config,
                version,
                package_name,
                args.tag,
                args.tag_version,
                environment,
            )
        elif action == "push":
            _do_push(
                docker,
                image_config,
                version,
                package_name,
                args.tag,
                args.tag_version,
                environment,
            )

    print(f"\n{'=' * 60}")
    print(f"Docker Build CLI — {action} complete")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
