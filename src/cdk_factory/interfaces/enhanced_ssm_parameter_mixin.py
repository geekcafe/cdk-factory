"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

"""
Enhanced SSM Parameter Mixin for CDK Factory
"""

import os
from typing import Dict, Any, Optional, List
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from aws_lambda_powertools import Logger
from cdk_factory.configurations.enhanced_ssm_config import EnhancedSsmConfig, SsmParameterDefinition
from cdk_factory.configurations.enhanced_base_config import EnhancedBaseConfig
from cdk_factory.interfaces.live_ssm_resolver import LiveSsmResolver

logger = Logger(service="EnhancedSsmParameterMixin")


class EnhancedSsmParameterMixin:
    """
    Enhanced SSM parameter mixin with auto-discovery and flexible patterns.
    
    This mixin extends the original SsmParameterMixin to support:
    - Auto-discovery of parameters based on resource types
    - Flexible pattern templates with environment variable support
    - Backward compatibility with existing configurations
    - Enhanced error handling and logging
    """
    
    def setup_enhanced_ssm_integration(self, scope: Construct, config, resource_type: str = None, resource_name: str = None):
        """
        Setup enhanced SSM integration for a resource.
        
        Args:
            scope: The CDK construct scope
            config: Configuration object with SSM settings
            resource_type: Type of resource (e.g., 'api_gateway', 'cognito', 'dynamodb')
            resource_name: Name of the resource instance
        """
        config_dict = config if isinstance(config, dict) else config.dictionary
        self.enhanced_ssm_config = EnhancedSsmConfig(
            config=config_dict,
            resource_type=resource_type or "unknown",
            resource_name=resource_name or "default"
        )
        self.scope = scope
        
        # Initialize live SSM resolver if configured
        self.live_resolver = LiveSsmResolver(config_dict)
        if self.live_resolver.enabled:
            logger.info(f"Live SSM resolution enabled for {resource_type}/{resource_name}")
        
    def auto_export_resources(self, resource_values: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, str]:
        """
        Automatically export resources based on enhanced configuration.
        
        Args:
            resource_values: Dictionary of resource values to export
            context: Additional context variables for template formatting
            
        Returns:
            Dictionary mapping attribute names to SSM parameter paths
        """
        if not hasattr(self, 'enhanced_ssm_config') or not self.enhanced_ssm_config.enabled:
            return {}
            
        exported_params = {}
        export_definitions = self.enhanced_ssm_config.get_export_definitions()
        
        logger.info(f"Auto-exporting {len(export_definitions)} parameters for {self.enhanced_ssm_config.resource_type}")
        
        for definition in export_definitions:
            attr = definition.attribute
            ssm_path = definition.path
            
            if attr in resource_values:
                value = resource_values[attr]
                if value is not None:
                    try:
                        param = self._create_enhanced_ssm_parameter(
                            ssm_path, 
                            value, 
                            definition.description or f"{attr} for {self.enhanced_ssm_config.resource_name}",
                            definition.parameter_type
                        )
                        exported_params[attr] = ssm_path
                        logger.info(f"Exported {attr} -> {ssm_path}")
                    except Exception as e:
                        logger.error(f"Failed to export {attr} to {ssm_path}: {e}")
            else:
                logger.warning(f"Attribute {attr} not found in resource values")
                
        return exported_params
    
    def auto_import_resources(self, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Automatically import resources based on enhanced configuration.
        
        Args:
            context: Additional context variables for template formatting
            
        Returns:
            Dictionary of imported resource values
        """
        if not hasattr(self, 'enhanced_ssm_config') or not self.enhanced_ssm_config.enabled:
            logger.info("Enhanced SSM integration not enabled or configured")
            return {}
            
        imported_values = {}
        import_definitions = self.enhanced_ssm_config.get_import_definitions()
        
        logger.info(f"Auto-importing {len(import_definitions)} parameters for {self.enhanced_ssm_config.resource_type}")
        
        for definition in import_definitions:
            try:
                value = self._import_enhanced_ssm_parameter(definition.path, definition.attribute)
                if value:
                    imported_values[definition.attribute] = value
                    logger.info(f"Imported {definition.attribute} <- {definition.path}")
                else:
                    logger.warning(f"No value found for {definition.attribute} at {definition.path}")
            except Exception as e:
                # Log warning but continue - allows for optional imports
                logger.warning(f"Could not import {definition.attribute} from {definition.path}: {e}")
                
        return imported_values
    
    def _create_enhanced_ssm_parameter(self, path: str, value: Any, description: str, param_type: str = "String") -> ssm.StringParameter:
        """
        Create an SSM parameter with enhanced handling.
        
        Args:
            path: SSM parameter path
            value: Value to store
            description: Parameter description
            param_type: Parameter type (String, StringList, SecureString)
            
        Returns:
            Created SSM parameter
        """
        # Handle different value types
        if isinstance(value, list):
            string_value = ",".join(str(v) for v in value)
            cdk_param_type = ssm.ParameterType.STRING_LIST
        elif param_type == "SecureString":
            string_value = str(value)
            cdk_param_type = ssm.ParameterType.SECURE_STRING
        else:
            string_value = str(value)
            cdk_param_type = ssm.ParameterType.STRING
            
        # Generate a unique construct ID from the path
        construct_id = f"ssm-param-{path.replace('/', '-').replace('_', '-')}"
        
        return ssm.StringParameter(
            self.scope,
            construct_id,
            parameter_name=path,
            string_value=string_value,
            description=description,
            type=cdk_param_type
        )
    
    def _import_enhanced_ssm_parameter(self, path: str, attribute: str) -> Optional[str]:
        """
        Import an SSM parameter value with enhanced error handling and live resolution fallback.
        
        Args:
            path: SSM parameter path
            attribute: Attribute name for logging
            
        Returns:
            Parameter value or None if not found
        """
        try:
            # Generate a unique construct ID from the path
            construct_id = f"imported-param-{path.replace('/', '-').replace('_', '-')}"
            
            param = ssm.StringParameter.from_string_parameter_name(
                self.scope,
                construct_id,
                path
            )
            cdk_token_value = param.string_value
            
            # Check if we should use live resolution for this token
            if hasattr(self, 'live_resolver') and self.live_resolver.should_use_live_resolution(cdk_token_value):
                live_value = self.live_resolver.resolve_parameter(path, fallback_value=None)
                if live_value:
                    logger.info(f"Live resolved {attribute} from {path}: {live_value[:20]}...")
                    return live_value
                else:
                    logger.warning(f"Live resolution failed for {attribute} at {path}, using CDK token")
            
            return cdk_token_value
            
        except Exception as e:
            # Try live resolution as fallback if CDK parameter import fails
            if hasattr(self, 'live_resolver') and self.live_resolver.enabled:
                logger.info(f"CDK parameter import failed for {path}, attempting live resolution")
                live_value = self.live_resolver.resolve_parameter(path, fallback_value=None)
                if live_value:
                    logger.info(f"Live resolved {attribute} from {path} after CDK failure")
                    return live_value
            
            logger.debug(f"Failed to import SSM parameter {path} for {attribute}: {e}")
            return None
    
    # Backward compatibility methods that delegate to enhanced versions
    def export_resource_to_ssm(
        self,
        scope: Construct,
        resource_values: Dict[str, Any],
        config: Any,
        resource_name: str,
        resource_type: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, ssm.StringParameter]:
        """
        Export resource attributes to SSM Parameter Store (backward compatibility).
        
        This method provides backward compatibility while leveraging enhanced functionality
        when an EnhancedBaseConfig is provided.
        """
        # If we have an enhanced config, use the new auto-export functionality
        if isinstance(config, EnhancedBaseConfig):
            if not hasattr(self, 'enhanced_ssm_config'):
                self.setup_enhanced_ssm_integration(scope, config)
            
            exported_paths = self.auto_export_resources(resource_values, context)
            
            # Convert paths back to parameter objects for backward compatibility
            parameters = {}
            for attr, path in exported_paths.items():
                # Create a mock parameter object with the path
                parameters[f"{attr}_path"] = type('MockParam', (), {'parameter_name': path})()
            
            return parameters
        
        # Fall back to original implementation for non-enhanced configs
        from .ssm_parameter_mixin import SsmParameterMixin
        mixin = SsmParameterMixin()
        return mixin.export_resource_to_ssm(scope, resource_values, config, resource_name, resource_type, context)
    
    def import_resources_from_ssm(
        self,
        scope: Construct,
        config: Any,
        resource_name: str,
        resource_type: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, str]:
        """
        Import resource attributes from SSM Parameter Store (backward compatibility).
        
        This method provides backward compatibility while leveraging enhanced functionality
        when an EnhancedBaseConfig is provided.
        """
        # If we have an enhanced config, use the new auto-import functionality
        if isinstance(config, EnhancedBaseConfig):
            if not hasattr(self, 'enhanced_ssm_config'):
                self.setup_enhanced_ssm_integration(scope, config)
            
            return self.auto_import_resources(context)
        
        # Fall back to original implementation for non-enhanced configs
        from .ssm_parameter_mixin import SsmParameterMixin
        mixin = SsmParameterMixin()
        return mixin.import_resources_from_ssm(scope, config, resource_name, resource_type, context)
    
    # Legacy method delegation for full backward compatibility
    def export_ssm_parameter(self, scope: Construct, id: str, value: str, parameter_name: str, description: str = None, string_list_value: bool = False) -> ssm.StringParameter:
        """Export a value to SSM Parameter Store (legacy compatibility)."""
        from .ssm_parameter_mixin import SsmParameterMixin
        mixin = SsmParameterMixin()
        return mixin.export_ssm_parameter(scope, id, value, parameter_name, description, string_list_value)
    
    def import_ssm_parameter(self, scope: Construct, id: str, parameter_name: str, version: Optional[int] = None) -> str:
        """Import a value from SSM Parameter Store (legacy compatibility)."""
        from .ssm_parameter_mixin import SsmParameterMixin
        mixin = SsmParameterMixin()
        return mixin.import_ssm_parameter(scope, id, parameter_name, version)
    
    def export_ssm_parameters_from_config(self, scope: Construct, config_dict: Dict[str, Any], ssm_config: Dict[str, str], resource: str = "") -> Dict[str, ssm.StringParameter]:
        """Export multiple SSM parameters based on configuration (legacy compatibility)."""
        from .ssm_parameter_mixin import SsmParameterMixin
        mixin = SsmParameterMixin()
        return mixin.export_ssm_parameters_from_config(scope, config_dict, ssm_config, resource)
