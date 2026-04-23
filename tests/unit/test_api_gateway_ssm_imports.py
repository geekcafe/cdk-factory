"""
Unit tests for API Gateway Stack SSM Lambda import path construction.
Covers namespace mode, legacy mode, and explicit SSM path scenarios.
"""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig


class TestApiGatewaySSMImports:
    """Test API Gateway SSM Lambda import path construction."""

    @pytest.fixture
    def app(self):
        return App()

    @pytest.fixture
    def deployment_config(self):
        workload_dict = {
            "name": "test-workload",
            "description": "Test workload",
        }
        deployment_dict = {
            "name": "test-deployment",
            "account": "123456789012",
            "region": "us-east-1",
            "environment": "test",
        }
        return DeploymentConfig(workload=workload_dict, deployment=deployment_dict)

    @pytest.fixture
    def workload_config(self):
        config_dict = {
            "name": "test-workload",
            "description": "Test workload",
            "devops": {"ci_cd": {"enabled": True}},
        }
        return WorkloadConfig(config=config_dict)

    def test_apigw_lambda_import_namespace(
        self, app, deployment_config, workload_config
    ):
        """Verify namespace SSM path for Lambda ARN import."""
        workload_dict = {"name": "test-workload"}
        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "ssm": {
                "auto_export": True,
                "imports": {
                    "namespace": "my-ns",
                },
            },
            "api_gateway": {
                "name": "test-api",
                "description": "Test API",
                "api_type": "REST",
                "stage_name": "prod",
                "routes": [
                    {
                        "path": "/test",
                        "method": "GET",
                        "lambda_name": "my-lambda",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    }
                ],
            },
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = ApiGatewayStack(
            scope=app,
            id="test-apigw-ns-import",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        # The stack should create an SSM parameter lookup at the namespace path.
        # CDK synthesizes SSM lookups as AWS::SSM::Parameter::Value<String> in
        # template parameters. Verify the template JSON contains the expected path.
        template_json = template.to_json()
        params = template_json.get("Parameters", {})
        found = any(
            "/my-ns/lambda/my-lambda/arn" in str(v.get("Default", ""))
            for v in params.values()
        )
        assert found, (
            "Expected SSM parameter lookup at /my-ns/lambda/my-lambda/arn "
            f"in template parameters, got: {params}"
        )

    def test_apigw_lambda_import_legacy(self, app, deployment_config, workload_config):
        """Verify that missing ssm.imports.namespace raises ValueError."""
        workload_dict = {"name": "test-workload"}
        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API",
                "api_type": "REST",
                "stage_name": "prod",
                "routes": [
                    {
                        "path": "/test",
                        "method": "GET",
                        "lambda_name": "my-lambda",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    }
                ],
            },
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = ApiGatewayStack(
            scope=app,
            id="test-apigw-legacy-import",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        with pytest.raises(ValueError, match="ssm.imports.namespace"):
            stack.build(
                stack_config=stack_config,
                deployment=deployment_config,
                workload=workload_config,
            )

    def test_apigw_explicit_ssm_path(self, app, deployment_config, workload_config):
        """Verify explicit SSM path is used without modification."""
        workload_dict = {"name": "test-workload"}
        stack_dict = {
            "name": "test-api-gateway",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API",
                "api_type": "REST",
                "stage_name": "prod",
                "routes": [
                    {
                        "path": "/test",
                        "method": "POST",
                        "lambda_arn_ssm_path": "/custom/path/arn",
                        "authorization_type": "NONE",
                        "allow_public_override": True,
                    }
                ],
            },
        }
        stack_config = StackConfig(stack=stack_dict, workload=workload_dict)

        stack = ApiGatewayStack(
            scope=app,
            id="test-apigw-explicit-path",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        stack.build(
            stack_config=stack_config,
            deployment=deployment_config,
            workload=workload_config,
        )
        template = Template.from_stack(stack)

        template_json = template.to_json()
        params = template_json.get("Parameters", {})
        found = any(
            "/custom/path/arn" in str(v.get("Default", "")) for v in params.values()
        )
        assert found, (
            "Expected SSM parameter lookup at /custom/path/arn "
            f"in template parameters, got: {params}"
        )
