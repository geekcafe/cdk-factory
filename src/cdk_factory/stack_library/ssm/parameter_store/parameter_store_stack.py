"""
Parameter Store Stack Pattern for CDK-Factory
Creates one or more SSM parameters in Parameter Store with flexible configuration.

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Optional, Dict, Any, List
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_ssm as ssm
from aws_cdk import Tags
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.parameter_store import (
    ParameterStoreConfig,
    ParameterConfig,
)
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig


logger = Logger(service="ParameterStoreStack")


@register_stack("parameter_store_library_module")
@register_stack("parameter_store_stack")
class ParameterStoreStack(IStack, StandardizedSsmMixin):
    """
    General-purpose Parameter Store stack for managing SSM parameters.
    
    Features:
    - Create multiple SSM parameters from configuration
    - Support all parameter types (String, StringList, SecureString)
    - Optional prefix for parameter names
    - Stable construct IDs
    - Global and per-parameter tags
    - Template variable substitution
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.config: Optional[ParameterStoreConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.created_parameters: List[ssm.StringParameter] = []

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """
        Build the Parameter Store stack.
        
        Expected configuration structure:
        {
          "parameter_store": {
            "prefix": "/{environment}/{workload}",  # Optional
            "auto_format_names": true,              # Optional, default true
            "global_tags": {                        # Optional
              "ManagedBy": "CDK-Factory"
            },
            "parameters": [                         # Required
              {
                "name": "/path/to/param" or "param-name",
                "value": "parameter-value",
                "type": "String|StringList|SecureString",  # Optional, default String
                "description": "Parameter description",    # Optional
                "tier": "Standard|Advanced",               # Optional, default Standard
                "allowed_pattern": "regex",                # Optional
                "data_type": "text|aws:ec2:image",  # Optional
                "tags": {"Key": "Value"}                   # Optional
              }
            ]
          }
        }
        """
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        # Load configuration
        param_store_dict = stack_config.dictionary.get("parameter_store", {})
        if not param_store_dict:
            logger.warning("No parameter_store configuration found in stack config")
            return

        self.config = ParameterStoreConfig(param_store_dict)

        # Create parameters
        if not self.config.parameters:
            logger.warning("No parameters defined in parameter_store configuration")
            return

        logger.info(f"Creating {len(self.config.parameters)} SSM parameters")
        for idx, param_config in enumerate(self.config.parameters):
            self._create_parameter(param_config, idx)

        logger.info(
            f"Successfully created {len(self.created_parameters)} SSM parameters"
        )

    def _create_parameter(
        self, param_config: ParameterConfig, index: int
    ) -> ssm.StringParameter:
        """
        Create a single SSM parameter using modern CDK patterns.
        
        Note: CDK v2 and CloudFormation limitations:
        - String: Use StringParameter (L2 construct)
        - StringList: Use StringListParameter (L2 construct)
        - SecureString: Created as String (CloudFormation limitation - requires manual conversion)
        
        CloudFormation does NOT support creating SecureString parameters. They are created
        as regular String parameters and must be manually updated after deployment using:
          aws ssm put-parameter --name '<name>' --value '<value>' --type SecureString --overwrite
        
        Args:
            param_config: Parameter configuration
            index: Index of parameter in the list (for stable IDs)
        """
        # Format parameter name
        param_name = self._format_parameter_name(param_config.name)

        # Replace template variables in value
        param_value = self._substitute_variables(param_config.value)

        # Create stable construct ID
        # Use a sanitized version of the parameter name for the ID
        safe_name = param_config.name.replace("/", "-").replace("_", "-").strip("-")
        construct_id = self._stable_id(f"param-{index}-{safe_name}")

        # Create the parameter
        logger.info(f"Creating parameter: {param_name} (type: {param_config.type})")

        # Handle different parameter types using modern CDK patterns
        if param_config.type == "StringList":
            # StringList parameters use dedicated construct
            param = ssm.StringListParameter(
                self,
                construct_id,
                parameter_name=param_name,
                string_list_value=param_value.split(",") if param_value else [],
                description=param_config.description or f"Managed by CDK-Factory",
                tier=self._get_parameter_tier(param_config.tier),
            )
        elif param_config.type == "SecureString":
            # ERROR: CloudFormation does NOT support creating SecureString parameters!
            # AWS::SSM::Parameter only supports "String" and "StringList" types.
            # 
            # DO NOT use SecureString in your configuration. Instead:
            # 1. Use AWS Secrets Manager (recommended) - full CloudFormation support
            # 2. Pre-create SecureString parameters manually before deployment
            # 3. Reference them in your app using {{ssm-secure:path}}
            #
            # See: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-ssm-parameter.html
            
            error_msg = (
                f"❌ SecureString parameter '{param_name}' cannot be created via CloudFormation. "
                f"\n   CloudFormation does not support SecureString type. "
                f"\n   "
                f"\n   Recommended solutions:"
                f"\n   1. Use AWS Secrets Manager instead (supports CloudFormation)"
                f"\n   2. Pre-create this parameter manually:"
                f"\n      aws ssm put-parameter --name '{param_name}' --value 'SECRET' --type SecureString"
                f"\n   "
                f"\n   See documentation: SECRETS_MANAGEMENT.md"
            )
            logger.error(error_msg)
            raise ValueError(
                f"SecureString parameters are not supported in CloudFormation. "
                f"Use AWS Secrets Manager or pre-create manually. Parameter: {param_name}"
            )
        else:
            # String parameters (default) - use L2 construct
            # Build parameter creation kwargs
            param_kwargs = {
                "parameter_name": param_name,
                "string_value": param_value,
                "description": param_config.description or f"Managed by CDK-Factory",
                "tier": self._get_parameter_tier(param_config.tier),
            }
            
            # Add optional fields only if specified
            if param_config.allowed_pattern:
                param_kwargs["allowed_pattern"] = param_config.allowed_pattern
            
            if param_config.data_type:
                param_kwargs["data_type"] = self._get_parameter_data_type(param_config.data_type)
            
            param = ssm.StringParameter(
                self,
                construct_id,
                **param_kwargs
            )

        # Apply tags
        self._apply_tags(param, param_config)

        self.created_parameters.append(param)
        return param

    def _format_parameter_name(self, name: str) -> str:
        """
        Format parameter name with optional prefix.
        
        If auto_format_names is true and name doesn't start with '/',
        prepend the prefix. Otherwise use name as-is.
        """
        if not self.config.auto_format_names:
            return name

        # If name already starts with '/', use it as-is
        if name.startswith("/"):
            return name

        # Build prefix if not explicitly set
        prefix = self.config.prefix
        if not prefix:
            prefix = f"/{self.deployment.environment}/{self.deployment.workload_name}"

        # Ensure prefix starts with / and doesn't end with /
        if not prefix.startswith("/"):
            prefix = f"/{prefix}"
        prefix = prefix.rstrip("/")

        # Combine prefix and name
        return f"{prefix}/{name}"

    def _substitute_variables(self, value: str) -> str:
        """
        Substitute template variables in parameter value.
        
        Supports:
        - {{ENVIRONMENT}}
        - {{WORKLOAD_NAME}}
        - {{AWS_ACCOUNT}}
        - {{AWS_REGION}}
        """
        replacements = {
            "{{ENVIRONMENT}}": self.deployment.environment,
            "{{WORKLOAD_NAME}}": self.deployment.workload_name,
            "{{AWS_ACCOUNT}}": self.deployment.account,
            "{{AWS_REGION}}": self.deployment.region,
        }

        result = value
        for placeholder, replacement in replacements.items():
            result = result.replace(placeholder, replacement)

        return result

    def _get_parameter_tier(self, tier_str: str) -> ssm.ParameterTier:
        """
        Convert string parameter tier to CDK ParameterTier enum.
        """
        tier_map = {
            "Standard": ssm.ParameterTier.STANDARD,
            "Advanced": ssm.ParameterTier.ADVANCED,
            "Intelligent-Tiering": ssm.ParameterTier.INTELLIGENT_TIERING,
        }
        return tier_map.get(tier_str, ssm.ParameterTier.STANDARD)

    def _get_parameter_data_type(self, data_type_str: str) -> ssm.ParameterDataType:
        """
        Convert string parameter data type to CDK ParameterDataType enum.
        
        Supported values:
        - text: Standard text parameter (default)
        - aws:ec2:image: AMI ID parameter
        """
        data_type_map = {
            "text": ssm.ParameterDataType.TEXT,
            "aws:ec2:image": ssm.ParameterDataType.AWS_EC2_IMAGE,
        }
        return data_type_map.get(data_type_str, ssm.ParameterDataType.TEXT)

    def _apply_tags(self, param: ssm.StringParameter, param_config: ParameterConfig) -> None:
        """
        Apply global and parameter-specific tags.
        """
        # Apply global tags first
        for key, value in self.config.global_tags.items():
            Tags.of(param).add(key, value)

        # Apply parameter-specific tags (these override global tags)
        for key, value in param_config.tags.items():
            Tags.of(param).add(key, value)

        # Always add managed-by tag
        Tags.of(param).add("ManagedBy", "CDK-Factory")
        Tags.of(param).add("Environment", self.deployment.environment)
        Tags.of(param).add("Workload", self.deployment.workload_name)

    def _stable_id(self, base: str) -> str:
        """
        Return a deterministic construct ID independent of pipeline names.
        """
        return f"{self.deployment.workload_name}-{self.deployment.environment}-{base}"