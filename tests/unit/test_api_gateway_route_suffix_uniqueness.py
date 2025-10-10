"""
Unit tests for API Gateway route suffix generation.

Tests the fix for duplicate construct IDs when multiple routes share the same path
but have different HTTP methods (e.g., GET/PUT/DELETE on /app/messages/{id}).

The _get_route_suffix() method should:
1. Use the 'name' field if provided (preferred)
2. Fall back to '{method}-{path}' for uniqueness if no name is provided
"""

import pytest
from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestApiGatewayRouteSuffixUniqueness:
    """Test suite for route suffix generation and uniqueness."""

    @pytest.fixture
    def api_gateway_stack(self):
        """Create a minimal API Gateway stack for testing."""
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
                    "description": "Test API Gateway",
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
        return stack

    def test_route_suffix_uses_name_field_when_provided(self, api_gateway_stack):
        """Test that route suffix uses the 'name' field when provided."""
        route = {
            "path": "/app/messages/{id}",
            "method": "PUT",
            "name": "my-custom-update-handler"
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        assert suffix == "my-custom-update-handler"

    def test_route_suffix_includes_method_when_no_name_provided(self, api_gateway_stack):
        """Test that route suffix includes HTTP method when no name field."""
        route = {
            "path": "/app/messages/{id}",
            "method": "GET"
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        assert suffix == "get-app-messages-{id}"

    def test_route_suffix_uniqueness_for_same_path_different_methods(self, api_gateway_stack):
        """Test that multiple routes with same path but different methods get unique suffixes."""
        routes = [
            {"path": "/app/messages/{id}", "method": "GET"},
            {"path": "/app/messages/{id}", "method": "PUT"},
            {"path": "/app/messages/{id}", "method": "DELETE"},
        ]
        
        suffixes = [api_gateway_stack._get_route_suffix(route) for route in routes]
        
        # All suffixes should be unique
        assert len(suffixes) == len(set(suffixes))
        assert suffixes == [
            "get-app-messages-{id}",
            "put-app-messages-{id}",
            "delete-app-messages-{id}",
        ]

    def test_route_suffix_handles_root_path(self, api_gateway_stack):
        """Test that root path is handled correctly."""
        route = {
            "path": "/",
            "method": "GET"
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        assert suffix == "get-health"  # Falls back to "health" for empty path

    def test_route_suffix_normalizes_path_slashes(self, api_gateway_stack):
        """Test that leading/trailing slashes are handled correctly."""
        routes = [
            {"path": "/app/messages", "method": "POST"},
            {"path": "app/messages", "method": "GET"},  # No leading slash
        ]
        
        suffixes = [api_gateway_stack._get_route_suffix(route) for route in routes]
        
        assert suffixes[0] == "post-app-messages"
        assert suffixes[1] == "get-app-messages"

    def test_route_suffix_handles_nested_paths(self, api_gateway_stack):
        """Test that deeply nested paths are converted correctly."""
        route = {
            "path": "/api/v1/users/{userId}/messages/{messageId}",
            "method": "PATCH"
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        assert suffix == "patch-api-v1-users-{userId}-messages-{messageId}"

    def test_route_suffix_name_takes_precedence_over_method_path(self, api_gateway_stack):
        """Test that 'name' field takes precedence even with method+path fallback available."""
        route = {
            "path": "/app/messages/{id}",
            "method": "PUT",
            "name": "geekcafe-prod-update-app-message"
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        # Should use name, not method-path
        assert suffix == "geekcafe-prod-update-app-message"
        assert suffix != "put-app-messages-{id}"

    def test_route_suffix_handles_different_http_methods(self, api_gateway_stack):
        """Test that all standard HTTP methods are handled correctly."""
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]
        path = "/api/resource"
        
        suffixes = []
        for method in methods:
            route = {"path": path, "method": method}
            suffix = api_gateway_stack._get_route_suffix(route)
            suffixes.append(suffix)
        
        # All should be unique and lowercase method
        assert len(suffixes) == len(set(suffixes))
        for method, suffix in zip(methods, suffixes):
            assert suffix.startswith(method.lower() + "-")

    def test_route_suffix_empty_name_falls_back_to_method_path(self, api_gateway_stack):
        """Test that empty string name is treated as no name."""
        route = {
            "path": "/app/messages",
            "method": "POST",
            "name": ""  # Empty name should be ignored
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        # Should fall back to method-path pattern
        assert suffix == "post-app-messages"

    def test_route_suffix_none_name_falls_back_to_method_path(self, api_gateway_stack):
        """Test that None name is treated as no name."""
        route = {
            "path": "/app/messages",
            "method": "POST",
            "name": None  # None should be ignored
        }
        
        suffix = api_gateway_stack._get_route_suffix(route)
        
        # Should fall back to method-path pattern
        assert suffix == "post-app-messages"

    def test_real_world_geekcafe_scenario(self, api_gateway_stack):
        """
        Test the exact scenario from geek-cafe-lambdas that caused the bug.
        Multiple CRUD operations on /app/messages/{id} with name fields.
        """
        routes = [
            {
                "path": "/app/messages/{id}",
                "method": "PUT",
                "name": "geekcafe-prod-update-app-message",
            },
            {
                "path": "/app/messages/{id}",
                "method": "DELETE",
                "name": "geekcafe-prod-delete-app-message",
            },
            {
                "path": "/app/messages/{id}",
                "method": "GET",
                "name": "geekcafe-prod-get-app-message",
            },
            {
                "path": "/app/messages",
                "method": "GET",
                "name": "geekcafe-prod-list-app-messages",
            },
        ]
        
        suffixes = [api_gateway_stack._get_route_suffix(route) for route in routes]
        
        # All suffixes should be unique
        assert len(suffixes) == len(set(suffixes))
        
        # Should use the provided names
        assert suffixes == [
            "geekcafe-prod-update-app-message",
            "geekcafe-prod-delete-app-message",
            "geekcafe-prod-get-app-message",
            "geekcafe-prod-list-app-messages",
        ]

    def test_real_world_geekcafe_scenario_without_names(self, api_gateway_stack):
        """
        Test the same scenario but without 'name' fields.
        Should generate unique suffixes using method+path.
        """
        routes = [
            {"path": "/app/messages/{id}", "method": "PUT"},
            {"path": "/app/messages/{id}", "method": "DELETE"},
            {"path": "/app/messages/{id}", "method": "GET"},
            {"path": "/app/messages", "method": "GET"},
        ]
        
        suffixes = [api_gateway_stack._get_route_suffix(route) for route in routes]
        
        # All suffixes should be unique
        assert len(suffixes) == len(set(suffixes))
        
        # Should use method-path pattern
        assert suffixes == [
            "put-app-messages-{id}",
            "delete-app-messages-{id}",
            "get-app-messages-{id}",
            "get-app-messages",
        ]
        
        # Verify no duplicate construct IDs would be created
        construct_ids = [f"test-api-imported-lambda-{suffix}" for suffix in suffixes]
        assert len(construct_ids) == len(set(construct_ids))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
