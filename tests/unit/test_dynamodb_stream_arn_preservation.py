"""
Preservation Property Tests — DynamoDB Stream ARN Export Fix

These tests capture baseline behavior that MUST be preserved after the fix.
They should PASS on both unfixed and fixed code.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**
"""

import os
import pytest
from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from cdk_factory.configurations.resources.dynamodb import DynamoDBConfig
from cdk_factory.configurations.enhanced_ssm_config import RESOURCE_AUTO_EXPORTS


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

# Valid DynamoDB table names: 3-30 chars, starts with letter, alphanumeric + underscore/hyphen/dot
table_name_st = st.from_regex(r"[a-zA-Z][a-zA-Z0-9_\-\.]{2,29}", fullmatch=True)

gsi_count_st = st.integers(min_value=0, max_value=20)

ttl_attribute_st = st.one_of(
    st.none(),
    st.text(
        min_size=1, max_size=30, alphabet=st.characters(whitelist_categories=("L", "N"))
    ),
)

point_in_time_recovery_st = st.booleans()

enable_delete_protection_st = st.booleans()

replica_regions_st = st.lists(
    st.sampled_from(
        ["us-east-1", "us-west-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
    ),
    min_size=0,
    max_size=3,
    unique=True,
)


# ---------------------------------------------------------------------------
# Test 2a: Property-based — non-stream properties return expected values
# ---------------------------------------------------------------------------


class TestPreservationNonStreamProperties:
    """
    **Validates: Requirements 3.3, 3.4**

    Test 2a (property-based): Generate random DynamoDB configs and verify
    all non-stream properties return expected values. These should pass on
    both unfixed and fixed code.
    """

    @given(
        name=table_name_st,
        gsi_count=gsi_count_st,
        ttl_attribute=ttl_attribute_st,
        pitr=point_in_time_recovery_st,
        delete_protection=enable_delete_protection_st,
        replica_regions=replica_regions_st,
    )
    @settings(max_examples=50)
    def test_non_stream_properties_preserved(
        self, name, gsi_count, ttl_attribute, pitr, delete_protection, replica_regions
    ):
        """Non-stream config properties return the values they were given."""
        deployment = _make_deployment()
        config_dict = {"name": name, "gsi_count": gsi_count}

        if ttl_attribute is not None:
            config_dict["ttl_attribute"] = ttl_attribute

        config_dict["point_in_time_recovery"] = pitr
        config_dict["enable_delete_protection"] = delete_protection
        config_dict["replica_regions"] = replica_regions

        config = DynamoDBConfig(config_dict, deployment)

        assert config.name == name, f"Expected name '{name}', got '{config.name}'"
        assert (
            config.gsi_count == gsi_count
        ), f"Expected gsi_count {gsi_count}, got {config.gsi_count}"
        assert (
            config.ttl_attribute == ttl_attribute
        ), f"Expected ttl_attribute '{ttl_attribute}', got '{config.ttl_attribute}'"
        assert (
            config.point_in_time_recovery == pitr
        ), f"Expected point_in_time_recovery {pitr}, got {config.point_in_time_recovery}"
        assert (
            config.enable_delete_protection == delete_protection
        ), f"Expected enable_delete_protection {delete_protection}, got {config.enable_delete_protection}"
        assert (
            config.replica_regions == replica_regions
        ), f"Expected replica_regions {replica_regions}, got {config.replica_regions}"


# ---------------------------------------------------------------------------
# Test 2b: Non-DynamoDB RESOURCE_AUTO_EXPORTS unchanged
# ---------------------------------------------------------------------------


class TestPreservationAutoExports:
    """
    **Validates: Requirements 3.4**

    Test 2b: Verify RESOURCE_AUTO_EXPORTS for all non-DynamoDB resource types
    remain unchanged. Snapshot the expected values and assert equality.
    """

    def test_vpc_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["vpc"] == [
            "vpc_id",
            "vpc_cidr",
            "public_subnet_ids",
            "private_subnet_ids",
            "isolated_subnet_ids",
        ]

    def test_rds_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["rds"] == [
            "db_instance_id",
            "db_endpoint",
            "db_port",
            "db_secret_arn",
        ]

    def test_lambda_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["lambda"] == [
            "function_name",
            "function_arn",
        ]

    def test_s3_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["s3"] == [
            "bucket_name",
            "bucket_arn",
        ]

    def test_cognito_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["cognito"] == [
            "user_pool_id",
            "user_pool_arn",
            "user_pool_name",
            "user_pool_client_id",
            "authorizer_id",
        ]

    def test_api_gateway_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["api_gateway"] == [
            "api_id",
            "api_arn",
            "api_url",
            "root_resource_id",
            "authorizer_id",
        ]

    def test_api_gateway_hyphen_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["api-gateway"] == [
            "api_id",
            "api_arn",
            "api_url",
            "root_resource_id",
            "authorizer_id",
        ]

    def test_security_group_auto_exports_unchanged(self):
        assert RESOURCE_AUTO_EXPORTS["security_group"] == [
            "security_group_id",
        ]


# ---------------------------------------------------------------------------
# Test 2c: auto_export=false does not trigger SSM exports
# ---------------------------------------------------------------------------


class TestPreservationSsmDisabled:
    """
    **Validates: Requirements 3.2**

    Test 2c: Verify that configs with ssm.auto_export: false do not trigger
    SSM exports. Build a DynamoDBStack with auto_export disabled and verify
    no SSM StringParameter constructs are created.
    """

    @pytest.fixture(autouse=True)
    def set_environment(self):
        """Set ENVIRONMENT variable for tests."""
        os.environ["ENVIRONMENT"] = "dev"
        yield
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

    def test_no_ssm_exports_when_auto_export_disabled(self):
        """No SSM StringParameter constructs when auto_export is false."""
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
                "name": "db-stack-no-export",
                "dynamodb": {
                    "name": "TestTableNoExport",
                },
                "ssm": {
                    "auto_export": False,
                },
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "dummy-deployment", "environment": "dev"},
        )

        stack = DynamoDBStack(app, "PreservationTestDynamoDBStack")
        stack.build(stack_config, deployment, dummy_workload)

        # Collect SSM StringParameter constructs
        ssm_params = [
            c for c in stack.node.children if isinstance(c, ssm.StringParameter)
        ]

        assert len(ssm_params) == 0, (
            f"Expected no SSM parameters when auto_export is false, "
            f"but found {len(ssm_params)}: {[p.node.id for p in ssm_params]}"
        )
