"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, Optional


class BaseConfig:
    """
    Base configuration class that provides common functionality for all resource configurations.
    
    This class serves as the foundation for all resource-specific configuration classes,
    providing standardized access to configuration properties and SSM parameter paths.
    
    SSM parameter paths can be customized with prefixes and templates at different levels:
    1. Global level: In the workload or deployment config
    2. Stack level: In the stack config
    3. Resource level: In the resource config (ssm.exports/ssm.imports)
    
    Example configurations:
    ```json
    {
        "ssm": {
            "prefix_template": "/{environment}/{resource_type}/{attribute}",
            "exports": {
                "vpc_id": "my-vpc-id"
            },
            "imports": {
                "security_group_id": "/my-app/security-group/id"
            }
        }
    }
    ```
    
    The template supports the following variables:
    - {deployment_name} - The name of the deployment
    - {environment} - The environment name
    - {workload_name} - The name of the workload
    - {resource_type} - The type of resource (e.g., vpc, security-group)
    - {resource_name} - The name of the resource
    - {attribute} - The attribute name
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the base configuration with a dictionary.
        
        Args:
            config: Dictionary containing configuration values
        """
        self.__config = config or {}
        
    @property
    def dictionary(self) -> Dict[str, Any]:
        """
        Get the raw configuration dictionary.
        
        Returns:
            The configuration dictionary
        """
        return self.__config
        
    @property
    def ssm(self) -> Dict[str, Any]:
        """
        Get the SSM configuration for this resource.
        
        Returns:
            Dictionary containing SSM configuration with imports/exports
        """
        return self.__config.get("ssm", {})
        
    @property
    def ssm_prefix_template(self) -> str:
        """
        Get the SSM parameter prefix template for this configuration.
        
        The template can include variables like {deployment_name}, {environment},
        {resource_type}, {resource_name}, and {attribute}.
        
        Returns:
            The SSM parameter prefix template string
        """
        return self.ssm.get("prefix_template", "/{deployment_name}/{resource_type}/{attribute}")
    
    @property
    def ssm_exports(self) -> Dict[str, str]:
        """
        Get the SSM parameter paths for values this resource exports.
        
        The SSM exports dictionary maps resource attributes to SSM parameter paths
        where this resource's values will be published.
        
        For example:
        {
            "vpc_id_path": "/my-app/vpc/id",
            "subnet_ids_path": "/my-app/vpc/subnet-ids"
        }
        
        Returns:
            Dictionary mapping attribute names to SSM parameter paths for export
        """
        return self.ssm.get("exports", {})
    
    @property
    def ssm_imports(self) -> Dict[str, str]:
        """
        Get the SSM parameter paths for values this resource imports/consumes.
        
        The SSM imports dictionary maps resource attributes to SSM parameter paths
        where this resource will look for values published by other stacks.
        
        For example:
        {
            "vpc_id_path": "/my-app/vpc/id",
            "user_pool_arn_path": "/my-app/cognito/user-pool-arn"
        }
        
        Returns:
            Dictionary mapping attribute names to SSM parameter paths for import
        """
        return self.ssm.get("imports", {})
        
            
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.
        
        Args:
            key: The configuration key
            default: Default value if key is not found
            
        Returns:
            The configuration value or default
        """
        return self.__config.get(key, default)
        
    def format_ssm_path(self, path: str, resource_type: str, resource_name: str, attribute: str, context: Dict[str, Any] = None) -> str:
        """
        Format an SSM parameter path using the template and provided values.
        
        Args:
            path: The raw path that might need formatting
            resource_type: The type of resource (e.g., 'vpc', 'security-group')
            resource_name: The name of the resource
            attribute: The attribute name (e.g., 'id', 'subnet-ids')
            context: Additional context variables for template formatting
            
        Returns:
            The formatted SSM parameter path
        """
        # If the path already starts with '/', assume it's already fully formatted
        if path and path.startswith('/'):
            return path
            
        # If no context is provided, create an empty dict
        context = context or {}
        
        # If the path doesn't contain any template variables, apply the template
        if path and '{' not in path:
            # This is just a simple attribute name, apply the template
            template = self.ssm_prefix_template
            
            # Add the required variables to the context
            format_context = {
                'resource_type': resource_type,
                'resource_name': resource_name,
                'attribute': path or attribute
            }
            
            # Add any additional context variables
            format_context.update(context)
            
            try:
                return template.format(**format_context)
            except KeyError as e:
                # If a required variable is missing, log a warning and return the original path
                import logging
                logging.warning(f"Missing template variable {e} for SSM path template: {template}")
                return path
        
        # If the path already contains template variables, just return it
        return path
    
    def get_export_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for exporting a specific attribute.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            resource_type: The type of resource (e.g., 'vpc', 'security-group')
            resource_name: The name of the resource
            context: Additional context variables for template formatting
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        path = self.ssm_exports.get(path_key)
        
        if path and resource_type:
            return self.format_ssm_path(path, resource_type, resource_name or key, key, context)
        
        return path
        
    def get_import_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for importing a specific attribute.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            resource_type: The type of resource (e.g., 'vpc', 'security-group')
            resource_name: The name of the resource
            context: Additional context variables for template formatting
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        path = self.ssm_imports.get(path_key)
        
        if path and resource_type:
            return self.format_ssm_path(path, resource_type, resource_name or key, key, context)
        
        return path
        
    def get_ssm_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for a specific attribute (checks both exports and imports).
        
        This is provided for backward compatibility.
        New code should use get_export_path or get_import_path instead.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            resource_type: The type of resource (e.g., 'vpc', 'security-group')
            resource_name: The name of the resource
            context: Additional context variables for template formatting
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        # Check exports first, then imports, then the legacy ssm_parameters
        path = self.ssm_exports.get(path_key) or self.ssm_imports.get(path_key) or self.__config.get("ssm_parameters", {}).get(path_key)
        
        if path and resource_type:
            return self.format_ssm_path(path, resource_type, resource_name or key, key, context)
        
        return path
