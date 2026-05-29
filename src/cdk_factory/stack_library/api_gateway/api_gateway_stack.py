"""
API Gateway Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from pathlib import Path
import hashlib
import os
import json
from typing import List, Dict, Any
import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_cognito as cognito
from aws_cdk import Size
from aws_cdk import aws_lambda as _lambda
from constructs import Construct
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from aws_lambda_powertools import Logger
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.utils.api_gateway_utilities import ApiGatewayUtilities
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from aws_cdk import aws_apigatewayv2 as api_gateway_v2
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from cdk_factory.utilities.file_operations import FileOperations
from cdk_factory.utilities.api_gateway_integration_utility import (
    ApiGatewayIntegrationUtility,
)
from cdk_factory.configurations.resources.apigateway_route_config import (
    ApiGatewayConfigRouteConfig,
)
from cdk_factory.utilities.route_metadata_validator import RouteMetadataValidator
from cdk_factory.utilities.synth_messages import synth_messages
from cdk_factory.stack_library.api_gateway.api_gateway_route_group_nested_stack import (
    ApiGatewayRouteGroupNestedStack,
)
from cdk_factory.stack_library.api_gateway.path_ownership_builder import (
    PathOwnershipBuilder,
)

logger = Logger(service="ApiGatewayStack")


@register_stack("api_gateway_library_module")
@register_stack("api_gateway_stack")
class ApiGatewayStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for AWS API Gateway (REST API).
    Supports all major RestApi parameters.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.api_config: ApiGatewayConfig | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None
        self.api_gateway_integrations: list = []
        self.integration_utility: ApiGatewayIntegrationUtility | None = None

    def build(self, stack_config, deployment, workload) -> None:
        self._build(stack_config, deployment, workload)

    def _build(self, stack_config, deployment, workload) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Validate ssm.imports keys — fail fast on unrecognized keys
        _KNOWN_IMPORT_KEYS = {
            "lambda_namespace",
            "route53_namespace",
            "cognito_namespace",
        }
        ssm_imports = stack_config.ssm_config.get("imports", {})
        unknown_keys = set(ssm_imports.keys()) - _KNOWN_IMPORT_KEYS
        if unknown_keys:
            raise ValueError(
                f"Stack '{stack_config.name}': unrecognized key(s) in ssm.imports: "
                f"{sorted(unknown_keys)}. "
                f"Valid keys are: {sorted(_KNOWN_IMPORT_KEYS)}"
            )

        self.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Initialize integration utility
        self.integration_utility = ApiGatewayIntegrationUtility(self)

        api_type = self.api_config.api_type
        api_name = self.api_config.name or "api-gateway"
        # Use stable construct ID to prevent CloudFormation logical ID changes on pipeline rename
        # API recreation would cause downtime, so construct ID must be stable
        stable_api_id = (
            f"{deployment.workload_name}-{deployment.environment}-api-gateway"
        )
        api_id = deployment.build_resource_name(api_name)

        routes = self.api_config.routes or []

        # Discover routes from Lambda stacks listed in depends_on
        discovered_routes = self._discover_routes_from_dependencies()
        routes = self._merge_routes(routes, discovered_routes)

        if not routes:
            routes = [
                {"path": "/health", "method": "GET", "src": None, "handler": None}
            ]

        if api_type == "HTTP":
            api = self._create_http_api(stable_api_id, routes)
            # TODO: Add custom domain support for HTTP API
            # self.__setup_custom_domain(api)
        elif api_type == "REST":
            if self.api_config.nested_stacks_enabled:
                self._build_with_nested_stacks(routes)
            else:
                api = self._create_rest_api(stable_api_id, routes)
                self.__setup_custom_domain(api)
        else:
            raise ValueError(f"Unsupported api_type: {api_type}")

    def _build_with_nested_stacks(self, routes: List[Dict[str, Any]]) -> None:
        """Orchestrate nested stack creation for route groups.

        Creates shared resources (REST API, authorizer, deployment, stage) in the
        parent stack and distributes route-specific resources across domain-aligned
        nested stacks.

        Uses the PathOwnershipBuilder (trie-based) to identify all path segments
        shared across multiple route groups and creates those shared resources in
        the parent stack. Each nested stack receives a resource_id_handoff_map
        telling it exactly where to attach its unique segments.

        Steps:
        1. Group routes by domain using _group_routes()
        2. Validate resource limits per group and total nested stack count
        3. Create REST API (shared resource in parent)
        4. Create Cognito Authorizer (shared resource in parent)
        4.5. Build path ownership trie and create shared resources in parent
        5. Determine CORS ownership for shared paths (first group in sorted order)
        6. Get CORS config for nested stacks
        7. Instantiate one ApiGatewayRouteGroupNestedStack per group with handoff map
        8. Compute deployment hash and create Deployment + Stage with dependencies
        9. Setup custom domain
        10. Export SSM parameters
        """
        # 1. Group routes by domain
        route_groups = self._group_routes(routes)

        # 2. Validate resource limits per group and total nested stack count (max 20)
        self._validate_resource_limits(route_groups)

        # 3. Create REST API (shared resource in parent) using the integration utility
        # This uses the same pattern as _create_rest_api() for consistency
        stable_api_id = (
            f"{self.deployment.workload_name}-{self.deployment.environment}-api-gateway"
        )
        api = self.integration_utility.create_api_gateway_with_config(
            stable_api_id, self.api_config, self.stack_config
        )

        # 4. Create Cognito Authorizer (shared resource in parent)
        authorizer = self._setup_cognito_authorizer(api, stable_api_id, routes)

        # 4.5. Build path ownership trie and create shared resources in parent
        # Use the trie-based PathOwnershipBuilder to identify all shared path
        # segments across route groups and compute handoff maps for each group.
        # Single-group case: pass root resource ID directly without shared resources.
        resource_id_map: Dict[str, str] = {"/": api.rest_api_root_resource_id}

        if len(route_groups) > 1:
            # Build trie from all route groups and validate ownership
            builder = PathOwnershipBuilder(route_groups)
            builder.build()
            builder.validate()

            # Create CfnResource for each shared node in the parent stack
            shared_nodes = builder.get_shared_nodes()

            if shared_nodes:
                logger.info(
                    f"Path ownership trie identified {len(shared_nodes)} shared node(s) "
                    f"across {len(route_groups)} nested stacks"
                )
                print(
                    f"🌳 Path ownership: {len(shared_nodes)} shared resource(s) "
                    f"created in parent stack"
                )

            for node in shared_nodes:
                path_key = "/" + "/".join(node.full_path)
                parent_path_key = (
                    "/" + "/".join(node.parent.full_path)
                    if node.parent and node.parent.segment
                    else "/"
                )
                construct_id = PathOwnershipBuilder.compute_construct_id(node.full_path)

                cfn_resource = apigateway.CfnResource(
                    self,
                    construct_id,
                    rest_api_id=api.rest_api_id,
                    parent_id=resource_id_map[parent_path_key],
                    path_part=node.segment,
                )
                resource_id_map[path_key] = cfn_resource.ref
        else:
            builder = None
            logger.info(
                "Single route group — passing root resource ID directly to nested stack "
                "(no shared resources needed in parent)."
            )

        # 5. Determine CORS ownership for shared paths
        # The first group in sorted order owns the OPTIONS method for any shared path.
        # Build a set of paths per group and identify shared paths.
        cors_ownership: Dict[str, str] = {}  # path -> owning group name
        sorted_group_names = sorted(route_groups.keys())
        for group_name in sorted_group_names:
            for route in route_groups[group_name]:
                route_path = route.get("path", "")
                if route_path and route_path not in cors_ownership:
                    # First group (in sorted order) to claim this path owns OPTIONS
                    cors_ownership[route_path] = group_name

        # 6. Get CORS config for nested stacks
        cors_config = self.api_config.default_cors_preflight_options or {}

        # 7. Instantiate one nested stack per group
        nested_stacks: List[ApiGatewayRouteGroupNestedStack] = []
        all_methods: List[apigateway.Method] = []

        for group_name in sorted_group_names:
            group_routes = route_groups[group_name]

            # Filter routes for CORS ownership: only include routes whose paths
            # are owned by this group for OPTIONS creation. Routes whose paths
            # are owned by another group get a flag to skip OPTIONS.
            routes_with_cors_flags = []
            for route in group_routes:
                route_copy = dict(route)
                route_path = route_copy.get("path", "")
                if cors_ownership.get(route_path) != group_name:
                    # This group does NOT own OPTIONS for this path — signal to skip
                    route_copy["_skip_cors"] = True
                routes_with_cors_flags.append(route_copy)

            nested_stack = ApiGatewayRouteGroupNestedStack(
                self, f"RouteGroup-{group_name}"
            )

            # Compute the resource_id_handoff_map for this group
            if builder is not None:
                # Multi-group case: resolve handoff map paths to actual resource IDs
                handoff_map = builder.get_handoff_map(group_name)
                resolved_handoff = {path: resource_id_map[path] for path in handoff_map}
            else:
                # Single-group case: handoff from API root only
                resolved_handoff = {"/": api.rest_api_root_resource_id}

            methods = nested_stack.build(
                api_gateway=api,
                root_resource_id=api.rest_api_root_resource_id,
                authorizer=authorizer,
                routes=routes_with_cors_flags,
                stack_config=self.stack_config,
                cors_config=cors_config,
                group_name=group_name,
                resource_id_handoff_map=resolved_handoff,
            )

            nested_stacks.append(nested_stack)
            all_methods.extend(methods)

        # 8. Compute deployment hash and create Deployment with dependencies
        deployment_hash = self._compute_deployment_hash(route_groups)
        deployment = apigateway.Deployment(
            self,
            f"Deployment-{deployment_hash}",
            api=api,
            description=f"Deployment with {len(all_methods)} methods across {len(nested_stacks)} nested stacks",
        )

        # Add explicit dependency from Deployment to every nested stack
        # This ensures CloudFormation does not create the Deployment until
        # all nested stacks have been provisioned (Requirement 4.2)
        for ns in nested_stacks:
            deployment.node.add_dependency(ns)

        # 9. Create Stage with dependency on Deployment (Requirement 4.4)
        stage_name = self.api_config.stage_name
        stage = apigateway.Stage(
            self,
            f"api-gateway-stage-{stage_name}",
            deployment=deployment,
            stage_name=stage_name,
            description=f"Stage {stage_name} with {len(all_methods)} methods across {len(nested_stacks)} nested stacks",
        )

        # Store stage reference for custom domain base path mapping
        self._store_deployment_stage_reference(api, stage)

        # 10. Setup custom domain (Requirement 2.5)
        self.__setup_custom_domain(api)

        # 11. Export SSM parameters (Requirement 9.1-9.4)
        self._export_ssm_parameters(api, authorizer)

    def _validate_resource_limits(
        self, route_groups: Dict[str, List[Dict[str, Any]]]
    ) -> None:
        """Check each route group against resource limit thresholds.

        Estimates the CloudFormation resource count per group using the formula:
        ~3 resources per route (Method + Permission + integration) plus unique
        path segments shared across routes in the group.

        Validations performed:
        1. Total nested stack count must not exceed 20
        2. No group may exceed 500 resources (hard CloudFormation limit)
        3. Groups exceeding max_resources_per_stack emit a warning

        Args:
            route_groups: Dict mapping group names to lists of route dicts.

        Raises:
            ValueError: If nested stack count exceeds 20 or any group exceeds
                500 resources.
        """
        max_per_stack = self.api_config.max_resources_per_stack

        # Validate total nested stack count (Requirement 7.7)
        if len(route_groups) > 20:
            raise ValueError(
                f"Nested stack count ({len(route_groups)}) exceeds maximum of 20. "
                f"Consolidate route groups in nested_stacks.grouping config."
            )

        for group_name, routes in route_groups.items():
            # Estimate: ~3 resources per route (Method + Permission + shared path segments)
            # Plus unique path segments
            unique_paths = set()
            for route in routes:
                path_parts = route.get("path", "").strip("/").split("/")
                for i in range(len(path_parts)):
                    unique_paths.add("/".join(path_parts[: i + 1]))

            estimated_resources = (len(routes) * 3) + len(unique_paths)

            # Hard limit: 500 resources (CloudFormation limit)
            if estimated_resources > 500:
                raise ValueError(
                    f"Route group '{group_name}' would produce ~{estimated_resources} "
                    f"resources, exceeding the CloudFormation limit of 500. "
                    f"Split this group in the nested_stacks.grouping config."
                )

            # Configurable threshold warning
            if estimated_resources > max_per_stack:
                print(
                    f"WARNING: Route group '{group_name}' would produce "
                    f"~{estimated_resources} resources, exceeding the configured "
                    f"limit of {max_per_stack}. Consider splitting this group."
                )

    def _group_routes(
        self, routes: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Assign routes to groups based on Domain_Grouping_Config.

        Algorithm:
        1. If explicit grouping is configured:
           a. Build reverse lookup from folder paths to group names
           b. For each route, resolve its Lambda resource folder path
           c. Match folder path to group using longest prefix match
           d. Assign unmatched routes to "default" group
        2. If no explicit grouping is configured (auto-grouping):
           a. For each route, resolve its Lambda resource folder path
           b. Use the top-level folder name as the group name
           c. This mirrors the folder structure under resources/
        3. Skip empty groups (no nested stack created for zero-route groups)

        Returns:
            Dict mapping group names to lists of route dicts. Empty groups
            are not included in the result.
        """
        grouping = self.api_config.nested_stacks_grouping
        groups: Dict[str, List[Dict[str, Any]]] = {}

        if grouping:
            # Explicit grouping: build reverse lookup from folder paths to group names
            folder_to_group: Dict[str, str] = {}
            for group_name, folders in grouping.items():
                for folder in folders:
                    folder_to_group[folder] = group_name

            for route in routes:
                lambda_name = route.get("lambda_name")
                folder_path = self._resolve_lambda_folder(lambda_name)

                # Match folder path to group (longest prefix match)
                group_name = folder_to_group.get(folder_path)
                if not group_name:
                    # Try parent folder matching for nested paths
                    parts = folder_path.split("/")
                    while parts and not group_name:
                        parts.pop()
                        group_name = folder_to_group.get("/".join(parts))

                group_name = group_name or "default"
                groups.setdefault(group_name, []).append(route)
        else:
            # Auto-grouping: use the Lambda resource folder path as the group name.
            # For nested paths like "workflow/api", uses the full path as the group name.
            # For top-level paths like "users", uses "users" as the group name.
            # Lambdas that can't be resolved to a folder go into "default".
            logger.info(
                "No explicit 'grouping' configured — auto-grouping routes by "
                "Lambda resource folder structure."
            )
            for route in routes:
                lambda_name = route.get("lambda_name")
                folder_path = self._resolve_lambda_folder(lambda_name)
                group_name = folder_path if folder_path else "default"
                groups.setdefault(group_name, []).append(route)

        return groups

    def _resolve_lambda_folder(self, lambda_name: str) -> str:
        """Determine the Lambda resource folder path from the lambda_name.

        Scans the workload config's Lambda resource folders on disk to find
        which folder contains a Lambda config JSON with the matching name.
        Results are cached after the first scan to avoid repeated file I/O.

        Args:
            lambda_name: The name of the Lambda function (e.g., "workflow-execution-output-file")

        Returns:
            The relative folder path (e.g., "workflow/api", "users", "file-system").
            Returns empty string if the lambda cannot be found.
        """
        if not hasattr(self, "_lambda_folder_cache"):
            self._lambda_folder_cache = self._build_lambda_folder_cache()

        return self._lambda_folder_cache.get(lambda_name, "")

    def _build_lambda_folder_cache(self) -> Dict[str, str]:
        """Build a lookup cache mapping lambda_name to its resource folder path.

        Scans the Lambda resource folders on disk, loading each JSON config
        file and extracting the 'name' field. The relative folder path from
        the resources root directory is used as the value.

        Returns:
            Dict mapping lambda names to their relative folder paths.
        """
        cache: Dict[str, str] = {}
        resources_dir = self._find_lambda_resources_dir()
        if not resources_dir:
            logger.warning(
                "Could not locate Lambda resources directory. "
                "Lambda folder resolution will not work."
            )
            return cache

        resources_path = Path(resources_dir)
        for json_file in resources_path.rglob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                name = config.get("name")
                if name:
                    # Compute relative folder path from resources root
                    relative_folder = str(json_file.parent.relative_to(resources_path))
                    # Normalize path separators and handle current dir
                    if relative_folder == ".":
                        relative_folder = ""
                    cache[name] = relative_folder
            except (json.JSONDecodeError, OSError):
                # Skip files that can't be parsed
                continue

        return cache

    def _find_lambda_resources_dir(self) -> str | None:
        """Locate the Lambda resources directory on disk.

        Searches workload paths for the standard Lambda resource folder
        structure at 'configs/stacks/lambdas/resources'.

        Returns:
            Absolute path to the resources directory, or None if not found.
        """
        if not self.workload:
            return None

        # Standard relative path for Lambda resource configs
        resource_rel_path = os.path.join("configs", "stacks", "lambdas", "resources")

        for base_path in self.workload.paths:
            candidate = os.path.join(base_path, resource_rel_path)
            if os.path.isdir(candidate):
                return candidate

        return None

    def _compute_deployment_hash(self, route_groups: Dict[str, List[Dict]]) -> str:
        """Compute a deterministic hash from all route signatures.

        Changes to any route in any group produce a new hash,
        forcing a new Deployment resource. Routes and groups are sorted
        internally to ensure deterministic output regardless of input order.

        Args:
            route_groups: Dict mapping group names to lists of route dicts.
                Each route dict must have 'method' and 'path' keys,
                and optionally 'lambda_name'.

        Returns:
            First 16 characters of the SHA-256 hex digest of all route
            signatures, suitable for use in a Deployment logical ID.
        """
        signatures = []
        for group_name in sorted(route_groups.keys()):
            for route in sorted(
                route_groups[group_name],
                key=lambda r: (r["path"], r["method"]),
            ):
                sig = f"{group_name}:{route['method'].upper()}:{route['path']}:{route.get('lambda_name', '')}"
                signatures.append(sig)

        combined = "|".join(signatures)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _discover_routes_from_dependencies(self) -> List[Dict[str, Any]]:
        """Discover routes from all Lambda stacks in the pipeline.

        Scans all stacks across all pipeline stages in the resolved workload
        config, looking for resources with `api` sections. This means routes
        are automatically discovered without needing to list every lambda
        stack in `depends_on`.
        """
        discovered = []
        if not self.workload:
            return discovered

        workload_dict = self.workload.dictionary
        deployments = workload_dict.get("deployments", [])

        for deployment in deployments:
            pipeline = deployment.get("pipeline", {})
            for stage in pipeline.get("stages", []):
                for stack in stage.get("stacks", []):
                    # Only look at lambda stacks
                    module = stack.get("module", "")
                    if "lambda" not in module:
                        continue

                    resources = stack.get("resources", [])
                    if isinstance(resources, dict):
                        # __inherits__ not resolved — skip
                        continue
                    if not resources:
                        resources = stack.get("lambdas", [])
                    if not resources:
                        continue

                    stack_name = stack.get("name", "unknown")
                    for resource in resources:
                        if not isinstance(resource, dict):
                            continue
                        lambda_name = resource.get("name")
                        api_config = resource.get("api")
                        if (
                            not lambda_name
                            or not api_config
                            or not api_config.get("route")
                        ):
                            continue

                        try:
                            RouteMetadataValidator.validate_route_metadata(
                                api_config, lambda_name
                            )
                        except ValueError as e:
                            logger.warning(
                                f"Invalid route metadata in '{stack_name}', lambda '{lambda_name}': {e}"
                            )
                            synth_messages.warning(
                                f"Invalid route: {lambda_name} — {e}"
                            )
                            continue

                        route = {
                            "path": api_config.get("route", ""),
                            "method": api_config.get("method", "GET").upper(),
                            "lambda_name": lambda_name,
                            "skip_authorizer": api_config.get("skip_authorizer", False),
                            "allow_public_override": api_config.get(
                                "allow_public_override", False
                            ),
                        }
                        if route["skip_authorizer"]:
                            route["authorization_type"] = "NONE"

                        # Only add the top-level route if there's no routes[] array,
                        # or if the top-level route isn't already in the routes[] array.
                        # When routes[] is present, it's the authoritative list.
                        sub_routes = api_config.get("routes", [])
                        top_level_in_sub_routes = any(
                            sr.get("route") == route["path"]
                            and sr.get("method", "GET").upper() == route["method"]
                            for sr in sub_routes
                        )

                        if not top_level_in_sub_routes:
                            discovered.append(route)
                            logger.info(
                                f"Discovered route: {route['method']} {route['path']} -> {lambda_name}"
                            )

                        # Expand multi-route lambdas
                        for sub_route in sub_routes:
                            sub = {
                                "path": sub_route.get("route", ""),
                                "method": sub_route.get("method", "GET").upper(),
                                "lambda_name": lambda_name,
                                "skip_authorizer": sub_route.get(
                                    "skip_authorizer",
                                    api_config.get("skip_authorizer", False),
                                ),
                                "allow_public_override": sub_route.get(
                                    "allow_public_override",
                                    api_config.get("allow_public_override", False),
                                ),
                            }
                            if sub["skip_authorizer"]:
                                sub["authorization_type"] = "NONE"
                            discovered.append(sub)
                            logger.info(
                                f"Discovered sub-route: {sub['method']} {sub['path']} -> {lambda_name}"
                            )

        if discovered:
            print(f"🔍 Discovered {len(discovered)} route(s) from Lambda stacks")

        return discovered

    def _find_dependency_stack_config(self, dep_name: str) -> dict | None:
        """Find a dependency's resolved stack config from the workload config."""
        if not self.workload:
            return None

        workload_dict = self.workload.dictionary
        deployments = workload_dict.get("deployments", [])
        for deployment in deployments:
            pipeline = deployment.get("pipeline", {})
            for stage in pipeline.get("stages", []):
                for stack in stage.get("stacks", []):
                    stack_name = stack.get("name", "")
                    if dep_name in stack_name:
                        return stack
        return None

    @staticmethod
    def _merge_routes(
        explicit: List[Dict[str, Any]], discovered: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge explicit and discovered routes. Explicit wins on conflict."""
        if not discovered:
            return list(explicit)
        if not explicit:
            return list(discovered)

        explicit_keys = {}
        for route in explicit:
            key = (route.get("path", ""), route.get("method", "GET").upper())
            explicit_keys[key] = route

        merged = list(explicit)
        for route in discovered:
            key = (route.get("path", ""), route.get("method", "GET").upper())
            if key in explicit_keys:
                logger.warning(
                    f"Route conflict: {key[1]} {key[0]} exists in both explicit config "
                    f"and discovered routes. Using explicit route definition."
                )
                synth_messages.warning(
                    f"Route conflict: {key[1]} {key[0]} — explicit config wins over discovered route"
                )
            else:
                merged.append(route)
                synth_messages.info(
                    f"Discovered route: {key[1]} {key[0]} -> {route.get('lambda_name')}"
                )

        return merged

    def _create_rest_api(self, api_id: str, routes: List[Dict[str, Any]]):
        # Use shared utility for consistent API Gateway creation
        # Note: The utility now creates API Gateway with deploy=False to prevent stage conflicts
        api_gateway = self.integration_utility.create_api_gateway_with_config(
            api_id, self.api_config, self.stack_config
        )

        # Setup API Gateway components in logical order
        self._setup_api_resources_and_methods(api_gateway)
        api_keys = self._setup_api_keys()
        self._setup_usage_plans(api_gateway, api_keys)
        authorizer = self._setup_cognito_authorizer(api_gateway, api_id, routes)
        self._setup_lambda_routes(api_gateway, api_id, routes, authorizer)

        # Finalize deployment and stage creation
        stage = self.__finalize_api_gateway_deployments()
        self._store_deployment_stage_reference(api_gateway, stage)

        # Export API Gateway configuration to SSM parameters using enhanced pattern
        self._export_ssm_parameters(api_gateway, authorizer)

        return api_gateway

    def _setup_api_resources_and_methods(self, api_gateway):
        """Setup API Gateway resources and methods from configuration"""
        if not self.api_config.resources:
            return

        for resource_config in self.api_config.resources:
            path = resource_config.get("path")
            if not path:
                continue

            # Create the resource
            resource = (
                api_gateway.root.resource_for_path(path)
                if path != "/"
                else api_gateway.root
            )

            # Add methods to the resource
            methods = resource_config.get("methods", [])
            for method_config in methods:
                self._add_method_to_resource(resource, method_config)

    def _add_method_to_resource(self, resource, method_config):
        """Add a single method to an API Gateway resource"""
        http_method = method_config.get("http_method", "GET")
        integration_type = method_config.get("integration_type", "MOCK")

        # Create the integration
        integration = self._create_method_integration(method_config, integration_type)

        # Create method responses
        method_responses = self._create_method_responses(method_config)

        # Get authorization type
        authorization_type = self._get_authorization_type(method_config)

        # Create the method
        method_options = {}
        if method_responses:
            method_options["method_responses"] = method_responses

        try:
            resource.add_method(
                http_method,
                integration,
                authorization_type=authorization_type,
                api_key_required=method_config.get("api_key_required", False),
                **method_options,
            )
        except Exception as e:
            print(str(e))

    def _create_method_integration(self, method_config, integration_type):
        """Create integration for a method"""
        if integration_type == "MOCK":
            return apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code=response.get("status_code", "200"),
                        response_templates=response.get("response_templates", {}),
                    )
                    for response in method_config.get(
                        "integration_responses", [{"status_code": "200"}]
                    )
                ],
                request_templates=method_config.get("request_templates", {}),
            )
        else:
            # Default to a mock integration if no specific integration is provided
            return apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code="200",
                        response_templates={
                            "application/json": '{"message": "Success"}'
                        },
                    )
                ],
                request_templates={"application/json": '{"statusCode": 200}'},
            )

    def _create_method_responses(self, method_config):
        """Create method responses for a method"""
        method_responses = []
        for response in method_config.get("method_responses", [{"status_code": "200"}]):
            status_code = response.get("status_code", "200")
            response_models = {}

            # Handle response models
            for content_type, model_name in response.get("response_models", {}).items():
                if model_name == "Empty":
                    response_models[content_type] = apigateway.Model.EMPTY_MODEL
                # Add more model mappings as needed

            method_responses.append(
                apigateway.MethodResponse(
                    status_code=status_code, response_models=response_models
                )
            )
        return method_responses

    def _get_authorization_type(self, method_config):
        """Get authorization type for a method"""
        authorization_type = method_config.get(
            "authorization_type", apigateway.AuthorizationType.NONE
        )
        if isinstance(authorization_type, str):
            authorization_type = apigateway.AuthorizationType[authorization_type]
        return authorization_type

    def _setup_api_keys(self):
        """Create API keys if specified in configuration"""
        api_keys = []
        if not self.api_config.api_keys:
            return api_keys

        for key_config in self.api_config.api_keys:
            key_name = key_config.get("name")
            if not key_name:
                continue

            api_key = apigateway.ApiKey(
                self,
                f"{key_name}-key",
                api_key_name=key_name,
                description=key_config.get("description"),
                enabled=key_config.get("enabled", True),
            )
            api_keys.append(api_key)
        return api_keys

    def _setup_usage_plans(self, api_gateway, api_keys):
        """Create usage plans if specified in configuration"""
        if not self.api_config.usage_plans:
            return

        for plan_config in self.api_config.usage_plans:
            plan_name = plan_config.get("name")
            if not plan_name:
                continue

            # Create throttle and quota settings
            throttle = self._create_throttle_settings(plan_config)
            quota = self._create_quota_settings(plan_config)

            # Create the usage plan
            usage_plan = apigateway.UsagePlan(
                self,
                f"{plan_name}-plan",
                name=plan_name,
                description=plan_config.get("description"),
                api_stages=(
                    [
                        apigateway.UsagePlanPerApiStage(
                            api=api_gateway,
                            stage=getattr(api_gateway, "_deployment_stage", None),
                        )
                    ]
                    if hasattr(api_gateway, "_deployment_stage")
                    and api_gateway._deployment_stage
                    else []
                ),
                throttle=throttle,
                quota=quota,
            )

            # Add API keys to the usage plan
            for api_key in api_keys:
                usage_plan.add_api_key(api_key)

    def _create_throttle_settings(self, plan_config):
        """Create throttle settings for usage plan"""
        if not plan_config.get("throttle"):
            return None

        return apigateway.ThrottleSettings(
            rate_limit=plan_config["throttle"].get("rate_limit"),
            burst_limit=plan_config["throttle"].get("burst_limit"),
        )

    def _create_quota_settings(self, plan_config):
        """Create quota settings for usage plan"""
        if not plan_config.get("quota"):
            return None

        return apigateway.QuotaSettings(
            limit=plan_config["quota"].get("limit"),
            period=apigateway.Period[plan_config["quota"].get("period", "MONTH")],
        )

    def _setup_cognito_authorizer(self, api_gateway, api_id, routes=None):
        """Setup Cognito authorizer if configured AND if any routes need it"""
        if not self.api_config.cognito_authorizer:
            return None

        # Use provided routes (discovered routes) or fall back to api_config routes
        check_routes = routes or self.api_config.routes or []
        needs_authorizer = any(
            route.get("authorization_type", "COGNITO") != "NONE"
            for route in check_routes
        )

        # If we're not creating an authorizer but Cognito is configured,
        # inform the integration utility so it can still perform security validations
        if not needs_authorizer:
            logger.info(
                "Cognito authorizer configured but no routes require authorization. "
                "Skipping authorizer creation but maintaining security validation context."
            )
            # Set a flag so the integration utility knows Cognito was available
            self.integration_utility.cognito_configured = True
            return None

        route_config = ApiGatewayConfigRouteConfig({})
        return self.integration_utility.get_or_create_authorizer(
            api_gateway, route_config, self.stack_config, api_id
        )

    def _get_route_suffix(self, route: dict) -> str:
        """
        Calculate a unique suffix for route construct IDs.
        Uses 'name' field if provided, otherwise includes method + path for uniqueness.
        """
        if "name" in route and route["name"]:
            return route["name"]  # Use the unique name provided in config
        else:
            # Include method to ensure uniqueness when same path has multiple methods
            method = route.get("method", "GET").upper()
            path_suffix = route["path"].strip("/").replace("/", "-") or "health"
            return f"{method.lower()}-{path_suffix}"

    def _setup_lambda_routes(self, api_gateway, api_id, routes, authorizer):
        """Setup Lambda routes and integrations"""
        for route in routes:
            # Check if this route references an existing Lambda via SSM
            lambda_arn_ssm_path = route.get("lambda_arn_ssm_path")
            lambda_name_ref = route.get("lambda_name")

            if lambda_arn_ssm_path or lambda_name_ref:
                # Import existing Lambda from SSM
                self._setup_existing_lambda_route(
                    api_gateway, api_id, route, authorizer
                )
            else:
                # Create new Lambda (legacy pattern)
                self._setup_single_lambda_route(api_gateway, api_id, route, authorizer)

    def _setup_existing_lambda_route(self, api_gateway, api_id, route, authorizer):
        """
        Setup API Gateway route with existing Lambda function imported from SSM.
        This is the NEW PATTERN for separating Lambda and API Gateway stacks.
        """
        route_path = route["path"]
        method = route.get("method", "GET").upper()
        suffix = self._get_route_suffix(
            route
        )  # Use shared method for consistent suffix calculation

        # Get Lambda ARN from SSM Parameter Store
        lambda_arn = self._get_lambda_arn_from_ssm(route)

        if not lambda_arn:
            raise ValueError(
                f"Could not resolve Lambda ARN for route {route_path}. "
                f"Ensure Lambda stack has deployed and exported ARN to SSM."
            )

        # Import Lambda function from ARN using fromFunctionAttributes
        # This allows us to add permissions even for imported functions
        lambda_fn = _lambda.Function.from_function_attributes(
            self,
            f"{api_id}-imported-lambda-{suffix}",
            function_arn=lambda_arn,
            same_environment=True,  # Allow permission grants for same-account imports
        )

        logger.info(f"Imported Lambda for route {route_path}: {lambda_arn}")

        # Setup API Gateway resource
        resource = (
            api_gateway.root.resource_for_path(route_path)
            if route_path != "/"
            else api_gateway.root
        )

        # Setup Lambda integration
        self._setup_lambda_integration(
            api_gateway, api_id, route, lambda_fn, authorizer, suffix
        )

        # Setup CORS using centralized utility
        self.integration_utility.setup_route_cors(resource, route_path, route)

        # Process additional routes pointing to the same Lambda
        self._setup_additional_routes(
            api_gateway, api_id, route, lambda_fn, authorizer, is_imported=True
        )

    def _get_lambda_arn_from_ssm(self, route: dict) -> str:
        """
        Get Lambda ARN from SSM Parameter Store.
        Supports both explicit SSM paths and auto-discovery via lambda_name.
        Caches lookups to avoid duplicate construct IDs when the same lambda
        is referenced by multiple routes.
        """
        # Lazy-init the cache
        if not hasattr(self, "_lambda_arn_cache"):
            self._lambda_arn_cache: dict = {}

        # Option 1: Explicit SSM path provided
        lambda_arn_ssm_path = route.get("lambda_arn_ssm_path")
        if lambda_arn_ssm_path:
            if lambda_arn_ssm_path in self._lambda_arn_cache:
                return self._lambda_arn_cache[lambda_arn_ssm_path]

            logger.info(f"Looking up Lambda ARN from SSM: {lambda_arn_ssm_path}")
            try:
                param = ssm.StringParameter.from_string_parameter_name(
                    self,
                    f"lambda-arn-param-{hash(lambda_arn_ssm_path) % 10000}",
                    lambda_arn_ssm_path,
                )
                self._lambda_arn_cache[lambda_arn_ssm_path] = param.string_value
                return param.string_value
            except Exception as e:
                logger.error(
                    f"Failed to retrieve Lambda ARN from SSM path {lambda_arn_ssm_path}: {e}"
                )
                raise

        # Option 2: Auto-discovery via lambda_name
        lambda_name = route.get("lambda_name")
        if lambda_name:
            if lambda_name in self._lambda_arn_cache:
                return self._lambda_arn_cache[lambda_name]

            # Build SSM path using convention from lambda_stack
            # Read SSM imports from top-level ssm block via stack_config
            ssm_imports_config = self.stack_config.ssm_config.get("imports", {})
            namespace = ssm_imports_config.get("lambda_namespace")
            if not namespace:
                raise ValueError(
                    f"Stack '{self.stack_config.name}': "
                    f"'ssm.imports.lambda_namespace' is required for Lambda auto-discovery "
                    f"(route references lambda_name='{lambda_name}'). "
                    f"Add 'ssm.imports.lambda_namespace' to your stack config."
                )
            ssm_path = f"/{namespace}/{lambda_name}/arn"
            logger.info(f"Auto-discovering Lambda ARN from SSM: {ssm_path}")

            try:
                param = ssm.StringParameter.from_string_parameter_name(
                    self, f"lambda-arn-{lambda_name}-param", ssm_path
                )
                self._lambda_arn_cache[lambda_name] = param.string_value
                return param.string_value
            except Exception as e:
                logger.error(
                    f"Failed to auto-discover Lambda ARN for '{lambda_name}' from {ssm_path}: {e}"
                )
                raise ValueError(
                    f"Lambda ARN not found in SSM for '{lambda_name}'. "
                    f"Ensure the Lambda stack has deployed and exported the ARN to: {ssm_path}"
                )

        return None

    def _setup_single_lambda_route(self, api_gateway, api_id, route, authorizer):
        """Setup a single Lambda route with integration and CORS"""
        suffix = self._get_route_suffix(
            route
        )  # Use shared method for consistent suffix calculation
        src = route.get("src")
        handler = route.get("handler")

        # Create Lambda function
        lambda_fn = self.create_lambda(
            api_id=api_id,
            src_dir=src,
            id_suffix=suffix,
            handler=handler,
        )

        route_path = route["path"]
        resource = (
            api_gateway.root.resource_for_path(route_path)
            if route_path != "/"
            else api_gateway.root
        )

        # Setup Lambda integration
        self._setup_lambda_integration(
            api_gateway, api_id, route, lambda_fn, authorizer, suffix
        )

        # Setup CORS using centralized utility
        self.integration_utility.setup_route_cors(resource, route_path, route)

        # Process additional routes pointing to the same Lambda
        self._setup_additional_routes(
            api_gateway, api_id, route, lambda_fn, authorizer, is_imported=False
        )

    def _setup_additional_routes(
        self,
        api_gateway,
        api_id,
        primary_route,
        lambda_fn,
        authorizer,
        is_imported=False,
    ):
        """
        Process additional_routes on a primary route config, creating new API Gateway
        resource + method integrations pointing to the same Lambda function.
        """
        additional_routes = primary_route.get("additional_routes", [])
        if not additional_routes:
            return

        for add_route in additional_routes:
            add_path = add_route["path"]
            add_method = add_route.get(
                "method", primary_route.get("method", "GET")
            ).upper()

            # Build a merged route dict: inherit from primary, override with additional
            merged_route = dict(primary_route)
            merged_route.update(add_route)
            # Ensure method is set
            merged_route["method"] = add_method
            # Remove additional_routes to avoid recursion
            merged_route.pop("additional_routes", None)

            add_suffix = self._get_route_suffix(merged_route)

            # Create API Gateway resource for the additional route
            resource = (
                api_gateway.root.resource_for_path(add_path)
                if add_path != "/"
                else api_gateway.root
            )

            # Setup Lambda integration for the additional route
            self._setup_lambda_integration(
                api_gateway, api_id, merged_route, lambda_fn, authorizer, add_suffix
            )

            # Setup CORS
            self.integration_utility.setup_route_cors(resource, add_path, merged_route)

            logger.info(
                f"Added additional route {add_method} {add_path} -> same Lambda"
            )

    def _validate_authorization_configuration(self, route, has_cognito_authorizer):
        """
        Validate authorization configuration using the shared utility method.

        This delegates to the ApiGatewayIntegrationUtility for consistent validation
        across both API Gateway stack and Lambda stack patterns.
        """
        # Convert route dict to ApiGatewayConfigRouteConfig for utility validation
        # Map "path" to "route" for compatibility with the config object
        route_config_dict = dict(route)  # Create a copy
        if "path" in route_config_dict:
            route_config_dict["route"] = route_config_dict["path"]

        api_route_config = ApiGatewayConfigRouteConfig(route_config_dict)

        # Use the utility's enhanced validation method
        validated_config = (
            self.integration_utility._validate_and_adjust_authorization_configuration(
                api_route_config, has_cognito_authorizer
            )
        )

        # Return the validated authorization type for use in the stack
        return validated_config.authorization_type

    def _setup_lambda_integration(
        self, api_gateway, api_id, route, lambda_fn, authorizer, suffix
    ):
        """Setup Lambda integration for a route"""
        route_path = route["path"]

        # Handle authorization type fallback logic before validation
        authorization_type = route.get("authorization_type", "COGNITO")

        # If no Cognito authorizer available and default COGNITO, fall back to NONE
        if (
            not authorizer
            and authorization_type == "COGNITO"
            and "authorization_type" not in route
        ):
            authorization_type = "NONE"
            logger.warning(
                f"No Cognito authorizer available for route {route_path} ({route.get('method', 'unknown')}), "
                f"defaulting to public access (NONE authorization)"
            )

        # Create a route config with the resolved authorization type for validation
        route_for_validation = dict(route)
        route_for_validation["authorization_type"] = authorization_type

        # Validate authorization configuration using the utility
        validated_authorization_type = self._validate_authorization_configuration(
            route_for_validation, authorizer is not None
        )

        # Use the validated authorization type
        authorization_type = validated_authorization_type

        # If set to NONE (explicitly or by fallback), skip authorization
        if authorization_type == "NONE":
            authorizer = None

        if route.get("src"):
            # Use shared utility for consistent Lambda integration behavior
            api_route_config = ApiGatewayConfigRouteConfig(
                {
                    "method": route["method"],
                    "route": route_path,
                    "authorization_type": authorization_type,
                    "api_key_required": False,
                    "user_pool_id": (
                        os.getenv("COGNITO_USER_POOL_ID") if authorizer else None
                    ),
                    "allow_public_override": route.get("allow_public_override", False),
                }
            )

            # Use shared utility for consistent behavior
            integration_info = self.integration_utility.setup_lambda_integration(
                lambda_fn, api_route_config, api_gateway, self.stack_config
            )

            # Store integration info
            integration_info["function_name"] = f"{api_id}-lambda-{suffix}"
            self.api_gateway_integrations.append(integration_info)
        else:
            # Fallback to original method for non-Lambda integrations
            self._setup_fallback_lambda_integration(
                api_gateway, route, lambda_fn, authorizer, api_id, suffix
            )

    def _setup_fallback_lambda_integration(
        self, api_gateway, route, lambda_fn, authorizer, api_id, suffix
    ):
        """Setup fallback Lambda integration for routes without src"""
        route_path = route["path"]

        # Handle authorization type fallback logic before validation
        authorization_type = route.get("authorization_type", "COGNITO")

        # If no Cognito authorizer available and default COGNITO, fall back to NONE
        if (
            not authorizer
            and authorization_type == "COGNITO"
            and "authorization_type" not in route
        ):
            authorization_type = "NONE"
            logger.warning(
                f"No Cognito authorizer available for route {route_path} ({route.get('method', 'unknown')}), "
                f"defaulting to public access (NONE authorization)"
            )

        # Create a route config with the resolved authorization type for validation
        route_for_validation = dict(route)
        route_for_validation["authorization_type"] = authorization_type

        # Validate authorization configuration using the utility
        validated_authorization_type = self._validate_authorization_configuration(
            route_for_validation, authorizer is not None
        )

        # Use the validated authorization type
        authorization_type = validated_authorization_type

        resource = (
            api_gateway.root.resource_for_path(route_path)
            if route_path != "/"
            else api_gateway.root
        )

        integration = apigateway.LambdaIntegration(lambda_fn)
        method_options = {}

        # Handle authorization type
        if authorization_type.upper() == "NONE":
            method_options["authorization_type"] = apigateway.AuthorizationType.NONE
        elif authorizer:
            method_options["authorization_type"] = apigateway.AuthorizationType.COGNITO
            method_options["authorizer"] = authorizer
        else:
            # Default to COGNITO but no authorizer available
            method_options["authorization_type"] = apigateway.AuthorizationType.COGNITO

        # Add the method with proper options
        try:
            resource.add_method(route["method"].upper(), integration, **method_options)

            # Store integration info for deployment finalization
            integration_info = {
                "api_gateway": api_gateway,
                "function_name": f"{api_id}-lambda-{suffix}",
                "route_path": route_path,
                "method": route["method"].upper(),
            }
            self.api_gateway_integrations.append(integration_info)

        except Exception as e:
            error_msg = f"Failed to create method {route['method'].upper()} on {route_path}: {str(e)}"
            print(error_msg)
            raise Exception(error_msg) from e

    def _store_deployment_stage_reference(self, api_gateway, stage):
        """Store stage reference for later use"""
        if stage:
            api_gateway._deployment_stage = stage
            # Also set it as the deployment_stage property that CDK expects
            try:
                # This is a bit of a hack, but we need to set the deployment stage
                # so that api_gateway.url works properly
                object.__setattr__(api_gateway, "_deployment_stage_internal", stage)
            except (AttributeError, TypeError) as e:
                # Log the error but don't fail the entire deployment
                # This is a non-critical operation for URL generation
                logger.warning(f"Could not set deployment stage internal property: {e}")
                pass

    def __finalize_api_gateway_deployments(self):
        """
        Create new deployments for API Gateways after all routes have been added.
        This ensures that all routes are included in the deployed stage.
        Returns the created stage for the first API Gateway.
        """
        if (
            not hasattr(self, "api_gateway_integrations")
            or not self.api_gateway_integrations
        ):
            logger.info(
                "No API Gateway integrations found, skipping deployment finalization"
            )
            return None

        # Use consolidated utility to group integrations
        from cdk_factory.utilities.api_gateway_integration_utility import (
            ApiGatewayIntegrationUtility,
        )

        utility = ApiGatewayIntegrationUtility(self)
        api_gateways = utility.group_integrations_by_api_gateway(
            self.api_gateway_integrations
        )

        created_stage = None

        # Create deployments and stages using consolidated utility
        for api_key, api_info in api_gateways.items():
            api_gateway = api_info["api_gateway"]
            integrations = api_info["integrations"]
            counter = api_info["counter"]

            # Use consolidated deployment and stage creation
            stage = utility.finalize_api_gateway_deployment(
                api_gateway=api_gateway,
                integrations=integrations,
                stack_config=self.stack_config,
                api_config=self.api_config,
                construct_scope=self,
                counter=counter,
            )

            # Store the first created stage to return
            if created_stage is None:
                created_stage = stage

        return created_stage

    def _export_ssm_parameters(self, api_gateway, authorizer=None):
        """Export API Gateway resources to SSM using top-level ssm config"""

        ssm_config = self.stack_config.ssm_config
        auto_export = self.stack_config.ssm_auto_export
        exports = ssm_config.get("exports", {})

        if not ssm_config or (not auto_export and not exports):
            logger.info("No SSM parameters configured for export")
            return

        # Prepare resource values for export
        resource_values = {
            "api_id": api_gateway.rest_api_id,
            "api_arn": api_gateway.arn_for_execute_api(),
            "root_resource_id": api_gateway.rest_api_root_resource_id,
        }

        # Add URL by constructing it manually since we have a custom deployment pattern
        try:
            region = self.deployment.region
            stage_name = self.api_config.stage_name
            api_url = f"https://{api_gateway.rest_api_id}.execute-api.{region}.amazonaws.com/{stage_name}"
            resource_values["api_url"] = api_url
            logger.info(f"Successfully constructed API URL: {api_url}")
        except Exception as e:
            logger.warning(f"Could not construct API URL: {e}")

        # Add authorizer ID if available
        if authorizer:
            resource_values["authorizer_id"] = authorizer.authorizer_id

        if auto_export:
            namespace = self.stack_config.ssm_namespace
            if not namespace:
                raise ValueError(
                    f"Stack '{self.stack_config.name}': "
                    f"'ssm.namespace' is required when 'ssm.auto_export' is true."
                )
            prefix = f"/{namespace}"
            for export_key, export_value in resource_values.items():
                if export_value is None:
                    continue
                self.export_ssm_parameter(
                    scope=self,
                    id=f"{self.node.id}-{export_key}",
                    value=export_value,
                    parameter_name=f"{prefix}/{export_key}",
                    description=f"API Gateway {export_key}",
                )
            logger.info(
                f"Auto-exported {len(resource_values)} API Gateway parameters to SSM"
            )
        else:
            self.setup_ssm_integration(
                scope=self,
                config=self.stack_config.dictionary,
                resource_type="api-gateway",
                resource_name=self.api_config.name or "api-gateway",
            )
            exported_params = self.export_ssm_parameters(resource_values)
            if exported_params:
                logger.info(
                    f"Exported {len(exported_params)} API Gateway parameters to SSM"
                )

    def _create_http_api(self, api_id: str, routes: List[Dict[str, Any]]):
        # HTTP API (v2)

        api = api_gateway_v2.HttpApi(
            self,
            id=api_id,
            api_name=self.api_config.name,
            description=self.api_config.description,
        )
        logger.info(f"Created HTTP API Gateway: {api.api_name}")
        # Add routes
        for route in routes:
            src = os.path.join(route.get("src"))
            if not src:
                continue
            lambda_fn = self.create_lambda(
                api_id=api_id,
                src_dir=src,
                id_suffix=route["path"].strip("/").replace("/", "-") or "health",
                handler=route.get("handler"),
            )
            route_path = route["path"]
            api.add_routes(
                path=route_path,
                methods=[api_gateway_v2.HttpMethod[route["method"].upper()]],
                integration=integrations.LambdaProxyIntegration(handler=lambda_fn),
            )

    def create_lambda(
        self,
        api_id: str,
        src_dir=None,
        id_suffix="health",
        handler: str | None = None,
    ):
        path = Path(__file__).parents[2]

        src_dir = src_dir or os.path.join(path, "lambdas")
        # src_dir = FileOperations.find_directory(self.workload.paths, src_dir)
        handler = handler or "health_handler.lambda_handler"
        # code_path = lambda_path or os.path.join(path, "lambdas/health_handler.py")
        # handler = handler or "health_handler.lambda_handler"
        if not os.path.exists(src_dir):
            src_dir = FileOperations.find_directory(self.workload.paths, src_dir)
            if not os.path.exists(src_dir):
                raise Exception(f"Lambda code path does not exist: {src_dir}")
        return _lambda.Function(
            self,
            f"{api_id}-lambda-{id_suffix}",
            # TODO need to make this configurable
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=handler,  # or "health_handler.lambda_handler",
            code=_lambda.Code.from_asset(src_dir),
            timeout=cdk.Duration.seconds(10),
        )

    def _setup_log_role(self) -> iam.Role:
        log_role = iam.Role(
            self,
            "ApiGatewayCloudWatchRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )
        return log_role

    def _setup_log_group(self) -> logs.LogGroup:
        log_group = logs.LogGroup(
            self,
            "ApiGatewayLogGroup",
            # don't add the log name, it totally blows up on secondary / redeploys
            # deleting a stack doesn't get rid of the logs and then it conflicts with
            # a new deployment
            # log_group_name=f"/aws/apigateway/{log_name}/access-logs",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,  # Adjust retention as needed
        )

        log_group.grant_write(iam.ServicePrincipal("apigateway.amazonaws.com"))
        log_role = self._setup_log_role()
        log_group.grant_write(log_role)
        return log_group

    def _get_log_format(self) -> apigateway.AccessLogFormat:
        access_log_format = apigateway.AccessLogFormat.custom(
            json.dumps(
                {
                    "requestId": "$context.requestId",
                    "extendedRequestId": "$context.extendedRequestId",
                    "method": "$context.httpMethod",
                    "route": "$context.resourcePath",
                    "status": "$context.status",
                    "requestBody": "$input.body",
                    "responseBody": "$context.responseLength",
                    "headers": "$context.requestHeaders",
                    "requestContext": "$context.requestContext",
                }
            )
        )

        return access_log_format

    def _deploy_options(self) -> apigateway.StageOptions:
        options = apigateway.StageOptions(
            access_log_destination=apigateway.LogGroupLogDestination(
                self._setup_log_group()
            ),
            access_log_format=self._get_log_format(),
            stage_name=self.api_config.deploy_options.get(
                "stage_name", "prod"
            ),  # Ensure this matches your intended deployment stage name
            logging_level=apigateway.MethodLoggingLevel.ERROR,  # Enables CloudWatch logging for all methods
            data_trace_enabled=self.api_config.deploy_options.get(
                "data_trace_enabled", False
            ),  # Includes detailed request/response data in logs
            metrics_enabled=self.api_config.deploy_options.get(
                "metrics_enabled", False
            ),  # Optionally enable detailed CloudWatch metrics (additional costs)
            tracing_enabled=self.api_config.deploy_options.get("tracing_enabled", True),
        )
        return options

    def __setup_custom_domain(self, api: apigateway.RestApi):
        # Support: single dict, array of dicts, or comma-separated domain_names in a single dict
        domains = self.api_config.custom_domains

        # Expand comma-separated domain_names into multiple domain configs
        # e.g., {"domain_names": "api.example.com,v3.api.example.com", "hosted_zone_name": "example.com"}
        # becomes two separate domain configs
        if len(domains) == 1 and "domain_names" in domains[0]:
            template = domains[0]
            names = [
                n.strip() for n in template["domain_names"].split(",") if n.strip()
            ]
            domains = []
            for name in names:
                entry = dict(template)
                entry["domain_name"] = name
                entry.pop("domain_names", None)
                domains.append(entry)

        # Backward compatibility: check old hosted_zone config if no custom_domain
        if not domains:
            record_name = self.api_config.hosted_zone.get("record_name", None)
            if record_name:
                domains = [
                    {
                        "domain_name": record_name,
                        "hosted_zone_id": self.api_config.hosted_zone.get("id"),
                        "hosted_zone_name": self.api_config.hosted_zone.get("name"),
                        "certificate_arn": self.api_config.ssl_cert_arn,
                    }
                ]

        if not domains:
            return

        for i, domain_config in enumerate(domains):
            self.__setup_single_custom_domain(api, domain_config, i)

    def __setup_single_custom_domain(
        self, api: apigateway.RestApi, domain_config: dict, index: int
    ):
        """Setup a single custom domain with certificate, base path mapping, and DNS records."""
        record_name = domain_config.get("domain_name")
        if not record_name:
            return

        # Use index suffix for unique construct IDs (empty for first/only domain)
        suffix = f"-{index}" if index > 0 else ""

        hosted_zone_id = domain_config.get("hosted_zone_id")

        # If hosted_zone_id is not provided, try SSM auto-discovery
        if not hosted_zone_id:
            ssm_imports_config = self.stack_config.ssm_config.get("imports", {})
            route53_ns = ssm_imports_config.get("route53_namespace")
            if route53_ns:
                ssm_path = f"/{route53_ns}/hosted-zone-id"
                logger.info(f"Auto-discovering hosted zone ID from SSM: {ssm_path}")
                param = ssm.StringParameter.from_string_parameter_name(
                    self, f"hosted-zone-id-param{suffix}", ssm_path
                )
                hosted_zone_id = param.string_value

        if not hosted_zone_id:
            raise ValueError(
                f"Hosted zone id is required for custom domain '{record_name}'. "
                "Provide it via custom_domain.hosted_zone_id, or configure "
                "ssm.imports.route53_namespace so it can be auto-discovered from SSM."
            )

        hosted_zone_name = domain_config.get("hosted_zone_name")
        if not hosted_zone_name:
            raise ValueError(
                f"Hosted zone name is required for custom domain '{record_name}'"
            )

        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            f"HostedZone{suffix}",
            hosted_zone_id=hosted_zone_id,
            zone_name=hosted_zone_name,
        )

        certificate: acm.Certificate | None = None
        cert_arn = domain_config.get("certificate_arn") or self.api_config.ssl_cert_arn
        if cert_arn:
            certificate = acm.Certificate.from_certificate_arn(
                self,
                f"ApiCertificate{suffix}",
                cert_arn,
            )
        else:
            certificate = acm.Certificate(
                self,
                id=f"ApiCertificate{suffix}",
                domain_name=record_name,
                validation=acm.CertificateValidation.from_dns(hosted_zone=hosted_zone),
            )

        if certificate:
            api_gateway_domain_resource = apigateway.DomainName(
                self,
                f"ApiCustomDomain{suffix}",
                domain_name=record_name,
                certificate=certificate,
            )

            apigateway.BasePathMapping(
                self,
                f"ApiBasePathMapping{suffix}",
                domain_name=api_gateway_domain_resource,
                rest_api=api,
                stage=getattr(api, "_deployment_stage", None) or api.deployment_stage,
                base_path="",
            )

            route53.ARecord(
                self,
                f"ARecordApi{suffix}",
                zone=hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    aws_route53_targets.ApiGatewayDomain(api_gateway_domain_resource)
                ),
            )

            route53.AaaaRecord(
                self,
                f"AAAARecordApi{suffix}",
                zone=hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    aws_route53_targets.ApiGatewayDomain(api_gateway_domain_resource)
                ),
            )
