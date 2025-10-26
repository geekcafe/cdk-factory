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
        workload_config: Optional[Dict] = None,
        deployment_config: Optional[Dict] = None,
    ):
        self.config = config.get("ssm", {})
        self.resource_type = resource_type
        self.resource_name = resource_name
        self._workload_config = workload_config or {}
        self._deployment_config = deployment_config or {}  # Deprecated, for backward compatibility

    @property
    def enabled(self) -> bool:
        return self.config.get("enabled", True)

    @property
    def workload(self) -> str:
        """Get workload name for SSM parameter paths (backward compatible with 'organization')"""
        # Try 'workload' first, fall back to 'organization' for backward compatibility
        return self.config.get("workload", self.config.get("organization", "default"))

    @property
    def environment(self) -> str:
        """
        Get environment - MUST be at workload level.
        
        Architecture: One workload deployment = One environment
        
        Priority:
        1. workload_config["environment"] - **STANDARD LOCATION** (required)
        2. workload_config["deployment"]["environment"] - Legacy (backward compatibility)
        3. deployment_config["environment"] - Legacy (backward compatibility)
        4. config["ssm"]["environment"] - Legacy (backward compatibility)
        5. ${ENVIRONMENT} - Environment variable (with validation)
        
        NO DEFAULT to 'dev' - fails explicitly to prevent cross-environment contamination
        
        Best Practice:
            {
              "workload": {
                "name": "my-app",
                "environment": "dev"  ← Single source of truth
              }
            }
        """
        # 1. Try workload config first (STANDARD LOCATION)
        env = self._workload_config.get("environment")
        
        # 2. Try workload["deployment"]["environment"] (backward compatibility)
        if not env:
            env = self._workload_config.get("deployment", {}).get("environment")
        
        # 3. Try deployment config (backward compatibility)
        if not env:
            env = self._deployment_config.get("environment")
        
        # 4. Fall back to SSM config (backward compatibility)
        if not env:
            env = self.config.get("environment", "${ENVIRONMENT}")
        
        # 5. Resolve environment variables
        if isinstance(env, str) and env.startswith("${") and env.endswith("}"):
            env_var = env[2:-1]
            env_value = os.getenv(env_var)
            if not env_value:
                raise ValueError(
                    f"Environment variable '{env_var}' is not set. "
                    f"Cannot default to 'dev' as this may cause cross-environment contamination. "
                    f"Best practice: Set 'environment' at workload level in your config. "
                    f"Alternatively, set the {env_var} environment variable."
                )
            return env_value
        
        # If still no environment, fail explicitly
        if not env:
            raise ValueError(
                "Environment must be explicitly specified at workload level. "
                "Cannot default to 'dev' as this may cause cross-environment resource contamination. "
                "Best practice: Add 'environment' to your workload config:\n"
                '  {"workload": {"name": "...", "environment": "dev|prod"}}'
            )
        
        return env

    @property
    def pattern(self) -> str:
        return self.config.get(
            "pattern",
            "/{workload}/{environment}/{stack_type}/{resource_name}/{attribute}",
        )


    @property
    def auto_export(self) -> bool:
        return self.config.get("auto_export", True)

    @property
    def auto_import(self) -> bool:
        return self.config.get("auto_import", True)

    @property
    def ssm_exports(self) -> List[Dict[str, Any]]:
        """Get explicit SSM exports configuration"""
        return self.config.get("exports", [])

    @property
    def ssm_imports(self) -> List[Dict[str, Any]]:
        """Get explicit SSM imports configuration"""
        return self.config.get("imports", [])

    def get_parameter_path(
        self, attribute: str, custom_path: Optional[str] = None
    ) -> str:
        """Generate SSM parameter path using pattern or custom path"""
        # Handle custom_path - must be a string starting with "/"
        # Protect against incorrect config like: "exports": {"enabled": true}
        if custom_path and isinstance(custom_path, str) and custom_path.startswith("/"):
            return custom_path

        # Convert underscore attribute names to hyphen format for consistent SSM paths
        formatted_attribute = attribute.replace("_", "-")

        # Use enhanced pattern (support both workload and organization for backward compatibility)
        return self.pattern.format(
            workload=self.workload,
            organization=self.workload,  # Backward compatibility
            environment=self.environment,
            stack_type=self.resource_type,
            resource_name=self.resource_name,
            attribute=formatted_attribute,
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

    def get_import_definitions(self, context: Dict[str, Any] = None) -> List[SsmParameterDefinition]:
        """Get SSM parameter definitions for imports"""
        definitions = []
        
        # Process explicit imports (can be dict format like {"user_pool_arn": "auto"} or list format)
        if self.ssm_imports:
            if isinstance(self.ssm_imports, dict):
                # Handle dict format: {"attribute": "auto" or path}
                # Skip metadata fields that are not actual imports
                metadata_fields = {"workload", "environment", "organization"}
                
                for attribute, import_value in self.ssm_imports.items():
                    # Skip metadata fields - they specify context, not what to import
                    if attribute in metadata_fields:
                        continue
                        
                    if import_value == "auto":
                        # Use auto-discovery with source mapping
                        imports_config = RESOURCE_AUTO_IMPORTS.get(self.resource_type, {})
                        import_info = imports_config.get(attribute, {})
                        source_resource_type = import_info.get("source_resource_type")
                        
                        if source_resource_type:
                            # Use default resource name for the source type
                            default_names = {
                                "vpc": "main-vpc",
                                "cognito": "user-pool", 
                                "security_group": "main-sg",
                                "dynamodb": "cdk-factory-table",
                                "api_gateway": "cdk-factory-api-gw",
                                "api-gateway": "cdk-factory-api-gw"
                            }
                            source_resource_name = default_names.get(source_resource_type, f"main-{source_resource_type}")
                            path = self._get_parameter_path_for_source(attribute, source_resource_type, source_resource_name)
                        else:
                            # Fallback to current resource path
                            path = self.get_parameter_path(attribute)
                    else:
                        # Use explicit path
                        path = import_value
                    
                    definitions.append(
                        SsmParameterDefinition(
                            attribute=attribute,
                            path=path,
                            parameter_type="String",
                            description=f"Imported {attribute}"
                        )
                    )
            elif isinstance(self.ssm_imports, list):
                # Handle list format: [{"attribute": "...", "path": "..."}]
                for import_config in self.ssm_imports:
                    definitions.append(
                        SsmParameterDefinition(
                            attribute=import_config["attribute"],
                            path=import_config["path"],
                            parameter_type=import_config.get("type", "String"),
                            description=import_config.get("description", f"Imported {import_config['attribute']}")
                        )
                    )
        
        # Process auto-discovered imports
        if self.auto_import:
            imports_config = RESOURCE_AUTO_IMPORTS.get(self.resource_type, {})
            for attribute, import_info in imports_config.items():
                # Skip if already processed in explicit imports
                if self.ssm_imports and isinstance(self.ssm_imports, dict) and attribute in self.ssm_imports:
                    continue
                    
                source_resource_type = import_info.get("source_resource_type")
                source_resource_name = import_info.get("source_resource_name")
                
                if source_resource_type:
                    # Generate path using source resource type and name
                    if source_resource_name:
                        path = self._get_parameter_path_for_source(attribute, source_resource_type, source_resource_name)
                    else:
                        # Use a default/generic resource name pattern for the source type
                        default_names = {
                            "vpc": "main-vpc",
                            "cognito": "user-pool", 
                            "security_group": "main-sg",
                            "dynamodb": "cdk-factory-table",
                            "api_gateway": "cdk-factory-api-gw",
                            "api-gateway": "cdk-factory-api-gw"
                        }
                        source_resource_name = default_names.get(source_resource_type, f"main-{source_resource_type}")
                        path = self._get_parameter_path_for_source(attribute, source_resource_type, source_resource_name)
                else:
                    # Fallback to current behavior if no source specified
                    path = self.get_parameter_path(attribute)
                
                definitions.append(
                    SsmParameterDefinition(
                        attribute=attribute,
                        path=path,
                        parameter_type="String",
                        description=f"Auto-imported {attribute} from {source_resource_type or 'unknown'}"
                    )
                )

        return definitions

    def _get_auto_exports(self) -> List[str]:
        """Get auto-discovered exports based on resource type"""
        return RESOURCE_AUTO_EXPORTS.get(self.resource_type, [])

    def _get_auto_imports(self) -> List[str]:
        """Get auto-discovered imports based on resource type"""
        imports_config = RESOURCE_AUTO_IMPORTS.get(self.resource_type, {})
        return list(imports_config.keys())

    def _get_parameter_path_for_source(self, attribute: str, source_resource_type: str, source_resource_name: str) -> str:
        """Generate SSM parameter path using source resource type and name instead of current resource"""
        # Convert underscores to hyphens for consistent path formatting
        formatted_attribute = attribute.replace("_", "-")
        formatted_resource_name = source_resource_name.replace("_", "-")
        formatted_resource_type = source_resource_type.replace("_", "-")
        
        return f"/{self.workload}/{self.environment}/{formatted_resource_type}/{formatted_resource_name}/{formatted_attribute}"


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
    "api-gateway": [
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
        "authorizer_id",
    ],
    "lambda": ["function_name", "function_arn"],
    "s3": ["bucket_name", "bucket_arn"],
    "dynamodb": ["table_name", "table_arn", "table_stream_arn"],
}

