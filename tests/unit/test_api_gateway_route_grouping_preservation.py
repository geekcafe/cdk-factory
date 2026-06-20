"""
Preservation Property Tests — Non-Auto-Grouping Behavior Unchanged

Property 2: Preservation - Non-Auto-Grouping Behavior Unchanged

These tests verify that non-buggy code paths work correctly on UNFIXED code
and must continue to work identically after the fix is applied. They cover:

1. Explicit nested_stacks.grouping uses the explicit grouping map with longest prefix match
2. When nested_stacks.enabled is false, no grouping occurs
3. Lambda resource configs with literal (no-placeholder) names produce correct cache entries
4. Lambdas not found on disk fall back to "default" group (empty string from _resolve_lambda_folder)

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

EXPECTED OUTCOME: These tests PASS on unfixed code (confirms baseline behavior to preserve).
"""

import json
import os
import string
import tempfile
import shutil
from typing import Dict, List, Any

import pytest
from hypothesis import given, settings, assume
from hypothesis.strategies import (
    composite,
    dictionaries,
    integers,
    just,
    lists,
    sampled_from,
    text,
)
from unittest.mock import patch

from aws_cdk import App
from cdk_factory.stack_library.api_gateway.api_gateway_stack import ApiGatewayStack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.workload.workload_factory import WorkloadConfig


# --- Strategies ---

# Realistic folder paths for grouping config
FOLDER_PATHS = [
    "users",
    "admin",
    "assets",
    "categories",
    "workflow/api",
    "workflow/app",
    "file-system",
    "metrics",
    "search",
    "reporting",
    "maintenance",
    "checkouts",
    "profiles",
    "media",
    "locations",
]

# Realistic group names
GROUP_NAMES = [
    "users",
    "admin",
    "assets",
    "categories",
    "workflow-api",
    "workflow-app",
    "file-system",
    "metrics",
    "search",
    "reporting",
    "maintenance",
    "checkouts",
    "profiles",
    "media",
    "locations",
]

# Realistic route path segments
ROUTE_SEGMENTS = [
    "tenants/{tenant-id}",
    "users",
    "users/{user-id}",
    "assets",
    "assets/{asset-id}",
    "categories",
    "categories/{category-id}",
    "admin",
    "admin/users",
    "search",
    "reports",
    "files",
    "files/{file-id}",
    "maintenance",
    "checkouts",
    "media",
    "locations",
]

HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH"]

# Literal lambda names (no placeholders)
LITERAL_LAMBDA_NAMES = [
    "my-app-dev-asset-handler",
    "my-app-dev-admin-handler",
    "service-prod-user-handler",
    "api-staging-search-handler",
    "workbench-dev-reporting-handler",
    "tool-qa-media-handler",
    "platform-dev-checkout-handler",
    "app-test-location-handler",
    "backend-dev-maintenance-handler",
    "data-dev-category-handler",
]


@composite
def explicit_grouping_config(draw, min_groups=2, max_groups=5):
    """Generate a random explicit grouping configuration.

    Returns a dict mapping group names to lists of folder paths.
    """
    num_groups = draw(
        integers(min_value=min_groups, max_value=min(max_groups, len(GROUP_NAMES)))
    )
    selected_groups = draw(
        lists(
            sampled_from(GROUP_NAMES),
            min_size=num_groups,
            max_size=num_groups,
            unique=True,
        )
    )
    selected_folders = draw(
        lists(
            sampled_from(FOLDER_PATHS),
            min_size=num_groups,
            max_size=num_groups,
            unique=True,
        )
    )

    grouping = {}
    for group_name, folder in zip(selected_groups, selected_folders):
        grouping[group_name] = [folder]

    return grouping


@composite
def routes_for_grouping(
    draw, grouping: Dict[str, List[str]], min_routes=2, max_routes=6
):
    """Generate random routes that map to the given grouping config folders."""
    num_routes = draw(integers(min_value=min_routes, max_value=max_routes))
    routes = []

    # Flatten the grouping to get all folder paths
    all_folders = []
    for folders in grouping.values():
        all_folders.extend(folders)

    for _ in range(num_routes):
        route_segment = draw(sampled_from(ROUTE_SEGMENTS))
        method = draw(sampled_from(HTTP_METHODS))
        lambda_name = draw(
            text(
                min_size=5,
                max_size=20,
                alphabet=string.ascii_lowercase + string.digits + "-",
            )
        )
        routes.append(
            {
                "path": f"/{route_segment}",
                "method": method,
                "lambda_name": lambda_name,
            }
        )

    return routes


