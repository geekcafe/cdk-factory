"""
Unit tests for API Gateway cross-stack resource management.
Tests the API Gateway integration utility with existing resource imports using factory.build().
No mocking - tests actual CDK output.
"""

import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path
from aws_cdk import App, Environment
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as _lambda

# Add the cdk-factory source to Python path to ensure we use the latest code
cdk_factory_src = Path(__file__).parent.parent.parent / "src"
if str(cdk_factory_src) not in sys.path:
    sys.path.insert(0, str(cdk_factory_src))

from cdk_factory.stack_library.aws_lambdas.lambda_stack import LambdaStack
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.stack import StackConfig


class TestApiGatewayCrossStackResources:
    """Test API Gateway cross-stack resource management functionality."""

    @pytest.fixture
    def app(self):
        """Create CDK App for testing."""
        return App()

    @pytest.fixture
    def temp_lambda_dir(self):
        """Create temporary directory with minimal Lambda function."""
        temp_dir = tempfile.mkdtemp()
        lambda_dir = Path(temp_dir) / "lambda_handlers" / "test"
        lambda_dir.mkdir(parents=True)

        # Create minimal Lambda handler
        handler_file = lambda_dir / "app.py"
        handler_file.write_text(
            """
def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Hello from test lambda'
    }
"""
        )

        # Create requirements.txt
        requirements_file = lambda_dir / "requirements.txt"
        requirements_file.write_text("# No additional requirements\n")

        yield str(lambda_dir)

        # Cleanup
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def deployment_config(self):
        """Create deployment configuration."""
        workload_dict = {
            "name": "test-cross-stack",
            "description": "Test workload for cross-stack API Gateway testing",
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
                "API_GATEWAY_ROOT_RESOURCE_ID": "test-root-resource-id",
                "COGNITO_AUTHORIZER_ID": "test-authorizer-id",
            },
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        """Create workload configuration."""
        return WorkloadConfig(
            {
                "workload": {
                    "name": "test-cross-stack",
                    "description": "Test workload for cross-stack testing",
                    "devops": {"ci_cd": {"enabled": True}},
                }
            }
        )

    def test_normal_resource_creation(
        self, app, temp_lambda_dir, deployment_config, workload_config
    ):
        """Test that old API Gateway pattern raises deprecation error."""
        stack_config = StackConfig(
            {
                "name": "test-normal-stack",
                "module": "lambda_stack",
                "enabled": True,
                "api_gateway": {"stage": {"name": "prod", "use_existing": True}},
                "resources": [
                    {
                        "name": "test-function",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Test Lambda function",
                        "api": {
                            "route": "/app/services/test",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        # Create and build stack
        stack = LambdaStack(
            app,
            "TestNormalStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Should raise deprecation error for old API Gateway pattern
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_existing_resource_import(
        self, app, temp_lambda_dir, deployment_config, workload_config
    ):
        """Test that old API Gateway pattern with resource imports raises deprecation error."""
        stack_config = StackConfig(
            {
                "name": "test-import-stack",
                "module": "lambda_stack",
                "enabled": True,
                "api_gateway": {
                    "stage": {"name": "prod", "use_existing": True},
                    "existing_resources": {
                        "/app": {
                            "resource_id": "existing-app-resource-123",
                            "description": "Import existing app resource",
                        }
                    },
                },
                "resources": [
                    {
                        "name": "test-import-function",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Test Lambda function with resource import",
                        "api": {
                            "route": "/app/services/property/search/id",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        # Create and build stack
        stack = LambdaStack(
            app,
            "TestImportStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Should raise deprecation error for old API Gateway pattern
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_multiple_existing_resource_imports(
        self, app, temp_lambda_dir, deployment_config, workload_config
    ):
        """Test that old API Gateway pattern with multiple resource imports raises deprecation error."""
        stack_config = StackConfig(
            {
                "name": "test-multi-import-stack",
                "module": "lambda_stack",
                "enabled": True,
                "api_gateway": {
                    "stage": {"name": "prod", "use_existing": True},
                    "existing_resources": {
                        "/app": {
                            "resource_id": "existing-app-resource-123",
                            "description": "Import existing app resource",
                        },
                        "/app/services": {
                            "resource_id": "existing-services-resource-456",
                            "description": "Import existing services resource",
                        },
                    },
                },
                "resources": [
                    {
                        "name": "test-multi-import-function",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Test Lambda function with multiple resource imports",
                        "api": {
                            "route": "/app/services/property/search/id",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        # Create and build stack
        stack = LambdaStack(
            app,
            "TestMultiImportStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Should raise deprecation error for old API Gateway pattern
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_mixed_import_and_create_resources(
        self, app, temp_lambda_dir, deployment_config, workload_config
    ):
        """Test that old API Gateway pattern with mixed resources raises deprecation error."""
        stack_config = StackConfig(
            {
                "name": "test-mixed-stack",
                "module": "lambda_stack",
                "enabled": True,
                "api_gateway": {
                    "stage": {"name": "prod", "use_existing": True},
                    "existing_resources": {
                        "/app": {
                            "resource_id": "existing-app-resource-123",
                            "description": "Import existing app resource",
                        }
                    },
                },
                "resources": [
                    {
                        "name": "test-mixed-function-1",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Function using imported resource",
                        "api": {
                            "route": "/app/configuration",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    },
                    {
                        "name": "test-mixed-function-2",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Function creating new resource",
                        "api": {
                            "route": "/health/status",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    },
                ],
            },
            workload=workload_config.dictionary,
        )

        # Create and build stack
        stack = LambdaStack(
            app,
            "TestMixedStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Should raise deprecation error for old API Gateway pattern
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(stack_config, deployment_config, workload_config)

    def test_invalid_resource_import_fallback(
        self, app, temp_lambda_dir, deployment_config, workload_config
    ):
        """Test that old API Gateway pattern with invalid resource imports raises deprecation error."""
        stack_config = StackConfig(
            {
                "name": "test-fallback-stack",
                "module": "lambda_stack",
                "enabled": True,
                "api_gateway": {
                    "stage": {"name": "prod", "use_existing": True},
                    "existing_resources": {
                        "/app": {
                            # Missing resource_id to test fallback
                            "description": "Import existing app resource without ID"
                        }
                    },
                },
                "resources": [
                    {
                        "name": "test-fallback-function",
                        "src": temp_lambda_dir,
                        "handler": "app.lambda_handler",
                        "description": "Test Lambda function with fallback",
                        "api": {
                            "route": "/app/services/test",
                            "method": "GET",
                            "authorization_type": "NONE",
                        },
                        "permissions": [],
                        "environment_variables": {},
                    }
                ],
            },
            workload=workload_config.dictionary,
        )

        # Create and build stack
        stack = LambdaStack(
            app,
            "TestFallbackStack",
            env=Environment(account="123456789012", region="us-east-1"),
        )

        # Should raise deprecation error for old API Gateway pattern
        with pytest.raises(ValueError, match="DEPRECATED CONFIGURATION DETECTED"):
            stack.build(stack_config, deployment_config, workload_config)
