"""
Unit tests for Lambda Stack using real configuration objects.
Tests the enhanced lambda_stack.py functionality without mocks.
"""

import os
import pytest
from unittest.mock import patch
from aws_cdk import App, Environment
from aws_cdk import aws_lambda as _lambda

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.lambda_function import LambdaFunctionConfig


class TestLambdaStackReal:
    """Test cases for Lambda Stack functionality using real config objects."""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing."""
        return App()

    @pytest.fixture
    def deployment_config(self):
        """Create real deployment configuration."""
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
            "devops": {"ci_cd": {"enabled": True}},
        }
        deployment_dict = {
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
            "devops": {"ci_cd": {"enabled": True}},
            "environment_variables": {
                "COGNITO_USER_POOL_ID": "test-user-pool-id",
                "API_GATEWAY_ID": "test-api-gateway-id",
                "API_GATEWAY_ARN": "arn:aws:apigateway:us-east-1::/restapis/test-api-gateway-id",
            },
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        """Create real workload configuration."""
        config_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return WorkloadConfig(config=config_dict)

    @pytest.fixture
    def stack_config_with_lambda(self):
        """Create real stack configuration with Lambda resource."""
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "resources": [
                {
                    "name": "test-function",
                    "src": "src/handlers/test",
                    "handler": "handler.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        return StackConfig(stack=stack_dict, workload=workload_dict)

    @pytest.fixture
    def stack_config_with_api_lambda(self):
        """Create real stack configuration with API Gateway Lambda resource."""
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "resources": [
                {
                    "name": "test-function-api",
                    "src": "src/handlers/test",
                    "handler": "handler.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/test/endpoint",
                        "method": "POST",
                        "skip_authorizer": True,
                        "api_key_required": False,
                        "request_parameters": {},
                        "existing_api_gateway_id": None,
                        "existing_authorizer_id": None,
                    },
                }
            ],
        }
        return StackConfig(stack=stack_dict, workload=workload_dict)

    def test_lambda_stack_initialization(self, app):
        """Test Lambda stack initializes correctly."""
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        assert stack is not None
        assert hasattr(stack, "api_gateway_integrations")
        assert stack.api_gateway_integrations == []
        assert stack.stack_config is None
        assert stack.deployment is None
        assert stack.workload is None

    def test_lambda_stack_build_basic_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        stack_config_with_lambda,
    ):
        """Test Lambda stack builds with basic Lambda function using real CDK synthesis."""
        from aws_cdk.assertions import Template
        
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        stack.build(
            stack_config=stack_config_with_lambda,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        assert stack.stack_config == stack_config_with_lambda
        assert stack.deployment == deployment_config
        assert stack.workload == workload_config
        assert len(stack.functions) == 1
        assert len(stack.api_gateway_integrations) == 0

        # Verify CloudFormation resources are created
        template.has_resource_properties("AWS::Lambda::Function", {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.11",
            "Timeout": 30,
            "MemorySize": 256,
        })

        # Should not have API Gateway resources for basic lambda
        template.resource_count_is("AWS::ApiGateway::RestApi", 0)

    def test_lambda_stack_build_with_api_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        stack_config_with_api_lambda,
        monkeypatch,
    ):
        """Test Lambda stack builds with API Gateway integration using real CDK synthesis."""
        from aws_cdk.assertions import Template
        
        # Set required environment variable for authorizer
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack without any mocks
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack with real synthesis
        stack.build(
            stack_config=stack_config_with_api_lambda,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify stack properties
        assert stack.stack_config == stack_config_with_api_lambda
        assert stack.deployment == deployment_config
        assert stack.workload == workload_config
        assert len(stack.functions) == 1
        assert len(stack.api_gateway_integrations) == 1

        # Verify CloudFormation resources are created
        # Lambda function should be present
        template.has_resource_properties("AWS::Lambda::Function", {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.11",
            "Timeout": 30,
            "MemorySize": 256,
        })

        # API Gateway should be present
        template.has_resource("AWS::ApiGateway::RestApi", {})
        
        # API Gateway method should be present
        template.has_resource_properties("AWS::ApiGateway::Method", {
            "HttpMethod": "POST",
        })

        # Lambda permission for API Gateway should be present
        template.has_resource_properties("AWS::Lambda::Permission", {
            "Action": "lambda:InvokeFunction",
            "Principal": "apigateway.amazonaws.com",
        })

        # Since skip_authorizer is True, no authorizer should be created
        template.resource_count_is("AWS::ApiGateway::Authorizer", 0)

    def test_lambda_stack_build_with_authorizer_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        monkeypatch,
    ):
        """Test Lambda stack builds with API Gateway authorizer using real CDK synthesis."""
        from aws_cdk.assertions import Template
        
        # Set required environment variable for authorizer
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack config with authorizer enabled
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "resources": [
                {
                    "name": "test-function-auth",
                    "src": "src/handlers/test",
                    "handler": "handler.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/secure/endpoint",
                        "method": "GET",
                        "skip_authorizer": False,  # Enable authorizer
                        "api_key_required": False,
                        "request_parameters": {},
                        "existing_api_gateway_id": None,
                        "existing_authorizer_id": None,
                    },
                }
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create stack without any mocks
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack-auth",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack with real synthesis
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify CloudFormation resources are created
        # Lambda function should be present
        template.has_resource_properties("AWS::Lambda::Function", {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.11",
        })

        # API Gateway should be present
        template.has_resource("AWS::ApiGateway::RestApi", {})

        # API Gateway method should be present
        template.has_resource_properties("AWS::ApiGateway::Method", {
            "HttpMethod": "GET",
        })

        # Cognito User Pool Authorizer should be present
        template.has_resource_properties("AWS::ApiGateway::Authorizer", {
            "Type": "COGNITO_USER_POOLS",
        })

        # Verify the __setup_api_gateway_integration method was executed
        assert len(stack.api_gateway_integrations) == 1

    def test_lambda_stack_build_with_existing_authorizer_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        monkeypatch,
    ):
        """Test Lambda stack correctly handles existing authorizer ID (currently unsupported)."""
        import pytest
        from aws_cdk.assertions import Template
        
        # Set required environment variable for authorizer (even though we're using existing)
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack config with existing authorizer ID
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "resources": [
                {
                    "name": "test-function-existing-auth",
                    "src": "src/handlers/test",
                    "handler": "handler.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/existing/auth/endpoint",
                        "method": "POST",
                        "skip_authorizer": False,
                        "api_key_required": False,
                        "request_parameters": {},
                        "existing_api_gateway_id": None,
                        "existing_authorizer_id": "abc123def456",  # Use existing authorizer
                    },
                }
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create stack without any mocks
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack-existing-auth",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack with real synthesis - should now work with L1 constructs
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify CloudFormation resources are created
        # Lambda function should be present
        template.has_resource_properties("AWS::Lambda::Function", {
            "Handler": "handler.lambda_handler",
            "Runtime": "python3.11",
        })

        # API Gateway should be present
        template.has_resource("AWS::ApiGateway::RestApi", {})

        # API Gateway method should be present with existing authorizer ID
        template.has_resource_properties("AWS::ApiGateway::Method", {
            "HttpMethod": "POST",
            "AuthorizationType": "COGNITO_USER_POOLS",
            "AuthorizerId": "abc123def456",  # Should reference existing authorizer
        })

        # Lambda permission for API Gateway should be present
        template.has_resource_properties("AWS::Lambda::Permission", {
            "Action": "lambda:InvokeFunction",
            "Principal": "apigateway.amazonaws.com",
        })

        # No new authorizer should be created since we're using existing one
        template.resource_count_is("AWS::ApiGateway::Authorizer", 0)

        # Verify the __setup_api_gateway_integration method was executed
        assert len(stack.api_gateway_integrations) == 1
        
        # Verify that the integration references the existing authorizer
        integration = stack.api_gateway_integrations[0]
        assert integration["function_name"] == "test-function-existing-auth"

    def test_lambda_function_config_creation(self, deployment_config):
        """Test LambdaFunctionConfig creation with real config."""
        config_dict = {
            "name": "test-function",
            "source": "src/handlers/test",
            "handler": "handler.lambda_handler",
            "runtime": "python3.11",
            "timeout": 30,
            "memory_size": 256,
            "environment_variables": {"TEST_VAR": "test_value"},
            "triggers": [],
            "sqs": {"queues": []},
            "schedule": None,
        }

        lambda_config = LambdaFunctionConfig(
            config=config_dict, deployment=deployment_config
        )

        assert lambda_config.name == "test-function"
        assert lambda_config.handler == "handler.lambda_handler"
        assert lambda_config.runtime.name == "python3.11"
        assert lambda_config.timeout.to_seconds() == 30
        assert lambda_config.memory_size == 256
        # assert lambda_config.api.routes
        assert lambda_config.triggers == []

    def test_lambda_function_config_with_api(self, deployment_config):
        """Test LambdaFunctionConfig creation with API Gateway config."""
        config_dict = {
            "name": "test-function-api",
            "src": "src/handlers/test",
            "handler": "handler.lambda_handler",
            "runtime": "python3.11",
            "timeout": 30,
            "memory_size": 256,
            "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
            "triggers": [],
            "sqs": {"queues": []},
            "schedule": None,
            "api": {
                "route": "/test/endpoint",
                "method": "POST",
                "skip_authorizer": False,
                "api_key_required": False,
                "request_parameters": {},
                "existing_api_gateway_id": None,
                "existing_authorizer_id": None,
            },
        }

        lambda_config = LambdaFunctionConfig(
            config=config_dict, deployment=deployment_config
        )

        assert lambda_config.name == "test-function-api"
        assert lambda_config.api is not None
        assert lambda_config.api.route == "/test/endpoint"
        assert lambda_config.api.method == "POST"
        assert lambda_config.api.skip_authorizer is False

    def test_stack_config_validation(self, deployment_config, workload_config):
        """Test that stack config validation works correctly."""
        app = App()
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Test with empty resources - should raise ValueError
        workload_dict = {"name": "test-workload"}
        empty_stack_dict = {"name": "empty-stack", "resources": []}
        empty_config = StackConfig(stack=empty_stack_dict, workload=workload_dict)

        with pytest.raises(ValueError, match="No resources found in stack config"):
            stack.build(
                stack_config=empty_config,
                deployment=deployment_config,
                workload=workload_config,
            )
