"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import cast
from aws_cdk import Duration, RemovalPolicy, aws_ecr
from aws_cdk import CfnResource
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct, IConstruct
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.resources.ecr import ECRConfig as ECR
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment

logger = Logger(__name__)


class ECRConstruct(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        deployment: Deployment,
        repo: ECR,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.scope = scope
        self.deployment = deployment
        self.ecr_name = repo.name
        self.image_scan_on_push = repo.image_scan_on_push
        self.empty_on_delete = repo.empty_on_delete
        self.auto_delete_untagged_images_in_days = (
            repo.auto_delete_untagged_images_in_days
        )

        # set it all up
        self.ecr = self.__create_ecr()
        self.__set_life_cycle_rules()
        self.__create_parameter_store_values()
        self.__setup_cross_account_access_permissions()

    def __create_ecr(self) -> aws_ecr.Repository:
        # create the ecr repo
        name = self.deployment.build_resource_name(
            self.ecr_name, ResourceTypes.ECR_REPOSITORY
        )
        ecr_repository = aws_ecr.Repository(
            scope=self,
            id=self.deployment.build_resource_name(self.ecr_name),
            repository_name=name,
            # auto delete images after x days
            # auto_delete_images=self.empty_on_delete,
            # delete images when repo is destroyed
            empty_on_delete=self.empty_on_delete,
            # scan on push true/false
            image_scan_on_push=self.image_scan_on_push,
            # removal policy on delete destroy if empty on delete otherwise retain
            removal_policy=(
                RemovalPolicy.DESTROY if self.empty_on_delete else RemovalPolicy.RETAIN
            ),
        )

        return ecr_repository

    def __create_parameter_store_values(self):
        """
        Stores the ecr info in the parameter store for consumption in
        other cdk stacks.

        I tried storing this a JSON, but since it's a token being passed around
        I was having a dificult time consuming it on other places.
        """

        parameter_name = self.deployment.get_ssm_parameter_name(
            "ecr", self.ecr_name, "name"
        )
        name_param = ssm.StringParameter(
            scope=self,
            id=self.deployment.build_resource_name(f"{self.ecr_name}-ssm-ecr-name"),
            parameter_name=parameter_name,
            string_value=self.ecr.repository_name,
            description=f"{self.ecr_name} - Name Used for CDK deployments",
        )

        # Ensure the SSM parameter creation depends on the ECR repository creation
        if name_param.node.default_child and isinstance(
            name_param.node.default_child, CfnResource
        ):
            name_param.node.default_child.add_dependency(
                cast(CfnResource, self.ecr.node.default_child)
            )

        parameter_name = self.deployment.get_ssm_parameter_name(
            "ecr", self.ecr_name, "uri"
        )
        uri_param = ssm.StringParameter(
            scope=self,
            id=self.deployment.build_resource_name(f"{self.ecr_name}-ssm-erc-uri"),
            parameter_name=parameter_name,
            string_value=self.ecr.repository_uri,
            description=f"{self.ecr_name} - Uri Used for CDK deployments",
        )

        # Access the CloudFormation resource of the SSM parameter
        if uri_param.node.default_child and isinstance(
            uri_param.node.default_child, CfnResource
        ):
            uri_param.node.default_child.add_dependency(
                cast(CfnResource, self.ecr.node.default_child)
            )

        parameter_name = self.deployment.get_ssm_parameter_name(
            "ecr", self.ecr_name, "arn"
        )

        arn_param = ssm.StringParameter(
            scope=self,
            id=self.deployment.build_resource_name(f"{self.ecr_name}-ssm-erc-arn"),
            parameter_name=parameter_name,
            string_value=self.ecr.repository_arn,
            description=f"{self.ecr_name} - Arn Used for CDK deployments",
        )

        if arn_param.node.default_child and isinstance(
            arn_param.node.default_child, CfnResource
        ):
            arn_param.node.default_child.add_dependency(
                cast(CfnResource, self.ecr.node.default_child)
            )

    def __set_life_cycle_rules(self) -> None:
        # ToDo/FixMe: tag_pattern_list is not recognized in the current version in AWS

        try:
            # always keep images tagged as prod
            self.ecr.add_lifecycle_rule(
                tag_pattern_list=["prod*"], max_image_count=9999
            )
        except Exception as e:  # pylint: disable=w0718
            if "unexpected keyword argument" in str(e):
                logger.warning(
                    "tag_pattern_list is not available in this version of the aws cdk"
                )
            else:
                raise

        if not self.auto_delete_untagged_images_in_days:
            return None

        days = self.auto_delete_untagged_images_in_days

        logger.info(
            f"Adding life cycle policy.  Removing untagged images after {days} days"
        )
        # remove any untagged images after x days
        self.ecr.add_lifecycle_rule(
            tag_status=aws_ecr.TagStatus.UNTAGGED, max_image_age=Duration.days(days)
        )

    def __get_ecr(self) -> aws_ecr.IRepository:

        return aws_ecr.Repository.from_repository_arn(
            scope=self,
            id=f"{self.deployment.build_resource_name(self.ecr_name)}-by-attribute",
            # repository_name=self.ecr.repository_name,
            repository_arn=self.ecr.repository_arn,
        )

    def __setup_cross_account_access_permissions(self):
        # Cross-account access policy

        if self.deployment.account == self.deployment.workload.get("devops", {}).get(
            "account"
        ):
            # we're in the same account as the "devops" so we don't need cross account
            # permisions
            return

        ecr = self.ecr or self.__get_ecr()
        cross_account_policy_statement = iam.PolicyStatement(
            actions=[
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:BatchCheckLayerAvailability",
            ],
            principals=[
                iam.AccountPrincipal(self.deployment.account)
            ],  # Replace with the account ID of the Lambda function
            resources=[ecr.repository_arn],
            effect=iam.Effect.ALLOW,
        )

        # Attach the policy to the ECR repository
        response = ecr.add_to_resource_policy(cross_account_policy_statement)

        # fails, we're not adding it this way
        assert response.statement_added

        response = self.ecr.add_to_resource_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
                conditions={
                    "StringLike": {
                        "aws:sourceArn": [
                            f"arn:aws:lambda:{self.deployment.region}:{self.deployment.account}:function:*"
                        ]
                    }
                },
                resources=[ecr.repository_arn],
            )
        )

        assert response.statement_added
