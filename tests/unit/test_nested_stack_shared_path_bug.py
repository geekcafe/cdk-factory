"""
Bug Condition Exploration Test: Duplicate Shared Path Resources Across Nested Stacks

**Validates: Requirements 1.1, 1.2, 1.3**

This test demonstrates the bug condition where multiple nested stacks sharing
a common path prefix (e.g., `/v3/tenants/{tenant-id}`) each independently create
AWS::ApiGateway::Resource entries for the shared prefix segments. This causes
CloudFormation 409 AlreadyExists errors on deploy.

EXPECTED BEHAVIOR (what the test asserts):
- Shared path segment resources (v3, tenants, {tenant-id}) should appear in the
  PARENT stack template only — NOT duplicated across nested stack templates.
- Each nested stack should only contain path resources for its domain-specific
  segments (e.g., "users", "metrics").

ON UNFIXED CODE: This test FAILS because each nested stack template contains
AWS::ApiGateway::Resource entries for v3, tenants, and {tenant-id} — these
duplicates cause 409 AlreadyExists errors on deploy.

Counterexamples documented:
- Each nested stack template contains AWS::ApiGateway::Resource for segments
  v3, tenants, {tenant-id} — these duplicates cause 409 AlreadyExists on deploy.
"""

import json
import os
import pytest
from unittest.mock import patch
from aws_cdk import App

from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig
from utils.synth_test_utils import get_resources_by_type


def _make_shared_prefix_routes():
    """Create two route groups that share the /v3/tenants/{tenant-id} prefix.

    - "users" group: /v3/tenants/{tenant-id}/users
    - "metrics" group: /v3/tenants/{tenant-id}/metrics

    Both share the path prefix: v3 -> tenants -> {tenant-id}
    """
    return [
        {
            "path": "/v3/tenants/{tenant-id}/users",
            "method": "GET",
            "lambda_name": "get-users",
            "authorization_type": "COGNITO",
        },
        {
            "path": "/v3/tenants/{tenant-id}/metrics",
            "method": "GET",
            "lambda_name": "get-metrics",
            "authorization_type": "COGNITO",
        },
    ]


