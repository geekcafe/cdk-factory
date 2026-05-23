"""
Unit tests for API Gateway _group_routes() method.

Tests the route grouping logic that assigns routes to domain-aligned groups
based on their Lambda resource folder path:
1. Routes are assigned to correct groups based on folder path matching
2. Unmatched routes (folder not in grouping config) go to "default" group
3. Multiple folders mapped to same group name are merged into one group
4. Empty groups are not present in the result
5. Longest prefix match: route in nested path matches parent group when exact match fails

Requirements: 1.1, 1.2, 1.4, 1.5, 1.7
"""

import pytest
from unittest.mock import patch
from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestGroupRoutes:
    """Test suite for _group_routes() method."""

    @pytest.fixture
    def api_gateway_stack(self):
        """Create a minimal API Gateway stack for testing."""
        app = App()
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "api_gateway": {
                    "name": "TestApi",
                    "description": "Test API Gateway",
                    "nested_stacks": {
                        "enabled": True,
                        "max_resources_per_stack": 200,
                        "grouping": {
                            "users": ["users"],
                            "workflow-api": ["workflow/api"],
                            "workflow-app": ["workflow/app"],
                            "file-system": ["file-system"],
                            "metrics": ["metrics"],
                        },
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )
        return stack

    def test_routes_assigned_to_correct_groups(self, api_gateway_stack):
        """Verify routes are assigned to the correct group based on folder path."""
        routes = [
            {
                "path": "/v3/tenants/{id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
            {
                "path": "/v3/tenants/{id}/users/{uid}",
                "method": "PUT",
                "lambda_name": "update-user",
            },
            {
                "path": "/v3/tenants/{id}/executions",
                "method": "GET",
                "lambda_name": "get-executions",
            },
            {
                "path": "/v3/tenants/{id}/files",
                "method": "GET",
                "lambda_name": "get-files",
            },
        ]

        # Mock _resolve_lambda_folder to return known folder paths
        def mock_resolve(lambda_name):
            folder_map = {
                "get-users": "users",
                "update-user": "users",
                "get-executions": "workflow/api",
                "get-files": "file-system",
            }
            return folder_map.get(lambda_name, "")

        with patch.object(
            api_gateway_stack, "_resolve_lambda_folder", side_effect=mock_resolve
        ):
            result = api_gateway_stack._group_routes(routes)

        assert "users" in result
        assert len(result["users"]) == 2
        assert "workflow-api" in result
        assert len(result["workflow-api"]) == 1
        assert "file-system" in result
        assert len(result["file-system"]) == 1

    def test_unmatched_routes_go_to_default_group(self, api_gateway_stack):
        """Verify routes whose folder path doesn't match any grouping go to 'default'."""
        routes = [
            {
                "path": "/v3/tenants/{id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
            {"path": "/v3/health", "method": "GET", "lambda_name": "health-check"},
            {"path": "/v3/unknown", "method": "GET", "lambda_name": "unknown-lambda"},
        ]

        def mock_resolve(lambda_name):
            folder_map = {
                "get-users": "users",
                "health-check": "monitoring",  # Not in grouping config
                "unknown-lambda": "some/random/path",  # Not in grouping config
            }
            return folder_map.get(lambda_name, "")

        with patch.object(
            api_gateway_stack, "_resolve_lambda_folder", side_effect=mock_resolve
        ):
            result = api_gateway_stack._group_routes(routes)

        assert "users" in result
        assert len(result["users"]) == 1
        assert "default" in result
        assert len(result["default"]) == 2
        # Verify the correct routes ended up in default
        default_lambda_names = [r["lambda_name"] for r in result["default"]]
        assert "health-check" in default_lambda_names
        assert "unknown-lambda" in default_lambda_names

    def test_multiple_folders_mapped_to_same_group_are_merged(self):
        """Verify routes from multiple folders mapped to the same group are merged."""
        app = App()
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        # Configure two folders mapped to the same group name
        stack_config = StackConfig(
            {
                "api_gateway": {
                    "name": "TestApi",
                    "nested_stacks": {
                        "enabled": True,
                        "max_resources_per_stack": 200,
                        "grouping": {
                            "workflow": ["workflow/api", "workflow/app"],
                            "users": ["users"],
                        },
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        routes = [
            {
                "path": "/v3/executions",
                "method": "GET",
                "lambda_name": "get-executions",
            },
            {
                "path": "/v3/workflow/start",
                "method": "POST",
                "lambda_name": "start-workflow",
            },
            {"path": "/v3/users", "method": "GET", "lambda_name": "get-users"},
        ]

        def mock_resolve(lambda_name):
            folder_map = {
                "get-executions": "workflow/api",
                "start-workflow": "workflow/app",
                "get-users": "users",
            }
            return folder_map.get(lambda_name, "")

        with patch.object(stack, "_resolve_lambda_folder", side_effect=mock_resolve):
            result = stack._group_routes(routes)

        # Both workflow/api and workflow/app routes should be in the "workflow" group
        assert "workflow" in result
        assert len(result["workflow"]) == 2
        workflow_lambda_names = [r["lambda_name"] for r in result["workflow"]]
        assert "get-executions" in workflow_lambda_names
        assert "start-workflow" in workflow_lambda_names

        # Users should be separate
        assert "users" in result
        assert len(result["users"]) == 1

    def test_empty_groups_are_skipped(self, api_gateway_stack):
        """Verify groups with no matching routes are not present in the result."""
        routes = [
            {
                "path": "/v3/tenants/{id}/users",
                "method": "GET",
                "lambda_name": "get-users",
            },
        ]

        def mock_resolve(lambda_name):
            folder_map = {
                "get-users": "users",
            }
            return folder_map.get(lambda_name, "")

        with patch.object(
            api_gateway_stack, "_resolve_lambda_folder", side_effect=mock_resolve
        ):
            result = api_gateway_stack._group_routes(routes)

        # Only "users" should be in the result; other configured groups
        # (workflow-api, workflow-app, file-system, metrics) should not appear
        assert "users" in result
        assert "workflow-api" not in result
        assert "workflow-app" not in result
        assert "file-system" not in result
        assert "metrics" not in result

    def test_longest_prefix_match_behavior(self, api_gateway_stack):
        """Verify routes in nested paths match parent group via longest prefix match."""
        routes = [
            {
                "path": "/v3/executions/v2",
                "method": "GET",
                "lambda_name": "get-executions-v2",
            },
            {
                "path": "/v3/executions",
                "method": "GET",
                "lambda_name": "get-executions",
            },
            {"path": "/v3/users", "method": "GET", "lambda_name": "get-users"},
        ]

        def mock_resolve(lambda_name):
            folder_map = {
                # This lambda is in a subfolder of workflow/api that isn't explicitly configured
                "get-executions-v2": "workflow/api/v2",
                # This lambda is in the exact configured folder
                "get-executions": "workflow/api",
                "get-users": "users",
            }
            return folder_map.get(lambda_name, "")

        with patch.object(
            api_gateway_stack, "_resolve_lambda_folder", side_effect=mock_resolve
        ):
            result = api_gateway_stack._group_routes(routes)

        # "workflow/api/v2" should match "workflow/api" group via longest prefix match
        assert "workflow-api" in result
        assert len(result["workflow-api"]) == 2
        workflow_lambda_names = [r["lambda_name"] for r in result["workflow-api"]]
        assert "get-executions-v2" in workflow_lambda_names
        assert "get-executions" in workflow_lambda_names

        assert "users" in result
        assert len(result["users"]) == 1

    def test_empty_folder_path_goes_to_default(self, api_gateway_stack):
        """Verify routes with empty folder path (unresolvable lambda) go to default."""
        routes = [
            {"path": "/v3/unknown", "method": "GET", "lambda_name": "mystery-lambda"},
        ]

        def mock_resolve(lambda_name):
            # Returns empty string for unresolvable lambdas
            return ""

        with patch.object(
            api_gateway_stack, "_resolve_lambda_folder", side_effect=mock_resolve
        ):
            result = api_gateway_stack._group_routes(routes)

        assert "default" in result
        assert len(result["default"]) == 1
        assert result["default"][0]["lambda_name"] == "mystery-lambda"

    def test_exact_match_takes_priority_over_prefix(self):
        """Verify exact folder match is used before falling back to prefix matching."""
        app = App()
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        # Configure both "workflow" and "workflow/api" as separate groups
        stack_config = StackConfig(
            {
                "api_gateway": {
                    "name": "TestApi",
                    "nested_stacks": {
                        "enabled": True,
                        "max_resources_per_stack": 200,
                        "grouping": {
                            "workflow-general": ["workflow"],
                            "workflow-api": ["workflow/api"],
                        },
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        routes = [
            {
                "path": "/v3/workflow/exec",
                "method": "GET",
                "lambda_name": "workflow-exec",
            },
            {
                "path": "/v3/workflow/api/list",
                "method": "GET",
                "lambda_name": "api-list",
            },
        ]

        def mock_resolve(lambda_name):
            folder_map = {
                "workflow-exec": "workflow",  # Exact match to "workflow"
                "api-list": "workflow/api",  # Exact match to "workflow/api"
            }
            return folder_map.get(lambda_name, "")

        with patch.object(stack, "_resolve_lambda_folder", side_effect=mock_resolve):
            result = stack._group_routes(routes)

        # Each route should go to its exact match group
        assert "workflow-general" in result
        assert len(result["workflow-general"]) == 1
        assert result["workflow-general"][0]["lambda_name"] == "workflow-exec"

        assert "workflow-api" in result
        assert len(result["workflow-api"]) == 1
        assert result["workflow-api"][0]["lambda_name"] == "api-list"

    def test_deeply_nested_path_matches_closest_ancestor(self):
        """Verify deeply nested paths match the closest configured ancestor group."""
        app = App()
        dummy_workload = WorkloadConfig(
            {
                "workload": {
                    "name": "test-workload",
                    "devops": {"name": "test-devops"},
                },
            }
        )
        stack_config = StackConfig(
            {
                "api_gateway": {
                    "name": "TestApi",
                    "nested_stacks": {
                        "enabled": True,
                        "max_resources_per_stack": 200,
                        "grouping": {
                            "workflow-general": ["workflow"],
                            "workflow-api": ["workflow/api"],
                        },
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestApiGatewayStack")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        routes = [
            {"path": "/v3/deep", "method": "GET", "lambda_name": "deep-lambda"},
        ]

        def mock_resolve(lambda_name):
            # Lambda is in workflow/api/v2/internal — should match "workflow/api" (closest ancestor)
            return "workflow/api/v2/internal"

        with patch.object(stack, "_resolve_lambda_folder", side_effect=mock_resolve):
            result = stack._group_routes(routes)

        # Should match "workflow/api" (longest prefix), not "workflow"
        assert "workflow-api" in result
        assert len(result["workflow-api"]) == 1
        assert "workflow-general" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
