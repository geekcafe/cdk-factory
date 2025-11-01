"""
Unit tests for API Gateway Stack SSM Lambda import functionality.
Tests the new pattern where API Gateway imports Lambda ARNs from SSM Parameter Store.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template
from aws_cdk import aws_ssm as ssm

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewaySSMLambdaImport:
    """Test cases for API Gateway Stack SSM Lambda import functionality."""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing."""
        return App()

    @pytest.fixture
    def deployment_config(self):
        """Create real deployment configuration."""
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for API Gateway SSM testing",
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
        """Create real workload configuration."""
        config_dict = {
            "name": "test-workload",
            "description": "Test workload for API Gateway SSM testing",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return WorkloadConfig(config=config_dict)

    def test_api_gateway_with_lambda_name_reference(
        self, app, deployment_config, workload_config, monkeypatch
    ):
        """Test API Gateway imports Lambda via lambda_name auto-discovery."""
        
        # Mock SSM parameter retrieval (in real scenario, Lambda stack would have created these)
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
                "description": "Test API Gateway with SSM Lambda import",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "organization": "test-workload",
                    "environment": "test",
                    "imports": {
                        "organization": "/test-workload/test/organization",
                        "environment": "/test-workload/test/environment",
                    },
                },
                "routes": [
                    {
                        "path": "/health",
                        "method": "GET",
                        "lambda_name": "test-lambda-function",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                        "cors": {
                            "origins": ["*"],
                            "methods": ["GET", "OPTIONS"],
                        },
                    }
                ],
            },
        }
        
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)
        
        # Create API Gateway stack
        stack = ApiGatewayStack(
            scope=app,
            id="test-api-gateway-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack - in real scenario SSM would have the Lambda ARN
        # The stack will create SSM parameter lookups
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        
        # Synthesize to verify structure
        template = Template.from_stack(stack)
        
        # Verify API Gateway was created
        template.has_resource("AWS::ApiGateway::RestApi", {})
        
        # Verify that the route was configured (even though Lambda import is dynamic)
        # The method should be created with Lambda integration
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "GET",
            },
        )

    def test_api_gateway_with_explicit_ssm_path(
        self, app, deployment_config, workload_config
    ):
        """Test API Gateway imports Lambda via explicit SSM path."""
        
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
                        "path": "/explicit",
                        "method": "POST",
                        "lambda_arn_ssm_path": "/custom/path/lambda/my-function/arn",
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
            id="test-api-gateway-explicit-ssm",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        
        # Synthesize to verify structure
        template = Template.from_stack(stack)
        
        # Verify API Gateway was created
        template.has_resource("AWS::ApiGateway::RestApi", {})
        
        # Verify that the route was configured
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "POST",
            },
        )

    def test_api_gateway_legacy_inline_lambda(
        self, app, deployment_config, workload_config
    ):
        """Test API Gateway still supports legacy pattern of creating Lambda inline."""
        
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }
        
        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway with inline Lambda (legacy)",
                "api_type": "REST",
                "stage_name": "prod",
                "routes": [
                    {
                        "path": "/legacy",
                        "method": "GET",
                        "src": "tests/unit/files/lambda",
                        "handler": "app.lambda_handler",
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
            id="test-api-gateway-legacy",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        
        # Synthesize to verify structure
        template = Template.from_stack(stack)
        
        # Verify API Gateway was created
        template.has_resource("AWS::ApiGateway::RestApi", {})
        
        # Verify Lambda function was created inline (legacy pattern)
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "app.lambda_handler",
            },
        )
        
        # Verify that the route was configured
        template.has_resource_properties(
            "AWS::ApiGateway::Method",
            {
                "HttpMethod": "GET",
            },
        )

    def test_api_gateway_mixed_lambda_sources(
        self, app, deployment_config, workload_config
    ):
        """Test API Gateway with mix of SSM-imported and inline Lambdas."""
        
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }
        
        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway with mixed Lambda sources",
                "api_type": "REST",
                "stage_name": "prod",
                "ssm": {
                    "enabled": True,
                    "imports": {
                        "organization": "/test-workload/test/organization",
                        "environment": "/test-workload/test/environment",
                    },
                },
                "routes": [
                    {
                        "path": "/imported",
                        "method": "GET",
                        "lambda_name": "imported-lambda",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    },
                    {
                        "path": "/inline",
                        "method": "POST",
                        "src": "tests/unit/files/lambda",
                        "handler": "app.lambda_handler",
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
            id="test-api-gateway-mixed",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        
        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        
        # Synthesize to verify structure
        template = Template.from_stack(stack)
        
        # Verify API Gateway was created
        template.has_resource("AWS::ApiGateway::RestApi", {})
        
        # Verify inline Lambda was created
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "app.lambda_handler",
            },
        )
        
        # Verify both routes were configured
        # Should have 2 methods (plus OPTIONS for CORS = 4 total potentially)
        methods = [
            res
            for res in template.to_json().get("Resources", {}).values()
            if res.get("Type") == "AWS::ApiGateway::Method"
            and res.get("Properties", {}).get("HttpMethod") in ["GET", "POST"]
        ]
        assert len(methods) >= 2, f"Expected at least 2 methods (GET and POST), found {len(methods)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
