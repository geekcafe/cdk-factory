"""
Lambda@Edge Stack Pattern for CDK-Factory
Supports deploying Lambda functions for CloudFront edge locations.
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Optional, Dict
from pathlib import Path
import json
import tempfile
import shutil
import importlib.resources

import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.lambda_edge import LambdaEdgeConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="LambdaEdgeStack")


@register_stack("lambda_edge_library_module")
@register_stack("lambda_edge_stack")
class LambdaEdgeStack(IStack, StandardizedSsmMixin):
    """
    Reusable stack for Lambda@Edge functions.
    
    Lambda@Edge constraints:
    - Must be deployed in us-east-1
    - Requires versioned functions (not $LATEST)
    - Max timeout: 5s for origin-request, 30s for viewer-request
    - No environment variables in viewer-request/response (origin-request/response only)
    """

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.edge_config: Optional[LambdaEdgeConfig] = None
        self.stack_config: Optional[StackConfig] = None
        self.deployment: Optional[DeploymentConfig] = None
        self.workload: Optional[WorkloadConfig] = None
        self.function: Optional[_lambda.Function] = None
        self.function_version: Optional[_lambda.Version] = None
        # Cache for resolved environment variables to prevent duplicate construct creation
        self._resolved_env_cache: Optional[Dict[str, str]] = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Build the Lambda@Edge stack"""
        self._build(stack_config, deployment, workload)

    def _build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        """Internal build method for the Lambda@Edge stack"""
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload
        
        # Validate region (Lambda@Edge must be in us-east-1)
        if self.region != "us-east-1":
            logger.warning(
                f"Lambda@Edge must be deployed in us-east-1, but stack region is {self.region}. "
                "Make sure your deployment config specifies us-east-1."
            )
        
        # Load Lambda@Edge configuration
        self.edge_config = LambdaEdgeConfig(
            stack_config.dictionary.get("lambda_edge", {}),
            deployment
        )
        
        # Use the Lambda function name from config (supports template variables)
        # e.g., "{{WORKLOAD_NAME}}-{{ENVIRONMENT}}-ip-gate" becomes "tech-talk-dev-ip-gate"
        function_name = self.edge_config.name
        logger.info(f"Lambda function name: '{function_name}'")
        
        # Create Lambda function
        self._create_lambda_function(function_name)
        
        # Create version (required for Lambda@Edge)
        self._create_function_version(function_name)
        
        # Add outputs
        self._add_outputs(function_name)

    def _sanitize_construct_name(self, name: str) -> str:
        """
        Create a deterministic, valid CDK construct name from any string.
        Replaces non-alphanumeric characters with dashes and limits length.
        """
        # Replace non-alphanumeric characters with dashes
        sanitized = ''.join(c if c.isalnum() else '-' for c in name)
        # Remove consecutive dashes
        while '--' in sanitized:
            sanitized = sanitized.replace('--', '-')
        # Remove leading/trailing dashes
        sanitized = sanitized.strip('-')
        # Limit to 255 characters (CDK limit)
        return sanitized[:255]

    def _resolve_environment_variables(self) -> Dict[str, str]:
        """
        Resolve environment variables, including SSM parameter references.
        Supports {{ssm:parameter-path}} syntax for dynamic SSM lookups.
        Uses CDK tokens that resolve at deployment time, not synthesis time.
        Caches results to prevent duplicate construct creation.
        """
        # Return cached result if available
        if self._resolved_env_cache is not None:
            return self._resolved_env_cache
        
        resolved_env = {}
        
        for key, value in self.edge_config.environment.items():
            # Check if value is an SSM parameter reference
            if isinstance(value, str) and value.startswith("{{ssm:") and value.endswith("}}"):
                # Extract SSM parameter path
                ssm_param_path = value[6:-2]  # Remove {{ssm: and }}
                
                # Create deterministic construct name from parameter path
                construct_name = self._sanitize_construct_name(f"env-{key}-{ssm_param_path}")
                
                # Import SSM parameter - this creates a token that resolves at deployment time
                param = ssm.StringParameter.from_string_parameter_name(
                    self,
                    construct_name,
                    ssm_param_path
                )
                resolved_value = param.string_value
                logger.info(f"Resolved environment variable {key} from SSM {ssm_param_path} as {construct_name}")
                resolved_env[key] = resolved_value
            else:
                resolved_env[key] = value
        
        # Cache the result
        self._resolved_env_cache = resolved_env
        return resolved_env

    def _create_lambda_function(self, function_name: str) -> None:
        """Create the Lambda function"""
        
        # Resolve code path - support package references (e.g., "cdk_factory:lambdas/cloudfront/ip_gate")
        code_path_str = self.edge_config.code_path
        
        if ':' in code_path_str:
            # Package reference format: "package_name:path/within/package"
            package_name, package_path = code_path_str.split(':', 1)
            logger.info(f"Resolving package reference: {package_name}:{package_path}")
            
            try:
                # Get the package's installed location
                if hasattr(importlib.resources, 'files'):
                    # Python 3.9+
                    package_root = importlib.resources.files(package_name)
                    code_path = Path(str(package_root / package_path))
                else:
                    # Fallback for older Python
                    import pkg_resources
                    package_root = pkg_resources.resource_filename(package_name, '')
                    code_path = Path(package_root) / package_path
                
                logger.info(f"Resolved package path to: {code_path}")
            except Exception as e:
                raise FileNotFoundError(
                    f"Could not resolve package reference '{code_path_str}': {e}\n"
                    f"Make sure package '{package_name}' is installed."
                )
        else:
            # Regular file path
            code_path = Path(code_path_str)
            if not code_path.is_absolute():
                # Assume relative to the project root
                code_path = Path.cwd() / code_path
        
        if not code_path.exists():
            raise FileNotFoundError(
                f"Lambda code path does not exist: {code_path}\n"
                f"Current working directory: {Path.cwd()}"
            )
        
        logger.info(f"Loading Lambda code from: {code_path}")
        
        # Create isolated temp directory for this function instance
        # This prevents conflicts when multiple functions use the same handler code
        temp_code_dir = Path(tempfile.mkdtemp(prefix=f"{function_name.replace('/', '-')}-"))
        logger.info(f"Creating isolated code directory at: {temp_code_dir}")
        
        # Copy source code to temp directory
        shutil.copytree(code_path, temp_code_dir, dirs_exist_ok=True)
        logger.info(f"Copied code from {code_path} to {temp_code_dir}")
        
        # Create runtime configuration file for Lambda@Edge
        # Since Lambda@Edge doesn't support environment variables, we bundle a config file
        # Use the full function_name (e.g., "tech-talk-dev-ip-gate") not just the base name
        resolved_env = self._resolve_environment_variables()
        runtime_config = {
            'environment': self.deployment.environment,
            'function_name': function_name,
            'region': self.deployment.region,
            'environment_variables': resolved_env  # Add actual environment variables
        }
        
        runtime_config_path = temp_code_dir / 'runtime_config.json'
        logger.info(f"Creating runtime config at: {runtime_config_path}")
        
        with open(runtime_config_path, 'w') as f:
            json.dump(runtime_config, f, indent=2)
        
        logger.info(f"Runtime config: {runtime_config}")
        
        # Use the temp directory for the Lambda code asset
        code_path = temp_code_dir
        
        # Map runtime string to CDK Runtime
        runtime_map = {
            "python3.11": _lambda.Runtime.PYTHON_3_11,
            "python3.10": _lambda.Runtime.PYTHON_3_10,
            "python3.9": _lambda.Runtime.PYTHON_3_9,
            "python3.12": _lambda.Runtime.PYTHON_3_12,
            "nodejs18.x": _lambda.Runtime.NODEJS_18_X,
            "nodejs20.x": _lambda.Runtime.NODEJS_20_X,
        }
        
        runtime = runtime_map.get(
            self.edge_config.runtime,
            _lambda.Runtime.PYTHON_3_11
        )
        
        # Lambda@Edge does NOT support environment variables
        # Configuration must be handled via:
        # 1. Hardcoded in the function code
        # 2. Fetched from SSM Parameter Store at runtime
        # 3. Other configuration mechanisms
        
        # Log warning if environment variables are configured
        if self.edge_config.environment:
            logger.warning(
                f"Lambda@Edge function '{function_name}' has environment variables configured, "
                "but Lambda@Edge does not support environment variables. "
                "The function must fetch these values from SSM Parameter Store at runtime."
            )
            for key, value in self.edge_config.environment.items():
                logger.warning(f"  - {key}: {value}")
        
        # Create execution role with CloudWatch Logs and SSM permissions
        execution_role = iam.Role(
            self,
            f"{function_name}-Role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("edgelambda.amazonaws.com")
            ),
            description=f"Execution role for Lambda@Edge function {function_name}",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )
        
        # Add SSM read permissions if environment variables reference SSM parameters
        if self.edge_config.environment:
            execution_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath"
                    ],
                    resources=[
                        f"arn:aws:ssm:*:{cdk.Aws.ACCOUNT_ID}:parameter/*"
                    ]
                )
            )
        
        # Create the Lambda function WITHOUT environment variables
        self.function = _lambda.Function(
            self,
            function_name,
            function_name=function_name,
            runtime=runtime,
            handler=self.edge_config.handler,
            code=_lambda.Code.from_asset(str(code_path)),
            memory_size=self.edge_config.memory_size,
            timeout=cdk.Duration.seconds(self.edge_config.timeout),
            description=self.edge_config.description,
            role=execution_role,
            # Lambda@Edge does NOT support environment variables
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        
        # Add tags
        for key, value in self.edge_config.tags.items():
            cdk.Tags.of(self.function).add(key, value)

    def _create_function_version(self, function_name: str) -> None:
        """
        Create a version of the Lambda function.
        Lambda@Edge requires versioned functions (cannot use $LATEST).
        """
        self.function_version = self.function.current_version
        
        # Add description to version
        cfn_version = self.function_version.node.default_child
        if cfn_version:
            cfn_version.add_property_override(
                "Description",
                f"Version for Lambda@Edge deployment - {self.edge_config.description}"
            )

    def _add_outputs(self, function_name: str) -> None:
        """Add CloudFormation outputs and SSM exports"""
        
        
        
        # SSM Parameter Store exports (if configured)
        ssm_exports = self.edge_config.dictionary.get("ssm", {}).get("exports", {})
        if ssm_exports:
            export_values = {
                "function_name": self.function.function_name,
                "function_arn": self.function.function_arn,
                "function_version_arn": self.function_version.function_arn,
                "function_version": self.function_version.version,
            }
            
            # Export each value to SSM using the enhanced parameter mixin
            for key, param_path in ssm_exports.items():
                if key in export_values:
                    self.export_ssm_parameter(
                        self,
                        f"{key}-param",
                        export_values[key],
                        param_path,
                        description=f"{key} for Lambda@Edge function {function_name}"
                    )
        
        # Export environment variables as SSM parameters
        # Since Lambda@Edge doesn't support environment variables, we export them
        # to SSM so the Lambda function can fetch them at runtime
        if self.edge_config.environment:
            logger.info("Exporting Lambda@Edge environment variables as SSM parameters")
            env_ssm_exports = self.edge_config.dictionary.get("environment_ssm_exports", {})
            
            # If no explicit environment_ssm_exports, create default SSM paths
            if not env_ssm_exports:
                # Auto-generate SSM parameter names based on environment variable names
                for env_key in self.edge_config.environment.keys():
                    # Use snake_case version of the key for SSM path
                    ssm_key = env_key.lower().replace('_', '-')
                    env_ssm_exports[env_key] = f"/{self.deployment.environment}/{function_name}/{ssm_key}"
            
            # Resolve and export environment variables to SSM
            resolved_env = self._resolve_environment_variables()
            for env_key, ssm_path in env_ssm_exports.items():
                if env_key in resolved_env:
                    env_value = resolved_env[env_key]
                    
                    # Handle empty values - SSM doesn't allow empty strings
                    # Use sentinel value "NONE" to indicate explicitly unset
                    if not env_value or (isinstance(env_value, str) and env_value.strip() == ""):
                        env_value = "NONE"
                        logger.info(
                            f"Environment variable {env_key} is empty - setting SSM parameter to 'NONE'. "
                            f"Lambda function should treat 'NONE' as unset/disabled."
                        )
                    
                    self.export_ssm_parameter(
                        self,
                        f"env-{env_key}-param",
                        env_value,
                        ssm_path,
                        description=f"Configuration for Lambda@Edge: {env_key}"
                    )
