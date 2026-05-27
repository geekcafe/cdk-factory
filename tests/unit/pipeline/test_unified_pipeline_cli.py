"""Unit tests for cdk_factory.pipeline.commands.unified_pipeline_cli.

Tests cover:
- derive_app_name examples (Requirements 9.3, 9.4, 9.5)
- Exit code 1 when no action flags provided (Requirement 2.3)
- Step ordering: run-tests → deploy-images → publish-code-artifact (Requirement 2.10)
- Halt on step failure (Requirement 2.14)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cdk_factory.pipeline.commands.unified_pipeline_cli import (
    derive_app_name,
    main,
)


# ---------------------------------------------------------------------------
# derive_app_name tests
# ---------------------------------------------------------------------------


class TestDeriveAppName:
    """Test derive_app_name replaces underscores with hyphens only."""

    def test_asset_workbench_workload(self) -> None:
        """asset_workbench_workload → asset-workbench-workload."""
        assert derive_app_name("asset_workbench_workload") == "asset-workbench-workload"

    def test_my_cool_app(self) -> None:
        """my_cool_app → my-cool-app."""
        assert derive_app_name("my_cool_app") == "my-cool-app"

    def test_preserves_hyphens_and_digits(self) -> None:
        """my-app2_utils → my-app2-utils (hyphens and digits preserved)."""
        assert derive_app_name("my-app2_utils") == "my-app2-utils"

    def test_no_underscores_unchanged(self) -> None:
        """A name with no underscores is returned unchanged."""
        assert derive_app_name("already-hyphenated") == "already-hyphenated"

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert derive_app_name("") == ""


# ---------------------------------------------------------------------------
# Exit code 1 when no flags provided
# ---------------------------------------------------------------------------


class TestNoFlagsExitCode:
    """Test that main exits with code 1 when no action flags are provided."""

    def test_exit_code_1_no_flags(self) -> None:
        """Calling main([]) with no action flags raises SystemExit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            main([])
        assert exc_info.value.code == 1

    def test_exit_code_1_only_project_root(self, tmp_path: Path) -> None:
        """Providing only --project-root (no action flag) still exits 1."""
        with pytest.raises(SystemExit) as exc_info:
            main(["--project-root", str(tmp_path)])
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Step ordering tests
# ---------------------------------------------------------------------------


class TestStepOrdering:
    """Test that steps execute in the fixed order: run-tests → deploy-images → publish-code-artifact."""

    def test_step_order_all_flags(self, tmp_path: Path) -> None:
        """When all flags are enabled, steps execute in correct order."""
        # Create a minimal pyproject.toml
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test_app"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        # Create docker-images.json so deploy-images doesn't skip
        docker_config = tmp_path / "docker-images.json"
        docker_config.write_text(
            '{"images": [{"repo_name": "test/repo", "dockerfile": "Dockerfile"}]}',
            encoding="utf-8",
        )

        call_order: list[str] = []

        # Side effects must accept *args/**kwargs because invoke_cli may call
        # with or without argv depending on signature inspection of the mock.
        def unit_tests_side_effect(*args, **kwargs):
            call_order.append("run-tests")

        def docker_build_side_effect(*args, **kwargs):
            call_order.append("deploy-images")

        def parameter_store_side_effect(*args, **kwargs):
            call_order.append("ssm-publish")

        def lambda_updater_side_effect(*args, **kwargs):
            call_order.append("lambda-update")

        def codeartifact_side_effect(*args, **kwargs):
            call_order.append("publish-code-artifact")

        mock_unit_tests = MagicMock(side_effect=unit_tests_side_effect)
        mock_docker_build = MagicMock(side_effect=docker_build_side_effect)
        mock_parameter_store = MagicMock(side_effect=parameter_store_side_effect)
        mock_lambda_updater = MagicMock(side_effect=lambda_updater_side_effect)
        mock_codeartifact = MagicMock(side_effect=codeartifact_side_effect)

        with (
            patch(
                "cdk_factory.pipeline.commands.unified_pipeline_cli.get_project_root",
                return_value=str(tmp_path),
            ),
            patch(
                "cdk_factory.pipeline.commands.unit_tests_cli.main",
                mock_unit_tests,
            ),
            patch(
                "cdk_factory.pipeline.commands.docker_build_cli.main",
                mock_docker_build,
            ),
            patch(
                "cdk_factory.pipeline.commands.parameter_store_cli.main",
                mock_parameter_store,
            ),
            patch(
                "cdk_factory.pipeline.commands.lambda_image_updater.main",
                mock_lambda_updater,
            ),
            patch(
                "cdk_factory.pipeline.publishing.codeartifact_publish.main",
                mock_codeartifact,
            ),
        ):
            main(
                [
                    "--run-tests",
                    "--deploy-images",
                    "--publish-code-artifact",
                    "--project-root",
                    str(tmp_path),
                ]
            )

        # Verify run-tests comes before deploy-images steps, which come before publish-code-artifact
        assert call_order[0] == "run-tests"
        # deploy-images produces multiple sub-steps (build, tag, push, ssm, lambda)
        assert call_order[-1] == "publish-code-artifact"
        # Ensure deploy-images steps are between run-tests and publish-code-artifact
        run_tests_idx = call_order.index("run-tests")
        publish_idx = call_order.index("publish-code-artifact")
        assert run_tests_idx < publish_idx