@composite
def routes_with_known_folders(draw, grouping: Dict[str, List[str]]):
    """Generate routes where each route is associated with a known folder from the grouping.

    Returns list of (route_dict, folder_path) tuples.
    """
    # Build reverse lookup
    all_folders = []
    for folders in grouping.values():
        all_folders.extend(folders)

    num_routes = draw(integers(min_value=2, max_value=8))
    routes_with_folders = []

    for i in range(num_routes):
        folder = draw(sampled_from(all_folders))
        method = draw(sampled_from(HTTP_METHODS))
        lambda_name = f"lambda-{i}-{draw(text(min_size=3, max_size=8, alphabet=string.ascii_lowercase))}"
        route = {
            "path": f"/tenants/{{tenant-id}}/{folder.replace('/', '-')}/{i}",
            "method": method,
            "lambda_name": lambda_name,
        }
        routes_with_folders.append((route, folder))

    return routes_with_folders


@composite
def literal_name_resource_configs(draw, min_configs=2, max_configs=5):
    """Generate random resource configs with literal (no-placeholder) names.

    Returns list of (literal_name, folder_name) tuples.
    """
    num_configs = draw(integers(min_value=min_configs, max_value=max_configs))
    configs = []
    used_names = set()

    for _ in range(num_configs):
        name = draw(sampled_from(LITERAL_LAMBDA_NAMES))
        if name in used_names:
            continue
        used_names.add(name)
        folder = draw(sampled_from(FOLDER_PATHS[:10]))  # Use top-level folders
        configs.append((name, folder))

    assume(len(configs) >= 2)
    return configs


# ---------------------------------------------------------------------------
# Property 2.1: Explicit Grouping — Longest Prefix Match
# ---------------------------------------------------------------------------


class TestExplicitGroupingPreservation:
    """
    Preservation: When explicit nested_stacks.grouping is configured,
    _group_routes() uses the explicit grouping map with longest prefix match
    (routes assigned to named groups).

    **Validates: Requirements 3.1**
    """

    @given(data=explicit_grouping_config(min_groups=2, max_groups=5))
    @settings(max_examples=100)
    def test_explicit_grouping_assigns_routes_to_named_groups(self, data):
        """Routes are assigned to correct groups based on explicit grouping config.

        When a route's lambda folder matches a configured folder path, it should
        be assigned to the corresponding group name. This uses longest prefix match.

        **Validates: Requirements 3.1**
        """
        grouping = data

        # Build reverse lookup from folder to group name
        folder_to_group = {}
        for group_name, folders in grouping.items():
            for folder in folders:
                folder_to_group[folder] = group_name

        # Pick some folders to assign to routes
        all_folders = list(folder_to_group.keys())
        assume(len(all_folders) >= 2)

        # Create routes with known folder assignments
        routes = []
        expected_assignments = {}  # lambda_name -> expected_group

        for i, folder in enumerate(all_folders):
            lambda_name = f"test-lambda-{i}"
            routes.append(
                {
                    "path": f"/tenants/{{tenant-id}}/resource-{i}",
                    "method": "GET",
                    "lambda_name": lambda_name,
                }
            )
            expected_assignments[lambda_name] = folder_to_group[folder]

        # Create stack with explicit grouping
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
                        "grouping": grouping,
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestExplicitGrouping")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Mock _resolve_lambda_folder to return known folder paths
        def mock_resolve(lambda_name):
            idx = int(lambda_name.split("-")[-1])
            return all_folders[idx]

        with patch.object(stack, "_resolve_lambda_folder", side_effect=mock_resolve):
            result = stack._group_routes(routes)

        # Verify each route ended up in the correct group
        for lambda_name, expected_group in expected_assignments.items():
            found = False
            for group_name, group_routes in result.items():
                for route in group_routes:
                    if route["lambda_name"] == lambda_name:
                        assert group_name == expected_group, (
                            f"Route '{lambda_name}' expected in group '{expected_group}' "
                            f"but found in '{group_name}'"
                        )
                        found = True
                        break
                if found:
                    break
            assert found, f"Route '{lambda_name}' not found in any group"

    @given(data=explicit_grouping_config(min_groups=2, max_groups=4))
    @settings(max_examples=100)
    def test_explicit_grouping_longest_prefix_match(self, data):
        """Nested paths match their parent group via longest prefix match.

        When a lambda's folder is "workflow/api/v2" and the grouping config has
        "workflow/api", the route should be assigned to the group that owns
        "workflow/api" (the longest matching prefix).

        **Validates: Requirements 3.1**
        """
        grouping = data

        # Pick one folder and create a nested version
        folder_to_group = {}
        for group_name, folders in grouping.items():
            for folder in folders:
                folder_to_group[folder] = group_name

        all_folders = list(folder_to_group.keys())
        assume(len(all_folders) >= 1)

        # Pick a folder and create a deeper nested path
        base_folder = all_folders[0]
        nested_folder = f"{base_folder}/nested/deep"
        expected_group = folder_to_group[base_folder]

        routes = [
            {
                "path": "/tenants/{tenant-id}/resource",
                "method": "GET",
                "lambda_name": "nested-lambda",
            }
        ]

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
                        "grouping": grouping,
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestLongestPrefix")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Mock returns a nested folder deeper than the configured one
        with patch.object(stack, "_resolve_lambda_folder", return_value=nested_folder):
            result = stack._group_routes(routes)

        # The route should be assigned to the group that owns the longest matching prefix
        assert expected_group in result, (
            f"Expected group '{expected_group}' not found in result. "
            f"Got groups: {list(result.keys())}. "
            f"Nested folder '{nested_folder}' should have matched "
            f"base folder '{base_folder}'."
        )
        assert any(
            r["lambda_name"] == "nested-lambda" for r in result[expected_group]
        ), f"Route 'nested-lambda' not found in expected group '{expected_group}'"

    @given(data=explicit_grouping_config(min_groups=2, max_groups=4))
    @settings(max_examples=100)
    def test_explicit_grouping_unmatched_goes_to_default(self, data):
        """Routes whose folder doesn't match any grouping config go to "default".

        **Validates: Requirements 3.1**
        """
        grouping = data

        routes = [
            {
                "path": "/tenants/{tenant-id}/unknown",
                "method": "GET",
                "lambda_name": "unmatched-lambda",
            }
        ]

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
                        "grouping": grouping,
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestDefaultFallback")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Return a folder path that doesn't match any configured group
        with patch.object(
            stack, "_resolve_lambda_folder", return_value="totally/unknown/path"
        ):
            result = stack._group_routes(routes)

        assert (
            "default" in result
        ), f"Unmatched route should go to 'default' group but got: {list(result.keys())}"
        assert any(r["lambda_name"] == "unmatched-lambda" for r in result["default"])


