"""
API Gateway Stack Pattern for CDK-Factory
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from pathlib import Path
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

logger = Logger(service="ApiGatewayStack")


@register_stack("api_gateway_library_module")
@register_stack("api_gateway_stack")
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

    def build(self, stack_config, deployment, workload) -> None:
        self._build(stack_config, deployment, workload)

    def _build(self, stack_config, deployment, workload) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        self.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        api_type = self.api_config.api_type
        api_id = deployment.build_resource_name(
            self.api_config.api_gateway_name or "api-gateway"
        )

        routes = self.api_config.routes or [
            {"path": "/health", "method": "GET", "lambda_code_path": None}
        ]
        if api_type == "HTTP":
            api = self._create_http_api(api_id, routes)
            # TODO: Add custom domain support for HTTP API
            # self.__setup_custom_domain(api)
        elif api_type == "REST":
            api = self._create_rest_api(api_id, routes)
            self.__setup_custom_domain(api)
        else:
            raise ValueError(f"Unsupported api_type: {api_type}")

    def _create_rest_api(self, api_id: str, routes: List[Dict[str, Any]]):
        # REST API
        endpoint_types = self.api_config.endpoint_types
        if endpoint_types:
            endpoint_types = [
                apigateway.EndpointType[e] if isinstance(e, str) else e
                for e in endpoint_types
            ]
        min_compression_size = self.api_config.min_compression_size
        if isinstance(min_compression_size, int):

            min_compression_size = Size.mebibytes(min_compression_size)
        kwargs = {
            "rest_api_name": self.api_config.api_gateway_name,
            "description": self.api_config.description,
            "deploy": self.api_config.deploy,
            "deploy_options": self._deploy_options(),
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
        api = apigateway.RestApi(
            self,
            id=api_id,
            **kwargs,
        )
        logger.info(f"Created API Gateway: {api.rest_api_name}")
        # Add routes
        # Cognito authorizer setup
        authorizer = None
        if self.api_config.cognito_authorizer:
            user_pool_arn = self.api_config.cognito_authorizer.get("user_pool_arn")
            if not user_pool_arn:
                ssm_path = self.api_config.cognito_authorizer.get(
                    "user_pool_arn_ssm_path"
                )
                if not ssm_path:
                    raise ValueError(
                        "user_pool_arn or user_pool_arn_ssm_path must be provided"
                    )
                user_pool_arn = ssm.StringParameter.from_string_parameter_name(
                    self, "UserPoolArn", ssm_path
                ).string_value
            authorizer_name = self.api_config.cognito_authorizer.get(
                "authorizer_name", "CognitoAuthorizer"
            )
            identity_source = self.api_config.cognito_authorizer.get(
                "identity_source", "method.request.header.Authorization"
            )

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

            suffix = route["path"].strip("/").replace("/", "-") or "health"
            lambda_fn = self.create_lambda(
                api_id=api_id,
                lambda_path=route.get("lambda_code_path"),
                id_suffix=suffix,
                handler=route.get("handler"),
            )

            route_path = route["path"]
            resource = (
                api.root.resource_for_path(route_path)
                if route_path != "/"
                else api.root
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

            cors_cfg = route.get("cors")
            methods = cors_cfg.get("methods") if cors_cfg else None
            origins = cors_cfg.get("origins") if cors_cfg else None
            ApiGatewayUtilities.bind_mock_for_cors(
                resource,
                route_path,
                http_method_list=methods,
                origins_list=origins,
            )

        return api

    def _create_http_api(self, api_id: str, routes: List[Dict[str, Any]]):
        # HTTP API (v2)

        api = api_gateway_v2.HttpApi(
            self,
            id=api_id,
            api_name=self.api_config.api_gateway_name,
            description=self.api_config.description,
        )
        logger.info(f"Created HTTP API Gateway: {api.api_name}")
        # Add routes
        for route in routes:
            lambda_fn = self.create_lambda(
                api_id=api_id,
                lambda_path=route.get("lambda_code_path"),
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
        lambda_path=None,
        id_suffix="health",
        handler: str | None = None,
    ):
        path = Path(__file__).parents[2]

        code_path = lambda_path or os.path.join(path, "lambdas/health_handler.py")
        handler = handler or "health_handler.lambda_handler"
        if not os.path.exists(code_path):
            code_path = FileOperations.find_file(self.workload.paths, code_path)
            if not os.path.exists(code_path):
                raise Exception(f"Lambda code path does not exist: {code_path}")
        return _lambda.Function(
            self,
            f"{api_id}-lambda-{id_suffix}",
            # TODO need to make this configurable
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler=handler or "health_handler.lambda_handler",
            code=_lambda.Code.from_asset(os.path.dirname(code_path)),
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
        record_name = self.api_config.hosted_zone.get("record_name", None)

        if not record_name:
            return

        hosted_zone_id = self.api_config.hosted_zone.get("id", None)

        if not hosted_zone_id:
            raise ValueError(
                "Hosted zone id is required, when you specify a hosted zone record name"
            )

        hosted_zone_name = self.api_config.hosted_zone.get("name", None)
        if not hosted_zone_name:
            raise ValueError(
                "Hosted zone name is required, when you specify a hosted zone record name"
            )

        hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
            self,
            "HostedZone",
            hosted_zone_id=hosted_zone_id,
            zone_name=hosted_zone_name,
        )

        certificate: acm.Certificate | None = None
        # either get or create the cert
        if self.api_config.ssl_cert_arn:
            certificate = acm.Certificate.from_certificate_arn(
                self,
                "ApiCertificate",
                self.api_config.ssl_cert_arn,
            )
        else:
            certificate = acm.Certificate(
                self,
                id="ApiCertificate",
                domain_name=record_name,
                validation=acm.CertificateValidation.from_dns(hosted_zone=hosted_zone),
            )

        if certificate:
            # API Gateway custom domain
            api_gateway_domain_resource = apigateway.DomainName(
                self,
                "ApiCustomDomain",
                domain_name=record_name,
                certificate=certificate,
            )

            # Base path mapping - root path to your stage
            apigateway.BasePathMapping(
                self,
                "ApiBasePathMapping",
                domain_name=api_gateway_domain_resource,
                rest_api=api,
                stage=api.deployment_stage,
                base_path="",  # Root path
            )

            # A Record
            route53.ARecord(
                self,
                "ARecordApi",
                zone=hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    aws_route53_targets.ApiGatewayDomain(api_gateway_domain_resource)
                ),
            )

            # AAAA Record
            route53.AaaaRecord(
                self,
                "AAAARecordApi",
                zone=hosted_zone,
                record_name=record_name,
                target=route53.RecordTarget.from_alias(
                    aws_route53_targets.ApiGatewayDomain(api_gateway_domain_resource)
                ),
            )
