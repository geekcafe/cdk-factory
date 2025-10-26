"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

import os
import cdk_nag
from aws_cdk import aws_ecr, aws_lambda
from aws_cdk import aws_iam as iam
from aws_lambda_powertools import Logger
from constructs import Construct
from cdk_factory.constructs.lambdas.lambda_function_role_construct import (
    LambdaRoleConstruct,
)
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment


from cdk_factory.configurations.resources.lambda_function import (
    LambdaFunctionConfig,
)
from cdk_factory.utilities.environment_services import EnvironmentServices
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.utilities.os_execute import OsExecute
from typing import List

logger = Logger(__name__)


class LambdaDockerConstruct(Construct):
    """
    Lambda Docker wrapper.

    """

    def __init__(
        self,
        scope: Construct,
        id: str,  # pylint: disable=W0622
        *,
        deployment: Deployment,
        workload: WorkloadConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.scope = scope
        self.deployment = deployment
        self.workload = workload

    def function(
        self,
        scope: Construct,
        deployment: Deployment,
        lambda_config: LambdaFunctionConfig,
        tag_or_digest: str | None = None,
        ecr_repo_name: str | None = None,
        ecr_arn: str | None = None,
        role: iam.Role | None = None,
        environment: dict | None = None,
    ) -> aws_lambda.DockerImageFunction:
        """
        Construct to create a lambda Docker deployment

        Args:
            scope (Construct): scope of the construct
            deployment (Deployment): Deployment Configuration Object

        Returns:
            aws_lambda.DockerImageFunction: Docker Image Function Reference
        """
        if not tag_or_digest:
            raise ValueError("tag_or_digest is required for a docker image function")

        if not role:
            role = LambdaRoleConstruct.Role(
                scope=scope,
                unique_id=lambda_config.name,
                deployment=deployment,
                lambda_config=lambda_config,
            )

        self.update_ecr_permissions(role=role, repo_arn=ecr_arn)
        self.update_role_permissions(role=role, lambda_config=lambda_config)
        function_id = deployment.build_resource_name(
            lambda_config.name, resource_type=ResourceTypes.LAMBDA_FUNCTION
        )
        environment_vars = EnvironmentServices.load_environment_variables(
            environment=environment,
            deployment=deployment,
            lambda_config=lambda_config,
            scope=self,
        )

        self.__suppress_nag(role=role)

        code: aws_lambda.DockerImageCode

        if lambda_config.docker.file:

            source = lambda_config.src
            if not os.path.exists(source):

                for dir in self.workload.paths:
                    if os.path.exists(os.path.join(dir, source)):
                        source = os.path.join(dir, source)
                        break
            if not os.path.exists(source):
                raise ValueError(f"Lambda Source directory {source} not found.")

            build_args = self.__process_build_args(lambda_config.docker.build_args)
            code = aws_lambda.DockerImageCode.from_image_asset(
                directory=source,
                build_args=build_args,
            )

        else:
            # get a reference to the ecr repository
            ecr_repository: aws_ecr.IRepository = self.get_ecr_repo(
                scope=scope,
                deployment=deployment,
                name=ecr_repo_name,
                arn=ecr_arn,
                function_name=lambda_config.name,
            )
            # important this needs to match an existing ECR
            code = aws_lambda.DockerImageCode.from_ecr(
                repository=ecr_repository,
                tag_or_digest=tag_or_digest,
            )

        function_name: str | None = None
        if not lambda_config.auto_name:
            function_name = function_id

        function = aws_lambda.DockerImageFunction(
            scope=scope,
            id=function_id,
            code=code,
            architecture=lambda_config.architecture,
            memory_size=lambda_config.memory_size,
            timeout=lambda_config.timeout,
            tracing=lambda_config.tracing,
            description=lambda_config.description,
            # environment_encryption=config.kms_key,
            environment=environment_vars,
            function_name=function_name,
            insights_version=lambda_config.insights_version,
            role=role.without_policy_updates(),
        )

        return function

    def __process_build_args(self, build_args: dict) -> dict:
        """
        Process the build args
        """
        process_args = {}
        # fixme
        # Add logic to process the build args
        for key, value in build_args.items():
            if "action:" in value:
                values = value.split(":")
                if values[0] == "action":
                    if values[1] == "generate_codeartifact_auth_token":

                        domain = values[2]
                        domain_owner = values[3]
                        duration = 900
                        profile: str | None = None
                        if len(values) == 5:
                            duration = values[4]
                        if len(values) == 6:
                            profile = values[5]

                        command = (
                            "aws codeartifact get-authorization-token "
                            f"--domain {domain} "
                            f"--domain-owner {domain_owner} "
                            "--query authorizationToken "
                            "--output text "
                            f"--duration-seconds {duration} "
                        )
                        code_build_id = os.getenv("CODEBUILD_BUILD_ID")

                        if profile and not code_build_id:
                            command += f"--profile {profile}"
                        commands = command.split(" ")
                        output = OsExecute.execute(commands=commands)

                        process_args[key] = output
                else:
                    raise ValueError(f"Invalid action {values[0]}")

            else:
                process_args[key] = value
        return process_args

    def update_role_permissions(
        self, role: iam.Role, lambda_config: LambdaFunctionConfig
    ) -> None:
        """
        Update the role to allow getting the ecr images
        """

        if not role:
            logger.warning("No role to update.")
            return

        permission: dict = {}
        for permission in lambda_config.permissions:
            actions: List[str] = []
            actions = permission.get("actions", [])
            resources = permission.get("resources", [])
            role.add_to_policy(
                iam.PolicyStatement(
                    actions=actions,
                    resources=resources,
                )
            )

    def update_ecr_permissions(self, role: iam.Role, repo_arn: str) -> None:
        """
        Update the role to allow getting the ecr images
        """

        if not role:
            logger.warning(f"No role to update for repo_arn {repo_arn}.")
            return

        if not repo_arn:
            logger.warning(
                "Missing repo arn.  This currently happens on first time deployments."
            )
            # we could use a wildcard here, but it's not recommended
            repo_arn = "*"
            # testing w/o first to see how it deploys
            return

        role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                resources=[
                    # use "*" for all repositories in the account (not advised)
                    repo_arn
                ],
            )
        )

    def get_ecr_repo(
        self,
        scope: Construct,
        deployment: Deployment,
        name: str,
        arn: str,
        function_name: str,
    ) -> aws_ecr.IRepository:
        """
        Get the repo
        The actual creation of the ecr repo is in a different stack (in the infrastructure stack)
        """

        ecr_repository = aws_ecr.Repository.from_repository_arn(
            scope=scope,
            id=deployment.build_resource_name(f"{name}-{function_name}-repo"),
            repository_arn=arn,
        )
        logger.info(
            {
                "item": "ecr_repository",
                "type": type(ecr_repository),
                "repo_name": name,
                "repo_arn": arn,
            }
        )
        return ecr_repository

    def __suppress_nag(self, role: iam.Role):
        # fixme
        # Add suppressions

        cdk_nag.NagSuppressions.add_resource_suppressions(
            role,
            suppressions=[
                {
                    "id": "AwsSolutions-IAM4",
                    "reason": "The AWSLambdaBasicExecutionRole is required for the basic Lambda execution and is managed by AWS.",
                    "appliesTo": [
                        "Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
                    ],
                },
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "The wildcard permissions are necessary for the Lambda function to access the bucket.",
                    "appliesTo": ["Resource::*"],
                },
            ],
        )
