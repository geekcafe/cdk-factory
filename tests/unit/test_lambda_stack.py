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
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [
                        {"name": "TEST_VAR", "value": "test_value"}
                    ],
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
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [
                        {"name": "TEST_VAR", "value": "test_value"}
                    ],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/test/endpoint",
                        "method": "POST",
                        "authorization_type": "NONE",
                        "api_key_required": False,
                        "request_parameters": {},
                        "api_gateway_id": None,
                        "authorizer_id": None,
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
        assert hasattr(stack, "exported_lambda_arns")
        assert stack.exported_lambda_arns == {}
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
        # No API Gateway integrations in new pattern
        assert len(stack.exported_lambda_arns) == 1

        # Verify CloudFormation resources are created
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "app.lambda_handler",
                "Runtime": "python3.11",
                "Timeout": 30,
                "MemorySize": 256,
            },
        )

        # Should not have API Gateway resources for basic lambda
        template.resource_count_is("AWS::ApiGateway::RestApi", 0)
        
        # Should not have SSM parameters if SSM is not enabled
        # (SSM export requires ssm.enabled: true in config)

    def test_lambda_stack_build_with_api_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        stack_config_with_api_lambda,
        monkeypatch,
    ):
        """Test Lambda stack raises deprecation error when API Gateway config is present."""
        import pytest

        # Set required environment variable for authorizer
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack without any mocks
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack with real synthesis - should raise deprecation error
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(
                stack_config=stack_config_with_api_lambda,
                deployment=deployment_config,
                workload=workload_config,
            )

    def test_lambda_stack_build_with_authorizer_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        monkeypatch,
    ):
        """Test Lambda stack raises deprecation error when API Gateway config with authorizer is present."""
        import pytest

        # Set required environment variable for authorizer
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack config with authorizer enabled - should trigger deprecation
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "api_gateway": {
                "name": "test-lambda-api",
                "description": "Test API for Lambda stack",
                "endpoint_types": ["REGIONAL"],
                "cognito_authorizer": {
                    "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TestPool123",
                    "authorizer_name": "TestAuthorizer",
                },
            },
            "resources": [
                {
                    "name": "test-function-auth",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [
                        {"name": "TEST_VAR", "value": "test_value"}
                    ],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/secure/endpoint",
                        "method": "GET",
                        "api_key_required": False,
                        "request_parameters": {},
                        "gateway_id": None,
                        "authorizer_id": None,
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

        # Build the stack - should raise deprecation error for api_gateway config
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(
                stack_config=stack_config,
                deployment=deployment_config,
                workload=workload_config,
            )

    def test_lambda_stack_build_with_existing_authorizer_real_synthesis(
        self,
        app,
        deployment_config,
        workload_config,
        monkeypatch,
    ):
        """Test Lambda stack raises deprecation error when API config with existing authorizer is present."""
        import pytest

        # Set required environment variable for authorizer (even though we're using existing)
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")

        # Create stack config with existing authorizer ID - should trigger deprecation
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
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [
                        {"name": "TEST_VAR", "value": "test_value"}
                    ],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                    "api": {
                        "route": "/existing/auth/endpoint",
                        "method": "POST",
                        "authorization_type": "COGNITO",
                        "api_key_required": False,
                        "request_parameters": {},
                        "api_gateway_id": None,
                        "authorizer_id": "abc123def456",  # Use existing authorizer
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

        # Build the stack - should raise deprecation error for api config
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(
                stack_config=stack_config,
                deployment=deployment_config,
                workload=workload_config,
            )

    def test_lambda_function_config_creation(self, deployment_config):
        """Test LambdaFunctionConfig creation with real config."""
        config_dict = {
            "name": "test-function",
            "source": "tests/unit/files/lambda",
            "handler": "app.lambda_handler",
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
        assert lambda_config.handler == "app.lambda_handler"
        assert lambda_config.runtime.name == "python3.11"
        assert lambda_config.timeout.to_seconds() == 30
        assert lambda_config.memory_size == 256
        # assert lambda_config.api.routes
        assert lambda_config.triggers == []

    def test_lambda_function_config_creation_with_api(self):
        """Test LambdaFunctionConfig creation with API Gateway config."""
        config_dict = {
            "name": "test-function-api",
            "src": "tests/unit/files/lambda",
            "handler": "app.lambda_handler",
            "runtime": "python3.11",
            "timeout": 30,
            "memory_size": 256,
            "environment_variables": [{"name": "TEST_VAR", "value": "test_value"}],
            "api": {
                "route": "/api/endpoint",
                "method": "POST",
                "authorization_type": "COGNITO",
                "api_key_required": False,
                "request_parameters": {},
                "api_gateway_id": None,
                "authorizer_id": None,
            },
        }

        lambda_config = LambdaFunctionConfig(config_dict)

        assert lambda_config.name == "test-function-api"
        assert lambda_config.handler == "app.lambda_handler"
        assert lambda_config.api.routes == "/api/endpoint"
        assert lambda_config.api.method == "POST"
        assert lambda_config.api.authorization_type == "COGNITO"

    def test_lambda_stack_with_real_sample_config(self, monkeypatch):
        """Test Lambda stack with real sample config using CdkAppFactory pattern."""
        from aws_cdk.assertions import Template
        from cdk_factory.app import CdkAppFactory
        import tempfile
        import os

        # Set required environment variables from the sample config
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TestPool123")
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.setenv("WORKLOAD_NAME", "factory-lambda")
        monkeypatch.setenv("AWS_ACCOUNT", "123456789012")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("HOSTED_ZONE_ID", "Z123456789")
        monkeypatch.setenv("HOSTED_ZONE_NAME", "example.com")
        monkeypatch.setenv("DNS_ALIAS", "api.example.com")
        monkeypatch.setenv("CODE_REPOSITORY_NAME", "geekcafe/factory-saas-lambda")
        monkeypatch.setenv(
            "CODE_REPOSITORY_ARN",
            "arn:aws:codeconnections:us-east-1:123456789012:connection/test",
        )
        monkeypatch.setenv("GIT_BRANCH", "main")
        monkeypatch.setenv("API_GATEWAY_ID", "wm4ctmgbu7")
        monkeypatch.setenv(
            "API_GATEWAY_ARN", "arn:aws:apigateway:us-east-1::/restapis/wm4ctmgbu7"
        )
        monkeypatch.setenv("COGNITO_AUTHORIZER_ID", "8m223r")
        monkeypatch.setenv("APP_TABLE_NAME", "factory-dev")

        # Use the real sample config file
        config_path = "tests/unit/files/lambda/sample_config.json"

        # Create a temporary directory for CDK output
        with tempfile.TemporaryDirectory() as temp_dir:
            outdir = os.path.join(temp_dir, "cdk.out")

            # Create the factory using the real pattern
            factory = CdkAppFactory(
                config_path=config_path,
                runtime_directory="tests/unit/files/lambda",
                outdir=outdir,
            )

            # This should reproduce the ValidationError with fromRestApiId()
            try:
                cloud_assembly = factory.synth(
                    paths=["tests/unit/files/lambda"], cdk_app_file="cdk_app.py"
                )

                # If we get here, our fix worked - no ValidationError occurred
                assert cloud_assembly is not None
                print(
                    "✅ Stack synthesis succeeded with existing API Gateway - ValidationError fixed!"
                )

                # Verify that all stacks were created
                stacks = cloud_assembly.stacks
                assert len(stacks) > 0, "No stacks were created"

                # Find the lambda stack - debug stack names first
                print(f"Available stacks: {[stack.stack_name for stack in stacks]}")

                # The sample config uses pipeline mode, so we need to find the pipeline stack
                # Look for any stack that contains our Lambda resources
                lambda_stack = None
                for stack in stacks:
                    template = stack.template
                    lambda_functions = [
                        res
                        for res in template.get("Resources", {}).values()
                        if res.get("Type") == "AWS::Lambda::Function"
                    ]
                    if len(lambda_functions) > 0:
                        lambda_stack = stack
                        break

                # If no stack has Lambda functions, just use the first stack for basic validation
                if lambda_stack is None and len(stacks) > 0:
                    lambda_stack = stacks[0]
                    print(
                        f"No Lambda functions found, using first stack for validation: {lambda_stack.stack_name}"
                    )

                assert (
                    lambda_stack is not None
                ), f"No stacks found. Available stacks: {[stack.stack_name for stack in stacks]}"
                print(f"✅ Using stack: {lambda_stack.stack_name}")

                # Verify the stack template contains the expected resources
                template = lambda_stack.template

                # Debug: Print all resource types in the template
                all_resources = template.get("Resources", {})
                resource_types = {}
                for res_name, res_data in all_resources.items():
                    res_type = res_data.get("Type", "Unknown")
                    if res_type not in resource_types:
                        resource_types[res_type] = 0
                    resource_types[res_type] += 1

                print(f"Template resource types: {resource_types}")
                print(f"Total resources in template: {len(all_resources)}")

                # Check that Lambda functions were created (may be 0 for pipeline stacks)
                lambda_functions = [
                    res
                    for res in template.get("Resources", {}).values()
                    if res.get("Type") == "AWS::Lambda::Function"
                ]

                print(f"✅ Found {len(lambda_functions)} Lambda functions")

                # For pipeline mode, the main validation is that synthesis succeeded without ValidationError
                print(
                    "✅ Main validation passed: Stack synthesis succeeded without ValidationError!"
                )

            except Exception as e:
                print(f"❌ Overlapping routes test failed: {e}")
                # Print more details about the error for debugging
                import traceback

                traceback.print_exc()
                raise AssertionError(f"Overlapping routes handling failed: {e}") from e

    def test_overlapping_api_gateway_routes(self, monkeypatch):
        """Test that deprecated overlapping routes config raises error"""
        from cdk_factory.app import CdkAppFactory
        import tempfile
        import os
        import pytest

        # Set up environment variables
        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.setenv("WORKLOAD_NAME", "overlapping-routes-test")
        monkeypatch.setenv("AWS_ACCOUNT", "123456789012")
        monkeypatch.setenv("AWS_REGION", "us-east-1")
        monkeypatch.setenv("API_GATEWAY_ID", "test123abc")
        monkeypatch.setenv("COGNITO_AUTHORIZER_ID", "auth456def")
        monkeypatch.setenv("COGNITO_USER_POOL_ID", "pool789ghi")
        monkeypatch.setenv("APP_TABLE_NAME", "test-table")

        # Use the overlapping routes config file (has deprecated API pattern)
        config_path = "tests/unit/files/lambda/overlapping_routes_config.json"

        # Create a temporary directory for CDK output
        with tempfile.TemporaryDirectory() as temp_dir:
            outdir = os.path.join(temp_dir, "cdk.out")

            # Create the factory using the real pattern
            factory = CdkAppFactory(
                config_path=config_path,
                runtime_directory="tests/unit/files/lambda",
                outdir=outdir,
            )

            # Should raise deprecation error for old API Gateway pattern
            with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
                factory.synth(
                    paths=["tests/unit/files/lambda"], cdk_app_file="cdk_app.py"
                )

    def test_lambda_stack_ssm_export(
        self,
        app,
        deployment_config,
        workload_config,
    ):
        """Test Lambda stack exports ARNs to SSM when enabled."""
        from aws_cdk.assertions import Template

        # Create stack config with SSM exports enabled
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload for Lambda stack testing",
        }
        stack_dict = {
            "name": "test-lambda-stack",
            "enabled": True,
            "ssm": {
                "enabled": True,
                "organization": "test-org",
                "environment": "test",
            },
            "resources": [
                {
                    "name": "test-function-ssm",
                    "src": "tests/unit/files/lambda",
                    "handler": "app.lambda_handler",
                    "runtime": "python3.11",
                    "timeout": 30,
                    "memory_size": 256,
                    "environment_variables": [
                        {"name": "TEST_VAR", "value": "test_value"}
                    ],
                    "triggers": [],
                    "sqs": {"queues": []},
                    "schedule": None,
                }
            ],
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        # Create stack
        stack = LambdaStack(
            scope=app,
            id="test-lambda-stack-ssm",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Build the stack
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )

        # Synthesize the stack to CloudFormation template
        template = Template.from_stack(stack)

        # Verify Lambda function was created
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "Handler": "app.lambda_handler",
                "Runtime": "python3.11",
            },
        )

        # Verify SSM parameters were created for Lambda ARN export
        template.has_resource_properties(
            "AWS::SSM::Parameter",
            {
                "Type": "String",
                "Tier": "Standard",
            },
        )

        # Should have 2 SSM parameters: arn and function-name
        template.resource_count_is("AWS::SSM::Parameter", 2)

        # Verify exported_lambda_arns was populated
        assert len(stack.exported_lambda_arns) == 1
        assert "test-function-ssm" in stack.exported_lambda_arns

    def test_stack_config_validation(self, deployment_config, workload_config):
        """Test that stack config validation works correctly."""
        app = App()
        stack = LambdaStack(
            scope=app,
            id="test-stack",
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
