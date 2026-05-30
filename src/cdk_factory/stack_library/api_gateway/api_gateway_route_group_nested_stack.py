"""
API Gateway Route Group Nested Stack for CDK-Factory.

Contains API Gateway route-specific resources (methods, path resources,
Lambda permissions) for a single domain group. The parent ApiGatewayStack
owns shared resources (REST API, authorizer, deployment, stage) and passes
references to each nested stack.

Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import Any, Dict, List, Set

from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from aws_lambda_powertools import Logger

from cdk_factory.stack_library.stack_base import NestedStackBase
from cdk_factory.utils.api_gateway_utilities import ApiGatewayUtilities

logger = Logger(service="ApiGatewayRouteGroupNestedStack")


class ApiGatewayRouteGroupNestedStack(NestedStackBase):
    """
    Nested stack containing API Gateway route-specific resources
    for a single domain group.

    This stack receives the REST API reference, root resource ID, and
    authorizer reference from the parent stack. It creates only route-specific
    resources: path segments, methods, Lambda permissions, and CORS OPTIONS
    methods.

    It SHALL NOT create its own RestApi, Authorizer, Deployment, or Stage.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

    def build(
        self,
        api_gateway: apigateway.IRestApi,
        root_resource_id: str,
        authorizer: apigateway.IAuthorizer | None,
        routes: List[Dict[str, Any]],
        stack_config: Any,
        cors_config: Dict[str, Any],
        group_name: str,
        shared_prefix: List[str] | None = None,
        api_root_resource_id: str | None = None,
        prefix_resource_ids: List[str] | None = None,
        resource_id_handoff_map: Dict[str, str] | None = None,
    ) -> List[apigateway.Method]:
        """
        Create all route resources for this group.

        Args:
            api_gateway: The REST API reference from the parent stack.
            root_resource_id: The REST API root resource ID for path creation.
            authorizer: The Cognito authorizer reference from the parent stack,
                or None if no authorizer is configured.
            routes: List of route configuration dicts assigned to this group.
            stack_config: The stack configuration for SSM namespace resolution.
            cors_config: Default CORS configuration from the parent stack.
            group_name: Group identifier for construct IDs.
            shared_prefix: (Deprecated) Optional list of shared path segments.
                Use resource_id_handoff_map instead.
            api_root_resource_id: (Deprecated) The actual API root resource ID.
                Use resource_id_handoff_map instead.
            prefix_resource_ids: (Deprecated) List of resource IDs for prefix chain.
                Use resource_id_handoff_map instead.
            resource_id_handoff_map: Dict mapping path prefixes (e.g., "/v3/tenants/{tenant-id}")
                to the API Gateway Resource IDs created by the parent stack at those
                divergence points. The nested stack uses this to determine where to
                attach its exclusive path segments. Key "/" maps to the API root resource.

        Returns:
            List of created Method constructs for deployment dependency tracking.
        """
        methods: List[apigateway.Method] = []

        # Step 1: Create path resources for all routes, deduplicating shared segments
        if resource_id_handoff_map is not None:
            # New trie-based path ownership: use handoff map
            path_resources = self._create_path_resources(
                api_gateway,
                root_resource_id,
                routes,
                resource_id_handoff_map=resource_id_handoff_map,
            )
        else:
            # Legacy path: use shared_prefix/prefix_resource_ids (deprecated)
            path_resources = self._create_path_resources(
                api_gateway,
                root_resource_id,
                routes,
                shared_prefix=shared_prefix,
                api_root_resource_id=api_root_resource_id,
                prefix_resource_ids=prefix_resource_ids,
            )

        # Step 2: Track which paths already have OPTIONS methods to prevent duplicates
        options_created: Set[str] = set()

        # Step 3: Cache for imported Lambda function constructs to avoid
        # duplicate construct IDs when the same Lambda is used by multiple routes
        lambda_fn_cache: Dict[str, _lambda.IFunction] = {}

        # Step 4: Process each route
        for route in routes:
            route_path = route["path"].rstrip("/") or "/"
            http_method = route.get("method", "GET").upper()
            lambda_name = route.get("lambda_name", "")

            # 4a: Resolve the Lambda ARN from SSM (cached to avoid duplicate SSM constructs)
            lambda_arn = self._resolve_lambda_arn(route, stack_config, group_name)

            # Import Lambda function from ARN (cached per unique lambda + method + path)
            suffix = f"{lambda_name}-{http_method}-{route_path}".replace(
                "/", "-"
            ).strip("-")
            fn_cache_key = f"{group_name}-lambda-{suffix}"

            if fn_cache_key in lambda_fn_cache:
                lambda_fn = lambda_fn_cache[fn_cache_key]
            else:
                lambda_fn = _lambda.Function.from_function_attributes(
                    self,
                    fn_cache_key,
                    function_arn=lambda_arn,
                    same_environment=True,
                )
                lambda_fn_cache[fn_cache_key] = lambda_fn

            # 4b: Get the resource for the route's path
            resource = path_resources.get(route_path)
            if not resource:
                raise ValueError(
                    f"Route group '{group_name}': No resource found for path '{route_path}'. "
                    f"This indicates a bug in _create_path_resources()."
                )

            # 4c: Create the method for this route
            method = self._create_route_method(resource, route, authorizer, lambda_fn)

            # 4d: Create Lambda permission for API Gateway invoke access
            self._create_lambda_permission(api_gateway, route, lambda_fn)

            # 4e: Setup CORS OPTIONS method for this resource path
            self._setup_cors_for_resource(
                resource, route_path, route, cors_config, options_created
            )

            # 4f: Append the method to results
            if method:
                methods.append(method)

        logger.info(
            f"Route group '{group_name}': created {len(methods)} methods "
            f"across {len(path_resources)} path resources."
        )

        return methods

    def _create_path_resources(
        self,
        api_gateway: apigateway.IRestApi,
        root_resource_id: str,
        routes: List[Dict[str, Any]],
        shared_prefix: List[str] | None = None,
        api_root_resource_id: str | None = None,
        prefix_resource_ids: List[str] | None = None,
        resource_id_handoff_map: Dict[str, str] | None = None,
    ) -> Dict[str, apigateway.Resource]:
        """
        Create API Gateway Resource entries for all path segments.

        Deduplicates shared path segments so multiple routes sharing
        a segment reuse a single resource entry.

        When resource_id_handoff_map is provided (new trie-based approach):
        - For each route, find the longest matching handoff path in the map
        - Import the resource at that handoff path from the parent stack
        - Create only the remaining (exclusive) path segments below it
        - If a route's entire path is shared, return the imported resource directly

        When shared_prefix is provided (deprecated legacy approach):
        - Full match: strip prefix, start from branch-point (root_resource_id)
        - Partial match: strip matching portion, start from intermediate
          prefix resource (using prefix_resource_ids)
        - No match: start from actual API root (api_root_resource_id)

        Args:
            api_gateway: The REST API reference.
            root_resource_id: The branch-point resource ID (end of prefix chain)
                or API root if no prefix.
            routes: List of route configuration dicts.
            shared_prefix: (Deprecated) Optional list of shared path segments created in parent.
            api_root_resource_id: (Deprecated) The actual API root resource ID for non-matching routes.
            prefix_resource_ids: (Deprecated) List of resource IDs at each prefix depth.
            resource_id_handoff_map: Dict mapping path prefixes (e.g., "/v3/tenants/{tenant-id}")
                to the API Gateway Resource IDs created by the parent stack. Key "/"
                maps to the API root resource.

        Returns:
            Dict mapping full path strings to apigateway.Resource objects.
        """
        # NEW PATH: Use resource_id_handoff_map when provided
        if resource_id_handoff_map is not None:
            return self._create_path_resources_from_handoff_map(
                api_gateway, routes, resource_id_handoff_map
            )

        # LEGACY PATH: Use shared_prefix/prefix_resource_ids (deprecated)
        return self._create_path_resources_legacy(
            api_gateway,
            root_resource_id,
            routes,
            shared_prefix=shared_prefix,
            api_root_resource_id=api_root_resource_id,
            prefix_resource_ids=prefix_resource_ids,
        )

    def _create_path_resources_from_handoff_map(
        self,
        api_gateway: apigateway.IRestApi,
        routes: List[Dict[str, Any]],
        resource_id_handoff_map: Dict[str, str],
    ) -> Dict[str, apigateway.Resource]:
        """
        Create path resources using the trie-based resource_id_handoff_map.

        For each route:
        1. Find the longest matching handoff path in the map
        2. Import the resource at that handoff path from the parent stack
        3. Create only the remaining (exclusive) path segments below it
        4. If a route's entire path matches a handoff path, return the imported
           resource directly (methods attach to it)

        Args:
            api_gateway: The REST API reference.
            routes: List of route configuration dicts.
            resource_id_handoff_map: Dict mapping path prefixes to resource IDs
                from the parent stack.

        Returns:
            Dict mapping full path strings to apigateway.Resource objects.
        """
        # Cache of imported handoff resources to avoid duplicate construct IDs
        imported_handoff_resources: Dict[str, apigateway.Resource] = {}

        # Dict mapping full path strings to Resource objects
        path_resources: Dict[str, apigateway.Resource] = {}

        # Pre-sort handoff paths by length (longest first) for longest-match lookup
        sorted_handoff_paths = sorted(
            resource_id_handoff_map.keys(), key=len, reverse=True
        )

        for route in routes:
            route_path = route.get("path", "").rstrip("/")
            if not route_path or route_path == "/":
                # Root path — import the "/" handoff resource
                if "/" in resource_id_handoff_map:
                    root_res = self._import_handoff_resource(
                        api_gateway,
                        "/",
                        resource_id_handoff_map["/"],
                        imported_handoff_resources,
                    )
                    path_resources["/"] = root_res
                continue

            # Find the longest matching handoff path for this route
            handoff_path = self._find_longest_handoff_match(
                route_path, sorted_handoff_paths
            )

            # Import the handoff resource from the parent stack
            handoff_resource_id = resource_id_handoff_map[handoff_path]
            handoff_resource = self._import_handoff_resource(
                api_gateway,
                handoff_path,
                handoff_resource_id,
                imported_handoff_resources,
            )

            # Determine which segments remain after the handoff point
            if handoff_path == "/":
                # Handoff from API root — all segments are exclusive
                remaining_segments = [s for s in route_path.strip("/").split("/") if s]
            else:
                # Strip the handoff path prefix from the route path
                handoff_segments = [s for s in handoff_path.strip("/").split("/") if s]
                all_segments = [s for s in route_path.strip("/").split("/") if s]
                remaining_segments = all_segments[len(handoff_segments) :]

            # If no remaining segments, the entire path is shared — attach directly
            if not remaining_segments:
                path_resources[route_path] = handoff_resource
                continue

            # Build exclusive resources incrementally below the handoff point
            # Use handoff_path as context key to differentiate paths starting
            # from different handoff points
            parent_resource = handoff_resource
            current_path = handoff_path if handoff_path != "/" else ""

            for segment in remaining_segments:
                current_path = f"{current_path}/{segment}"
                lookup_key = f"handoff:{current_path}"

                if lookup_key in path_resources:
                    parent_resource = path_resources[lookup_key]
                else:
                    new_resource = parent_resource.add_resource(
                        segment,
                        default_cors_preflight_options=None,
                    )
                    path_resources[lookup_key] = new_resource
                    parent_resource = new_resource

            # Map the full original route path to the final resource
            path_resources[route_path] = parent_resource

        return path_resources

    def _find_longest_handoff_match(
        self, route_path: str, sorted_handoff_paths: List[str]
    ) -> str:
        """
        Find the longest handoff path that is a prefix of the given route path.

        The match is segment-based (not character-based) to avoid partial segment
        matches. For example, "/v3/tenants" should NOT match "/v3/tenants-admin/foo".

        Args:
            route_path: The full route path (e.g., "/v3/tenants/{tenant-id}/users").
            sorted_handoff_paths: Handoff paths sorted by length (longest first).

        Returns:
            The longest matching handoff path, or "/" if no other match is found.
        """
        route_segments = [s for s in route_path.strip("/").split("/") if s]

        for handoff_path in sorted_handoff_paths:
            if handoff_path == "/":
                continue  # "/" always matches — use as fallback

            handoff_segments = [s for s in handoff_path.strip("/").split("/") if s]

            # Check if handoff_segments is a prefix of route_segments
            if len(handoff_segments) <= len(route_segments):
                if route_segments[: len(handoff_segments)] == handoff_segments:
                    return handoff_path

        # Fallback to root
        return "/"

    def _import_handoff_resource(
        self,
        api_gateway: apigateway.IRestApi,
        handoff_path: str,
        resource_id: str,
        cache: Dict[str, apigateway.Resource],
    ) -> apigateway.Resource:
        """
        Import a handoff resource from the parent stack, using a cache to avoid
        duplicate construct IDs.

        Args:
            api_gateway: The REST API reference.
            handoff_path: The path key (e.g., "/v3/tenants/{tenant-id}").
            resource_id: The resource ID to import.
            cache: Dict of already-imported resources keyed by handoff_path.

        Returns:
            The imported apigateway.Resource.
        """
        if handoff_path in cache:
            return cache[handoff_path]

        # Generate a stable construct ID from the handoff path
        construct_id = f"imported-handoff-{self._sanitize_construct_id(handoff_path)}"

        resource = apigateway.Resource.from_resource_attributes(
            self,
            construct_id,
            rest_api=api_gateway,
            resource_id=resource_id,
            path=handoff_path,
        )
        cache[handoff_path] = resource
        return resource

    def _create_path_resources_legacy(
        self,
        api_gateway: apigateway.IRestApi,
        root_resource_id: str,
        routes: List[Dict[str, Any]],
        shared_prefix: List[str] | None = None,
        api_root_resource_id: str | None = None,
        prefix_resource_ids: List[str] | None = None,
    ) -> Dict[str, apigateway.Resource]:
        """
        (Deprecated) Create path resources using the legacy shared_prefix approach.

        This method is preserved for backward compatibility during the transition
        to the trie-based resource_id_handoff_map approach.

        Args:
            api_gateway: The REST API reference.
            root_resource_id: The branch-point resource ID (end of prefix chain)
                or API root if no prefix.
            routes: List of route configuration dicts.
            shared_prefix: Optional list of shared path segments created in parent.
            api_root_resource_id: The actual API root resource ID for non-matching routes.
            prefix_resource_ids: List of resource IDs at each prefix depth.

        Returns:
            Dict mapping full path strings to apigateway.Resource objects.
        """
        # Import the branch-point resource (or root if no prefix) from the parent stack
        root_resource = apigateway.Resource.from_resource_attributes(
            self,
            "imported-root-resource",
            rest_api=api_gateway,
            resource_id=root_resource_id,
            path="/",
        )

        # Import intermediate prefix resources for partial prefix matching
        imported_prefix_resources: Dict[int, apigateway.Resource] = {}
        if prefix_resource_ids and shared_prefix:
            for depth, res_id in enumerate(prefix_resource_ids):
                if res_id == root_resource_id:
                    # This is the branch-point — already imported as root_resource
                    imported_prefix_resources[depth] = root_resource
                else:
                    imported_prefix_resources[depth] = (
                        apigateway.Resource.from_resource_attributes(
                            self,
                            f"imported-prefix-depth-{depth}",
                            rest_api=api_gateway,
                            resource_id=res_id,
                            path="/",
                        )
                    )

        # Dict mapping full path strings to Resource objects
        path_resources: Dict[str, apigateway.Resource] = {"/": root_resource}

        for route in routes:
            route_path = route.get("path", "").rstrip("/")
            if not route_path or route_path == "/":
                continue

            # Split path into segments
            segments = [s for s in route_path.strip("/").split("/") if s]

            # Determine which resource to start from based on prefix matching
            start_resource = root_resource
            if shared_prefix:
                prefix_len = len(shared_prefix)
                if (
                    len(segments) >= prefix_len
                    and segments[:prefix_len] == shared_prefix
                ):
                    # Full prefix match — strip prefix, start from branch-point
                    segments = segments[prefix_len:]
                    start_resource = root_resource
                else:
                    # Check for partial prefix match
                    match_depth = 0
                    for i, prefix_seg in enumerate(shared_prefix):
                        if i < len(segments) and segments[i] == prefix_seg:
                            match_depth = i + 1
                        else:
                            break

                    if match_depth > 0 and imported_prefix_resources:
                        # Partial match — strip matching portion, start from
                        # the intermediate prefix resource at that depth
                        segments = segments[match_depth:]
                        start_resource = imported_prefix_resources.get(
                            match_depth, root_resource
                        )
                    elif api_root_resource_id and prefix_resource_ids:
                        # No match at all — start from actual API root
                        start_resource = imported_prefix_resources.get(0, root_resource)
                    # else: no prefix_resource_ids available, fall through to root_resource

            # If all segments were stripped, the route maps to the start resource
            if not segments:
                path_resources[route_path] = start_resource
                continue

            # Build resources incrementally for each segment
            # Use a context prefix in the dict key to differentiate paths that
            # start from different parent resources (e.g., branch-point vs
            # intermediate prefix resource). This prevents collisions when two
            # routes produce the same stripped path but under different parents.
            context_key = id(start_resource)
            current_path = ""
            parent_resource = start_resource

            for segment in segments:
                current_path = f"{current_path}/{segment}"
                lookup_key = f"{context_key}:{current_path}"

                if lookup_key in path_resources:
                    parent_resource = path_resources[lookup_key]
                else:
                    new_resource = parent_resource.add_resource(
                        segment,
                        default_cors_preflight_options=None,
                    )
                    path_resources[lookup_key] = new_resource
                    parent_resource = new_resource

            # Map the full original route path to the final resource
            path_resources[route_path] = parent_resource

        return path_resources

    def _sanitize_construct_id(self, path: str) -> str:
        """
        Sanitize a path string for use as a CDK construct ID.

        Replaces characters that are not valid in construct IDs
        (slashes, braces, etc.) with dashes.

        Args:
            path: The full path string (e.g. "/v3/tenants/{tenant-id}").

        Returns:
            A sanitized string suitable for use as a construct ID.
        """
        sanitized = path.strip("/")
        sanitized = sanitized.replace("/", "-")
        sanitized = sanitized.replace("{", "")
        sanitized = sanitized.replace("}", "")
        return sanitized or "root"

    def _create_route_method(
        self,
        resource: apigateway.Resource,
        route: Dict[str, Any],
        authorizer: apigateway.IAuthorizer | None,
        lambda_fn: _lambda.IFunction,
    ) -> apigateway.Method:
        """
        Create a single Method with Lambda proxy integration for a route.

        Applies the authorizer reference when authorization_type is COGNITO.
        Sets authorization type to NONE when skip_authorizer is true or
        allow_public_override is true.

        Args:
            resource: The API Gateway resource (path) to attach the method to.
            route: The route configuration dict.
            authorizer: The authorizer reference, or None.
            lambda_fn: The Lambda function to integrate with.

        Returns:
            The created Method construct.
        """
        http_method = route.get("method", "GET").upper()
        route_path = route.get("path", "")

        # Create Lambda proxy integration
        integration = apigateway.LambdaIntegration(lambda_fn, proxy=True)

        # Determine authorization type and authorizer to use
        method_options: Dict[str, Any] = {}

        skip_authorizer = route.get("skip_authorizer", False)
        allow_public_override = route.get("allow_public_override", False)
        authorization_type = route.get("authorization_type", "COGNITO").upper()

        if skip_authorizer:
            # Explicit skip — no authorization
            method_options["authorization_type"] = apigateway.AuthorizationType.NONE
        elif allow_public_override and authorization_type == "NONE":
            # Public override explicitly allowed — no authorization
            method_options["authorization_type"] = apigateway.AuthorizationType.NONE
        elif authorizer and authorization_type != "NONE":
            # Cognito authorizer available and route wants auth
            method_options["authorization_type"] = apigateway.AuthorizationType.COGNITO
            method_options["authorizer"] = authorizer
        else:
            # No authorizer configured or route explicitly set to NONE
            method_options["authorization_type"] = apigateway.AuthorizationType.NONE

        # Add the method to the resource
        try:
            method = resource.add_method(
                http_method,
                integration,
                **method_options,
            )

            # Suppress CDK Nag for routes that intentionally skip authorization
            if skip_authorizer or (
                allow_public_override and authorization_type == "NONE"
            ):
                ApiGatewayUtilities.add_nag_suppression(
                    method,
                    apig4_reason="Route is configured with skip_authorizer or allow_public_override",
                    cog4_reason="Route is configured with skip_authorizer or allow_public_override",
                )

            return method
        except Exception as e:
            error_msg = (
                f"Failed to create method {http_method} on {route_path}: {str(e)}"
            )
            logger.error(error_msg)
            raise Exception(error_msg) from e

    def _create_lambda_permission(
        self,
        api_gateway: apigateway.IRestApi,
        route: Dict[str, Any],
        lambda_fn: _lambda.IFunction,
    ) -> None:
        """
        Create Lambda invoke permission scoped to specific method and path.

        Grants API Gateway invoke access for the Lambda integration,
        scoped to the specific HTTP method and resource path of the route.

        The source ARN pattern is:
        arn:aws:execute-api:{region}:{account}:{api-id}/*/{method}{path}

        Args:
            api_gateway: The REST API reference for source ARN construction.
            route: The route configuration dict.
            lambda_fn: The Lambda function to grant permission to.
        """
        method = route.get("method", "GET").upper()
        route_path = route.get("path", "/")

        # Sanitize the construct ID to avoid special characters
        path_sanitized = (
            route_path.strip("/").replace("/", "-").replace("{", "").replace("}", "")
        )
        suffix = (
            f"{method.lower()}-{path_sanitized}" if path_sanitized else method.lower()
        )

        # Create the Lambda permission using CfnPermission (L1 construct)
        # This is required for cross-stack Lambda integrations where the Lambda
        # is imported from another stack via SSM ARN lookup.
        _lambda.CfnPermission(
            self,
            f"lambda-permission-{suffix}",
            action="lambda:InvokeFunction",
            function_name=lambda_fn.function_arn,
            principal="apigateway.amazonaws.com",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{api_gateway.rest_api_id}/*/{method}{route_path}",
        )

    def _setup_cors_for_resource(
        self,
        resource: apigateway.Resource,
        route_path: str,
        route: Dict[str, Any],
        cors_config: Dict[str, Any],
        options_created: Set[str],
    ) -> None:
        """
        Create OPTIONS method with Mock Integration for CORS preflight.

        Uses route-level CORS config if present, otherwise falls back to
        the parent default CORS config. Tracks created OPTIONS paths to
        prevent duplicate creation.

        If the route has `_skip_cors` set to True, this method skips OPTIONS
        creation for that path. This is used when another nested stack owns
        the OPTIONS method for a shared path (Requirement 8.4).

        Args:
            resource: The API Gateway resource to add OPTIONS to.
            route_path: The full path string for tracking.
            route: The route configuration dict (may contain route-level CORS).
            cors_config: Default CORS configuration from the parent stack.
            options_created: Set of paths that already have OPTIONS methods.
        """
        # Check if this route's CORS is owned by another group — skip if so
        if route.get("_skip_cors", False):
            logger.info(
                f"CORS for path '{route_path}' is owned by another group, "
                f"skipping OPTIONS creation in this nested stack."
            )
            return

        # Check if OPTIONS already created for this path — skip if so
        if route_path in options_created:
            logger.info(
                f"OPTIONS method already exists for path '{route_path}', "
                f"skipping duplicate creation."
            )
            return

        # Determine CORS config: route-level overrides parent default
        effective_cors = route.get("cors", {}) or cors_config or {}

        # Extract allowed methods, origins, and headers from the effective config
        allowed_methods = effective_cors.get(
            "allow_methods",
            ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
        )
        allowed_origins = effective_cors.get("allow_origins", ["*"])
        allowed_headers = effective_cors.get(
            "allow_headers",
            [
                "Content-Type",
                "X-Amz-Date",
                "Authorization",
                "X-Api-Key",
                "X-Amz-Security-Token",
            ],
        )

        # Normalize to comma-separated strings
        if isinstance(allowed_methods, list):
            allowed_methods_str = ",".join(allowed_methods)
        else:
            allowed_methods_str = str(allowed_methods)

        if isinstance(allowed_origins, list):
            allowed_origins_str = ",".join(allowed_origins)
        else:
            allowed_origins_str = str(allowed_origins)

        if isinstance(allowed_headers, list):
            allowed_headers_str = ",".join(allowed_headers)
        else:
            allowed_headers_str = str(allowed_headers)

        try:
            options_integration = apigateway.MockIntegration(
                integration_responses=[
                    apigateway.IntegrationResponse(
                        status_code="200",
                        response_parameters={
                            "method.response.header.Access-Control-Allow-Headers": f"'{allowed_headers_str}'",
                            "method.response.header.Access-Control-Allow-Methods": f"'{allowed_methods_str}'",
                            "method.response.header.Access-Control-Allow-Origin": f"'{allowed_origins_str}'",
                        },
                    )
                ],
                passthrough_behavior=apigateway.PassthroughBehavior.NEVER,
                request_templates={"application/json": '{"statusCode": 200}'},
            )

            options_method = resource.add_method(
                "OPTIONS",
                options_integration,
                method_responses=[
                    apigateway.MethodResponse(
                        status_code="200",
                        response_parameters={
                            "method.response.header.Access-Control-Allow-Headers": True,
                            "method.response.header.Access-Control-Allow-Methods": True,
                            "method.response.header.Access-Control-Allow-Origin": True,
                        },
                    )
                ],
                authorization_type=apigateway.AuthorizationType.NONE,
            )

            # Suppress CDK Nag rules for OPTIONS — preflight requests cannot carry auth
            ApiGatewayUtilities.add_nag_suppression(
                options_method,
                apig4_reason="OPTIONS method does not require authorization",
                cog4_reason="OPTIONS method does not require authorization or Cognito",
            )

            # Track that OPTIONS has been created for this path
            options_created.add(route_path)

        except Exception as e:
            if "There is already a Construct with name 'OPTIONS'" in str(e):
                logger.warning(
                    f"OPTIONS method already exists for path '{route_path}', "
                    f"skipping duplicate creation."
                )
                # Still track it to prevent further attempts
                options_created.add(route_path)
            else:
                logger.error(
                    f"Failed to create OPTIONS method for path '{route_path}': {e}"
                )
                raise

    def _resolve_lambda_arn(
        self,
        route: Dict[str, Any],
        stack_config: Any,
        group_name: str,
    ) -> str:
        """
        Resolve a Lambda ARN from SSM Parameter Store.

        Supports both explicit SSM paths (via route's `lambda_arn_ssm_path`)
        and auto-discovery via `lambda_name`. Caches lookups to avoid
        duplicate construct IDs when the same Lambda is referenced by
        multiple routes.

        The SSM path convention is: /{lambda_namespace}/{lambda_name}/arn
        where lambda_namespace comes from stack_config.ssm_config["imports"]["lambda_namespace"].

        Args:
            route: The route configuration dict containing lambda_name or
                lambda_arn_ssm_path.
            stack_config: The stack configuration containing SSM import settings.
            group_name: The route group name for construct ID namespacing.

        Returns:
            The resolved Lambda ARN string.

        Raises:
            ValueError: If lambda_namespace is not configured or the Lambda
                ARN cannot be resolved.
        """
        # Lazy-init the cache
        if not hasattr(self, "_lambda_arn_cache"):
            self._lambda_arn_cache: Dict[str, str] = {}

        # Option 1: Explicit SSM path provided
        lambda_arn_ssm_path = route.get("lambda_arn_ssm_path")
        if lambda_arn_ssm_path:
            if lambda_arn_ssm_path in self._lambda_arn_cache:
                return self._lambda_arn_cache[lambda_arn_ssm_path]

            logger.info(f"Looking up Lambda ARN from SSM: {lambda_arn_ssm_path}")
            try:
                param = ssm.StringParameter.from_string_parameter_name(
                    self,
                    f"{group_name}-lambda-arn-param-{hash(lambda_arn_ssm_path) % 10000}",
                    lambda_arn_ssm_path,
                )
                self._lambda_arn_cache[lambda_arn_ssm_path] = param.string_value
                return param.string_value
            except Exception as e:
                logger.error(
                    f"Failed to retrieve Lambda ARN from SSM path "
                    f"{lambda_arn_ssm_path}: {e}"
                )
                raise ValueError(
                    f"Route group '{group_name}': Failed to resolve Lambda ARN "
                    f"from SSM path '{lambda_arn_ssm_path}'. "
                    f"Ensure the Lambda stack has deployed and exported the ARN."
                ) from e

        # Option 2: Auto-discovery via lambda_name
        lambda_name = route.get("lambda_name")
        if lambda_name:
            if lambda_name in self._lambda_arn_cache:
                return self._lambda_arn_cache[lambda_name]

            # Build SSM path using convention: /{lambda_namespace}/{lambda_name}/arn
            ssm_imports_config = stack_config.ssm_config.get("imports", {})
            namespace = ssm_imports_config.get("lambda_namespace")
            if not namespace:
                raise ValueError(
                    f"Route group '{group_name}': "
                    f"'ssm.imports.lambda_namespace' is required for Lambda ARN resolution "
                    f"(route references lambda_name='{lambda_name}'). "
                    f"Add 'ssm.imports.lambda_namespace' to your stack config."
                )

            ssm_path = f"/{namespace}/{lambda_name}/arn"
            logger.info(f"Auto-discovering Lambda ARN from SSM: {ssm_path}")

            try:
                param = ssm.StringParameter.from_string_parameter_name(
                    self,
                    f"{group_name}-lambda-arn-{lambda_name}-param",
                    ssm_path,
                )
                self._lambda_arn_cache[lambda_name] = param.string_value
                return param.string_value
            except Exception as e:
                logger.error(
                    f"Failed to auto-discover Lambda ARN for '{lambda_name}' "
                    f"from {ssm_path}: {e}"
                )
                raise ValueError(
                    f"Lambda ARN not found in SSM for '{lambda_name}'. "
                    f"Expected path: /{namespace}/{lambda_name}/arn. "
                    f"Ensure the Lambda stack has deployed and exported the ARN."
                ) from e

        raise ValueError(
            f"Route group '{group_name}': Route for path '{route.get('path')}' "
            f"has no 'lambda_name' or 'lambda_arn_ssm_path'. "
            f"Cannot resolve Lambda ARN."
        )
