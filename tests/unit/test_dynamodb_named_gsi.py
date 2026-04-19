"""
Unit tests for DynamoDB named GSI configuration.
"""

import pytest
from unittest.mock import MagicMock
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.dynamodb.dynamodb_stack import DynamoDBStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestDynamoDBNamedGSI:
    """Test DynamoDB named GSI configuration."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        return DeploymentConfig(
            workload={"name": "test-workload"},
            deployment={
                "name": "test",
                "account": "123456789012",
                "region": "us-east-1",
                "environment": "dev",
            },
        )

    @pytest.fixture
    def workload_config(self):
        return WorkloadConfig(
            config={
                "name": "test-workload",
                "devops": {"account": "123456789012", "region": "us-east-1"},
            }
        )

    def test_named_gsi_with_pk_and_sk(self, app, deployment_config, workload_config):
        """Verify named GSI with partition key and sort key."""
        stack_config = StackConfig(
            stack={
                "name": "test-dynamodb",
                "dynamodb": {
                    "name": "test-table",
                    "global_secondary_indexes": [
                        {
                            "index_name": "by-email",
                            "partition_key": {"name": "email", "type": "S"},
                            "sort_key": {"name": "created_at", "type": "S"},
                        }
                    ],
                },
            },
            workload={"name": "test-workload"},
        )
        stack = DynamoDBStack(
            app,
            "TestNamedGSI",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::GlobalTable",
            {
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "by-email",
                        "KeySchema": [
                            {"AttributeName": "email", "KeyType": "HASH"},
                            {"AttributeName": "created_at", "KeyType": "RANGE"},
                        ],
                    }
                ],
            },
        )

    def test_named_gsi_pk_only(self, app, deployment_config, workload_config):
        """Verify named GSI with partition key only (no sort key)."""
        stack_config = StackConfig(
            stack={
                "name": "test-dynamodb",
                "dynamodb": {
                    "name": "test-table-pk-only",
                    "global_secondary_indexes": [
                        {
                            "index_name": "by-tenant",
                            "partition_key": {"name": "tenant_id", "type": "S"},
                        }
                    ],
                },
            },
            workload={"name": "test-workload"},
        )
        stack = DynamoDBStack(
            app,
            "TestNamedGSIPKOnly",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::GlobalTable",
            {
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "by-tenant",
                        "KeySchema": [
                            {"AttributeName": "tenant_id", "KeyType": "HASH"},
                        ],
                    }
                ],
            },
        )

    def test_named_gsi_number_type(self, app, deployment_config, workload_config):
        """Verify named GSI with number attribute type."""
        stack_config = StackConfig(
            stack={
                "name": "test-dynamodb",
                "dynamodb": {
                    "name": "test-table-number",
                    "global_secondary_indexes": [
                        {
                            "index_name": "by-score",
                            "partition_key": {"name": "category", "type": "S"},
                            "sort_key": {"name": "score", "type": "N"},
                        }
                    ],
                },
            },
            workload={"name": "test-workload"},
        )
        stack = DynamoDBStack(
            app,
            "TestNamedGSINumber",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        # Verify the number attribute is defined
        template.has_resource_properties(
            "AWS::DynamoDB::GlobalTable",
            {
                "AttributeDefinitions": [
                    {"AttributeName": "pk", "AttributeType": "S"},
                    {"AttributeName": "sk", "AttributeType": "S"},
                    {"AttributeName": "category", "AttributeType": "S"},
                    {"AttributeName": "score", "AttributeType": "N"},
                ],
            },
        )

    def test_conflict_gsi_count_and_named(
        self, app, deployment_config, workload_config
    ):
        """Verify error when both gsi_count and global_secondary_indexes are set."""
        stack_config = StackConfig(
            stack={
                "name": "test-dynamodb",
                "dynamodb": {
                    "name": "test-table-conflict",
                    "gsi_count": 5,
                    "global_secondary_indexes": [
                        {
                            "index_name": "by-email",
                            "partition_key": {"name": "email", "type": "S"},
                        }
                    ],
                },
            },
            workload={"name": "test-workload"},
        )
        stack = DynamoDBStack(
            app,
            "TestConflict",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        with pytest.raises(ValueError, match="Use one or the other"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_auto_gsi_still_works(self, app, deployment_config, workload_config):
        """Verify gsi_count mode still works (backward compat)."""
        stack_config = StackConfig(
            stack={
                "name": "test-dynamodb",
                "dynamodb": {
                    "name": "test-table-auto",
                    "gsi_count": 2,
                },
            },
            workload={"name": "test-workload"},
        )
        stack = DynamoDBStack(
            app,
            "TestAutoGSI",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(stack_config, deployment_config, workload_config)
        template = Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::DynamoDB::GlobalTable",
            {
                "GlobalSecondaryIndexes": [
                    {"IndexName": "gsi0"},
                    {"IndexName": "gsi1"},
                ],
            },
        )
