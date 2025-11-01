"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

"""
Configuration Validator for CDK Factory

Provides comprehensive validation for all CDK Factory configurations
including SSM integration, dependencies, and module-specific requirements.
"""

import json
import jsonschema
from typing import Dict, Any, List, Optional
from pathlib import Path
from aws_lambda_powertools import Logger

from cdk_factory.interfaces.standardized_ssm_mixin import SsmStandardValidator, ValidationResult

logger = Logger(service="ConfigValidator")


class ConfigValidator:
    """
    Comprehensive configuration validator for CDK Factory.
    
    Validates:
    - Module configuration against JSON schemas
    - SSM configuration structure and paths
    - Dependency graph consistency
    - Template variable usage
    - Required parameters and formats
    """
    
    def __init__(self, schemas_dir: Optional[str] = None):
        """
        Initialize configuration validator.
        
        Args:
            schemas_dir: Directory containing JSON schema files
        """
        self.schemas = self._load_schemas(schemas_dir)
        self.ssm_validator = SsmStandardValidator()
    
    def _load_schemas(self, schemas_dir: Optional[str]) -> Dict[str, Dict[str, Any]]:
        """
        Load JSON schemas for module validation.
        
        Args:
            schemas_dir: Directory containing schema files
            
        Returns:
            Dictionary mapping module names to schemas
        """
        schemas = {}
        
        # Default schemas directory
        if not schemas_dir:
            schemas_dir = Path(__file__).parent.parent / "schemas"
        
        schemas_path = Path(schemas_dir)
        if not schemas_path.exists():
            logger.warning(f"Schemas directory not found: {schemas_path}")
            return schemas
        
        # Load all JSON schema files
        for schema_file in schemas_path.glob("*.json"):
            try:
                with open(schema_file, 'r') as f:
                    schema = json.load(f)
                    module_name = schema_file.stem
                    schemas[module_name] = schema
                    logger.info(f"Loaded schema for module: {module_name}")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")
        
        return schemas
    
    def validate_module_config(self, module_name: str, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate module configuration against its JSON schema.
        
        Args:
            module_name: Name of the module
            config: Configuration dictionary to validate
            
        Returns:
            ValidationResult with validation status and errors
        """
        errors = []
        
        # Check if schema exists for module
        if module_name not in self.schemas:
            # Use generic schema if module-specific schema not found
            schema = self._get_generic_schema()
            logger.info(f"Using generic schema for module: {module_name}")
        else:
            schema = self.schemas[module_name]
        
        try:
            jsonschema.validate(config, schema)
            logger.info(f"Module configuration validation passed: {module_name}")
        except jsonschema.ValidationError as e:
            error_msg = f"Configuration validation failed: {e.message}"
            if e.absolute_path:
                error_msg += f" at {'.'.join(str(p) for p in e.absolute_path)}"
            errors.append(error_msg)
            logger.error(error_msg)
        except Exception as e:
            errors.append(f"Schema validation error: {str(e)}")
            logger.error(f"Schema validation error for {module_name}: {e}")
        
        # Additional module-specific validations
        module_errors = self._validate_module_specific(module_name, config)
        errors.extend(module_errors)
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def validate_ssm_configuration(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate SSM configuration using standardized validator.
        
        Args:
            config: Configuration dictionary containing SSM settings
            
        Returns:
            ValidationResult with validation status and errors
        """
        return self.ssm_validator.validate_configuration(config)
    
    def validate_dependencies(self, config: Dict[str, Any], available_stacks: List[str]) -> ValidationResult:
        """
        Validate dependency configuration.
        
        Args:
            config: Configuration dictionary with dependencies
            available_stacks: List of available stack names
            
        Returns:
            ValidationResult with validation status and errors
        """
        errors = []
        
        dependencies = config.get("dependencies", [])
        if not isinstance(dependencies, list):
            errors.append("dependencies must be a list")
            return ValidationResult(valid=False, errors=errors)
        
        # Check that all dependencies exist
        for dep in dependencies:
            if dep not in available_stacks:
                errors.append(f"Dependency not found: {dep}")
        
        # Check for circular dependencies
        if self._has_circular_dependency(config.get("name", ""), dependencies, available_stacks):
            errors.append("Circular dependency detected")
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def validate_template_variables(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate template variable usage in configuration.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            ValidationResult with validation status and errors
        """
        errors = []
        
        def find_template_variables(obj, path=""):
            if isinstance(obj, str):
                import re
                variables = re.findall(r'\{\{([^}]+)\}\}', obj)
                for var in variables:
                    # Check for valid template variables
                    valid_vars = ["ENVIRONMENT", "WORKLOAD_NAME", "AWS_REGION", "RESOURCE_NAME"]
                    if var not in valid_vars:
                        errors.append(f"Invalid template variable '{var}' at {path}")
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    find_template_variables(value, current_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    find_template_variables(item, f"{path}[{i}]")
        
        find_template_variables(config)
        
        return ValidationResult(valid=len(errors) == 0, errors=errors)
    
    def validate_complete_configuration(self, config: Dict[str, Any], available_stacks: List[str] = None) -> ValidationResult:
        """
        Perform comprehensive validation of configuration.
        
        Args:
            config: Complete configuration dictionary
            available_stacks: List of available stack names for dependency validation
            
        Returns:
            ValidationResult with comprehensive validation status
        """
        all_errors = []
        
        # Validate required fields
        required_fields = ["name", "module"]
        for field in required_fields:
            if field not in config:
                all_errors.append(f"Missing required field: {field}")
        
        # Validate module configuration
        module_name = config.get("module")
        if module_name:
            module_validation = self.validate_module_config(module_name, config)
            all_errors.extend(module_validation.errors)
        
        # Validate SSM configuration
        ssm_validation = self.validate_ssm_configuration(config)
        all_errors.extend(ssm_validation.errors)
        
        # Validate dependencies
        if available_stacks:
            dep_validation = self.validate_dependencies(config, available_stacks)
            all_errors.extend(dep_validation.errors)
        
        # Validate template variables
        template_validation = self.validate_template_variables(config)
        all_errors.extend(template_validation.errors)
        
        return ValidationResult(valid=len(all_errors) == 0, errors=all_errors)
    
    def _validate_module_specific(self, module_name: str, config: Dict[str, Any]) -> List[str]:
        """
        Perform module-specific validations.
        
        Args:
            module_name: Name of the module
            config: Configuration dictionary
            
        Returns:
            List of validation errors
        """
        errors = []
        
        if module_name == "vpc_library_module":
            errors.extend(self._validate_vpc_config(config))
        elif module_name == "auto_scaling_library_module":
            errors.extend(self._validate_auto_scaling_config(config))
        elif module_name == "ecs_cluster_stack":
            errors.extend(self._validate_ecs_config(config))
        
        return errors
    
    def _validate_vpc_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate VPC-specific configuration."""
        errors = []
        vpc_config = config.get("vpc", {})
        
        # Validate CIDR format
        cidr = vpc_config.get("cidr")
        if cidr:
            import ipaddress
            try:
                ipaddress.IPv4Network(cidr)
            except ValueError:
                errors.append(f"Invalid CIDR format: {cidr}")
        
        # Validate max AZs
        max_azs = vpc_config.get("max_azs")
        if max_azs and (not isinstance(max_azs, int) or max_azs < 1 or max_azs > 6):
            errors.append(f"max_azs must be an integer between 1 and 6: {max_azs}")
        
        return errors
    
    def _validate_auto_scaling_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate Auto Scaling-specific configuration."""
        errors = []
        asg_config = config.get("auto_scaling", {})
        
        # Validate capacity settings
        min_capacity = asg_config.get("min_capacity")
        max_capacity = asg_config.get("max_capacity")
        desired_capacity = asg_config.get("desired_capacity")
        
        if all([min_capacity, max_capacity, desired_capacity]):
            if not (min_capacity <= desired_capacity <= max_capacity):
                errors.append("desired_capacity must be between min_capacity and max_capacity")
        
        # Validate instance type
        instance_type = asg_config.get("instance_type")
        if instance_type:
            valid_types = ["t2.nano", "t2.micro", "t2.small", "t2.medium", "t2.large",
                          "t3.nano", "t3.micro", "t3.small", "t3.medium", "t3.large",
                          "t3a.nano", "t3a.micro", "t3a.small", "t3a.medium", "t3a.large"]
            if instance_type not in valid_types:
                errors.append(f"Invalid instance type: {instance_type}")
        
        return errors
    
    def _validate_ecs_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate ECS-specific configuration."""
        errors = []
        ecs_config = config.get("ecs", {})
        
        # Validate capacity providers
        capacity_providers = ecs_config.get("capacity_providers", [])
        valid_providers = ["FARGATE", "FARGATE_SPOT", "EC2", "EC2_SPOT"]
        
        for provider in capacity_providers:
            if provider not in valid_providers:
                errors.append(f"Invalid capacity provider: {provider}")
        
        return errors
    
    def _get_generic_schema(self) -> Dict[str, Any]:
        """Get generic schema for modules without specific schemas."""
        return {
            "type": "object",
            "required": ["name", "module"],
            "properties": {
                "name": {
                    "type": "string",
                    "pattern": "^[a-zA-Z0-9][a-zA-Z0-9_-]*$"
                },
                "module": {
                    "type": "string"
                },
                "enabled": {
                    "type": "boolean",
                    "default": True
                },
                "dependencies": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "default": []
                },
                "ssm": {
                    "type": "object",
                    "properties": {
                        "imports": {
                            "type": "object",
                            "patternProperties": {
                                "^[a-zA-Z][a-zA-Z0-9_]*$": {
                                    "oneOf": [
                                        {"type": "string"},
                                        {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    ]
                                }
                            }
                        },
                        "exports": {
                            "type": "object",
                            "patternProperties": {
                                "^[a-zA-Z][a-zA-Z0-9_]*$": {"type": "string"}
                            }
                        }
                    },
                    "additionalProperties": False
                }
            },
            "additionalProperties": True
        }
    
    def _has_circular_dependency(self, stack_name: str, dependencies: List[str], available_stacks: List[str]) -> bool:
        """
        Check for circular dependencies using simple detection.
        
        Args:
            stack_name: Name of the current stack
            dependencies: List of dependencies for current stack
            available_stacks: List of all available stacks
            
        Returns:
            True if circular dependency detected
        """
        # Simple check: if stack appears in its own dependencies
        if stack_name in dependencies:
            return True
        
        # For more complex circular dependency detection,
        # we would need to build the full dependency graph
        # This is a simplified implementation
        return False


class SchemaGenerator:
    """Generate JSON schemas for module configurations."""
    
    def generate_schema_from_module(self, module_class) -> Dict[str, Any]:
        """
        Generate JSON schema from module class documentation.
        
        Args:
            module_class: Module class to generate schema for
            
        Returns:
            JSON schema dictionary
        """
        # This would parse module class documentation and config classes
        # to generate appropriate JSON schemas
        # For now, return a basic schema
        return {
            "type": "object",
            "required": ["name", "module"],
            "properties": {
                "name": {"type": "string"},
                "module": {"type": "string"}
            }
        }
    
    def save_schema(self, module_name: str, schema: Dict[str, Any], output_dir: str):
        """
        Save JSON schema to file.
        
        Args:
            module_name: Name of the module
            schema: JSON schema to save
            output_dir: Directory to save schema in
        """
        output_path = Path(output_dir) / f"{module_name}.json"
        
        with open(output_path, 'w') as f:
            json.dump(schema, f, indent=2)
        
        logger.info(f"Saved schema for {module_name} to {output_path}")


# Utility functions for validation

def validate_configuration_file(file_path: str, validator: ConfigValidator = None) -> ValidationResult:
    """
    Validate a configuration file.
    
    Args:
        file_path: Path to configuration file
        validator: ConfigValidator instance (creates default if None)
        
    Returns:
        ValidationResult with validation status
    """
    if validator is None:
        validator = ConfigValidator()
    
    try:
        with open(file_path, 'r') as f:
            config = json.load(f)
        
        return validator.validate_complete_configuration(config)
    
    except Exception as e:
        return ValidationResult(valid=False, errors=[f"Failed to load configuration file: {str(e)}"])


def validate_configurations_directory(directory: str, validator: ConfigValidator = None) -> Dict[str, ValidationResult]:
    """
    Validate all configuration files in a directory.
    
    Args:
        directory: Directory containing configuration files
        validator: ConfigValidator instance (creates default if None)
        
    Returns:
        Dictionary mapping file names to validation results
    """
    if validator is None:
        validator = ConfigValidator()
    
    results = {}
    config_dir = Path(directory)
    
    for config_file in config_dir.glob("*.json"):
        result = validate_configuration_file(str(config_file), validator)
        results[config_file.name] = result
    
    return results
