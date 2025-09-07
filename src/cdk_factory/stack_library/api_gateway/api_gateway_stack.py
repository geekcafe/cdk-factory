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
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import (
    EnhancedSsmParameterMixin,
)
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

logger = Logger(service="ApiGatewayStack")


@register_stack("api_gateway_library_module")
@register_stack("api_gateway_stack")
class ApiGatewayStack(IStack, EnhancedSsmParameterMixin):
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

        self.api_config = ApiGatewayConfig(
            stack_config.dictionary.get("api_gateway", {})
        )

        # Initialize integration utility
        self.integration_utility = ApiGatewayIntegrationUtility(self)

        api_type = self.api_config.api_type
        api_name = self.api_config.name or "api-gateway"
        api_id = deployment.build_resource_name(api_name)

        routes = self.api_config.routes or [
            {"path": "/health", "method": "GET", "src": None, "handler": None}
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
        # Use shared utility for consistent API Gateway creation
        # Note: The utility now creates API Gateway with deploy=False to prevent stage conflicts
        api_gateway = self.integration_utility.create_api_gateway_with_config(
            api_id, self.api_config, self.stack_config
        )
        
        # Setup API Gateway components in logical order
        self._setup_api_resources_and_methods(api_gateway)
        api_keys = self._setup_api_keys()
        self._setup_usage_plans(api_gateway, api_keys)
        authorizer = self._setup_cognito_authorizer(api_gateway, api_id)
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
                request_templates={
                    "application/json": '{"statusCode": 200}'
                },
            )

    def _create_method_responses(self, method_config):
        """Create method responses for a method"""
        method_responses = []
        for response in method_config.get(
            "method_responses", [{"status_code": "200"}]
        ):
            status_code = response.get("status_code", "200")
            response_models = {}

            # Handle response models
            for content_type, model_name in response.get(
                "response_models", {}
            ).items():
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
                api_stages=[
                    apigateway.UsagePlanPerApiStage(
                        api=api_gateway, stage=getattr(api_gateway, '_deployment_stage', None)
                    )
                ] if hasattr(api_gateway, '_deployment_stage') and api_gateway._deployment_stage else [],
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
            period=apigateway.Period[
                plan_config["quota"].get("period", "MONTH")
            ],
        )

    def _setup_cognito_authorizer(self, api_gateway, api_id):
        """Setup Cognito authorizer if configured"""
        if not self.api_config.cognito_authorizer:
            return None
            
        route_config = ApiGatewayConfigRouteConfig({})
        return self.integration_utility.get_or_create_authorizer(
            api_gateway, route_config, self.stack_config, api_id
        )

    def _setup_lambda_routes(self, api_gateway, api_id, routes, authorizer):
        """Setup Lambda routes and integrations"""
        for route in routes:
            self._setup_single_lambda_route(api_gateway, api_id, route, authorizer)

    def _setup_single_lambda_route(self, api_gateway, api_id, route, authorizer):
        """Setup a single Lambda route with integration and CORS"""
        suffix = route["path"].strip("/").replace("/", "-") or "health"
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
        self._setup_lambda_integration(api_gateway, api_id, route, lambda_fn, authorizer, suffix)
        
        # Setup CORS
        self._setup_route_cors(resource, route_path, route)

    def _setup_lambda_integration(self, api_gateway, api_id, route, lambda_fn, authorizer, suffix):
        """Setup Lambda integration for a route"""
        route_path = route["path"]
        authorization_type = route.get("authorization_type")
        
        if route.get("src"):
            # Use shared utility for consistent Lambda integration behavior
            api_route_config = ApiGatewayConfigRouteConfig(
                {
                    "method": route["method"],
                    "route": route_path,
                    "authorization_type": (
                        authorization_type if authorization_type else "NONE"
                    ),
                    "api_key_required": False,
                    "skip_authorizer": not authorizer,
                    "user_pool_id": (
                        os.getenv("COGNITO_USER_POOL_ID") if authorizer else None
                    ),
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

    def _setup_fallback_lambda_integration(self, api_gateway, route, lambda_fn, authorizer, api_id, suffix):
        """Setup fallback Lambda integration for routes without src"""
        route_path = route["path"]
        authorization_type = route.get("authorization_type")
        
        resource = (
            api_gateway.root.resource_for_path(route_path)
            if route_path != "/"
            else api_gateway.root
        )
        
        integration = apigateway.LambdaIntegration(lambda_fn)
        method_options = {}

        # Handle authorization type
        if (
            authorizer
            and authorization_type
            and authorization_type.upper() != "NONE"
        ):
            method_options["authorization_type"] = (
                apigateway.AuthorizationType.COGNITO
            )
            method_options["authorizer"] = authorizer
        else:
            method_options["authorization_type"] = (
                apigateway.AuthorizationType.NONE
            )

        # Add the method with proper options
        try:
            resource.add_method(
                route["method"].upper(), integration, **method_options
            )
            
            # Store integration info for deployment finalization
            integration_info = {
                "api_gateway": api_gateway,
                "function_name": f"{api_id}-lambda-{suffix}",
                "route_path": route_path,
                "method": route["method"].upper()
            }
            self.api_gateway_integrations.append(integration_info)
            
        except Exception as e:
            error_msg = f"Failed to create method {route['method'].upper()} on {route_path}: {str(e)}"
            print(error_msg)
            raise Exception(error_msg) from e

    def _setup_route_cors(self, resource, route_path, route):
        """Setup CORS for a route"""
        cors_cfg = route.get("cors")
        methods = cors_cfg.get("methods") if cors_cfg else None
        origins = cors_cfg.get("origins") if cors_cfg else None
        ApiGatewayUtilities.bind_mock_for_cors(
            resource,
            route_path,
            http_method_list=methods,
            origins_list=origins,
        )

    def _store_deployment_stage_reference(self, api_gateway, stage):
        """Store stage reference for later use"""
        if stage:
            api_gateway._deployment_stage = stage
            # Also set it as the deployment_stage property that CDK expects
            try:
                # This is a bit of a hack, but we need to set the deployment stage
                # so that api_gateway.url works properly
                object.__setattr__(api_gateway, '_deployment_stage_internal', stage)
            except:
                pass

    def __finalize_api_gateway_deployments(self):
        """
        Create new deployments for API Gateways after all routes have been added.
        This ensures that all routes are included in the deployed stage.
        Returns the created stage for the first API Gateway.
        """
        if not hasattr(self, 'api_gateway_integrations') or not self.api_gateway_integrations:
            logger.info("No API Gateway integrations found, skipping deployment finalization")
            return None

        # Group integrations by API Gateway using object identity instead of CDK token
        api_gateways = {}
        api_counter = 0
        
        for integration in self.api_gateway_integrations:
            api_gateway = integration.get('api_gateway')
            if api_gateway:
                # Use object identity as key instead of CDK token
                api_key = id(api_gateway)
                if api_key not in api_gateways:
                    api_counter += 1
                    api_gateways[api_key] = {
                        'api_gateway': api_gateway,
                        'integrations': [],
                        'counter': api_counter
                    }
                api_gateways[api_key]['integrations'].append(integration)

        created_stage = None
        
        # Create new deployments for each API Gateway
        for api_key, api_info in api_gateways.items():
            api_gateway = api_info['api_gateway']
            integration_count = len(api_info['integrations'])
            counter = api_info['counter']
            
            logger.info(f"Creating new deployment for API Gateway {counter} with {integration_count} integrations")
            
            # Create a new deployment using counter for construct ID
            deployment = apigateway.Deployment(
                self,
                f"api-gateway-{counter}-deployment-final",
                api=api_gateway,
                description=f"Deployment with all {integration_count} routes included"
            )
            
            # Update or create the stage with the new deployment using proper stage options
            stage_name = self.api_config.stage_name  # Use configurable stage name
            if stage_name is None:
                raise ValueError("Stage name is required in API Gateway config")
            if stage_name.lower() == "auto":
                try:
                    stage_name = self.stack_config.name
                except Exception as e:
                    raise ValueError("Stage name is required in API Gateway config") from e
            
            stage_options = self._deploy_options()
            
            stage = apigateway.Stage(
                self,
                f"api-gateway-{counter}-stage-final",
                deployment=deployment,
                stage_name=stage_name,
                description=f"Production stage with all routes deployed",
                access_log_destination=stage_options.access_log_destination,
                access_log_format=stage_options.access_log_format,
                logging_level=stage_options.logging_level,
                data_trace_enabled=stage_options.data_trace_enabled,
                metrics_enabled=stage_options.metrics_enabled,
                tracing_enabled=stage_options.tracing_enabled,
                throttling_rate_limit=stage_options.throttling_rate_limit,
                throttling_burst_limit=stage_options.throttling_burst_limit
            )
            
            # Store the first created stage to return
            if created_stage is None:
                created_stage = stage
            
            logger.info(f"Created stage '{stage_name}' for API Gateway {counter}")
        
        return created_stage

    def _export_ssm_parameters(self, api_gateway, authorizer=None):
        """Export API Gateway resources to SSM using enhanced SSM parameter mixin"""

        # Setup enhanced SSM integration with proper resource type and name
        api_name = self.api_config.name or "api-gateway"

        self.setup_enhanced_ssm_integration(
            scope=self,
            config=self.stack_config.dictionary.get("api_gateway", {}),
            resource_type="api-gateway",
            resource_name=api_name,
        )

        # Prepare resource values for export
        resource_values = {
            "api_id": api_gateway.rest_api_id,
            "api_arn": api_gateway.arn_for_execute_api(),
            "root_resource_id": api_gateway.rest_api_root_resource_id,
        }
        
        # Add URL by constructing it manually since we have a custom deployment pattern
        try:
            # Construct the API URL manually using the API ID and region
            region = self.deployment.region
            stage_name = "prod"  # Default stage name we use
            api_url = f"https://{api_gateway.rest_api_id}.execute-api.{region}.amazonaws.com/{stage_name}"
            resource_values["api_url"] = api_url
            logger.info(f"Successfully constructed API URL: {api_url}")
        except Exception as e:
            logger.warning(f"Could not construct API URL: {e}")
            pass

        # Add authorizer ID if available
        if authorizer:
            resource_values["authorizer_id"] = authorizer.authorizer_id

        # Use enhanced SSM parameter export
        exported_params = self.auto_export_resources(resource_values)

        if exported_params:
            logger.info(
                f"Exported {len(exported_params)} API Gateway parameters to SSM"
            )
        else:
            logger.info("No SSM parameters configured for export")

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
                stage=getattr(api, '_deployment_stage', None) or api.deployment_stage,
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
