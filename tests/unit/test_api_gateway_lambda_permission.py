"""
Unit test to verify Lambda permissions are granted for imported Lambda functions.
This test ensures that the fix for "Invalid permissions on Lambda function" error works.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template, Match

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewayLambdaPermission:
    """Test Lambda invoke permissions for imported Lambda functions."""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing."""
        return App()

    @pytest.fixture
    def deployment_config(self):
        """Create deployment configuration."""
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }
        deployment_dict = {
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
            "workload_name": "test-workload",
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        """Create workload configuration."""
        config_dict = {
            "name": "test-workload",
            "description": "Test workload",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return WorkloadConfig(config=config_dict)

    def test_lambda_permission_created_for_imported_lambda(
        self, app, deployment_config, workload_config, monkeypatch
    ):
        """
        Test that Lambda::Permission is created when importing Lambda from SSM.
        This prevents "Invalid permissions on Lambda function" errors.
        """
        monkeypatch.setenv("CDK_DEFAULT_ACCOUNT", "123456789012")
        monkeypatch.setenv("CDK_DEFAULT_REGION", "us-east-1")

        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }

        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway with Lambda permission",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "organization": "test-workload",
                    "environment": "test",
                    "imports": {
                        "organization": "test-workload",
                        "environment": "test",
                    },
                },
                "routes": [
                    {
                        "path": "/api/users",
                        "method": "GET",
                        "lambda_name": "user-service",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    }
                ],
            },
        }

        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create API Gateway stack
        stack = ApiGatewayStack(
            scope=app,
            id="test-api-gateway-permissions",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize and verify Lambda permission is created
        template = Template.from_stack(stack)

        # CRITICAL: Verify Lambda::Permission resource exists
        # This is what grants API Gateway permission to invoke the Lambda
        template.has_resource_properties(
            "AWS::Lambda::Permission",
            {
                "Action": "lambda:InvokeFunction",
                "Principal": "apigateway.amazonaws.com",
                # The source ARN should reference the specific API Gateway and route
                "SourceArn": Match.string_like_regexp(
                    r"arn:aws:execute-api:.*:.*:.*/\*/GET/api/users"
                ),
            },
        )

        # Also verify the API Gateway method was created
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "GET",
            },
        )

    def test_lambda_permission_created_for_explicit_ssm_path(
        self, app, deployment_config, workload_config
    ):
        """
        Test that Lambda::Permission is created when using explicit SSM path.
        """
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }

        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway with explicit SSM path",
                "api_type": "REST",
                "stage_name": "prod",
                "routes": [
                    {
                        "path": "/api/orders",
                        "method": "POST",
                        "lambda_arn_ssm_path": "/my-app/prod/lambda/order-service/arn",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    }
                ],
            },
        }

        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create API Gateway stack
        stack = ApiGatewayStack(
            scope=app,
            id="test-api-gateway-explicit-permissions",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize and verify Lambda permission is created
        template = Template.from_stack(stack)

        # CRITICAL: Verify Lambda::Permission resource exists
        template.has_resource_properties(
            "AWS::Lambda::Permission",
            {
                "Action": "lambda:InvokeFunction",
                "Principal": "apigateway.amazonaws.com",
                # The source ARN should reference the specific API Gateway and route
                "SourceArn": Match.string_like_regexp(
                    r"arn:aws:execute-api:.*:.*:.*/\*/POST/api/orders"
                ),
            },
        )

    def test_multiple_routes_create_multiple_permissions(
        self, app, deployment_config, workload_config
    ):
        """
        Test that multiple routes create separate Lambda permissions.
        """
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }

        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway with multiple routes",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "imports": {
                        "organization": "test-workload",
                        "environment": "test",
                    },
                },
                "routes": [
                    {
                        "path": "/api/users",
                        "method": "GET",
                        "lambda_name": "user-service",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    },
                    {
                        "path": "/api/products",
                        "method": "GET",
                        "lambda_name": "product-service",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    },
                ],
            },
        }

        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create API Gateway stack
        stack = ApiGatewayStack(
            scope=app,
            id="test-api-gateway-multiple-permissions",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize and verify multiple Lambda permissions are created
        template = Template.from_stack(stack)

        # Count Lambda::Permission resources
        template_json = template.to_json()
        permission_count = sum(
            1
            for resource in template_json.get("Resources", {}).values()
            if resource.get("Type") == "AWS::Lambda::Permission"
        )

        # Should have at least 2 permissions (one per route)
        assert (
            permission_count >= 2
        ), f"Expected at least 2 Lambda permissions, found {permission_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
