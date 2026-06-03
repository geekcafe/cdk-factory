"""
Bug Condition Exploration Test — Placeholder Cache Keys Cause Lookup Misses

Property 1: Bug Condition - Placeholder Cache Keys Cause Lookup Misses

This test demonstrates that _build_lambda_folder_cache() stores raw unresolved
placeholder names from disk (e.g., "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler")
while _discover_routes_from_dependencies() provides fully resolved names
(e.g., "asset-workbench-dev-asset-handler"). The cache lookup always misses,
returning an empty string, which routes everything to the "default" group.

**Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**

EXPECTED OUTCOME: This test FAILS on unfixed code — failure confirms the bug exists.
"""

import json
import os
import tempfile
from typing import Dict, List, Any

import pytest
from hypothesis import given, settings, assume
from hypothesis.strategies import (
    composite,
    text,
    sampled_from,
)
from unittest.mock import patch, PropertyMock

from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# --- Strategies ---

# Realistic workload names (lowercase alphanumeric with hyphens)
WORKLOAD_NAMES = [
    "asset-workbench",
    "my-app",
    "data-platform",
    "web-service",
    "api-gateway",
    "user-service",
    "order-mgmt",
]

# Realistic deployment namespaces
DEPLOYMENT_NAMESPACES = [
    "dev",
    "staging",
    "prod",
    "test",
    "uat",
    "qa",
    "sandbox",
]

# Realistic handler suffixes (what comes after the workload-namespace prefix)
HANDLER_SUFFIXES = [
    "asset-handler",
    "admin-handler",
    "category-handler",
    "checkout-handler",
    "media-handler",
    "search-handler",
    "reporting-handler",
    "location-handler",
    "maintenance-handler",
    "profile-handler",
]

# Folder names corresponding to handlers
FOLDER_NAMES = [
    "assets",
    "admin",
    "categories",
    "checkouts",
    "media",
    "search",
    "reporting",
    "locations",
    "maintenance",
    "profiles",
]


@composite
def workload_and_namespace(draw):
    """Generate a workload name and deployment namespace combination."""
    workload_name = draw(sampled_from(WORKLOAD_NAMES))
    namespace = draw(sampled_from(DEPLOYMENT_NAMESPACES))
    return workload_name, namespace


