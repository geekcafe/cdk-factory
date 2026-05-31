"""
Preservation Property Tests — Lambda Deployments Fallback Behavior

These tests capture baseline behavior that MUST be preserved after the fix.
They run on UNFIXED code first (observation-first methodology) and should
PASS both before and after the fix is applied.

**Property 2: Preservation** - Lambda Deployments Fallback Behavior

For any image config where no `ecr` field is present but valid `lambda_deployments`
entries exist, the `_do_push` function SHALL produce exactly the same behavior as
the original function, deriving ECR URI from deployment entries and pushing the
image identically.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch, call
from typing import List

from hypothesis import given, settings, assume
from hypothesis import strategies as st

from cdk_factory.pipeline.commands.docker_build_cli import _do_push
from cdk_factory.pipeline.conventions.docker_tags import resolve_docker_tags


# ---------------------------------------------------------------------------
# Strategies for generating test inputs
# ---------------------------------------------------------------------------

# AWS account IDs: 12-digit numeric strings
_account_strategy = st.from_regex(r"[0-9]{12}", fullmatch=True)

# AWS regions
_region_strategy = st.sampled_from(
    [
        "us-east-1",
        "us-east-2",
        "us-west-1",
        "us-west-2",
        "eu-west-1",
        "eu-central-1",
        "ap-southeast-1",
        "ap-northeast-1",
    ]
)

# Repo names: lowercase alphanumeric with dashes/slashes, 1-50 chars
_repo_name_strategy = st.from_regex(r"[a-z][a-z0-9\-/]{0,49}", fullmatch=True)

# Package names: lowercase alphanumeric with dashes/underscores
_package_name_strategy = st.from_regex(r"[a-z][a-z0-9_\-]{0,29}", fullmatch=True)

# Version strings: semver-like
_version_strategy = st.from_regex(r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,5}", fullmatch=True)

# Environment names
_environment_strategy = st.sampled_from(
    [
        "dev",
        "staging",
        "integration",
        "qa",
        "uat",
        "prod",
    ]
)

# CLI tag names: alphanumeric with dashes/dots
_tag_strategy = st.from_regex(r"[a-z][a-z0-9\.\-]{0,19}", fullmatch=True)

# Lists of CLI tags (0-3 tags)
_tags_list_strategy = st.lists(_tag_strategy, min_size=0, max_size=3)


# ---------------------------------------------------------------------------
# Property-Based Tests — Lambda Deployments Fallback
# ---------------------------------------------------------------------------


class TestLambdaDeploymentsFallbackProperty:
    """
    **Validates: Requirements 3.1, 3.2**

    Property 2: Preservation — Lambda Deployments Fallback

    For any valid lambda_deployments config (no ecr field), _do_push calls
    execute_push_to_aws with ECR URI derived from deployment account/region.
    """

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=100)
    def test_single_enabled_deployment_pushes_to_correct_ecr_uri(
        self, account: str, region: str, repo_name: str, version: str, package_name: str
    ):
        """For a single enabled deployment, _do_push calls execute_push_to_aws
        with the ECR URI derived from deployment account and region.

        **Validates: Requirements 3.1**
        """
        image_config = {
            "repo_name": repo_name,
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=[],
                tag_version=True,
                environment=None,
            )

        # Should have been called exactly once
        assert docker.execute_push_to_aws.call_count == 1

        call_kwargs = docker.execute_push_to_aws.call_args
        expected_ecr_base = f"{account}.dkr.ecr.{region}.amazonaws.com"
        expected_ecr_uri = f"{expected_ecr_base}/{repo_name}"

        # Verify the aws_region matches
        assert (
            call_kwargs.kwargs["aws_region"] == region
            or call_kwargs[1].get("aws_region") == region
            if call_kwargs.kwargs
            else call_kwargs[1]["aws_region"] == region
        )

        # Verify the ECR URI base is correct
        actual_ecr_uri = call_kwargs.kwargs.get("aws_ecr_uri") or call_kwargs[1].get(
            "aws_ecr_uri"
        )
        assert actual_ecr_uri == expected_ecr_base

        # Verify tags contain the fully qualified ECR URI with repo name
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")
        for tag in actual_tags:
            assert tag.startswith(expected_ecr_uri + ":")

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=100)
    def test_disabled_deployment_skips_push(
        self, account: str, region: str, repo_name: str, version: str, package_name: str
    ):
        """For a disabled deployment, _do_push does NOT call execute_push_to_aws.

        **Validates: Requirements 3.1**
        """
        image_config = {
            "repo_name": repo_name,
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": False}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=[],
                tag_version=True,
                environment=None,
            )

        # Should NOT have been called
        assert docker.execute_push_to_aws.call_count == 0

    @given(
        account=_account_strategy,
        region=_region_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=50)
    def test_repo_name_defaults_to_package_name(
        self, account: str, region: str, version: str, package_name: str
    ):
        """When repo_name is not specified, it defaults to package_name.

        **Validates: Requirements 3.1**
        """
        image_config = {
            # No repo_name specified
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=[],
                tag_version=True,
                environment=None,
            )

        assert docker.execute_push_to_aws.call_count == 1

        call_kwargs = docker.execute_push_to_aws.call_args
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")
        expected_ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{package_name}"
        for tag in actual_tags:
            assert tag.startswith(expected_ecr_uri + ":")


class TestTagResolutionPreservationProperty:
    """
    **Validates: Requirements 3.3, 3.4**

    Property 2: Preservation — Tag Resolution

    For all tag combinations (version, environment, CLI tags), tag resolution
    produces the same output whether invoked through _do_push or directly.
    """

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
        environment=_environment_strategy,
        cli_tags=_tags_list_strategy,
        tag_version=st.booleans(),
    )
    @settings(max_examples=100)
    def test_tag_resolution_matches_expected_output(
        self,
        account: str,
        region: str,
        repo_name: str,
        version: str,
        package_name: str,
        environment: str,
        cli_tags: List[str],
        tag_version: bool,
    ):
        """Tags passed to execute_push_to_aws match the expected tag resolution logic.

        The expected tags are: CLI tags + version (if tag_version) + environment tags.
        If no tags at all, defaults to [version].

        **Validates: Requirements 3.3, 3.4**
        """
        image_config = {
            "repo_name": repo_name,
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {"ENVIRONMENT": environment}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=cli_tags,
                tag_version=tag_version,
                environment=environment,
            )

        assert docker.execute_push_to_aws.call_count == 1

        call_kwargs = docker.execute_push_to_aws.call_args
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")

        # Compute expected tags using the same logic as _do_push
        expected_all_tags: List[str] = list(cli_tags)
        if tag_version:
            expected_all_tags.append(version)
        env_tags = resolve_docker_tags(environment=environment, version=version)
        for t in env_tags:
            if t not in expected_all_tags:
                expected_all_tags.append(t)
        if not expected_all_tags:
            expected_all_tags = [version]

        ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
        expected_qualified = [f"{ecr_uri}:{t}" for t in expected_all_tags]

        assert actual_tags == expected_qualified, (
            f"Tag mismatch.\n"
            f"  Expected: {expected_qualified}\n"
            f"  Actual:   {actual_tags}"
        )

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=50)
    def test_tag_version_flag_includes_version_in_tags(
        self,
        account: str,
        region: str,
        repo_name: str,
        version: str,
        package_name: str,
    ):
        """When --tag-version is set, the version string appears in the pushed tags.

        **Validates: Requirements 3.4**
        """
        image_config = {
            "repo_name": repo_name,
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=[],
                tag_version=True,
                environment=None,
            )

        assert docker.execute_push_to_aws.call_count == 1

        call_kwargs = docker.execute_push_to_aws.call_args
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")

        ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
        version_tag = f"{ecr_uri}:{version}"
        assert (
            version_tag in actual_tags
        ), f"Version tag '{version_tag}' not found in actual tags: {actual_tags}"

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=50)
    def test_no_tags_defaults_to_version(
        self,
        account: str,
        region: str,
        repo_name: str,
        version: str,
        package_name: str,
    ):
        """When no CLI tags, no tag_version, and no environment, defaults to [version].

        **Validates: Requirements 3.3**
        """
        image_config = {
            "repo_name": repo_name,
            "lambda_deployments": [
                {"account": account, "region": region, "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version=version,
                package_name=package_name,
                tags=[],
                tag_version=False,
                environment=None,
            )

        assert docker.execute_push_to_aws.call_count == 1

        call_kwargs = docker.execute_push_to_aws.call_args
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")

        ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
        expected = [f"{ecr_uri}:{version}"]
        assert actual_tags == expected


# ---------------------------------------------------------------------------
# Observation Tests — Concrete Examples (Observation-First Methodology)
# ---------------------------------------------------------------------------


class TestPreservationObservations:
    """
    Concrete observation tests that verify specific behaviors on unfixed code.
    These serve as the observation step before writing property tests.

    **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
    """

    def test_observe_single_deployment_pushes_to_correct_uri(self):
        """Observe: _do_push with lambda_deployments calls execute_push_to_aws
        with URI derived from deployment account/region.

        **Validates: Requirements 3.1**
        """
        image_config = {
            "repo_name": "my-service",
            "lambda_deployments": [
                {"account": "013453151395", "region": "us-east-1", "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-service",
                tags=[],
                tag_version=True,
                environment=None,
            )

        docker.execute_push_to_aws.assert_called_once()
        call_kwargs = docker.execute_push_to_aws.call_args
        actual_ecr_uri = call_kwargs.kwargs.get("aws_ecr_uri") or call_kwargs[1].get(
            "aws_ecr_uri"
        )
        assert actual_ecr_uri == "013453151395.dkr.ecr.us-east-1.amazonaws.com"

    def test_observe_disabled_deployment_skips(self):
        """Observe: _do_push with disabled deployment skips that deployment.

        **Validates: Requirements 3.1**
        """
        image_config = {
            "repo_name": "my-service",
            "lambda_deployments": [
                {"account": "013453151395", "region": "us-east-1", "enabled": False}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-service",
                tags=[],
                tag_version=True,
                environment=None,
            )

        docker.execute_push_to_aws.assert_not_called()

    def test_observe_tag_resolution_with_environment(self):
        """Observe: tag resolution produces version + environment + latest tags
        correctly on unfixed code.

        **Validates: Requirements 3.3, 3.4**
        """
        image_config = {
            "repo_name": "my-service",
            "lambda_deployments": [
                {"account": "013453151395", "region": "us-east-1", "enabled": True}
            ],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.2.3",
                package_name="my-service",
                tags=["custom-tag"],
                tag_version=True,
                environment="dev",
            )

        docker.execute_push_to_aws.assert_called_once()
        call_kwargs = docker.execute_push_to_aws.call_args
        actual_tags = call_kwargs.kwargs.get("tags") or call_kwargs[1].get("tags")

        ecr_uri = "013453151395.dkr.ecr.us-east-1.amazonaws.com/my-service"
        # Expected: custom-tag, 1.2.3 (tag_version), then env tags: 1.2.3, dev, latest
        # After dedup: custom-tag, 1.2.3, dev, latest
        assert f"{ecr_uri}:custom-tag" in actual_tags
        assert f"{ecr_uri}:1.2.3" in actual_tags
        assert f"{ecr_uri}:dev" in actual_tags
        assert f"{ecr_uri}:latest" in actual_tags

    def test_observe_no_deployments_prints_warning(self):
        """Observe: _do_push with no lambda_deployments prints warning and skips.

        **Validates: Requirements 3.2**
        """
        import io
        import sys

        image_config = {
            "repo_name": "my-service",
            "lambda_deployments": [],
        }

        docker = MagicMock()
        docker.execute_push_to_aws = MagicMock()

        captured_stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AWS_PROFILE", None)
            old_stderr = sys.stderr
            sys.stderr = captured_stderr
            try:
                _do_push(
                    docker=docker,
                    image_config=image_config,
                    version="1.0.0",
                    package_name="my-service",
                    tags=[],
                    tag_version=True,
                    environment=None,
                )
            finally:
                sys.stderr = old_stderr

        docker.execute_push_to_aws.assert_not_called()
        warning_output = captured_stderr.getvalue()
        assert "Warning" in warning_output or "lambda_deployments" in warning_output
