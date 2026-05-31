"""
Preservation Property Tests — ECR Push Behavior

These tests verify the ECR push path works correctly for all valid configurations.
They cover tag resolution, single/multi-region, and error cases.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
from typing import List

import pytest
from hypothesis import given, settings
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
    ["dev", "staging", "integration", "qa", "uat", "prod"]
)

# CLI tag names: alphanumeric with dashes/dots
_tag_strategy = st.from_regex(r"[a-z][a-z0-9\.\-]{0,19}", fullmatch=True)

# Lists of CLI tags (0-3 tags)
_tags_list_strategy = st.lists(_tag_strategy, min_size=0, max_size=3)


# ---------------------------------------------------------------------------
# Property-Based Tests — ECR Push Path
# ---------------------------------------------------------------------------


class TestEcrPushProperty:
    """
    Property: For any valid ecr config, _do_push calls execute_push_to_aws
    with ECR URI derived from ecr account/region.

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=100)
    def test_ecr_config_pushes_to_correct_ecr_uri(
        self, account: str, region: str, repo_name: str, version: str, package_name: str
    ):
        """For a valid ecr config, _do_push calls execute_push_to_aws
        with the ECR URI derived from ecr account and region."""
        image_config = {
            "repo_name": repo_name,
            "ecr": {"account": account, "region": region},
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

        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        expected_ecr_base = f"{account}.dkr.ecr.{region}.amazonaws.com"
        expected_ecr_uri = f"{expected_ecr_base}/{repo_name}"

        assert call_kwargs["aws_region"] == region
        assert call_kwargs["aws_ecr_uri"] == expected_ecr_base

        # Verify tags contain the fully qualified ECR URI with repo name
        for tag in call_kwargs["tags"]:
            assert tag.startswith(expected_ecr_uri + ":")

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
        """When repo_name is not specified, it defaults to package_name."""
        image_config = {
            "ecr": {"account": account, "region": region},
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

        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        expected_ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{package_name}"
        for tag in call_kwargs["tags"]:
            assert tag.startswith(expected_ecr_uri + ":")


class TestTagResolutionProperty:
    """
    Property: Tag resolution produces correct output for all combinations.

    **Validates: Requirements 3.3, 3.4**
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
        """Tags passed to execute_push_to_aws match the expected tag resolution logic."""
        image_config = {
            "repo_name": repo_name,
            "ecr": {"account": account, "region": region},
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

        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        actual_tags = call_kwargs["tags"]

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

        assert actual_tags == expected_qualified

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=50)
    def test_tag_version_flag_includes_version_in_tags(
        self, account: str, region: str, repo_name: str, version: str, package_name: str
    ):
        """When --tag-version is set, the version string appears in the pushed tags."""
        image_config = {
            "repo_name": repo_name,
            "ecr": {"account": account, "region": region},
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

        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
        version_tag = f"{ecr_uri}:{version}"
        assert version_tag in call_kwargs["tags"]

    @given(
        account=_account_strategy,
        region=_region_strategy,
        repo_name=_repo_name_strategy,
        version=_version_strategy,
        package_name=_package_name_strategy,
    )
    @settings(max_examples=50)
    def test_no_tags_defaults_to_version(
        self, account: str, region: str, repo_name: str, version: str, package_name: str
    ):
        """When no CLI tags, no tag_version, and no environment, defaults to [version]."""
        image_config = {
            "repo_name": repo_name,
            "ecr": {"account": account, "region": region},
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

        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        ecr_uri = f"{account}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
        expected = [f"{ecr_uri}:{version}"]
        assert call_kwargs["tags"] == expected


# ---------------------------------------------------------------------------
# Error Case Tests
# ---------------------------------------------------------------------------


class TestPushErrorCases:
    """Tests for error conditions in _do_push."""

    def test_no_ecr_field_raises_error(self):
        """When no ecr field is present, raises RuntimeError."""
        image_config = {
            "repo_name": "my-service",
        }

        docker = MagicMock()

        with pytest.raises(RuntimeError, match="No 'ecr' field found"):
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-service",
                tags=[],
                tag_version=True,
                environment=None,
            )

    def test_lambda_deployments_without_ecr_raises_error(self):
        """lambda_deployments alone is no longer sufficient for push — ecr is required."""
        image_config = {
            "repo_name": "my-service",
            "lambda_deployments": [
                {"account": "013453151395", "region": "us-east-1", "enabled": True}
            ],
        }

        docker = MagicMock()

        with pytest.raises(RuntimeError, match="No 'ecr' field found"):
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-service",
                tags=[],
                tag_version=True,
                environment=None,
            )

    def test_ecr_with_tag_resolution_and_environment(self):
        """Verify tag resolution produces version + environment + latest tags."""
        image_config = {
            "repo_name": "my-service",
            "ecr": {"account": "013453151395", "region": "us-east-1"},
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
        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        actual_tags = call_kwargs["tags"]

        ecr_uri = "013453151395.dkr.ecr.us-east-1.amazonaws.com/my-service"
        assert f"{ecr_uri}:custom-tag" in actual_tags
        assert f"{ecr_uri}:1.2.3" in actual_tags
        assert f"{ecr_uri}:dev" in actual_tags
        assert f"{ecr_uri}:latest" in actual_tags