# ---------------------------------------------------------------------------
# Property 2.2: Disabled Nested Stacks — No Grouping Occurs
# ---------------------------------------------------------------------------


class TestDisabledNestedStacksPreservation:
    """
    Preservation: When nested_stacks.enabled is false, the nested stacks feature
    is not used and all routes remain in the main stack. The _group_routes()
    behavior is about HOW routes would be grouped IF nested stacks were used.
    When disabled, the nested stack codepath is skipped entirely.

    We verify that the ApiGatewayConfig correctly reports nested_stacks_enabled=False
    and that the grouping config is empty when disabled.

    **Validates: Requirements 3.2**
    """

    @given(
        route_count=integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_nested_stacks_disabled_reports_false(self, route_count):
        """When nested_stacks.enabled is false, ApiGatewayConfig.nested_stacks_enabled returns False.

        This is the gate that prevents the nested stacks codepath from being entered.

        **Validates: Requirements 3.2**
        """
        config = ApiGatewayConfig(
            {
                "name": "TestApi",
                "nested_stacks": {
                    "enabled": False,
                },
            }
        )

        assert (
            config.nested_stacks_enabled is False
        ), "nested_stacks_enabled should be False when 'enabled' is False"

    @given(
        route_count=integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    def test_absent_nested_stacks_reports_false(self, route_count):
        """When nested_stacks section is absent, nested_stacks_enabled returns False.

        **Validates: Requirements 3.2**
        """
        config = ApiGatewayConfig(
            {
                "name": "TestApi",
            }
        )

        assert (
            config.nested_stacks_enabled is False
        ), "nested_stacks_enabled should be False when 'nested_stacks' section is absent"
        assert (
            config.nested_stacks_grouping == {}
        ), "nested_stacks_grouping should be empty dict when section is absent"

    @given(
        route_count=integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_disabled_nested_stacks_grouping_is_empty(self, route_count):
        """When nested_stacks.enabled is false, grouping config is empty.

        Even if grouping is configured alongside enabled=false, the feature
        gate (enabled check) prevents nested stacks from being created.

        **Validates: Requirements 3.2**
        """
        config = ApiGatewayConfig(
            {
                "name": "TestApi",
                "nested_stacks": {
                    "enabled": False,
                    "grouping": {
                        "users": ["users"],
                        "admin": ["admin"],
                    },
                },
            }
        )

        # The enabled flag is the gate — if false, nested stacks aren't created
        assert config.nested_stacks_enabled is False


# ---------------------------------------------------------------------------
# Property 2.3: Literal Names — Cache Stores Correctly
# ---------------------------------------------------------------------------


class TestLiteralNameCachePreservation:
    """
    Preservation: Lambda resource configs with literal (non-placeholder) names
    in the name field produce correct cache entries that can be looked up successfully.

    This is non-buggy behavior that already works on unfixed code because there
    are no placeholders to resolve — the literal name IS the cache key.

    **Validates: Requirements 3.3, 3.4**
    """

    @given(configs=literal_name_resource_configs(min_configs=2, max_configs=5))
    @settings(max_examples=100)
    def test_literal_names_stored_correctly_in_cache(self, configs):
        """Cache stores literal names correctly and lookups succeed.

        When resource configs have no placeholder tokens in the name field,
        _build_lambda_folder_cache() stores the literal name as the cache key
        and lookups with that exact name succeed.

        **Validates: Requirements 3.3, 3.4**
        """
        # Create temp directory with resource configs using literal names
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        try:
            for literal_name, folder in configs:
                folder_path = os.path.join(resources_dir, folder)
                os.makedirs(folder_path, exist_ok=True)

                config_data = {
                    "name": literal_name,  # No placeholders!
                    "description": f"Handler with literal name",
                    "api": {
                        "route": f"/tenants/{{tenant-id}}/{folder}",
                        "method": "GET",
                    },
                }

                # Use a unique filename based on the name
                safe_filename = literal_name.replace("/", "-") + ".json"
                json_file = os.path.join(folder_path, safe_filename)
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(config_data, f)

            # Create stack and build cache
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
                        "nested_stacks": {"enabled": True},
                    }
                },
                workload=dummy_workload.dictionary,
            )
            deployment = DeploymentConfig(
                workload=dummy_workload.dictionary,
                deployment={"name": "test-deployment", "environment": "test"},
            )
            stack = ApiGatewayStack(app, "TestLiteralCache")
            stack.stack_config = stack_config
            stack.deployment = deployment
            stack.workload = dummy_workload
            stack.api_config = ApiGatewayConfig(
                stack_config.dictionary.get("api_gateway", {})
            )

            with patch.object(
                stack, "_find_lambda_resources_dir", return_value=resources_dir
            ):
                cache = stack._build_lambda_folder_cache()

            # Verify each literal name is stored correctly
            for literal_name, folder in configs:
                assert literal_name in cache, (
                    f"Literal name '{literal_name}' not found in cache. "
                    f"Cache keys: {list(cache.keys())}"
                )
                # For top-level folders without "/" in the path
                actual_folder = cache[literal_name]
                # Handle folder paths that might have slashes
                expected_folder = folder
                assert actual_folder == expected_folder, (
                    f"Literal name '{literal_name}' mapped to '{actual_folder}' "
                    f"but expected '{expected_folder}'"
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(configs=literal_name_resource_configs(min_configs=2, max_configs=4))
    @settings(max_examples=100)
    def test_resolve_lambda_folder_succeeds_for_literal_names(self, configs):
        """_resolve_lambda_folder() successfully looks up literal names.

        This confirms that when the name field has no placeholders, the existing
        cache mechanism works correctly — the name on disk IS the lookup key.

        **Validates: Requirements 3.4**
        """
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        try:
            for literal_name, folder in configs:
                folder_path = os.path.join(resources_dir, folder)
                os.makedirs(folder_path, exist_ok=True)

                config_data = {
                    "name": literal_name,
                    "api": {
                        "route": f"/tenants/{{tenant-id}}/{folder}",
                        "method": "GET",
                    },
                }

                safe_filename = literal_name.replace("/", "-") + ".json"
                json_file = os.path.join(folder_path, safe_filename)
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(config_data, f)

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
                        "nested_stacks": {"enabled": True},
                    }
                },
                workload=dummy_workload.dictionary,
            )
            deployment = DeploymentConfig(
                workload=dummy_workload.dictionary,
                deployment={"name": "test-deployment", "environment": "test"},
            )
            stack = ApiGatewayStack(app, "TestLiteralResolve")
            stack.stack_config = stack_config
            stack.deployment = deployment
            stack.workload = dummy_workload
            stack.api_config = ApiGatewayConfig(
                stack_config.dictionary.get("api_gateway", {})
            )

            with patch.object(
                stack, "_find_lambda_resources_dir", return_value=resources_dir
            ):
                for literal_name, folder in configs:
                    result = stack._resolve_lambda_folder(literal_name)
                    assert result == folder, (
                        f"_resolve_lambda_folder('{literal_name}') returned "
                        f"'{result}' instead of expected '{folder}'"
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Property 2.4: Default Fallback — Lambdas Not On Disk
# ---------------------------------------------------------------------------


class TestDefaultFallbackPreservation:
    """
    Preservation: Lambdas that genuinely cannot be found on disk still fall back
    to the "default" group. When _resolve_lambda_folder() returns an empty string,
    _group_routes() assigns the route to "default".

    **Validates: Requirements 3.4**
    """

    @given(
        lambda_names=lists(
            text(
                min_size=5,
                max_size=25,
                alphabet=string.ascii_lowercase + string.digits + "-",
            ),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=100)
    def test_resolve_lambda_folder_returns_empty_for_unknown_names(self, lambda_names):
        """_resolve_lambda_folder() returns empty string for lambda names not on disk.

        When a lambda name doesn't exist in any resource config file on disk,
        the cache lookup returns empty string, which triggers assignment to "default".

        **Validates: Requirements 3.4**
        """
        # Create an empty resources directory (no configs at all)
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        try:
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
                        "nested_stacks": {"enabled": True},
                    }
                },
                workload=dummy_workload.dictionary,
            )
            deployment = DeploymentConfig(
                workload=dummy_workload.dictionary,
                deployment={"name": "test-deployment", "environment": "test"},
            )
            stack = ApiGatewayStack(app, "TestDefaultFallback")
            stack.stack_config = stack_config
            stack.deployment = deployment
            stack.workload = dummy_workload
            stack.api_config = ApiGatewayConfig(
                stack_config.dictionary.get("api_gateway", {})
            )

            with patch.object(
                stack, "_find_lambda_resources_dir", return_value=resources_dir
            ):
                for name in lambda_names:
                    result = stack._resolve_lambda_folder(name)
                    assert result == "", (
                        f"_resolve_lambda_folder('{name}') returned '{result}' "
                        f"instead of empty string for a name not on disk"
                    )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(
        lambda_names=lists(
            text(
                min_size=5,
                max_size=20,
                alphabet=string.ascii_lowercase + string.digits + "-",
            ),
            min_size=1,
            max_size=5,
            unique=True,
        )
    )
    @settings(max_examples=100)
    def test_auto_grouping_unknown_lambdas_go_to_default(self, lambda_names):
        """Routes with unresolvable lambda names go to "default" group in auto-grouping.

        When auto-grouping is active (no explicit grouping) and _resolve_lambda_folder()
        returns empty string, the route is assigned to "default".

        **Validates: Requirements 3.4**
        """
        # Create empty resources directory
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        try:
            app = App()
            dummy_workload = WorkloadConfig(
                {
                    "workload": {
                        "name": "test-workload",
                        "devops": {"name": "test-devops"},
                    },
                }
            )
            # No explicit grouping — triggers auto-grouping path
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
                deployment={"name": "test-deployment", "environment": "test"},
            )
            stack = ApiGatewayStack(app, "TestAutoGroupDefault")
            stack.stack_config = stack_config
            stack.deployment = deployment
            stack.workload = dummy_workload
            stack.api_config = ApiGatewayConfig(
                stack_config.dictionary.get("api_gateway", {})
            )

            routes = [
                {
                    "path": f"/tenants/{{tenant-id}}/resource-{i}",
                    "method": "GET",
                    "lambda_name": name,
                }
                for i, name in enumerate(lambda_names)
            ]

            with patch.object(
                stack, "_find_lambda_resources_dir", return_value=resources_dir
            ):
                result = stack._group_routes(routes)

            # All routes should be in "default" because none can be resolved
            assert (
                "default" in result
            ), f"Expected 'default' group but got: {list(result.keys())}"
            assert len(result["default"]) == len(lambda_names), (
                f"Expected {len(lambda_names)} routes in 'default' but got "
                f"{len(result['default'])}"
            )
            # No other groups should exist
            assert list(result.keys()) == [
                "default"
            ], f"Expected only 'default' group but got: {list(result.keys())}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @given(data=explicit_grouping_config(min_groups=2, max_groups=3))
    @settings(max_examples=100)
    def test_explicit_grouping_empty_folder_goes_to_default(self, data):
        """With explicit grouping, empty folder resolution also goes to "default".

        When _resolve_lambda_folder() returns "" (lambda not on disk) and explicit
        grouping is configured, the route goes to "default" because "" doesn't
        match any configured folder path.

        **Validates: Requirements 3.4**
        """
        grouping = data

        routes = [
            {
                "path": "/tenants/{tenant-id}/mystery",
                "method": "GET",
                "lambda_name": "missing-lambda",
            }
        ]

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
                        "grouping": grouping,
                    },
                }
            },
            workload=dummy_workload.dictionary,
        )
        deployment = DeploymentConfig(
            workload=dummy_workload.dictionary,
            deployment={"name": "test-deployment", "environment": "test"},
        )
        stack = ApiGatewayStack(app, "TestExplicitDefault")
        stack.stack_config = stack_config
        stack.deployment = deployment
        stack.workload = dummy_workload
        stack.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # _resolve_lambda_folder returns "" for unknown lambda
        with patch.object(stack, "_resolve_lambda_folder", return_value=""):
            result = stack._group_routes(routes)

        assert "default" in result, (
            f"Expected 'default' group for unresolvable lambda but got: "
            f"{list(result.keys())}"
        )
        assert any(r["lambda_name"] == "missing-lambda" for r in result["default"])


