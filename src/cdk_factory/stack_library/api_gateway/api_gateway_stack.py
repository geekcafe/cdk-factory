"""
API Gateway Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from pathlib import Path
import aws_cdk as cdk
from aws_cdk import aws_apigateway as apigateway
from constructs import Construct
from cdk_factory.interfaces.istack import IStack
from aws_lambda_powertools import Logger
from cdk_factory.stack.stack_module_registry import register_stack

logger = Logger(service="ApiGatewayStack")


@register_stack("api_gateway_library_module")
class ApiGatewayStack(IStack):
    """
    Reusable stack for AWS API Gateway (REST API).
    Supports all major RestApi parameters.
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.api_config = None
        self.stack_config = None
        self.deployment = None
        self.workload = None
        self.api = None

    def build(self, stack_config, deployment, workload) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        from cdk_factory.configurations.resources.api_gateway import ApiGatewayConfig

        self.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Lambda import
        from aws_cdk import aws_lambda as _lambda
        import os

        # Determine API type (REST or HTTP)
        api_type = self.api_config.api_type
        self.api = None
        api_id = deployment.build_resource_name(
            self.api_config.api_gateway_name or "api-gateway"
        )

        # Prepare Lambda function for health route or user-provided code
        def create_lambda(lambda_path=None, id_suffix="health"):
            path = Path(__file__).parents[2]

            code_path = lambda_path or os.path.join(path, "lambdas/health_handler.py")

            if not os.path.exists(code_path):
                raise Exception(f"Lambda code path does not exist: {code_path}")
            return _lambda.Function(
                self,
                f"{api_id}-lambda-{id_suffix}",
                runtime=_lambda.Runtime.PYTHON_3_11,
                handler="health_handler.lambda_handler",
                code=_lambda.Code.from_asset(os.path.dirname(code_path)),
                timeout=cdk.Duration.seconds(10),
            )

        # Route setup
        routes = self.api_config.routes or [
            {"path": "/health", "method": "GET", "lambda_code_path": None}
        ]

        # REST API
        if api_type == "REST":
            endpoint_types = self.api_config.endpoint_types
            if endpoint_types:
                endpoint_types = [
                    apigateway.EndpointType[e] if isinstance(e, str) else e
                    for e in endpoint_types
                ]
            min_compression_size = self.api_config.min_compression_size
            if isinstance(min_compression_size, int):
                from aws_cdk import Size

                min_compression_size = Size.mebibytes(min_compression_size)
            kwargs = {
                "rest_api_name": self.api_config.api_gateway_name,
                "description": self.api_config.description,
                "deploy": self.api_config.deploy,
                "deploy_options": self.api_config.deploy_options,
                "endpoint_types": endpoint_types,
                "api_key_source_type": self.api_config.api_key_source_type,
                "binary_media_types": self.api_config.binary_media_types,
                "cloud_watch_role": self.api_config.cloud_watch_role,
                "default_cors_preflight_options": self.api_config.default_cors_preflight_options,
                "default_method_options": self.api_config.default_method_options,
                "default_integration": self.api_config.default_integration,
                "disable_execute_api_endpoint": self.api_config.disable_execute_api_endpoint,
                "endpoint_export_name": self.api_config.endpoint_export_name,
                "fail_on_warnings": self.api_config.fail_on_warnings,
                "min_compression_size": min_compression_size,
                "parameters": self.api_config.parameters,
                "policy": self.api_config.policy,
                "retain_deployments": self.api_config.retain_deployments,
                "rest_api_id": self.api_config.rest_api_id,
                "root_resource_id": self.api_config.root_resource_id,
                "cloud_watch_role_removal_policy": self.api_config.cloud_watch_role_removal_policy,
            }
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            self.api = apigateway.RestApi(
                self,
                id=api_id,
                **kwargs,
            )
            logger.info(f"Created API Gateway: {self.api.rest_api_name}")
            # Add routes
            # Cognito authorizer setup
            authorizer = None
            if self.api_config.cognito_authorizer:
                user_pool_arn = self.api_config.cognito_authorizer["user_pool_arn"]
                authorizer_name = self.api_config.cognito_authorizer.get(
                    "authorizer_name", "CognitoAuthorizer"
                )
                identity_source = self.api_config.cognito_authorizer.get(
                    "identity_source", "method.request.header.Authorization"
                )
                from aws_cdk import aws_cognito as cognito

                user_pool = cognito.UserPool.from_user_pool_arn(
                    self, f"{api_id}-userpool", user_pool_arn
                )
                authorizer = apigateway.CognitoUserPoolsAuthorizer(
                    self,
                    f"{api_id}-authorizer",
                    cognito_user_pools=[user_pool],
                    authorizer_name=authorizer_name,
                    identity_source=identity_source,
                )

            for route in routes:
                lambda_fn = create_lambda(
                    route.get("lambda_code_path"),
                    id_suffix=route["path"].strip("/").replace("/", "-") or "health",
                )
                resource = (
                    self.api.root.add_resource(route["path"].strip("/"))
                    if route["path"] != "/"
                    else self.api.root
                )
                authorization_type = route.get("authorization_type")
                if authorizer and authorization_type != "NONE":
                    resource.add_method(
                        route["method"].upper(),
                        apigateway.LambdaIntegration(lambda_fn),
                        authorization_type=apigateway.AuthorizationType.COGNITO,
                        authorizer=authorizer,
                    )
                else:
                    resource.add_method(
                        route["method"].upper(),
                        apigateway.LambdaIntegration(lambda_fn),
                        authorization_type=apigateway.AuthorizationType.NONE,
                    )
                # Add CORS mock OPTIONS method if requested or default
                from cdk_factory.utils.api_gateway_utilities import ApiGatewayUtilities

                cors_cfg = route.get("cors")
                methods = cors_cfg.get("methods") if cors_cfg else None
                origins = cors_cfg.get("origins") if cors_cfg else None
                ApiGatewayUtilities.bind_mock_for_cors(
                    resource,
                    route["path"],
                    http_method_list=methods,
                    origins_list=origins,
                )

        # HTTP API (v2)
        elif api_type == "HTTP":
            from aws_cdk import aws_apigatewayv2 as api_gateway_v2
            from aws_cdk import aws_apigatewayv2_integrations as integrations

            self.api = api_gateway_v2.HttpApi(
                self,
                id=api_id,
                api_name=self.api_config.api_gateway_name,
                description=self.api_config.description,
            )
            logger.info(f"Created HTTP API Gateway: {self.api.api_name}")
            # Add routes
            for route in routes:
                lambda_fn = create_lambda(
                    route.get("lambda_code_path"),
                    id_suffix=route["path"].strip("/").replace("/", "-") or "health",
                )
                self.api.add_routes(
                    path=route["path"],
                    methods=[api_gateway_v2.HttpMethod[route["method"].upper()]],
                    integration=integrations.LambdaProxyIntegration(handler=lambda_fn),
                )
        else:
            raise ValueError(f"Unsupported api_type: {api_type}")
