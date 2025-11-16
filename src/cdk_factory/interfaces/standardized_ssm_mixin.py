"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

"""
Standardized SSM Parameter Mixin for CDK Factory

This is the single, standardized approach for SSM parameter handling
across all CDK Factory modules. It replaces the mixed patterns of
Basic SSM, Enhanced SSM, and Custom SSM handling.

Key Features:
- Single source of truth for SSM integration
- Consistent configuration structure
- Template variable resolution
- Comprehensive validation
- Clear error handling
- Backward compatibility support
"""

import os
import re
from typing import Dict, Any, Optional, List, Union
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from constructs import Construct
from aws_lambda_powertools import Logger
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.workload import WorkloadConfig

logger = Logger(service="StandardizedSsmMixin")


class StandardizedSsmMixin:
    """
    Standardized SSM parameter mixin for all CDK Factory modules.
    
    This mixin provides a single, consistent approach for SSM parameter
    handling that will be used across all modules to eliminate confusion
    and ensure consistency.
    
    Standard Configuration Structure:
    {
        "ssm": {
            "enabled": true,
            "imports": {
                "parameter_name": "/path/to/parameter"
            },
            "exports": {
                "parameter_name": {
                    "path": "/path/to/export",
                    "value": "parameter_value_or_reference"
                }
            }
        }
    }
    
    Key Features:
    - Configuration-driven SSM imports/exports
    - Template variable resolution
    - List parameter support (for security groups, etc.)
    - Cached imported values for easy access
    - Backward compatibility with existing interfaces
    """

    def __init__(self, *args, **kwargs):
        """Initialize the mixin with cached storage for imported values."""
        # Don't call super() to avoid MRO issues in multiple inheritance
        # Initialize cached storage for imported values
        self._ssm_imported_values: Dict[str, Union[str, List[str]]] = {}
        self._ssm_exported_values: Dict[str, str] = {}

    # Backward compatibility methods from old SsmParameterMixin
    def get_ssm_imported_value(self, key: str, default: Any = None) -> Any:
        """Get an SSM imported value by key with optional default."""
        return self._ssm_imported_values.get(key, default)

    def has_ssm_import(self, key: str) -> bool:
        """Check if an SSM import exists by key."""
        return key in self._ssm_imported_values

    def export_ssm_parameter(
        self,
        scope: Construct,
        id: str,
        value: Any,
        parameter_name: str,
        description: str = None,
        string_value: str = None
    ) -> ssm.StringParameter:
        """Export a value to SSM Parameter Store."""
        if string_value is None:
            string_value = str(value)
        
        param = ssm.StringParameter(
            scope,
            id,
            parameter_name=parameter_name,
            string_value=string_value,
            description=description or f"SSM parameter: {parameter_name}"
        )
        
        # Store in exported values for tracking
        self._ssm_exported_values[parameter_name] = string_value
        return param

    def export_resource_to_ssm(
        self,
        scope: Construct,
        resource_values: Dict[str, Any],
        config: Any = None,
        resource_name: str = None,
        resource_type: str = None,
        context: Dict[str, Any] = None
    ) -> Dict[str, ssm.StringParameter]:
        """Export multiple resource values to SSM Parameter Store."""
        params = {}
        
        invalid_export_keys = []
        # Only export parameters that are explicitly configured in ssm_exports
        if not hasattr(config, 'ssm_exports') or not config.ssm_exports:
            logger.debug("No SSM exports configured")
            return params
            
        for key, export_path in config.ssm_exports.items():
            # Only export if the value exists in resource_values
            if key in resource_values:
                value = resource_values[key]
                
                param = self.export_ssm_parameter(
                    scope=scope,
                    id=f"{resource_name}-{key}-param",
                    value=value,
                    parameter_name=export_path,
                    description=f"{(resource_type or 'Resource').title()} {key} for {resource_name}"
                )
                params[key] = param
            else:
                invalid_export_keys.append(key)
                logger.warning(f"SSM export configured for '{key}' but no value found in resource_values")
        
        if invalid_export_keys:
            message = f"Export SSM Error\n🚨 SSM exports configured for '{invalid_export_keys}' but no values found in resource_values"
            available_keys = list(resource_values.keys())
            message = f"{message}\n✅ Available keys: {available_keys}"
            message = f"{message}\n👉 Please update to the correct key or remove from the export list."
            logger.warning(message)
            raise ValueError(message)
            
        return params

    def normalize_resource_name(self, name: str, for_export: bool = False) -> str:
        """Normalize a resource name for SSM parameter naming."""
        # Convert to lowercase and replace special characters with hyphens
        import re
        normalized = re.sub(r'[^a-zA-Z0-9-]', '-', str(name).lower())
        # Remove consecutive hyphens
        normalized = re.sub(r'-+', '-', normalized)
        # Remove leading/trailing hyphens
        normalized = normalized.strip('-')
        return normalized

    def setup_ssm_integration(
        self,
        scope: Construct,
        config: Any,
        resource_type: str,
        resource_name: str,
        deployment: DeploymentConfig = None,
        workload: WorkloadConfig = None
    ):
        """
        Setup standardized SSM integration - single entry point for all modules.
        
        Args:
            scope: The CDK construct scope
            config: Configuration object with SSM settings
            resource_type: Type of resource (e.g., 'vpc', 'auto_scaling', 'ecs')
            resource_name: Name of the resource instance
            deployment: Deployment configuration for template variables
            workload: Workload configuration for template variables
        """
        # Store configuration references
        self.scope = scope
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.deployment = deployment
        self.workload = workload
        
        # Extract configuration dictionary
        if hasattr(config, 'dictionary'):
            self.config_dict = config.dictionary
        elif isinstance(config, dict):
            self.config_dict = config
        else:
            self.config_dict = {}
        
        # Initialize SSM storage
        self._ssm_imported_values: Dict[str, Union[str, List[str]]] = {}
        self._ssm_exported_values: Dict[str, str] = {}
        
        # Extract SSM configuration
        self.ssm_config = self.config_dict.get("ssm", {})
        
        # Validate SSM configuration structure
        self._validate_ssm_configuration()
        
        logger.info(f"Setup standardized SSM integration for {resource_type}/{resource_name}")
        logger.info(f"SSM imports: {len(self.ssm_config.get('imports', {}))}")
        logger.info(f"SSM exports: {len(self.ssm_config.get('exports', {}))}")
    
    def process_ssm_imports(self) -> None:
        """
        Process SSM imports using standardized approach.
        
        This method handles:
        - Template variable resolution
        - Path validation
        - CDK token creation
        - Error handling
        """
        imports = self.ssm_config.get("imports", {})
        
        if not imports:
            logger.info(f"No SSM imports configured for {self.resource_type}/{self.resource_name}")
            return
        
        logger.info(f"Processing {len(imports)} SSM imports for {self.resource_type}/{self.resource_name}")
        
        for import_key, import_value in imports.items():
            try:
                resolved_value = self._resolve_ssm_import(import_value, import_key)
                self._ssm_imported_values[import_key] = resolved_value
                logger.info(f"Successfully imported SSM parameter: {import_key}")
            except Exception as e:
                error_msg = f"Failed to import SSM parameter {import_key}: {str(e)}"
                logger.error(error_msg)
                raise ValueError(error_msg)
    
    def export_ssm_parameters(self, resource_values: Dict[str, Any]) -> Dict[str, str]:
        """
        Export SSM parameters using standardized approach.
        
        Args:
            resource_values: Dictionary of resource values to export
            
        Returns:
            Dictionary mapping attribute names to SSM parameter paths
        """
        exports = self.ssm_config.get("exports", {})
        
        if not exports:
            logger.info(f"No SSM exports configured for {self.resource_type}/{self.resource_name}")
            return {}
        
        logger.info(f"Exporting {len(exports)} SSM parameters for {self.resource_type}/{self.resource_name}")
        
        exported_params = {}
        for export_key, export_path in exports.items():
            if export_key not in resource_values:
                logger.warning(f"Export key '{export_key}' not found in resource values")
                continue
            
            value = resource_values[export_key]
            if value is None:
                logger.warning(f"Export value for '{export_key}' is None, skipping")
                continue
            
            try:
                self._create_ssm_parameter(export_key, export_path, value)
                exported_params[export_key] = export_path
                logger.info(f"Successfully exported SSM parameter: {export_key}")
            except Exception as e:
                logger.error(f"Failed to export SSM parameter {export_key}: {str(e)}")
                raise
        
        return exported_params
    
    def resolve_ssm_value(self, scope: Construct, value: str, unique_id: str) -> str:
        """
        Resolve SSM parameter references with support for different parameter types.
        
        Supported patterns:
        - {{ssm:path}} - String or SecureString parameter (default)
        - {{ssm-secure:path}} - SecureString parameter (explicit, for clarity)
        - {{ssm-list:path}} - StringList parameter (returns comma-separated string)
        
        Args:
            scope: CDK construct scope
            value: Value that may contain SSM reference
            unique_id: Unique identifier for the construct
            
        Returns:
            Resolved SSM parameter value as a CDK token
        """
        if not isinstance(value, str):
            return value
        
        import re
        
        # Check if SSM reference is embedded in a larger string (e.g., ARN with SSM reference)
        # Example: "arn:aws:s3:::{{ssm:/path/to/bucket}}/*"
        # Pattern matches: {{ssm:...}}, {{ssm-list:...}}, {{ssm-secure:...}}
        if "{{ssm" in value and not value.startswith("{{ssm"):
            match = re.search(r'\{\{ssm[^}]*:[^}]+\}\}', value)
            if match:
                ssm_ref = match.group(0)
                # Recursively resolve the SSM reference itself (handles all types)
                ssm_value = self.resolve_ssm_value(scope, ssm_ref, f"{unique_id}-embedded")
                # Replace the SSM reference with resolved value in the original string
                resolved_value = value.replace(ssm_ref, ssm_value)
                logger.info(f"Resolved embedded SSM in string: {value} -> {resolved_value}")
                return resolved_value
        
        # Define SSM patterns with their handlers
        ssm_patterns = [
            {
                "prefix": "{{ssm-list:",
                "type": "StringList",
                "extract_path": lambda v: v[11:-2],  # Remove {{ssm-list: and }}
                "resolve": lambda path: ssm.StringParameter.value_for_string_list_parameter(
                    scope=scope, parameter_name=path
                )
            },
            {
                "prefix": "{{ssm-secure:",
                "type": "SecureString",
                "extract_path": lambda v: v[13:-2],  # Remove {{ssm-secure: and }}
                "resolve": lambda path: ssm.StringParameter.value_for_secure_string_parameter_name(
                    scope=scope, parameter_name=path, version=1
                )
            },
            {
                "prefix": "{{ssm:",
                "type": "String",
                "extract_path": lambda v: v[6:-2],  # Remove {{ssm: and }}
                "resolve": lambda path: ssm.StringParameter.from_string_parameter_name(
                    scope=scope,
                    id=f"{unique_id}-env-{hash(path) % 10000}",
                    string_parameter_name=path
                ).string_value
            }
        ]
        
        # Try each pattern in order (most specific first)
        for pattern in ssm_patterns:
            if value.startswith(pattern["prefix"]) and value.endswith("}}"):
                ssm_param_path = pattern["extract_path"](value)
                resolved_value = pattern["resolve"](ssm_param_path)
                logger.info(f"Resolved SSM {pattern['type']} parameter: {ssm_param_path}")
                return resolved_value
        
        # No SSM pattern matched
        return value

    def _resolve_ssm_import(self, import_value: Union[str, List[str]], import_key: str) -> Union[str, List[str]]:
        """
        Resolve SSM import value with proper error handling and validation.
        
        Args:
            import_value: SSM path or list of SSM paths
            import_key: Import key for error reporting
            
        Returns:
            Resolved CDK token(s) for the SSM parameter(s)
        """
        if isinstance(import_value, list):
            # Handle list imports (like security group IDs)
            resolved_list = []
            for i, value in enumerate(import_value):
                resolved_item = self._resolve_single_ssm_import(value, f"{import_key}[{i}]")
                resolved_list.append(resolved_item)
            return resolved_list
        else:
            # Handle single imports
            return self._resolve_single_ssm_import(import_value, import_key)
    
    def _resolve_single_ssm_import(self, ssm_path: str, context: str) -> str:
        """
        Resolve individual SSM parameter import.
        
        Args:
            ssm_path: SSM parameter path with template variables
            context: Context for error reporting
            
        Returns:
            CDK token for the SSM parameter
        """
        # Resolve template variables in path
        resolved_path = self._resolve_template_variables(ssm_path)
        
        # Validate path format
        self._validate_ssm_path(resolved_path, context)
        
        # Create CDK SSM parameter reference
        construct_id = f"import-{context.replace('.', '-').replace('[', '-').replace(']', '-')}"
        param = ssm.StringParameter.from_string_parameter_name(
            self.scope, construct_id, resolved_path
        )
        
        # Return the CDK token (will resolve at deployment time)
        return param.string_value
    
    def _resolve_template_variables(self, template_string: str) -> str:
        """
        Resolve template variables in SSM paths.
        
        Supported variables:
        - {{ENVIRONMENT}}: Deployment environment
        - {{WORKLOAD_NAME}}: Workload name
        - {{AWS_REGION}}: AWS region
        
        Args:
            template_string: String with template variables
            
        Returns:
            Resolved string with variables replaced
        """
        if not template_string:
            return template_string
        
        # Prepare template variables
        variables = {}
        
        # Always prioritize workload environment for consistency
        if self.workload:
            variables["ENVIRONMENT"] = self.workload.dictionary.get("environment", "test")
            variables["WORKLOAD_NAME"] = self.workload.dictionary.get("name", "test-workload")
            variables["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")
        elif self.deployment:
            # Fallback to deployment only if workload not available
            variables["ENVIRONMENT"] = self.deployment.environment
            variables["WORKLOAD_NAME"] = self.deployment.workload_name
            variables["AWS_REGION"] = getattr(self.deployment, 'region', None) or os.getenv("AWS_REGION", "us-east-1")
        else:
            # Final fallback to environment variables
            variables["ENVIRONMENT"] = os.getenv("ENVIRONMENT", "test")
            variables["WORKLOAD_NAME"] = os.getenv("WORKLOAD_NAME", "test-workload")
            variables["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")
        
        # Replace template variables
        resolved = template_string
        for key, value in variables.items():
            pattern = r"\{\{" + re.escape(key) + r"\}\}"
            resolved = re.sub(pattern, str(value), resolved)
        
        # Check for unresolved variables
        unresolved_vars = re.findall(r"\{\{([^}]+)\}\}", resolved)
        if unresolved_vars:
            logger.warning(f"Unresolved template variables: {unresolved_vars}")
        
        return resolved
    
    def _validate_ssm_path(self, path: str, context: str) -> None:
        """
        Validate SSM parameter path format.
        
        Args:
            path: SSM parameter path to validate
            context: Context for error reporting
            
        Raises:
            ValueError: If path format is invalid
        """
        if not path:
            raise ValueError(f"{context}: SSM path cannot be empty")
        
        if not path.startswith("/"):
            raise ValueError(f"{context}: SSM path must start with '/': {path}")
        
        segments = path.split("/")
        if len(segments) < 4:
            raise ValueError(f"{context}: SSM path must have at least 4 segments: {path}")
        
        # Validate path structure
        # segments[0] = "" (empty from leading /)
        # segments[1] = environment
        # segments[2] = workload_name  
        # segments[3] = resource_type
        # segments[4+] = attribute
        
        if len(segments) >= 4:
            environment = segments[1]
            resource_type = segments[3]
            
            # Check for valid environment patterns
            if environment not in ["dev", "staging", "prod", "test", "alpha", "beta", "sandbox"]:
                logger.warning(f"{context}: Unusual environment segment: {environment}")
            
            # Check for valid resource type patterns
            if not re.match(r'^[a-z][a-z0-9_-]*$', resource_type):
                logger.warning(f"{context}: Unusual resource type segment: {resource_type}")
    
    def _validate_ssm_configuration(self) -> None:
        """
        Validate the overall SSM configuration structure.
        
        Raises:
            ValueError: If configuration structure is invalid
        """
        if not isinstance(self.ssm_config, dict):
            raise ValueError("SSM configuration must be a dictionary")
        
        # Validate imports
        imports = self.ssm_config.get("imports", {})
        if imports is not None and not isinstance(imports, dict):
            raise ValueError("SSM imports must be a dictionary")
        
        # Validate exports
        exports = self.ssm_config.get("exports", {})
        if exports is not None and not isinstance(exports, dict):
            raise ValueError("SSM exports must be a dictionary")
        
        # Validate import paths
        for key, value in imports.items():
            if isinstance(value, list):
                for i, item in enumerate(value):
                    self._validate_ssm_path(item, f"imports.{key}[{i}]")
            else:
                self._validate_ssm_path(value, f"imports.{key}")
        
        # Validate export paths
        for key, value in exports.items():
            self._validate_ssm_path(value, f"exports.{key}")
    
    def _create_ssm_parameter(self, export_key: str, export_path: str, value: Any) -> ssm.StringParameter:
        """
        Create SSM parameter with standard settings.
        
        Args:
            export_key: Export key for construct ID
            export_path: SSM parameter path
            value: Value to store
            
        Returns:
            Created SSM parameter
        """
        # Resolve template variables in export path
        resolved_path = self._resolve_template_variables(export_path)
        
        # Validate export path
        self._validate_ssm_path(resolved_path, f"exports.{export_key}")
        
        # Generate unique construct ID
        construct_id = f"export-{export_key.replace('_', '-')}"
        
        # Create SSM parameter with standard settings
        param = ssm.StringParameter(
            self.scope,
            construct_id,
            parameter_name=resolved_path,
            string_value=str(value),
            description=f"Auto-exported {export_key} for {self.resource_type}/{self.resource_name}",
            tier=ssm.ParameterTier.STANDARD
        )
        
        # Track exported parameter
        self._ssm_exported_values[export_key] = resolved_path
        
        return param
    
    # Public interface methods for accessing SSM values
    
    def has_ssm_import(self, import_name: str) -> bool:
        """
        Check if SSM import exists.
        
        Args:
            import_name: Name of the import to check
            
        Returns:
            True if import exists, False otherwise
        """
        return import_name in self._ssm_imported_values
    
    def get_ssm_imported_value(self, import_name: str, default: Any = None) -> Any:
        """
        Get SSM imported value with optional default.
        
        Args:
            import_name: Name of the import
            default: Default value if import not found
            
        Returns:
            Imported value or default
        """
        return self._ssm_imported_values.get(import_name, default)
    
    def get_ssm_exported_path(self, export_name: str) -> Optional[str]:
        """
        Get SSM exported parameter path.
        
        Args:
            export_name: Name of the export
            
        Returns:
            SSM parameter path or None if not found
        """
        return self._ssm_exported_values.get(export_name)
    
    def get_all_ssm_imports(self) -> Dict[str, Union[str, List[str]]]:
        """
        Get all SSM imported values.
        
        Returns:
            Dictionary of all imported values
        """
        return self._ssm_imported_values.copy()
    
    def get_all_ssm_exports(self) -> Dict[str, str]:
        """
        Get all SSM exported parameter paths.
        
        Returns:
            Dictionary of all exported parameter paths
        """
        return self._ssm_exported_values.copy()
    
    
    def get_subnet_ids(self, config) -> List[str]:
        """
        Helper function to parse subnet IDs from SSM imports.
        
        This common pattern handles:
        1. Comma-separated subnet ID strings from SSM
        2. List of subnet IDs from SSM
        3. Fallback to config attributes
        
        Args:
            config: Configuration object that might have subnet_ids attribute
            
        Returns:
            List of subnet IDs (empty list if not found or invalid format)
        """
        # Use the standardized SSM imports
        ssm_imports = self.get_all_ssm_imports()
        if "subnet_ids" in ssm_imports:
            subnet_ids = ssm_imports["subnet_ids"]
            
            # Handle comma-separated string or list
            if isinstance(subnet_ids, str):
                # Split comma-separated string
                parsed_ids = [sid.strip() for sid in subnet_ids.split(',') if sid.strip()]
                return parsed_ids
            elif isinstance(subnet_ids, list):
                return subnet_ids
            else:
                logger.warning(f"Unexpected subnet_ids type: {type(subnet_ids)}")
                return []
        
        # Fallback: Check config attributes
        elif hasattr(config, 'subnet_ids') and config.subnet_ids:
            return config.subnet_ids
        
        else:
            logger.warning("No subnet IDs found, using default behavior")
            return []

