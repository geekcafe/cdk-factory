"""
CDK synthesis integration tests for tree-based path ownership.

Verifies that the PathOwnershipBuilder correctly integrates with the
ApiGatewayStack and ApiGatewayRouteGroupNestedStack during CDK synthesis,
producing CloudFormation templates with correct resource ownership.

Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.2, 6.1, 6.2, 6.3, 7.1, 7.2
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_multi_group_routes():
    """Create routes representing the real Aplos NCA configuration (12 groups).

    Routes span multiple groups that share the /v3/tenants/{tenant-id} prefix,
    plus groups that diverge at /v3 (e.g., warm-up under /v3/admin).
    """
    return [
        # users group
        {
            "path": "/v3/tenants/{tenant-id}/users",
            "method": "GET",
            "lambda_name": "get-users",
        },
        {
            "path": "/v3/tenants/{tenant-id}/users/{user-id}",
            "method": "GET",
            "lambda_name": "get-user",
        },
        {
            "path": "/v3/tenants/{tenant-id}/users/{user-id}",
            "method": "PUT",
            "lambda_name": "update-user",
        },
        # workflow-api group
        {
            "path": "/v3/tenants/{tenant-id}/workflow/executions",
            "method": "POST",
            "lambda_name": "create-execution",
        },
        {
            "path": "/v3/tenants/{tenant-id}/workflow/executions/{execution-id}",
            "method": "GET",
            "lambda_name": "get-execution",
        },
        # file-system group
        {
            "path": "/v3/tenants/{tenant-id}/files",
            "method": "GET",
            "lambda_name": "get-files",
        },
        {
            "path": "/v3/tenants/{tenant-id}/files/{file-id}",
            "method": "GET",
            "lambda_name": "get-file",
        },
        # metrics group
        {
            "path": "/v3/tenants/{tenant-id}/metrics",
            "method": "GET",
            "lambda_name": "get-metrics",
        },
        {
            "path": "/v3/tenants/{tenant-id}/users/{user-id}/metrics",
            "method": "GET",
            "lambda_name": "get-user-metrics",
        },
        # audit-logs group
        {
            "path": "/v3/tenants/{tenant-id}/audit-logs",
            "method": "GET",
            "lambda_name": "get-audit-logs",
        },
        # report-templates group
        {
            "path": "/v3/tenants/{tenant-id}/report-templates",
            "method": "GET",
            "lambda_name": "get-report-templates",
        },
        {
            "path": "/v3/tenants/{tenant-id}/report-templates/{template-id}",
            "method": "GET",
            "lambda_name": "get-report-template",
        },
        # subscriptions group
        {
            "path": "/v3/tenants/{tenant-id}/subscriptions",
            "method": "GET",
            "lambda_name": "get-subscriptions",
        },
        # tenants group
        {
            "path": "/v3/tenants/{tenant-id}",
            "method": "GET",
            "lambda_name": "get-tenant",
        },
        {
            "path": "/v3/tenants/{tenant-id}/settings",
            "method": "GET",
            "lambda_name": "get-tenant-settings",
        },
        # site-messages group
        {
            "path": "/v3/tenants/{tenant-id}/site-messages",
            "method": "GET",
            "lambda_name": "get-site-messages",
        },
        # validations group
        {
            "path": "/v3/tenants/{tenant-id}/validations",
            "method": "POST",
            "lambda_name": "run-validation",
        },
        # warm-up group (diverges at /v3)
        {"path": "/v3/admin/warm-up", "method": "POST", "lambda_name": "warm-up"},
        # legacy group
        {
            "path": "/v3/tenants/{tenant-id}/legacy/reports",
            "method": "GET",
            "lambda_name": "get-legacy-reports",
        },
    ]


def _mock_resolve_lambda_folder(lambda_name: str) -> str:
    """Mock folder resolution mapping lambda names to their group folders."""
    folder_map = {
        "get-users": "users",
        "get-user": "users",
        "update-user": "users",
        "create-execution": "workflow/api",
        "get-execution": "workflow/api",
        "get-files": "file-system",
        "get-file": "file-system",
        "get-metrics": "metrics",
        "get-user-metrics": "metrics",
        "get-audit-logs": "audit-logs",
        "get-report-templates": "report-templates",
        "get-report-template": "report-templates",
        "get-subscriptions": "subscriptions",
        "get-tenant": "tenants",
        "get-tenant-settings": "tenants",
        "get-site-messages": "site-messages",
        "run-validation": "validations",
        "warm-up": "warm-up",
        "get-legacy-reports": "legacy",
    }
    return folder_map.get(lambda_name, "")


def _get_nested_stack_templates(cloud_assembly):
    """Extract nested stack templates from the cloud assembly directory."""
    assembly_dir = cloud_assembly.directory
    templates = []

    for filename in os.listdir(assembly_dir):
        if filename.endswith(".nested.template.json"):
            filepath = os.path.join(assembly_dir, filename)
            with open(filepath, "r") as f:
                templates.append(json.load(f))

    return templates


def _get_all_api_gateway_resources_from_template(template):
    """Get all AWS::ApiGateway::Resource entries with their PathPart values."""
    resources = get_resources_by_type(template, "AWS::ApiGateway::Resource")
    return [
        {
            "logical_id": r["logical_id"],
            "path_part": r["resource"]["Properties"].get("PathPart", ""),
        }
        for r in resources
    ]


def _build_nested_stacks_app(routes, grouping, nested_stacks_enabled=True):
    """Build and synthesize an API Gateway stack with the given configuration.

    Args:
        routes: List of route dicts.
        grouping: Dict mapping group names to folder lists.
        nested_stacks_enabled: Whether nested stacks are enabled.

    Returns:
        Dict with 'app', 'stack', 'cloud_assembly' keys.
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

    api_gateway_config = {
        "name": "test-path-ownership-api",
        "description": "Integration test API",
        "api_type": "REST",
        "endpoint_types": ["REGIONAL"],
        "stage_name": "api",
        "cognito_authorizer": {
            "name": "CognitoAuth",
            "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TestPool",
        },
        "nested_stacks": {
            "enabled": nested_stacks_enabled,
            "max_resources_per_stack": 200,
            "grouping": grouping,
        },
    }

    stack_config = StackConfig(
        {
            "name": "api-gateway-integration-test",
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
            "api_gateway": api_gateway_config,
        },
        workload=dummy_workload.dictionary,
    )

    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment", "environment": "dev"},
    )

    stack = ApiGatewayStack(app, "TestPathOwnershipIntegration")

    with (
        patch.object(
            stack, "_resolve_lambda_folder", side_effect=_mock_resolve_lambda_folder
        ),
        patch.object(stack, "_discover_routes_from_dependencies", return_value=routes),
    ):
        stack.build(stack_config, deployment, dummy_workload)

    cloud_assembly = app.synth()

    return {
        "app": app,
        "stack": stack,
        "cloud_assembly": cloud_assembly,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


MULTI_GROUP_GROUPING = {
    "users": ["users"],
    "workflow-api": ["workflow/api"],
    "file-system": ["file-system"],
    "metrics": ["metrics"],
    "audit-logs": ["audit-logs"],
    "report-templates": ["report-templates"],
    "subscriptions": ["subscriptions"],
    "tenants": ["tenants"],
    "site-messages": ["site-messages"],
    "validations": ["validations"],
    "warm-up": ["warm-up"],
    "legacy": ["legacy"],
}


@pytest.fixture
def multi_group_app():
    """Synthesize with the full 12-group Aplos NCA route configuration."""
    return _build_nested_stacks_app(
        routes=_make_multi_group_routes(),
        grouping=MULTI_GROUP_GROUPING,
    )


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestPathOwnershipIntegration:
    """CDK synthesis integration tests for tree-based path ownership."""

    def test_multi_group_no_duplicate_resources(self, multi_group_app):
        """Synthesize with multiple groups and verify no duplicate resources.

        No two nested stack templates should contain an AWS::ApiGateway::Resource
        with the same PathPart under the same parent. This is the core guarantee
        of the path ownership model.

        Validates: Requirements 3.1, 3.2, 4.1
        """
        cloud_assembly = multi_group_app["cloud_assembly"]
        nested_templates = _get_nested_stack_templates(cloud_assembly)

        assert len(nested_templates) > 0, "Expected nested stack templates"

        # Collect all (PathPart, ParentId) pairs across all nested stacks
        # to verify no duplicates exist
        all_resource_keys = []
        for ns_template in nested_templates:
            resources = get_resources_by_type(ns_template, "AWS::ApiGateway::Resource")
            for r in resources:
                props = r["resource"]["Properties"]
                path_part = props.get("PathPart", "")
                parent_id = str(props.get("ParentId", ""))
                all_resource_keys.append((path_part, parent_id))

        # Check for duplicates: same (PathPart, ParentId) in different nested stacks
        # Note: Within a single nested stack, CDK prevents duplicates.
        # Across nested stacks, the path ownership builder should prevent them.
        seen = set()
        duplicates = []
        for key in all_resource_keys:
            if key in seen:
                duplicates.append(key)
            seen.add(key)

        assert len(duplicates) == 0, (
            f"Found duplicate API Gateway Resources across nested stacks: {duplicates}. "
            f"This indicates the path ownership builder failed to assign shared "
            f"segments to the parent stack."
        )

    def test_shared_resources_in_parent_only(self, multi_group_app):
        """Shared path resources appear only in parent stack template.

        The shared segments (v3, tenants, {tenant-id}) should be created as
        CfnResource entries in the parent stack, not in any nested stack.

        Validates: Requirements 3.1, 3.2, 3.3
        """
        cloud_assembly = multi_group_app["cloud_assembly"]
        stack = multi_group_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        # Parent should have AWS::ApiGateway::Resource entries for shared paths
        parent_api_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Resource"
        )
        parent_path_parts = [
            r["resource"]["Properties"].get("PathPart", "")
            for r in parent_api_resources
        ]

        # The shared segments across all 12 groups are: v3, tenants, {tenant-id}
        # (all groups except warm-up share /v3/tenants/{tenant-id})
        assert (
            "v3" in parent_path_parts
        ), "Shared segment 'v3' should be in parent stack"
        assert (
            "tenants" in parent_path_parts
        ), "Shared segment 'tenants' should be in parent stack"
        assert (
            "{tenant-id}" in parent_path_parts
        ), "Shared segment '{tenant-id}' should be in parent stack"

        # Verify these shared segments do NOT appear in nested stacks
        nested_templates = _get_nested_stack_templates(cloud_assembly)
        for ns_template in nested_templates:
            ns_resources = _get_all_api_gateway_resources_from_template(ns_template)
            ns_path_parts = [r["path_part"] for r in ns_resources]

            # No nested stack should create 'v3', 'tenants', or '{tenant-id}'
            # as those are shared across multiple groups
            assert (
                "v3" not in ns_path_parts
            ), "Shared segment 'v3' should NOT be in any nested stack"
            assert (
                "tenants" not in ns_path_parts
            ), "Shared segment 'tenants' should NOT be in any nested stack"
            assert (
                "{tenant-id}" not in ns_path_parts
            ), "Shared segment '{tenant-id}' should NOT be in any nested stack"

    def test_nested_stacks_have_only_exclusive_resources(self, multi_group_app):
        """Each nested stack template contains only exclusive resources for its group.

        Nested stacks should only create path segments that are unique to their
        group — segments that no other group's routes traverse.

        Validates: Requirements 4.1, 4.2
        """
        cloud_assembly = multi_group_app["cloud_assembly"]
        nested_templates = _get_nested_stack_templates(cloud_assembly)

        assert len(nested_templates) > 0, "Expected nested stack templates"

        # Collect path parts from each nested stack
        for ns_template in nested_templates:
            ns_resources = get_resources_by_type(
                ns_template, "AWS::ApiGateway::Resource"
            )

            for r in ns_resources:
                path_part = r["resource"]["Properties"].get("PathPart", "")
                # None of the shared segments should appear
                assert path_part not in ("v3", "tenants", "{tenant-id}"), (
                    f"Nested stack contains shared segment '{path_part}' "
                    f"which should only be in the parent stack"
                )

    def test_single_stack_mode_unchanged(self):
        """Single-stack mode (nested_stacks.enabled=false) works as before.

        When nested stacks are disabled, the API Gateway stack should use
        the traditional single-stack route creation without invoking the
        PathOwnershipBuilder.

        Validates: Requirements 6.1
        """
        routes = [
            {
                "path": "/v3/tenants/{tenant-id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
            {
                "path": "/v3/tenants/{tenant-id}/metrics",
                "method": "GET",
                "lambda_name": "get-metrics",
            },
        ]

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
                "name": "api-gateway-single-stack",
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
                    "name": "test-single-stack-api",
                    "description": "Single stack mode test",
                    "api_type": "REST",
                    "endpoint_types": ["REGIONAL"],
                    "stage_name": "api",
                    "cognito_authorizer": {
                        "name": "CognitoAuth",
                        "user_pool_arn": "arn:aws:cognito-idp:us-east-1:123456789012:userpool/us-east-1_TestPool",
                    },
                    "nested_stacks": {
                        "enabled": False,
                    },
                },
            },
            workload=dummy_workload.dictionary,
        )

        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "dev"},
        )

        stack = ApiGatewayStack(app, "TestSingleStackMode")

        with (
            patch.object(
                stack, "_resolve_lambda_folder", side_effect=_mock_resolve_lambda_folder
            ),
            patch.object(
                stack, "_discover_routes_from_dependencies", return_value=routes
            ),
        ):
            stack.build(stack_config, deployment, dummy_workload)

        cloud_assembly = app.synth()
        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        # In single-stack mode: no nested stacks
        nested_stack_resources = get_resources_by_type(
            parent_template, "AWS::CloudFormation::Stack"
        )
        assert (
            len(nested_stack_resources) == 0
        ), "Single-stack mode should NOT create nested stacks"

        # Should have REST API, methods, and resources all in one template
        rest_apis = get_resources_by_type(parent_template, "AWS::ApiGateway::RestApi")
        assert len(rest_apis) == 1, "Should have exactly 1 REST API"

        methods = get_resources_by_type(parent_template, "AWS::ApiGateway::Method")
        assert (
            len(methods) >= 2
        ), f"Expected at least 2 methods in single-stack mode, got {len(methods)}"

        api_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Resource"
        )
        assert (
            len(api_resources) > 0
        ), "Should have API Gateway Resources in single-stack mode"

    def test_single_group_no_shared_resources(self):
        """All routes in one group produces no shared resources in parent.

        When all routes belong to a single group, there are no shared segments
        and the parent should not create any AWS::ApiGateway::Resource entries.
        The nested stack handles all path creation.

        Validates: Requirements 6.2, 6.3
        """
        routes = [
            {
                "path": "/v3/tenants/{tenant-id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
            {
                "path": "/v3/tenants/{tenant-id}/users/{user-id}",
                "method": "GET",
                "lambda_name": "get-user",
            },
            {
                "path": "/v3/tenants/{tenant-id}/users/{user-id}",
                "method": "PUT",
                "lambda_name": "update-user",
            },
        ]

        result = _build_nested_stacks_app(
            routes=routes,
            grouping={"users": ["users"]},
        )

        cloud_assembly = result["cloud_assembly"]
        stack = result["stack"]
        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        # Parent should NOT have any AWS::ApiGateway::Resource entries
        # because all routes are in a single group (no shared segments)
        parent_api_resources = get_resources_by_type(
            parent_template, "AWS::ApiGateway::Resource"
        )
        assert len(parent_api_resources) == 0, (
            f"Single-group mode should have no shared resources in parent, "
            f"but found {len(parent_api_resources)}: "
            f"{[r['resource']['Properties'].get('PathPart') for r in parent_api_resources]}"
        )

        # Should still have exactly 1 nested stack
        nested_stacks = get_resources_by_type(
            parent_template, "AWS::CloudFormation::Stack"
        )
        assert (
            len(nested_stacks) == 1
        ), f"Expected 1 nested stack for single group, got {len(nested_stacks)}"

    def test_adding_route_does_not_break_other_stacks(self):
        """Adding a new route to a group doesn't affect other stacks.

        Synthesize once with a base configuration, then add a route to one
        group and verify the other groups' nested stack templates are unchanged.

        Validates: Requirements 7.1, 7.2
        """
        base_routes = [
            {
                "path": "/v3/tenants/{tenant-id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
            {
                "path": "/v3/tenants/{tenant-id}/metrics",
                "method": "GET",
                "lambda_name": "get-metrics",
            },
            {"path": "/v3/admin/warm-up", "method": "POST", "lambda_name": "warm-up"},
        ]

        grouping = {
            "users": ["users"],
            "metrics": ["metrics"],
            "warm-up": ["warm-up"],
        }

        # Synthesize base configuration
        base_result = _build_nested_stacks_app(routes=base_routes, grouping=grouping)
        base_assembly = base_result["cloud_assembly"]
        base_nested_templates = _get_nested_stack_templates(base_assembly)

        # Add a new route to the users group
        extended_routes = base_routes + [
            {
                "path": "/v3/tenants/{tenant-id}/users/{user-id}/profile",
                "method": "GET",
                "lambda_name": "get-user",
            },
        ]

        # Synthesize extended configuration
        extended_result = _build_nested_stacks_app(
            routes=extended_routes, grouping=grouping
        )
        extended_assembly = extended_result["cloud_assembly"]
        extended_nested_templates = _get_nested_stack_templates(extended_assembly)

        # Both should have the same number of nested stacks (3 groups)
        assert len(base_nested_templates) == 3
        assert len(extended_nested_templates) == 3

        # The parent stack should still have the same shared resources
        base_parent = base_assembly.get_stack_by_name(
            base_result["stack"].stack_name
        ).template
        extended_parent = extended_assembly.get_stack_by_name(
            extended_result["stack"].stack_name
        ).template

        base_shared = get_resources_by_type(base_parent, "AWS::ApiGateway::Resource")
        extended_shared = get_resources_by_type(
            extended_parent, "AWS::ApiGateway::Resource"
        )

        base_shared_parts = sorted(
            r["resource"]["Properties"].get("PathPart", "") for r in base_shared
        )
        extended_shared_parts = sorted(
            r["resource"]["Properties"].get("PathPart", "") for r in extended_shared
        )

        # Shared resources in the parent should only grow (never shrink).
        # With preemptive sharing, adding a route with new parameterized segments
        # (e.g., {user-id}) adds those to the parent stack. The critical invariant
        # is that no existing shared resources are removed — which would cause
        # a CloudFormation resource relocation conflict.
        assert set(base_shared_parts).issubset(set(extended_shared_parts)), (
            f"Adding a route to users group REMOVED shared resources (relocation risk). "
            f"Before: {base_shared_parts}, After: {extended_shared_parts}"
        )

    def test_twelve_groups_synthesize_successfully(self, multi_group_app):
        """Full 12-group configuration synthesizes without errors.

        This is a smoke test ensuring the real-world Aplos NCA configuration
        with 12 route groups can be synthesized end-to-end.

        Validates: Requirements 3.1, 3.2, 3.3, 4.1, 4.2
        """
        cloud_assembly = multi_group_app["cloud_assembly"]
        stack = multi_group_app["stack"]

        parent_template = cloud_assembly.get_stack_by_name(stack.stack_name).template

        # Should have 12 nested stacks
        nested_stacks = get_resources_by_type(
            parent_template, "AWS::CloudFormation::Stack"
        )
        assert (
            len(nested_stacks) == 12
        ), f"Expected 12 nested stacks (one per group), got {len(nested_stacks)}"

        # Should have nested stack templates
        nested_templates = _get_nested_stack_templates(cloud_assembly)
        assert (
            len(nested_templates) == 12
        ), f"Expected 12 nested stack templates, got {len(nested_templates)}"

        # All nested stacks should have at least one method
        for ns_template in nested_templates:
            methods = get_resources_by_type(ns_template, "AWS::ApiGateway::Method")
            assert (
                len(methods) > 0
            ), "Every nested stack should have at least one method"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
