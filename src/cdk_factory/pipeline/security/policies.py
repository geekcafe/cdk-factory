"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from typing import List

from aws_cdk import aws_iam as iam


from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.configurations.workload import WorkloadConfig
from cdk_factory.configurations.deployment import DeploymentConfig


class CodeBuildPolicy:
    """Code Build Policy Information"""

    def code_build_policies(
        self, pipeline: PipelineConfig, code_artifact_access_role: iam.Role
    ) -> List[iam.PolicyStatement]:
        """
        Generate the Code Build Polices
        """
        workload: WorkloadConfig = WorkloadConfig(pipeline.workload)
        code_build_policy = []

        if workload.management and workload.management.cross_account_role_arn:
            code_build_policy.append(
                # policy assumption on management account
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[workload.management.cross_account_role_arn],
                )
            )

        deployment: DeploymentConfig
        for deployment in pipeline.deployments:
            # target accounts
            if deployment.enabled:
                # TODO: make this a key/value in the config.json
                # e.g deployment.code_build_role
                # allow for hard coded value
                # -- cdk-hnb659fds-deploy-role-111111111-REGION
                # or do some string interpolation
                # -- cdk-hnb659fds-deploy-role-{{AWS-ACCOUNT}}-{{AWS-REGION}}
                cdk_role_name = f"cdk-hnb659fds-deploy-role-{deployment.account}-{deployment.region}"
                policy = iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["sts:AssumeRole"],
                    resources=[
                        f"arn:aws:iam::{deployment.account}:role/{cdk_role_name}"
                    ],
                )
                code_build_policy.append(policy)

        # add the ability to read and write to ecr

        policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["ecr:*"],
            resources=[
                (
                    "arn:aws:ecr:"
                    f"{workload.devops.region}:"
                    f"{workload.devops.account}:repository/*"
                )
            ],
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="ElasticContainerRegistryPolicy",
            actions=[
                "ecr:BatchCheckLayerAvailability",
                "ecr:CompleteLayerUpload",
                "ecr:GetAuthorizationToken",
                "ecr:InitiateLayerUpload",
                "ecr:PutImage",
                "ecr:UploadLayerPart",
            ],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="SSMPolicy",
            effect=iam.Effect.ALLOW,
            actions=["ssm:*"],
            resources=["*"],
        )
        code_build_policy.append(policy)

        policy = iam.PolicyStatement(
            sid="CodeArtifactPolicy",
            effect=iam.Effect.ALLOW,
            actions=[
                "codeartifact:GetAuthorizationToken",
                "codeartifact:GetRepositoryEndpoint",
                "codeartifact:ReadFromRepository",
                "sts:GetServiceBearerToken",
            ],
            resources=["*"],
        )
        code_build_policy.append(policy)

        # allow it to assume the code artifact role
        # which it will use to pass credentials to the docker build
        assume_codeartifact_role_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=["sts:AssumeRole"],
            resources=[f"{code_artifact_access_role.role_arn}"],
        )
        code_build_policy.append(assume_codeartifact_role_policy)

        # add ec2 policy
        policy = iam.PolicyStatement(
            sid="EC2Policy",
            effect=iam.Effect.ALLOW,
            actions=["ec2:*"],
            resources=["*"],
        )
        code_build_policy.append(policy)

        # S3 permissions for deployment scripts (error pages, static assets, etc.)
        # TODO: tighten security
        s3_policy = iam.PolicyStatement(
            sid="S3Policy",
            actions=[
                "s3:*",
            ],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
        code_build_policy.append(s3_policy)

        # TODO: allow users to add their own policies

        return code_build_policy
