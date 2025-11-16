"""
Geek Cafe, LLC
Maintainers: Eric Wilson
MIT License.  See Project Root for the license information.
"""

from aws_cdk import aws_iam as iam
from constructs import Construct

from cdk_factory.configurations.pipeline import PipelineConfig
from cdk_factory.configurations.resources.resource_types import ResourceTypes
from cdk_factory.configurations.workload import WorkloadConfig


class PipelineRoles:
    def __init__(
        self,
        scope: Construct,
        pipeline: PipelineConfig,
    ) -> None:
        # Parameters

        self.code_pipeline_service_role: iam.Role = (
            self.__create_code_pipeline_service_role(scope=scope, pipeline=pipeline)
        )

        self.code_artifact_access_role: iam.Role = (
            self.__create_code_artifact_access_role(scope=scope, pipeline=pipeline)
        )

    def __create_code_pipeline_service_role(
        self, scope: Construct, pipeline: PipelineConfig
    ):
        # CodePipeline Service Role
        role = iam.Role(
            scope,
            pipeline.build_resource_name(
                "CodePipeline-{{pipeline-name}}-{{environment}}",
                resource_type=ResourceTypes.IAM_ROLE,
                lower_case=False,
            ),
            assumed_by=iam.ServicePrincipal("codepipeline.amazonaws.com"),
        )

        # CodePipeline Service Role Policy
        statements = [
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetBucketVersioning",
                    "s3:PutObject",
                ],
                resources=[
                    "arn:aws:s3:::codepipeline*",
                    "arn:aws:s3:::elasticbeanstalk*",
                ],
                effect=iam.Effect.ALLOW,
            ),
            iam.PolicyStatement(
                actions=[
                    "codecommit:CancelUploadArchive",
                    "codecommit:GetBranch",
                    "codecommit:GetCommit",
                    "codecommit:GetUploadArchiveStatus",
                    "codecommit:UploadArchive",
                    "codecommit:GetRepository",
                    "codecommit:GitPull",
                    # "elasticbeanstalk:*",
                    "ec2:*",
                    # "elasticloadbalancing:*",
                    "autoscaling:*",
                    "cloudwatch:*",
                    "s3:*",
                    "sns:*",
                    "cloudformation:*",
                    # "rds:*",
                    "sqs:*",
                    # "ecs:*",
                    "ecr:*",
                    "iam:PassRole",
                    "codebuild:BatchGetBuilds",
                    "codebuild:StartBuild",
                    "ssm:*",
                    "codeartifact:GetAuthorizationToken",
                    "codeartifact:GetRepositoryEndpoint",
                    "codeartifact:ReadFromRepository",
                ],
                resources=["*"],
                effect=iam.Effect.ALLOW,
            ),
        ]

        for statement in statements:
            role.add_to_policy(statement)

        return role

    def __create_code_artifact_access_role(
        self, scope: Construct, pipeline: PipelineConfig
    ):
        # Define the CodeArtifact Access Role
        workload: WorkloadConfig = WorkloadConfig(pipeline.workload)
        role = iam.Role(
            scope=scope,
            id="CodeArtifactAccessRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("codebuild.amazonaws.com"),
                iam.AccountPrincipal(f"{workload.devops.account}"),
            ),
            role_name=pipeline.build_resource_name(
                "CodeArtifact-{{pipeline-name}}-{{environment}}",
                resource_type=ResourceTypes.IAM_ROLE,
                lower_case=False,
            ),
        )

        # Attach policies to the role to allow access to CodeArtifact
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "codeartifact:GetAuthorizationToken",
                    "codeartifact:GetRepositoryEndpoint",
                    "codeartifact:ReadFromRepository",
                    "sts:GetServiceBearerToken",
                ],
                resources=["*"],  # Restrict as necessary
            )
        )

        ecr_policy = iam.PolicyStatement(
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
        role.add_to_policy(ecr_policy)
                        

        return role
