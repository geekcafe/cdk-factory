"""
Lambda Deploy Role Stack — Cross-Account IAM Role for Lambda Image Updates

Creates an IAM role in the target (workload) account that allows the DevOps
account's CodeBuild pipeline to assume it and update Lambda function images.

This role is the "target side" counterpart to the AssumeRoleLambdaUpdater
policy created in the DevOps account's CodeBuild configuration. Together
they enable the Lambda Image Updater to perform cross-account deployments.

Trust: DevOps account (CodeBuild) → assumes this role
Permissions: SSM read (discover Lambda ARNs) + Lambda UpdateFunctionCode

Usage in stack config JSON:
{
    "name": "my-workload-lambda-deploy-role",
    "module": "lambda_deploy_role_stack",
    "enabled": true,
    "ssm": {
        "auto_export": true,
        "namespace": "my-workload/dev/iam/lambda-deploy-role"
    },
    "lambda_deploy_role": {
        "role_name": "DevOpsLambdaDeployRole",
        "devops_account": "{{DEVOPS_AWS_ACCOUNT}}",
        "ssm_resource_prefix": "*",
        "lambda_resource_prefix": "*"
    }
}

Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License. See Project Root for the license information.
"""

import cdk_nag
from aws_cdk import aws_iam as iam
from constructs import Construct
from aws_lambda_powertools import Logger

from cdk_factory.interfaces.istack import IStack
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin
from cdk_factory.stack.stack_module_registry import register_stack
from cdk_factory.configurations.stack import StackConfig
from cdk_factory.configurations.deployment import DeploymentConfig
from cdk_factory.workload.workload_factory import WorkloadConfig

logger = Logger(service="LambdaDeployRoleStack")


@register_stack("lambda_deploy_role_stack")
class LambdaDeployRoleStack(IStack, StandardizedSsmMixin):
    """
    Creates a cross-account IAM role for Lambda image deployment.

    This role is assumed by the Lambda Image Updater running in CodeBuild
    on the DevOps account. It grants the minimum permissions needed to:
    1. Discover Lambda functions via SSM parameters
    2. Read current Lambda function configuration
    3. Update Lambda function code with a new Docker image URI

    Configuration Fields (under "lambda_deploy_role"):
        role_name (str): IAM role name. Default: "DevOpsLambdaDeployRole"
        devops_account (str): AWS account ID of the DevOps/pipeline account (required)
        ssm_resource_prefix (str): SSM parameter path prefix to scope read access.
            Default: "*" (all parameters). Example: "my-app/*"
        lambda_resource_prefix (str): Lambda function name prefix to scope update access.
            Default: "*" (all functions). Example: "my-app-*"

    SSM Exports (when ssm.auto_export is true):
        /{namespace}/role_arn — The role ARN
        /{namespace}/role_name — The role name
    """

    DEFAULT_ROLE_NAME = "DevOpsLambdaDeployRole"

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        self.role: iam.Role | None = None
        self.stack_config: StackConfig | None = None
        self.deployment: DeploymentConfig | None = None
        self.workload: WorkloadConfig | None = None

    def build(
        self,
        stack_config: StackConfig,
        deployment: DeploymentConfig,
        workload: WorkloadConfig,
    ) -> None:
        self.stack_config = stack_config
        self.deployment = deployment
        self.workload = workload

        config = stack_config.dictionary.get("lambda_deploy_role", {})

        role_name = config.get("role_name", self.DEFAULT_ROLE_NAME)
        devops_account = config.get("devops_account")
        ssm_prefix = config.get("ssm_resource_prefix", "*")
        lambda_prefix = config.get("lambda_resource_prefix", "*")

        if not devops_account:
            raise ValueError(
                "lambda_deploy_role.devops_account is required. "
                "This is the AWS account ID of the DevOps/pipeline account "
                "that runs CodeBuild and the Lambda Image Updater."
            )

        # Trust policy: allow the DevOps account to assume this role
        self.role = iam.Role(
            self,
            "LambdaDeployRole",
            role_name=role_name,
            assumed_by=iam.AccountPrincipal(devops_account),
            description=(
                f"Allows the DevOps pipeline (account {devops_account}) to "
                f"discover and update Lambda function images in this account."
            ),
        )

        # SSM read — needed to discover Lambda ARNs via GetParametersByPath
        ssm_resource = (
            f"arn:aws:ssm:{deployment.region}:{deployment.account}"
            f":parameter/{ssm_prefix}"
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="SSMReadForLambdaDiscovery",
                effect=iam.Effect.ALLOW,
                actions=[
                    "ssm:GetParameter",
                    "ssm:GetParametersByPath",
                ],
                resources=[ssm_resource],
            )
        )

        # Lambda read + update — needed to get current image and deploy new one
        lambda_resource = (
            f"arn:aws:lambda:{deployment.region}:{deployment.account}"
            f":function:{lambda_prefix}"
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                sid="LambdaImageUpdate",
                effect=iam.Effect.ALLOW,
                actions=[
                    "lambda:GetFunction",
                    "lambda:UpdateFunctionCode",
                ],
                resources=[lambda_resource],
            )
        )

        # Suppress cdk-nag wildcard findings — the wildcards are intentionally
        # scoped to a prefix and needed because Lambda functions are discovered
        # dynamically via SSM at deploy time.
        cdk_nag.NagSuppressions.add_resource_suppressions(
            self.role,
            [
                cdk_nag.NagPackSuppression(
                    id="AwsSolutions-IAM5",
                    reason=(
                        "Wildcard resources are scoped to configured prefixes. "
                        "Lambda functions are discovered dynamically via SSM "
                        "by the Lambda Image Updater."
                    ),
                ),
            ],
            apply_to_children=True,
        )

        # Export role details to SSM
        self._export_ssm_parameters()

        logger.info(
            {
                "message": "Created Lambda deploy role",
                "role_name": role_name,
                "devops_account": devops_account,
                "ssm_prefix": ssm_prefix,
                "lambda_prefix": lambda_prefix,
            }
        )

    def _export_ssm_parameters(self) -> None:
        """Export role ARN and name to SSM for discoverability."""
        if not self.role or not self.stack_config:
            return

        if not self.stack_config.ssm_auto_export:
            return

        namespace = self.stack_config.ssm_namespace
        if not namespace:
            return

        prefix = f"/{namespace}"
        resource_values = {
            "role_arn": self.role.role_arn,
            "role_name": self.role.role_name,
        }

        for export_key, export_value in resource_values.items():
            parameter_path = f"{prefix}/{export_key}"
            self.export_ssm_parameter(
                scope=self,
                id=f"{self.node.id}-{export_key}",
                value=export_value,
                parameter_name=parameter_path,
                description=f"Lambda deploy role {export_key}",
            )

        logger.info(
            f"Exported {len(resource_values)} SSM parameters for Lambda deploy role"
        )
