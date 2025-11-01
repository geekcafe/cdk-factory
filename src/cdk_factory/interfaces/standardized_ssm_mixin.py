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
        "imports": {
          "vpc_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/vpc/id",
          "security_group_ids": ["/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/sg/ecs-id"]
        },
        "exports": {
          "resource_id": "/{{ENVIRONMENT}}/{{WORKLOAD_NAME}}/resource-type/id"
        }
      }
    }
    """
    
    def setup_standardized_ssm_integration(
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
    
    def process_standardized_ssm_imports(self) -> None:
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
    
    def export_standardized_ssm_parameters(self, resource_values: Dict[str, Any]) -> Dict[str, str]:
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
        
        if self.deployment:
            variables["ENVIRONMENT"] = self.deployment.environment
            variables["WORKLOAD_NAME"] = self.deployment.workload_name
            variables["AWS_REGION"] = getattr(self.deployment, 'region', None) or os.getenv("AWS_REGION", "us-east-1")
        elif self.workload:
            variables["ENVIRONMENT"] = getattr(self.workload, 'environment', 'test')
            variables["WORKLOAD_NAME"] = getattr(self.workload, 'name', 'test-workload')
            variables["AWS_REGION"] = os.getenv("AWS_REGION", "us-east-1")
        else:
            # Fallback to environment variables
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
            if environment not in ["dev", "staging", "prod", "test"]:
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
