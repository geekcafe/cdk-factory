"""
CDK synthesis tests for API Gateway nested stack mode.

Verifies that when nested_stacks.enabled is true:
1. Parent template contains AWS::CloudFormation::Stack resources (one per route group)
2. Nested stack templates contain methods and Lambda permissions
3. Parent template retains shared resources: REST API, authorizer, deployment, stage

Requirements: 1.3, 2.1, 2.2, 2.3, 2.4, 2.7, 3.3, 3.4
"""

import json
import os
import pytest
from unittest.mock import patch
from aws_cdk import App

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from utils.synth_test_utils import get_resources_by_type


def _make_routes():
    """Create a minimal set of routes across 3 groups for testing."""
    return [
        {
            "path": "/v3/tenants/{tenant_id}/users",
            "method": "GET",
            "lambda_name": "get-users",
            "authorization_type": "COGNITO",
        },
        {
            "path": "/v3/tenants/{tenant_id}/users/{user_id}",
            "method": "PUT",
            "lambda_name": "update-user",
            "authorization_type": "COGNITO",
        },
        {
            "path": "/v3/tenants/{tenant_id}/files",
            "method": "GET",
            "lambda_name": "get-files",
            "authorization_type": "COGNITO",
        },
        {
            "path": "/v3/tenants/{tenant_id}/metrics",
            "method": "GET",
            "lambda_name": "get-metrics",
            "authorization_type": "COGNITO",
        },
    ]


def _mock_resolve_lambda_folder(lambda_name: str) -> str:
    """Mock folder resolution for test routes."""
    folder_map = {
        "get-users": "users",
        "update-user": "users",
        "get-files": "file-system",
        "get-metrics": "metrics",
    }
    return folder_map.get(lambda_name, "")


def _get_nested_stack_templates(cloud_assembly):
    """Extract nested stack templates from the cloud assembly directory.

    CDK writes nested stack templates with a '.nested.template.json' suffix.
    """
    assembly_dir = cloud_assembly.directory
    templates = []

    for filename in os.listdir(assembly_dir):
        if filename.endswith(".nested.template.json"):
            filepath = os.path.join(assembly_dir, filename)
            with open(filepath, "r") as f:
                templates.append(json.load(f))

    return templates


@pytest.fixture
def nested_stack_app():
    """Create a fully configured app with nested stacks enabled and synthesize it.

    Mocks:
    - _resolve_lambda_folder: returns known folder paths without file I/O
    - _discover_routes_from_dependencies: returns our test routes directly
    """
    app = App()

    dummy_workload = WorkloadConfig(
        {
            "workload": {
                "name": "test-workload",
                "devops": {
                    "name": "test-devops",
                    "account": "123456789012",
                    "region": "us-east-1",
                    "commands": [],
                },
            },
        }
    )

    stack_config = StackConfig(
        {
            "name": "api-gateway-test",
            "module": "api_gateway_library_module",
            "enabled": True,
            "ssm": {
                "namespace": "test/api-gateway",
                "auto_export": True,
                "imports": {
                    "lambda_namespace": "test/lambdas",
                    "cognito_namespace": "test/cognito",
                },
            },
            "api_gateway": {
                "name": "test-nested-api",
                "description": "Test API with nested stacks",
                "api_type": "REST",
                "endpoint_types": ["REGIONAL"],
                "stage_name": "prod",
                "cognito_authorizer": {
                    "name": "CognitoAuth",
                    "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TestPool",
                },
                "nested_stacks": {
                    "enabled": True,
                    "max_resources_per_stack": 200,
                    "grouping": {
                        "users": ["users"],
                        "file-system": ["file-system"],
                        "metrics": ["metrics"],
                    },
                },
            },
        },
        workload=dummy_workload.dictionary,
    )

    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment", "environment": "dev"},
    )

    stack = ApiGatewayStack(app, "TestNestedStacksApi")

    # Mock _resolve_lambda_folder to avoid file system scanning
    # Mock _discover_routes_from_dependencies to return our test routes
    with (
        patch.object(
            stack, "_resolve_lambda_folder", side_effect=_mock_resolve_lambda_folder
        ),
        patch.object(
            stack, "_discover_routes_from_dependencies", return_value=_make_routes()
        ),
    ):
        stack.build(stack_config, deployment, dummy_workload)

    # Synthesize the entire app (parent + nested stacks)
    cloud_assembly = app.synth()

    return {
        "app": app,
        "stack": stack,
        "cloud_assembly": cloud_assembly,
    }


