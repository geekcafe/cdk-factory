"""
Unit tests for API Gateway _compute_deployment_hash() method.

Tests the deterministic hash computation used to force new API Gateway
deployments when routes change:
1. Same route_groups input produces the same hash (deterministic)
2. Adding a route to a group changes the hash
3. Removing a route from a group changes the hash
4. Reordering routes within a group does NOT change the hash (sorted internally)
5. Reordering groups does NOT change the hash (sorted internally)
6. Adding a new group changes the hash
7. Removing a group changes the hash
8. Hash is exactly 16 characters long
"""

import pytest
from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


class TestComputeDeploymentHash:
    """Test suite for _compute_deployment_hash() method."""

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

    @pytest.fixture
    def base_route_groups(self):
        """Provide a standard route_groups dict for reuse across tests."""
        return {
            "users": [
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
            ],
            "workflow": [
                {
                    "path": "/v3/tenants/{id}/executions",
                    "method": "POST",
                    "lambda_name": "create-execution",
                },
            ],
        }

    def test_same_input_produces_same_hash(self, api_gateway_stack, base_route_groups):
        """Verify deterministic output: same input always produces same hash."""
        hash1 = api_gateway_stack._compute_deployment_hash(base_route_groups)
        hash2 = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert hash1 == hash2

    def test_hash_is_16_characters(self, api_gateway_stack, base_route_groups):
        """Verify hash output is exactly 16 hex characters."""
        result = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert len(result) == 16
        # Verify it's valid hex
        int(result, 16)

    def test_adding_route_changes_hash(self, api_gateway_stack, base_route_groups):
        """Verify adding a route to an existing group changes the hash."""
        hash_before = api_gateway_stack._compute_deployment_hash(base_route_groups)

        # Add a new route to the users group
        base_route_groups["users"].append(
            {
                "path": "/v3/tenants/{id}/users/{uid}",
                "method": "DELETE",
                "lambda_name": "delete-user",
            }
        )
        hash_after = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert hash_before != hash_after

    def test_removing_route_changes_hash(self, api_gateway_stack, base_route_groups):
        """Verify removing a route from a group changes the hash."""
        hash_before = api_gateway_stack._compute_deployment_hash(base_route_groups)

        # Remove the last route from users group
        base_route_groups["users"].pop()
        hash_after = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert hash_before != hash_after

    def test_reordering_routes_within_group_does_not_change_hash(
        self, api_gateway_stack
    ):
        """Verify reordering routes within a group produces the same hash (sorted internally)."""
        routes_order_a = {
            "users": [
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
                    "path": "/v3/tenants/{id}/users/{uid}",
                    "method": "DELETE",
                    "lambda_name": "delete-user",
                },
            ],
        }

        routes_order_b = {
            "users": [
                {
                    "path": "/v3/tenants/{id}/users/{uid}",
                    "method": "DELETE",
                    "lambda_name": "delete-user",
                },
                {
                    "path": "/v3/tenants/{id}/users/{uid}",
                    "method": "PUT",
                    "lambda_name": "update-user",
                },
                {
                    "path": "/v3/tenants/{id}/users",
                    "method": "GET",
                    "lambda_name": "get-users",
                },
            ],
        }

        hash_a = api_gateway_stack._compute_deployment_hash(routes_order_a)
        hash_b = api_gateway_stack._compute_deployment_hash(routes_order_b)

        assert hash_a == hash_b

    def test_reordering_groups_does_not_change_hash(self, api_gateway_stack):
        """Verify reordering groups produces the same hash (sorted internally)."""
        # Python dicts maintain insertion order, so we create two dicts
        # with different insertion orders
        groups_order_a = {
            "users": [
                {
                    "path": "/v3/tenants/{id}/users",
                    "method": "GET",
                    "lambda_name": "get-users",
                },
            ],
            "workflow": [
                {
                    "path": "/v3/tenants/{id}/executions",
                    "method": "POST",
                    "lambda_name": "create-execution",
                },
            ],
            "metrics": [
                {
                    "path": "/v3/tenants/{id}/metrics",
                    "method": "GET",
                    "lambda_name": "get-metrics",
                },
            ],
        }

        groups_order_b = {
            "metrics": [
                {
                    "path": "/v3/tenants/{id}/metrics",
                    "method": "GET",
                    "lambda_name": "get-metrics",
                },
            ],
            "users": [
                {
                    "path": "/v3/tenants/{id}/users",
                    "method": "GET",
                    "lambda_name": "get-users",
                },
            ],
            "workflow": [
                {
                    "path": "/v3/tenants/{id}/executions",
                    "method": "POST",
                    "lambda_name": "create-execution",
                },
            ],
        }

        hash_a = api_gateway_stack._compute_deployment_hash(groups_order_a)
        hash_b = api_gateway_stack._compute_deployment_hash(groups_order_b)

        assert hash_a == hash_b

    def test_adding_new_group_changes_hash(self, api_gateway_stack, base_route_groups):
        """Verify adding a new group changes the hash."""
        hash_before = api_gateway_stack._compute_deployment_hash(base_route_groups)

        # Add a new group
        base_route_groups["metrics"] = [
            {
                "path": "/v3/tenants/{id}/metrics",
                "method": "GET",
                "lambda_name": "get-metrics",
            },
        ]
        hash_after = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert hash_before != hash_after

    def test_removing_group_changes_hash(self, api_gateway_stack, base_route_groups):
        """Verify removing a group changes the hash."""
        hash_before = api_gateway_stack._compute_deployment_hash(base_route_groups)

        # Remove the workflow group
        del base_route_groups["workflow"]
        hash_after = api_gateway_stack._compute_deployment_hash(base_route_groups)

        assert hash_before != hash_after


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
