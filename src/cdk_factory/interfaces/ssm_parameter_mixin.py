"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Dict, Any, Optional, Union, List
from aws_cdk import aws_ssm as ssm
from constructs import Construct
from aws_lambda_powertools import Logger

logger = Logger(__name__)


class SsmParameterMixin:
    """
    A mixin class that provides SSM parameter export and import functionality
    for CDK stacks.

    This mixin should be used by stack classes to standardize how SSM parameters
    are exported and imported across the project.
    
    Enhanced to support:
    - List parameter imports (for security groups, etc.)
    - Cached imported values for easy access
    - Backward compatibility with existing interfaces
    """

    def __init__(self, *args, **kwargs):
        """Initialize the mixin with cached storage for imported values."""
        # Don't call super() to avoid MRO issues in multiple inheritance
        # Initialize cached storage for imported values
        self._ssm_imported_values: Dict[str, Union[str, List[str]]] = {}

    def initialize_ssm_imports(self) -> None:
        """
        Initialize SSM imports storage.
        Call this in your stack's __init__ method if not using __init__ above.
        """
        if not hasattr(self, '_ssm_imported_values'):
            self._ssm_imported_values: Dict[str, Union[str, List[str]]] = {}

    def get_ssm_imported_value(self, key: str, default: Any = None) -> Any:
        """
        Get a cached SSM imported value by key.
        
        Args:
            key: The SSM import key
            default: Default value if key not found
            
        Returns:
            The imported value or default
        """
        return self._ssm_imported_values.get(key, default)

    def has_ssm_import(self, key: str) -> bool:
        """
        Check if an SSM import key exists in cached values.
        
        Args:
            key: The SSM import key to check
            
        Returns:
            True if key exists, False otherwise
        """
        return key in self._ssm_imported_values

    def process_ssm_imports(
        self, 
        config: Any, 
        deployment: Any,
        resource_type: str = "resource"
    ) -> None:
        """
        Process SSM imports from configuration and cache them for later use.
        
        This method handles list imports (like security_group_ids) and caches
        the results for easy access via get_ssm_imported_value().
        
        Args:
            config: The configuration object with ssm.imports property
            deployment: The deployment configuration for path resolution
            resource_type: Type of resource for logging purposes
        """
        # Get SSM configuration from new pattern
        ssm_config = getattr(config, 'ssm', {})
        ssm_imports = ssm_config.get('imports', {})
        
        if not ssm_imports:
            logger.debug(f"No SSM imports configured for {resource_type}")
            return
        
        logger.info(f"Processing {len(ssm_imports)} SSM imports for {resource_type}")
        
        for param_key, param_value in ssm_imports.items():
            try:
                if isinstance(param_value, list):
                    # Handle list imports (like security_group_ids)
                    imported_list = []
                    for item in param_value:
                        param_path = self._resolve_ssm_path(item, deployment)
                        
                        construct_id = f"ssm-import-{param_key}-{hash(param_path) % 10000}"
                        param = ssm.StringParameter.from_string_parameter_name(
                            self, construct_id, param_path
                        )
                        imported_list.append(param.string_value)
                    
                    self._ssm_imported_values[param_key] = imported_list
                    logger.info(f"Imported SSM parameter list: {param_key} with {len(imported_list)} items")
                else:
                    # Handle string values
                    param_path = self._resolve_ssm_path(param_value, deployment)
                    
                    construct_id = f"ssm-import-{param_key}-{hash(param_path) % 10000}"
                    param = ssm.StringParameter.from_string_parameter_name(
                        self, construct_id, param_path
                    )
                    
                    self._ssm_imported_values[param_key] = param.string_value
                    logger.info(f"Imported SSM parameter: {param_key} from {param_path}")
                    
            except Exception as e:
                logger.error(f"Failed to import SSM parameter {param_key}: {e}")
                raise

    def _resolve_ssm_path(self, path: str, deployment: Any) -> str:
        """
        Resolve SSM parameter path (handle relative vs absolute paths).
        
        Args:
            path: The parameter path from configuration
            deployment: The deployment configuration for context
            
        Returns:
            Fully resolved SSM parameter path
        """
        if not path.startswith('/'):
            # Convert relative path to absolute path
            return f"/{deployment.environment}/{deployment.workload_name}/{path}"
        return path

    @staticmethod
    def normalize_resource_name(name: str, for_export: bool = False) -> str:
        """
        Normalize resource names for consistent naming across CDK stacks.

        Args:
            name: The resource name to normalize
            for_export: If True, keeps hyphens for CloudFormation export compatibility

        Returns:
            Normalized name with consistent convention

        Examples:
            "web-servers" -> "web_servers" (for SSM parameters)
            "web-servers" -> "web-servers" (for CloudFormation exports, for_export=True)
            "API-Gateway" -> "api_gateway" or "api-gateway"
        """
        if for_export:
            # CloudFormation exports only allow alphanumeric, colons, hyphens
            return name.lower()
        else:
            # SSM parameters use underscores for consistency
            return name.replace("-", "_").lower()

    def export_ssm_parameter(
        self,
        scope: Construct,
        id: str,
        value: str,
        parameter_name: str,
        description: str = None,
        string_list_value: bool = False,
    ) -> ssm.StringParameter:
        """
        Export a value to SSM Parameter Store.

        Args:
            scope: The CDK construct scope
            id: The construct ID for the SSM parameter
            value: The value to store in the parameter
            parameter_name: The name of the parameter in SSM
            description: Optional description for the parameter
            string_list_value: Whether the parameter is a comma-delimited list

        Returns:
            The created SSM parameter
        """
        if not parameter_name:
            logger.warning(f"No SSM parameter name provided for {id}, skipping export")
            return None

        # Ensure parameter name starts with a slash
        if not parameter_name.startswith("/"):
            parameter_name = f"/{parameter_name}"

        logger.info(f"Exporting SSM parameter: {parameter_name}")

        return ssm.StringParameter(
            scope=scope,
            id=id,
            string_value=value,
            parameter_name=parameter_name,
            description=description,
        )

    def import_ssm_parameter(
        self,
        scope: Construct,
        id: str,
        parameter_name: str,
        version: Optional[int] = None,
    ) -> str:
        """
        Import a value from SSM Parameter Store.

        Args:
            scope: The CDK construct scope
            id: The construct ID for the SSM parameter reference
            parameter_name: The name of the parameter in SSM
            version: Optional specific version to retrieve

        Returns:
            The parameter value as a string
        """
        if not parameter_name:
            logger.warning(f"No SSM parameter name provided for {id}, cannot import")
            return None

        # Ensure parameter name starts with a slash
        if not parameter_name.startswith("/"):
            parameter_name = f"/{parameter_name}"

        logger.info(f"Importing SSM parameter: {parameter_name}")

        if version:
            return ssm.StringParameter.from_string_parameter_attributes(
                scope,
                id,
                parameter_name=parameter_name,
                version=version,
            ).string_value
        else:
            return ssm.StringParameter.from_string_parameter_name(
                scope,
                id,
                parameter_name,
            ).string_value

    def export_ssm_parameters_from_config(
        self,
        scope: Construct,
        config_dict: Dict[str, Any],
        ssm_config: Dict[str, str],
        resource: str = "",
    ) -> Dict[str, ssm.StringParameter]:
        """
        Export multiple SSM parameters based on a configuration dictionary and SSM path mapping.

        Args:
            scope: The CDK construct scope
            config_dict: Dictionary containing values to export
            ssm_config: Dictionary mapping keys to SSM parameter paths
            resource: Optional resource name for the parameter IDs

        Returns:
            Dictionary of created SSM parameters
        """
        parameters = {}
        missing_keys = []
        for key, path in ssm_config.items():
            if key not in config_dict:
                # missing or misspelled key
                missing_keys.append(key)
                continue

            if not path:
                # nothing configured for this key which is acceptable
                continue

            value = str(config_dict[key])
            id_name = f"{resource}{key.replace('_', '-')}-param"

            param = self.export_ssm_parameter(
                scope=scope,
                id=id_name,
                value=value,
                parameter_name=path,
                description=f"Exported {key} from {resource}",
            )

            if param:
                parameters[key] = param

        if missing_keys:
            logger.warning(f"Missing keys: {missing_keys}")
            # TODO : throw an exception here?
            message = (
                "🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨"
                f"\nThe following keys are missing from the config dictionary: {missing_keys}."
                f"\nThe accepted keys are: {list(config_dict.keys())}."
                "\nPlease check your configuration.  Some keys may be misspelled."
                "\n🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨🚨"
            )
            print(message)
            logger.error(message.replace("\n", ""))
            exit(1)

        return parameters

    def export_resource_to_ssm(
        self,
        scope: Construct,
        resource_values: Dict[str, Any],
        config: Any,  # Should be a BaseConfig subclass
        resource_name: str,
        resource_type: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, ssm.StringParameter]:
        """
        Export resource attributes to SSM Parameter Store based on configuration.

        This is a higher-level method that makes it clear we're exporting values.
        It first tries to use the ssm_exports property, then falls back to ssm_parameters.

        Args:
            scope: The CDK construct scope
            resource_values: Dictionary of resource values to export
            config: Configuration object with ssm_exports or ssm_parameters
            resource_name: Name of the resource (used as prefix for parameter IDs)
            resource_type: Type of the resource (e.g., 'vpc', 'security-group')
            context: Additional context variables for template formatting

        Returns:
            Dictionary of created SSM parameters
        """
        # First try the new ssm_exports property
        ssm_config = getattr(config, "ssm_exports", {})

        # If empty, fall back to the legacy ssm_parameters for backward compatibility
        if not ssm_config:
            ssm_config = getattr(config, "ssm_parameters", {})

        # Export all resources to SSM if paths are configured
        if ssm_config:
            logger.info(f"Exporting resources to SSM: {list(ssm_config.keys())}")

            # Format the SSM paths using the template if available
            formatted_ssm_config = {}
            for key, path in ssm_config.items():
                # Extract the attribute name from the key (remove _path suffix)
                attr_name = key[:-5] if key.endswith("_path") else key

                # If config has format_ssm_path method, use it to format the path
                if hasattr(config, "format_ssm_path") and resource_type:
                    formatted_path = config.format_ssm_path(
                        path=path,
                        resource_type=resource_type,
                        resource_name=resource_name,
                        attribute=attr_name,
                        context=context,
                    )
                    formatted_ssm_config[key] = formatted_path
                else:
                    formatted_ssm_config[key] = path

            return self.export_ssm_parameters_from_config(
                scope=scope,
                config_dict=resource_values,
                ssm_config=formatted_ssm_config,
                resource=f"{resource_name}-",
            )
        else:
            logger.info(f"No SSM export paths configured for {resource_name} resources")
            logger.info("The following SSM exports are available for this resource: ")
            for key, item in resource_values.items():
                logger.info(f"{key}: {item}")
            return {}

    def import_resources_from_ssm(
        self,
        scope: Construct,
        config: Any,  # Should be a BaseConfig subclass
        resource_name: str,
        resource_type: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, str]:
        """
        Import resource attributes from SSM Parameter Store based on configuration.

        This is a higher-level method that makes it clear we're importing values.
        Uses the new ssm.imports pattern.
        
        Enhanced to also cache results for easy access via get_ssm_imported_value().

        Args:
            scope: The CDK construct scope
            config: Configuration object with ssm.imports
            resource_name: Name of the resource (used as prefix for parameter IDs)
            resource_type: Type of the resource (e.g., 'vpc', 'security-group')
            context: Additional context variables for template formatting

        Returns:
            Dictionary of imported SSM parameter values
        """
        # Get SSM configuration from new pattern
        ssm_config = getattr(config, "ssm", {})
        ssm_imports = ssm_config.get("imports", {})

        imported_values = {}

        if ssm_imports:
            logger.info(f"Importing resources from SSM: {list(ssm_imports.keys())}")
            for key, path in ssm_imports.items():
                if not path:
                    continue

                # Extract the attribute name from the key (remove _path suffix)
                attr_name = key[:-5] if key.endswith("_path") else key

                # Format the SSM path using the template if available
                if hasattr(config, "format_ssm_path") and resource_type:
                    formatted_path = config.format_ssm_path(
                        path=path,
                        resource_type=resource_type,
                        resource_name=resource_name,
                        attribute=attr_name,
                        context=context,
                    )
                else:
                    formatted_path = path

                id_name = f"{resource_name}-{key.replace('_', '')}-Import"
                value = self.import_ssm_parameter(
                    scope=scope, id=id_name, parameter_name=formatted_path
                )

                if value:
                    # Remove _path suffix if present
                    final_key = key[:-5] if key.endswith("_path") else key
                    imported_values[final_key] = value
                    
                    # Also cache for easy access via get_ssm_imported_value()
                    self._ssm_imported_values[final_key] = value
        else:
            logger.info(f"No SSM import paths configured for {resource_name} resources")

        return imported_values
