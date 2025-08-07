import pytest
from aws_cdk import App
from aws_cdk import aws_apigateway as apigateway
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from unittest.mock import MagicMock
import pytest


def test_api_gateway_stack_minimal():
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "api_gateway": {
                "api_gateway_name": "TestApi",
                "description": "Minimal API Gateway",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    stack = ApiGatewayStack(app, "TestApiGatewayStack")
    stack.build(stack_config, deployment, dummy_workload)

    resources = [c for c in stack.node.children if isinstance(c, apigateway.RestApi)]
    assert len(resources) == 1
    api: apigateway.RestApi = resources[0]
    assert api.rest_api_name == "TestApi"
    assert api.stack.api_config.description == "Minimal API Gateway"


def test_api_gateway_stack_full_config():
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "dummy-workload", "devops": {"name": "dummy-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "api_gateway": {
                "api_gateway_name": "FullApi",
                "description": "Full config API Gateway",
                # "deploy": False,
                "endpoint_types": ["EDGE"],  # Use string to test enum conversion
                "binary_media_types": ["application/octet-stream"],
                "cloud_watch_role": False,
                "disable_execute_api_endpoint": True,
                "fail_on_warnings": True,
                "retain_deployments": True,
                "min_compression_size": 512,
                "cognito_authorizer": {
                    "user_pool_arn_ssm_path": "/dev/cdk-factory/cognito/user-pool-arn",
                    "authorizer_name": "CognitoAuthorizer",
                    "identity_source": "method.request.header.Authorization",
                },
                "routes": [
                    {
                        "path": "/app/health",
                        "method": "GET",
                        "handler": "app.lambda_handler",
                        "cors": {"methods": ["GET"], "origins": ["*"]},
                    },
                    {
                        "path": "/health",
                        "method": "GET",
                        "handler": "app.lambda_handler",
                        "authorization_type": "NONE",
                        "cors": {"methods": ["GET"], "origins": ["*"]},
                    },
                ],
                "hosted_zone": {
                    "record_name": "api.example.com",
                    "id": "Z12345678901234567890",
                    "name": "example.com",
                },
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "dummy-deployment"},
    )
    stack = ApiGatewayStack(app, "FullApiGatewayStack")
    stack.build(stack_config, deployment, dummy_workload)

    resources = [c for c in stack.node.children if isinstance(c, apigateway.RestApi)]
    assert len(resources) == 1
    api: apigateway.RestApi = resources[0]
    assert api.rest_api_name == "FullApi"
    assert api.stack.api_config.description == "Full config API Gateway"
    assert api.stack.api_config.deploy is True
    assert api.stack.api_config.endpoint_types[0] == "EDGE"
    assert api.stack.api_config.binary_media_types == ["application/octet-stream"]
    assert api.stack.api_config.cloud_watch_role is False
    assert api.stack.api_config.disable_execute_api_endpoint is True
    assert api.stack.api_config.fail_on_warnings is True
    assert api.stack.api_config.retain_deployments is True
    assert api.stack.api_config.min_compression_size == 512
