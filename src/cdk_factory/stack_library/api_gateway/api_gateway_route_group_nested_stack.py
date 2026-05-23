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

        Returns:
            List of created Method constructs for deployment dependency tracking.
        """
        methods: List[apigateway.Method] = []

        # Step 1: Create path resources for all routes, deduplicating shared segments
        path_resources = self._create_path_resources(
            api_gateway, root_resource_id, routes
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
    ) -> Dict[str, apigateway.Resource]:
        """
        Create API Gateway Resource entries for all path segments.

        Deduplicates shared path segments so multiple routes sharing
        a segment reuse a single resource entry.

        Algorithm:
        1. Import the root resource using from_resource_attributes
        2. For each route, split the path into segments
        3. Build resources incrementally — for each segment, check if a
           resource already exists for that path prefix
        4. If it exists, reuse it. If not, create via add_resource()
        5. Use a dict to track created resources by their full path string

        Args:
            api_gateway: The REST API reference.
            root_resource_id: The root resource ID for path creation.
            routes: List of route configuration dicts.

        Returns:
            Dict mapping full path strings (e.g. "/v3/tenants/{tenant-id}")
            to apigateway.Resource objects.
        """
        # Import the root resource from the parent stack
        root_resource = apigateway.Resource.from_resource_attributes(
            self,
            "imported-root-resource",
            rest_api=api_gateway,
            resource_id=root_resource_id,
            path="/",
        )

        # Dict mapping full path strings to Resource objects
        # The root is represented by "/"
        path_resources: Dict[str, apigateway.Resource] = {"/": root_resource}

        for route in routes:
            route_path = route.get("path", "").rstrip("/")
            if not route_path or route_path == "/":
                continue

            # Split path into segments:
            # "/v3/tenants/{tenant-id}/users" → ["v3", "tenants", "{tenant-id}", "users"]
            segments = [s for s in route_path.strip("/").split("/") if s]

            # Build resources incrementally for each segment
            current_path = ""
            parent_resource = root_resource

            for segment in segments:
                current_path = f"{current_path}/{segment}"

                if current_path in path_resources:
                    # Resource already exists for this path prefix — reuse it
                    parent_resource = path_resources[current_path]
                else:
                    # Create a new resource for this segment
                    # Use sanitized path as construct ID for determinism and uniqueness
                    construct_id = self._sanitize_construct_id(current_path)

                    new_resource = parent_resource.add_resource(
                        segment,
                        default_cors_preflight_options=None,
                    )

                    path_resources[current_path] = new_resource
                    parent_resource = new_resource

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

            resource.add_method(
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