class TestBugConditionPlaceholderCacheMismatch:
    """
    Property 1: Bug Condition - Placeholder Cache Keys Cause Lookup Misses

    FOR ALL inputs WHERE isBugCondition(input):
      cache = buildLambdaFolderCache(input)
      FOR ALL resolved_name IN input.discovered_route_lambda_names:
        folder = cache.get(resolved_name)
        ASSERT folder != ""
        ASSERT folder == relative_path_of_resource_on_disk(resolved_name)

    **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2**
    """

    def _create_temp_resources_dir(
        self,
        workload_name: str,
        namespace: str,
        handler_suffixes: List[str],
        folder_names: List[str],
    ) -> str:
        """Create a temporary directory structure mimicking configs/stacks/lambdas/resources/.

        Each subfolder contains a JSON file with a placeholder name field like:
        "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-<handler-suffix>"
        """
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        for folder, suffix in zip(folder_names, handler_suffixes):
            folder_path = os.path.join(resources_dir, folder)
            os.makedirs(folder_path, exist_ok=True)

            config = {
                "name": f"{{{{WORKLOAD_NAME}}}}-{{{{DEPLOYMENT_NAMESPACE}}}}-{suffix}",
                "description": f"Handler for {folder}",
                "api": {
                    "route": f"/tenants/{{tenant-id}}/{folder}",
                    "method": "GET",
                },
            }

            json_file = os.path.join(folder_path, f"{suffix}.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(config, f)

        return tmp_dir

    @given(data=workload_and_namespace())
    @settings(max_examples=50)
    def test_resolved_name_lookup_returns_correct_folder(self, data):
        """Cache lookup with resolved lambda name returns correct folder path.

        When WORKLOAD_NAME=<workload> and DEPLOYMENT_NAMESPACE=<namespace>,
        looking up "<workload>-<namespace>-asset-handler" in the cache should
        return "assets" (the folder where the config lives on disk).

        On UNFIXED code, this FAILS because the cache stores the raw placeholder
        name "{{WORKLOAD_NAME}}-{{DEPLOYMENT_NAMESPACE}}-asset-handler" as the key,
        not the resolved name.

        **Validates: Requirements 1.1, 1.2, 2.1, 2.2**
        """
        workload_name, namespace = data

        # Use a subset of handlers for speed
        handler_suffixes = HANDLER_SUFFIXES[
            :3
        ]  # asset-handler, admin-handler, category-handler
        folder_names = FOLDER_NAMES[:3]  # assets, admin, categories

        tmp_dir = self._create_temp_resources_dir(
            workload_name, namespace, handler_suffixes, folder_names
        )

        try:
            # Set environment variables as they would be during CDK synth
            env_patch = {
                "WORKLOAD_NAME": workload_name,
                "DEPLOYMENT_NAMESPACE": namespace,
            }

            with patch.dict(os.environ, env_patch):
                # Create a minimal stack instance to call _build_lambda_folder_cache
                app = App()
                dummy_workload = WorkloadConfig(
                    {
                        "workload": {
                            "name": workload_name,
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
                            },
                        }
                    },
                    workload=dummy_workload.dictionary,
                )
                deployment = DeploymentConfig(
                    workload=dummy_workload.dictionary,
                    deployment={"name": "test-deployment", "environment": namespace},
                )
                stack = ApiGatewayStack(app, f"TestStack-{workload_name}-{namespace}")
                stack.stack_config = stack_config
                stack.deployment = deployment
                stack.workload = dummy_workload
                stack.api_config = ApiGatewayConfig(
                    stack_config.dictionary.get("api_gateway", {})
                )

                # Mock _find_lambda_resources_dir to return our temp dir
                resources_dir = os.path.join(
                    tmp_dir, "configs", "stacks", "lambdas", "resources"
                )
                with patch.object(
                    stack, "_find_lambda_resources_dir", return_value=resources_dir
                ):
                    cache = stack._build_lambda_folder_cache()

                    # For each handler, the resolved name should map to the correct folder
                    for folder, suffix in zip(folder_names, handler_suffixes):
                        resolved_name = f"{workload_name}-{namespace}-{suffix}"
                        result = cache.get(resolved_name, "")

                        # THIS IS THE BUG: on unfixed code, result will be ""
                        # because the cache key is the raw placeholder name
                        assert result == folder, (
                            f"_build_lambda_folder_cache() lookup FAILED:\n"
                            f"  Resolved name: '{resolved_name}'\n"
                            f"  Expected folder: '{folder}'\n"
                            f"  Got: '{result}' (empty string means cache miss)\n"
                            f"  Cache keys: {list(cache.keys())}\n"
                            f"  This confirms the bug: cache stores raw placeholder names "
                            f"but lookup uses resolved names."
                        )
        finally:
            # Cleanup temp directory
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(data=workload_and_namespace())
    @settings(max_examples=50)
    def test_resolve_lambda_folder_returns_correct_folder(self, data):
        """_resolve_lambda_folder() with resolved name returns correct folder.

        This tests the full resolution path: build cache, then look up.
        On unfixed code, _resolve_lambda_folder("asset-workbench-dev-asset-handler")
        returns "" instead of "assets".

        **Validates: Requirements 1.2, 2.2**
        """
        workload_name, namespace = data

        handler_suffixes = HANDLER_SUFFIXES[:3]
        folder_names = FOLDER_NAMES[:3]

        tmp_dir = self._create_temp_resources_dir(
            workload_name, namespace, handler_suffixes, folder_names
        )

        try:
            env_patch = {
                "WORKLOAD_NAME": workload_name,
                "DEPLOYMENT_NAMESPACE": namespace,
            }

            with patch.dict(os.environ, env_patch):
                app = App()
                dummy_workload = WorkloadConfig(
                    {
                        "workload": {
                            "name": workload_name,
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
                            },
                        }
                    },
                    workload=dummy_workload.dictionary,
                )
                deployment = DeploymentConfig(
                    workload=dummy_workload.dictionary,
                    deployment={"name": "test-deployment", "environment": namespace},
                )
                stack = ApiGatewayStack(app, f"TestStack-{workload_name}-{namespace}")
                stack.stack_config = stack_config
                stack.deployment = deployment
                stack.workload = dummy_workload
                stack.api_config = ApiGatewayConfig(
                    stack_config.dictionary.get("api_gateway", {})
                )

                resources_dir = os.path.join(
                    tmp_dir, "configs", "stacks", "lambdas", "resources"
                )
                with patch.object(
                    stack, "_find_lambda_resources_dir", return_value=resources_dir
                ):
                    for folder, suffix in zip(folder_names, handler_suffixes):
                        resolved_name = f"{workload_name}-{namespace}-{suffix}"
                        result = stack._resolve_lambda_folder(resolved_name)

                        assert result == folder, (
                            f"_resolve_lambda_folder('{resolved_name}') returned "
                            f"'{result}' instead of '{folder}'.\n"
                            f"  This confirms the bug: cache key mismatch between "
                            f"raw placeholder names and resolved names."
                        )
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(data=workload_and_namespace())
    @settings(max_examples=50)
    def test_auto_grouping_distributes_routes_across_groups(self, data):
        """End-to-end: routes with resolved names are distributed across groups (not all in "default").

        When auto-grouping is active (no explicit nested_stacks.grouping), routes should
        be distributed to groups matching their Lambda resource folder paths.
        On unfixed code, all routes end up in "default" because folder resolution fails.

        **Validates: Requirements 1.3, 2.2**
        """
        workload_name, namespace = data

        handler_suffixes = HANDLER_SUFFIXES[:3]
        folder_names = FOLDER_NAMES[:3]

        tmp_dir = self._create_temp_resources_dir(
            workload_name, namespace, handler_suffixes, folder_names
        )

        try:
            env_patch = {
                "WORKLOAD_NAME": workload_name,
                "DEPLOYMENT_NAMESPACE": namespace,
            }

            with patch.dict(os.environ, env_patch):
                app = App()
                dummy_workload = WorkloadConfig(
                    {
                        "workload": {
                            "name": workload_name,
                            "devops": {"name": "test-devops"},
                        },
                    }
                )
                # No explicit grouping — triggers auto-grouping
                stack_config = StackConfig(
                    {
                        "api_gateway": {
                            "name": "TestApi",
                            "nested_stacks": {
                                "enabled": True,
                            },
                        }
                    },
                    workload=dummy_workload.dictionary,
                )
                deployment = DeploymentConfig(
                    workload=dummy_workload.dictionary,
                    deployment={"name": "test-deployment", "environment": namespace},
                )
                stack = ApiGatewayStack(app, f"TestStack-{workload_name}-{namespace}")
                stack.stack_config = stack_config
                stack.deployment = deployment
                stack.workload = dummy_workload
                stack.api_config = ApiGatewayConfig(
                    stack_config.dictionary.get("api_gateway", {})
                )

                resources_dir = os.path.join(
                    tmp_dir, "configs", "stacks", "lambdas", "resources"
                )

                # Build routes with resolved lambda names (as _discover_routes_from_dependencies would)
                routes = []
                for folder, suffix in zip(folder_names, handler_suffixes):
                    resolved_name = f"{workload_name}-{namespace}-{suffix}"
                    routes.append(
                        {
                            "path": f"/tenants/{{tenant-id}}/{folder}",
                            "method": "GET",
                            "lambda_name": resolved_name,
                        }
                    )

                with patch.object(
                    stack, "_find_lambda_resources_dir", return_value=resources_dir
                ):
                    route_groups = stack._group_routes(routes)

                # On correctly working code, routes should be distributed across
                # multiple groups (one per folder). On buggy code, everything
                # goes to "default" because _resolve_lambda_folder returns "".
                assert len(route_groups) > 1, (
                    f"Expected routes to be distributed across multiple groups, "
                    f"but got only {len(route_groups)} group(s): {list(route_groups.keys())}.\n"
                    f"  This confirms the bug: all routes went to 'default' because "
                    f"folder resolution failed due to placeholder/resolved name mismatch."
                )

                # Verify "default" doesn't contain all routes
                default_count = len(route_groups.get("default", []))
                total_routes = sum(len(r) for r in route_groups.values())
                assert default_count < total_routes, (
                    f"All {total_routes} routes ended up in 'default' group.\n"
                    f"  Expected routes distributed across groups: {folder_names}\n"
                    f"  Route groups: {list(route_groups.keys())}\n"
                    f"  This confirms the bug: _resolve_lambda_folder() returns empty "
                    f"string for all resolved names."
                )
        finally:
            import shutil

            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
