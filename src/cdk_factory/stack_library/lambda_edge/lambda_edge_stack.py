"""
Lambda@Edge Stack Pattern for CDK-Factory
Supports deploying Lambda functions for CloudFront edge locations.
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

from typing import Optional
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_lambda_powertools import Logger
from constructs import Construct

from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.resources.lambda_edge import LambdaEdgeConfig
from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.enhanced_ssm_parameter_mixin import EnhancedSsmParameterMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="LambdaEdgeStack")


@register_stack("lambda_edge_library_module")
@register_stack("lambda_edge_stack")
class LambdaEdgeStack(IStack, EnhancedSsmParameterMixin):
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
        
        function_name = deployment.build_resource_name(self.edge_config.name)
        
        # Create Lambda function
        self._create_lambda_function(function_name)
        
        # Create version (required for Lambda@Edge)
        self._create_function_version(function_name)
        
        # Add outputs
        self._add_outputs(function_name)

    def _create_lambda_function(self, function_name: str) -> None:
        """Create the Lambda function"""
        
        # Resolve code path (relative to runtime directory or absolute)
        code_path = Path(self.edge_config.code_path)
        if not code_path.is_absolute():
            # Assume relative to the project root
            code_path = Path.cwd() / code_path
        
        if not code_path.exists():
            raise FileNotFoundError(
                f"Lambda code path does not exist: {code_path}\n"
                f"Current working directory: {Path.cwd()}"
            )
        
        logger.info(f"Loading Lambda code from: {code_path}")
        
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
        
        # Create execution role with CloudWatch Logs permissions
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
        
        # Create the Lambda function
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
            environment=self.edge_config.environment,
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
        
        # CloudFormation outputs
        cdk.CfnOutput(
            self,
            "FunctionName",
            value=self.function.function_name,
            description="Lambda function name",
            export_name=f"{function_name}-name"
        )
        
        cdk.CfnOutput(
            self,
            "FunctionArn",
            value=self.function.function_arn,
            description="Lambda function ARN (unversioned)",
            export_name=f"{function_name}-arn"
        )
        
        cdk.CfnOutput(
            self,
            "FunctionVersionArn",
            value=self.function_version.function_arn,
            description="Lambda function version ARN (use this for Lambda@Edge)",
            export_name=f"{function_name}-version-arn"
        )
        
        # SSM Parameter Store exports (if configured)
        ssm_exports = self.edge_config.dictionary.get("ssm_exports", {})
        if ssm_exports:
            export_values = {
                "function_name": self.function.function_name,
                "function_arn": self.function.function_arn,
                "function_version_arn": self.function_version.function_arn,
                "function_version": self.function_version.version,
            }
            
            self.store_ssm_parameters(self.edge_config, export_values)