# Enhanced import structure that maps attributes to their source resource types
RESOURCE_AUTO_IMPORTS = {
    "security_group": {
        "vpc_id": {"source_resource_type": "vpc"}
    },
    "rds": {
        "vpc_id": {"source_resource_type": "vpc"},
        "security_group_ids": {"source_resource_type": "security_group"},
        "subnet_group_name": {"source_resource_type": "vpc"}
    },
    "lambda": {
        "vpc_id": {"source_resource_type": "vpc"},
        "security_group_ids": {"source_resource_type": "security_group"},
        "subnet_ids": {"source_resource_type": "vpc"},
        "user_pool_arn": {"source_resource_type": "cognito"},
        "table_name": {"source_resource_type": "dynamodb"}
    },
    "api_gateway": {
        "user_pool_arn": {"source_resource_type": "cognito"},
        "authorizer_id": {"source_resource_type": "cognito"}
    },
    "api-gateway": {
        "user_pool_arn": {"source_resource_type": "cognito"},
        "authorizer_id": {"source_resource_type": "cognito"}
    },
    "ecs": {
        "vpc_id": {"source_resource_type": "vpc"},
        "security_group_ids": {"source_resource_type": "security_group"},
        "subnet_ids": {"source_resource_type": "vpc"}
    },
    "alb": {
        "vpc_id": {"source_resource_type": "vpc"},
        "security_group_ids": {"source_resource_type": "security_group"},
        "subnet_ids": {"source_resource_type": "vpc"}
    },
}
