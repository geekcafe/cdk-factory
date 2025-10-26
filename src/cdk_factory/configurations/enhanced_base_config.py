"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, Optional, List

from .base_config import BaseConfig
from .enhanced_ssm_config import EnhancedSsmConfig, SsmParameterDefinition


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
        
        # Initialize enhanced SSM config if SSM is configured
        if config.get("ssm"):
            self._enhanced_ssm = EnhancedSsmConfig(
                config=config,
                resource_type=resource_type or "unknown",
                resource_name=resource_name or "default"
            )
        else:
            self._enhanced_ssm = None

        if config.get("enhanced_ssm") is not None:
            raise ValueError("SSM parameter error: 'enhanced_ssm' is no longer supported, change to 'ssm' field name.")
        
    @property
    def ssm_enabled(self) -> bool:
        """Check if SSM parameter integration is enabled"""
        return self._enhanced_ssm.enabled if self._enhanced_ssm else False
    
    @property
    def ssm_workload(self) -> str:
        """Get the workload name for SSM parameter paths"""
        return self._enhanced_ssm.workload if self._enhanced_ssm else "cdk-factory"
    
    @property
    def ssm_organization(self) -> str:
        """Deprecated: Use ssm_workload instead. Kept for backward compatibility."""
        return self.ssm_workload
    
    @property
    def ssm_environment(self) -> str | None:
        """Get the environment name for SSM parameter paths"""
        return self._enhanced_ssm.environment if self._enhanced_ssm else None
    
    @property
    def ssm_pattern(self) -> str:
        """Get the SSM parameter path pattern"""
        return self._enhanced_ssm.pattern if self._enhanced_ssm else "/{workload}/{environment}/{stack_type}/{resource_name}/{attribute}"
    
    @property
    def ssm_auto_export(self) -> bool:
        """Check if auto-export is enabled"""
        return self._enhanced_ssm.auto_export if self._enhanced_ssm else True
    
    @property
    def ssm_auto_import(self) -> bool:
        """Check if auto-import is enabled"""
        return self._enhanced_ssm.auto_import if self._enhanced_ssm else True
    
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
        if self._enhanced_ssm:
            return self._enhanced_ssm.get_parameter_path(attribute, custom_path)
        
        # Fallback to simple path generation
        if custom_path and custom_path.startswith("/"):
            return custom_path
        return f"/{self.ssm_workload}/{self.ssm_environment}/{attribute}"
    
    def get_export_definitions(self, context: Dict[str, Any] = None) -> List[SsmParameterDefinition]:
        """
        Get list of parameters to export with auto-discovery support.
        
        Args:
            context: Additional context variables for template formatting
            
        Returns:
            List of SSM parameter definitions for export
        """
        if self._enhanced_ssm:
            return self._enhanced_ssm.get_export_definitions()
        return []
    
    def get_import_definitions(self, context: Dict[str, Any] = None) -> List[SsmParameterDefinition]:
        """
        Get list of parameters to import with auto-discovery support.
        
        Args:
            context: Additional context variables for template formatting
            
        Returns:
            List of SSM parameter definitions for import
        """
        if self._enhanced_ssm:
            return self._enhanced_ssm.get_import_definitions()
        return []
    
    # Override parent methods to use enhanced functionality
    def get_export_path(self, key: str, resource_type: str = None, resource_name: str = None, context: Dict[str, Any] = None) -> Optional[str]:
        """
        Get an SSM parameter path for exporting a specific attribute with enhanced auto-discovery.
        """
        # First check if we have enhanced SSM config
        if self._enhanced_ssm:
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
        if self._enhanced_ssm:
            import_defs = self.get_import_definitions(context)
            for definition in import_defs:
                if definition.attribute == key:
                    return definition.path
        
        # Fall back to parent implementation
        return super().get_import_path(key, resource_type or self.resource_type, resource_name or self.resource_name, context)