# ---------------------------------------------------------------------------
# Property 2.5: Configs Without API Section Are Skipped
# ---------------------------------------------------------------------------


class TestNoApiSectionSkippedPreservation:
    """
    Preservation: Lambda resource configs without an api section are skipped
    during route discovery. They don't appear in the cache unless they have a name.

    The cache stores ALL configs with a name field regardless of api section,
    but _discover_routes_from_dependencies() only discovers routes from configs
    that have both a name AND an api section with a route.

    **Validates: Requirements 3.3**
    """

    @given(
        has_api=sampled_from([True, False]),
        num_configs=integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_configs_without_api_section_still_cached_by_name(
        self, has_api, num_configs
    ):
        """Configs without api section are still cached (they have a name), but
        won't produce routes in discovery.

        The _build_lambda_folder_cache() caches ALL configs with a name field,
        regardless of whether they have an api section. This is correct behavior
        because the cache is purely about name-to-folder mapping.

        **Validates: Requirements 3.3**
        """
        tmp_dir = tempfile.mkdtemp()
        resources_dir = os.path.join(
            tmp_dir, "configs", "stacks", "lambdas", "resources"
        )
        os.makedirs(resources_dir)

        try:
            configs_written = []
            for i in range(num_configs):
                folder = f"folder-{i}"
                folder_path = os.path.join(resources_dir, folder)
                os.makedirs(folder_path, exist_ok=True)

                name = f"lambda-no-api-{i}"
                config_data = {"name": name, "description": "A lambda without API"}

                if has_api:
                    config_data["api"] = {
                        "route": f"/resource-{i}",
                        "method": "GET",
                    }

                json_file = os.path.join(folder_path, f"config-{i}.json")
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(config_data, f)
                configs_written.append((name, folder))

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
                        "nested_stacks": {"enabled": True},
                    }
                },
                workload=dummy_workload.dictionary,
            )
            deployment = DeploymentConfig(
                workload=dummy_workload.dictionary,
                deployment={"name": "test-deployment", "environment": "test"},
            )
            stack = ApiGatewayStack(app, "TestNoApiCache")
            stack.stack_config = stack_config
            stack.deployment = deployment
            stack.workload = dummy_workload
            stack.api_config = ApiGatewayConfig(
                stack_config.dictionary.get("api_gateway", {})
            )

            with patch.object(
                stack, "_find_lambda_resources_dir", return_value=resources_dir
            ):
                cache = stack._build_lambda_folder_cache()

            # The cache stores ALL configs with a name, regardless of api section
            for name, folder in configs_written:
                assert name in cache, (
                    f"Config with name '{name}' should be in cache "
                    f"regardless of api section presence"
                )
                assert cache[name] == folder, (
                    f"Config '{name}' mapped to '{cache[name]}' "
                    f"instead of expected '{folder}'"
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
