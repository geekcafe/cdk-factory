"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import cast, Dict
from aws_cdk import Duration, RemovalPolicy, aws_ecr
from aws_cdk import CfnResource
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ssm as ssm
from aws_lambda_powertools import Logger
from constructs import Construct, IConstruct
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.resources.ecr import ECRConfig as ECR
from cdk_factory.configurations.deployment import DeploymentConfig as Deployment
from cdk_factory.interfaces.standardized_ssm_mixin import StandardizedSsmMixin

logger = Logger(__name__)


class ECRConstruct(Construct, StandardizedSsmMixin):
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
        # Initialize StandardizedSsmMixin explicitly
        StandardizedSsmMixin.__init__(self, **kwargs)

        self.scope = scope
        self.deployment = deployment
        self.repo = repo
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
        other cdk stacks using the SsmParameterMixin.

        This method uses the new configurable SSM parameter prefix system.
        """
        # Check if SSM exports are configured
        if not hasattr(self.repo, 'ssm_exports') or not self.repo.ssm_exports:
            logger.debug("No SSM exports configured for ECR repository")
            return
        
        # Create a dictionary of resource values to export
        resource_values = {
            "name": self.ecr.repository_name,
            "uri": self.ecr.repository_uri,
            "arn": self.ecr.repository_arn
        }
        
        # Use the export_resource_to_ssm method from SsmParameterMixin
        params = self.export_resource_to_ssm(
            scope=self,
            resource_values=resource_values,
            config=self.repo,  # Pass the ECRConfig object which has ssm_exports
            resource_name=self.ecr_name,
            resource_type="ecr",
            context={
                "deployment_name": self.deployment.name,
                "environment": self.deployment.environment,
                "workload_name": self.deployment.workload_name
            }
        )
        
        # Add dependencies to ensure SSM parameters are created after the ECR repository
        if params:
            for param in params.values():
                if param and hasattr(param, 'node') and param.node.default_child and isinstance(param.node.default_child, CfnResource):
                    param.node.default_child.add_dependency(
                        cast(CfnResource, self.ecr.node.default_child)
                    )

    def __set_life_cycle_rules(self) -> None:
        # Note: tag_pattern_list is deprecated and causes circular dependencies in CDK synthesis
        # Only add lifecycle rule for untagged images if configured
        
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
        """
        Setup cross-account access permissions with flexible configuration support.
        
        Supports both legacy (default Lambda access) and new configurable approach.
        """
        # Check if cross-account access is disabled
        if not self.repo.cross_account_enabled:
            logger.info(f"Cross-account access disabled for {self.ecr_name}")
            return

        # Check if we're in the same account as devops
        if self.deployment.account == self.deployment.workload.get("devops", {}).get("account"):
            logger.info(f"Same account as devops, skipping cross-account permissions for {self.ecr_name}")
            return

        access_config = self.repo.cross_account_access
        
        if access_config and access_config.get("services"):
            # New configurable approach
            logger.info(f"Setting up configurable cross-account access for {self.ecr_name}")
            self.__setup_configurable_access(access_config)
        else:
            # Legacy approach - default Lambda access for backward compatibility
            logger.info(f"Setting up legacy cross-account access (Lambda only) for {self.ecr_name}")
            self.__setup_legacy_lambda_access()

    def __setup_configurable_access(self, access_config: dict):
        """Setup cross-account access using configuration"""
        
        # Get list of accounts (default to deployment account)
        accounts = access_config.get("accounts", [self.deployment.account])
        
        # Add account principal policies if accounts are specified
        if accounts:
            self.__add_account_principal_policy(accounts)
        
        # Add service-specific policies
        services = access_config.get("services", [])
        for service_config in services:
            self.__add_service_principal_policy(service_config)

    def __add_account_principal_policy(self, accounts: list):
        """Add policy for AWS account principals"""
        principals = [iam.AccountPrincipal(account) for account in accounts]
        
        policy_statement = iam.PolicyStatement(
            actions=[
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:BatchCheckLayerAvailability",
            ],
            principals=principals,
            effect=iam.Effect.ALLOW,
        )

        response = self.ecr.add_to_resource_policy(policy_statement)
        if not response.statement_added:
            logger.warning(f"Failed to add account principal policy for {', '.join(accounts)}")
        else:
            logger.info(f"Added account principal policy for accounts: {', '.join(accounts)}")

    def __add_service_principal_policy(self, service_config: dict):
        """Add policy for service principal (Lambda, ECS, CodeBuild, etc.)"""
        service_name = service_config.get("name", "unknown")
        service_principal = service_config.get("service_principal")
        actions = service_config.get("actions", ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"])
        conditions = service_config.get("condition")

        if not service_principal:
            # Infer service principal from common service names
            service_principal_map = {
                "lambda": "lambda.amazonaws.com",
                "ecs": "ecs-tasks.amazonaws.com",
                "ecs-tasks": "ecs-tasks.amazonaws.com",
                "codebuild": "codebuild.amazonaws.com",
                "codepipeline": "codepipeline.amazonaws.com",
                "ec2": "ec2.amazonaws.com",
            }
            service_principal = service_principal_map.get(service_name.lower())
            
        if not service_principal:
            logger.warning(f"Unknown service principal for service: {service_name}")
            return

        policy_statement = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=actions,
            principals=[iam.ServicePrincipal(service_principal)],
        )
        
        # Add conditions if specified
        if conditions:
            for condition_key, condition_value in conditions.items():
                policy_statement.add_condition(condition_key, condition_value)

        response = self.ecr.add_to_resource_policy(policy_statement)
        if not response.statement_added:
            logger.warning(f"Failed to add service principal policy for {service_name}")
        else:
            logger.info(f"Added service principal policy for {service_name} ({service_principal})")

    def __setup_legacy_lambda_access(self):
        """Legacy method: Setup default Lambda-only cross-account access"""
        
        # Add account principal policy
        self.__add_account_principal_policy([self.deployment.account])
        
        # Add Lambda service principal policy with default condition
        lambda_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
            principals=[iam.ServicePrincipal("lambda.amazonaws.com")],
        )
        
        lambda_policy.add_condition(
            "StringLike",
            {
                "aws:sourceArn": [
                    f"arn:aws:lambda:{self.deployment.region}:{self.deployment.account}:function:*"
                ]
            }
        )

        response = self.ecr.add_to_resource_policy(lambda_policy)
        if not response.statement_added:
            logger.warning("Failed to add Lambda service principal policy")
        else:
            logger.info("Added legacy Lambda service principal policy")