class TestNestedStacksSynthesis:
    """Test CDK synthesis with nested stacks enabled."""

    def test_parent_contains_nested_stack_resources(self, nested_stack_app):
        """Verify parent template contains AWS::CloudFormation::Stack resources.

        Requirement 1.3: Create one nested stack per Route_Group.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        nested_stack_resources = get_resources_by_type(
            parent_template, "AWS::CloudFormation::Stack"
        )

        # We configured 3 groups: users, file-system, metrics
        assert len(nested_stack_resources) == 3, (
            f"Expected 3 nested stacks (one per route group), "
            f"got {len(nested_stack_resources)}"
        )

    def test_one_nested_stack_per_configured_route_group(self, nested_stack_app):
        """Verify exactly one nested stack per configured route group.

        Requirement 1.3: THE Parent_Stack SHALL create one Nested_Stack per Route_Group.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        nested_stack_resources = get_resources_by_type(
            parent_template, "AWS::CloudFormation::Stack"
        )

        # Verify logical IDs contain the group names
        logical_ids = [r["logical_id"] for r in nested_stack_resources]

        # Each group should have a corresponding nested stack
        # CDK generates logical IDs from construct IDs, so they should contain
        # the group name pattern
        assert any(
            "users" in lid.lower() for lid in logical_ids
        ), f"No nested stack found for 'users' group. Logical IDs: {logical_ids}"
        assert any(
            "filesystem" in lid.lower() or "file" in lid.lower() for lid in logical_ids
        ), f"No nested stack found for 'file-system' group. Logical IDs: {logical_ids}"
        assert any(
            "metrics" in lid.lower() for lid in logical_ids
        ), f"No nested stack found for 'metrics' group. Logical IDs: {logical_ids}"

    def test_parent_contains_rest_api(self, nested_stack_app):
        """Verify parent template contains the REST API resource.

        Requirement 2.1: THE Parent_Stack SHALL create and own the RestApi.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        rest_api_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::RestApi"
        )

        assert (
            len(rest_api_resources) == 1
        ), f"Expected exactly 1 REST API in parent, got {len(rest_api_resources)}"

    def test_parent_contains_authorizer(self, nested_stack_app):
        """Verify parent template contains the Cognito authorizer.

        Requirement 2.2: THE Parent_Stack SHALL create and own the Authorizer.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        authorizer_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Authorizer"
        )

        assert len(authorizer_resources) >= 1, (
            f"Expected at least 1 authorizer in parent, "
            f"got {len(authorizer_resources)}"
        )

    def test_parent_contains_deployment(self, nested_stack_app):
        """Verify parent template contains the Deployment resource.

        Requirement 2.3: THE Parent_Stack SHALL create and own the Deployment.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        deployment_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Deployment"
        )

        assert len(deployment_resources) >= 1, (
            f"Expected at least 1 deployment in parent, "
            f"got {len(deployment_resources)}"
        )

    def test_parent_contains_stage(self, nested_stack_app):
        """Verify parent template contains the Stage resource.

        Requirement 2.4: THE Parent_Stack SHALL create and own the Stage.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        stage_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Stage"
        )

        assert (
            len(stage_resources) >= 1
        ), f"Expected at least 1 stage in parent, got {len(stage_resources)}"

    def test_nested_stacks_contain_methods(self, nested_stack_app):
        """Verify nested stack templates contain API Gateway Method resources.

        Requirement 3.3: THE Nested_Stack SHALL create Method entries.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        nested_stack_templates = _get_nested_stack_templates(cloud_assembly)

        assert (
            len(nested_stack_templates) > 0
        ), "No nested stack templates found in cloud assembly"

        # Verify nested stacks contain Method resources
        total_methods = 0
        for ns_template in nested_stack_templates:
            methods = get_resources_by_type(ns_template, "AWS::ApiGateway::Method")
            total_methods += len(methods)

        # We have 4 routes, so we expect at least 4 methods across nested stacks
        # (plus OPTIONS methods for CORS)
        assert (
            total_methods >= 4
        ), f"Expected at least 4 methods across nested stacks, got {total_methods}"

    def test_nested_stacks_contain_lambda_permissions(self, nested_stack_app):
        """Verify nested stack templates contain Lambda Permission resources.

        Requirement 3.4: THE Nested_Stack SHALL create Lambda Permission entries.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        nested_stack_templates = _get_nested_stack_templates(cloud_assembly)

        assert (
            len(nested_stack_templates) > 0
        ), "No nested stack templates found in cloud assembly"

        # Verify nested stacks contain Lambda Permission resources
        total_permissions = 0
        for ns_template in nested_stack_templates:
            permissions = get_resources_by_type(ns_template, "AWS::Lambda::Permission")
            total_permissions += len(permissions)

        # We have 4 routes, so we expect at least 4 Lambda permissions
        assert total_permissions >= 4, (
            f"Expected at least 4 Lambda permissions across nested stacks, "
            f"got {total_permissions}"
        )

    def test_nested_stacks_do_not_contain_shared_resources(self, nested_stack_app):
        """Verify nested stacks do NOT create their own RestApi, Authorizer, Deployment, or Stage.

        Requirement 2.7: THE Nested_Stack SHALL NOT create its own shared resources.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        nested_stack_templates = _get_nested_stack_templates(cloud_assembly)

        assert (
            len(nested_stack_templates) > 0
        ), "No nested stack templates found in cloud assembly"

        for ns_template in nested_stack_templates:
            rest_apis = get_resources_by_type(ns_template, "AWS::ApiGateway::RestApi")
            authorizers = get_resources_by_type(
                ns_template, "AWS::ApiGateway::Authorizer"
            )
            deployments = get_resources_by_type(
                ns_template, "AWS::ApiGateway::Deployment"
            )
            stages = get_resources_by_type(ns_template, "AWS::ApiGateway::Stage")

            assert (
                len(rest_apis) == 0
            ), "Nested stack should NOT contain AWS::ApiGateway::RestApi"
            assert (
                len(authorizers) == 0
            ), "Nested stack should NOT contain AWS::ApiGateway::Authorizer"
            assert (
                len(deployments) == 0
            ), "Nested stack should NOT contain AWS::ApiGateway::Deployment"
            assert (
                len(stages) == 0
            ), "Nested stack should NOT contain AWS::ApiGateway::Stage"

    def test_parent_does_not_contain_methods(self, nested_stack_app):
        """Verify parent template does NOT contain Method resources directly.

        Methods should be in nested stacks, not the parent.
        """
        cloud_assembly = nested_stack_app["cloud_assembly"]
        stack = nested_stack_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        method_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Method"
        )

        assert len(method_resources) == 0, (
            f"Parent should NOT contain Method resources directly when nested stacks "
            f"are enabled, but found {len(method_resources)}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