def _mock_resolve_lambda_folder(lambda_name: str) -> str:
    """Mock folder resolution to assign routes to different groups."""
    folder_map = {
        "get-users": "users",
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


def _count_path_segment_resources(template, segment_name: str) -> int:
    """Count AWS::ApiGateway::Resource entries whose PathPart matches segment_name.

    Args:
        template: CloudFormation template dict.
        segment_name: The path segment to search for (e.g., "v3", "tenants", "{tenant-id}").

    Returns:
        Number of resources with matching PathPart.
    """
    resources = get_resources_by_type(template, "AWS::ApiGateway::Resource")
    count = 0
    for r in resources:
        path_part = r["resource"].get("Properties", {}).get("PathPart", "")
        if path_part == segment_name:
            count += 1
    return count


@pytest.fixture
def shared_prefix_app():
    """Create a minimal app with nested stacks enabled and two route groups
    sharing the /v3/tenants/{tenant-id} prefix, then synthesize it.

    This fixture sets up the exact bug condition:
    - Two route groups ("users" and "metrics")
    - Both have routes under /v3/tenants/{tenant-id}/...
    - Nested stacks enabled
    - Each nested stack receives root_resource_id (the bug)
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
                "name": "test-shared-prefix-api",
                "description": "Test API for shared prefix bug",
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

    stack = ApiGatewayStack(app, "TestSharedPrefixBug")

    with (
        patch.object(
            stack, "_resolve_lambda_folder", side_effect=_mock_resolve_lambda_folder
        ),
        patch.object(
            stack,
            "_discover_routes_from_dependencies",
            return_value=_make_shared_prefix_routes(),
        ),
    ):
        stack.build(stack_config, deployment, dummy_workload)

    cloud_assembly = app.synth()

    return {
        "app": app,
        "stack": stack,
        "cloud_assembly": cloud_assembly,
    }


class TestNestedStackSharedPathBug:
    """Bug condition exploration: duplicate shared path resources across nested stacks.

    **Validates: Requirements 1.1, 1.2, 1.3**

    These tests assert the EXPECTED (correct) behavior: shared path segment
    resources should only exist in the parent stack, not in nested stacks.

    On UNFIXED code, these tests FAIL — confirming the bug exists.

    Counterexamples:
    - Each nested stack template contains AWS::ApiGateway::Resource for segments
      v3, tenants, {tenant-id} — these duplicates cause 409 AlreadyExists on deploy.
    """

    def test_shared_prefix_resources_not_duplicated_in_nested_stacks(
        self, shared_prefix_app
    ):
        """Assert that shared path segments (v3, tenants, {tenant-id}) do NOT
        appear in nested stack templates.

        Bug condition: When multiple nested stacks share /v3/tenants/{tenant-id},
        each nested stack independently creates resources for v3, tenants, and
        {tenant-id}. This causes CloudFormation 409 errors.

        Expected behavior: Shared prefix resources should be in the parent stack
        only. Nested stacks should only have domain-specific segments.
        """
        cloud_assembly = shared_prefix_app["cloud_assembly"]
        nested_templates = _get_nested_stack_templates(cloud_assembly)

        assert len(nested_templates) == 2, (
            f"Expected 2 nested stack templates (users, metrics), "
            f"got {len(nested_templates)}"
        )

        shared_segments = ["v3", "tenants", "{tenant-id}"]

        for i, ns_template in enumerate(nested_templates):
            for segment in shared_segments:
                count = _count_path_segment_resources(ns_template, segment)
                assert count == 0, (
                    f"COUNTEREXAMPLE: Nested stack template {i} contains "
                    f"{count} AWS::ApiGateway::Resource with PathPart='{segment}'. "
                    f"Shared path segments should be in the parent stack only, "
                    f"not duplicated across nested stacks. "
                    f"This duplication causes CloudFormation 409 AlreadyExists errors."
                )

    def test_total_shared_segment_resources_across_nested_stacks(
        self, shared_prefix_app
    ):
        """Assert that the total count of shared path segment resources across
        ALL nested stacks is zero.

        If the bug exists, we expect 2 copies of each shared segment (one per
        nested stack) = 6 total duplicate resources across 2 stacks.
        """
        cloud_assembly = shared_prefix_app["cloud_assembly"]
        nested_templates = _get_nested_stack_templates(cloud_assembly)

        shared_segments = ["v3", "tenants", "{tenant-id}"]
        total_duplicates = 0

        for ns_template in nested_templates:
            for segment in shared_segments:
                total_duplicates += _count_path_segment_resources(ns_template, segment)

        assert total_duplicates == 0, (
            f"COUNTEREXAMPLE: Found {total_duplicates} shared path segment "
            f"resources across nested stack templates. Expected 0. "
            f"Each nested stack is independently creating resources for the "
            f"shared prefix segments (v3, tenants, {{tenant-id}}), which causes "
            f"CloudFormation 409 AlreadyExists errors on deploy."
        )

    def test_nested_stacks_only_contain_domain_specific_segments(
        self, shared_prefix_app
    ):
        """Assert that each nested stack only contains path resources for its
        domain-specific segments (after the shared prefix).

        - "users" nested stack should only have a resource for "users"
        - "metrics" nested stack should only have a resource for "metrics"

        Neither should have resources for v3, tenants, or {tenant-id}.
        """
        cloud_assembly = shared_prefix_app["cloud_assembly"]
        nested_templates = _get_nested_stack_templates(cloud_assembly)

        shared_segments = {"v3", "tenants", "{tenant-id}"}
        domain_segments = {"users", "metrics"}

        for ns_template in nested_templates:
            api_resources = get_resources_by_type(
                ns_template, "AWS::ApiGateway::Resource"
            )

            for r in api_resources:
                path_part = r["resource"].get("Properties", {}).get("PathPart", "")
                assert path_part not in shared_segments, (
                    f"COUNTEREXAMPLE: Nested stack contains "
                    f"AWS::ApiGateway::Resource with PathPart='{path_part}' "
                    f"which is a shared prefix segment. Only domain-specific "
                    f"segments ({domain_segments}) should be in nested stacks. "
                    f"Shared segments should be created in the parent stack."
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
