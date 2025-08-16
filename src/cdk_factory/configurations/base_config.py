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
        return self.__config.get("ssm_exports", {})
    
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
        return self.__config.get("ssm_imports", {})
        
    @property
    def ssm_parameters(self) -> Dict[str, str]:
        """
        Get all SSM parameter path mappings (both exports and imports).
        
        This is provided for backward compatibility.
        New code should use ssm_exports and ssm_imports instead.
        
        Returns:
            Dictionary mapping attribute names to SSM parameter paths
        """
        # Merge exports and imports, with exports taking precedence
        combined = {**self.ssm_imports, **self.ssm_exports}
        # Also include any parameters directly under ssm_parameters for backward compatibility
        combined.update(self.__config.get("ssm_parameters", {}))
        return combined
        
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
        
    def get_export_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for exporting a specific attribute.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        return self.ssm_exports.get(path_key)
        
    def get_import_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for importing a specific attribute.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        return self.ssm_imports.get(path_key)
        
    def get_ssm_path(self, key: str) -> Optional[str]:
        """
        Get an SSM parameter path for a specific attribute (checks both exports and imports).
        
        This is provided for backward compatibility.
        New code should use get_export_path or get_import_path instead.
        
        Args:
            key: The attribute name (e.g., "vpc_id", "subnet_ids")
            
        Returns:
            The SSM parameter path or None if not defined
        """
        path_key = f"{key}_path"
        # Check exports first, then imports, then the legacy ssm_parameters
        return self.ssm_exports.get(path_key) or self.ssm_imports.get(path_key) or self.__config.get("ssm_parameters", {}).get(path_key)
