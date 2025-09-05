"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, Optional, List
import os
from dataclasses import dataclass
from enum import Enum

from .base_config import BaseConfig


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


# Resource type definitions for auto-discovery
RESOURCE_AUTO_EXPORTS = {
    "vpc": ["vpc_id", "vpc_cidr", "public_subnet_ids", "private_subnet_ids", "isolated_subnet_ids"],
    "security_group": ["security_group_id"],
    "rds": ["db_instance_id", "db_endpoint", "db_port", "db_secret_arn"],
    "api_gateway": ["api_gateway_id", "api_gateway_arn", "root_resource_id", "authorizer_id"],
    "cognito": ["user_pool_id", "user_pool_arn", "user_pool_client_id"],
    "lambda": ["function_name", "function_arn"],
    "s3": ["bucket_name", "bucket_arn"],
    "dynamodb": ["table_name", "table_arn"],
    "ecr": ["repository_name", "repository_arn", "repository_uri"],
    "load_balancer": ["load_balancer_arn", "load_balancer_dns_name", "target_group_arn"],
    "auto_scaling": ["auto_scaling_group_name", "auto_scaling_group_arn"]
}

RESOURCE_AUTO_IMPORTS = {
    "security_group": ["vpc_id"],
    "rds": ["vpc_id", "security_group_ids", "subnet_group_name"],
    "lambda": ["vpc_id", "security_group_ids", "subnet_ids"],
    "api_gateway": ["cognito_user_pool_id", "cognito_user_pool_arn"],
    "ecs": ["vpc_id", "security_group_ids", "subnet_ids"],
    "alb": ["vpc_id", "security_group_ids", "subnet_ids"],
    "load_balancer": ["vpc_id", "security_group_ids", "subnet_ids"],
    "auto_scaling": ["vpc_id", "security_group_ids", "subnet_ids", "load_balancer_target_group_arn"]
}


