"""Tests for API Gateway stack synthesis"""
import pytest
from unittest.mock import patch, MagicMock
from aws_cdk import App
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_apigateway as apigateway

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig
from utils.synth_test_utils import (
    get_resources_by_type,
    assert_resource_count,
    assert_has_resource_with_properties,
    assert_has_tag,
    find_tag_value
)


@pytest.fixture
def dummy_workload():
    """Create a dummy workload config for testing"""
    return WorkloadConfig(
        {
            "name": "dummy-workload",
            "description": "Dummy workload for testing",
            "devops": {
                "account": "123456789012",
                "region": "us-east-1",
                "commands": []
            },
            "stacks": [
                {
                    "name": "api-test",
                    "module": "api_gateway_library_module",
                    "enabled": True,
                    "api_gateway": {
                        "name": "test-api",
                        "description": "Test API Gateway",
                        "endpoint_types": ["REGIONAL"],
                        "cors": True,
                        "api_key_required": False,
                        "default_method_options": {
                            "authorization_type": apigateway.AuthorizationType.NONE
                        }
                    },
                }
            ],
        }
    )


def test_api_gateway_stack_synth(dummy_workload):
    """Test that the API Gateway stack can be synthesized without errors"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "api-test",
            "module": "api_gateway_library_module",
            "enabled": True,
            "api_gateway": {
                "name": "test-api",
                "description": "Test API Gateway",
                "endpoint_types": ["REGIONAL"],
                "cors": True,
                "api_key_required": False,
                "default_method_options": {
                    "authorization_type": apigateway.AuthorizationType.NONE
                }
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = ApiGatewayStack(app, "TestApiGatewayStack")
    
    # Build the stack
    stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestApiGatewayStack").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a REST API
    rest_api_resources = get_resources_by_type(template, "AWS::ApiGateway::RestApi")
    assert len(rest_api_resources) == 1
    
    # Get the REST API resource
    rest_api_resource = rest_api_resources[0]["resource"]
    
    # Check REST API properties
    assert rest_api_resource["Properties"]["Name"] == "test-api"
    assert rest_api_resource["Properties"]["Description"] == "Test API Gateway"
    assert rest_api_resource["Properties"]["EndpointConfiguration"]["Types"] == ["REGIONAL"]
    
    # Check that we have a deployment
    deployment_resources = get_resources_by_type(template, "AWS::ApiGateway::Deployment")
    assert len(deployment_resources) > 0
    
    # Check that we have a stage
    stage_resources = get_resources_by_type(template, "AWS::ApiGateway::Stage")
    assert len(stage_resources) > 0


def test_api_gateway_with_resources(dummy_workload):
    """Test that the API Gateway stack can be synthesized with resources and methods"""
    # Create the app and stack
    app = App()
    
    # Create the stack config
    stack_config = StackConfig(
        {
            "name": "api-test",
            "module": "api_gateway_library_module",
            "enabled": True,
            "api_gateway": {
                "name": "test-api-with-resources",
                "description": "Test API Gateway with resources",
                "endpoint_types": ["REGIONAL"],
                "cors": True,
                "api_key_required": True,
                "default_method_options": {
                    "authorization_type": apigateway.AuthorizationType.NONE
                },
                "resources": [
                    {
                        "path": "/users",
                        "methods": [
                            {
                                "http_method": "GET",
                                "integration_type": "MOCK",
                                "request_templates": {
                                    "application/json": '{"statusCode": 200}'
                                },
                                "integration_responses": [
                                    {
                                        "status_code": "200",
                                        "response_templates": {
                                            "application/json": '{"message": "Success"}'
                                        }
                                    }
                                ],
                                "method_responses": [
                                    {
                                        "status_code": "200",
                                        "response_models": {
                                            "application/json": "Empty"
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ],
                "api_keys": [
                    {
                        "name": "test-api-key",
                        "description": "Test API Key"
                    }
                ],
                "usage_plans": [
                    {
                        "name": "test-usage-plan",
                        "description": "Test Usage Plan",
                        "throttle": {
                            "rate_limit": 10,
                            "burst_limit": 5
                        },
                        "quota": {
                            "limit": 1000,
                            "period": "MONTH"
                        }
                    }
                ]
            },
        },
        workload=dummy_workload.dictionary,
    )
    
    # Create the deployment config
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment"},
    )
    
    # Create and build the stack
    stack = ApiGatewayStack(app, "TestApiGatewayWithResources")
    
    # Build the stack
    stack.build(stack_config, deployment, dummy_workload)
    
    # Synthesize the stack to CloudFormation
    template = app.synth().get_stack_by_name("TestApiGatewayWithResources").template
    
    # Verify the template has the expected resources
    resources = template.get("Resources", {})
    
    # Check that we have a REST API
    rest_api_resources = get_resources_by_type(template, "AWS::ApiGateway::RestApi")
    assert len(rest_api_resources) == 1
    
    # Check that we have API resources
    api_resources = get_resources_by_type(template, "AWS::ApiGateway::Resource")
    assert len(api_resources) > 0
    
    # Find the /users resource
    users_resource = None
    for resource_info in api_resources:
        resource = resource_info["resource"]
        if resource["Properties"].get("PathPart") == "users":
            users_resource = resource
            break
    
    assert users_resource is not None, "Resource /users not found"
    
    # Check that we have methods
    method_resources = get_resources_by_type(template, "AWS::ApiGateway::Method")
    assert len(method_resources) > 0
    
    # Check that we have API keys
    api_key_resources = get_resources_by_type(template, "AWS::ApiGateway::ApiKey")
    assert len(api_key_resources) > 0
    
    # Check that we have usage plans
    usage_plan_resources = get_resources_by_type(template, "AWS::ApiGateway::UsagePlan")
    assert len(usage_plan_resources) > 0
    
    # Get the usage plan resource
    usage_plan_resource = usage_plan_resources[0]["resource"]
    
    # Check usage plan properties
    assert usage_plan_resource["Properties"]["UsagePlanName"] == "test-usage-plan"
    assert usage_plan_resource["Properties"]["Description"] == "Test Usage Plan"
    assert usage_plan_resource["Properties"]["Throttle"]["RateLimit"] == 10
    assert usage_plan_resource["Properties"]["Throttle"]["BurstLimit"] == 5
    assert usage_plan_resource["Properties"]["Quota"]["Limit"] == 1000
    assert usage_plan_resource["Properties"]["Quota"]["Period"] == "MONTH"
