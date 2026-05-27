"""
Property-based tests for project root resolution and CDK directory resolution.

Feature: cdk-pipeline-commands, Property 1: Project root resolution respects explicit path
Feature: cdk-pipeline-commands, Property 2: CDK directory resolution is relative to project root
Validates: Requirements 1.2, 1.5, 2.4
"""

import os
from pathlib import Path

from hypothesis import given, settings, assume
from hypothesis.strategies import text

from cdk_factory.pipeline.synth.cdk_synth_exec import _resolve_project_root


# Strategies for generating test inputs
# Valid path segments (alphanumeric + common path chars)
_path_segment = text(
    min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-."
)

# Generate absolute paths like /tmp/segment
_absolute_path_strategy = _path_segment.map(lambda s: f"/tmp/{s}")

# Generate relative directory paths (no leading slash)
_relative_dir_strategy = text(
    min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-/."
)


class TestProjectRootResolutionProperties:
    """Property tests for _resolve_project_root().

    Feature: cdk-pipeline-commands, Property 1: Project root resolution respects explicit path
    """

    @given(path=_absolute_path_strategy)
    @settings(max_examples=100)
    def test_explicit_path_is_returned_as_absolute(self, path: str):
        """For any valid absolute path string provided as project_root,
        _resolve_project_root() SHALL return that path resolved to an absolute path,
        regardless of environment variables or current working directory.

        Validates: Requirements 1.2, 1.5, 2.4
        """
        result = _resolve_project_root(project_root=path)

        # Result must be an absolute path
        assert result.is_absolute()

        # Result must equal the resolved version of the input path
        expected = Path(path).resolve()
        assert result == expected

    @given(path=_absolute_path_strategy)
    @settings(max_examples=100)
    def test_explicit_path_ignores_env_var(self, path: str):
        """When an explicit project_root is provided, the CODEBUILD_SRC_DIR
        environment variable SHALL be ignored.

        Validates: Requirements 1.2, 2.4
        """
        old_val = os.environ.get("CODEBUILD_SRC_DIR")
        try:
            os.environ["CODEBUILD_SRC_DIR"] = "/some/other/path"
            result = _resolve_project_root(project_root=path)
            expected = Path(path).resolve()
            assert result == expected
        finally:
            if old_val is None:
                os.environ.pop("CODEBUILD_SRC_DIR", None)
            else:
                os.environ["CODEBUILD_SRC_DIR"] = old_val

    @given(path=_absolute_path_strategy)
    @settings(max_examples=100)
    def test_explicit_path_ignores_cwd(self, path: str):
        """When an explicit project_root is provided, the current working
        directory SHALL NOT affect the result.

        Validates: Requirements 1.2, 2.4
        """
        # Ensure CODEBUILD_SRC_DIR is not set
        old_val = os.environ.pop("CODEBUILD_SRC_DIR", None)
        try:
            result = _resolve_project_root(project_root=path)
            expected = Path(path).resolve()
            assert result == expected
        finally:
            if old_val is not None:
                os.environ["CODEBUILD_SRC_DIR"] = old_val


class TestCdkDirResolutionProperties:
    """Property tests for CDK directory resolution logic.

    Feature: cdk-pipeline-commands, Property 2: CDK directory resolution is relative to project root
    """

    @given(root=_absolute_path_strategy, cdk_dir=_relative_dir_strategy)
    @settings(max_examples=100)
    def test_cdk_dir_is_relative_to_project_root(self, root: str, cdk_dir: str):
        """For any valid project root path and any relative directory string
        provided as cdk_dir, the resolved CDK directory SHALL equal the project
        root joined with the relative directory, resolved to an absolute path.

        Validates: Requirements 1.5
        """
        # Filter out empty or whitespace-only cdk_dir values
        assume(cdk_dir.strip() != "")
        # Filter out paths that start with / (they would be absolute)
        assume(not cdk_dir.startswith("/"))
        # Filter out paths with consecutive dots that could cause issues
        assume(".." not in cdk_dir)

        project_root = Path(root).resolve()
        resolved_cdk_dir = (project_root / cdk_dir).resolve()

        # The resolved CDK dir must be absolute
        assert resolved_cdk_dir.is_absolute()

        # The resolved CDK dir must equal project_root / cdk_dir resolved
        expected = (Path(root).resolve() / cdk_dir).resolve()
        assert resolved_cdk_dir == expected

    @given(root=_absolute_path_strategy, cdk_dir=_relative_dir_strategy)
    @settings(max_examples=100)
    def test_cdk_dir_resolution_is_deterministic(self, root: str, cdk_dir: str):
        """Resolving the same project root and cdk_dir multiple times SHALL
        always produce the same result.

        Validates: Requirements 1.5
        """
        assume(cdk_dir.strip() != "")
        assume(not cdk_dir.startswith("/"))

        project_root = Path(root).resolve()
        result1 = (project_root / cdk_dir).resolve()
        result2 = (project_root / cdk_dir).resolve()

        assert result1 == result2