class EnhancedBaseConfig(BaseConfig):
    """
    Enhanced base configuration class with auto-discovery SSM parameter support.
    
    This class extends BaseConfig to provide automatic discovery of SSM parameters
    based on resource types, while maintaining full backward compatibility.
    
    Features:
    - Auto-discovery of export/import parameters based on resource type
    - Flexible pattern templates with environment variable support
    - Backward compatibility with existing ssm_parameters, ssm_exports, ssm_imports
    - Environment-aware parameter path generation
    """
    
    def __init__(self, config: Dict[str, Any], resource_type: str = None, resource_name: str = None) -> None:
        """
        Initialize the enhanced configuration.
        
        Args:
            config: Dictionary containing configuration values
            resource_type: The type of resource (e.g., 'vpc', 'api_gateway')
            resource_name: The name of the resource instance
        """
        super().__init__(config)
        self.resource_type = resource_type
        self.resource_name = resource_name
        # Support both "ssm" and "ssm" field names for backward compatibility
        self._ssm_config = config.get("ssm", {})

        if  config.get("enhanced_ssm") is not None:
            raise ValueError("SSM parameter error: 'enhanced_ssm' is no longer supported, change to 'ssm' field name.")
        
    @property
    def ssm_enabled(self) -> bool:
        """Check if SSM parameter integration is enabled"""
        return self._ssm_config.get("enabled", True)
    
    @property
    def ssm_organization(self) -> str:
        """Get the organization name for SSM parameter paths"""
        return self._ssm_config.get("organization", "cdk-factory")
    
    @property
    def ssm_environment(self) -> str:
        """Get the environment name for SSM parameter paths"""
        env = self._ssm_config.get("environment", "${ENVIRONMENT}")
        # Replace environment variables
        if env.startswith("${") and env.endswith("}"):
            env_var = env[2:-1]
            return os.getenv(env_var, "dev")
        return env
    
    @property
    def ssm_pattern(self) -> str:
        """Get the SSM parameter path pattern"""
        # Support both "pattern" and "parameter_template" field names
        pattern = self._ssm_config.get("parameter_template") or self._ssm_config.get("pattern")
        if pattern:
            return pattern
        return "/{organization}/{environment}/{stack_type}/{resource_name}/{attribute}"
    
    @property
    def ssm_auto_export(self) -> bool:
        """Check if auto-export is enabled"""
        return self._ssm_config.get("auto_export", True)
    
    @property
    def ssm_auto_import(self) -> bool:
        """Check if auto-import is enabled"""
        return self._ssm_config.get("auto_import", True)
    
    def get_parameter_path(self, attribute: str, custom_path: Optional[str] = None, context: Dict[str, Any] = None) -> str:
        """
        Generate SSM parameter path using pattern or custom path.
        
        Args:
            attribute: The attribute name (e.g., 'vpc_id', 'db_endpoint')
            custom_path: Custom path override
            context: Additional context variables for template formatting
            
        Returns:
            The formatted SSM parameter path
        """
        if custom_path and custom_path.startswith("/"):
            return custom_path
            
        # Use the enhanced pattern
        pattern = self.ssm_pattern
        
        # Build context for template formatting
        format_context = {
            "organization": self.ssm_organization,
            "environment": self.ssm_environment,
            "stack_type": self.resource_type or "unknown",
            "resource_name": custom_path or attribute,
            "attribute": custom_path or attribute
        }
        
        # Add any additional context variables
        if context:
            format_context.update(context)
        
        # Handle template variables in curly braces (e.g., {{ENVIRONMENT}})
        import re
        def replace_template_vars(match):
            var_name = match.group(1)
            if var_name in format_context:
                return str(format_context[var_name])
            # Try environment variables
            env_value = os.getenv(var_name)
            if env_value:
                return env_value
            # Return original if not found
            return match.group(0)
        
        # Replace {{VAR}} patterns first
        pattern = re.sub(r'\{\{([^}]+)\}\}', replace_template_vars, pattern)
        
        # Then handle {resource_name} patterns
        try:
            return pattern.format(**format_context)
        except KeyError as e:
            # If a required variable is missing, log a warning and return a fallback path
            import logging
            logging.warning(f"Missing template variable {e} for SSM path pattern: {pattern}")
            return f"/{self.ssm_organization}/{self.ssm_environment}/{attribute}"
    
    def get_auto_export_attributes(self) -> List[str]:
        """Get list of attributes that should be auto-exported for this resource type"""
        if not self.resource_type:
            return []
        return RESOURCE_AUTO_EXPORTS.get(self.resource_type, [])
    
    def get_auto_import_attributes(self) -> List[str]:
        """Get list of attributes that should be auto-imported for this resource type"""
        if not self.resource_type:
            return []
        return RESOURCE_AUTO_IMPORTS.get(self.resource_type, [])
    
    def get_export_definitions(self, context: Dict[str, Any] = None) -> List[SsmParameterDefinition]:
        """
        Get list of parameters to export with auto-discovery support.
        
        Args:
            context: Additional context variables for template formatting
            
        Returns:
            List of SSM parameter definitions for export
        """
        if not self.ssm_enabled:
            return []
            
        definitions = []
        
        # Start with configured exports - support both "exports" and "parameters" field names
        configured_exports = self._ssm_config.get("exports", self._ssm_config.get("parameters", {}))
        
        # Add auto-discovered exports if enabled
        if self.ssm_auto_export:
            auto_exports = self.get_auto_export_attributes()
            for attr in auto_exports:
                attr_key = f"{attr}_path"
                if attr_key not in configured_exports:
                    configured_exports[attr_key] = "auto"
        
        # Also check legacy ssm_exports from base config
        legacy_exports = self.ssm_exports
        for key, path in legacy_exports.items():
            if key not in configured_exports:
                configured_exports[key] = path
        
        # Convert to parameter definitions
        for attr_key, path_config in configured_exports.items():
            # Extract attribute name (remove _path suffix if present)
            attr_name = attr_key[:-5] if attr_key.endswith("_path") else attr_key
            
            # Determine the actual path
            if path_config == "auto":
                actual_path = self.get_parameter_path(attr_name, context=context)
            else:
                # Use the path_config as the resource_name part in the template
                actual_path = self.get_parameter_path(path_config, context=context)
            
            definitions.append(SsmParameterDefinition(
                attribute=attr_name,
                path=actual_path,
                description=f"Auto-exported {attr_name} for {self.resource_name or self.resource_type}",
                auto_export=True
            ))
            
        return definitions
    
    def get_import_definitions(self, context: Dict[str, Any] = None) -> List[SsmParameterDefinition]:
        """
        Get list of parameters to import with auto-discovery support.
        
        Args:
            context: Additional context variables for template formatting
            
        Returns:
            List of SSM parameter definitions for import
        """
        if not self.ssm_enabled:
            return []
            
        definitions = []
        
        # Start with configured imports
        configured_imports = self._ssm_config.get("imports", {})
        
        # Add auto-discovered imports if enabled
        if self.ssm_auto_import:
            auto_imports = self.get_auto_import_attributes()
            for attr in auto_imports:
                attr_key = f"{attr}_path"
                if attr_key not in configured_imports:
                    configured_imports[attr_key] = "auto"
        
        # Also check legacy ssm_imports from base config
        legacy_imports = self.ssm_imports
        for key, path in legacy_imports.items():
            if key not in configured_imports:
                configured_imports[key] = path
        
        # Convert to parameter definitions
        for attr_key, path_config in configured_imports.items():
            # Extract attribute name (remove _path suffix if present)
            attr_name = attr_key[:-5] if attr_key.endswith("_path") else attr_key
            
            # Determine the actual path
            if path_config == "auto":
                actual_path = self.get_parameter_path(attr_name, context=context)
            else:
                actual_path = self.get_parameter_path(attr_name, path_config, context)
            
            definitions.append(SsmParameterDefinition(
                attribute=attr_name,
                path=actual_path,
                description=f"Auto-imported {attr_name} for {self.resource_name or self.resource_type}",
                auto_import=True
            ))
            
        return definitions
    
    # Override parent methods to use enhanced functionality
    def get_export_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for exporting a specific attribute with enhanced auto-discovery.
        """
        # First check if we have enhanced SSM config
        if self.ssm_enabled:
            export_defs = self.get_export_definitions(context)
            for definition in export_defs:
                if definition.attribute == key:
                    return definition.path
        
        # Fall back to parent implementation
        return super().get_export_path(key, resource_type or self.resource_type, resource_name or self.resource_name, context)
    
    def get_import_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for importing a specific attribute with enhanced auto-discovery.
        """
        # First check if we have enhanced SSM config
        if self.ssm_enabled:
            import_defs = self.get_import_definitions(context)
            for definition in import_defs:
                if definition.attribute == key:
                    return definition.path
        
        # Fall back to parent implementation
        return super().get_import_path(key, resource_type or self.resource_type, resource_name or self.resource_name, context)
