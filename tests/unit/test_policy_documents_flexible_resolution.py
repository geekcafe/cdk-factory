"""
Unit tests for PolicyDocuments flexible resource resolution
Tests the new ResourceResolver pattern for loading resources from environment variables or enhanced SSM parameters
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from aws_cdk import App, Stack
from aws_cdk import aws_iam as iam

from cdk_factory.constructs.lambdas.policies.policy_docs import (
    PolicyDocuments,
    ResourceResolver,
)
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestPolicyDocumentsFlexibleResolution(unittest.TestCase):

    def setUp(self):
        """Set up test environment"""
        self.app = App()
        self.stack = Stack(self.app, "TestStack")

        # Create test workload config
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
                "region": "us-east-1",
                "account": "123456789012",
            }
        )

        # Create test deployment config
        self.deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={
                "name": "test-deployment",
                "environment": "dev",
                "account": "123456789012",
                "region": "us-east-1",
            },
        )

        # Create test lambda config
        self.lambda_config = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": ["dynamodb_read", "dynamodb_write", "dynamodb_delete"],
            }
        )

        # Create test IAM role
        self.role = iam.Role(
            self.stack,
            "TestRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        # Clean up environment variables
        for var in self._all_env_vars():
            if var in os.environ:
                del os.environ[var]

    @staticmethod
    def _all_env_vars():
        """All env vars that the permissions_map eagerly evaluates."""
        return [
            "APP_TABLE_NAME",
            "DYNAMODB_TABLE_NAME",
            "DYNAMODB_APP_TABLE_NAME",
            "DYNAMODB_AUDIT_TABLE_NAME",
            "DYNAMODB_TRANSIENT_TABLE_NAME",
            "S3_WORKLOAD_BUCKET_NAME",
            "ANALYSIS_BUCKET",
            "S3_TRANSIENT_DATA_BUCKET_NAME",
            "S3_UPLOAD_BUCKET_NAME",
            "AWS_REGION",
            "AWS_ACCOUNT",
        ]

    def tearDown(self):
        """Clean up environment variables"""
        for var in self._all_env_vars():
            if var in os.environ:
                del os.environ[var]

    def test_resource_resolver_environment_variable_fallback(self):
        """Test that ResourceResolver falls back to environment variables when deployment config is not available"""

        # Create a deployment config without account/region to test fallback
        dummy_workload = WorkloadConfig(
            {"workload": {"name": "test-workload", "devops": {"name": "test-devops"}}}
        )

        deployment_without_account = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "dev"},
        )

        # Set environment variables
        os.environ["APP_TABLE_NAME"] = "test-table-env"
        os.environ["AWS_REGION"] = "us-west-2"
        os.environ["AWS_ACCOUNT"] = "987654321098"

        resolver = ResourceResolver(
            scope=self.stack,
            deployment=deployment_without_account,
            lambda_config=self.lambda_config,
        )

        # Test table name resolution (should use env var)
        table_name = resolver.get_table_name()
        self.assertEqual(table_name, "test-table-env")

        # Test region resolution (should use deployment default)
        aws_region = resolver.get_aws_region()
        self.assertEqual(aws_region, "us-east-1")  # Default from deployment config

        # Test account resolution (should use env var since not in deployment)
        aws_account = resolver.get_aws_account()
        self.assertEqual(aws_account, "987654321098")

    def test_resource_resolver_deployment_config_priority(self):
        """Test that ResourceResolver uses deployment config over environment variables"""

        # Set environment variables
        os.environ["AWS_REGION"] = "us-west-2"
        os.environ["AWS_ACCOUNT"] = "987654321098"

        resolver = ResourceResolver(
            scope=self.stack,
            deployment=self.deployment,
            lambda_config=self.lambda_config,
        )

        # Deployment config should take priority
        aws_region = resolver.get_aws_region()
        self.assertEqual(aws_region, "us-east-1")  # From deployment config

        aws_account = resolver.get_aws_account()
        self.assertEqual(aws_account, "123456789012")  # From deployment config

    def test_resource_resolver_no_table_name_returns_none(self):
        """Test that ResourceResolver returns None when no table name is available"""

        resolver = ResourceResolver(
            scope=self.stack,
            deployment=self.deployment,
            lambda_config=self.lambda_config,
        )

        table_name = resolver.get_table_name()
        self.assertIsNone(table_name)

    def test_policy_documents_dynamodb_read_with_environment_variables(self):
        """Test DynamoDB read permissions generation with structured format"""

        policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

        # Test DynamoDB read permissions via structured format
        permissions = policy_docs.get_permission_details(
            {"dynamodb": "read", "table": "test-table-env"}
        )

        self.assertEqual(permissions["name"], "DynamoDB")
        self.assertIn("DynamoDB Read", permissions["description"])

        # SID is now generated with a table slug suffix
        self.assertIn("DynamoDbRead", permissions["sid"])

        # Check actions
        expected_actions = [
            "dynamodb:GetItem",
            "dynamodb:Scan",
            "dynamodb:Query",
            "dynamodb:BatchGetItem",
        ]
        self.assertEqual(permissions["actions"], expected_actions)

        # Check resources contain table ARN
        resources = permissions["resources"]
        self.assertTrue(any("test-table-env" in resource for resource in resources))
        self.assertTrue(any("us-east-1" in resource for resource in resources))
        self.assertTrue(any("123456789012" in resource for resource in resources))

    def test_policy_documents_dynamodb_write_with_environment_variables(self):
        """Test DynamoDB write permissions generation with structured format"""

        policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

        # Test DynamoDB write permissions via structured format
        permissions = policy_docs.get_permission_details(
            {"dynamodb": "write", "table": "test-table-write"}
        )

        self.assertEqual(permissions["name"], "DynamoDB")
        self.assertIn("DynamoDB Write", permissions["description"])

        # SID is now generated with a table slug suffix
        self.assertIn("DynamoDbWrite", permissions["sid"])

        # Check actions
        expected_actions = [
            "dynamodb:BatchWriteItem",
            "dynamodb:PutItem",
            "dynamodb:UpdateItem",
        ]
        self.assertEqual(permissions["actions"], expected_actions)

        # Check resources contain table ARN
        resources = permissions["resources"]
        self.assertTrue(any("test-table-write" in resource for resource in resources))

    def test_policy_documents_dynamodb_delete_with_environment_variables(self):
        """Test DynamoDB delete permissions generation with structured format"""

        policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

        # Test DynamoDB delete permissions via structured format
        permissions = policy_docs.get_permission_details(
            {"dynamodb": "delete", "table": "test-table-delete"}
        )

        self.assertEqual(permissions["name"], "DynamoDB")
        self.assertIn("DynamoDB Delete", permissions["description"])

        # SID is now generated with a table slug suffix
        self.assertIn("DynamoDbDelete", permissions["sid"])

        # Check actions
        expected_actions = ["dynamodb:DeleteItem"]
        self.assertEqual(permissions["actions"], expected_actions)

        # Check resources contain table ARN
        resources = permissions["resources"]
        self.assertTrue(any("test-table-delete" in resource for resource in resources))

    def test_policy_documents_no_table_name_raises_error(self):
        """Test that empty table name in structured format raises helpful error message"""

        policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

        # Test that structured format with empty table raises ValueError
        with self.assertRaises(ValueError) as context:
            policy_docs.get_permission_details({"dynamodb": "read", "table": ""})

        error_message = str(context.exception)
        self.assertIn("requires 'table' field", error_message)

    @patch(
        "cdk_factory.constructs.lambdas.policies.policy_docs.ResourceResolver._get_ssm_mixin"
    )
    def test_resource_resolver_enhanced_ssm_integration(self, mock_get_ssm_mixin):
        """Test ResourceResolver with enhanced SSM parameter integration"""

        # Mock SSM mixin
        mock_ssm_mixin = MagicMock()
        mock_ssm_mixin.auto_import_resources.return_value = {
            "table_name": "test-table-ssm"
        }
        mock_get_ssm_mixin.return_value = mock_ssm_mixin

        # Create lambda config with SSM enabled
        lambda_config_with_ssm = LambdaFunctionConfig(
            {
                "name": "test-lambda",
                "permissions": ["dynamodb_read"],
                "ssm": {
                    "enabled": True,
                    "organization": "test-org",
                    "environment": "dev",
                    "imports": {"table_name": "auto"},
                },
            }
        )

        resolver = ResourceResolver(
            scope=self.stack,
            deployment=self.deployment,
            lambda_config=lambda_config_with_ssm,
        )

        # Test table name resolution via SSM
        table_name = resolver.get_table_name()
        self.assertEqual(table_name, "test-table-ssm")

        # Verify SSM mixin was called
        mock_ssm_mixin.auto_import_resources.assert_called_once()

    def test_policy_documents_full_integration_with_permissions(self):
        """Test full integration of PolicyDocuments with permission generation"""

        policy_docs = PolicyDocuments(
            scope=self.stack,
            role=self.role,
            lambda_config=self.lambda_config,
            deployment=self.deployment,
        )

        # Test getting permission details for DynamoDB permissions using structured format
        read_details = policy_docs.get_permission_details(
            {"dynamodb": "read", "table": "integration-test-table"}
        )
        write_details = policy_docs.get_permission_details(
            {"dynamodb": "write", "table": "integration-test-table"}
        )
        delete_details = policy_docs.get_permission_details(
            {"dynamodb": "delete", "table": "integration-test-table"}
        )

        # Verify all permissions were generated successfully
        self.assertIsNotNone(read_details)
        self.assertIsNotNone(write_details)
        self.assertIsNotNone(delete_details)

        # Verify they all reference the same table
        for details in [read_details, write_details, delete_details]:
            resources = details["resources"]
            self.assertTrue(
                any("integration-test-table" in resource for resource in resources)
            )


if __name__ == "__main__":
    unittest.main()