class ValidationResult:
    """Result of configuration validation."""
    
    def __init__(self, valid: bool, errors: List[str] = None):
        self.valid = valid
        self.errors = errors or []


class SsmStandardValidator:
    """Validator for SSM standard compliance."""
    
    def validate_configuration(self, config: dict) -> ValidationResult:
        """
        Validate configuration against SSM standards.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            ValidationResult with validation status and errors
        """
        errors = []
        
        # Check SSM configuration structure
        ssm_config = config.get("ssm", {})
        if not isinstance(ssm_config, dict):
            errors.append("ssm configuration must be a dictionary")
        else:
            # Validate imports
            imports = ssm_config.get("imports", {})
            if imports is not None and not isinstance(imports, dict):
                errors.append("ssm.imports must be a dictionary")
            else:
                for key, value in imports.items():
                    errors.extend(self._validate_import(key, value))
            
            # Validate exports
            exports = ssm_config.get("exports", {})
            if exports is not None and not isinstance(exports, dict):
                errors.append("ssm.exports must be a dictionary")
            else:
                for key, value in exports.items():
                    errors.extend(self._validate_export(key, value))
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def _validate_import(self, key: str, value) -> List[str]:
        """Validate individual import configuration."""
        errors = []
        
        if isinstance(value, list):
            for i, item in enumerate(value):
                errors.extend(self._validate_ssm_path(item, f"imports.{key}[{i}]"))
        else:
            errors.extend(self._validate_ssm_path(value, f"imports.{key}"))
        
        return errors
    
    def _validate_export(self, key: str, value: str) -> List[str]:
        """Validate individual export configuration."""
        return self._validate_ssm_path(value, f"exports.{key}")
    
    def _validate_ssm_path(self, path: str, context: str) -> List[str]:
        """Validate SSM parameter path format."""
        errors = []
        
        if not path:
            errors.append(f"{context}: SSM path cannot be empty")
        elif not path.startswith("/"):
            errors.append(f"{context}: SSM path must start with '/': {path}")
        else:
            segments = path.split("/")
            if len(segments) < 4:
                errors.append(f"{context}: SSM path must have at least 4 segments: {path}")
            
            # Check for template variables
            if "{{ENVIRONMENT}}" not in path and "{{WORKLOAD_NAME}}" not in path:
                errors.append(f"{context}: SSM path should use template variables: {path}")
        
        return errors
    
        
    
