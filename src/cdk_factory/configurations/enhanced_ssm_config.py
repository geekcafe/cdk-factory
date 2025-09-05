"""Enhanced SSM Parameter Configuration for CDK Factory"""

import os
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum


class SsmMode(Enum):
    AUTO = "auto"
    MANUAL = "manual"
    DISABLED = "disabled"


@dataclass
class SsmParameterDefinition:
    """Defines an SSM parameter with its metadata"""

    attribute: str
    path: Optional[str] = None
    description: Optional[str] = None
    parameter_type: str = "String"  # String, StringList, SecureString
    auto_export: bool = True
    auto_import: bool = True


class EnhancedSsmConfig:
    """Enhanced SSM configuration with auto-discovery and flexible patterns"""

    def __init__(
        self,
        config: Dict,
        resource_type: str,
        resource_name: str,
    ):
        self.config = config.get("ssm", {})
        self.resource_type = resource_type
        self.resource_name = resource_name

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)

    @property
    def organization(self) -> str:
        return self.config.get("organization", "default")

    @property
    def environment(self) -> str:
        env = self.config.get("environment", "${ENVIRONMENT}")
        # Replace environment variables
        if env.startswith("${") and env.endswith("}"):
            env_var = env[2:-1]
            return os.getenv(env_var, "dev")
        return env

    @property
    def pattern(self) -> str:
        return self.config.get(
            "pattern",
            "/{organization}/{environment}/{stack_type}/{resource_name}/{attribute}",
        )


    @property
    def auto_export(self) -> bool:
        return self.config.get("auto_export", True)

    @property
    def auto_import(self) -> bool:
        return self.config.get("auto_import", True)

    def get_parameter_path(
        self, attribute: str, custom_path: Optional[str] = None
    ) -> str:
        """Generate SSM parameter path using pattern or custom path"""
        if custom_path and custom_path.startswith("/"):
            return custom_path

        # Use enhanced pattern
        return self.pattern.format(
            organization=self.organization,
            environment=self.environment,
            stack_type=self.resource_type,
            resource_name=self.resource_name,
            attribute=attribute,
        )

    def get_export_definitions(self) -> List[SsmParameterDefinition]:
        """Get list of parameters to export"""
        exports = self.config.get("exports", {})
        definitions = []

        # Add auto-discovered exports
        if self.auto_export:
            auto_exports = self._get_auto_exports()
            for attr in auto_exports:
                if attr not in exports:
                    exports[attr] = "auto"

        # Convert to parameter definitions
        for attr, path_config in exports.items():
            custom_path = None if path_config == "auto" else path_config
            definitions.append(
                SsmParameterDefinition(
                    attribute=attr,
                    path=self.get_parameter_path(attr, custom_path),
                    auto_export=True,
                )
            )

        return definitions

    def get_import_definitions(self) -> List[SsmParameterDefinition]:
        """Get list of parameters to import"""
        imports = self.config.get("imports", {})
        definitions = []

        # Add auto-discovered imports
        if self.auto_import:
            auto_imports = self._get_auto_imports()
            for attr in auto_imports:
                if attr not in imports:
                    imports[attr] = "auto"

        # Convert to parameter definitions
        for attr, path_config in imports.items():
            custom_path = None if path_config == "auto" else path_config
            definitions.append(
                SsmParameterDefinition(
                    attribute=attr,
                    path=self.get_parameter_path(attr, custom_path),
                    auto_import=True,
                )
            )

        return definitions

    def _get_auto_exports(self) -> List[str]:
        """Get auto-discovered exports based on resource type"""
        return RESOURCE_AUTO_EXPORTS.get(self.resource_type, [])

    def _get_auto_imports(self) -> List[str]:
        """Get auto-discovered imports based on resource type"""
        return RESOURCE_AUTO_IMPORTS.get(self.resource_type, [])


# Resource type definitions for auto-discovery
RESOURCE_AUTO_EXPORTS = {
    "vpc": [
        "vpc_id",
        "vpc_cidr",
        "public_subnet_ids",
        "private_subnet_ids",
        "isolated_subnet_ids",
    ],
    "security_group": ["security_group_id"],
    "rds": ["db_instance_id", "db_endpoint", "db_port", "db_secret_arn"],
    "api_gateway": [
        "api_id",
        "api_arn",
        "api_url",
        "root_resource_id",
        "authorizer_id",
    ],
    "cognito": [
        "user_pool_id",
        "user_pool_arn",
        "user_pool_name",
        "user_pool_client_id",
    ],
    "lambda": ["function_name", "function_arn"],
    "s3": ["bucket_name", "bucket_arn"],
    "dynamodb": ["table_name", "table_arn", "table_stream_arn"],
}

RESOURCE_AUTO_IMPORTS = {
    "security_group": ["vpc_id"],
    "rds": ["vpc_id", "security_group_ids", "subnet_group_name"],
    "lambda": ["vpc_id", "security_group_ids", "subnet_ids"],
    "api_gateway": ["user_pool_arn"],
    "ecs": ["vpc_id", "security_group_ids", "subnet_ids"],
    "alb": ["vpc_id", "security_group_ids", "subnet_ids"],
}
