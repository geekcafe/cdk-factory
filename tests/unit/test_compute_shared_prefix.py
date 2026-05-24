"""
Unit tests for ApiGatewayStack._compute_shared_prefix()

Tests the computation of the longest common path prefix across all routes.
This method is used to identify shared path segments that should be created
once in the parent stack rather than duplicated across nested stacks.

Validates: Requirements 2.1
"""

import pytest
from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


@pytest.fixture
def api_gateway_stack():
    """Create a minimal ApiGatewayStack instance for testing _compute_shared_prefix."""
    app = App()
    dummy_workload = WorkloadConfig(
        {
            "workload": {"name": "test-workload", "devops": {"name": "test-devops"}},
        }
    )
    stack_config = StackConfig(
        {
            "api_gateway": {
                "name": "TestApi",
                "description": "Test API",
            }
        },
        workload=dummy_workload.dictionary,
    )
    deployment = DeploymentConfig(
        workload=dummy_workload.dictionary,
        deployment={"name": "test-deployment", "environment": "test"},
    )
    stack = ApiGatewayStack(app, "TestStack")
    stack.build(stack_config, deployment, dummy_workload)
    return stack


class TestComputeSharedPrefix:
    """Tests for _compute_shared_prefix method."""

    def test_empty_routes_returns_empty_prefix(self, api_gateway_stack):
        """Empty route set returns empty prefix."""
        result = api_gateway_stack._compute_shared_prefix([])
        assert result == []

    def test_single_route_returns_full_path_as_prefix(self, api_gateway_stack):
        """Single route returns its full path segments as the prefix."""
        routes = [{"path": "/v3/tenants/{tenant-id}/users"}]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}", "users"]

    def test_two_routes_with_shared_prefix(self, api_gateway_stack):
        """Two routes sharing /v3/tenants/{tenant-id} return that as prefix."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users"},
            {"path": "/v3/tenants/{tenant-id}/metrics"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}"]

    def test_routes_with_no_common_prefix(self, api_gateway_stack):
        """Routes with no common prefix return empty list."""
        routes = [
            {"path": "/health"},
            {"path": "/v3/tenants/{tenant-id}/users"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == []

    def test_routes_with_partial_common_prefix(self, api_gateway_stack):
        """Routes sharing only the first segment return that segment."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users"},
            {"path": "/v3/health"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3"]

    def test_multiple_routes_all_sharing_prefix(self, api_gateway_stack):
        """Multiple routes all sharing the same prefix."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users"},
            {"path": "/v3/tenants/{tenant-id}/metrics"},
            {"path": "/v3/tenants/{tenant-id}/workflow"},
            {"path": "/v3/tenants/{tenant-id}/audit-logs"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}"]

    def test_parameterized_segments_treated_as_regular(self, api_gateway_stack):
        """Parameterized segments like {tenant-id} are treated as regular segments."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users/{user-id}/files"},
            {"path": "/v3/tenants/{tenant-id}/users/{user-id}/settings"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}", "users", "{user-id}"]

    def test_routes_with_different_depths(self, api_gateway_stack):
        """Routes with different path depths compute prefix up to shortest."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users/{user-id}/files"},
            {"path": "/v3/tenants/{tenant-id}/metrics"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}"]

    def test_routes_with_leading_trailing_slashes(self, api_gateway_stack):
        """Leading and trailing slashes are handled correctly."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users/"},
            {"path": "/v3/tenants/{tenant-id}/metrics"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}"]

    def test_route_with_empty_path(self, api_gateway_stack):
        """Route with empty path results in empty prefix."""
        routes = [
            {"path": ""},
            {"path": "/v3/tenants/{tenant-id}/users"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == []

    def test_route_missing_path_key(self, api_gateway_stack):
        """Route dict missing 'path' key is treated as empty path."""
        routes = [
            {"method": "GET"},
            {"path": "/v3/tenants/{tenant-id}/users"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == []

    def test_identical_routes_return_full_path(self, api_gateway_stack):
        """Identical routes return the full path as prefix."""
        routes = [
            {"path": "/v3/tenants/{tenant-id}/users"},
            {"path": "/v3/tenants/{tenant-id}/users"},
        ]
        result = api_gateway_stack._compute_shared_prefix(routes)
        assert result == ["v3", "tenants", "{tenant-id}", "users"]
