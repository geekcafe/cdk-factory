"""
API Gateway Integration Utility for CDK-Factory
Shared utility for Lambda API Gateway integrations
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import os
from typing import Optional
from aws_cdk import aws_apigateway as apigateway
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_cognito as cognito
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.configurations.resources.lambda_functions import ApiGatewayConfigRouteConfig

logger = Logger(service="ApiGatewayIntegrationUtility")


class ApiGatewayIntegrationUtility:
    """Utility class for API Gateway Lambda integrations"""
    
    def __init__(self, scope: Construct):
        self.scope = scope
        self.region = scope.region
        self.account = scope.account
    
    def setup_lambda_integration(
        self, 
        lambda_function: _lambda.Function, 
        api_config: ApiGatewayConfigRouteConfig,
        api_gateway: apigateway.RestApi,
        stack_config
    ) -> dict:
        """Setup API Gateway integration for Lambda function"""
        if not api_config:
            raise ValueError("API Gateway config is missing in Lambda function config")

        # Get or create authorizer if needed
        authorizer = None
        if not api_config.skip_authorizer:
            authorizer = self.get_or_create_authorizer(api_gateway, api_config, stack_config)

        # Create integration
        integration = apigateway.LambdaIntegration(
            lambda_function,
            proxy=True,
            allow_test_invoke=True,
        )

        # Add method to API Gateway
        resource = self.get_or_create_resource(api_gateway, api_config.routes)

        # Handle existing authorizer ID using L1 constructs
        if self._get_existing_authorizer_id(api_config, stack_config):
            method = self._create_method_with_existing_authorizer(
                api_gateway, resource, lambda_function, api_config, stack_config
            )
        else:
            # Use L2 constructs for new authorizers
            # Determine authorization type based on whether authorizer is provided
            if authorizer:
                auth_type = apigateway.AuthorizationType.COGNITO
            else:
                auth_type = apigateway.AuthorizationType[api_config.authorization_type]

            method = resource.add_method(
                api_config.method.upper(),
                integration,
                authorizer=authorizer,
                api_key_required=api_config.api_key_required,
                request_parameters=api_config.request_parameters,
                authorization_type=auth_type,
            )

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
        existing_integrations: list = None
    ) -> apigateway.RestApi:
        """Get existing API Gateway or create new one"""
        # Check for existing API Gateway ID
        api_gateway_id = self._get_existing_api_gateway_id(api_config, stack_config)
        
        if api_gateway_id:
            # Import existing API Gateway
            root_resource_id = (
                stack_config.dictionary.get("api_gateway", {})
                .get("root_resource_id", None)
            )
            
            if root_resource_id:
                logger.info(
                    f"Using existing API Gateway {api_gateway_id} with root resource {root_resource_id}"
                )
                return apigateway.RestApi.from_rest_api_attributes(
                    self.scope,
                    f"imported-api-{api_gateway_id}",
                    rest_api_id=api_gateway_id,
                    root_resource_id=root_resource_id,
                )
            else:
                logger.warning(
                    f"No root_resource_id provided for API Gateway {api_gateway_id}. "
                    "Using from_rest_api_id() - this may cause validation issues in some CDK versions."
                )
                try:
                    return apigateway.RestApi.from_rest_api_id(
                        self.scope,
                        f"imported-api-{api_gateway_id}",
                        api_gateway_id,
                    )
                except Exception as e:
                    if "ValidationError" in str(e) and "root is not configured" in str(e):
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

        # Create new REST API
        api_id = f"{stack_config.name}-api"
        api = apigateway.RestApi(
            self.scope,
            api_id,
            rest_api_name=f"{stack_config.name}-api",
            description=f"API Gateway for {stack_config.name} Lambda functions",
            default_cors_preflight_options=apigateway.CorsOptions(
                allow_origins=apigateway.Cors.ALL_ORIGINS,
                allow_methods=apigateway.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                ],
            ),
        )

        return api

    def get_or_create_authorizer(
        self, 
        api_gateway: apigateway.RestApi, 
        api_config: ApiGatewayConfigRouteConfig,
        stack_config
    ) -> Optional[apigateway.Authorizer]:
        """Get existing authorizer or create new one"""
        # Check if we should reference existing authorizer
        if self._get_existing_authorizer_id(api_config, stack_config):
            # For existing authorizers, we'll handle this in the method creation
            # using L1 constructs which support authorizer_id parameter
            return None

        # Check if authorizer already exists for this API
        authorizer_id = f"{api_gateway.node.id}-authorizer"

        # Get user pool from environment or config
        user_pool_id = api_config.user_pool_id or os.getenv("COGNITO_USER_POOL_ID")
        if not user_pool_id:
            raise ValueError(
                "COGNITO_USER_POOL_ID environment variable or config setting is required for API Gateway authorizer"
            )

        user_pool = cognito.UserPool.from_user_pool_id(
            self.scope,
            f"{authorizer_id}-user-pool",
            user_pool_id,
        )

        # Create Cognito authorizer
        authorizer = apigateway.CognitoUserPoolsAuthorizer(
            self.scope,
            authorizer_id,
            cognito_user_pools=[user_pool],
            identity_source="method.request.header.Authorization",
        )

        return authorizer

    def get_or_create_resource(
        self, 
        api_gateway: apigateway.RestApi, 
        route_path: str
    ) -> apigateway.Resource:
        """Get or create API Gateway resource for the given route path"""
        if not route_path or route_path == "/":
            return api_gateway.root

        # Remove leading slash and split path
        path_parts = route_path.lstrip("/").split("/")
        current_resource = api_gateway.root

        # Navigate/create nested resources
        for part in path_parts:
            if not part:  # Skip empty parts
                continue

            # Check if resource already exists
            existing_resource = None
            for child in current_resource.node.children:
                if hasattr(child, "path_part") and child.path_part == part:
                    existing_resource = child
                    break

            if existing_resource:
                current_resource = existing_resource
            else:
                current_resource = current_resource.add_resource(part)

        return current_resource

    def _get_existing_api_gateway_id(
        self, 
        api_config: ApiGatewayConfigRouteConfig,
        stack_config
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

    def _get_existing_authorizer_id(
        self, 
        api_config: ApiGatewayConfigRouteConfig,
        stack_config
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

    def _create_method_with_existing_authorizer(
        self,
        api_gateway: apigateway.RestApi,
        resource: apigateway.Resource,
        lambda_function: _lambda.Function,
        api_config: ApiGatewayConfigRouteConfig,
        stack_config
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
            logger.warning(f"Empty HTTP method detected for {lambda_function.function_name}, defaulting to GET")
            http_method = "GET"
        
        # Create method using L1 construct with existing authorizer ID
        method = apigateway.CfnMethod(
            self.scope,
            f"method-{http_method.lower()}-{resource.node.id}-existing-auth",
            http_method=http_method,
            resource_id=resource.resource_id,
            rest_api_id=api_gateway.rest_api_id,
            authorization_type="COGNITO_USER_POOLS",
            authorizer_id=self._get_existing_authorizer_id(api_config, stack_config),
            api_key_required=api_config.api_key_required,
            request_parameters=api_config.request_parameters,
            integration=integration_props,
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
