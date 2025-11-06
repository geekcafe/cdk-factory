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
        
        # Configure edge log retention for regional logs
        self._configure_edge_log_retention(function_name)
        
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

        # Log warning if environment variables are configured
        if self.edge_config.environment:
            logger.warning(
                f"Lambda@Edge function '{function_name}' has environment variables configured, "
                "but Lambda@Edge does not support environment variables. The function must fetch these values from SSM Parameter Store at runtime."
            )
            for key, value in self.edge_config.environment.items():
                logger.warning(f"  - {key}: {value}")
        
        # Create execution role with CloudWatch Logs and SSM permissions
        execution_role = iam.Role(
            self,
            f"{function_name}-Role",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("edgelambda.amazonaws.com"),
                iam.ServicePrincipal("cloudfront.amazonaws.com")  # Add CloudFront service principal
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
            # Configuration must be fetched from SSM at runtime
            log_retention=logs.RetentionDays.ONE_WEEK,
        )
        
        # Add tags
        for key, value in self.edge_config.tags.items():
            cdk.Tags.of(self.function).add(key, value)

        # Add resource-based policy allowing CloudFront to invoke the Lambda function
        # This is REQUIRED for Lambda@Edge to work properly
        permission_kwargs = {
            "principal": iam.ServicePrincipal("cloudfront.amazonaws.com"),
            "action": "lambda:InvokeFunction",
        }
        
        # Optional: Add source ARN restriction if CloudFront distribution ARN is available
        # This provides more secure permission scoping
        distribution_arn_path = f"/{self.deployment.environment}/{self.workload.name}/cloudfront/arn"
        try:
            distribution_arn = ssm.StringParameter.from_string_parameter_name(
                self,
                "cloudfront-distribution-arn",
                distribution_arn_path
            ).string_value
            
            # Add source ARN condition for more secure permission scoping
            permission_kwargs["source_arn"] = distribution_arn
            logger.info(f"Adding CloudFront permission with source ARN restriction: {distribution_arn}")
        except Exception:
            # Distribution ARN not available (common during initial deployment)
            # CloudFront will scope the permission appropriately when it associates the Lambda
            logger.warning(f"CloudFront distribution ARN not found at {distribution_arn_path}, using open permission")
        
        self.function.add_permission(
            "CloudFrontInvokePermission",
            **permission_kwargs
        )

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

    def _configure_edge_log_retention(self, function_name: str) -> None:
        """
        Configure log retention for Lambda@Edge regional logs.
        
        Lambda@Edge creates log groups in multiple regions that need
        separate retention configuration from the primary log group.
        """
        from aws_cdk import custom_resources as cr
        
        # Get edge log retention from config (default to same as primary logs)
        edge_retention_days = self.edge_config.dictionary.get("edge_log_retention_days", 7)
        
        # List of common Lambda@Edge regions
        edge_regions = [
            'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
            'eu-west-1', 'eu-west-2', 'eu-central-1',
            'ap-southeast-1', 'ap-southeast-2', 'ap-northeast-1',
            'ca-central-1', 'sa-east-1'
        ]
        
        # Create custom resource to set log retention for each region
        for region in edge_regions:
            log_group_name = f"/aws/lambda/{region}.{function_name}"
            
            # Use AwsCustomResource to set log retention
            cr.AwsCustomResource(
                self, f"EdgeLogRetention-{region}",
                on_update={
                    "service": "Logs",
                    "action": "putRetentionPolicy",
                    "parameters": {
                        "logGroupName": log_group_name,
                        "retentionInDays": edge_retention_days
                    },
                    "physical_resource_id": cr.PhysicalResourceId.from_response("logGroupName")
                },
                on_delete={
                    "service": "Logs", 
                    "action": "deleteRetentionPolicy",
                    "parameters": {
                        "logGroupName": log_group_name
                    },
                    "physical_resource_id": cr.PhysicalResourceId.from_response("logGroupName")
                },
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=[f"arn:aws:logs:{region}:*:log-group:{log_group_name}*"]
                )
            )
        
        logger.info(f"Configured edge log retention to {edge_retention_days} days for {len(edge_regions)} regions")

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
                env_ssm_exports = {
                    key: f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/{key.lower()}"
                    for key in self.edge_config.environment.keys()
                }
            
            # Export each environment variable to SSM
            for var_name, var_value in self.edge_config.environment.items():
                ssm_path = env_ssm_exports.get(var_name, f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/{var_name.lower()}")
                self.export_ssm_parameter(
                    self,
                    f"{var_name}-env-param",
                    var_value,
                    ssm_path,
                    description=f"Lambda@Edge environment variable: {var_name} for {function_name}"
                )
        
        # Export the complete configuration as a single SSM parameter for dynamic updates
        config_ssm_path = f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/config"
        full_config = {
            "environment_variables": self.edge_config.environment or {}
        }
        
        self.export_ssm_parameter(
            self,
            "full-config-param",
            json.dumps(full_config),
            config_ssm_path,
            description=f"Complete Lambda@Edge configuration for {function_name} - update this for dynamic changes"
        )
        
        # Export cache TTL parameter for dynamic cache control
        cache_ttl_ssm_path = f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/cache-ttl"
        default_cache_ttl = self.edge_config.dictionary.get("cache_ttl_seconds", 300)  # Default 5 minutes
        
        self.export_ssm_parameter(
            self,
            "cache-ttl-param",
            str(default_cache_ttl),
            cache_ttl_ssm_path,
            description=f"Lambda@Edge configuration cache TTL in seconds for {function_name} - adjust for maintenance windows (30-3600)"
        )
        
        # Create additional default parameters if configured
        default_params = self.edge_config.dictionary.get("default_parameters", {})
        if default_params:
            logger.info(f"Creating {len(default_params)} default SSM parameters")
            
            for param_name, param_value in default_params.items():
                param_path = f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/defaults/{param_name}"
                
                # Create descriptive parameter description
                descriptions = {
                    "CACHE_TTL": f"Configuration cache TTL in seconds for {function_name}",
                    "HEALTH_CHECK_TIMEOUT": f"ALB health check timeout in seconds for {function_name}",
                    "HEALTH_CHECK_CACHE_TTL": f"Health check result cache TTL in seconds for {function_name}",
                    "MAINTENANCE_MODE": f"Maintenance mode toggle for {function_name}",
                    "GATE_ENABLED": f"IP gate toggle for {function_name}",
                    "ALLOW_CIDRS": f"Allowed CIDR blocks for {function_name}",
                    "HEALTH_CHECK_PATH": f"Health check endpoint path for {function_name}",
                    "ALB_DOMAIN": f"ALB DNS name for {function_name}",
                    "DEBUG_MODE": f"Debug mode toggle for {function_name}",
                    "CIRCUIT_BREAKER_THRESHOLD": f"Circuit breaker failure threshold for {function_name}",
                    "CIRCUIT_BREAKER_TIMEOUT": f"Circuit breaker timeout in seconds for {function_name}"
                }
                
                description = descriptions.get(param_name, f"Default parameter '{param_name}' for Lambda@Edge function {function_name}")
                
                self.export_ssm_parameter(
                    scope=self,
                    id=f"default-{param_name.lower()}-param",
                    value=str(param_value),
                    parameter_name=param_path,
                    description=description
                )

        # Resolve and export environment variables to SSM
        resolved_env = self._resolve_environment_variables()
        for env_key, env_value in resolved_env.items():
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
                        scope=self,
                        id=f"env-{env_key}-param",
                        value=env_value,
                        parameter_name=ssm_path,
                        description=f"Configuration for Lambda@Edge: {env_key}"
                    )
