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
        # e.g., "{{ENVIRONMENT}}-{{WORKLOAD_NAME}}-ip-gate" becomes "tech-talk-dev-ip-gate"
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
        
        # Use the new simplified configuration structure
        configuration = self.edge_config.dictionary.get("configuration", {})
        runtime_config = configuration.get("runtime", {})
        ui_config = configuration.get("ui", {})
        
        for key, value in runtime_config.items():
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
        
        # Get the UI configuration
        configuration = self.edge_config.dictionary.get("configuration", {})
        ui_config = configuration.get("ui", {})
        

        workload_name = self.deployment.workload.get("name")

        if not workload_name:
            raise ValueError("Workload name is required for Lambda@Edge function")
        runtime_config = {
            'environment': self.deployment.environment,
            'workload': workload_name,
            'function_name': function_name,
            'region': self.deployment.region,
            'runtime': resolved_env,  # Runtime variables (SSM, etc.)
            'ui': ui_config  # UI configuration (colors, messages, etc.)
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
        configuration = self.edge_config.dictionary.get("configuration", {})
        runtime_config = configuration.get("runtime", {})
        
        if runtime_config:
            logger.warning(
                f"Lambda@Edge function '{function_name}' has environment variables configured, "
                "but Lambda@Edge does not support environment variables. The function must fetch these values from SSM Parameter Store at runtime."
            )
            for key, value in runtime_config.items():
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
        if runtime_config:
            execution_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath"
                    ],
                    resources=[
                        f"arn:aws:ssm:*:{self.deployment.account}:parameter/*"
                    ]
                )
            )
        
        # Add Secrets Manager permissions for origin secret access
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[
                    f"arn:aws:secretsmanager:*:{self.deployment.account}:secret:{self.deployment.environment}/{self.workload.name}/origin-secret*"
                ]
            )
        )
        
        # Add ELB permissions for target health API access
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "elasticloadbalancing:DescribeTargetHealth",
                    "elasticloadbalancing:DescribeTargetGroups",
                    "elasticloadbalancing:DescribeLoadBalancers",
                    "elasticloadbalancing:DescribeListeners",
                    "elasticloadbalancing:DescribeTags"
                ],
                resources=[
                    "*"
                ]
            )
        )
        
        # Add ACM permissions for certificate validation
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "acm:DescribeCertificate",
                    "acm:ListCertificates"
                ],
                resources=[
                    f"arn:aws:acm:*:{self.deployment.account}:certificate/*"
                ]
            )
        )
        
        # Add Route 53 permissions for health check access
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "route53:GetHealthCheckStatus",
                    "route53:ListHealthChecks",
                    "route53:GetHealthCheck"
                ],
                resources=[
                    f"arn:aws:route53:::{self.deployment.account}:health-check/*"
                ]
            )
        )
        
        # Add CloudWatch permissions for enhanced logging and metrics
        execution_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "cloudwatch:PutMetricData"
                ],
                resources=[
                    f"arn:aws:logs:*:{self.deployment.account}:log-group:/aws/lambda/*",
                    f"arn:aws:cloudwatch:*:{self.deployment.account}:metric:*"
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
        
        # we need to apply this later as the is created before the distribution
        # TODO: this would be created on a second pass (or in a later stage)
        if False:
            
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
        Configure log retention for Lambda@Edge log groups in all edge regions
        
        TODO: IMPLEMENT POST-DEPLOYMENT SOLUTION
        --------------------------------------
        Lambda@Edge log groups are created on-demand when the function is invoked
        at edge locations, not during deployment. This means we cannot set retention
        policies during CloudFormation deployment.
        
        Possible solutions to implement:
        1. EventBridge rule that triggers on log group creation
        2. Custom Lambda function that runs periodically to set retention
        3. Post-deployment script that waits for log groups to appear
        4. CloudWatch Logs subscription filter that handles new log groups
        
        Current behavior: DISABLED to prevent deployment failures
        """
        
        # DISABLED: Edge log groups don't exist during deployment
        # Lambda@Edge creates log groups on-demand at edge locations
        # Setting retention policies during deployment fails with "log group does not exist"
        
        edge_retention_days = self.edge_config.dictionary.get("edge_log_retention_days", 7)
        logger.warning(
            f"Edge log retention configuration disabled - log groups are created on-demand. "
            f"Desired retention: {edge_retention_days} days. "
            f"See TODO in _configure_edge_log_retention() for implementation approach."
        )
        
        # TODO: Implement one of these solutions:
        # 1. EventBridge + Lambda: Trigger on log group creation and set retention
        # 2. Periodic Lambda: Scan for edge log groups and apply retention policies  
        # 3. Post-deployment script: Wait for log groups to appear after edge replication
        # 4. CloudWatch Logs subscription: Process new log group events
        
        return

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
        
        # Export the complete configuration as a single SSM parameter
        config_ssm_path = f"/{self.deployment.environment}/{self.workload.name}/lambda-edge/config"
        configuration = self.edge_config.dictionary.get("configuration", {})
        environment_variables = configuration.get("environment_variables", {})
        
        # Build full configuration that Lambda@Edge expects
        full_config = {
            "environment_variables": environment_variables,
            "runtime": configuration.get("runtime", {}),
            "ui": configuration.get("ui", {})
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
