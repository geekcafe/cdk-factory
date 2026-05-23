"""
Unit tests for API Gateway _validate_resource_limits() method.

Tests the validation logic that checks route groups against resource limits:
1. Warning emitted when a group exceeds the configurable max_resources_per_stack threshold
2. Synthesis fails (ValueError) when a group exceeds 500 resources (hard CloudFormation limit)
3. Synthesis fails (ValueError) when nested stack count exceeds 20
"""

import pytest
from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestValidateResourceLimits:
    """Test suite for _validate_resource_limits() method."""

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
                        "grouping": {"users": ["users"]},
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

    def test_passes_when_groups_within_limits(self, api_gateway_stack):
        """Verify no error or warning when groups are within all limits."""
        route_groups = {
            "users": [
                {
                    "path": "/v3/tenants/{id}/users",
                    "method": "GET",
                    "lambda_name": "get-users",
                },
                {
                    "path": "/v3/tenants/{id}/users/{uid}",
                    "method": "GET",
                    "lambda_name": "get-user",
                },
            ],
        }

        # Should not raise
        api_gateway_stack._validate_resource_limits(route_groups)

    def test_fails_when_nested_stack_count_exceeds_20(self, api_gateway_stack):
        """Verify synthesis fails when more than 20 route groups exist."""
        # Create 21 groups with one route each
        route_groups = {
            f"group-{i}": [
                {
                    "path": f"/api/resource-{i}",
                    "method": "GET",
                    "lambda_name": f"lambda-{i}",
                }
            ]
            for i in range(21)
        }

        with pytest.raises(ValueError) as exc_info:
            api_gateway_stack._validate_resource_limits(route_groups)

        assert "Nested stack count (21) exceeds maximum of 20" in str(exc_info.value)
        assert "Consolidate route groups" in str(exc_info.value)

    def test_passes_with_exactly_20_groups(self, api_gateway_stack):
        """Verify 20 groups (the maximum) does not raise."""
        route_groups = {
            f"group-{i}": [
                {
                    "path": f"/api/resource-{i}",
                    "method": "GET",
                    "lambda_name": f"lambda-{i}",
                }
            ]
            for i in range(20)
        }

        # Should not raise
        api_gateway_stack._validate_resource_limits(route_groups)

    def test_fails_when_group_exceeds_500_resources(self, api_gateway_stack):
        """Verify synthesis fails when a group would produce more than 500 resources."""
        # Create a group with enough routes to exceed 500 resources
        # Each route produces ~3 resources + unique path segments
        # 170 routes with unique paths: 170*3 = 510 + path segments > 500
        routes = [
            {
                "path": f"/api/v1/resource-{i}",
                "method": "GET",
                "lambda_name": f"lambda-{i}",
            }
            for i in range(170)
        ]

        route_groups = {"oversized-group": routes}

        with pytest.raises(ValueError) as exc_info:
            api_gateway_stack._validate_resource_limits(route_groups)

        assert "oversized-group" in str(exc_info.value)
        assert "exceeding the CloudFormation limit of 500" in str(exc_info.value)
        assert "Split this group" in str(exc_info.value)

    def test_emits_warning_when_group_exceeds_threshold(
        self, api_gateway_stack, capsys
    ):
        """Verify warning is printed when a group exceeds max_resources_per_stack."""
        # With max_resources_per_stack=200, create enough routes to exceed it
        # 60 routes with unique paths: 60*3 = 180 + path segments > 200
        routes = [
            {
                "path": f"/api/v1/resource-{i}",
                "method": "GET",
                "lambda_name": f"lambda-{i}",
            }
            for i in range(60)
        ]

        route_groups = {"large-group": routes}

        # Should not raise (under 500) but should print warning
        api_gateway_stack._validate_resource_limits(route_groups)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "large-group" in captured.out
        assert "exceeding the configured limit of 200" in captured.out
        assert "Consider splitting this group" in captured.out

    def test_no_warning_when_group_within_threshold(self, api_gateway_stack, capsys):
        """Verify no warning when group is within max_resources_per_stack."""
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
        ]

        route_groups = {"users": routes}

        api_gateway_stack._validate_resource_limits(route_groups)

        captured = capsys.readouterr()
        assert "WARNING" not in captured.out

    def test_resource_estimation_accounts_for_shared_path_segments(
        self, api_gateway_stack, capsys
    ):
        """Verify resource estimation includes unique path segments."""
        # Routes sharing path segments should have fewer unique paths
        # than routes with completely different paths
        routes_shared = [
            {"path": "/api/v1/users", "method": "GET", "lambda_name": "list-users"},
            {"path": "/api/v1/users/{id}", "method": "GET", "lambda_name": "get-user"},
            {
                "path": "/api/v1/users/{id}",
                "method": "PUT",
                "lambda_name": "update-user",
            },
        ]
        # Shared paths: api, api/v1, api/v1/users, api/v1/users/{id} = 4 unique segments
        # Resources: 3 routes * 3 = 9 + 4 segments = 13

        route_groups = {"users": routes_shared}

        # Should not raise or warn with default 200 limit
        api_gateway_stack._validate_resource_limits(route_groups)

        captured = capsys.readouterr()
        assert "WARNING" not in captured.out

    def test_custom_max_resources_per_stack_threshold(self):
        """Verify custom max_resources_per_stack value is respected."""
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
                        "max_resources_per_stack": 10,  # Very low threshold
                        "grouping": {"users": ["users"]},
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

        # 3 routes: 3*3 = 9 + path segments > 10
        routes = [
            {"path": "/api/users", "method": "GET", "lambda_name": "list-users"},
            {"path": "/api/users/{id}", "method": "GET", "lambda_name": "get-user"},
            {"path": "/api/users/{id}", "method": "PUT", "lambda_name": "update-user"},
        ]

        route_groups = {"users": routes}

        # Should warn but not raise (under 500)
        import io
        import sys

        captured_output = io.StringIO()
        sys.stdout = captured_output
        try:
            stack._validate_resource_limits(route_groups)
        finally:
            sys.stdout = sys.__stdout__

        output = captured_output.getvalue()
        assert "WARNING" in output
        assert "exceeding the configured limit of 10" in output

    def test_multiple_groups_validated_independently(self, api_gateway_stack, capsys):
        """Verify each group is validated independently."""
        # One small group (within limits) and one that exceeds threshold
        route_groups = {
            "small-group": [
                {"path": "/api/health", "method": "GET", "lambda_name": "health"},
            ],
            "large-group": [
                {
                    "path": f"/api/v1/resource-{i}",
                    "method": "GET",
                    "lambda_name": f"lambda-{i}",
                }
                for i in range(60)
            ],
        }

        api_gateway_stack._validate_resource_limits(route_groups)

        captured = capsys.readouterr()
        assert "large-group" in captured.out
        assert "small-group" not in captured.out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
