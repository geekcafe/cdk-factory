"""
ApiGatewayConfig - supports all major RestApi settings for AWS CDK.
Maintainers: Eric Wilson
MIT License. See Project Root for license information.
"""

from typing import Any
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig


class ApiGatewayConfig(EnhancedBaseConfig):
    """
    API Gateway Configuration - supports all major RestApi settings.
    Each property reads from the config dict and provides a sensible default if not set.
    """

    def __init__(self, config: dict = None) -> None:
        super().__init__(
            config or {},
            resource_type="api-gateway",
            resource_name=(
                config.get("name", "api-gateway") if config else "api-gateway"
            ),
        )
        self.__config = config or {}

    @property
    def name(self) -> str | None:
        return self.__config.get("name") or self.__config.get("name")

    @property
    def description(self) -> str | None:
        return self.__config.get("description")

    @property
    def deploy(self) -> bool:
        return self.__config.get("deploy", True)

    @property
    def deploy_options(self) -> dict:
        return self.__config.get("deploy_options", {})

    @property
    def endpoint_types(self) -> list[str] | None:
        return self.__config.get("endpoint_types")

    @property
    def api_key_source_type(self) -> str | None:
        return self.__config.get("api_key_source_type")

    @property
    def binary_media_types(self) -> list[str] | None:
        return self.__config.get("binary_media_types")

    @property
    def cloud_watch_role(self) -> bool:
        return self.__config.get("cloud_watch_role", True)

    @property
    def default_cors_preflight_options(self) -> dict | None:
        return self.__config.get("default_cors_preflight_options")

    @property
    def default_method_options(self) -> dict | None:
        return self.__config.get("default_method_options")

    @property
    def default_integration(self) -> dict | None:
        return self.__config.get("default_integration")

    @property
    def disable_execute_api_endpoint(self) -> bool:
        return self.__config.get("disable_execute_api_endpoint", False)

    @property
    def endpoint_export_name(self) -> str | None:
        return self.__config.get("endpoint_export_name")

    @property
    def fail_on_warnings(self) -> bool:
        return self.__config.get("fail_on_warnings", False)

    @property
    def min_compression_size(self) -> int | None:
        return self.__config.get("min_compression_size")

    @property
    def parameters(self) -> dict | None:
        return self.__config.get("parameters")

    @property
    def policy(self) -> Any:
        return self.__config.get("policy")

    @property
    def retain_deployments(self) -> bool:
        return self.__config.get("retain_deployments", False)

    @property
    def rest_api_id(self) -> str | None:
        return self.__config.get("rest_api_id")

    @property
    def root_resource_id(self) -> str | None:
        return self.__config.get("root_resource_id")

    @property
    def cloud_watch_role_removal_policy(self) -> str | None:
        return self.__config.get("cloud_watch_role_removal_policy")

    @property
    def api_type(self) -> str:
        """API type: REST (default) or HTTP"""
        return self.__config.get("api_type", "REST").upper()

    @property
    def routes(self) -> list[dict]:
        """List of route definitions (path, method)"""
        return self.__config.get("routes", [])

    @property
    def cognito_authorizer(self) -> dict | None:
        """Cognito authorizer config: expects dict with user_pool_arn, authorizer_name, identity_source"""
        return self.__config.get("cognito_authorizer")

    # Add more properties as needed for all RestApi/HttpApi options
    @property
    def hosted_zone(self) -> dict:
        return self.__config.get("hosted_zone", {})

    @property
    def ssl_cert_arn(self) -> str | None:
        return self.__config.get("ssl_cert_arn")

    @property
    def resources(self) -> list[dict]:
        """List of resource definitions for API Gateway"""
        return self.__config.get("resources", [])

    @property
    def api_keys(self) -> list[dict]:
        """List of API key definitions"""
        return self.__config.get("api_keys", [])

    @property
    def usage_plans(self) -> list[dict]:
        """List of usage plan definitions"""
        return self.__config.get("usage_plans", [])

    @property
    def export_to_ssm(self) -> bool:
        """Whether to export API Gateway configuration to SSM parameters for cross-stack references"""
        return self.__config.get("export_to_ssm", False)

    @property
    def stage_name(self) -> str:
        """API Gateway deployment stage name (default: 'prod')"""
        return self.__config.get("stage_name", "prod")
