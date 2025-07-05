"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_cdk import aws_iam as iam
from constructs import Construct
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.constructs.lambdas.policies.policy_docs import PolicyDocuments
from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.configurations.resources.resource_types import ResourceTypes


class LambdaRoleConstruct:
    @staticmethod
    def Role(
        scope: Construct,
        unique_id: str,
        deployment: Deployment,
        lambda_config: LambdaFunctionConfig,
    ) -> iam.Role:
        """Create the lambda role"""
        lambda_execution_role = iam.Role(
            scope,
            id=deployment.build_resource_name(
                f"{unique_id}-LambdaExecutionRole", ResourceTypes.IAM_ROLE
            ),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        )

        lambda_config.execution_role_arn = lambda_execution_role.role_arn
        lambda_config.execution_role_name = lambda_execution_role.role_name

        pd = PolicyDocuments(
            scope=scope,
            role=lambda_execution_role,
            deployment=deployment,
            lambda_config=lambda_config,
        )
        pd.generate_and_bind_lambda_policy_docs()

        return lambda_execution_role
