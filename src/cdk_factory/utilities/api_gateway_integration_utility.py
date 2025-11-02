"""
API Gateway Integration Utility for CDK-Factory
Shared utility for Lambda API Gateway integrations
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
from typing import Optional
import aws_cdk as cdk
import json
import time
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_logs as logs
from aws_cdk import aws_iam as iam
from cdk_factory.utils.api_gateway_utilities import ApiGatewayUtilities
from aws_cdk import RemovalPolicy
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.configurations.resources.apigateway_route_config import (
    ApiGatewayConfigRouteConfig,
)
from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig
from cdk_factory.configurations.stack import StackConfig

logger = Logger(service="ApiGatewayIntegrationUtility")


class ApiGatewayIntegrationUtility:
    """Utility class for API Gateway Lambda integrations"""

    def __init__(self, scope: Construct):
        self.scope = scope
        self.region = scope.region
        self.account = scope.account
        self.api_gateway = None
        self.authorizer = None
        self.cognito_configured = False  # Flag for when Cognito is configured but authorizer not created
        self._log_group = None
        self._log_role = None

    def setup_lambda_integration(
        self,
        lambda_function: _lambda.Function,
        api_config: ApiGatewayConfigRouteConfig,
        api_gateway: apigateway.RestApi,
        stack_config,
    ) -> dict:
        """Setup API Gateway integration for Lambda function"""
        if not api_config:
            raise ValueError("API Gateway config is missing in Lambda function config")

        # Validate authorization configuration for security
        # Check if Cognito is available (either authorizer created OR configured but not created)
        has_cognito_authorizer = (
            self.authorizer is not None
            or self.cognito_configured
            or self._get_existing_authorizer_id_with_ssm_fallback(
                api_config, stack_config
            )
            is not None
        )

        # Apply enhanced authorization validation and fallback logic
        api_config = self._validate_and_adjust_authorization_configuration(
            api_config, has_cognito_authorizer
        )

        # Get or create authorizer if needed (only for COGNITO_USER_POOLS authorization)
        if api_config.authorization_type != "NONE" and not self.authorizer:
            self.authorizer = self.get_or_create_authorizer(
                api_gateway, api_config, stack_config
            )

        # Create integration
        integration = apigateway.LambdaIntegration(
            lambda_function,
            proxy=True,
            allow_test_invoke=True,
        )

        # Add method to API Gateway
        resource = self.get_or_create_resource(
            api_gateway, api_config.routes, stack_config
        )

        # Handle existing authorizer ID using L1 constructs
        if self._get_existing_authorizer_id_with_ssm_fallback(api_config, stack_config):
            method = self._create_method_with_existing_authorizer(
                api_gateway, resource, lambda_function, api_config, stack_config
            )
        else:
            # Use L2 constructs for new authorizers
            # Determine authorization type and authorizer based on authorization_type
            if api_config.authorization_type == "NONE":
                # Public access - no authorization required
                auth_type = apigateway.AuthorizationType.NONE
                authorizer_to_use = None
            elif self.authorizer:
                # Cognito authorization with existing authorizer
                auth_type = apigateway.AuthorizationType.COGNITO
                authorizer_to_use = self.authorizer
            else:
                # Use configured authorization type
                auth_type = apigateway.AuthorizationType[api_config.authorization_type]
                authorizer_to_use = None

            method = None
            try:
                method = resource.add_method(
                    api_config.method.upper(),
                    integration,
                    authorizer=authorizer_to_use,
                    api_key_required=api_config.api_key_required,
                    request_parameters=api_config.request_parameters,
                    authorization_type=auth_type,
                )
            except Exception as e:
                error_msg = f"Failed to create method {api_config.method.upper()} on {api_config.routes}: {str(e)}"
                print(error_msg)
                raise Exception(error_msg) from e
        # Return integration info for potential cross-stack references
        return {
            "api_gateway": api_gateway,
            "method": method,
            "resource": resource,
            "integration": integration,
        }

    def get_or_create_api_gateway(
        self,
        api_config: ApiGatewayConfigRouteConfig,
        stack_config,
        existing_integrations: list = None,
    ) -> apigateway.RestApi:
        """Get existing API Gateway or create new one"""
        # Check for existing API Gateway ID

        if self.api_gateway:
            return self.api_gateway

        api_gateway_id = self._get_existing_api_gateway_id_with_ssm_fallback(
            api_config, stack_config
        )

        if api_gateway_id:
            # Import existing API Gateway
            root_resource_id = self._get_root_resource_id_with_ssm_fallback(
                stack_config
            )

            if root_resource_id:
                logger.info(
                    f"Using existing API Gateway {api_gateway_id} with root resource {root_resource_id}"
                )
                self.api_gateway = apigateway.RestApi.from_rest_api_attributes(
                    self.scope,
                    f"imported-api-{api_gateway_id}",
                    rest_api_id=api_gateway_id,
                    root_resource_id=root_resource_id,
                )
                return self.api_gateway
            else:
                logger.warning(
                    f"No root_resource_id provided for API Gateway {api_gateway_id}. "
                    "Using from_rest_api_id() - this may cause validation issues in some CDK versions."
                )
                try:
                    self.api_gateway = apigateway.RestApi.from_rest_api_id(
                        self.scope,
                        f"imported-api-{api_gateway_id}",
                        api_gateway_id,
                    )
                    return self.api_gateway
                except Exception as e:
                    if "ValidationError" in str(e) and "root is not configured" in str(
                        e
                    ):
                        logger.error(
                            f"Cannot import API Gateway {api_gateway_id} without root_resource_id. "
                            "Please add 'root_resource_id' to your api_gateway configuration."
                        )
                        raise ValueError(
                            f"API Gateway {api_gateway_id} requires 'root_resource_id' in configuration. "
                            "Add 'root_resource_id' to your api_gateway config section."
                        ) from e
                    else:
                        raise

        # Check if we already created an API in this stack
        if existing_integrations:
            for integration in existing_integrations:
                if integration.get("api_gateway"):
                    return integration["api_gateway"]

        # Create new REST API using centralized creation logic
        api_id = f"{stack_config.name}-api"
        self.api_gateway = self._create_rest_api_with_full_config(api_id, stack_config)

        return self.api_gateway

    def create_api_gateway_with_config(
        self, api_id: str, api_config: ApiGatewayConfig, stack_config: StackConfig
    ) -> apigateway.RestApi:
        """Create API Gateway using the full configuration from api_gateway_stack pattern"""
        return self._create_rest_api_with_full_config_from_api_config(
            api_id, api_config, stack_config
        )

    def _create_rest_api_with_full_config_from_api_config(
        self, api_id: str, api_config: ApiGatewayConfig, stack_config: StackConfig
    ) -> apigateway.RestApi:
        """Create REST API using ApiGatewayConfig object (from api_gateway_stack)"""
        from aws_cdk import aws_logs as logs
        from aws_cdk import aws_iam as iam
        from aws_cdk import Size
        import json

        # Get the API name from the config
        api_name = api_config.name or "api-gateway"

        # Create log group for API Gateway access logs
        log_group = logs.LogGroup(
            self.scope,
            f"{api_id}-log-group",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,
        )

        # Create log role for API Gateway
        log_role = iam.Role(
            self.scope,
            f"{api_id}-log-role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )

        log_group.grant_write(iam.ServicePrincipal("apigateway.amazonaws.com"))
        log_group.grant_write(log_role)

        # Access log format
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

        # Stage options with comprehensive configuration
        stage_options = apigateway.StageOptions(
            access_log_destination=apigateway.LogGroupLogDestination(log_group),
            access_log_format=access_log_format,
            stage_name=api_config.stage_name,
            logging_level=apigateway.MethodLoggingLevel.ERROR,
            data_trace_enabled=api_config.deploy_options.get(
                "data_trace_enabled", False
            ),
            metrics_enabled=api_config.deploy_options.get("metrics_enabled", False),
            tracing_enabled=api_config.deploy_options.get("tracing_enabled", True),
            throttling_rate_limit=api_config.deploy_options.get(
                "throttling_rate_limit", 1000
            ),
            throttling_burst_limit=api_config.deploy_options.get(
                "throttling_burst_limit", 2000
            ),
        )

        # Handle endpoint types
        endpoint_types = api_config.endpoint_types
        if endpoint_types:
            endpoint_types = [
                apigateway.EndpointType[e] if isinstance(e, str) else e
                for e in endpoint_types
            ]

        # Handle min compression size
        min_compression_size = api_config.min_compression_size
        if isinstance(min_compression_size, int):
            min_compression_size = Size.mebibytes(min_compression_size)

        # Build kwargs with all configuration options from ApiGatewayConfig
        kwargs = {
            "rest_api_name": api_name,
            "description": api_config.description,
            "deploy": False,  # Always create without initial deployment to prevent stage conflicts
            # Note: deploy_options removed when deploy=False to avoid CDK error
            "endpoint_types": endpoint_types,
            "api_key_source_type": api_config.api_key_source_type,
            "binary_media_types": api_config.binary_media_types,
            "cloud_watch_role": api_config.cloud_watch_role,
            "default_cors_preflight_options": api_config.default_cors_preflight_options,
            "default_method_options": api_config.default_method_options,
            "default_integration": api_config.default_integration,
            "disable_execute_api_endpoint": api_config.disable_execute_api_endpoint,
            "endpoint_export_name": api_config.endpoint_export_name,
            "fail_on_warnings": api_config.fail_on_warnings,
            "min_compression_size": min_compression_size,
            "parameters": api_config.parameters,
            "policy": api_config.policy,
            "retain_deployments": api_config.retain_deployments,
            "rest_api_id": api_config.rest_api_id,
            "root_resource_id": api_config.root_resource_id,
            "cloud_watch_role_removal_policy": api_config.cloud_watch_role_removal_policy,
        }

        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        # Create the REST API
        api_gateway = apigateway.RestApi(
            self.scope,
            api_id,
            **kwargs,
        )

        logger.info(f"Created API Gateway: {api_gateway.rest_api_name}")
        return api_gateway

    def _create_rest_api_with_full_config(
        self, api_id: str, stack_config
    ) -> apigateway.RestApi:
        """Create REST API with full configuration options like api_gateway_stack"""
        from aws_cdk import aws_logs as logs
        from aws_cdk import aws_iam as iam
        from aws_cdk import Size
        import json

        # Get API Gateway config from stack config, with sensible defaults
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})

        # API name
        api_name = api_gateway_config.get("name", f"{stack_config.name}-api")

        # Deployment options
        deploy_options = api_gateway_config.get("deploy_options", {})
        stage_name = api_gateway_config.get("stage_name", "prod")

        # Create log group for API Gateway access logs
        log_group = logs.LogGroup(
            self.scope,
            f"{api_id}-log-group",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,
        )

        # Create log role for API Gateway
        log_role = iam.Role(
            self.scope,
            f"{api_id}-log-role",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )

        log_group.grant_write(iam.ServicePrincipal("apigateway.amazonaws.com"))
        log_group.grant_write(log_role)

        # Access log format
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

        # Stage options with comprehensive configuration
        stage_options = apigateway.StageOptions(
            access_log_destination=apigateway.LogGroupLogDestination(log_group),
            access_log_format=access_log_format,
            stage_name=stage_name,
            logging_level=apigateway.MethodLoggingLevel.ERROR,
            data_trace_enabled=deploy_options.get("data_trace_enabled", False),
            metrics_enabled=deploy_options.get("metrics_enabled", False),
            tracing_enabled=deploy_options.get("tracing_enabled", True),
            throttling_rate_limit=deploy_options.get("throttling_rate_limit", 1000),
            throttling_burst_limit=deploy_options.get("throttling_burst_limit", 2000),
        )

        # Build kwargs with all possible configuration options
        kwargs = {
            "rest_api_name": api_name,
            "description": api_gateway_config.get(
                "description", f"API Gateway for {stack_config.name} Lambda functions"
            ),
            "deploy": api_gateway_config.get("deploy", True),
            "deploy_options": stage_options,
            "cloud_watch_role": api_gateway_config.get("cloud_watch_role", True),
            "default_cors_preflight_options": self._get_default_cors_options(
                api_gateway_config
            ),
            "fail_on_warnings": api_gateway_config.get("fail_on_warnings", False),
            "retain_deployments": api_gateway_config.get("retain_deployments", False),
        }

        # Add optional parameters if they exist
        if api_gateway_config.get("endpoint_types"):
            endpoint_types = [
                apigateway.EndpointType[e] if isinstance(e, str) else e
                for e in api_gateway_config["endpoint_types"]
            ]
            kwargs["endpoint_types"] = endpoint_types

        if api_gateway_config.get("api_key_source_type"):
            kwargs["api_key_source_type"] = api_gateway_config["api_key_source_type"]

        if api_gateway_config.get("binary_media_types"):
            kwargs["binary_media_types"] = api_gateway_config["binary_media_types"]

        if api_gateway_config.get("min_compression_size"):
            min_compression_size = api_gateway_config["min_compression_size"]
            if isinstance(min_compression_size, int):
                min_compression_size = Size.mebibytes(min_compression_size)
            kwargs["min_compression_size"] = min_compression_size

        if api_gateway_config.get("parameters"):
            kwargs["parameters"] = api_gateway_config["parameters"]

        if api_gateway_config.get("policy"):
            kwargs["policy"] = api_gateway_config["policy"]

        if api_gateway_config.get("disable_execute_api_endpoint"):
            kwargs["disable_execute_api_endpoint"] = api_gateway_config[
                "disable_execute_api_endpoint"
            ]

        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        # Create the REST API
        api_gateway = apigateway.RestApi(
            self.scope,
            api_id,
            **kwargs,
        )

        logger.info(f"Created API Gateway: {api_gateway.rest_api_name}")
        return api_gateway

    def _get_default_cors_options(
        self, api_gateway_config: dict
    ) -> apigateway.CorsOptions:
        """Get default CORS options with configuration override capability"""
        cors_config = api_gateway_config.get("default_cors_preflight_options")

        if cors_config:
            return cors_config

        # Default CORS configuration
        return apigateway.CorsOptions(
            allow_origins=apigateway.Cors.ALL_ORIGINS,
            allow_methods=apigateway.Cors.ALL_METHODS,
            allow_headers=[
                "Content-Type",
                "X-Amz-Date",
                "Authorization",
                "X-Api-Key",
            ],
        )

    def get_or_create_authorizer(
        self,
        api_gateway: apigateway.RestApi,
        api_config: ApiGatewayConfigRouteConfig,
        stack_config,
        api_id: str | None = None,
    ) -> Optional[apigateway.Authorizer]:
        """Get existing authorizer or create new one"""
        # Check if we should reference existing authorizer

        if self.authorizer:
            return self.authorizer

        if self._get_existing_authorizer_id_with_ssm_fallback(api_config, stack_config):
            # For existing authorizers, we'll handle this in the method creation
            # using L1 constructs which support authorizer_id parameter
            return None

        # Check if authorizer already exists for this API
        authorizer_id = f"{api_id or api_gateway.rest_api_name}-authorizer"

        # Get user pool from multiple sources with SSM support
        user_pool_id = None
        user_pool_arn = None

        # First try to get from api_config
        user_pool_id = api_config.user_pool_id or os.getenv("COGNITO_USER_POOL_ID")

        # Check if stack config has cognito_authorizer configuration
        cognito_config = stack_config.dictionary.get("cognito_authorizer", {})
        if not cognito_config:
            cognito_config = stack_config.dictionary.get("api_gateway", {}).get(
                "cognito_authorizer", {}
            )
        if cognito_config:
            # Try to get user_pool_arn directly
            user_pool_arn = cognito_config.get("user_pool_arn")

            # If not found, try SSM parameter lookup using enhanced pattern
            if not user_pool_arn:
                # Check for new ssm_imports pattern in API Gateway configuration
                api_gateway_config = stack_config.dictionary.get("api_gateway", {})
                ssm_config = api_gateway_config.get("ssm", {})
                ssm_imports = ssm_config.get("imports", {})
                ssm_path = ssm_imports.get("user_pool_arn") or cognito_config.get(
                    "user-pool-arn"
                )

                if ssm_path:
                    # Use enhanced SSM parameter import with auto-discovery support
                    from cdk_factory.interfaces.standardized_ssm_mixin import (
                        StandardizedSsmMixin,
                    )

                    ssm_mixin = StandardizedSsmMixin()

                    # Setup enhanced SSM integration for auto-import
                    # Use "user-pool" as resource identifier for SSM paths to match cognito exports
                    api_gateway_config = stack_config.dictionary.get("api_gateway", {}).copy()
                    
                    # Configure SSM imports for auto-discovery
                    if ssm_path == "auto":
                        if "ssm" not in api_gateway_config:
                            api_gateway_config["ssm"] = {}
                        if "imports" not in api_gateway_config["ssm"]:
                            api_gateway_config["ssm"]["imports"] = {}
                        api_gateway_config["ssm"]["imports"]["user_pool_arn"] = "/{{ORGANIZATION}}/{{ENVIRONMENT}}/cognito/user-pool/arn"
                    
                    ssm_mixin.setup_ssm_integration(
                        scope=self.scope,
                        config=api_gateway_config,
                        resource_type="cognito",
                        resource_name="user-pool",
                    )

                    # Get user pool ARN using new pattern - read directly from config
                    if ssm_path == "auto":
                        logger.info("Using auto-import for user pool ARN")
                        ssm_imports = api_gateway_config.get("ssm", {}).get("imports", {})
                        user_pool_arn = ssm_imports.get("user_pool_arn")
                    else:
                        # Use direct parameter import for specific SSM path
                        logger.info(
                            f"Looking up user pool ARN from SSM parameter: {ssm_path}"
                        )
                        user_pool_arn = ssm_mixin._resolve_single_ssm_import(ssm_path, "user_pool_arn")

            # Extract user pool ID from ARN if we have it
            if user_pool_arn and not user_pool_id:
                # ARN format: arn:aws:cognito-idp:region:account:userpool/pool_id
                user_pool_id = user_pool_arn.split("/")[-1]

        # Final validation
        if not user_pool_id:
            raise ValueError(
                "User pool ID is required for API Gateway authorizer. "
                "Provide via COGNITO_USER_POOL_ID environment variable, "
                "api_config.user_pool_id, stack_config.cognito_authorizer.user_pool_arn, "
                "or stack_config.cognito_authorizer.user_pool_arn_ssm_path"
            )

        if user_pool_arn:
            user_pool = cognito.UserPool.from_user_pool_arn(
                scope=self.scope,
                id=f"{api_id}-user-pool",
                user_pool_arn=user_pool_arn,
            )
        else:
            user_pool = cognito.UserPool.from_user_pool_id(
                scope=self.scope,
                id=f"{api_id}-user-pool",
                user_pool_id=user_pool_id,
            )
        # Create Cognito authorizer
        # self.authorizer = apigateway.CognitoUserPoolsAuthorizer(
        #     self.scope,
        #     authorizer_id,
        #     cognito_user_pools=[user_pool],
        #     identity_source="method.request.header.Authorization",
        # )

        authorizer_name = (
            stack_config.dictionary.get("api_gateway", {})
            .get("cognito_authorizer", {})
            .get("authorizer_name", "CognitoAuthorizer")
        )
        identity_source = (
            stack_config.dictionary.get("api_gateway", {})
            .get("cognito_authorizer", {})
            .get("identity_source", "method.request.header.Authorization")
        )
        self.authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self.scope,
            f"{api_id}-authorizer",
            cognito_user_pools=[user_pool],
            authorizer_name=authorizer_name,
            identity_source=identity_source,
        )
        
        # The authorizer is automatically attached to the API Gateway when used in a method
        # But we need to ensure it's created in the context of the API's scope
        # The actual attachment happens when the authorizer is referenced in method creation

        return self.authorizer

    def get_or_create_resource(
        self, api_gateway: apigateway.RestApi, route_path: str, stack_config=None
    ) -> apigateway.Resource:
        """Get or create API Gateway resource for the given route path with cross-stack support"""
        if not route_path or route_path == "/":
            return api_gateway.root

        # Check for existing resource import configuration
        if stack_config:
            api_gateway_config = stack_config.dictionary.get("api_gateway", {})
            existing_resources = api_gateway_config.get("existing_resources", {})

            if existing_resources:
                return self._create_resource_with_imports(
                    api_gateway, route_path, existing_resources
                )

        # Use the built-in resource_for_path method which handles existing resources correctly
        try:
            # This method automatically creates the full path and reuses existing resources
            return api_gateway.root.resource_for_path(route_path)
        except Exception as e:
            logger.warning(f"Failed to create resource for path {route_path}: {e}")
            # Fallback to manual creation if needed
            return self._create_resource_manually(api_gateway, route_path)

    def _create_resource_manually(
        self, api_gateway: apigateway.RestApi, route_path: str
    ) -> apigateway.Resource:
        """Manually create resource path as fallback"""
        # Remove leading slash and split path
        path_parts = route_path.lstrip("/").split("/")
        current_resource = api_gateway.root

        # Navigate/create nested resources
        for part in path_parts:
            if not part:  # Skip empty parts
                continue

            # Check if resource already exists using a more robust method
            existing_resource = None
            try:
                # Try to find existing resource by checking all children
                for child in current_resource.node.children:
                    if (
                        hasattr(child, "path_part")
                        and getattr(child, "path_part", None) == part
                    ):
                        existing_resource = child
                        break

                if existing_resource:
                    current_resource = existing_resource
                else:
                    # Create new resource
                    current_resource = current_resource.add_resource(part)

            except Exception as e:
                logger.error(f"Error creating resource part '{part}': {e}")
                # Try to continue with existing resource if creation fails
                if existing_resource:
                    current_resource = existing_resource
                else:
                    raise

        return current_resource

    def _create_resource_with_imports(
        self, api_gateway: apigateway.RestApi, route_path: str, existing_resources: dict
    ) -> apigateway.Resource:
        """Create resource path using existing resource imports to avoid conflicts"""
        from aws_cdk import aws_apigateway as apigateway

        # Remove leading slash and split path
        path_parts = route_path.lstrip("/").split("/")
        current_resource = api_gateway.root
        current_path = ""

        # Navigate through path parts, importing existing resources where configured
        for i, part in enumerate(path_parts):
            if not part:  # Skip empty parts
                continue

            current_path = "/" + "/".join(path_parts[: i + 1])

            # Check if this path segment should be imported from existing resources
            if current_path in existing_resources:
                resource_config = existing_resources[current_path]
                resource_id = resource_config.get("resource_id")

                if resource_id:
                    logger.info(
                        f"Importing existing resource for path {current_path} with ID: {resource_id}"
                    )

                    # Import the existing resource using L1 constructs
                    current_resource = self._import_existing_resource(
                        api_gateway, current_resource, part, resource_id, current_path
                    )
                else:
                    # Create normally if no resource_id specified
                    current_resource = self._add_resource_safely(current_resource, part)
            else:
                # Create normally for non-imported paths
                current_resource = self._add_resource_safely(current_resource, part)

        return current_resource

    def _import_existing_resource(
        self,
        api_gateway: apigateway.RestApi,
        parent_resource: apigateway.Resource,
        path_part: str,
        resource_id: str,
        full_path: str,
    ) -> apigateway.Resource:
        """Import an existing API Gateway resource by ID"""
        from aws_cdk import aws_apigateway as apigateway

        try:
            # Use CfnResource to reference existing resource
            # This creates a reference without trying to create the resource
            imported_resource = apigateway.Resource.from_resource_id(
                self.scope, f"imported-resource-{hash(full_path) % 10000}", resource_id
            )

            logger.info(
                f"Successfully imported existing resource: {path_part} (ID: {resource_id})"
            )
            return imported_resource

        except Exception as e:
            logger.warning(
                f"Failed to import resource {path_part} with ID {resource_id}: {e}"
            )
            # Fallback to normal creation
            return self._add_resource_safely(parent_resource, path_part)

    def _add_resource_safely(
        self, parent_resource: apigateway.Resource, path_part: str
    ) -> apigateway.Resource:
        """Add resource with conflict handling"""
        try:
            return parent_resource.add_resource(path_part)
        except Exception as e:
            if "AlreadyExists" in str(e) or "same parent already has this name" in str(
                e
            ):
                logger.warning(
                    f"Resource {path_part} already exists, attempting to find existing resource"
                )

                # Try to find the existing resource in children
                for child in parent_resource.node.children:
                    if (
                        hasattr(child, "path_part")
                        and getattr(child, "path_part", None) == path_part
                    ):
                        logger.info(f"Found existing resource: {path_part}")
                        return child

                # If not found in children, re-raise the error
                logger.error(f"Could not find or create resource: {path_part}")
                raise e
            else:
                raise e

    def _get_existing_api_gateway_id_with_ssm_fallback(
        self, api_config: ApiGatewayConfigRouteConfig, stack_config
    ) -> Optional[str]:
        """Get existing API Gateway ID with SSM parameter fallback support"""
        # First try direct config values
        api_gateway_id = self._get_existing_api_gateway_id(api_config, stack_config)
        if api_gateway_id:
            return api_gateway_id

        # Try SSM parameter lookup
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})
        ssm_path = api_gateway_config.get("id_ssm_path")

        if ssm_path:
            logger.info(f"Looking up API Gateway ID from SSM parameter: {ssm_path}")
            try:
                api_gateway_id = ssm.StringParameter.from_string_parameter_name(
                    self.scope,
                    f"api-gateway-id-param-{hash(ssm_path) % 10000}",
                    ssm_path,
                ).string_value
                logger.info(f"Found API Gateway ID from SSM: {api_gateway_id}")
                return api_gateway_id
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve API Gateway ID from SSM path {ssm_path}: {e}"
                )

        # Try environment variable fallback
        env_var_name = api_gateway_config.get("id_env_var", "API_GATEWAY_ID")
        env_api_gateway_id = os.getenv(env_var_name)
        if env_api_gateway_id:
            logger.info(
                f"Using API Gateway ID from environment variable {env_var_name}: {env_api_gateway_id}"
            )
            return env_api_gateway_id

        return None

    def _get_existing_api_gateway_id(
        self, api_config: ApiGatewayConfigRouteConfig, stack_config
    ) -> Optional[str]:
        """Get existing API Gateway ID from config"""
        if api_config.api_gateway_id:
            logger.info(
                f"Using existing API Gateway ID from route config (api): {api_config.api_gateway_id}"
            )
            return api_config.api_gateway_id
        else:
            api_gateway_id = stack_config.dictionary.get("api_gateway", {}).get(
                "id", None
            )
            if api_gateway_id:
                logger.info(
                    f"Using existing API Gateway ID from stack config (api_gateway): {api_gateway_id}"
                )
                return api_gateway_id

        return None

    def _get_existing_authorizer_id_with_ssm_fallback(
        self, api_config: ApiGatewayConfigRouteConfig, stack_config
    ) -> Optional[str]:
        """Get existing authorizer ID with SSM parameter fallback support"""
        # First try direct config values
        authorizer_id = self._get_existing_authorizer_id(api_config, stack_config)
        if authorizer_id:
            return authorizer_id

        # Try enhanced SSM parameter lookup with auto-discovery
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})
        ssm_config = api_gateway_config.get("ssm", {})

        if ssm_config.get("enabled", False):
            try:
                from cdk_factory.interfaces.standardized_ssm_mixin import (
                    StandardizedSsmMixin,
                )

                ssm_mixin = StandardizedSsmMixin()

                # Setup enhanced SSM integration for auto-import
                # Use consistent resource name for cross-stack compatibility
                ssm_mixin.setup_ssm_integration(
                    scope=self.scope,
                    config=api_gateway_config,
                    resource_type="api-gateway",
                    resource_name="cdk-factory-api-gw",  # Use descriptive name for cross-stack sharing
                )

                # Check if authorizer_id is configured for import
                imports_config = ssm_config.get("imports", {})
                if "authorizer_id" in imports_config:
                    import_value = imports_config["authorizer_id"]

                    if import_value == "auto":
                        logger.info("Using auto-import for authorizer ID")
                        imported_values = ssm_mixin.auto_import_resources()
                        authorizer_id = imported_values.get("authorizer_id")
                        if authorizer_id:
                            logger.info(
                                f"Found authorizer ID via auto-import: {authorizer_id}"
                            )
                            return authorizer_id
                    else:
                        # Use direct parameter import for specific SSM path
                        logger.info(
                            f"Looking up authorizer ID from SSM parameter: {import_value}"
                        )
                        authorizer_id = ssm_mixin._resolve_single_ssm_import(
                            import_value, "authorizer_id"
                        )
                        if authorizer_id:
                            logger.info(
                                f"Found authorizer ID from SSM: {authorizer_id}"
                            )
                            return authorizer_id

            except Exception as e:
                logger.warning(
                    f"Failed to retrieve authorizer ID via enhanced SSM: {e}"
                )

        # Fallback to traditional SSM parameter lookup
        authorizer_config = stack_config.dictionary.get("api_gateway", {}).get(
            "authorizer", {}
        )
        ssm_path = authorizer_config.get("id_ssm_path")

        if ssm_path:
            logger.info(f"Looking up authorizer ID from SSM parameter: {ssm_path}")
            try:
                authorizer_id = ssm.StringParameter.from_string_parameter_name(
                    self.scope,
                    f"authorizer-id-param-{hash(ssm_path) % 10000}",
                    ssm_path,
                ).string_value
                logger.info(f"Found authorizer ID from SSM: {authorizer_id}")
                return authorizer_id
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve authorizer ID from SSM path {ssm_path}: {e}"
                )

        # Try environment variable fallback
        env_var_name = authorizer_config.get("id_env_var", "COGNITO_AUTHORIZER_ID")
        env_authorizer_id = os.getenv(env_var_name)
        if env_authorizer_id:
            logger.info(
                f"Using authorizer ID from environment variable {env_var_name}: {env_authorizer_id}"
            )
            return env_authorizer_id

        return None

    def _get_existing_authorizer_id(
        self, api_config: ApiGatewayConfigRouteConfig, stack_config
    ) -> Optional[str]:
        """Get existing authorizer ID from config"""
        if api_config.authorizer_id:
            logger.info(
                f"Using existing authorizer ID from route config (api): {api_config.authorizer_id}"
            )
            return api_config.authorizer_id
        else:
            authorizer_id = (
                stack_config.dictionary.get("api_gateway", {})
                .get("authorizer", {})
                .get("id", None)
            )
            if authorizer_id:
                logger.info(
                    f"Using existing authorizer ID from stack config (api_gateway.authorizer): {authorizer_id}"
                )
                return authorizer_id

        return None

    def _get_root_resource_id_with_ssm_fallback(self, stack_config) -> Optional[str]:
        """Get root resource ID with SSM parameter fallback support"""
        # First try direct config value
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})
        root_resource_id = api_gateway_config.get("root_resource_id")

        if root_resource_id:
            logger.info(f"Using root resource ID from config: {root_resource_id}")
            return root_resource_id

        # Try SSM parameter lookup
        ssm_path = api_gateway_config.get("root_resource_id_ssm_path")

        if ssm_path:
            logger.info(f"Looking up root resource ID from SSM parameter: {ssm_path}")
            try:
                root_resource_id = ssm.StringParameter.from_string_parameter_name(
                    self.scope,
                    f"root-resource-id-param-{hash(ssm_path) % 10000}",
                    ssm_path,
                ).string_value
                logger.info(f"Found root resource ID from SSM: {root_resource_id}")
                return root_resource_id
            except Exception as e:
                logger.warning(
                    f"Failed to retrieve root resource ID from SSM path {ssm_path}: {e}"
                )

        # Try environment variable fallback
        env_var_name = api_gateway_config.get(
            "root_resource_id_env_var", "API_GATEWAY_ROOT_RESOURCE_ID"
        )
        env_root_resource_id = os.getenv(env_var_name)
        if env_root_resource_id:
            logger.info(
                f"Using root resource ID from environment variable {env_var_name}: {env_root_resource_id}"
            )
            return env_root_resource_id

        return None

    def export_api_gateway_to_ssm(
        self,
        api_gateway: apigateway.RestApi,
        authorizer: Optional[apigateway.Authorizer] = None,
        stack_config=None,
        export_prefix: str = None,
    ) -> dict:
        """Export API Gateway configuration values to SSM parameters for cross-stack references"""
        if not export_prefix:
            stack_name = stack_config.name if stack_config else "api-gateway"
            export_prefix = f"/my-cool-app/{stack_name}/api-gateway"

        exported_params = {}

        # Export API Gateway ID
        api_id_param = ssm.StringParameter(
            self.scope,
            f"ssm-export-api-id",
            parameter_name=f"{export_prefix}/id",
            string_value=api_gateway.rest_api_id,
            description=f"API Gateway ID for {export_prefix}",
        )
        exported_params["api_gateway_id"] = api_id_param.parameter_name
        logger.info(f"Exported API Gateway ID to SSM: {api_id_param.parameter_name}")

        # Export API Gateway ARN
        api_arn_param = ssm.StringParameter(
            self.scope,
            f"ssm-export-api-arn",
            parameter_name=f"{export_prefix}/arn",
            string_value=api_gateway.rest_api_arn,
            description=f"API Gateway ARN for {export_prefix}",
        )
        exported_params["api_gateway_arn"] = api_arn_param.parameter_name
        logger.info(f"Exported API Gateway ARN to SSM: {api_arn_param.parameter_name}")

        # Export root resource ID
        root_resource_param = ssm.StringParameter(
            self.scope,
            f"ssm-export-root-resource-id",
            parameter_name=f"{export_prefix}/root-resource-id",
            string_value=api_gateway.root.resource_id,
            description=f"API Gateway root resource ID for {export_prefix}",
        )
        exported_params["root_resource_id"] = root_resource_param.parameter_name
        logger.info(
            f"Exported root resource ID to SSM: {root_resource_param.parameter_name}"
        )

        # Export authorizer ID if provided
        if authorizer:
            authorizer_id_param = ssm.StringParameter(
                self.scope,
                f"ssm-export-authorizer-id",
                parameter_name=f"{export_prefix}/authorizer/id",
                string_value=authorizer.authorizer_id,
                description=f"API Gateway authorizer ID for {export_prefix}",
            )
            exported_params["authorizer_id"] = authorizer_id_param.parameter_name
            logger.info(
                f"Exported authorizer ID to SSM: {authorizer_id_param.parameter_name}"
            )

        return exported_params

    def setup_route_cors(
        self, resource: apigateway.Resource, route_path: str, route: dict
    ):
        """Setup CORS for a route - centralized method for both API Gateway and Lambda stacks"""
        cors_cfg = route.get("cors")
        methods = cors_cfg.get("methods") if cors_cfg else None
        origins = cors_cfg.get("origins") if cors_cfg else None
        ApiGatewayUtilities.bind_mock_for_cors(
            resource,
            route_path,
            http_method_list=methods,
            origins_list=origins,
        )

    def _create_method_with_existing_authorizer(
        self,
        api_gateway: apigateway.RestApi,
        resource: apigateway.Resource,
        lambda_function: _lambda.Function,
        api_config: ApiGatewayConfigRouteConfig,
        stack_config,
    ) -> apigateway.CfnMethod:
        """Create API Gateway method using L1 constructs to support existing authorizer ID"""

        # Convert L2 integration to L1 integration properties
        # Note: For CfnMethod integration, property names use camelCase
        integration_props = {
            "type": "AWS_PROXY",
            "integrationHttpMethod": "POST",
            "uri": f"arn:aws:apigateway:{self.region}:lambda:path/2015-03-31/functions/{lambda_function.function_arn}/invocations",
        }

        # Ensure HTTP method is not empty
        http_method = api_config.method.upper() if api_config.method else "GET"
        if not http_method or http_method.strip() == "":
            logger.warning(
                f"Empty HTTP method detected for {lambda_function.function_name}, defaulting to GET"
            )
            http_method = "GET"

        # Use the validated authorization type from api_config
        auth_type = api_config.authorization_type
        method_props = {
            "http_method": http_method,
            "resource_id": resource.resource_id,
            "rest_api_id": api_gateway.rest_api_id,
            "authorization_type": auth_type,
            "api_key_required": api_config.api_key_required,
            "request_parameters": api_config.request_parameters,
            "integration": integration_props,
        }
        
        # Only add authorizer_id if authorization type is not NONE
        if auth_type != "NONE":
            method_props["authorizer_id"] = self._get_existing_authorizer_id_with_ssm_fallback(
                api_config, stack_config
            )

        # Create method using L1 construct with validated authorization configuration
        method = apigateway.CfnMethod(
            self.scope,
            f"method-{http_method.lower()}-{resource.node.id}-existing-auth",
            **method_props
        )

        # Add Lambda permission for API Gateway to invoke the function
        lambda_permission = _lambda.CfnPermission(
            self.scope,
            f"lambda-permission-{api_config.method.lower()}-{resource.node.id}-existing-auth",
            action="lambda:InvokeFunction",
            function_name=lambda_function.function_name,
            principal="apigateway.amazonaws.com",
            source_arn=f"arn:aws:execute-api:{self.region}:{self.account}:{api_gateway.rest_api_id}/*/{api_config.method.upper()}{resource.path}",
        )

        return method

    def finalize_api_gateway_deployment(
        self,
        api_gateway: apigateway.RestApi,
        integrations: List[Dict[str, Any]],
        stack_config: StackConfig,
        api_config: Optional[ApiGatewayConfig] = None,
        construct_scope: Optional[Construct] = None,
        counter: int = 1,
    ) -> apigateway.Stage:
        """
        Create deployment and stage for API Gateway with all integrations.
        Consolidates logic from both API Gateway and Lambda stacks.
        """
        scope = construct_scope or self.scope

        # Determine stage name with fallback logic
        stage_name = self._get_stage_name(stack_config, api_config)

        # Check if using existing stage
        use_existing = self._should_use_existing_stage(stack_config)

        logger.info(
            f"Creating deployment for API Gateway with {len(integrations)} integrations"
        )

        # Create deployment
        deployment_id = f"api-gateway-{counter}-deployment-final"
        if len(integrations) == 1 and integrations[0].get("function_name"):
            # Lambda stack deployment
            deployment_id = "api-gateway-deployment"

        deployment = apigateway.Deployment(
            scope,
            deployment_id,
            api=api_gateway,
            description=f"Deployment with all {len(integrations)} routes included",
            stage_name=stage_name if use_existing else None,
        )
        # Add timestamp to deployment logical ID to prevent conflicts and force new deployment
        deployment.add_to_logical_id(datetime.now(UTC).isoformat())

        # Create stage if not using existing
        stage = None
        if not use_existing:
            stage_options = (
                self._create_stage_options(api_config) if api_config else None
            )
            stage_id = f"{api_gateway.rest_api_name}-{stage_name}-stage"
            if len(integrations) == 1 and integrations[0].get("function_name"):
                # Lambda stack stage
                stage_id = f"{api_gateway.rest_api_name}-{stage_name}-stage-lambdas"

            stage_kwargs = {
                "deployment": deployment,
                "stage_name": stage_name,
                "description": f"Stage {stage_name} with {len(integrations)} integrations",
            }

            # Add stage options if available
            if stage_options:
                stage_kwargs.update(
                    {
                        "access_log_destination": stage_options.access_log_destination,
                        "access_log_format": stage_options.access_log_format,
                        "logging_level": stage_options.logging_level,
                        "data_trace_enabled": stage_options.data_trace_enabled,
                        "metrics_enabled": stage_options.metrics_enabled,
                        "tracing_enabled": stage_options.tracing_enabled,
                        "throttling_rate_limit": stage_options.throttling_rate_limit,
                        "throttling_burst_limit": stage_options.throttling_burst_limit,
                    }
                )

            stage = apigateway.Stage(scope, stage_id, **stage_kwargs)

        logger.info(
            f"Created deployment and stage '{stage_name}' for API Gateway: {api_gateway.rest_api_name}"
        )
        logger.info(
            f"Routes available at: https://{api_gateway.rest_api_id}.execute-api.{scope.region}.amazonaws.com/{stage_name}"
        )

        return stage

    def _get_stage_name(
        self, stack_config: StackConfig, api_config: Optional[ApiGatewayConfig] = None
    ) -> str:
        """Get stage name with fallback logic from both stacks"""
        # Try Lambda stack config format first
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})
        stage_name = api_gateway_config.get("stage", {}).get("name")

        if stage_name:
            return stage_name

        # Try API Gateway stack config format
        if api_config and hasattr(api_config, "stage_name") and api_config.stage_name:
            stage_name = api_config.stage_name
        else:
            # Fallback to legacy format
            stage_name = api_gateway_config.get("stage_name", "prod")

        # Handle special cases
        if stage_name is None:
            raise ValueError("Stage name is required in API Gateway config")

        if stage_name.lower() == "auto":
            try:
                stage_name = stack_config.name
            except Exception as e:
                raise ValueError("Stage name is required in API Gateway config") from e

        return stage_name

    def _should_use_existing_stage(self, stack_config: StackConfig) -> bool:
        """Check if should use existing stage"""
        api_gateway_config = stack_config.dictionary.get("api_gateway", {})
        use_existing = api_gateway_config.get("stage", {}).get("use_existing", False)
        return str(use_existing).lower() == "true"

    def _create_stage_options(
        self, api_config: ApiGatewayConfig
    ) -> apigateway.StageOptions:
        """Create stage options with full configuration"""
        log_group = self._setup_log_group()
        access_log_format = self._get_log_format()

        deploy_options = api_config.deploy_options or {}

        return apigateway.StageOptions(
            access_log_destination=apigateway.LogGroupLogDestination(log_group),
            access_log_format=access_log_format,
            logging_level=apigateway.MethodLoggingLevel.ERROR,
            data_trace_enabled=deploy_options.get("data_trace_enabled", False),
            metrics_enabled=deploy_options.get("metrics_enabled", False),
            tracing_enabled=deploy_options.get("tracing_enabled", True),
            throttling_rate_limit=deploy_options.get("throttling_rate_limit", 1000),
            throttling_burst_limit=deploy_options.get("throttling_burst_limit", 2000),
        )

    def _setup_log_group(self) -> logs.LogGroup:
        """Setup CloudWatch log group for API Gateway"""
        if self._log_group:
            return self._log_group

        self._log_group = logs.LogGroup(
            self.scope,
            "ApiGatewayLogGroup",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_MONTH,
        )

        self._log_group.grant_write(iam.ServicePrincipal("apigateway.amazonaws.com"))
        log_role = self._setup_log_role()
        self._log_group.grant_write(log_role)

        return self._log_group

    def _setup_log_role(self) -> iam.Role:
        """Setup IAM role for API Gateway logging"""
        if self._log_role:
            return self._log_role

        self._log_role = iam.Role(
            self.scope,
            "ApiGatewayLogRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonAPIGatewayPushToCloudWatchLogs"
                )
            ],
        )

        return self._log_role

    def _get_log_format(self) -> apigateway.AccessLogFormat:
        """Get access log format for API Gateway"""
        return apigateway.AccessLogFormat.custom(
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

    def group_integrations_by_api_gateway(
        self, integrations: List[Dict[str, Any]]
    ) -> Dict[int, Dict[str, Any]]:
        """Group integrations by API Gateway using object identity"""
        api_gateways = {}
        api_counter = 0

        for integration in integrations:
            api_gateway = integration.get("api_gateway")
            if api_gateway:
                # Use object identity as key instead of CDK token
                api_key = id(api_gateway)
                if api_key not in api_gateways:
                    api_counter += 1
                    api_gateways[api_key] = {
                        "api_gateway": api_gateway,
                        "integrations": [],
                        "counter": api_counter,
                    }
                api_gateways[api_key]["integrations"].append(integration)

        return api_gateways

    def _validate_and_adjust_authorization_configuration(
        self, api_config: ApiGatewayConfigRouteConfig, has_cognito_authorizer: bool
    ) -> ApiGatewayConfigRouteConfig:
        """
        Validate and adjust authorization configuration for security and clarity.

        This method implements 'secure by default' with explicit overrides:
        - If Cognito is available and route wants NONE auth, requires explicit override
        - If Cognito is not available and route wants COGNITO auth, raises error
        - Provides verbose warnings for monitoring and security awareness
        - Returns a potentially modified api_config with adjusted authorization_type

        Args:
            api_config (ApiGatewayConfigRouteConfig): Route configuration
            has_cognito_authorizer (bool): Whether a Cognito authorizer is configured

        Returns:
            ApiGatewayConfigRouteConfig: Potentially modified configuration

        Raises:
            ValueError: When there are security conflicts without explicit overrides
        """
        import logging
        from copy import deepcopy

        # Create a copy to avoid modifying the original
        modified_config = deepcopy(api_config)

        auth_type = str(getattr(api_config, "authorization_type", "COGNITO")).upper()
        route_path = getattr(api_config, "routes", "unknown")
        method = getattr(api_config, "method", "unknown")
        
        logger = logging.getLogger(__name__)

        # Check for explicit override flag
        explicit_override = getattr(api_config, "allow_public_override", False)
        # Handle both boolean and string values
        if isinstance(explicit_override, str):
            explicit_override = explicit_override.lower() in ("true", "1", "yes")
        else:
            explicit_override = bool(explicit_override)
        
        logger = logging.getLogger(__name__)

        # Case 1: Cognito available + NONE requested + No explicit override = ERROR
        if has_cognito_authorizer and auth_type == "NONE" and not explicit_override:
            error_msg = (
                f"🚨 SECURITY CONFLICT DETECTED for route {route_path} ({method}):\n"
                f"   ❌ Cognito authorizer is configured (manual or auto-import)\n"
                f"   ❌ authorization_type is set to 'NONE' (public access)\n"
                f"   ❌ This creates a security risk - public endpoint with auth available\n\n"
                f"💡 SOLUTIONS:\n"
                f"   1. Remove Cognito configuration if you want public access\n"
                f"   2. Add 'allow_public_override': true to explicitly allow public access\n"
                f"   3. Remove 'authorization_type': 'NONE' to use secure Cognito auth\n\n"
                f"🔒 This prevents accidental public endpoints when authentication is available.\n\n"
                f"👉 ApiGatewayIntegrationUtility documentation for more details: \n\n "
                "\t https://github.com/geekcafe/cdk-factory/blob/main/src/cdk_factory/utilities/api_gateway_integration_utility.py \n\n"
                "\t and https://github.com/geekcafe/cdk-factory/blob/main/src/cdk_factory/stack_library/api_gateway/api_gateway_stack.py"
            )
            raise ValueError(error_msg)

        # Case 2: No Cognito + COGNITO explicitly requested = ERROR
        # Only error if COGNITO was explicitly requested, not if it's the default
        original_auth_type = None
        if hasattr(api_config, "dictionary") and api_config.dictionary:
            original_auth_type = api_config.dictionary.get("authorization_type")

        if not has_cognito_authorizer and original_auth_type == "COGNITO":
            error_msg = (
                f"🚨 CONFIGURATION ERROR for route {route_path} ({method}):\n"
                f"   ❌ authorization_type is explicitly set to 'COGNITO' but no Cognito authorizer configured\n"
                f"   ❌ Cannot secure endpoint without authentication provider\n\n"
                f"💡 SOLUTIONS:\n"
                f"   1. Add Cognito configuration to enable authentication\n"
                f"   2. Set authorization_type to 'NONE' for public access\n"
                f"   3. Configure SSM auto-import for user_pool_arn\n"
                f"   4. Remove explicit authorization_type to use default behavior"
            )
            raise ValueError(error_msg)

        # Case 3: Cognito available + NONE requested + Explicit override = WARN
        if has_cognito_authorizer and auth_type == "NONE" and explicit_override:
            warning_msg = (
                f"⚠️  PUBLIC ENDPOINT CONFIGURED: {route_path} ({method})\n"
                f"   🔓 This endpoint is intentionally public (allow_public_override: true)\n"
                f"   🔐 Cognito authentication is available but overridden\n"
                f"   📊 Consider monitoring this endpoint for unexpected usage patterns\n"
                f"   🔍 Review periodically: Should this endpoint be secured?"
            )

            # Print to console during deployment for visibility
            print(warning_msg)

            # Structured logging for monitoring and metrics
            logger.warning(
                "Public endpoint configured with Cognito available",
                extra={
                    "route": route_path,
                    "method": method,
                    "security_override": True,
                    "cognito_available": True,
                    "authorization_type": "NONE",
                    "metric_name": "public_endpoint_with_cognito",
                    "security_decision": "intentional_public",
                    "recommendation": "review_periodically",
                },
            )

        # Case 4: No Cognito + default COGNITO = Fall back to NONE
        if (
            not has_cognito_authorizer
            and auth_type == "COGNITO"
            and original_auth_type is None
        ):
            modified_config.authorization_type = "NONE"
            logger.info(
                f"No Cognito authorizer available for route {route_path} ({method}), "
                f"defaulting to public access (NONE authorization)"
            )

        # Case 5: No Cognito + NONE = INFO (expected for public-only APIs)
        if not has_cognito_authorizer and auth_type == "NONE":
            logger.info(
                f"Public endpoint configured (no Cognito available): {route_path} ({method})",
                extra={
                    "route": route_path,
                    "method": method,
                    "authorization_type": "NONE",
                    "cognito_available": False,
                    "security_decision": "public_only_api",
                },
            )

        return modified_config
