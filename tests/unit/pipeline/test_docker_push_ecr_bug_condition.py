"""
Bug Condition Exploration Tests — Docker Push ECR Field Ignored

These tests demonstrate that the current `_do_push` function in `docker_build_cli.py`
ignores the top-level `ecr` field on image configs when no `lambda_deployments` are
present. The function returns early with a warning instead of pushing to the ECR URI
derived from the `ecr` field.

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

**Validates: Requirements 1.1, 2.1**
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.pipeline.commands.docker_build_cli import _do_push
from cdk_factory.utilities.docker_utilities import DockerUtilities


# ---------------------------------------------------------------------------
# Bug Condition Tests
# ---------------------------------------------------------------------------


class TestDockerPushEcrBugCondition:
    """
    **Validates: Requirements 1.1, 2.1**

    Property 1: Bug Condition — ECR Field Push Ignored

    For any image config where an `ecr` field is present with valid `account` and
    `region` values and no `lambda_deployments`, the `_do_push` function SHALL
    call `execute_push_to_aws` with the ECR URI derived from `ecr.account` and
    `ecr.region`. On unfixed code, this test FAILS because `_do_push` returns
    early with a warning when `lambda_deployments` is empty.
    """

    def test_ecr_field_push_ignored_no_lambda_deployments(self):
        """Bug condition: ecr field present, no lambda_deployments.

        When image config has `ecr: {account: "072708757319", region: "us-east-1"}`
        and no `lambda_deployments`, `_do_push` should call `execute_push_to_aws`
        with the correct ECR URI. On unfixed code, the mock is never called because
        `_do_push` returns early with a warning.

        **Validates: Requirements 1.1, 2.1**
        """
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": {
                "account": "072708757319",
                "region": "us-east-1",
            },
            # No lambda_deployments — this triggers the bug
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version="1.0.0",
            package_name="my-package",
            tags=["latest"],
            tag_version=True,
            environment=None,
        )

        # Assert execute_push_to_aws was called with the ECR URI from the ecr field
        expected_ecr_base = "072708757319.dkr.ecr.us-east-1.amazonaws.com"
        expected_ecr_uri = f"{expected_ecr_base}/my-repo"

        docker.execute_push_to_aws.assert_called_once()
        call_kwargs = docker.execute_push_to_aws.call_args
        # Check region
        assert (
            call_kwargs.kwargs.get("aws_region")
            or call_kwargs[1].get("aws_region") == "us-east-1"
            or call_kwargs[0][0] == "us-east-1"
        ), f"Expected aws_region='us-east-1', got call: {call_kwargs}"
        # Check ECR URI contains the account
        args, kwargs = call_kwargs
        ecr_uri_arg = kwargs.get("aws_ecr_uri") or (args[1] if len(args) > 1 else None)
        assert (
            ecr_uri_arg is not None
        ), "execute_push_to_aws was not called with aws_ecr_uri"
        assert (
            "072708757319" in ecr_uri_arg
        ), f"Expected ECR URI to contain account '072708757319', got: {ecr_uri_arg}"

    def test_ecr_field_push_ignored_empty_lambda_deployments(self):
        """Bug condition: ecr field present, lambda_deployments is empty list.

        Same as above but with an explicit empty `lambda_deployments: []`.
        On unfixed code, `_do_push` sees empty deployments and returns early.

        **Validates: Requirements 1.1, 2.1**
        """
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": {
                "account": "072708757319",
                "region": "us-east-1",
            },
            "lambda_deployments": [],  # Empty — triggers the bug
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version="1.0.0",
            package_name="my-package",
            tags=["latest"],
            tag_version=False,
            environment=None,
        )

        # Assert execute_push_to_aws was called
        docker.execute_push_to_aws.assert_called_once()

    @given(
        account=st.just("072708757319"),
        region=st.just("us-east-1"),
        repo_name=st.just("my-repo"),
        version=st.just("1.0.0"),
        tag=st.just("latest"),
    )
    @settings(max_examples=5)
    def test_property_ecr_field_push_called(
        self, account, region, repo_name, version, tag
    ):
        """Property-based: For the concrete bug condition case, execute_push_to_aws
        must be called with ECR URI derived from ecr.account and ecr.region.

        Scoped to the concrete failing case: image config with
        ecr: {account: "072708757319", region: "us-east-1"} and no lambda_deployments.

        On unfixed code, this FAILS because _do_push returns early with a warning.

        **Validates: Requirements 1.1, 2.1**
        """
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = f"{repo_name}:{version}"

        image_config = {
            "repo_name": repo_name,
            "ecr": {
                "account": account,
                "region": region,
            },
            # No lambda_deployments
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version=version,
            package_name="my-package",
            tags=[tag],
            tag_version=True,
            environment=None,
        )

        # The expected ECR base URI
        expected_ecr_base = f"{account}.dkr.ecr.{region}.amazonaws.com"
        expected_ecr_repo_uri = f"{expected_ecr_base}/{repo_name}"

        # Assert push was called
        docker.execute_push_to_aws.assert_called_once()

        # Verify the ECR URI passed contains the account and region
        args, kwargs = docker.execute_push_to_aws.call_args
        ecr_uri_arg = kwargs.get("aws_ecr_uri") or (args[1] if len(args) > 1 else None)
        assert (
            ecr_uri_arg == expected_ecr_base
        ), f"Expected aws_ecr_uri='{expected_ecr_base}', got: {ecr_uri_arg}"

        # Verify tags contain the fully qualified ECR URI with tag
        tags_arg = kwargs.get("tags") or (args[2] if len(args) > 2 else None)
        assert tags_arg is not None, "execute_push_to_aws was not called with tags"
        for t in tags_arg:
            assert (
                expected_ecr_repo_uri in t
            ), f"Expected tag to contain '{expected_ecr_repo_uri}', got: {t}"


# ---------------------------------------------------------------------------
# Multi-Region ECR Tests
# ---------------------------------------------------------------------------


class TestDockerPushEcrMultiRegion:
    """Tests for multi-region ECR push support (ecr as array)."""

    def test_ecr_array_pushes_to_all_regions(self):
        """When ecr is an array, _do_push pushes to each target."""
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": [
                {"account": "072708757319", "region": "us-east-1"},
                {"account": "072708757319", "region": "us-west-2"},
                {"account": "072708757319", "region": "eu-west-1"},
            ],
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version="1.0.0",
            package_name="my-package",
            tags=["latest"],
            tag_version=True,
            environment=None,
        )

        # Should be called once per region
        assert docker.execute_push_to_aws.call_count == 3

        # Verify each call targets the correct region
        calls = docker.execute_push_to_aws.call_args_list
        regions_pushed = [c.kwargs.get("aws_region") for c in calls]
        assert "us-east-1" in regions_pushed
        assert "us-west-2" in regions_pushed
        assert "eu-west-1" in regions_pushed

    def test_ecr_array_different_accounts(self):
        """When ecr array has different accounts, each gets its own push."""
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": [
                {"account": "072708757319", "region": "us-east-1"},
                {"account": "111222333444", "region": "eu-west-1"},
            ],
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version="1.0.0",
            package_name="my-package",
            tags=[],
            tag_version=True,
            environment=None,
        )

        assert docker.execute_push_to_aws.call_count == 2

        calls = docker.execute_push_to_aws.call_args_list
        ecr_uris = [c.kwargs.get("aws_ecr_uri") for c in calls]
        assert "072708757319.dkr.ecr.us-east-1.amazonaws.com" in ecr_uris
        assert "111222333444.dkr.ecr.eu-west-1.amazonaws.com" in ecr_uris

    def test_ecr_single_object_still_works(self):
        """Single object shape continues to work (backward compat)."""
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": {"account": "072708757319", "region": "us-east-1"},
        }

        _do_push(
            docker=docker,
            image_config=image_config,
            version="1.0.0",
            package_name="my-package",
            tags=["latest"],
            tag_version=False,
            environment=None,
        )

        docker.execute_push_to_aws.assert_called_once()
        call_kwargs = docker.execute_push_to_aws.call_args.kwargs
        assert call_kwargs["aws_region"] == "us-east-1"
        assert (
            call_kwargs["aws_ecr_uri"] == "072708757319.dkr.ecr.us-east-1.amazonaws.com"
        )

    def test_ecr_empty_array_raises_error(self):
        """Empty ecr array raises RuntimeError."""
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": [],
        }

        with pytest.raises(RuntimeError, match="Empty 'ecr' array"):
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-package",
                tags=[],
                tag_version=True,
                environment=None,
            )

    def test_ecr_array_entry_missing_account_raises_error(self):
        """If any entry in the ecr array is missing account, raises RuntimeError."""
        docker = MagicMock(spec=DockerUtilities)
        docker.build_tag = "my-repo:1.0.0"

        image_config = {
            "repo_name": "my-repo",
            "ecr": [
                {"account": "072708757319", "region": "us-east-1"},
                {"region": "us-west-2"},  # Missing account
            ],
        }

        with pytest.raises(RuntimeError, match="ecr.account is required"):
            _do_push(
                docker=docker,
                image_config=image_config,
                version="1.0.0",
                package_name="my-package",
                tags=[],
                tag_version=True,
                environment=None,
            )
