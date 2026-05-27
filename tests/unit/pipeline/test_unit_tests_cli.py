"""Unit tests for cdk_factory.pipeline.commands.unit_tests_cli."""

import os
from pathlib import Path
from unittest.mock import patch

from cdk_factory.pipeline.commands.unit_tests_cli import get_project_root


def test_get_project_root_with_override() -> None:
    """Explicit override path takes precedence over env var and cwd."""
    result = get_project_root("/tmp/my-project")
    assert result == str(Path("/tmp/my-project").resolve())


def test_get_project_root_from_codebuild_env() -> None:
    """CODEBUILD_SRC_DIR is used when no override is provided."""
    with patch.dict(os.environ, {"CODEBUILD_SRC_DIR": "/codebuild/src"}):
        result = get_project_root()
    assert result == "/codebuild/src"


def test_get_project_root_falls_back_to_cwd() -> None:
    """Falls back to cwd when no override and no env var."""
    with patch.dict(os.environ, {}, clear=True):
        # Remove CODEBUILD_SRC_DIR if present
        env_copy = os.environ.copy()
        env_copy.pop("CODEBUILD_SRC_DIR", None)
        with patch.dict(os.environ, env_copy, clear=True):
            result = get_project_root()
    assert result == str(Path.cwd().resolve())


def test_get_project_root_override_takes_precedence_over_env() -> None:
    """Override path takes precedence even when CODEBUILD_SRC_DIR is set."""
    with patch.dict(os.environ, {"CODEBUILD_SRC_DIR": "/codebuild/src"}):
        result = get_project_root("/tmp/override")
    assert result == str(Path("/tmp/override").resolve())


def test_module_is_runnable(tmp_path: Path) -> None:
    """Verify the module can be invoked with --help without error."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cdk_factory.pipeline.commands.unit_tests_cli",
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--project-root" in result.stdout
    assert "--ignore-integration" in result.stdout
