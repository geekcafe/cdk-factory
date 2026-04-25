"""
Bug Condition Exploration Tests — DynamoDB Stream ARN Export Fails When Streams Disabled

These tests demonstrate that:
1. DynamoDBConfig has no `stream_specification` or `streams_enabled` properties
2. The auto-export system unconditionally exports `table_stream_arn` even when
   DynamoDB Streams are not enabled on the table

The tests are EXPECTED TO FAIL on unfixed code — failure confirms the bug exists.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2
"""

import os
import pytest
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_deployment():
    """Create a minimal mock deployment for DynamoDBConfig."""
    deployment = MagicMock()
    deployment.environment = "dev"
    return deployment


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid DynamoDB table names: 3-255 chars, alphanumeric + underscore/hyphen/dot
table_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_\-\.]{2,29}", fullmatch=True)


# ---------------------------------------------------------------------------
# Test 1a: stream_specification property missing
# ---------------------------------------------------------------------------


class TestBugConditionStreamSpecification:
    """
    **Validates: Requirements 1.3, 2.3**

    Test 1a: DynamoDBConfig should have a `stream_specification` property
    that returns None when not set. On unfixed code, this will fail with
    AttributeError because the property doesn't exist.
    """

    def test_stream_specification_is_none_when_not_set(self):
        """stream_specification should return None for config without streams."""
        deployment = _make_deployment()
        config = DynamoDBConfig({"name": "test-table"}, deployment)
        assert config.stream_specification is None


# ---------------------------------------------------------------------------
# Test 1b: streams_enabled property missing
# ---------------------------------------------------------------------------


class TestBugConditionStreamsEnabled:
    """
    **Validates: Requirements 1.3, 2.2**

    Test 1b: DynamoDBConfig should have a `streams_enabled` property
    that returns False when stream_specification is not set. On unfixed code,
    this will fail with AttributeError because the property doesn't exist.
    """

    def test_streams_enabled_is_false_when_not_set(self):
        """streams_enabled should return False for config without streams."""
        deployment = _make_deployment()
        config = DynamoDBConfig({"name": "test-table"}, deployment)
        assert config.streams_enabled is False


# ---------------------------------------------------------------------------
# Test 1c: table_stream_arn unconditionally exported
# ---------------------------------------------------------------------------


class TestBugConditionStreamArnExport:
    """
    **Validates: Requirements 1.1, 1.2, 2.1**

    Test 1c: When building a DynamoDBStack with ssm.auto_export: true and
    no stream_specification, table_stream_arn should NOT be in the exported
    SSM parameters. On unfixed code, table_stream_arn WILL be exported
    (bug condition), so this assertion fails.
    """

    @pytest.fixture(autouse=True)
    def set_environment(self):
        """Set ENVIRONMENT variable for tests."""
        os.environ["ENVIRONMENT"] = "dev"
        yield
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

    def test_stream_arn_not_exported_when_streams_disabled(self):
        """table_stream_arn should not be in SSM exports when streams are not enabled."""
        from aws_cdk import App
        from aws_cdk import aws_ssm as ssm
        from cdk_factory.stack_library.dynamodb.dynamodb_stack import DynamoDBStack
        from cdk_factory.configurations.stack import StackConfig
        from cdk_factory.configurations.deployment import DeploymentConfig
        from cdk_factory.workload.workload_factory import WorkloadConfig

        app = App()
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "dummy-workload",
                    "environment": "dev",
                    "devops": {"name": "dummy-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "name": "db-stack",
                "dynamodb": {
                    "name": "TestTable",
                },
                "ssm": {
                    "auto_export": True,
                    "namespace": "test/dev/dynamodb/app",
                },
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "dummy-deployment", "environment": "dev"},
        )

        stack = DynamoDBStack(app, "BugTestDynamoDBStack")
        stack.build(stack_config, deployment, dummy_workload)

        # Collect SSM StringParameter construct IDs — CDK token values
        # aren't plain strings, so we check the construct node IDs instead
        ssm_param_ids = [
            c.node.id for c in stack.node.children if isinstance(c, ssm.StringParameter)
        ]

        # Check that no SSM parameter construct ID contains "table_stream_arn"
        stream_arn_params = [pid for pid in ssm_param_ids if "table_stream_arn" in pid]

        assert len(stream_arn_params) == 0, (
            f"Bug confirmed: table_stream_arn is being exported to SSM even though "
            f"streams are not enabled. Found SSM params with stream_arn: {stream_arn_params}"
        )


# ---------------------------------------------------------------------------
# Test 1d: Property-based test
# ---------------------------------------------------------------------------


class TestBugConditionPropertyBased:
    """
    **Validates: Requirements 1.3, 2.2, 2.3**

    Test 1d (property-based): For any config without stream_specification,
    streams_enabled should be False and stream_specification should be None.
    On unfixed code, this will fail with AttributeError.
    """

    @given(name=table_name_st)
    @settings(max_examples=50)
    def test_no_stream_spec_means_streams_disabled(self, name):
        """For any table name, config without stream_specification has streams disabled."""
        deployment = _make_deployment()
        config = DynamoDBConfig({"name": name}, deployment)

        assert config.stream_specification is None, (
            f"Expected stream_specification to be None for table '{name}', "
            f"got {config.stream_specification}"
        )
        assert config.streams_enabled is False, (
            f"Expected streams_enabled to be False for table '{name}', "
            f"got {config.streams_enabled}"
        )