# ---------------------------------------------------------------------------
# Halt on step failure
# ---------------------------------------------------------------------------


class TestHaltOnStepFailure:
    """Test that pipeline halts when a step fails."""

    def test_halt_on_run_tests_failure(self, tmp_path: Path) -> None:
        """When run-tests fails, subsequent steps are not executed."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test_app"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        docker_config = tmp_path / "docker-images.json"
        docker_config.write_text(
            '{"images": [{"repo_name": "test/repo", "dockerfile": "Dockerfile"}]}',
            encoding="utf-8",
        )

        call_order: list[str] = []

        def failing_tests(*args, **kwargs):
            call_order.append("run-tests")
            raise SystemExit(1)

        mock_docker_build = MagicMock(
            side_effect=lambda *args, **kwargs: call_order.append("deploy-images")
        )
        mock_codeartifact = MagicMock(
            side_effect=lambda *args, **kwargs: call_order.append(
                "publish-code-artifact"
            )
        )

        with (
            patch(
                "cdk_factory.pipeline.commands.unified_pipeline_cli.get_project_root",
                return_value=str(tmp_path),
            ),
            patch(
                "cdk_factory.pipeline.commands.unit_tests_cli.main",
                MagicMock(side_effect=failing_tests),
            ),
            patch(
                "cdk_factory.pipeline.commands.docker_build_cli.main",
                mock_docker_build,
            ),
            patch(
                "cdk_factory.pipeline.commands.parameter_store_cli.main",
                MagicMock(side_effect=lambda *args, **kwargs: None),
            ),
            patch(
                "cdk_factory.pipeline.commands.lambda_image_updater.main",
                MagicMock(side_effect=lambda *args, **kwargs: None),
            ),
            patch(
                "cdk_factory.pipeline.publishing.codeartifact_publish.main",
                mock_codeartifact,
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "--run-tests",
                        "--deploy-images",
                        "--publish-code-artifact",
                        "--project-root",
                        str(tmp_path),
                    ]
                )

            assert exc_info.value.code == 1

        # Only run-tests was called; deploy-images and publish-code-artifact were not
        assert call_order == ["run-tests"]
        mock_docker_build.assert_not_called()
        mock_codeartifact.assert_not_called()

    def test_halt_on_deploy_images_failure(self, tmp_path: Path) -> None:
        """When deploy-images (docker build) fails, publish-code-artifact is not executed."""
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[project]\nname = "test_app"\nversion = "1.0.0"\n',
            encoding="utf-8",
        )

        docker_config = tmp_path / "docker-images.json"
        docker_config.write_text(
            '{"images": [{"repo_name": "test/repo", "dockerfile": "Dockerfile"}]}',
            encoding="utf-8",
        )

        call_order: list[str] = []

        def failing_docker_build(*args, **kwargs):
            call_order.append("deploy-images")
            raise SystemExit(1)

        mock_codeartifact = MagicMock(
            side_effect=lambda *args, **kwargs: call_order.append(
                "publish-code-artifact"
            )
        )

        with (
            patch(
                "cdk_factory.pipeline.commands.unified_pipeline_cli.get_project_root",
                return_value=str(tmp_path),
            ),
            patch(
                "cdk_factory.pipeline.commands.docker_build_cli.main",
                MagicMock(side_effect=failing_docker_build),
            ),
            patch(
                "cdk_factory.pipeline.commands.parameter_store_cli.main",
                MagicMock(side_effect=lambda *args, **kwargs: None),
            ),
            patch(
                "cdk_factory.pipeline.commands.lambda_image_updater.main",
                MagicMock(side_effect=lambda *args, **kwargs: None),
            ),
            patch(
                "cdk_factory.pipeline.publishing.codeartifact_publish.main",
                mock_codeartifact,
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main(
                    [
                        "--deploy-images",
                        "--publish-code-artifact",
                        "--project-root",
                        str(tmp_path),
                    ]
                )

            assert exc_info.value.code == 1

        # deploy-images was called but publish-code-artifact was not
        assert "deploy-images" in call_order
        assert "publish-code-artifact" not in call_order
        mock_codeartifact.assert_not_called()
